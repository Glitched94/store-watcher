from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Literal, Optional, cast

from . import JsonDict, _to_int, connect

KindLiteral = Literal["discord", "email"]


@dataclass
class Listener:
    id: Optional[int]
    region: str
    kind: KindLiteral
    enabled: bool
    name: str
    config: JsonDict
    user_id: int  # required owner


# ------------------ helpers ------------------


def parse_kind_literal(s: str) -> KindLiteral:
    s_norm = (s or "").strip().lower()
    if s_norm not in ("discord", "email"):
        s_norm = "discord"
    return cast(KindLiteral, s_norm)


# ------------------ schema ------------------


def ensure_listener_schema(db_path: Path) -> None:
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS listeners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                region TEXT NOT NULL,
                kind TEXT NOT NULL,              -- 'discord' | 'email'
                enabled INTEGER NOT NULL DEFAULT 1,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_listeners_user   ON listeners(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_listeners_region ON listeners(region)")
        cur.execute("CREATE INDEX IF NOT EXISTS ix_listeners_kind   ON listeners(kind)")
        conn.commit()


# ------------------ CRUD ------------------


def add_listener(db_path: Path, listener: Listener) -> int:
    ensure_listener_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO listeners (region, kind, enabled, name, config_json, user_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                listener.region.upper(),
                listener.kind,
                1 if listener.enabled else 0,
                listener.name,
                json.dumps(listener.config, ensure_ascii=False),
                listener.user_id,
            ),
        )
        new_id = _to_int(cur.lastrowid, 0)
        conn.commit()
        return new_id


def list_listeners(
    db_path: Path,
    *,
    user_id: Optional[int] = None,
    region: Optional[str] = None,
) -> List[Listener]:
    ensure_listener_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()

        clauses: List[str] = []
        params: List[Any] = []

        if user_id is not None:
            clauses.append("user_id = ?")
            params.append(user_id)

        if region and region.upper() != "ALL":
            clauses.append("region IN (?, 'ALL')")
            params.append(region.upper())

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"""
            SELECT id, region, kind, enabled, name, config_json, user_id
            FROM listeners
            {where_sql}
            ORDER BY id DESC
        """
        cur.execute(sql, params)
        rows = cur.fetchall()

    out: List[Listener] = []
    for row in rows:
        cfg_json = row["config_json"]
        try:
            cfg = json.loads(cfg_json) if isinstance(cfg_json, str) else {}
        except Exception:
            cfg = {}

        out.append(
            Listener(
                id=_to_int(row["id"], 0),
                region=str(row["region"] or "").upper(),
                kind=parse_kind_literal(str(row["kind"] or "discord")),
                enabled=bool(_to_int(row["enabled"], 1)),
                name=str(row["name"] or ""),
                config=cfg,
                user_id=_to_int(row["user_id"], 0),
            )
        )
    return out


def set_listener_enabled(
    db_path: Path,
    listener_id: int,
    enabled: bool,
    *,
    user_id: Optional[int] = None,
) -> None:
    ensure_listener_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute(
                "UPDATE listeners SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (1 if enabled else 0, listener_id),
            )
        else:
            cur.execute(
                """
                UPDATE listeners
                   SET enabled=?, updated_at=CURRENT_TIMESTAMP
                 WHERE id=? AND user_id=?
                """,
                (1 if enabled else 0, listener_id, user_id),
            )
        conn.commit()


def delete_listener(
    db_path: Path,
    listener_id: int,
    *,
    user_id: Optional[int] = None,
) -> None:
    ensure_listener_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        if user_id is None:
            cur.execute("DELETE FROM listeners WHERE id=?", (listener_id,))
        else:
            cur.execute("DELETE FROM listeners WHERE id=? AND user_id=?", (listener_id, user_id))
        conn.commit()
