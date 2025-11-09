from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from . import connect

# ------------------ model ------------------


@dataclass
class Item:
    key: str
    host: Optional[str]
    code: Optional[str]
    url: Optional[str]
    name: Optional[str]
    first_seen: Optional[str]
    status: int
    status_since: Optional[str]
    image: Optional[str]


# ------------------ schema ------------------


def ensure_item_schema(db_path: Path) -> None:
    """Create the items table if it doesn't already exist."""
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
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
            )
            """
        )
        conn.commit()


# ------------------ queries ------------------


def load_items(db_path: Path) -> List[Item]:
    """Return all items as dataclass instances."""
    ensure_item_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT key, host, code, url, name, first_seen, status, status_since, image FROM items"
        )
        rows = cur.fetchall()

    return [
        Item(
            key=str(r["key"]),
            host=r["host"],
            code=r["code"],
            url=r["url"],
            name=r["name"],
            first_seen=r["first_seen"],
            status=int(r["status"] or 0),
            status_since=r["status_since"],
            image=r["image"],
        )
        for r in rows
    ]


def load_items_dict(db_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Return items as a dictionary keyed by item key:
      { key: { url, first_seen, status, status_since, [name], [host], [image] } }
    """
    result: Dict[str, Dict[str, Any]] = {}
    for it in load_items(db_path):
        record: Dict[str, Any] = {
            "url": it.url or "",
            "first_seen": it.first_seen or "",
            "status": int(it.status or 0),
            "status_since": it.status_since or "",
        }
        if it.name:
            record["name"] = it.name
        if it.host:
            record["host"] = it.host
        if it.image:
            record["image"] = it.image
        result[it.key] = record
    return result


def save_items(items: Dict[str, Dict[str, Any]], db_path: Path) -> None:
    """
    Upsert a dictionary of items into the database.
    Structure:
      { key: { url, first_seen, status, status_since, ... } }
    """
    ensure_item_schema(db_path)

    def _row(key: str, rec: Dict[str, Any]) -> tuple[str, str, str, str, str, str, int, str, str]:
        return (
            key,
            str(rec.get("host") or ""),
            key.split(":", 1)[-1] if ":" in key else str(rec.get("code") or key),
            str(rec.get("url") or ""),
            str(rec.get("name") or ""),
            str(rec.get("first_seen") or ""),
            int(rec.get("status", 0)),
            str(rec.get("status_since") or rec.get("first_seen") or ""),
            str(rec.get("image") or ""),
        )

    rows: Iterable[tuple[str, str, str, str, str, str, int, str, str]] = (
        _row(key, rec) for key, rec in items.items()
    )

    with connect(db_path) as conn:
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
