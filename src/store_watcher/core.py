from __future__ import annotations
import os, re, time, traceback
from datetime import timedelta
from typing import Dict, Iterable, Set

from dotenv import load_dotenv
from .utils import make_session, utcnow_iso, iso_to_dt
from .state import load_state, save_state, make_present_record
from .adapters.base import Adapter, Item
from .adapters.disneystore import DisneyStoreAdapter
from .notify import build_notifiers_from_env, render_change_digest, Notifier

ADAPTERS: Dict[str, Adapter] = {
    "disneystore": DisneyStoreAdapter(),
}

def _compile(rx: str | None):
    return re.compile(rx) if rx else None

def run_watcher(
    site: str,
    url_override: str | None,
    interval: int,
    restock_hours: int,
    include_re: str | None,
    exclude_re: str | None,
    once: bool,
) -> None:
    load_dotenv()

    adapter = ADAPTERS.get(site)
    if not adapter:
        raise SystemExit(f"Unknown site adapter: {site}")

    target_url = (url_override or os.getenv("TARGET_URL", "")).strip()
    if not target_url:
        raise SystemExit("Please set TARGET_URL in .env or pass --url")

    include_rx = _compile(include_re or os.getenv("INCLUDE_RE", "").strip() or None)
    exclude_rx = _compile(exclude_re or os.getenv("EXCLUDE_RE", "").strip() or None)

    restock_delta = timedelta(hours=restock_hours)

    from pathlib import Path
    state_path = Path(os.getenv("STATE_FILE", "seen_items.json"))

    # Build notifiers from env (Email/Discord)
    notifiers: list[Notifier] = build_notifiers_from_env()
    if not notifiers:
        print("[warn] No notifiers configured (set SMTP_* or DISCORD_WEBHOOK_URL). Will log only.")

    print(f"[info] Watching: {target_url} via adapter={site}")
    if include_rx: print(f"[info] Include: {include_rx.pattern}")
    if exclude_rx: print(f"[info] Exclude: {exclude_rx.pattern}")
    print(f"[info] Restock window: {restock_hours}h")
    print(f"[info] State file: {state_path}")
    print(f"[info] Notifiers: {', '.join(type(n).__name__ for n in notifiers) or 'none'}")

    state = load_state(state_path)
    print(f"[info] Known items: {len(state)}")

    session = make_session()

    def tick() -> None:
        nonlocal state
        now_iso = utcnow_iso()
        now_dt = iso_to_dt(now_iso)

        # Fetch items
        items: Iterable[Item] = adapter.fetch(
            session=session,
            url=target_url,
            include_rx=include_rx,
            exclude_rx=exclude_rx,
        )
        current_codes: Set[str] = set()
        latest_url_for: Dict[str, str] = {}
        latest_name_for: Dict[str, str] = {}

        for it in items:
            current_codes.add(it.code)
            if it.url:
                latest_url_for[it.code] = it.url
            if it.title:
                latest_name_for[it.code] = it.title

        new_codes: list[str] = []
        restocked_codes: list[str] = []

        # Mark absences
        for code, info in state.items():
            if code not in current_codes and info.get("status", 1) == 1:
                info["status"] = 0
                info["status_since"] = now_iso

        # Handle present items
        for code in current_codes:
            preferred_url = latest_url_for.get(code, state.get(code, {}).get("url", ""))
            preferred_name = latest_name_for.get(code, state.get(code, {}).get("name", None))
            
            if code not in state:
                state[code] = make_present_record(preferred_url, now_iso, preferred_name)
                new_codes.append(code)
            else:
                info = state[code]
                if preferred_url and preferred_url != info.get("url", ""):
                    info["url"] = preferred_url
                # If we have a nicer name now, keep it
                if preferred_name and preferred_name != info.get("name"):
                    info["name"] = preferred_name
                if info.get("status", 0) == 0:
                    absent_since = iso_to_dt(info.get("status_since", now_iso))
                    if now_dt - absent_since >= restock_delta:
                        restocked_codes.append(code)
                    info["status"] = 1
                    info["status_since"] = now_iso
                else:
                    info["status"] = 1

        # Persist & notify
        save_state(state, state_path)

        if new_codes or restocked_codes:
            subject, html_body, text_body = render_change_digest(
                new_codes=new_codes,
                restocked_codes=restocked_codes,
                state=state,
                restock_hours=restock_hours,
                target_url=target_url,
                total_count=len(current_codes),
            )
            for n in notifiers:
                try:
                    n.send(subject, html_body, text_body)
                except Exception:
                    traceback.print_exc()

        print(f"[info] tick: current={len(current_codes)} new={len(new_codes)} restocked={len(restocked_codes)} known={len(state)}")

    while True:
        try:
            tick()
        except Exception:
            traceback.print_exc()
        if once:
            break
        time.sleep(interval)
