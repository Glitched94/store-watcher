from __future__ import annotations

import os
import re
import time
import traceback
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Pattern

from dotenv import load_dotenv

from .adapters.base import Adapter, Item
from .adapters.sfcc import SFCCGridAdapter
from .db.config import ensure_listener_schema
from .db.items import load_items_dict, save_items
from .notify import build_notifiers_from_db, render_change_digest
from .utils import (
    domain_of,
    iso_to_dt,
    make_session,
    pretty_name_from_url,
    site_label,
    utcnow_iso,
)

ADAPTERS: dict[str, Adapter] = {
    "sfcc": SFCCGridAdapter(),
    "disneystore": SFCCGridAdapter(),  # alias
}


MULTIPLE_URLS_ERROR = "Only a single URL is supported. Run one watcher per target page."


def _compile(rx: Optional[str]) -> Optional[Pattern[str]]:
    return re.compile(rx) if rx else None


def normalize_single_url(raw: str | None) -> str:
    """
    Trim the input and ensure only one URL is provided.

    Accepts comma or newline separators, raising if multiple entries are detected.
    Returns an empty string when the input is None or blank.
    """

    if raw is None:
        return ""

    candidates = [p.strip() for p in re.split(r"[,\n]", raw) if p.strip()]
    if len(candidates) > 1:
        raise ValueError(MULTIPLE_URLS_ERROR)

    return candidates[0] if candidates else ""


def _resolve_target_url(url_override: str | None) -> str:
    """
    Prefer an explicit URL (override or TARGET_URL). If absent, assemble a grid URL
    from discrete SFCC components (TARGET_HOST, TARGET_REGION_SLUG, TARGET_LOCALE,
    TARGET_CATEGORY_SLUG). Returns an empty string when insufficient data is provided.
    """
    direct = normalize_single_url(url_override or os.getenv("TARGET_URL", "").strip())
    if direct:
        return direct

    host = (os.getenv("TARGET_HOST") or "").strip()
    region = (os.getenv("TARGET_REGION_SLUG") or "").strip()
    locale = (os.getenv("TARGET_LOCALE") or "").strip()
    category = (os.getenv("TARGET_CATEGORY_SLUG") or "").strip()
    start = int(os.getenv("TARGET_START", "0") or 0)
    size = int(os.getenv("TARGET_PAGE_SIZE", "200") or 200)
    scheme = (os.getenv("TARGET_SCHEME") or "https").strip() or "https"

    if host and region and locale and category:
        from .adapters.sfcc import build_grid_url

        return build_grid_url(
            host=host,
            region_slug=region,
            locale=locale,
            category_slug=category,
            scheme=scheme,
            start=start,
            size=size,
        )

    return ""


def _make_present_record(
    url: str,
    now_iso: str,
    name: str | None = None,
    host: str | None = None,
    image: str | None = None,
    price: str | None = None,
    availability_message: str | None = None,
    available: bool | None = None,
    in_stock_allocation: int | None = None,
    status: int = 1,
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "url": url,
        "first_seen": now_iso,
        "status": status,
        "status_since": now_iso,
    }
    if name:
        rec["name"] = name
    if host:
        rec["host"] = host
    if image:
        rec["image"] = image
    if price:
        rec["price"] = price
    rec["price_changed"] = False
    if availability_message:
        rec["availability_message"] = availability_message
    rec["availability_changed"] = False
    if available is not None:
        rec["available"] = available
    if in_stock_allocation is not None:
        rec["in_stock_allocation"] = in_stock_allocation
    return rec


def _apply_change_tracking(
    info: Dict[str, Any],
    *,
    price: str | None = None,
    availability_message: str | None = None,
    available: bool | None = None,
) -> None:
    price_changed = False
    if price:
        current_price = info.get("price")
        if price != current_price:
            info["prev_price"] = current_price or ""
            info["price"] = price
            price_changed = True
    info["price_changed"] = price_changed

    availability_changed = False
    if availability_message:
        current_message = info.get("availability_message")
        if availability_message != current_message:
            info["prev_availability_message"] = current_message or ""
            info["availability_message"] = availability_message
            availability_changed = True
    if available is not None:
        current_available = info.get("available")
        if available != current_available:
            info["prev_available"] = current_available
            info["available"] = available
            availability_changed = True
    info["availability_changed"] = availability_changed


