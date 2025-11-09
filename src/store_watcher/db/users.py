from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from . import connect


@dataclass(frozen=True)
class User:
    id: int
    provider: str  # "google"
    sub: str  # provider subject
    email: str
    name: str
    picture: Optional[str]


# ------------------ schema ------------------


def ensure_user_schema(db_path: Path) -> None:
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                provider TEXT NOT NULL,
                sub      TEXT NOT NULL,
                email    TEXT NOT NULL,
                name     TEXT NOT NULL,
                picture  TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cur.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_users_provider_sub ON users(provider, sub)"
        )
        cur.execute("CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)")
        conn.commit()


# ------------------ CRUD ------------------


def upsert_user_google(
    db_path: Path, *, sub: str, email: str, name: str, picture: Optional[str]
) -> User:
    ensure_user_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE users
               SET email = ?, name = ?, picture = ?, updated_at = CURRENT_TIMESTAMP
             WHERE provider = 'google' AND sub = ?
            """,
            (email, name, picture, sub),
        )
        if cur.rowcount == 0:
            cur.execute(
                """
                INSERT INTO users (provider, sub, email, name, picture)
                VALUES ('google', ?, ?, ?, ?)
                """,
                (sub, email, name, picture),
            )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE provider='google' AND sub=?", (sub,))
        row = cur.fetchone()
        assert row, "failed to upsert user"
        return User(
            id=int(row["id"]),
            provider=str(row["provider"]),
            sub=str(row["sub"]),
            email=str(row["email"]),
            name=str(row["name"]),
            picture=row["picture"] if row["picture"] is not None else None,
        )


def get_user_by_id(db_path: Path, user_id: int) -> Optional[User]:
    ensure_user_schema(db_path)
    with connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        return User(
            id=int(row["id"]),
            provider=str(row["provider"]),
            sub=str(row["sub"]),
            email=str(row["email"]),
            name=str(row["name"]),
            picture=row["picture"] if row["picture"] is not None else None,
        )
