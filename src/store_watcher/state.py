from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any

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

def make_present_record(url: str, now_iso: str, name: str | None = None) -> Dict[str, Any]:
    return {"url": url, "first_seen": now_iso, "status": 1, "status_since": now_iso, **({"name": name} if name else {})}

def _migrate_from_list(raw: list) -> Dict[str, Dict[str, Any]]:
    print("[info] Migrating legacy list -> status machine")
    now = utcnow_iso()
    state: Dict[str, Dict[str, Any]] = {}
    for u in raw:
        cu = canonicalize(u)
        code = extract_product_code(cu)
        if not code:
            continue
        if code not in state:
            state[code] = make_present_record(cu, now)
    return state

def _migrate_from_dict(raw: dict) -> Dict[str, Dict[str, Any]]:
    """
    Accept prior dicts keyed by URL or code with either:
    - {'first_seen','last_seen'} timestamps, or
    - already using 'status'/'status_since'
    Normalize to code-keyed status machine.
    """
    print("[info] Migrating legacy dict -> status machine (if needed)")
    now = utcnow_iso()
    migrated: Dict[str, Dict[str, Any]] = {}

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

            entry: Dict[str, Any] = {
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

def load_state(path: Path) -> Dict[str, Dict[str, Any]]:
    try:
        if path.exists():
            raw = json.loads(path.read_text())
            if isinstance(raw, list):
                return _migrate_from_list(raw)
            if isinstance(raw, dict):
                return _migrate_from_dict(raw)
    except Exception as ex:
        print("[error] Failed to load state:", ex)
    return {}

def save_state(state: Dict[str, Dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(state, indent=2, sort_keys=True))
