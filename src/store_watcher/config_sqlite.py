from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, List, Literal, Optional, cast

ListenerKind = Literal["discord", "email"]


class Listener:
    def __init__(
        self,
        id: Optional[int],
        region: str,
        kind: ListenerKind,
        enabled: bool,
        name: str,
        config: dict[str, Any],
    ):
        self.id = id
        self.region = region
        self.kind = kind
        self.enabled = enabled
        self.name = name
        self.config = config

    def __repr__(self) -> str:
        return f"Listener(id={self.id}, region={self.region}, kind={self.kind}, enabled={self.enabled})"


def _to_int(val: Any, default: int = 0) -> int:
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def ensure_listener_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS listeners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT NOT NULL,
                kind TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                name TEXT,
                config_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def list_listeners(db_path: Path, region: Optional[str] = None) -> List[Listener]:
    ensure_listener_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        if region and region.upper() != "ALL":
            cur.execute(
                "SELECT id, region, kind, enabled, name, config_json "
                "FROM listeners WHERE region IN (?, 'ALL')",
                (region.upper(),),
            )
        else:
            cur.execute("SELECT id, region, kind, enabled, name, config_json FROM listeners")
        rows = cur.fetchall()

    listeners: List[Listener] = []
    for rid, reg, kind, enabled, name, cfg_json in rows:
        # Parse config safely
        try:
            cfg = json.loads(cfg_json) if cfg_json else {}
        except Exception:
            cfg = {}

        # Normalize kind to one of the two allowed values, then cast for mypy
        k_raw = (str(kind or "")).strip().lower()
        k_norm = "email" if k_raw == "email" else "discord"
        k_lit = cast(Literal["discord", "email"], k_norm)

        listeners.append(
            Listener(
                id=_to_int(rid),
                region=str(reg or "").upper(),
                kind=k_lit,  # now a Literal
                enabled=bool(_to_int(enabled, 1)),
                name=str(name or ""),
                config=cfg,
            )
        )
    return listeners


def add_listener(db_path: Path, listener: Listener) -> None:
    ensure_listener_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO listeners (region, kind, enabled, name, config_json) VALUES (?, ?, ?, ?, ?)",
            (
                listener.region,
                listener.kind,
                1 if listener.enabled else 0,
                listener.name,
                json.dumps(listener.config),
            ),
        )
        conn.commit()


def set_listener_enabled(db_path: Path, listener_id: int, enabled: bool) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE listeners SET enabled = ? WHERE id = ?",
            (1 if enabled else 0, listener_id),
        )
        conn.commit()


def delete_listener(db_path: Path, listener_id: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM listeners WHERE id = ?", (listener_id,))
        conn.commit()