def _migrate_keys_to_composite(
    state: Dict[str, Dict[str, Any]], default_host: str
) -> Dict[str, Dict[str, Any]]:
    """
    Upgrade keys like '4380...' -> '<host>:4380...'. If already composite, keep.
    Ensure each record carries 'host'.
    """
    upgraded: Dict[str, Dict[str, Any]] = {}
    for k, v in state.items():
        if ":" in k:
            host, _code = k.split(":", 1)
            v.setdefault("host", host)
            upgraded[k] = v
        else:
            # legacy numeric key – use default_host as prefix
            new_key = f"{default_host}:{k}"
            v.setdefault("host", default_host)
            upgraded[new_key] = v
    return upgraded


def run_watcher(
    site: str,
    url_override: str | None,
    interval: int,
    restock_hours: int,
    include_re: str | None,
    exclude_re: str | None,
    once: bool,
    dotenv_path: str | None = None,
) -> None:
    load_dotenv(dotenv_path=dotenv_path)

    adapter = ADAPTERS.get(site) or ADAPTERS["sfcc"]

    # ---- SINGLE URL ONLY ----
    try:
        url = _resolve_target_url(url_override)
    except ValueError as exc:
        raise SystemExit(str(exc))

    if not url:
        raise SystemExit(
            "Set TARGET_URL in env, pass --url, or provide TARGET_HOST + TARGET_REGION_SLUG + "
            "TARGET_LOCALE + TARGET_CATEGORY_SLUG"
        )

    state_db = os.getenv("STATE_DB", "").strip()
    if not state_db:
        raise SystemExit("Set STATE_DB to a writable SQLite path (e.g. /app/data/state.db)")

    default_host = domain_of(url)
    include_rx = _compile(include_re or os.getenv("INCLUDE_RE", "").strip() or None)
    exclude_rx = _compile(exclude_re or os.getenv("EXCLUDE_RE", "").strip() or None)
    restock_delta = timedelta(hours=restock_hours)

    watcher_label = site_label(url)

    # ---- Notifiers from DB only ----
    ensure_listener_schema(Path(state_db))
    notifiers = build_notifiers_from_db(state_db, watcher_label)

    print(f"[info] Watching: {url} via adapter={site}")
    if include_rx:
        print(f"[info] Include: {include_rx.pattern}")
    if exclude_rx:
        print(f"[info] Exclude: {exclude_rx.pattern}")
    print(f"[info] Restock window: {restock_hours}h")
    print(f"[info] State backend: sqlite ({state_db})")

    # Load current state (SQLite only) and normalize keys
    state = load_items_dict(Path(state_db))
    state = _migrate_keys_to_composite(state, default_host)
    save_items(state, Path(state_db))  # persist any migrations
    print(f"[info] Known items: {len(state)}")

    session = make_session()
    managed_host = domain_of(url)
    label = site_label(url)

    def tick() -> None:
        nonlocal state
        now_iso = utcnow_iso()
        now_dt = iso_to_dt(now_iso)

        site_current_count = 0
        site_new: dict[str, list[str]] = {}
        site_restocked: dict[str, list[str]] = {}

        present_keys: set[str] = set()
        url_for_key: dict[str, str] = {}
        name_for_key: dict[str, str] = {}
        image_for_key: dict[str, str] = {}
        price_for_key: dict[str, str] = {}
        availability_message_for_key: dict[str, str] = {}
        available_for_key: dict[str, Optional[bool]] = {}
        allocation_for_key: dict[str, Optional[int]] = {}

        # fetch current items
        items_iter: Iterable[Item] = adapter.fetch(
            session=session, url=url, include_rx=include_rx, exclude_rx=exclude_rx
        )
        for it in items_iter:
            key = f"{managed_host}:{it.code}"
            present_keys.add(key)
            is_available = it.available
            if is_available is not False:
                site_current_count += 1
            available_for_key[key] = is_available
            if it.url:
                url_for_key[key] = it.url
            if it.title:
                name_for_key[key] = it.title
            elif it.url:
                fallback = pretty_name_from_url(it.url)
                if fallback:
                    name_for_key[key] = fallback
            if it.image:
                image_for_key[key] = it.image
            if it.price:
                price_for_key[key] = it.price
            if it.availability:
                availability_message_for_key[key] = it.availability
            allocation_for_key[key] = it.in_stock_allocation

        # mark absences (only for our host)
        for key, info in state.items():
            key_host = key.split(":", 1)[0]
            if key_host != managed_host:
                continue
            if key not in present_keys and info.get("status", 1) == 1:
                info["status"] = 0
                info["status_since"] = now_iso

        # handle present items
        for key in present_keys:
            preferred_url = url_for_key.get(key, state.get(key, {}).get("url", ""))
            preferred_name = name_for_key.get(key) or state.get(key, {}).get("name")
            preferred_img = image_for_key.get(key, state.get(key, {}).get("image", ""))
            preferred_price = price_for_key.get(key) or state.get(key, {}).get("price")
            preferred_availability_msg = availability_message_for_key.get(key) or state.get(
                key, {}
            ).get("availability_message")
            preferred_available = available_for_key.get(
                key, state.get(key, {}).get("available", True)
            )
            preferred_allocation = allocation_for_key.get(
                key, state.get(key, {}).get("in_stock_allocation")
            )

            if key not in state:
                rec = _make_present_record(
                    preferred_url,
                    now_iso,
                    preferred_name,
                    host=managed_host,
                    image=preferred_img or None,
                    price=preferred_price,
                    availability_message=preferred_availability_msg,
                    available=preferred_available if preferred_available is not None else None,
                    in_stock_allocation=(
                        preferred_allocation if preferred_allocation is not None else None
                    ),
                    status=1 if preferred_available is not False else 0,
                )
                state[key] = rec
                site_new.setdefault(label, []).append(key)
            else:
                info = state[key]
                if preferred_url and preferred_url != info.get("url", ""):
                    info["url"] = preferred_url
                if preferred_name and preferred_name != info.get("name"):
                    info["name"] = preferred_name
                if preferred_img and not info.get("image"):
                    info["image"] = preferred_img
                _apply_change_tracking(
                    info,
                    price=preferred_price,
                    availability_message=preferred_availability_msg,
                    available=preferred_available,
                )
                if preferred_allocation is not None:
                    info["in_stock_allocation"] = preferred_allocation
                info.setdefault("host", managed_host)
                if preferred_available is False:
                    if info.get("status", 0) != 0:
                        info["status_since"] = now_iso
                    info["status"] = 0
                else:
                    if info.get("status", 0) == 0:
                        absent_since = iso_to_dt(info.get("status_since", now_iso))
                        if now_dt - absent_since >= restock_delta:
                            site_restocked.setdefault(label, []).append(key)
                        info["status"] = 1
                        info["status_since"] = now_iso
                    else:
                        info["status"] = 1

        # Re-check all known items for this host (not just ones seen in the grid)
        host_keys = [k for k in state if k.split(":", 1)[0] == managed_host]
        for key in host_keys:
            if key in present_keys:
                continue
            code = key.split(":", 1)[-1]
            try:
                detail_item = adapter.fetch_details(session=session, url=url, code=code)
            except Exception:
                detail_item = None
            if not detail_item:
                continue

            detail_record = state.get(key)
            if detail_record is None:
                continue
            info_detail: Dict[str, Any] = detail_record

            prev_status = int(info_detail.get("status", 0))
            prev_status_since_raw = info_detail.get("status_since", now_iso)
            prev_status_since = (
                iso_to_dt(prev_status_since_raw) if prev_status_since_raw else now_dt
            )

            if detail_item.url:
                info_detail["url"] = detail_item.url
            if detail_item.title:
                info_detail["name"] = detail_item.title
            if detail_item.image and not info_detail.get("image"):
                info_detail["image"] = detail_item.image
            _apply_change_tracking(
                info_detail,
                price=detail_item.price,
                availability_message=detail_item.availability,
                available=detail_item.available,
            )
            if detail_item.in_stock_allocation is not None:
                info_detail["in_stock_allocation"] = detail_item.in_stock_allocation

            # Update status based on refreshed availability
            if detail_item.available is False:
                if prev_status != 0:
                    info_detail["status_since"] = now_iso
                info_detail["status"] = 0
            elif detail_item.available is True:
                if prev_status == 0:
                    if now_dt - prev_status_since >= restock_delta:
                        site_restocked.setdefault(label, []).append(key)
                    info_detail["status_since"] = now_iso
                info_detail["status"] = 1

        # persist (SQLite only)
        save_items(state, Path(state_db))

        # notify
        new_codes: list[str] = []
        restocked_codes: list[str] = []
        for _lab, keys in site_new.items():
            new_codes.extend(keys)
        for _lab, keys in site_restocked.items():
            restocked_codes.extend(keys)
        total_now = site_current_count

        if new_codes or restocked_codes:
            subject, html_body, text_body = render_change_digest(
                new_codes=new_codes,
                restocked_codes=restocked_codes,
                state=state,
                restock_hours=restock_hours,
                target_url=url,
                total_count=total_now,
            )
            for n in notifiers:
                try:
                    n.send(subject, html_body, text_body)
                except Exception:
                    traceback.print_exc()

        print(
            "[info] tick: total={} new={} restocked={} known={}".format(
                total_now, len(new_codes), len(restocked_codes), len(state)
            )
        )

    while True:
        try:
            tick()
        except Exception:
            traceback.print_exc()
        if once:
            break
        time.sleep(interval)
