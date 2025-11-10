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


def _compile(rx: Optional[str]) -> Optional[Pattern[str]]:
    return re.compile(rx) if rx else None


def _make_present_record(
    url: str,
    now_iso: str,
    name: str | None = None,
    host: str | None = None,
    image: str | None = None,
) -> Dict[str, Any]:
    rec: Dict[str, Any] = {
        "url": url,
        "first_seen": now_iso,
        "status": 1,
        "status_since": now_iso,
    }
    if name:
        rec["name"] = name
    if host:
        rec["host"] = host
    if image:
        rec["image"] = image
    return rec


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
    url = url_override or os.getenv("TARGET_URL", "").strip()
    if not url:
        raise SystemExit("Set TARGET_URL in env or pass --url")

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

        # fetch current items
        items_iter: Iterable[Item] = adapter.fetch(
            session=session, url=url, include_rx=include_rx, exclude_rx=exclude_rx
        )
        for it in items_iter:
            site_current_count += 1
            key = f"{managed_host}:{it.code}"
            present_keys.add(key)
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

            if key not in state:
                rec = _make_present_record(
                    preferred_url,
                    now_iso,
                    preferred_name,
                    host=managed_host,
                    image=preferred_img or None,
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
                info.setdefault("host", managed_host)
                if info.get("status", 0) == 0:
                    absent_since = iso_to_dt(info.get("status_since", now_iso))
                    if now_dt - absent_since >= restock_delta:
                        site_restocked.setdefault(label, []).append(key)
                    info["status"] = 1
                    info["status_since"] = now_iso
                else:
                    info["status"] = 1

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
