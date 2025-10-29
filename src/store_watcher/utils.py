from __future__ import annotations
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

MINOR_WORDS = {
    "a","an","and","as","at","but","by","for","from","in","into","of","on","or",
    "the","to","with","without","over","under"
}

# --- Time helpers ---
def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def iso_to_dt(s: str):
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)

# --- URL canonicalization & product codes ---
def canonicalize(url: str) -> str:
    u = urlsplit(url)
    scheme = "https"
    netloc = u.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", u.path)
    return urlunsplit((scheme, netloc, path, "", ""))

CODE_RE = re.compile(r"/([^/]+)\.html(?:\?|$)", re.IGNORECASE)
DIGITS_RE = re.compile(r"(\d{6,})")

def extract_product_code(url: str) -> str | None:
    m = CODE_RE.search(url)
    if not m:
        return None
    filename = m.group(1)
    codes = DIGITS_RE.findall(filename)
    return codes[-1] if codes else None

# --- HTTP session with retries/backoff ---
def make_session() -> requests.Session:
    s = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.2,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.headers.update({"User-Agent": "StoreWatcher/2.0 (+https://github.com/yourname/store-watcher)"})
    return s

def html_to_text(s: str) -> str:
    """Very small HTML→text converter good enough for Discord/webhooks."""
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"</p\s*>", "\n\n", s, flags=re.I)
    s = re.sub(r"</li\s*>", "\n", s, flags=re.I)
    s = re.sub(r"<li\s*>", "- ", s, flags=re.I)
    s = re.sub(r"</?(ul|ol|strong|em|b|i|u|p|div|span)[^>]*>", "", s, flags=re.I)
    s = re.sub(r"<a [^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"\2 (\1)", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)  # strip remaining tags
    return html.unescape(s).strip()

def escape_md(s: str) -> str:
    """Escape Discord Markdown special chars."""
    return re.sub(r"([\\*_`~|>])", r"\\\1", s)

def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1] + "…"

def slug_to_title(slug: str) -> str:
    """
    Convert 'disneyland-70th-anniversary-vault-collection-pin-display-frame-with-three-pins-limited-edition-438018657693'
    -> 'Disneyland 70th Anniversary Vault Collection Pin Display Frame with Three Pins Limited Edition'
    (stops before trailing numeric code tokens)
    """
    # remove trailing numeric token(s)
    parts = slug.split("-")
    trimmed: list[str] = []
    for token in parts:
        if token.isdigit() and len(token) >= 6:
            break
        trimmed.append(token)

    words = [w for w in trimmed if w]
    if not words:
        return slug

    # smart title case
    titled: list[str] = []
    for i, w in enumerate(words):
        base = w.replace("_", " ")
        if base.upper() in ("D23", "WDW", "WDI"):
            titled.append(base.upper())
        elif base.isdigit():
            titled.append(base)
        elif i not in (0, len(words)-1) and base.lower() in MINOR_WORDS:
            titled.append(base.lower())
        else:
            titled.append(base.capitalize())
    return " ".join(titled)

def pretty_name_from_url(url: str) -> str:
    """
    Take the last path segment before .html and prettify it.
    """
    m = CODE_RE.search(url)
    if not m:
        return url
    filename = m.group(1)  # slug-with-code
    return slug_to_title(filename)

def suppress_embed_url(url: str) -> str:
    """
    Wrap URL in angle brackets to prevent Discord auto-embeds.
    """
    return f"<{url}>"

def short_product_url_from_state(url: str, code: str) -> str:
    """
    Build the shortest valid product URL for Discord.
    For DisneyStore we can use: https://www.disneystore.com/<code>.html
    Falls back to the original url if host isn't disneystore.com or code is missing.
    """
    u = urlsplit(url)
    host = u.netloc.lower()
    if code and host.endswith("disneystore.com"):
        return urlunsplit(("https", "www.disneystore.com", f"/{code}.html", "", ""))
    # fallback: original canonicalized
    return canonicalize(url)
