# ai-register

[中文](README.md) | English

A lightweight batch registration tool with OpenAI and Grok flows, mailbox OTP retrieval (duckmail / tempmail / iCloud), and optional CPA/Grok2API upload.

> The current default mail provider is `icloud`, with aliases loaded from `data/icloud_aliases.txt` by default.

## Features

- Concurrent batch execution
- Switchable mail provider (duckmail / tempmail / icloud)
- OpenAI OAuth and Grok provider switching
- [CPA](https://github.com/router-for-me/CLIProxyAPI) upload support
- [grok2api](https://github.com/chenyme/grok2api) upload support

## Quick Start

### 1) Install dependencies

Option A (recommended, uv):

```bash
uv sync
```

Option B (pip):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 2) Initialize config

```bash
cp config.example.yaml config.yaml
```

Then fill in sensitive fields:

- `mail_providers.duckmail.bearer`
- `mail_providers.tempmail.api_key`
- `mail_providers.icloud.imap_username` + `mail_providers.icloud.app_password` (when using iCloud)
- `data/icloud_aliases.txt` (default alias file, one email per line)
- `cpa.token` (only required when CPA upload is enabled)
- `g2a.token` (only required when Grok2API upload is enabled)

### 3) Run

The unified entry point is `main.py`.

Check configuration first:

```bash
python main.py
```

Run batch flow:

```bash
python main.py
```

The actual flow is selected by `model_provider` in `config.yaml`.

## Configuration Reference

| Field | Description                             |
| --- |-----------------------------------------|
| `concurrency` | Number of concurrent workers            |
| `total_accounts` | Total number of target accounts         |
| `proxy` | Global proxy; leave empty to disable    |
| `token_dir` | Token output directory                  |
| `model_provider` | Model provider name (`openai` / `grok`) |
| `model_providers.openai.*` | OpenAI OAuth configuration              |
| `model_providers.grok.browser_proxy` | Grok browser proxy setting              |
| `mail_provider` | Mail provider (`duckmail` / `tempmail` / `icloud`) |
| `mail_providers.duckmail.*` | DuckMail settings                       |
| `mail_providers.tempmail.*` | TempMail settings                       |
| `mail_providers.icloud.imap_username` | iCloud main account (IMAP login)        |
| `mail_providers.icloud.app_password` | iCloud app-specific password (not Apple ID password) |
| `mail_providers.icloud.aliases` | iCloud alias pool (main account can be included) |
| `mail_providers.icloud.aliases_file` | iCloud alias file (one email per line) |
| `mail_providers.icloud.state_dir` | iCloud alias state directory (`in_use_aliases.txt` / `registered_aliases.txt`) |
| `cpa.enable` | Enable CPA upload                       |
| `cpa.api_url` | CPA upload endpoint                     |
| `cpa.token` | CPA login token                         |
| `g2a.enable` | Enable Grok2API upload                  |
| `g2a.api_url` | Grok2API upload endpoint                |
| `g2a.token` | Grok2API login token                    |
| `cpa.use_proxy` | Whether to force using the global `proxy` for CPA uploads (default: false; when true uploads use `proxy`, otherwise local addresses may bypass proxy) |
| `g2a.use_proxy` | Whether to force using the global `proxy` for Grok2API uploads (default: false; when true uploads use `proxy`, otherwise local addresses may bypass proxy) |

See [config.example.yaml](config.example.yaml) for a complete example.

## iCloud OTP Notes

- iCloud requires an **app-specific password** (regular Apple ID password will fail).
- The flow takes a mailbox snapshot (`before_ids`) right before triggering OTP, then only parses incremental emails.
- iCloud provider scans both `INBOX` and `Junk`, and uses composite IDs (`Folder:ID`) to avoid cross-folder ID collisions.
- IMAP fetch uses `BODY.PEEK[]` to avoid iCloud `RFC822` empty-payload issues.
- On successful registration, the flow calls `mark_alias_registered(email)`; on failure, it calls `release_alias(email)`.

## Account Credential Persistence

- After successful registration, both OpenAI and Grok flows append `email + password` to:
  - `<token_dir>/<model_provider>/accounts.txt`
- One line format: `email<TAB>password`
- Examples: `token_dir/openai/accounts.txt`, `token_dir/grok/accounts.txt`

## iCloud Configuration Guide (copy-ready)

### 1) Generate an app-specific password in Apple ID

1. Go to your Apple ID account security page.
2. Create an **app-specific password** (e.g. name it `ai-register`).
3. Use a password like `abcd-efgh-ijkl-mnop`.

> This must be an app-specific password, not your Apple ID login password.

### 2) Enable iCloud provider in `config.yaml`

`mail_provider: "icloud"` is already the default. Fill in your main account and alias source:

```yaml
mail_provider: "icloud"

mail_providers:
  icloud:
    imap_username: "main_account@icloud.com"
    app_password: "abcd-efgh-ijkl-mnop"

    aliases:
      - "alias_1@icloud.com"
      - "alias_2@icloud.com"
      - "main_account@icloud.com"

    aliases_file: "data/icloud_aliases.txt"
    state_dir: "token_dir/icloud"
```

### 3) Prefer `aliases_file` for larger alias pools

Example `data/icloud_aliases.txt`:

```txt
# one email per line
alias_1@icloud.com
alias_2@icloud.com
main_account@icloud.com
```

### 4) Pre-run checklist

- `imap_username` / `app_password` are required.
- At least one of `aliases` or `aliases_file` must be provided, and the final pool cannot be empty.
- A default `data/icloud_aliases.txt` file is included; you can edit it directly.
- OTP emails may go to Junk; the system scans both `INBOX` and `Junk` automatically.

## Environment Variable Overrides

Supports overriding part of the config via environment variables. Common ones include:

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
