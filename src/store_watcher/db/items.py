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
    prev_price: Optional[str]
    availability_message: Optional[str]
    prev_availability_message: Optional[str]
    available: Optional[bool]
    prev_available: Optional[bool]
    price_changed: Optional[bool]
    availability_changed: Optional[bool]
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
                prev_price TEXT,
                availability_message TEXT,
                prev_availability_message TEXT,
                available INTEGER,
                prev_available INTEGER,
                price_changed INTEGER,
                availability_changed INTEGER,
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
            ("prev_price", "ALTER TABLE items ADD COLUMN prev_price TEXT"),
            ("availability_message", "ALTER TABLE items ADD COLUMN availability_message TEXT"),
            (
                "prev_availability_message",
                "ALTER TABLE items ADD COLUMN prev_availability_message TEXT",
            ),
            ("available", "ALTER TABLE items ADD COLUMN available INTEGER"),
            ("prev_available", "ALTER TABLE items ADD COLUMN prev_available INTEGER"),
            ("price_changed", "ALTER TABLE items ADD COLUMN price_changed INTEGER"),
            ("availability_changed", "ALTER TABLE items ADD COLUMN availability_changed INTEGER"),
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
                prev_price,
                availability_message,
                prev_availability_message,
                available,
                prev_available,
                price_changed,
                availability_changed,
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
            prev_price=r["prev_price"],
            availability_message=r["availability_message"],
            prev_availability_message=r["prev_availability_message"],
            available=bool(r["available"]) if r["available"] is not None else None,
            prev_available=bool(r["prev_available"]) if r["prev_available"] is not None else None,
            price_changed=(bool(r["price_changed"]) if r["price_changed"] is not None else None),
            availability_changed=(
                bool(r["availability_changed"]) if r["availability_changed"] is not None else None
            ),
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
        if it.prev_price:
            record["prev_price"] = it.prev_price
        if it.availability_message:
            record["availability_message"] = it.availability_message
        if it.prev_availability_message:
            record["prev_availability_message"] = it.prev_availability_message
        if it.available is not None:
            record["available"] = bool(it.available)
        if it.prev_available is not None:
            record["prev_available"] = bool(it.prev_available)
        if it.price_changed is not None:
            record["price_changed"] = bool(it.price_changed)
        if it.availability_changed is not None:
            record["availability_changed"] = bool(it.availability_changed)
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

    def _row(
        key: str, rec: Dict[str, Any]
    ) -> tuple[
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        str,
        Optional[int],
        Optional[int],
        Optional[int],
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

        prev_available_raw = rec.get("prev_available")
        if prev_available_raw is None:
            prev_available: Optional[int] = None
        elif isinstance(prev_available_raw, bool):
            prev_available = int(prev_available_raw)
        else:
            try:
                prev_available = int(prev_available_raw)
            except Exception:
                prev_available = None

        price_changed_raw = rec.get("price_changed")
        if price_changed_raw is None:
            price_changed: Optional[int] = None
        elif isinstance(price_changed_raw, bool):
            price_changed = int(price_changed_raw)
        else:
            try:
                price_changed = int(price_changed_raw)
            except Exception:
                price_changed = None

        availability_changed_raw = rec.get("availability_changed")
        if availability_changed_raw is None:
            availability_changed: Optional[int] = None
        elif isinstance(availability_changed_raw, bool):
            availability_changed = int(availability_changed_raw)
        else:
            try:
                availability_changed = int(availability_changed_raw)
            except Exception:
                availability_changed = None

        return (
            key,
            str(rec.get("host") or ""),
            key.split(":", 1)[-1] if ":" in key else str(rec.get("code") or key),
            str(rec.get("url") or ""),
            str(rec.get("name") or ""),
            str(rec.get("price") or ""),
            str(rec.get("prev_price") or ""),
            str(availability_message),
            str(rec.get("prev_availability_message") or ""),
            available,
            prev_available,
            price_changed,
            availability_changed,
            str(rec.get("first_seen") or ""),
            int(rec.get("status", 0)),
            str(rec.get("status_since") or rec.get("first_seen") or ""),
            str(rec.get("image") or ""),
            stock,
        )

    rows: Iterable[
        tuple[
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            str,
            Optional[int],
            Optional[int],
            Optional[int],
            Optional[int],
            str,
            int,
            str,
            str,
            Optional[int],
        ]
    ] = (_row(key, rec) for key, rec in items.items())

    with connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO items (
                key,
                host,
                code,
                url,
                name,
                price,
                prev_price,
                availability_message,
                prev_availability_message,
                available,
                prev_available,
                price_changed,
                availability_changed,
                first_seen,
                status,
                status_since,
                image,
                in_stock_allocation
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                host=excluded.host,
                code=excluded.code,
                url=excluded.url,
                name=excluded.name,
                price=excluded.price,
                prev_price=excluded.prev_price,
                availability_message=excluded.availability_message,
                prev_availability_message=excluded.prev_availability_message,
                available=excluded.available,
                prev_available=excluded.prev_available,
                price_changed=excluded.price_changed,
                availability_changed=excluded.availability_changed,
                first_seen=excluded.first_seen,
                status=excluded.status,
                status_since=excluded.status_since,
                image=excluded.image,
                in_stock_allocation=excluded.in_stock_allocation
            """,
            list(rows),
        )
        conn.commit()
