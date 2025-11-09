from pathlib import Path

from store_watcher.db.config import (
    Listener,
    add_listener,
    delete_listener,
    ensure_listener_schema,
    list_listeners,
    parse_kind_literal,
    set_listener_enabled,
)


def test_listeners_crud_scoped_to_user(tmp_path: Path) -> None:
    dbp = tmp_path / "state.db"
    ensure_listener_schema(dbp)

    user_a = 101
    user_b = 202

    # Add two listeners for A, one for B
    id1 = add_listener(
        dbp,
        Listener(
            id=None,
            region="US",
            kind=parse_kind_literal("discord"),
            enabled=True,
            name="A Discord",
            config={"webhook_url": "https://discord.example/webhook/abc"},
            user_id=user_a,
        ),
    )
    id2 = add_listener(
        dbp,
        Listener(
            id=None,
            region="ALL",
            kind=parse_kind_literal("email"),
            enabled=False,
            name="A Email",
            config={
                "smtp_host": "smtp.example",
                "smtp_port": 587,
                "smtp_user": "a@example.com",
                "smtp_pass": "secret",
                "from": "a@example.com",
                "to": "a@example.com",
            },
            user_id=user_a,
        ),
    )
    id3 = add_listener(
        dbp,
        Listener(
            id=None,
            region="EU",
            kind=parse_kind_literal("discord"),
            enabled=True,
            name="B Discord",
            config={"webhook_url": "https://discord.example/webhook/xyz"},
            user_id=user_b,
        ),
    )

    # A sees only their listeners
    la = list_listeners(dbp, user_id=user_a)
    ids_a = {l.id for l in la}
    assert ids_a == {id1, id2}

    # Region filter: "US" should include explicit US + ALL
    la_us = list_listeners(dbp, user_id=user_a, region="US")
    ids_us = {l.id for l in la_us}
    assert ids_us == {id1, id2}  # includes ALL

    # Region filter "ALL" explicitly still returns all user listeners
    la_all = list_listeners(dbp, user_id=user_a, region="ALL")
    assert {l.id for l in la_all} == {id1, id2}

    # B sees only their listener
    lb = list_listeners(dbp, user_id=user_b)
    assert {l.id for l in lb} == {id3}

    # Toggle (scoped)
    set_listener_enabled(dbp, id2, True, user_id=user_a)
    la2 = {l.id: l.enabled for l in list_listeners(dbp, user_id=user_a)}
    assert la2[id2] is True

    # Delete (scoped)
    delete_listener(dbp, id1, user_id=user_a)
    la3 = {l.id for l in list_listeners(dbp, user_id=user_a)}
    assert la3 == {id2}

    # Ensure B’s still intact
    assert {l.id for l in list_listeners(dbp, user_id=user_b)} == {id3}
