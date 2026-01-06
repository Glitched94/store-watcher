# tests/test_items_db.py
from pathlib import Path

from store_watcher.db.items import (
    ensure_item_schema,
    load_items,
    load_items_dict,
    save_items,
)


def _state_record(
    url: str,
    *,
    name: str | None = None,
    image: str | None = None,
    price: str | None = None,
    availability_message: str | None = None,
    available: bool | None = None,
    in_stock_allocation: int | None = None,
) -> dict:
    rec = {
        "url": url,
        "first_seen": "2025-01-01T00:00:00Z",
        "status": 1,
        "status_since": "2025-01-01T00:00:00Z",
    }
    if name:
        rec["name"] = name
    if image:
        rec["image"] = image
    if price:
        rec["price"] = price
    if availability_message:
        rec["availability_message"] = availability_message
    if available is not None:
        rec["available"] = available
    if in_stock_allocation is not None:
        rec["in_stock_allocation"] = in_stock_allocation
    return rec


def test_items_roundtrip_via_state_dict(tmp_path: Path) -> None:
    dbp = tmp_path / "state.db"
    ensure_item_schema(dbp)

    items_in = {
        # composite keys: "<host>:<code>"
        "disneystore.com:438039197642": _state_record(
            "https://www.disneystore.com/animal-pin-the-muppets-438039197642.html",
            name="Animal Pin – The Muppets",
            image="https://cdn.example.com/438039197642.jpg",
            price="$9.99",
            availability_message="Low Stock",
            available=True,
            in_stock_allocation=12,
        ),
        "disneystore.com:438018657693": _state_record(
            "https://www.disneystore.com/xyz-438018657693.html",
            available=False,
        ),
    }

    # upsert
    save_items(items_in, dbp)

    # raw dataclass list
    items = load_items(dbp)
    assert len(items) == 2

    # UI-shaped dict
    items_out = load_items_dict(dbp)

    # shape preserved
    assert set(items_out.keys()) == set(items_in.keys())

    a = items_out["disneystore.com:438039197642"]
    assert a["url"].startswith("https://www.disneystore.com/")
    assert a["name"] == "Animal Pin – The Muppets"
    assert a["status"] == 1
    assert a["image"].endswith("438039197642.jpg")
    assert a["price"] == "$9.99"
    assert a["availability_message"] == "Low Stock"
    assert a["available"] is True
    assert a["in_stock_allocation"] == 12

    b = items_out["disneystore.com:438018657693"]
    assert b["status"] == 1
    assert b["available"] is False
    # optional name presence is fine either way
    assert "name" not in b or isinstance(b["name"], str)
