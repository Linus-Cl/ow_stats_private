"""Active sessions tracking (SQLite-backed heartbeat)."""
from __future__ import annotations
import os
import sqlite3
import time

ACTIVE_DB = os.path.join(os.path.dirname(__file__), "active_sessions.db")


def init_active_db() -> None:
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                last_seen INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_heartbeat(session_id: str) -> None:
    if not session_id:
        return
    now = int(time.time())
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO active_sessions(session_id,last_seen) VALUES(?,?) ON CONFLICT(session_id) DO UPDATE SET last_seen=excluded.last_seen",
            (session_id, now),
        )
        try:
            active_window = int(os.getenv("ONLINE_ACTIVE_WINDOW_SECONDS", "20"))
        except Exception:
            active_window = 20
        cur.execute(
            "DELETE FROM active_sessions WHERE last_seen < ?",
            (now - 2 * active_window,),
        )
        conn.commit()
    finally:
        conn.close()


def count_active(within_seconds: int | None = None) -> int:
    if within_seconds is None:
        try:
            within_seconds = int(os.getenv("ONLINE_ACTIVE_WINDOW_SECONDS", "20"))
        except Exception:
            within_seconds = 20
    now = int(time.time())
    threshold = now - within_seconds
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM active_sessions WHERE last_seen >= ?", (threshold,)
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0
    finally:
        conn.close()


def set_app_state(key: str, value: str) -> None:
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def get_app_state(key: str) -> str | None:
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_state WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()
