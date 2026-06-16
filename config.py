"""
config.py
=========
Central configuration: player list, environment-driven settings, app-wide defaults.
"""

import os

# ── Players ────────────────────────────────────────────────────────────────
PLAYERS: list[str] = ["Bobo", "Phil", "Steven", "Jaina"]

# ── Security ───────────────────────────────────────────────────────────────
INPUT_PIN: str = os.environ.get("INPUT_PIN", "")
if not INPUT_PIN:
    raise RuntimeError("Environment variable INPUT_PIN is not set.")

# ── Data ───────────────────────────────────────────────────────────────────
LOCAL_DATA_FILE: str = "local_data.jsonl"

# ── Server / Render ────────────────────────────────────────────────────────
STATIC_CACHE_TTL: int = 86400  # seconds (1 day) for static assets
SELF_PING_INTERVAL: int = 9 * 60  # seconds – keeps Render Free Tier awake
POLL_UPDATE_SECONDS: int = int(os.environ.get("POLL_UPDATE_SECONDS", "5"))
ONLINE_ACTIVE_WINDOW: int = int(os.environ.get("ONLINE_ACTIVE_WINDOW_SECONDS", "20"))

# ── Firebase fallback season ──────────────────────────────────────────────
DEFAULT_SEASON: str = "Season 21"
