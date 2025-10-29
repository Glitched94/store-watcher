# watch_store.py
import json, os, re, smtplib, time, traceback
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Dict, Set, Tuple
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# =========================
# Configuration (.env)
# =========================
TARGET_URL = os.getenv("TARGET_URL", "").strip()  # Use the Disney grid endpoint for server-rendered HTML
CHECK_EVERY = int(os.getenv("CHECK_EVERY", "300"))
RESTOCK_WINDOW_HOURS = int(os.getenv("RESTOCK_WINDOW_HOURS", "24"))

INCLUDE_RE = os.getenv("INCLUDE_RE", "").strip()
EXCLUDE_RE = os.getenv("EXCLUDE_RE", "").strip()
include_rx = re.compile(INCLUDE_RE) if INCLUDE_RE else None
exclude_rx = re.compile(EXCLUDE_RE) if EXCLUDE_RE else None

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", SMTP_USER)
EMAIL_TO = os.getenv("EMAIL_TO", "")

STATE_FILE = Path("seen_items.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StoreWatcher/2.0)"}
PRODUCT_LINK_RE = re.compile(r"/[^/]+\.html(?:\?|$)")

# Keep items that lack a numeric product code (rare). If False, they are ignored.
KEEP_NO_CODE_ITEMS = False

# =========================
# Helpers
# =========================
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def iso_to_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)

def canonicalize(url: str) -> str:
    u = urlsplit(url)
    scheme = "https"
    netloc = u.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", u.path)
    return urlunsplit((scheme, netloc, path, "", ""))

# Extract last numeric chunk (>=6 digits) in the filename before .html
CODE_RE = re.compile(r"/([^/]+)\.html(?:\?|$)", re.IGNORECASE)
DIGITS_RE = re.compile(r"(\d{6,})")
def extract_product_code(url: str) -> str | None:
    m = CODE_RE.search(url)
    if not m:
        return None
    filename = m.group(1)
    codes = DIGITS_RE.findall(filename)
    return codes[-1] if codes else None

def fetch_product_pairs(url: str) -> Set[Tuple[str, str]]:
    """
    Returns a set of (code, canonical_url) for items found on the page.
    """
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    found: Set[Tuple[str, str]] = set()
    for a in soup.select("a[href]"):
        href = urljoin(url, a["href"])
        if PRODUCT_LINK_RE.search(href):
            if include_rx and not include_rx.search(href):
                continue
            if exclude_rx and exclude_rx.search(href):
                continue
            cu = canonicalize(href)
            code = extract_product_code(cu)
            if code:
                found.add((code, cu))
            elif KEEP_NO_CODE_ITEMS:
                found.add((cu, cu))
    return found

# =========================
# State I/O and Migration
# =========================
"""
Unified state schema (per item code):
state[code] = {
  "url": "<canonical product url>",
  "first_seen": "<ISO>",
  "status": 0|1,            # 1 = present this tick, 0 = absent this tick
  "status_since": "<ISO>"   # when status last changed
}
"""

def _make_present(url: str, now_iso: str) -> Dict[str, str | int]:
    return {"url": url, "first_seen": now_iso, "status": 1, "status_since": now_iso}

def _migrate_from_list(raw: list) -> Dict[str, Dict[str, str | int]]:
    print("[info] Migrating legacy list -> status machine")
    now = utcnow_iso()
    state: Dict[str, Dict[str, str | int]] = {}
    for u in raw:
        cu = canonicalize(u)
        code = extract_product_code(cu) or (cu if KEEP_NO_CODE_ITEMS else None)
        if not code:
            continue
        if code not in state:
            state[code] = _make_present(cu, now)
    return state

def _migrate_from_dict(raw: dict) -> Dict[str, Dict[str, str | int]]:
    """
    Accepts prior dicts keyed by URL or code, with either:
      - {"first_seen","last_seen"} timestamps, or
      - already using "status"/"status_since"
    Normalizes to code-keyed status machine.
    """
    print("[info] Migrating legacy dict -> status machine (if needed)")
    now = utcnow_iso()
    migrated: Dict[str, Dict[str, str | int]] = {}

    for k, v in raw.items():
        # Determine identity (code or URL)
        if k.isdigit():
            code = k
            url = v.get("url") or ""
        else:
            url = canonicalize(k)
            code = extract_product_code(url) or (url if KEEP_NO_CODE_ITEMS else None)
            if not code:
                continue

        # If already status-based, keep as-is but normalize fields
        if "status" in v and "status_since" in v:
            first_seen = v.get("first_seen") or now
            status = int(v.get("status") or 1)
            status_since = v.get("status_since") or first_seen
            migrated[code] = {
                "url": url or v.get("url", ""),
                "first_seen": first_seen,
                "status": 1 if status else 0,
                "status_since": status_since,
            }
            continue

        # Else assume last_seen/first_seen model
        first_seen = v.get("first_seen") or v.get("last_seen") or now
        last_seen = v.get("last_seen") or first_seen

        # Interpret legacy: treat as currently present (status=1), since we don't know absence yet
        migrated[code] = {
            "url": url or v.get("url", ""),
            "first_seen": first_seen,
            "status": 1,
            "status_since": last_seen,
        }

    return migrated

