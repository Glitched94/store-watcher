from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

# Schema:
# items(key TEXT PRIMARY KEY, host TEXT, code TEXT, url TEXT, name TEXT,
#       first_seen TEXT, status INTEGER, status_since TEXT, image TEXT)


def _connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
    CREATE TABLE IF NOT EXISTS items (
      key TEXT PRIMARY KEY,
      host TEXT,
      code TEXT,
      url TEXT,
      name TEXT,
      first_seen TEXT,
      status INTEGER,
      status_since TEXT,
      image TEXT
    );
    """
    )
    # add image column if missing (older DBs)
    try:
        conn.execute("ALTER TABLE items ADD COLUMN image TEXT;")
    except sqlite3.OperationalError:
        pass
    conn.commit()


def load_state(db_path: Path) -> dict[str, dict[str, Any]]:
    conn = _connect(db_path)
    _ensure_schema(conn)
    cur = conn.execute(
        "SELECT key, host, code, url, name, first_seen, status, status_since, image FROM items"
    )
    out: dict[str, dict[str, Any]] = {}
    for key, host, _code, url, name, first_seen, status, status_since, image in cur:
        rec: dict[str, Any] = {
            "url": url or "",
            "first_seen": first_seen or "",
            "status": int(status or 0),
            "status_since": status_since or "",
        }
        if name:
            rec["name"] = name
        if host:
            rec["host"] = host
        if image:
            rec["image"] = image
        out[key] = rec
    conn.close()
    return out


def save_state(state: dict[str, dict[str, Any]], db_path: Path) -> None:
    conn = _connect(db_path)
    _ensure_schema(conn)
    rows: Iterable[tuple[str, str, str, str, str, str, int, str, str]] = (
        (
            key,
            rec.get("host") or "",
            key.split(":", 1)[-1] if ":" in key else (rec.get("code") or key),
            rec.get("url") or "",
            rec.get("name") or "",
            rec.get("first_seen") or "",
            int(rec.get("status", 0)),
            rec.get("status_since") or rec.get("first_seen") or "",
            rec.get("image") or "",
        )
        for key, rec in state.items()
    )
    conn.executemany(
        """
      INSERT INTO items (key, host, code, url, name, first_seen, status, status_since, image)
      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(key) DO UPDATE SET
        host=excluded.host,
        code=excluded.code,
        url=excluded.url,
        name=excluded.name,
        first_seen=excluded.first_seen,
        status=excluded.status,
        status_since=excluded.status_since,
        image=excluded.image
    """,
        list(rows),
    )
    conn.commit()
    conn.close()
