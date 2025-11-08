from __future__ import annotations

import os
import re
import time
import traceback
from collections.abc import Iterable
from datetime import timedelta
from pathlib import Path
from typing import Optional, Pattern

from dotenv import load_dotenv

from .adapters.base import Adapter, Item
from .adapters.sfcc import SFCCGridAdapter
from .notify import Notifier, build_notifiers_from_env, render_change_digest
from .state import load_state, make_present_record, migrate_keys_to_composite, save_state
from .utils import domain_of, iso_to_dt, make_session, pretty_name_from_url, site_label, utcnow_iso

ADAPTERS: dict[str, Adapter] = {
    "sfcc": SFCCGridAdapter(),
    "disneystore": SFCCGridAdapter(),  # alias for convenience
}


def _compile(rx: Optional[str]) -> Optional[Pattern[str]]:
    return re.compile(rx) if rx else None


def _split_urls(urls: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"[,\n]", urls) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for p in parts:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


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

    env_single = os.getenv("TARGET_URL", "").strip()
    env_multi = os.getenv("TARGET_URLS", "").strip()
    urls: list[str] = []

    if url_override:
        urls = _split_urls(url_override)
    elif env_multi:
        urls = _split_urls(env_multi)
    elif env_single:
        urls = [env_single]

    if not urls:
        raise SystemExit("Set TARGET_URL or TARGET_URLS in .env, or pass --url/--urls")

    default_host = domain_of(urls[0])

    include_rx = _compile(include_re or os.getenv("INCLUDE_RE", "").strip() or None)
    exclude_rx = _compile(exclude_re or os.getenv("EXCLUDE_RE", "").strip() or None)
    restock_delta = timedelta(hours=restock_hours)

    state_db = os.getenv("STATE_DB", "").strip()
    state_path = Path(os.getenv("STATE_FILE", "seen_items.json"))

    notifiers: list[Notifier] = build_notifiers_from_env()
    if not notifiers:
        print("[warn] No notifiers configured (set SMTP_* or DISCORD_WEBHOOK_URL). Will log only.")

    print(f"[info] Watching {len(urls)} URL(s) via adapter={site}")
    for u in urls:
        print(f"       - {u} [{site_label(u)}]")
    if include_rx:
        print(f"[info] Include: {include_rx.pattern}")
    if exclude_rx:
        print(f"[info] Exclude: {exclude_rx.pattern}")
    print(f"[info] Restock window: {restock_hours}h")

    if state_db:
        print(f"[info] State backend: sqlite ({state_db})")
    else:
        print(f"[info] State backend: json ({state_path})")

    print(f"[info] Notifiers: {', '.join(type(n).__name__ for n in notifiers) or 'none'}")

    state = load_state(state_path)
    state = migrate_keys_to_composite(state, default_host)
    save_state(state, state_path)
    print(f"[info] Known items: {len(state)}")

    session = make_session()

    def tick() -> None:
        nonlocal state
        now_iso = utcnow_iso()
        now_dt = iso_to_dt(now_iso)

        site_current_counts: dict[str, int] = {}
        site_new: dict[str, list[str]] = {}
        site_restocked: dict[str, list[str]] = {}

        present_keys: set[str] = set()
        url_for_key: dict[str, str] = {}
        name_for_key: dict[str, str] = {}
        image_for_key: dict[str, str] = {}

        for url in urls:
            host = domain_of(url)
            label = site_label(url)
            items: Iterable[Item] = adapter.fetch(
                session=session,
                url=url,
                include_rx=include_rx,
                exclude_rx=exclude_rx,
            )
            count = 0
            for it in items:
                count += 1
                key = f"{host}:{it.code}"
                present_keys.add(key)
                if it.url:
                    url_for_key[key] = it.url
                # prefer adapter title; else derive from URL
                if it.title:
                    name_for_key[key] = it.title
                elif it.url:
                    fallback = pretty_name_from_url(it.url)
                    if fallback:
                        name_for_key[key] = fallback
                if it.image:
                    image_for_key[key] = it.image
            site_current_counts[label] = site_current_counts.get(label, 0) + count

        for key, info in state.items():
            if key not in present_keys and info.get("status", 1) == 1:
                info["status"] = 0
                info["status_since"] = now_iso

        for key in present_keys:
            preferred_url = url_for_key.get(key, state.get(key, {}).get("url", ""))
            preferred_name = name_for_key.get(key) or state.get(key, {}).get("name")
            preferred_img = image_for_key.get(key, state.get(key, {}).get("image", ""))

            if key not in state:
                host, _code = key.split(":", 1)
                rec = make_present_record(preferred_url, now_iso, preferred_name, host=host)
                if preferred_img:
                    rec["image"] = preferred_img
                state[key] = rec
                lab = site_label(host)
                site_new.setdefault(lab, []).append(key)
            else:
                info = state[key]
                if preferred_url and preferred_url != info.get("url", ""):
                    info["url"] = preferred_url
                if preferred_name and preferred_name != info.get("name"):
                    info["name"] = preferred_name
                if preferred_img and not info.get("image"):
                    info["image"] = preferred_img
                info.setdefault("host", key.split(":", 1)[0])
                if info.get("status", 0) == 0:
                    absent_since = iso_to_dt(info.get("status_since", now_iso))
                    if now_dt - absent_since >= restock_delta:
                        lab = site_label(key.split(":", 1)[0])
                        site_restocked.setdefault(lab, []).append(key)
                    info["status"] = 1
                    info["status_since"] = now_iso
                else:
                    info["status"] = 1

        save_state(state, state_path)

        new_codes: list[str] = []
        restocked_codes: list[str] = []
        for _lab, keys in site_new.items():
            new_codes.extend(keys)
        for _lab, keys in site_restocked.items():
            restocked_codes.extend(keys)

        total_now = sum(site_current_counts.values())

        if new_codes or restocked_codes:
            subject, html_body, text_body = render_change_digest(
                new_codes=new_codes,
                restocked_codes=restocked_codes,
                state=state,
                restock_hours=restock_hours,
                target_url="(multiple)",
                total_count=total_now,
            )
            for n in notifiers:
                try:
                    n.send(subject, html_body, text_body)
                except Exception:
                    traceback.print_exc()

        print(
            "[info] tick: "
            f"total={total_now} new={len(new_codes)} "
            f"restocked={len(restocked_codes)} known={len(state)}"
        )

    while True:
        try:
            tick()
        except Exception:
            traceback.print_exc()
        if once:
            break
        time.sleep(interval)
