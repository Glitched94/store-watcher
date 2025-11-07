import json
from pathlib import Path

from store_watcher.state import load_state, make_present_record, save_state
from store_watcher.utils import utcnow_iso


def test_migrate_from_legacy_list(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            [
                "https://disneystore.com/foo-438039197642.html",
                "https://disneystore.com/bar-438018657693.html?x=y",
            ]
        )
    )
    state = load_state(p)
    assert set(state.keys()) == {"438039197642", "438018657693"}
    assert state["438039197642"]["status"] == 1


def test_migrate_from_legacy_dict_last_seen(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "https://disneystore.com/foo-438039197642.html": {
                    "first_seen": "2025-01-01T00:00:00Z",
                    "last_seen": "2025-01-02T00:00:00Z",
                },
                "438018657693": {
                    "url": "https://disneystore.com/x-438018657693.html",
                    "first_seen": "2025-01-03T00:00:00Z",
                },
            }
        )
    )
    state = load_state(p)
    assert set(state.keys()) == {"438039197642", "438018657693"}
    assert state["438039197642"]["status"] == 1
    assert "status_since" in state["438039197642"]


def test_save_and_reload_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    now = utcnow_iso()
    s = {
        "438039197642": make_present_record(
            "https://disneystore.com/438039197642.html", now, name="Muppets Pin"
        )
    }
    save_state(s, p)
    loaded = load_state(p)
    assert loaded["438039197642"]["url"].endswith("/438039197642.html")
    assert loaded["438039197642"]["name"] == "Muppets Pin"
