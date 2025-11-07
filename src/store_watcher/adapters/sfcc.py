from __future__ import annotations

import re
from collections.abc import Iterable
from typing import List, Optional, Pattern, Set
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
    def fetch(
        self,
        session: requests.Session,
        url: str,
        include_rx: Optional[Pattern[str]],
        exclude_rx: Optional[Pattern[str]],
    ) -> Iterable[Item]:
        seen_codes: Set[str] = set()
        max_pages = 10

        def _iter_page(u: str) -> List[Item]:
            r = session.get(u, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            out: List[Item] = []
            for a in soup.select("a[href]"):
                raw_href = a.get("href")
                href: Optional[str]
                if isinstance(raw_href, list):
                    href = str(raw_href[0]) if raw_href else None
                else:
                    href = str(raw_href) if raw_href else None
                if not href:
                    continue
                href = urljoin(u, href)
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
                raw_title = a.get("title")
                title: Optional[str]
                if isinstance(raw_title, list):
                    title = str(raw_title[0]) if raw_title else None
                else:
                    title = str(raw_title) if raw_title else None
                if not title:
                    title = a.get_text(strip=True) or None
                out.append(Item(code=code, url=cu, title=title, price=None))
            return out

        for it in _iter_page(url):
            yield it

        page = 2
        while page <= max_pages:
            next_url = _set_page(url, page)
            batch = _iter_page(next_url)
            if not batch:
                break
            for it in batch:
                yield it
            page += 1
