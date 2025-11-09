from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, TypedDict

from fastapi import HTTPException, status
from starlette.requests import Request

from ..db.items import load_items_dict


class SessionUser(TypedDict, total=False):
    id: int
    email: str
    name: str
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
    value = os.getenv(name, default)
    if not value:
        return default
    if any(k in name for k in ("PASS", "TOKEN", "KEY", "SECRET")):
        return "••••••••"
    return value


def _require_user(request: Request) -> SessionUser:
    user = request.session.get("user")
    if not user or "id" not in user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return user


def _load_state_any() -> Dict[str, Dict[str, Any]]:
    """
    UI needs a dict-like shape of items. Prefer SQLite; fall back to JSON if present.
    """
    db = os.getenv("STATE_DB")
    if db:
        return load_items_dict(Path(db))
    f = Path(os.getenv("STATE_FILE", "seen_items.json"))
    return json.loads(f.read_text()) if f.exists() else {}


def _state_version() -> str:
    _backend, path = _state_sources()
    try:
        return str(int(path.stat().st_mtime))
    except Exception:
        return "0"


def _state_sources() -> Tuple[str, Path]:
    db = os.getenv("STATE_DB", "").strip()
    if db:
        return "sqlite", Path(db)
    json_path = os.getenv("STATE_FILE", "seen_items.json")
    return "json", Path(json_path)


def _to_ord(iso: Optional[str]) -> int:
    if not iso:
        return 0
    s = iso.replace("Z", "+00:00")
    try:
        y, m, d = int(s[0:4]), int(s[5:7]), int(s[8:10])
        hh, mm, ss = int(s[11:13]), int(s[14:16]), int(s[17:19])
        return ((((y * 12 + m) * 31 + d) * 24 + hh) * 60 + mm) * 60 + ss
    except Exception:
        return 0
