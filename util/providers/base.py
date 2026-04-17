from abc import ABC, abstractmethod


class MailProviderError(Exception):
    """邮箱 provider 统一异常类型。"""


class MailProvider(ABC):
    """邮箱 provider 抽象接口。"""

    name = "base"

    @abstractmethod
    def create_temp_email(self):
        """创建临时邮箱，返回 (email, password, mail_token)。"""

    @abstractmethod
    def fetch_emails(self, mail_token):
        """获取邮件列表。"""

    @abstractmethod
    def fetch_email_detail(self, mail_token, msg_id):
        """获取单封邮件详情。"""

    def get_current_ids(self, mail_token=None):
        """可选：在触发发码前抓取邮箱快照 ID 集合。"""
        _ = mail_token
        return set()

    def wait_for_verification_email(
        self,
        mail_token,
        timeout=120,
        before_ids=None,
        logger=None,
    ):
        """可选：provider 自定义的验证码等待逻辑。"""
        _ = (mail_token, timeout, before_ids, logger)
        return None
