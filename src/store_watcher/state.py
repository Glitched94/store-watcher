from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .utils import canonicalize, extract_product_code, utcnow_iso

"""
Unified state schema (per item code):

state[code] = {
  "url": "<canonical product url>",
  "first_seen": "<ISO>",
  "status": 0|1,            # 1 = present this tick, 0 = absent this tick
  "status_since": "<ISO>"   # when status last changed
  "name": "<optional human name>",
}
"""


def make_present_record(
    url: str, now_iso: str, name: str | None = None, host: str | None = None
) -> dict[str, Any]:
    rec: dict[str, Any] = {"url": url, "first_seen": now_iso, "status": 1, "status_since": now_iso}
    if name:
        rec["name"] = name
    if host:
        rec["host"] = host
    return rec


def _migrate_from_list(raw: list) -> dict[str, dict[str, Any]]:
    print("[info] Migrating legacy list -> status machine")
    now = utcnow_iso()
    state: dict[str, dict[str, Any]] = {}
    for u in raw:
        cu = canonicalize(u)
        code = extract_product_code(cu)
        if not code:
            continue
        if code not in state:
            state[code] = make_present_record(cu, now)
    return state


def _migrate_from_dict(raw: dict) -> dict[str, dict[str, Any]]:
    """
    Accept prior dicts keyed by URL or code with either:
    - {'first_seen','last_seen'} timestamps, or
    - already using 'status'/'status_since'
    Normalize to code-keyed status machine.
    """
    print("[info] Migrating legacy dict -> status machine (if needed)")
    now = utcnow_iso()
    migrated: dict[str, dict[str, Any]] = {}

    for k, v in raw.items():
        # Determine identity (code or URL)
        if k.isdigit():
            code = k
            url = v.get("url") or ""
        else:
            url = canonicalize(k)
            code = extract_product_code(url)
            if not code:
                continue

        # If already status-based, keep as-is but normalize fields
        if "status" in v and "status_since" in v:
            first_seen = v.get("first_seen") or now
            status = 1 if v.get("status") else 0
            status_since = v.get("status_since") or first_seen
            name = v.get("name")  # <-- preserve name if present

            entry: dict[str, Any] = {
                "url": url or v.get("url", ""),
                "first_seen": first_seen,
                "status": status,
                "status_since": status_since,
            }
            if name:  # <-- keep it
                entry["name"] = name

            migrated[code] = entry
            continue

        # Else assume last_seen/first_seen model
        first_seen = v.get("first_seen") or v.get("last_seen") or now
        last_seen = v.get("last_seen") or first_seen
        migrated[code] = {
            "url": url or v.get("url", ""),
            "first_seen": first_seen,
            "status": 1,
            "status_since": last_seen,
        }

    return migrated


def _json_path_override(path: Path | None) -> Path:
    return Path(os.getenv("STATE_FILE", str(path or "seen_items.json")))


def _db_path() -> Path | None:
    p = os.getenv("STATE_DB", "").strip()
    return Path(p) if p else None


def migrate_keys_to_composite(
    state: dict[str, dict[str, Any]], default_host: str
) -> dict[str, dict[str, Any]]:
    """
    Upgrade keys like '4380...' -> '<host>:4380...'. If already composite, keep.
    Also ensure each record carries 'host' for future labeling.
    """
    upgraded: dict[str, dict[str, Any]] = {}
    for k, v in state.items():
        if ":" in k:
            host, code = k.split(":", 1)
            v.setdefault("host", host)
            upgraded[k] = v
        else:
            # legacy numeric or url-ish key; prefer numeric code as identity
            code = k if k.isdigit() else (extract_product_code(v.get("url", "")) or k)
            host = v.get("host") or default_host
            new_key = f"{host}:{code}"
            v.setdefault("host", host)
            upgraded[new_key] = v
    return upgraded


def load_state(path: Path | None = None) -> dict[str, dict[str, Any]]:
    db = _db_path()
    if db:
        from .state_sqlite import load_state as _load_sqlite

        return _load_sqlite(db)
    # JSON
    p = _json_path_override(path)
    try:
        if p.exists():
            raw = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                return _migrate_from_list(raw)  # your existing function
            if isinstance(raw, dict):
                return _migrate_from_dict(raw)  # your existing function
    except Exception:
        import traceback

        traceback.print_exc()
    return {}


def save_state(state: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    db = _db_path()
    if db:
        from .state_sqlite import save_state as _save_sqlite

        _save_sqlite(state, db)
        return
    # JSON
    p = _json_path_override(path)
    p.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
