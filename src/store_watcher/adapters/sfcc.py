from __future__ import annotations

import os
import re
from typing import Any, Dict, Iterable, List, Optional, Pattern, Set, Tuple
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

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


_SFCC_PATH_RX = re.compile(r"^/on/demandware\.store/([^/]+)/([^/]+)/", re.I)
DEFAULT_REGION_SLUG = "Sites-shopDisney-Site"
DEFAULT_LOCALE = "default"


def _extract_region_slug_and_locale(u: str) -> Tuple[str, str]:
    """
    Parse the region slug and locale segment from an SFCC URL path.
    Falls back to default values when the pattern is absent.
    """
    sp = urlsplit(u)
    match = _SFCC_PATH_RX.search(sp.path)
    if match:
        return match.group(1), match.group(2)
    return DEFAULT_REGION_SLUG, DEFAULT_LOCALE


def _region_locale_from_env_or_url(u: str) -> Tuple[str, str]:
    env_region = (os.getenv("TARGET_REGION_SLUG") or "").strip()
    env_locale = (os.getenv("TARGET_LOCALE") or "").strip()
    if env_region and env_locale:
        return env_region, env_locale
    return _extract_region_slug_and_locale(u)


def _build_variation_url(u: str, code: str, *, quantity: int = 1) -> str:
    sp = urlsplit(u)
    root = urlunsplit((sp.scheme or "https", sp.netloc, "", "", ""))
    region_slug, locale = _region_locale_from_env_or_url(u)
    path = f"/on/demandware.store/{region_slug}/{locale}/Product-Variation"
    query = urlencode({"pid": code, "quantity": max(1, int(quantity))})
    return urljoin(root, urlunsplit(("", "", path, query, "")))


def build_grid_url(
    host: str,
    region_slug: str,
    locale: str,
    category_slug: str,
    *,
    scheme: str = "https",
    start: int = 0,
    size: int = 200,
) -> str:
    """
    Construct an SFCC Search-UpdateGrid URL from discrete components.
    """
    root = urlunsplit((scheme or "https", host, "", "", ""))
    path = f"/on/demandware.store/{region_slug}/{locale}/Search-UpdateGrid"
    query = urlencode({"cgid": category_slug, "start": start, "sz": size})
    return urljoin(root, urlunsplit(("", "", path, query, "")))


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
        details_cache: Dict[str, Optional[Dict[str, Any]]] = {}

        def _fetch_variation(code: str) -> Optional[Dict[str, Any]]:
            if code in details_cache:
                return details_cache[code]

            detail_url = _build_variation_url(url, code, quantity=10_000)
            try:
                r = session.get(detail_url, timeout=20)
                r.raise_for_status()
                payload = r.json()
            except Exception:
                details_cache[code] = None
                return None

            parsed = _parse_variation_payload(payload)
            details_cache[code] = parsed
            return parsed

        def _enrich(item: Item) -> Item:
            # Fetch structured availability + images from the Product-Variation endpoint
            details = _fetch_variation(item.code)
            if not details:
                return item

            if details.get("image"):
                item.image = tune_image_url(str(details["image"]), size=768, quality=100)
            if details.get("url"):
                item.url = canonicalize(urljoin(url, str(details["url"])))
            if details.get("title") and not item.title:
                item.title = str(details["title"])
            if details.get("price"):
                item.price = str(details["price"])
            if details.get("available") is not None:
                item.available = bool(details["available"])
            if details.get("availability_message"):
                item.availability = str(details["availability_message"])
            if details.get("in_stock_allocation") is not None:
                try:
                    item.in_stock_allocation = int(details["in_stock_allocation"])
                except Exception:
                    item.in_stock_allocation = None
            return item

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
            yield _enrich(it)

        # Additional pages (best effort; some regions may ignore)
        page = 2
        while page <= max_pages:
            next_url = _set_page(url, page)
            batch = _iter_page(next_url)
            if not batch:
                break
            for it in batch:
                yield _enrich(it)
            page += 1

    def fetch_details(self, session: requests.Session, url: str, code: str) -> Optional[Item]:
        detail_url = _build_variation_url(url, code, quantity=10_000)
        try:
            r = session.get(detail_url, timeout=20)
            r.raise_for_status()
            payload = r.json()
        except Exception:
            item = Item(code=code, url="")
            item.in_stock_allocation = 0
            item.available = False
            return item

        parsed = _parse_variation_payload(payload)
        if not parsed:
            item = Item(code=code, url="")
            item.in_stock_allocation = 0
            item.available = False
            return item

        item = Item(code=code, url="")
        if parsed.get("url"):
            item.url = canonicalize(urljoin(url, str(parsed["url"])))
        if parsed.get("title"):
            item.title = str(parsed["title"])
        if parsed.get("price"):
            item.price = str(parsed["price"])
        if parsed.get("available") is not None:
            item.available = bool(parsed["available"])
        if parsed.get("availability_message"):
            item.availability = str(parsed["availability_message"])
        if parsed.get("image"):
            item.image = tune_image_url(str(parsed["image"]), size=768, quality=100)
        if parsed.get("in_stock_allocation") is not None:
            try:
                item.in_stock_allocation = int(parsed["in_stock_allocation"])
            except Exception:
                item.in_stock_allocation = 0

        return item


