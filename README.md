# 🧭 Store Watcher

**Store Watcher** monitors retail pages for **new** and **restocked** products, alerting you via **Discord** or **Email**.
It provides a web dashboard built with FastAPI + HTMX, Google login, and a persistent SQLite backend — all running through Docker.

> Watch your favorite store pages — never miss a restock again.

---

## 🚀 Highlights

* 🧩 **Full-stack app** — FastAPI web UI with Google OAuth login
* 💾 **SQLite-backed** persistence for users, items, and listeners
* 🔔 **Smart notifications** — detects new + restocked products via product codes
* 💬 **Discord & Email alerts** — chunked, clean, and configurable
* 🐳 **Docker-native architecture** — separate UI and watcher containers
* 🧠 **CI/CD verified** — linting, typing, and tests in GitHub Actions

---

## 🧩 Architecture Overview

```
store-watcher/
├─ src/store_watcher/
│  ├─ ui/                  # FastAPI + HTMX web UI
│  │  ├─ routes_main.py    # Dashboard & landing
│  │  ├─ routes_auth.py    # Google login/logout
│  │  ├─ routes_admin.py   # Manage listeners & tests
│  │  └─ core.py           # App factory
│  ├─ db/                  # SQLite-backed persistence
│  ├─ adapters/            # Site scrapers/adapters (e.g., Disney Store)
│  ├─ notify/              # Email & Discord notifiers
│  ├─ core.py              # Watcher logic and state tracking
│  ├─ cli.py               # Typer CLI
│  └─ utils.py             # URL parsing, regex helpers, etc.
├─ tests/                  # pytest suite
├─ Dockerfile              # Base image build
├─ docker-compose.yml      # Multi-region setup
└─ .github/workflows/ci.yml
```

---

## 🖥️ Web UI

* FastAPI + HTMX dashboard
* Google authentication
* Manage **listeners** (Discord or Email)
* Send **test notifications**
* View all listeners by region and user

### Run locally

```bash
uvicorn store_watcher.ui:create_app --factory --host 0.0.0.0 --port 8000
```

---

## ⚙️ Watcher Services

Each watcher runs independently and monitors a single `TARGET_URL`.

### Example `.env.us`

```ini
# Target page to monitor
TARGET_URL=https://www.disneystore.com/on/demandware.store/Sites-shopDisney-Site/default/Search-UpdateGrid?cgid=collectibles-pins&start=0&sz=200

# Polling + restock behavior
CHECK_EVERY=300
RESTOCK_WINDOW_HOURS=24
INCLUDE_RE=
EXCLUDE_RE=(t-shirt|hoodie|jersey|cap)\b

# Email delivery (used by Email listeners)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email@gmail.com
SMTP_PASS=your_app_password
EMAIL_FROM=alerts@yourdomain.com
```

Each watcher container reads its own `.env.<region>` file — e.g. `.env.us`, `.env.eu`, etc.
Listeners in the UI database only need to specify **destination info** (Discord webhook or Email To address).

---

## 🧰 Docker Deployment

### Example `docker-compose.yml`

```yaml
services:
  ui:
    image: ghcr.io/glitched94/store-watcher:latest
    container_name: store-watcher-ui
    command: >
      uvicorn store_watcher.ui:create_app
      --factory --host 0.0.0.0 --port 8000
    env_file:
      - ./.env.ui
    volumes:
      - data:/app/data
    ports:
      - "8000:8000"
    restart: unless-stopped

  watcher_us:
    image: ghcr.io/glitched94/store-watcher:latest
    container_name: store-watcher-us
    command: store-watcher watch
    env_file:
      - ./.env.us
    volumes:
      - data:/app/data
    restart: unless-stopped

  watcher_eu:
    image: ghcr.io/glitched94/store-watcher:latest
    container_name: store-watcher-eu
    command: store-watcher watch
    env_file:
      - ./.env.eu
    volumes:
      - data:/app/data
    restart: unless-stopped

volumes:
  data:
```

### Local usage

```bash
# Build fresh images
docker compose build --no-cache

# Start all services
docker compose up -d

# Stop and remove
docker compose down
```

---

## 🔔 Notifications

### Discord

* Markdown-formatted `[Name](url)` links
* Embeds suppressed for clean messages
* Automatic chunking under 2000 characters
* Simple “Test” button in the UI

### Email

* Clean HTML + plaintext layout
* SMTP credentials from `.env.ui`
* “To” addresses configured per listener

---

## 🧪 Development

```bash
# Install dev environment
pip install -e ".[dev]"

# Run linting, typing, and tests
ruff check .
black --check .
mypy
pytest -q
```

Run the UI locally:

```bash
python -m store_watcher.ui
```

Run a watcher directly:

```bash
store-watcher watch --url https://example.com
```

---

## ⚙️ Continuous Integration

GitHub Actions automatically runs on every push:

* ✅ `ruff`, `black`, `mypy`
* 🧪 `pytest` on Python 3.11 + 3.12
* 📦 Builds and checks wheel/sdist
* 🐳 Builds and pushes multi-arch Docker image to GHCR

---

## 🧭 Roadmap

* Historical item tracking and analytics
* Price change notifications
* Webhook integrations
* Optional retry/backoff and rate limiting

---

## 🧑‍💻 Author

**Joshua Dietrich**
MIT License

---
