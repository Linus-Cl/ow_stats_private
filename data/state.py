"""
data/state.py
=============
Cross-worker state via SQLite: active sessions (live viewer counter)
and key/value app state (data_token for update broadcast).
"""

from __future__ import annotations

import os
import sqlite3
import threading
import time

import config

# ── Database path ──────────────────────────────────────────────────────────
ACTIVE_DB: str = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "active_sessions.db"
)

# Thread-local connection pool — avoids opening a new connection per call.
_local = threading.local()


def _connect() -> sqlite3.Connection:
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(ACTIVE_DB, check_same_thread=False)
        _local.conn = conn
    return conn


# ── Schema init (called once at import) ────────────────────────────────────


def init_db() -> None:
    conn = _connect()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                last_seen  INTEGER
            )
        """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key   TEXT PRIMARY KEY,
                value TEXT
            )
        """
        )
        conn.commit()
    finally:
        conn.close()


# ── Heartbeat / online counter ─────────────────────────────────────────────


def upsert_heartbeat(session_id: str) -> None:
    if not session_id:
        return
    now = int(time.time())
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO active_sessions(session_id, last_seen) VALUES(?, ?) "
        "ON CONFLICT(session_id) DO UPDATE SET last_seen = excluded.last_seen",
        (session_id, now),
    )
    # Opportunistic cleanup
    window = config.ONLINE_ACTIVE_WINDOW
    cur.execute(
        "DELETE FROM active_sessions WHERE last_seen < ?",
        (now - 2 * window,),
    )
    conn.commit()


def delete_session(session_id: str) -> None:
    """Remove a specific session (called on page close via /bye)."""
    if not session_id:
        return
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM active_sessions WHERE session_id = ?", (session_id,))
    conn.commit()


def count_active(within_seconds: int | None = None) -> int:
    if within_seconds is None:
        within_seconds = config.ONLINE_ACTIVE_WINDOW
    now = int(time.time())
    threshold = now - within_seconds
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM active_sessions WHERE last_seen >= ?",
        (threshold,),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


# ── Generic key/value state ────────────────────────────────────────────────


def set_app_state(key: str, value: str) -> None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO app_state(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def get_app_state(key: str) -> str | None:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT value FROM app_state WHERE key = ?", (key,))
    row = cur.fetchone()
    return row[0] if row else None


# ── Auto-init on import ───────────────────────────────────────────────────
init_db()