def load_state() -> Dict[str, Dict[str, str | int]]:
    try:
        if STATE_FILE.exists():
            raw = json.loads(STATE_FILE.read_text())
            if isinstance(raw, list):
                return _migrate_from_list(raw)
            if isinstance(raw, dict):
                return _migrate_from_dict(raw)
    except Exception:
        traceback.print_exc()
    return {}

def save_state(state: Dict[str, Dict[str, str | int]]) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, sort_keys=True))

# =========================
# Email
# =========================
def send_email(new_codes, restocked_codes, total_count: int, state: Dict[str, Dict[str, str | int]]) -> None:
    if not (SMTP_HOST and SMTP_USER and SMTP_PASS and EMAIL_FROM and EMAIL_TO):
        print("[warn] Email not configured; skipping email send")
        return

    def li(code: str) -> str:
        url = state.get(code, {}).get("url", "")
        anchor = f'<a href="{url}">{url or code}</a>'
        label = code if code.isdigit() else "item"
        return f"<li>{label}: {anchor}</li>"

    parts = []
    if new_codes:
        parts.append(
            f"<p><strong>New items ({len(new_codes)}):</strong></p><ul>"
            + "".join(li(c) for c in sorted(new_codes))
            + "</ul>"
        )
    if restocked_codes:
        parts.append(
            f"<p><strong>Restocked (≥{RESTOCK_WINDOW_HOURS}h absent) ({len(restocked_codes)}):</strong></p><ul>"
            + "".join(li(c) for c in sorted(restocked_codes))
            + "</ul>"
        )
    if not parts:
        return

    bits = []
    if new_codes: bits.append(f"{len(new_codes)} new")
    if restocked_codes: bits.append(f"{len(restocked_codes)} restocked")
    subject = "[Store Watch] " + " & ".join(bits) + f" (now {total_count} total)"

    body_html = f"""
    <p>Changes detected on <a href="{TARGET_URL}">{TARGET_URL}</a>.</p>
    {''.join(parts)}
    <p>Total items now: {total_count}</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO
    msg.attach(MIMEText(body_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(EMAIL_FROM, [EMAIL_TO], msg.as_string())

    print(f"[info] Email sent: {subject}")

# =========================
# Main Loop (status machine)
# =========================
def main():
    if not TARGET_URL:
        raise SystemExit("Please set TARGET_URL in .env")

    print(f"[info] Watching: {TARGET_URL}")
    if INCLUDE_RE: print(f"[info] Include filter: {INCLUDE_RE}")
    if EXCLUDE_RE: print(f"[info] Exclude filter: {EXCLUDE_RE}")
    print(f"[info] Restock window: {RESTOCK_WINDOW_HOURS}h")

    state = load_state()
    print(f"[info] Known items (by code): {len(state)}")
    restock_delta = timedelta(hours=RESTOCK_WINDOW_HOURS)

    while True:
        try:
            current_pairs = fetch_product_pairs(TARGET_URL)  # Set[(code, url)]
            now_iso = utcnow_iso()
            now_dt = iso_to_dt(now_iso)

            current_codes = {code for code, _ in current_pairs}
            canonical_for_code = {c: u for c, u in current_pairs}

            new_codes = []
            restocked_codes = []

            # 1) Mark codes absent that were previously present but not found this tick
            for c, info in state.items():
                if c not in current_codes and info.get("status", 1) == 1:
                    info["status"] = 0
                    info["status_since"] = now_iso  # start of absence

            # 2) Handle current (present) codes
            for c in current_codes:
                preferred_url = canonical_for_code.get(c, state.get(c, {}).get("url", ""))

                if c not in state:
                    # New item
                    state[c] = _make_present(preferred_url, now_iso)
                    new_codes.append(c)
                else:
                    info = state[c]
                    # Keep the nicest URL (no query usually)
                    if preferred_url and preferred_url != info.get("url", ""):
                        info["url"] = preferred_url

                    if info.get("status", 0) == 0:
                        # Was absent, now present → check absence duration for restock alert
                        absent_since = iso_to_dt(info.get("status_since", now_iso))
                        if now_dt - absent_since >= restock_delta:
                            restocked_codes.append(c)
                        # Flip to present; status_since marks the start of present period
                        info["status"] = 1
                        info["status_since"] = now_iso
                    else:
                        # Already present; do not touch status_since (keeps start of present run)
                        info["status"] = 1

            # Persist before emailing to avoid duplicate alerts on crash
            save_state(state)
            send_email(new_codes, restocked_codes, total_count=len(current_codes), state=state)

            print(f"[info] tick: current={len(current_codes)} new={len(new_codes)} restocked={len(restocked_codes)} known={len(state)}")
        except Exception:
            traceback.print_exc()

        time.sleep(CHECK_EVERY)

if __name__ == "__main__":
    main()
