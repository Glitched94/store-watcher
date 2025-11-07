from __future__ import annotations

import re
from collections.abc import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from ..utils import canonicalize, extract_product_code
from .base import Adapter, Item

PRODUCT_LINK_RE = re.compile(r"/[^/]+\.html(?:\?|$)")

class DisneyStoreAdapter(Adapter):
    """
    Fetch items from a Disney Store category grid endpoint that returns server-rendered HTML, e.g.:

    https://www.disneystore.com/on/demandware.store/Sites-shopDisney-Site/default/Search-UpdateGrid?cgid=collectibles-pins&start=0&sz=200
    """

    def fetch(self, session: requests.Session, url: str, include_rx, exclude_rx) -> Iterable[Item]:
        r = session.get(url, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        seen: set[str] = set()
        for a in soup.select("a[href]"):
            href = urljoin(url, a.get("href", ""))
            if not PRODUCT_LINK_RE.search(href):
                continue
            cu = canonicalize(href)
            if include_rx and not include_rx.search(cu):
                continue
            if exclude_rx and exclude_rx.search(cu):
                continue
            code = extract_product_code(cu)
            if not code:
                continue
            if code in seen:
                continue
            seen.add(code)

            # Optional: best-effort title (safe; may be None)
            title = (a.get("title") or a.get_text(strip=True) or None)
            yield Item(code=code, url=cu, title=title, price=None)
