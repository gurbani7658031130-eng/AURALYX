"""SQLite-backed global approval store."""

import asyncio
import json
import os
import sqlite3
import time
from typing import Optional

_DB_PATH = os.path.join(os.path.dirname(__file__), "approved_users.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_sync():
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS approved_users (
                user_id INTEGER PRIMARY KEY,
                approved_at INTEGER NOT NULL,
                approved_by INTEGER NOT NULL,
                permissions TEXT NOT NULL DEFAULT '[]',
                reason TEXT,
                expiry_time INTEGER
            )
            """
        )
        # Forward-compatible migration for old schema without `permissions`.
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(approved_users)").fetchall()}
        if "permissions" not in columns:
            conn.execute("ALTER TABLE approved_users ADD COLUMN permissions TEXT NOT NULL DEFAULT '[]'")
        conn.commit()


async def init_db():
    await asyncio.to_thread(_init_sync)


def _is_user_approved_sync(user_id: int) -> bool:
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT user_id
            FROM approved_users
            WHERE user_id = ?
              AND (expiry_time IS NULL OR expiry_time > ?)
            """,
            (int(user_id), now),
        ).fetchone()
        return row is not None


async def is_user_approved(user_id: int) -> bool:
    return await asyncio.to_thread(_is_user_approved_sync, int(user_id))


def _approve_user_sync(
    user_id: int,
    approved_by: int,
    permissions: list[str],
    reason: str = "",
    expiry_time: Optional[int] = None,
) -> bool:
    now = int(time.time())
    with _connect() as conn:
        # Clean expired approval for this user so re-approval can proceed.
        conn.execute(
            "DELETE FROM approved_users WHERE user_id = ? AND expiry_time IS NOT NULL AND expiry_time <= ?",
            (int(user_id), now),
        )
        exists = conn.execute("SELECT 1 FROM approved_users WHERE user_id = ?", (int(user_id),)).fetchone()
        if exists:
            return False

        conn.execute(
            """
            INSERT INTO approved_users (user_id, approved_at, approved_by, permissions, reason, expiry_time)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                int(user_id),
                now,
                int(approved_by),
                json.dumps(sorted(set(permissions or []))),
                (reason or "")[:250],
                expiry_time,
            ),
        )
        conn.commit()
        return True


async def approve_user(
    user_id: int,
    approved_by: int,
    permissions: list[str],
    reason: str = "",
    expiry_time: Optional[int] = None,
) -> bool:
    return await asyncio.to_thread(
        _approve_user_sync,
        int(user_id),
        int(approved_by),
        list(permissions or []),
        reason,
        expiry_time,
    )


def _disapprove_user_sync(user_id: int) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM approved_users WHERE user_id = ?", (int(user_id),))
        conn.commit()
        return cur.rowcount > 0


async def disapprove_user(user_id: int) -> bool:
    return await asyncio.to_thread(_disapprove_user_sync, int(user_id))


def _list_approved_users_sync(limit: int = 500) -> list[dict]:
    now = int(time.time())
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT user_id, approved_at, approved_by, permissions, reason, expiry_time
            FROM approved_users
            WHERE (expiry_time IS NULL OR expiry_time > ?)
            ORDER BY approved_at ASC
            LIMIT ?
            """,
            (now, int(limit)),
        ).fetchall()
        out = []
        for row in rows:
            d = dict(row)
            raw = d.get("permissions", "[]")
            try:
                d["permissions"] = json.loads(raw) if raw else []
            except Exception:
                d["permissions"] = []
            out.append(d)
        return out


async def list_approved_users(limit: int = 500) -> list[dict]:
    return await asyncio.to_thread(_list_approved_users_sync, int(limit))


def _get_user_permissions_sync(user_id: int) -> list[str]:
    now = int(time.time())
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT permissions
            FROM approved_users
            WHERE user_id = ?
              AND (expiry_time IS NULL OR expiry_time > ?)
            """,
            (int(user_id), now),
        ).fetchone()
        if not row:
            return []
        raw = row["permissions"] or "[]"
        try:
            parsed = json.loads(raw)
            return [str(x) for x in parsed if isinstance(x, str)]
        except Exception:
            return []


async def get_user_permissions(user_id: int) -> list[str]:
    return await asyncio.to_thread(_get_user_permissions_sync, int(user_id))


def _set_user_permissions_sync(user_id: int, permissions: list[str]) -> bool:
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE approved_users SET permissions = ? WHERE user_id = ?",
            (json.dumps(sorted(set(permissions or []))), int(user_id)),
        )
        conn.commit()
        return cur.rowcount > 0


async def set_user_permissions(user_id: int, permissions: list[str]) -> bool:
    return await asyncio.to_thread(_set_user_permissions_sync, int(user_id), list(permissions or []))