def _parse_variation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract useful fields from a Product-Variation response.
    Returns keys: available (bool|None), availability_message (str|None), image (str|None),
    url (str|None), title (str|None), price (str|None)
    """
    product = payload.get("product") or {}

    availability_data = product.get("availability") or {}
    messages = availability_data.get("messages") or []
    message: Optional[str] = None
    if isinstance(messages, list) and messages:
        first = messages[0]
        if isinstance(first, str):
            message = first.strip() or None

    stock_allocation_raw = availability_data.get("inStockAllocation")
    stock_allocation: int
    if isinstance(stock_allocation_raw, int):
        stock_allocation = stock_allocation_raw
    elif isinstance(stock_allocation_raw, str):
        try:
            stock_allocation = int(stock_allocation_raw)
        except Exception:
            stock_allocation = 0
    else:
        stock_allocation = 0

    available = stock_allocation > 0

    if message is None and isinstance(availability_data.get("displayLowStockMessage"), bool):
        if availability_data.get("displayLowStockMessage"):
            message = "Low Stock"
        elif available is False:
            message = "Out of Stock"

    # Prefer the feature media (includes tuned imgSrc values)
    image: Optional[str] = None
    product_media = payload.get("productMedia") or {}
    feature = product_media.get("feature") or {}
    feature_images = feature.get("images") or []
    if isinstance(feature_images, list):
        for img in feature_images:
            if not isinstance(img, dict):
                continue
            image = img.get("imgSrc") or img.get("url")
            if image:
                title = img.get("title") or img.get("alt")
                break
        else:
            title = None
    else:
        title = None

    # Fallback to product.images.highRes
    if image is None:
        imgs = (product.get("images") or {}).get("highRes") or []
        if isinstance(imgs, list):
            for img in imgs:
                if not isinstance(img, dict):
                    continue
                image = img.get("imgSrc") or img.get("url")
                if image and not title:
                    title = img.get("title") or img.get("alt")
                if image:
                    break

    # Use the structured display name if available
    if not title:
        custom = product.get("custom") or {}
        prod_name = custom.get("productDisplayName")
        if isinstance(prod_name, str) and prod_name.strip():
            title = prod_name.strip()

    price_data = (product.get("price") or {}).get("sales") or {}
    price = price_data.get("formatted") if isinstance(price_data, dict) else None

    product_url = product.get("selectedProductUrl")
    if not isinstance(product_url, str):
        product_url = None

    return {
        "available": available,
        "availability_message": message,
        "image": image,
        "url": product_url,
        "title": title,
        "price": price,
        "in_stock_allocation": stock_allocation,
    }
