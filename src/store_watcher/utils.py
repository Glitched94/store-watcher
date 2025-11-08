from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from requests.adapters import HTTPAdapter, Retry

# ---------- Time helpers ----------


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def iso_to_dt(s: str) -> datetime:
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return datetime.fromisoformat(s)


# ---------- URL + identity helpers ----------


def canonicalize(url: str) -> str:
    u = urlsplit(url)
    scheme = "https"
    netloc = u.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = re.sub(r"/{2,}", "/", u.path)
    return urlunsplit((scheme, netloc, path, "", ""))


_CODE_RE = re.compile(r"/([^/]+)\.html(?:\?|$)", re.IGNORECASE)
_DIGITS_RE = re.compile(r"(\d{6,})")


def extract_product_code(url: str) -> Optional[str]:
    m = _CODE_RE.search(url)
    if not m:
        return None
    filename = m.group(1)
    codes = _DIGITS_RE.findall(filename)
    return codes[-1] if codes else None


def domain_of(u_or_host: str) -> str:
    host = urlsplit(u_or_host).netloc or u_or_host
    host = host.lower()
    return host[4:] if host.startswith("www.") else host


def site_label(s: str) -> str:
    h = domain_of(s)
    if h.endswith(".co.uk") or h.endswith("disneystore.co.uk"):
        return "UK"
    if h.endswith(".eu") or h.endswith("disneystore.eu"):
        return "EU"
    if h.endswith(".asia") or h.endswith("disneystore.asia"):
        return "ASIA"
    if h.endswith(".com.au") or h.endswith("disneystore.com.au"):
        return "AU"
    if h.endswith(".co.jp") or h.endswith("disney.co.jp"):
        return "JP"
    return "US"


# ---------- Name prettifier ----------


def slug_to_title(slug: str) -> str:
    """
    Convert a product slug into Title Case, stopping before trailing numeric code tokens.
    """
    parts = [p for p in slug.split("-") if p]
    out: list[str] = []
    for p in parts:
        if _DIGITS_RE.fullmatch(p):
            break
        out.append(p.capitalize() if p.lower() not in {"and", "with", "the", "of", "for"} else p)
    if not out:
        out = parts[:]
    return " ".join(out).strip()


def pretty_name_from_url(url: str) -> Optional[str]:
    u = urlsplit(url)
    path = u.path.rstrip("/")
    if not path.endswith(".html"):
        return None
    slug = path.rsplit("/", 1)[-1].removesuffix(".html")
    titled = slug_to_title(slug)
    return titled or None


# ---------- HTML to text / md helpers ----------


def html_to_text(s: str) -> str:
    s = re.sub(r"<a [^>]*href=['\"]([^'\"]+)['\"][^>]*>(.*?)</a>", r"\2 (\1)", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return _html.unescape(s).strip()


def escape_md(s: str) -> str:
    return s.replace("[", r"\[").replace("]", r"\]").replace("(", r"\(").replace(")", r"\)")


# ---------- Image URL extraction & tuning ----------


def _apply_template_params(template_url: str, *, size: int) -> Optional[str]:
    """
    Handle SFCC-style templates like ...{width}x{height}... or ...{w}x{h}...
    """
    try:
        w = str(int(size))
        h = w
        u = template_url
        u = u.replace("{width}", w).replace("{height}", h)
        u = u.replace("{w}", w).replace("{h}", h)
        return u
    except Exception:
        return None


def img_src_from_tag(base_url: str, tag: Any) -> Optional[str]:
    """Return an absolute URL from a tag (<img> or <source>), preferring src, then data-* , then srcset."""
    if tag is None:
        return None

    # src
    src = tag.get("src")
    if isinstance(src, list):
        src = src[0] if src else None
    if src:
        return urljoin(base_url, str(src))

    # common lazy attrs
    for k in ("data-src", "data-original", "data-lazy", "data-image"):
        val = tag.get(k)
        if val:
            return urljoin(base_url, str(val))

    # data-src-template with width/height placeholders (common on US)
    tmpl = tag.get("data-src-template") or tag.get("data-template")
    if tmpl:
        applied = _apply_template_params(str(tmpl), size=768)
        if applied:
            return urljoin(base_url, applied)

    # srcset (img or source)
    for k in ("data-srcset", "srcset"):
        ss = tag.get(k)
        if ss:
            first = str(ss).split(",")[0].strip().split(" ")[0]
            if first:
                return urljoin(base_url, first)

    return None


def tune_image_url(url: str, *, size: int = 768, quality: int = 100) -> str:
    """
    For SFCC/CDN product images that ship params like ?qlt=70&wid=247&hei=247,
    return a version tuned for our UI (square `size` and `quality`).
    """
    try:
        sp = urlsplit(url)
        qs = dict(parse_qsl(sp.query, keep_blank_values=True))
        qs["qlt"] = str(max(1, min(100, int(quality))))
        qs["wid"] = str(int(size))
        qs["hei"] = str(int(size))
        return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(qs), sp.fragment))
    except Exception:
        return url


# ---------- HTTP session ----------


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0 (compatible; StoreWatcher/3.1)"})
    retries = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "HEAD"]),
        raise_on_status=False,
    )
    s.mount("https://", HTTPAdapter(max_retries=retries))
    s.mount("http://", HTTPAdapter(max_retries=retries))
    return s


# ---------- Misc ----------


def short_product_url_from_state(full_url: str, code: str) -> str:
    """
    Build a compact, canonical product URL like:
      https://disneystore.com/<code>.html
    using the host from `full_url`. If `code` is empty, just return `full_url`.
    """
    if not code:
        return full_url
    u = urlsplit(full_url)
    scheme = u.scheme or "https"
    host = u.netloc or "disneystore.com"
    if host.startswith("www."):
        host = host[4:]
    path = f"/{code}.html"
    return urlunsplit((scheme, host, path, "", ""))
