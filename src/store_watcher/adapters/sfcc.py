from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from ..utils import canonicalize, extract_product_code
from .base import Adapter, Item

PRODUCT_LINK_RE = re.compile(r"/[^/]+\.html(?:\?|$)")


def _set_page(url: str, page: int) -> str:
    u = urlsplit(url)
    q = parse_qs(u.query, keep_blank_values=True)
    q["page"] = [str(page)]
    return urlunsplit((u.scheme, u.netloc, u.path, urlencode(q, doseq=True), ""))


class SFCCGridAdapter(Adapter):
    def fetch(self, session: requests.Session, url: str, include_rx, exclude_rx) -> Iterable[Item]:
        seen_codes: set[str] = set()
        max_pages = 10  # safety cap; adjust as needed

        def parse_once(u: str) -> int:
            r = session.get(u, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            found_here = 0
            for a in soup.select("a[href]"):
                href = urljoin(u, a.get("href", ""))
                if not PRODUCT_LINK_RE.search(href):
                    continue
                cu = canonicalize(href)
                if include_rx and not include_rx.search(cu):
                    continue
                if exclude_rx and exclude_rx.search(cu):
                    continue
                code = extract_product_code(cu)
                if not code or code in seen_codes:
                    continue
                seen_codes.add(code)
                title = a.get("title") or a.get_text(strip=True) or None
                yield Item(code=code, url=cu, title=title, price=None)
                found_here += 1
            return found_here

        # page 1
        yielded = 0
        for it in parse_once(url):
            yielded += 1
            yield it

        # try subsequent pages if site supports ?page=
        page = 2
        while page <= max_pages:
            next_url = _set_page(url, page)
            found = 0
            for it in parse_once(next_url):
                yielded += 1
                found += 1
                yield it
            if found == 0:
                break
            page += 1
