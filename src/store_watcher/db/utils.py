from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, cast

JsonDict = Dict[str, Any]


# ------------------ Core helpers ------------------


def _ensure_dir(path: Path) -> None:
    """Create the parent directory for a path if it doesn't exist."""
    path.parent.mkdir(parents=True, exist_ok=True)


def connect(db_path: Path) -> sqlite3.Connection:
    """
    Open a SQLite connection with sane defaults (WAL mode, NORMAL sync).
    Always ensures the directory exists.
    """
    _ensure_dir(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
    except sqlite3.OperationalError:
        pass
    return conn


def _to_int(value: Any, default: int = 0) -> int:
    """Safely coerce to int; returns default on failure."""
    if value is None:
        return default
    if isinstance(value, int):
        return value
    try:
        return int(cast(Any, value))
    except Exception:
        return default


def fetch_all_dicts(cur: sqlite3.Cursor) -> List[JsonDict]:
    """Convert a cursor result to list[dict] (when row_factory isn't Row)."""
    columns = [col[0] for col in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]
