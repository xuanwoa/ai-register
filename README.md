# ai-register

中文 | [English](README_en.md)

轻量的批量注册脚本工具，支持 OpenAI 与 Grok 两套注册流程，以及临时邮箱验证码读取（duckmail / tempmail / iCloud）和可选的 CPA/Grok2API 上传。

> 当前默认邮箱 provider 为 `icloud`，默认从 `data/icloud_aliases.txt` 读取别名池。

## 功能特性

- 并发批量执行
- 可切换邮箱 provider（duckmail / tempmail / icloud）
- 支持 OpenAI OAuth 与 Grok provider 切换
- 支持 [CPA](https://github.com/router-for-me/CLIProxyAPI) 上传
- 支持 [grok2api](https://github.com/chenyme/grok2api) 上传

## 快速开始

### 1) 安装依赖

方式 A（推荐，uv）:

```bash
uv sync
```

方式 B（pip）:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) 初始化配置

```bash
cp config.example.yaml config.yaml
```

然后填写敏感项:

- `mail_providers.duckmail.bearer`
- `mail_providers.tempmail.api_key`
- `mail_providers.icloud.imap_username` + `mail_providers.icloud.app_password`（使用 iCloud 时）
- `data/icloud_aliases.txt`（默认别名文件，每行一个邮箱）
- `cpa.token`（仅在启用 CPA 上传时需要）

### 3) 启动

入口统一使用 `main.py`。

先做配置检查:

```bash
python main.py
```

执行批量流程:

```bash
python main.py
```

通过 `config.yaml` 里的 `model_provider` 选择执行 `openai` 或 `grok`。

## 配置说明

| 字段 | 说明                                   |
| --- |--------------------------------------|
| `concurrency` | 并发数                                  |
| `total_accounts` | 目标注册账号总数                             |
| `proxy` | 全局代理，留空表示不使用                         |
| `token_dir` | token 输出目录                           |
| `model_provider` | 模型 provider 名称（`openai` / `grok`）    |
| `model_providers.openai.*` | OpenAI OAuth 配置                      |
| `model_providers.grok.browser_proxy` | Grok 浏览器代理配置                         |
| `mail_provider` | 邮箱 provider（`duckmail` / `tempmail` / `icloud`） |
| `mail_providers.duckmail.*` | DuckMail 配置                          |
| `mail_providers.tempmail.*` | TempMail 配置                          |
| `mail_providers.icloud.imap_username` | iCloud 主账号（IMAP 登录账号）                  |
| `mail_providers.icloud.app_password` | iCloud App 专用密码（不是 Apple ID 登录密码）     |
| `mail_providers.icloud.aliases` | iCloud 别名池（可含主账号）                      |
| `mail_providers.icloud.aliases_file` | iCloud 别名文件（每行一个邮箱，支持注释）             |
| `mail_providers.icloud.state_dir` | iCloud 别名状态目录（保存 `in_use_aliases.txt` / `registered_aliases.txt`） |
| `cpa.enable` | 是否启用 CPA 上传                          |
| `cpa.api_url` | CPA 上传接口地址                           |
| `cpa.token` | CPA 登录 token                         |
| `g2a.enable` | 是否启用 Grok2API 上传                     |
| `g2a.api_url` | Grok2API 上传接口地址                      |
| `g2a.token` | Grok2API 登录 token                    |
| `cpa.use_proxy` | 上传 CPA 时是否强制使用全局 `proxy`（默认 false；为 true 时使用 `proxy`，否则本地地址可能绕过代理） |
| `g2a.use_proxy` | 上传 Grok2API 时是否强制使用全局 `proxy`（默认 false；为 true 时使用 `proxy`，否则本地地址可能绕过代理） |

示例配置请参考 [config.example.yaml](config.example.yaml)。

## iCloud 接码注意事项

- iCloud 必须使用 **App 专用密码**，不能使用 Apple ID 登录密码。
- 系统会在触发发码前自动抓取邮箱快照（`before_ids`），之后仅解析新增邮件，避免误读历史验证码。
- iCloud provider 会同时扫描 `INBOX` 与 `Junk`，并使用 `Folder:ID` 复合 ID 规避文件夹 ID 冲突。
- 底层 IMAP 拉取采用 `BODY.PEEK[]`，规避 iCloud `RFC822` 空包问题。
- 注册成功后会调用 `mark_alias_registered(email)` 固化别名状态；失败时会调用 `release_alias(email)` 释放占用别名。

## 账号凭据落盘规则

- OpenAI 与 Grok 注册成功后，都会将 `email + password` 追加写入：
  - `<token_dir>/<model_provider>/accounts.txt`
- 每行格式为：`email<TAB>password`
- 示例：`token_dir/openai/accounts.txt`、`token_dir/grok/accounts.txt`

## iCloud 配置教程（可直接照抄）

### 1) 在 Apple ID 里生成 App 专用密码

1. 登录 Apple ID 管理页（账户安全）。
2. 找到 **App 专用密码**，新建一个密码（例如命名 `ai-register`）。
3. 得到类似 `abcd-efgh-ijkl-mnop` 的密码字符串。

> 注意：这里必须是 App 专用密码，不是 Apple ID 登录密码。

### 2) 在 `config.yaml` 启用 iCloud provider

默认已是 `mail_provider: "icloud"`。只需填写主账号和别名池：

```yaml
mail_provider: "icloud"

mail_providers:
  icloud:
    # 主账号（IMAP 登录账号）
    imap_username: "main_account@icloud.com"
    # Apple ID 里创建的 App 专用密码
    app_password: "abcd-efgh-ijkl-mnop"

    # 方式 A：直接写别名池（推荐先用这个）
    aliases:
      - "alias_1@icloud.com"
      - "alias_2@icloud.com"
      - "main_account@icloud.com"  # 主账号本身也可作为接码邮箱

    # 方式 B：用文件加载别名（与 aliases 二选一）
    aliases_file: "data/icloud_aliases.txt"

    # 别名状态目录（可保持默认）
    state_dir: "token_dir/icloud"
```

### 3) 别名较多时，改用 `aliases_file`

例如 `data/icloud_aliases.txt`：

```txt
# 每行一个邮箱，支持注释
alias_1@icloud.com
alias_2@icloud.com
main_account@icloud.com
```

然后在 `config.yaml` 中配置：

```yaml
mail_provider: "icloud"
mail_providers:
  icloud:
    imap_username: "main_account@icloud.com"
    app_password: "abcd-efgh-ijkl-mnop"
    aliases: []
    aliases_file: "data/icloud_aliases.txt"
```

### 4) 运行前检查

- `imap_username` / `app_password` 必填。
- `aliases` 与 `aliases_file` 至少提供一种，且最终别名池不能为空。
- 默认已提供 `data/icloud_aliases.txt`，可直接维护此文件。
- iCloud 可能把验证码丢到垃圾箱，系统会自动扫描 `INBOX` + `Junk`，无需手动处理。

## 环境变量覆盖

支持使用环境变量覆盖部分配置，常用项如下:

- `CONCURRENCY`
- `TOTAL_ACCOUNTS`
- `PROXY`
- `MODEL_PROVIDER`
- `MAIL_PROVIDER`
- `TOKEN_DIR`
- `CPA_ENABLE`
- `CPA_API_URL`
- `CPA_TOKEN`
 - `CPA_USE_PROXY`
 - `G2A_USE_PROXY`
