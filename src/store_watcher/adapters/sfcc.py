from __future__ import annotations

import re
from typing import Iterable, List, Optional, Pattern, Set
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from bs4.element import Tag

from ..utils import (
    canonicalize,
    extract_product_code,
    img_src_from_tag,
    tune_image_url,
)
from .base import Adapter, Item

# SFCC-style product URLs typically end in "...-<digits>.html" (ignore query strings)
PRODUCT_LINK_RE = re.compile(r"/[^/]+\.html(?:\?|$)", re.I)


def as_tag(obj: object | None) -> Optional[Tag]:
    """Return obj if it is a bs4 Tag, else None (filters out NavigableString/ints/etc)."""
    return obj if isinstance(obj, Tag) else None


# Many SFCC themes use one of these class fragments on the product card container.
_CARD_CLASS_RX = re.compile(
    r"(product|tile|grid|card|result|hit|search|listing|item|cell|slot)", re.I
)


def find_card_container(a: Tag) -> Optional[Tag]:
    """
    Walk up a few ancestors from the product <a> to find a 'card' container that likely holds the image.
    """
    node: Optional[Tag] = a
    for _ in range(8):
        if node is None:
            return None
        classes = " ".join(node.get("class", [])).lower()
        if _CARD_CLASS_RX.search(classes):
            return node
        node = as_tag(getattr(node, "parent", None))
    return None


def find_image_near(card_or_link: Tag, base_url: str) -> Optional[str]:
    """
    Heuristic to find a product image URL near the given card/link:
    - prefer <picture><source> src/srcset
    - else <img> src/data-src/srcset
    - search in the element itself, then its ancestors, then a few siblings
    """
    # 1) Within the given node
    for node in (card_or_link,):
        pic = as_tag(node.find("picture"))
        if pic is not None:
            src = as_tag(pic.find("source"))
            if src is not None:
                u = img_src_from_tag(base_url, src)
                if u:
                    return u
        img = as_tag(node.find("img"))
        if img is not None:
            u = img_src_from_tag(base_url, img)
            if u:
                return u

    # 2) Within ancestors up to 8 levels
    parent = as_tag(getattr(card_or_link, "parent", None))
    for _ in range(8):
        if parent is None:
            break
        pic = as_tag(parent.find("picture"))
        if pic is not None:
            src = as_tag(pic.find("source"))
            if src is not None:
                u = img_src_from_tag(base_url, src)
                if u:
                    return u
        img = as_tag(parent.find("img"))
        if img is not None:
            u = img_src_from_tag(base_url, img)
            if u:
                return u
        parent = as_tag(getattr(parent, "parent", None))

    # 3) Look at a few next/prev siblings (some US cards split image/text into sibling nodes)
    sib = as_tag(getattr(card_or_link, "next_sibling", None))
    for _ in range(4):
        if sib is None:
            break
        pic = as_tag(getattr(sib, "find", lambda *_a, **_k: None)("picture"))
        if pic is not None:
            src = as_tag(pic.find("source"))
            if src is not None:
                u = img_src_from_tag(base_url, src)
                if u:
                    return u
        img = as_tag(getattr(sib, "find", lambda *_a, **_k: None)("img"))
        if img is not None:
            u = img_src_from_tag(base_url, img)
            if u:
                return u
        sib = as_tag(getattr(sib, "next_sibling", None))

    sib = as_tag(getattr(card_or_link, "previous_sibling", None))
    for _ in range(4):
        if sib is None:
            break
        pic = as_tag(getattr(sib, "find", lambda *_a, **_k: None)("picture"))
        if pic is not None:
            src = as_tag(pic.find("source"))
            if src is not None:
                u = img_src_from_tag(base_url, src)
                if u:
                    return u
        img = as_tag(getattr(sib, "find", lambda *_a, **_k: None)("img"))
        if img is not None:
            u = img_src_from_tag(base_url, img)
            if u:
                return u
        sib = as_tag(getattr(sib, "previous_sibling", None))

    return None


class SFCCGridAdapter(Adapter):
    """
    Generic adapter for SFCC grid pages (server-rendered HTML).
    Walks grid <a> links, extracts code, title, and best-effort image from the same card.
    """

    def fetch(
        self,
        session: requests.Session,
        url: str,
        include_rx: Optional[Pattern[str]],
        exclude_rx: Optional[Pattern[str]],
    ) -> Iterable[Item]:
        seen_codes: Set[str] = set()
        max_pages = 10  # safety cap

        def _set_page(u: str, page_idx: int) -> str:
            # Many SFCC grids accept start= & sz=; page_idx starts at 1.
            from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

            sp = urlsplit(u)
            qs = dict(parse_qsl(sp.query, keep_blank_values=True))
            if "start" in qs and "sz" in qs:
                try:
                    sz = int(qs.get("sz", "0") or "0")
                    if sz > 0:
                        qs["start"] = str((page_idx - 1) * sz)
                except Exception:
                    pass
            else:
                return u
            return urlunsplit((sp.scheme, sp.netloc, sp.path, urlencode(qs), sp.fragment))

        def _iter_page(u: str) -> List[Item]:
            r = session.get(u, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            out: List[Item] = []

            # Find anchors that look like product tiles, then try to find the closest image inside the same card.
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

                # Locate container and image
                card = find_card_container(a) or a
                img_url = find_image_near(card, u)
                if img_url:
                    img_url = tune_image_url(img_url, size=768, quality=100)

                out.append(Item(code=code, url=cu, title=title, price=None, image=img_url))
            return out

        # Page 1
        for it in _iter_page(url):
            yield it

        # Additional pages (best effort; some regions may ignore)
        page = 2
        while page <= max_pages:
            next_url = _set_page(url, page)
            batch = _iter_page(next_url)
            if not batch:
                break
            for it in batch:
                yield it
            page += 1
