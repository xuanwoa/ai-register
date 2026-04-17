import email
import csv
import io
import imaplib
import os
import re
import threading
import time
from email.header import decode_header

from util import get_logger
from util.providers.base import MailProvider, MailProviderError


logger = get_logger("icloud")


def _decode_mime_header(value):
    if not value:
        return ""
    try:
        parts = decode_header(value)
    except Exception:
        return str(value)

    out = []
    for part, encoding in parts:
        if isinstance(part, bytes):
            enc = encoding or "utf-8"
            try:
                out.append(part.decode(enc, errors="ignore"))
            except Exception:
                out.append(part.decode("utf-8", errors="ignore"))
        else:
            out.append(str(part))
    return "".join(out)


def _load_aliases_from_file(path):
    aliases = []
    if not path:
        return aliases
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        raise MailProviderError(f"icloud.aliases_file 不存在: {path}")

    if not str(raw or "").strip():
        return aliases

    lines = raw.splitlines()
    header = (lines[0] if lines else "").strip().lower()

    # 兼容 vaultwarden/csv 导出：从 login_username（优先）或 name 字段提取 icloud 邮箱
    if "," in header and "login_username" in header:
        email_pattern = re.compile(r"([a-z0-9._%+\-]+@icloud\.com)", re.IGNORECASE)
        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            if not isinstance(row, dict):
                continue
            candidate_fields = [
                str(row.get("login_username") or "").strip(),
                str(row.get("name") or "").strip(),
            ]
            matched = ""
            for field in candidate_fields:
                m = email_pattern.search(field)
                if m:
                    matched = m.group(1)
                    break
            if matched:
                aliases.append(matched)
        return aliases

    # 兼容旧格式：每行一个邮箱
    for line in lines:
        v = str(line or "").strip()
        if not v or v.startswith("#"):
            continue
        aliases.append(v)
    return aliases


