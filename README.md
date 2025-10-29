# Store Watcher

Watch online store pages and get alerts for **new** and **restocked** products.

- Robust identity via **product codes** (e.g., `438039197642`)
- Compact **state machine** tracks presence/absence over time
- Alerts via **Email** and **Discord** (chunked, cleanly formatted messages)
- Extensible **adapter** system (Disney Store included)
- CLI for running, debugging, and scheduling
- Fully tested and CI-verified with GitHub Actions

> A production-minded Python demo: adapters, state machines, CLI, notifications, testing, and CI.

---

## ✨ Features

- **New item alerts** — first time an item appears.
- **Restock alerts** — re-added after `RESTOCK_WINDOW_HOURS` of absence.
- **Pretty notifications**  
  - Email: bold item names as links.  
  - Discord: Markdown links `[Name](short-url)` with embeds suppressed and auto-chunking for long lists.
- **Polite fetching** — headers, intervals, and retries configurable.
- **Portable state** — human-readable JSON with automatic migrations.
- **Tested** — utilities, adapter parsing, state logic, and rendering covered by pytest.

---

## 🚀 Quickstart

```bash
# 1. Install
pipx install .

# Or for development
pip install -e ".[dev]"

# 2. Create your .env
cp .env.example .env

# 3. Run (defaults: 5 min interval, 24 h restock window)
store-watcher watch
````

### `.env` example

```ini
# Disney Store pins grid (server-rendered HTML)
TARGET_URL=https://www.disneystore.com/on/demandware.store/Sites-shopDisney-Site/default/Search-UpdateGrid?cgid=collectibles-pins&start=0&sz=200

# Optional regex filters (Python regex)
INCLUDE_RE=
EXCLUDE_RE=(t-shirt|jersey|cap|hoodie|sweatshirt)\b

# Loop cadence & restock window
CHECK_EVERY=300
RESTOCK_WINDOW_HOURS=24

# Email (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=your_email@gmail.com
EMAIL_TO=you@yourdomain.com

# Discord Webhook (optional)
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/xxx/yyy
DISCORD_USERNAME=Store Watcher
DISCORD_AVATAR_URL=
```

---

## 🧰 CLI

```bash
# Run watcher (defaults from .env)
store-watcher watch

# Override on the fly
store-watcher watch --every 600 --restock 48

# Single pass (no loop / no email)
store-watcher watch --once

# View or clear stored state
store-watcher state show
store-watcher state clear
```

> 💡 Tip: On Windows, use `pythonw.exe` or Task Scheduler; on Linux, use `systemd` for background operation.

---

## ⚙️ How it Works

Each product is keyed by its numeric code:

```json
{
  "438039197642": {
    "url": "https://disneystore.com/438039197642.html",
    "name": "Animal Pin – The Muppets",
    "first_seen": "2025-10-29T03:05:00Z",
    "status": 1,
    "status_since": "2025-10-29T03:05:00Z"
  }
}
```

| Field          | Meaning                                                                        |
| -------------- | ------------------------------------------------------------------------------ |
| `status`       | `1` = present, `0` = absent                                                    |
| `status_since` | when the current status began                                                  |
| **Restock**    | triggers only on an *absent → present* transition after `RESTOCK_WINDOW_HOURS` |

---

## 🪄 Notifications

### Email

* Simple HTML list of new/restocked products
* Each item name is a clickable link
* Sent through your SMTP configuration

### Discord

* Clean Markdown messages with `[Name](short-url)` format
* Embeds suppressed (no bulky previews)
* Automatic message chunking if over Discord’s 2000-character limit

Example:

```
New items (3):
- [Ariel and Sebastian Pin – The Little Mermaid](https://www.disneystore.com/438039196577.html)
- [Disneyland 70th Anniversary Vault Collection Pin Display Frame](https://www.disneystore.com/438018657693.html)
- [Mickey Mouse Holiday Pin](https://www.disneystore.com/438039190384.html)

Total items now: 23
```

---

## 🕒 Scheduling

### Windows Task Scheduler

```powershell
$task   = "StoreWatcher"
$py     = "C:\Python312\pythonw.exe"
$script = "C:\Users\<you>\AppData\Local\Programs\Python\Python312\Scripts\store-watcher.exe"
$cwd    = "C:\path\to\repo"

schtasks /Create /TN $task /SC ONLOGON `
  /TR "cmd /c cd /d `"$cwd`" && `"$script`" watch" `
  /RL LIMITED /F
```

### Linux systemd

```ini
# /etc/systemd/system/store-watcher.service
[Unit]
Description=Store Watcher

[Service]
WorkingDirectory=/opt/store-watcher
ExecStart=/usr/local/bin/store-watcher watch
Restart=always

[Install]
WantedBy=multi-user.target
```

---

## 🧱 Project Structure

```
store-watcher/
├─ src/store_watcher/
│  ├─ cli.py           # Typer CLI commands
│  ├─ core.py          # loop + state machine
│  ├─ notify.py        # Email & Discord notifiers
│  ├─ adapters/
│  │  ├─ base.py       # Adapter ABC + Item type
│  │  └─ disneystore.py
│  ├─ utils.py         # canonicalization, code extraction, short URLs
│  └─ state.py         # JSON store + migrations
├─ tests/              # pytest unit tests
├─ .pre-commit-config.yaml
├─ pyproject.toml
├─ README.md
└─ .github/workflows/ci.yml
```

---

## 🧪 Development

```bash
# Dev install
pip install -e ".[dev]"

# Lint, format, type-check, test
ruff check .
ruff format --check .
mypy src
pytest -q
```

### Pre-commit hooks

```bash
pre-commit install
pre-commit install --hook-type pre-push
pre-commit run --all-files
```

These run `ruff`, `black`, `mypy`, and `pytest` automatically before you commit or push.

---

## 🧰 Continuous Integration

GitHub Actions (`.github/workflows/ci.yml`) runs:

* `ruff`, `black`, `mypy`
* `pytest` on Python 3.11 + 3.12
* builds wheel + sdist and uploads as artifact

---

## 🧭 Roadmap

* Retries with backoff (429/5xx)
* Additional adapters (Shopify, Playwright for JS sites)
* Optional SQLite backend
* Price/title change detection
* Small web dashboard

---

## 🤝 Ethics

Respect each site’s Terms of Service and robots.txt.
Keep polling intervals reasonable.
This tool is for personal use and demonstration purposes only.

---

## 📄 License

MIT
