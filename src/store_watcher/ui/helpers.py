from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypedDict

from fastapi import HTTPException
from starlette.requests import Request

from ..state_sqlite import load_state as load_state_sqlite


class SessionUser(TypedDict, total=False):
    sub: Optional[str]
    email: str
    name: Optional[str]
    picture: Optional[str]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _h_since(iso: Optional[str]) -> Optional[float]:
    if not iso:
        return None
    s = iso.replace("Z", "+00:00")
    try:
        then = datetime.fromisoformat(s)
    except Exception:
        return None
    return max(0.0, (_utcnow() - then).total_seconds() / 3600.0)


def _safe_env(name: str, default: str = "") -> str:
    # Never leak secrets in cleartext
    value = os.getenv(name, default)
    if not value:
        return default
    if any(k in name for k in ("PASS", "TOKEN", "KEY", "SECRET")):
        return "••••••••"
    return value


def _require_user(request: Request) -> SessionUser:
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=307, headers={"Location": "/login"})
    return user


def _load_state_any() -> Dict[str, Dict[str, Any]]:
    db = os.getenv("STATE_DB")
    if db:
        return load_state_sqlite(Path(db))
    f = Path(os.getenv("STATE_FILE", "seen_items.json"))
    return json.loads(f.read_text()) if f.exists() else {}


def _state_version() -> str:
    """
    For cache-busting, use mtime of the chosen backend file (DB or JSON).
    """
    _backend, path = _state_sources()
    try:
        return str(int(path.stat().st_mtime))
    except Exception:
        return "0"


def _state_sources() -> Tuple[str, Path]:
    """
    Returns ("sqlite", db_path) if STATE_DB is set, else ("json", json_path).
    """
    db = os.getenv("STATE_DB", "").strip()
    if db:
        return "sqlite", Path(db)
    json_path = os.getenv("STATE_FILE", "seen_items.json")
    return "json", Path(json_path)


def _to_ord(iso: Optional[str]) -> int:
    """Turn an ISO-ish timestamp into a sortable integer; 0 on failure."""
    if not iso:
        return 0
    s = iso.replace("Z", "+00:00")
    try:
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        hh, mm, ss = int(s[11:13]), int(s[14:16]), int(s[17:19])
        return ((((y * 12 + m) * 31 + d) * 24 + hh) * 60 + mm) * 60 + ss
    except Exception:
        return 0
