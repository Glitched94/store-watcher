from pathlib import Path

from store_watcher.db.users import ensure_user_schema, get_user_by_id, upsert_user_google


def test_users_upsert_and_get(tmp_path: Path):
    dbp = tmp_path / "state.db"
    ensure_user_schema(dbp)

    u = upsert_user_google(
        dbp,
        sub="google-sub-123",
        email="jane@example.com",
        name="Jane Example",
        picture="https://example.com/pic.jpg",
    )
    assert u.id > 0
    assert u.email == "jane@example.com"

    # Update same sub with new data
    u2 = upsert_user_google(
        dbp,
        sub="google-sub-123",
        email="jane2@example.com",
        name="Jane Two",
        picture=None,
    )
    assert u2.id == u.id
    assert u2.email == "jane2@example.com"
    assert u2.picture is None

    # Fetch by id
    fetched = get_user_by_id(dbp, u.id)
    assert fetched is not None
    assert fetched.email == "jane2@example.com"
