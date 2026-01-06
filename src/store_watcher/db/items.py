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
    price: Optional[str]
    availability_message: Optional[str]
    available: Optional[bool]
    first_seen: Optional[str]
    status: int
    status_since: Optional[str]
    image: Optional[str]
    in_stock_allocation: Optional[int]


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
                price TEXT,
                availability_message TEXT,
                available INTEGER,
                first_seen TEXT,
                status INTEGER,
                status_since TEXT,
                image TEXT,
                in_stock_allocation INTEGER
            )
            """
        )
        cur.execute("PRAGMA table_info(items)")
        existing = {row["name"] for row in cur.fetchall()}
        migrations = [
            ("price", "ALTER TABLE items ADD COLUMN price TEXT"),
            ("availability_message", "ALTER TABLE items ADD COLUMN availability_message TEXT"),
            ("available", "ALTER TABLE items ADD COLUMN available INTEGER"),
            ("in_stock_allocation", "ALTER TABLE items ADD COLUMN in_stock_allocation INTEGER"),
        ]
        for col, sql in migrations:
            if col not in existing:
                cur.execute(sql)
        conn.commit()


# ------------------ queries ------------------


def load_items(db_path: Path) -> List[Item]:
    """Return all items as dataclass instances."""
    ensure_item_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                key,
                host,
                code,
                url,
                name,
                price,
                availability_message,
                available,
                first_seen,
                status,
                status_since,
                image,
                in_stock_allocation
            FROM items
            """
        )
        rows = cur.fetchall()

    return [
        Item(
            key=str(r["key"]),
            host=r["host"],
            code=r["code"],
            url=r["url"],
            name=r["name"],
            price=r["price"],
            availability_message=r["availability_message"],
            available=bool(r["available"]) if r["available"] is not None else None,
            first_seen=r["first_seen"],
            status=int(r["status"] or 0),
            status_since=r["status_since"],
            image=r["image"],
            in_stock_allocation=(
                int(r["in_stock_allocation"]) if r["in_stock_allocation"] is not None else None
            ),
        )
        for r in rows
    ]


def load_items_dict(db_path: Path) -> Dict[str, Dict[str, Any]]:
    """
    Return items as a dictionary keyed by item key:
      { key: { url, first_seen, status, status_since, [name], [host], [image], [price], [availability_message], [available] } }
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
        if it.price:
            record["price"] = it.price
        if it.availability_message:
            record["availability_message"] = it.availability_message
        if it.available is not None:
            record["available"] = bool(it.available)
        if it.in_stock_allocation is not None:
            record["in_stock_allocation"] = int(it.in_stock_allocation)
        result[it.key] = record
    return result


def save_items(items: Dict[str, Dict[str, Any]], db_path: Path) -> None:
    """
    Upsert a dictionary of items into the database.
    Structure:
      { key: { url, first_seen, status, status_since, ... } }
    """
    ensure_item_schema(db_path)

    def _row(key: str, rec: Dict[str, Any]) -> tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        Optional[int],
        str,
        int,
        str,
        str,
        Optional[int],
    ]:
        availability_message = rec.get("availability_message") or rec.get("availability") or ""
        avail_raw = rec.get("available")
        if avail_raw is None:
            available: Optional[int] = None
        elif isinstance(avail_raw, bool):
            available = int(avail_raw)
        else:
            try:
                available = int(avail_raw)
            except Exception:
                available = None

        stock_raw = rec.get("in_stock_allocation")
        stock: Optional[int]
        if stock_raw is None:
            stock = None
        else:
            try:
                stock = int(stock_raw)
            except Exception:
                stock = None

        return (
            key,
            str(rec.get("host") or ""),
            key.split(":", 1)[-1] if ":" in key else str(rec.get("code") or key),
            str(rec.get("url") or ""),
            str(rec.get("name") or ""),
            str(rec.get("price") or ""),
            str(availability_message),
            available,
            str(rec.get("first_seen") or ""),
            int(rec.get("status", 0)),
            str(rec.get("status_since") or rec.get("first_seen") or ""),
            str(rec.get("image") or ""),
            stock,
        )

    rows: Iterable[
        tuple[str, str, str, str, str, str, str, Optional[int], str, int, str, str, Optional[int]]
    ] = (_row(key, rec) for key, rec in items.items())

    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO items (key, host, code, url, name, price, availability_message, available, first_seen, status, status_since, image, in_stock_allocation)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                host=excluded.host,
                code=excluded.code,
                url=excluded.url,
                name=excluded.name,
                price=excluded.price,
                availability_message=excluded.availability_message,
                available=excluded.available,
                first_seen=excluded.first_seen,
                status=excluded.status,
                status_since=excluded.status_since,
                image=excluded.image,
                in_stock_allocation=excluded.in_stock_allocation
            """,
            list(rows),
        )
        conn.commit()
