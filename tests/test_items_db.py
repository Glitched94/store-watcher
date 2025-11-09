# tests/test_items_db.py
from pathlib import Path

from store_watcher.db.items import (
    ensure_item_schema,
    load_items,
    load_items_dict,
    save_items,
)


def _state_record(url: str, *, name: str | None = None, image: str | None = None) -> dict:
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
    return rec


def test_items_roundtrip_via_state_dict(tmp_path: Path):
    dbp = tmp_path / "state.db"
    ensure_item_schema(dbp)

    items_in = {
        # composite keys: "<host>:<code>"
        "disneystore.com:438039197642": _state_record(
            "https://www.disneystore.com/animal-pin-the-muppets-438039197642.html",
            name="Animal Pin – The Muppets",
            image="https://cdn.example.com/438039197642.jpg",
        ),
        "disneystore.com:438018657693": _state_record(
            "https://www.disneystore.com/xyz-438018657693.html"
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

    b = items_out["disneystore.com:438018657693"]
    assert b["status"] == 1
    # optional name presence is fine either way
    assert "name" not in b or isinstance(b["name"], str)