class IcloudAliasManager:
    _LOCK = threading.Lock()
    _POOL = {}

    def __init__(
        self,
        imap_username: str,
        app_password: str,
        aliases=None,
        aliases_file=None,
        state_dir=None,
    ):
        self.imap_username = str(imap_username or "").strip()
        self.app_password = str(app_password or "").strip()
        self.state_dir = str(state_dir or "").strip()
        self._resolved_state_dir = ""

        loaded_aliases = []
        if isinstance(aliases, list):
            loaded_aliases.extend([str(x).strip() for x in aliases if str(x or "").strip()])
        loaded_aliases.extend(_load_aliases_from_file(aliases_file))

        uniq = []
        seen = set()
        for a in loaded_aliases:
            key = a.lower()
            if key in seen:
                continue
            seen.add(key)
            uniq.append(a)

        if not self.imap_username:
            raise MailProviderError("mail_providers.icloud.imap_username 未配置")
        if not self.app_password:
            raise MailProviderError("mail_providers.icloud.app_password 未配置")
        if not uniq:
            raise MailProviderError("mail_providers.icloud.aliases / aliases_file 至少配置一个邮箱")

        if self.imap_username.lower() in {x.lower() for x in uniq}:
            logger.warning("检测到 aliases 池包含 IMAP 主账号: {}（仅在你显式配置时才会出现）", self.imap_username)

        self.aliases = uniq
        self._resolved_state_dir = self._resolve_state_dir()
        logger.info(
            "iCloud alias 管理器初始化 | imap_user={} | aliases_total={} | aliases_file={} | state_dir={}",
            self.imap_username,
            len(self.aliases),
            aliases_file or "",
            self._resolved_state_dir,
        )
        self._init_pool()

    def _resolve_state_dir(self) -> str:
        state_dir = self.state_dir
        if state_dir:
            state_dir = os.path.expanduser(state_dir)
            if not os.path.isabs(state_dir):
                state_dir = os.path.join(os.getcwd(), state_dir)
        else:
            state_dir = os.path.join(os.getcwd(), "token_dir", "icloud")
        os.makedirs(state_dir, exist_ok=True)
        return state_dir

    def _state_file(self, name: str) -> str:
        folder = self._resolved_state_dir
        return os.path.join(folder, name)

    def _read_alias_set(self, filename: str):
        path = self._state_file(filename)
        out = set()
        if not path or not os.path.exists(path):
            return out
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    v = str(line or "").strip()
                    if not v or v.startswith("#"):
                        continue
                    out.add(v.lower())
        except Exception:
            return out
        return out

    def _write_alias_set(self, filename: str, values):
        path = self._state_file(filename)
        if not path:
            return
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for item in sorted({str(x).strip().lower() for x in values if str(x).strip()}):
                f.write(item + "\n")

    def _init_pool(self):
        user_key = self.imap_username.lower()
        with self._LOCK:
            if user_key in self._POOL:
                return

            state_dir = self._resolved_state_dir

            registered = self._read_alias_set("registered_aliases.txt")
            in_use = self._read_alias_set("in_use_aliases.txt")

            aliases = self.aliases.copy()
            available = [
                a
                for a in aliases
                if a.lower() not in registered and a.lower() not in in_use
            ]

            # 兜底：处理“上次异常退出导致 in_use 残留”场景。
            # 当 available 为空，但仍存在“未注册却在 in_use”邮箱时，自动回收。
            if not available:
                recyclable = [a for a in aliases if a.lower() in in_use and a.lower() not in registered]
                if recyclable:
                    logger.warning(
                        "检测到可回收的 in_use 残留 alias，自动回收 | recyclable={} | state_dir={}",
                        recyclable,
                        state_dir,
                    )
                    recyclable_keys = {x.lower() for x in recyclable}
                    in_use = {x for x in in_use if x not in recyclable_keys}
                    available = recyclable.copy()
                    self._write_alias_set("in_use_aliases.txt", in_use)

            self._POOL[user_key] = {
                "available": available,
                "in_use": in_use,
                "registered": registered,
                "state_dir": state_dir,
            }
            logger.info(
                "alias 池已初始化 | user={} | total={} | available={} | in_use={} | registered={} | state_dir={}",
                self.imap_username,
                len(self.aliases),
                len(available),
                len(in_use),
                len(registered),
                state_dir,
            )

    def _get_state(self):
        user_key = self.imap_username.lower()
        state = self._POOL.get(user_key)
        if not isinstance(state, dict):
            raise MailProviderError("icloud alias 状态未初始化")
        return state

    def get_next_alias(self) -> str:
        with self._LOCK:
            state = self._get_state()
            available = state.get("available") or []
            if not available:
                registered = state.get("registered") or set()
                in_use = state.get("in_use") or set()
                raise MailProviderError(
                    "iCloud aliases 已耗尽，请扩容 aliases 列表或清理 state_dir。"
                    f" aliases_total={len(self.aliases)}"
                    f" registered={len(registered)}"
                    f" in_use={len(in_use)}"
                    f" state_dir={self._resolved_state_dir}"
                )
            alias = str(available.pop(0)).strip()
            if alias:
                in_use = state.get("in_use") or set()
                in_use.add(alias.lower())
                state["in_use"] = in_use
                self._write_alias_set("in_use_aliases.txt", in_use)
                logger.info(
                    "分配 alias 成功 | alias={} | remaining_available={} | in_use_count={}",
                    alias,
                    len(available),
                    len(in_use),
                )
            return alias

    def mark_registered(self, alias: str):
        normalized = str(alias or "").strip().lower()
        if not normalized:
            return
        with self._LOCK:
            state = self._get_state()
            registered = state.get("registered") or set()
            in_use = state.get("in_use") or set()
            registered.add(normalized)
            in_use.discard(normalized)
            state["registered"] = registered
            state["in_use"] = in_use
            self._write_alias_set("registered_aliases.txt", registered)
            self._write_alias_set("in_use_aliases.txt", in_use)
            logger.info(
                "alias 标记为已注册 | alias={} | registered_count={} | in_use_count={}",
                normalized,
                len(registered),
                len(in_use),
            )

    def release_alias(self, alias: str):
        normalized = str(alias or "").strip().lower()
        if not normalized:
            return
        with self._LOCK:
            state = self._get_state()
            in_use = state.get("in_use") or set()
            registered = state.get("registered") or set()
            available = state.get("available") or []

            in_use.discard(normalized)
            if normalized not in registered:
                alias_map = {str(a).lower(): str(a) for a in self.aliases}
                original = alias_map.get(normalized, normalized)
                if normalized not in {str(x).lower() for x in available}:
                    available.append(original)
            state["in_use"] = in_use
            state["available"] = available
            self._write_alias_set("in_use_aliases.txt", in_use)
            logger.info(
                "alias 已释放 | alias={} | available_count={} | in_use_count={} | registered_count={}",
                normalized,
                len(available),
                len(in_use),
                len(registered),
            )

    def get_imap_credentials(self):
        return self.imap_username, self.app_password


