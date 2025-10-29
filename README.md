# Store Watcher

Watch retail category pages and get alerts for **new** and **restocked** items.

- Robust identity via **product codes** (e.g., `...-438039197642.html`)
- Noise-control via a compact **state machine**: `status` (present/absent) + `status_since`
- Alerts via **email** out of the box; Slack/webhooks easy to add
- Extensible **adapter** interface (Disney Store included; Shopify example planned)
- CLI with clean logs; runs great as a scheduled task or service

> This repo is a small but production-minded demo of Python skills: adapters, state machines, CLI + packaging, tests, and CI hooks.

---

## Features

- **New item alerts**: first time an item is observed.
- **Restock alerts**: item was absent for ≥ `RESTOCK_WINDOW_HOURS`, then observed present again.
- **Canonicalization**: URLs normalized; identity keyed by product code to ignore query-string noise.
- **Polite fetching**: user-agent set, interval controlled; retry/backoff recommended (see roadmap).
- **Portable state**: human-readable JSON with auto-migrations across versions.

---

## Quickstart

```bash
# 1) Install
pipx install .

# Or locally for development
pip install -e .

# 2) Create .env
cp .env.example .env

# 3) Run (default 5 min interval, 24h restock window)
store-watcher watch
````

### .env example

```ini
# Disney Store pins grid (server-rendered HTML)
TARGET_URL=https://www.disneystore.com/on/demandware.store/Sites-shopDisney-Site/default/Search-UpdateGrid?cgid=collectibles-pins&start=0&sz=200

# Optional regex filters (Python regex). Leave blank to disable.
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
```

---

## CLI

```bash
# Run watcher (defaults from .env)
store-watcher watch

# Override some values on the fly
store-watcher watch --every 600 --restock 48

# Dry-run once (fetch + compute + print, no loop / no email)
store-watcher watch --once

# Show current known state
store-watcher state show

# Clear local state (be careful!)
store-watcher state clear
```

> Tip: Use `pythonw.exe` on Windows or a service/daemon on Linux to run headless.

---

## How it works (state machine)

Per item (keyed by **code**):

```json
{
  "438039197642": {
    "url": "https://disneystore.com/animal-pin-the-muppets-438039197642.html",
    "first_seen": "2025-10-29T03:05:00Z",
    "status": 1,
    "status_since": "2025-10-29T03:05:00Z"
  }
}
```

* `status`: `1` present, `0` absent
* `status_since`: when that status last changed
* **Restock** triggers only on an *observed* absent→present transition where
  `now - status_since ≥ RESTOCK_WINDOW_HOURS`.

---

## Scheduling

### Windows (Task Scheduler)

```powershell
$task   = "StoreWatcher"
$py     = "C:\Python312\pythonw.exe"
$script = "C:\Users\<you>\AppData\Local\Programs\Python\Python312\Scripts\store-watcher.exe"
$cwd    = "C:\path\to\repo"

schtasks /Create /TN $task /SC ONLOGON `
  /TR "cmd /c cd /d `"$cwd`" && `"$script`" watch" `
  /RL LIMITED /F
```

### Linux (systemd)

```
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

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now store-watcher
```

---

## Project structure

```
store-watcher/
├─ src/store_watcher/
│  ├─ __init__.py
│  ├─ cli.py           # Typer commands: watch, state show/clear
│  ├─ core.py          # loop, state machine, email notifier
│  ├─ adapters/
│  │  ├─ base.py       # Adapter ABC + Item type
│  │  └─ disneystore.py
│  ├─ utils.py         # URL canonicalize, product code extraction
│  └─ state.py         # JSON store + migrations
├─ tests/              # pytest
├─ README.md
├─ pyproject.toml
├─ .env.example
└─ .github/workflows/ci.yml
```

---

## Development

```bash
# Dev install
pip install -e ".[dev]"

# Run linters & tests
ruff check .
black --check .
mypy src
pytest -q
```

---

## Roadmap

* Retries with backoff (429/5xx), jittered cadence
* Slack/Discord/Webhook notifiers
* Shopify adapter (+ Playwright “headless” adapter for JS-heavy sites)
* Price/title change detection via normalized DOM hashing
* Optional SQLite state backend, small dashboard page

---

## Ethics

Respect each site’s Terms of Service and robots.txt. Keep intervals reasonable. This tool is for personal use and demos.

---

## License

MIT