class RobustIcloudMailbox:
    def __init__(
        self,
        manager: IcloudAliasManager,
        *,
        strict_recipient_match: bool = True,
        allow_verification_fallback: bool = False,
    ):
        self.username, self.password = manager.get_imap_credentials()
        self.host = "imap.mail.me.com"
        self.folders = ["INBOX", "Junk"]
        self.strict_recipient_match = bool(strict_recipient_match)
        self.allow_verification_fallback = bool(allow_verification_fallback)

    def _connect(self):
        logger.info("连接 iCloud IMAP | host={} | user={}", self.host, self.username)
        try:
            mail = imaplib.IMAP4_SSL(self.host, 993)
            mail.login(self.username, self.password)
            logger.info("iCloud IMAP 登录成功 | user={}", self.username)
            return mail
        except Exception as exc:
            logger.error("iCloud IMAP 连接/登录失败 | user={} | err={}", self.username, exc)
            raise

    def get_current_ids(self):
        mail = self._connect()
        current_ids = set()
        try:
            for folder in self.folders:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK":
                    logger.warning("IMAP 选择文件夹失败 | folder={} | status={}", folder, status)
                    continue
                status, data = mail.search(None, "ALL")
                if status == "OK" and data and data[0]:
                    for r_id in data[0].split():
                        current_ids.add(f"{folder}:{r_id.decode('utf-8')}")
                logger.info(
                    "IMAP 文件夹快照完成 | folder={} | message_count={}",
                    folder,
                    len(data[0].split()) if (status == "OK" and data and data[0]) else 0,
                )
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        logger.info("IMAP 当前邮件 ID 快照完成 | total_ids={}", len(current_ids))
        return current_ids

    def _fetch_raw_email(self, mail, msg_id):
        status, msg_data = mail.fetch(msg_id, "(BODY.PEEK[])")
        if status != "OK" or not msg_data:
            return None
        for item in msg_data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], (bytes, bytearray)):
                return bytes(item[1])
        return None

    def _parse_message(self, folder, msg_id, raw_email):
        msg = email.message_from_bytes(raw_email)
        subject = _decode_mime_header(msg.get("Subject") or "")
        sender = _decode_mime_header(msg.get("From") or "")
        recipient = _decode_mime_header(msg.get("To") or "")
        cc = _decode_mime_header(msg.get("Cc") or "")
        delivered_to = _decode_mime_header(msg.get("Delivered-To") or "")
        original_to = _decode_mime_header(msg.get("X-Original-To") or "")
        date = _decode_mime_header(msg.get("Date") or "")

        text_content = ""
        html_content = ""
        if msg.is_multipart():
            for part in msg.walk():
                ctype = str(part.get_content_type() or "").lower()
                payload = part.get_payload(decode=True)
                if not isinstance(payload, (bytes, bytearray)):
                    continue
                decoded = payload.decode(errors="ignore")
                if ctype == "text/plain":
                    text_content += decoded + "\n"
                elif ctype == "text/html":
                    html_content += decoded + "\n"
        else:
            payload = msg.get_payload(decode=True)
            if isinstance(payload, (bytes, bytearray)):
                decoded = payload.decode(errors="ignore")
                ctype = str(msg.get_content_type() or "").lower()
                if ctype == "text/html":
                    html_content = decoded
                else:
                    text_content = decoded

        gid = f"{folder}:{msg_id.decode('utf-8')}"
        return {
            "id": gid,
            "folder": folder,
            "subject": subject,
            "from": sender,
            "to": recipient,
            "cc": cc,
            "delivered_to": delivered_to,
            "original_to": original_to,
            "text": text_content,
            "html": html_content,
            "date": date,
        }

    @staticmethod
    def _looks_like_verification_email(parsed: dict) -> bool:
        if not isinstance(parsed, dict):
            return False
        subject = str(parsed.get("subject") or "")
        sender = str(parsed.get("from") or "")
        text = str(parsed.get("text") or "")
        html = str(parsed.get("html") or "")
        combined = "\n".join([subject, sender, text[:800], html[:800]])
        lower = combined.lower()

        keywords = [
            "verification",
            "verify",
            "otp",
            "one-time",
            "security code",
            "验证码",
            "openai",
            "x.ai",
            "grok",
        ]
        has_keyword = any(k in lower for k in keywords)
        has_code = bool(
            re.search(r"(?<![A-Z0-9-])[A-Z0-9]{3}-[A-Z0-9]{3}(?![A-Z0-9-])", combined)
            or re.search(r"(?<![a-zA-Z0-9])(\d{6})(?![a-zA-Z0-9])", combined)
        )
        return has_keyword or has_code

    @staticmethod
    def _extract_emails(value: str):
        if not value:
            return set()
        return {
            m.group(1).strip().lower()
            for m in re.finditer(r"([a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,})", str(value), re.IGNORECASE)
            if m and m.group(1)
        }

    def _match_recipient_hint(self, parsed: dict, hint: str) -> bool:
        if not hint:
            return True
        if not isinstance(parsed, dict):
            return False

        normalized_hint = str(hint or "").strip().lower()
        if not normalized_hint:
            return True

        if self.strict_recipient_match:
            header_values = [
                str(parsed.get("to") or ""),
                str(parsed.get("cc") or ""),
                str(parsed.get("delivered_to") or ""),
                str(parsed.get("original_to") or ""),
            ]
            header_emails = set()
            for item in header_values:
                header_emails.update(self._extract_emails(item))
            return normalized_hint in header_emails

        recipients = " ".join(
            [
                str(parsed.get("to") or ""),
                str(parsed.get("cc") or ""),
                str(parsed.get("delivered_to") or ""),
                str(parsed.get("original_to") or ""),
                str(parsed.get("text") or "")[:200],
                str(parsed.get("html") or "")[:200],
            ]
        ).lower()
        return normalized_hint in recipients

    def fetch_recent_messages(self, before_ids=None, recipient_hint=None, max_per_folder=60):
        before = set(str(x) for x in (before_ids or set()))
        hint = str(recipient_hint or "").strip().lower()
        logger.info(
            "开始拉取 iCloud 邮件 | before_ids={} | recipient_hint={} | max_per_folder={}",
            len(before),
            hint or "<none>",
            max_per_folder,
        )

        mail = self._connect()
        out = []
        try:
            for folder in self.folders:
                status, _ = mail.select(folder, readonly=True)
                if status != "OK":
                    logger.warning("IMAP 选择文件夹失败 | folder={} | status={}", folder, status)
                    continue
                status, data = mail.search(None, "ALL")
                if status != "OK" or not data or not data[0]:
                    logger.info("文件夹无可扫描邮件 | folder={} | status={}", folder, status)
                    continue

                raw_ids = data[0].split()
                scanned = 0
                matched = 0
                new_candidates = 0
                filtered_by_hint = 0
                fallback_by_verification = 0
                for r_id in reversed(raw_ids):
                    gid = f"{folder}:{r_id.decode('utf-8')}"
                    if gid in before:
                        continue
                    new_candidates += 1

                    raw_email = self._fetch_raw_email(mail, r_id)
                    if not raw_email:
                        continue
                    parsed = self._parse_message(folder, r_id, raw_email)
                    if not isinstance(parsed, dict):
                        continue

                    if hint and (not self._match_recipient_hint(parsed, hint)):
                        if self.allow_verification_fallback and self._looks_like_verification_email(parsed):
                            fallback_by_verification += 1
                            logger.warning(
                                "recipient_hint 未命中，但已启用验证码兜底放行 | hint={} | msg_id={} | subject={} | from={}",
                                hint,
                                parsed.get("id") or "",
                                parsed.get("subject") or "",
                                parsed.get("from") or "",
                            )
                        else:
                            filtered_by_hint += 1
                            continue

                    out.append(parsed)
                    scanned += 1
                    matched += 1
                    if scanned >= max_per_folder:
                        break

                logger.info(
                    "文件夹扫描完成 | folder={} | total={} | new_candidates={} | matched={} | filtered_by_hint={} | fallback_by_verification={} | collected_total={}",
                    folder,
                    len(raw_ids),
                    new_candidates,
                    matched,
                    filtered_by_hint,
                    fallback_by_verification,
                    len(out),
                )
        finally:
            try:
                mail.logout()
            except Exception:
                pass
        logger.info("iCloud 拉信完成 | collected_messages={}", len(out))
        return out


class IcloudMailProvider(MailProvider):
    name = "icloud"

    def __init__(
        self,
        imap_username,
        app_password,
        aliases=None,
        aliases_file=None,
        state_dir=None,
        strict_recipient_match=True,
        allow_verification_fallback=False,
        **kwargs,
    ):
        _ = kwargs
        self.manager = IcloudAliasManager(
            imap_username=imap_username,
            app_password=app_password,
            aliases=aliases,
            aliases_file=aliases_file,
            state_dir=state_dir,
        )
        self.mailbox = RobustIcloudMailbox(
            self.manager,
            strict_recipient_match=strict_recipient_match,
            allow_verification_fallback=allow_verification_fallback,
        )

    def create_temp_email(self):
        alias = self.manager.get_next_alias()
        # iCloud 不需要额外邮箱密码，mail_token 复用 alias 作为收件过滤提示。
        logger.info("本次注册使用 alias: {}", alias)
        return alias, "", alias

    def fetch_emails(self, mail_token):
        try:
            return self.mailbox.fetch_recent_messages(recipient_hint=mail_token)
        except Exception as exc:
            logger.error("fetch_emails 失败 | token={} | err={}", mail_token, exc)
            return []

    def fetch_email_detail(self, mail_token, msg_id):
        _ = mail_token
        if not isinstance(msg_id, str) or ":" not in msg_id:
            return None

        folder, raw = msg_id.split(":", 1)
        if not folder or not raw.isdigit():
            return None

        mail = self.mailbox._connect()
        try:
            status, _ = mail.select(folder, readonly=True)
            if status != "OK":
                logger.warning("fetch_email_detail 选择文件夹失败 | folder={} | status={}", folder, status)
                return None
            raw_email = self.mailbox._fetch_raw_email(mail, raw.encode("utf-8"))
            if not raw_email:
                logger.warning("fetch_email_detail 未取到原始邮件 | msg_id={}", msg_id)
                return None
            parsed = self.mailbox._parse_message(folder, raw.encode("utf-8"), raw_email)
            if not isinstance(parsed, dict):
                logger.warning("fetch_email_detail 解析邮件失败 | msg_id={}", msg_id)
                return None
            return parsed
        except Exception as exc:
            logger.error("fetch_email_detail 异常 | msg_id={} | err={}", msg_id, exc)
            return None
        finally:
            try:
                mail.logout()
            except Exception:
                pass

    def get_current_ids(self, mail_token=None):
        _ = mail_token
        try:
            return self.mailbox.get_current_ids()
        except Exception as exc:
            logger.error("get_current_ids 失败 | err={}", exc)
            return set()

    @staticmethod
    def _extract_verification_code(content: str):
        if not content:
            return None

        # 优先匹配 xAI 常见 3-3 验证码，再匹配 6 位数字。
        # 注意：3-3 模式必须保持大小写敏感，避免把 HTML/CSS 片段（如 font-family）误识别为验证码。
        patterns = [
            r"(?<![A-Z0-9-])([A-Z0-9]{3}-[A-Z0-9]{3})(?![A-Z0-9-])",
            r"(?i:(?:verification code|验证码|your code))[:\s]*[<>\s]*([A-Z0-9]{3}-[A-Z0-9]{3})\b",
            r"background-color:\s*#F3F3F3[^>]*>[\s\S]*?([A-Z0-9]{3}-[A-Z0-9]{3})[\s\S]*?</p>",
            r"Subject:.*?(\d{6})",
            r">\s*(\d{6})\s*<",
            r"(?<![&#\d])(\d{6})(?![&#\d])",
        ]

        for pattern in patterns:
            m = re.search(pattern, content)
            if not m:
                continue
            code = str(m.group(1) or "").strip()
            if not code or code == "177010":
                continue
            return code
        return None

    def wait_for_verification_email(self, mail_token, timeout=120, before_ids=None, logger=None):
        seen = set(str(x) for x in (before_ids or set()))
        deadline = time.time() + int(timeout or 0)
        poll_round = 0
        internal_logger = globals().get("logger")

        while time.time() < deadline:
            poll_round += 1
            messages = self.mailbox.fetch_recent_messages(before_ids=seen, recipient_hint=mail_token)
            if internal_logger:
                internal_logger.info(
                    "验证码轮询 | round={} | token={} | fetched={} | seen_ids={}",
                    poll_round,
                    mail_token,
                    len(messages),
                    len(seen),
                )
            for msg in messages:
                if not isinstance(msg, dict):
                    continue
                msg_id = str(msg.get("id") or "")
                if msg_id:
                    seen.add(msg_id)

                subject = str(msg.get("subject") or "")
                text = str(msg.get("text") or "")
                html = str(msg.get("html") or "")

                # 先扫 subject + text/plain，尽量避免 HTML 模板噪声抢先命中。
                code = self._extract_verification_code("\n".join([subject, text]))
                if not code and html:
                    code = self._extract_verification_code(html)
                if code:
                    normalized = code.replace("-", "")
                    if internal_logger:
                        internal_logger.info(
                            "命中验证码 | msg_id={} | raw_code={} | normalized_code={}",
                            msg_id,
                            code,
                            normalized,
                        )
                    return normalized

            if logger:
                logger("等待 iCloud 验证码中...")
            time.sleep(4)

        if internal_logger:
            internal_logger.warning(
                "等待 iCloud 验证码超时 | token={} | timeout={}s | seen_ids={}",
                mail_token,
                timeout,
                len(seen),
            )
        return None

    def mark_alias_registered(self, alias):
        self.manager.mark_registered(alias)

    def release_alias(self, alias):
        self.manager.release_alias(alias)
