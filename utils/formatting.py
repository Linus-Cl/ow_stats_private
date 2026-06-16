"""
utils/formatting.py
====================
Shared formatting helpers: time-of-day extraction, duration parsing,
and season display formatting.  These are used in both the daily report
and the match-history views, so they live in one place.
"""

from __future__ import annotations

import re
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Time-of-day extraction  (row-level helper)
# ---------------------------------------------------------------------------

_TIME_COLUMNS = ("Uhrzeit", "Zeit", "Time", "Startzeit", "Start")


def parse_time(row: Any) -> str:
    """Extract an ``HH:MM`` time-of-day string from a DataFrame row.

    Strategy:
    1. If ``Datum`` is a ``Timestamp`` with a non-midnight time component, use that.
    2. Otherwise try dedicated time columns (Uhrzeit, Zeit, Time, …).
    3. Handles Excel numeric fractions, ``HH:MM`` strings, 3-/4-digit compact forms,
       and full datetime fallback via ``pd.to_datetime``.

    Returns ``""`` when no time can be determined.
    """
    # 1. Timestamp with embedded time
    try:
        dt = row.get("Datum")
        if (
            isinstance(dt, pd.Timestamp)
            and pd.notna(dt)
            and (dt.hour or dt.minute or dt.second)
        ):
            return dt.strftime("%H:%M")
    except Exception:
        pass

    # 2. Dedicated columns
    for col in _TIME_COLUMNS:
        val = (
            row.get(col)
            if col in (row.index if hasattr(row, "index") else row)
            else None
        )
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue

        # Excel numeric time (fraction of day)
        if isinstance(val, (int, float)):
            try:
                frac = float(val) % 1.0
                secs = int(round(frac * 86400))
                h, m = secs // 3600, (secs % 3600) // 60
                if 0 <= h < 24 and 0 <= m < 60:
                    return f"{h:02d}:{m:02d}"
            except Exception:
                pass

        s = str(val).strip().replace(",", ":")
        # HH:MM
        match = re.match(r"^(\d{1,2}):(\d{2})", s)
        if match:
            hh, mm = int(match.group(1)), int(match.group(2))
            if 0 <= hh < 24 and 0 <= mm < 60:
                return f"{hh:02d}:{mm:02d}"
        # Compact 3-/4-digit (e.g. 930 → 09:30)
        if re.fullmatch(r"\d{3,4}", s):
            s2 = s.zfill(4)
            hh, mm = int(s2[:2]), int(s2[2:])
            if 0 <= hh < 24 and 0 <= mm < 60:
                return f"{hh:02d}:{mm:02d}"
        # Full datetime string fallback
        try:
            dtp = pd.to_datetime(s, errors="raise")
            if pd.notna(dtp):
                return pd.Timestamp(dtp).strftime("%H:%M")
        except Exception:
            pass

    return ""


def compose_datetime(row: Any) -> pd.Timestamp | None:
    """Combine ``Datum`` date and best-effort time into a single ``Timestamp``.

    Used for ordering matches within a day.
    """
    base = row.get("Datum")
    if isinstance(base, pd.Timestamp) and pd.notna(base):
        if base.hour or base.minute or base.second:
            return base
        tstr = parse_time(row)
        if tstr:
            try:
                h, m = tstr.split(":")
                return pd.Timestamp(
                    year=base.year,
                    month=base.month,
                    day=base.day,
                    hour=int(h),
                    minute=int(m),
                )
            except Exception:
                return base
        return base
    return None


# ---------------------------------------------------------------------------
# Duration parsing  (row-level helper)
# ---------------------------------------------------------------------------

_DURATION_COLUMNS = (
    "Matchtime",
    "Dauer",
    "Duration",
    "Matchdauer",
    "Match Duration",
    "Spielzeit",
    "Length",
    "Zeitdauer",
)


def parse_duration(row: Any) -> str:
    """Extract a ``M:SS`` duration string from a DataFrame row.

    Checks dedicated duration columns first, then falls back to ``Minute``/``Second`` columns.
    Returns ``""`` when no duration can be determined.
    """
    val = None
    for col in _DURATION_COLUMNS:
        v = (
            row.get(col)
            if col in (row.index if hasattr(row, "index") else row)
            else None
        )
        if v is not None and not (isinstance(v, float) and pd.isna(v)):
            val = v
            break

    # Fallback: separate Minute / Second columns
    if val is None and (
        "Minute" in (row.index if hasattr(row, "index") else row)
        or "Second" in (row.index if hasattr(row, "index") else row)
    ):
        try:
            m = int(row.get("Minute") or 0)
            s = int(row.get("Second") or 0)
            total = max(0, m * 60 + s)
            return f"{total // 60}:{total % 60:02d}" if total > 0 else ""
        except Exception:
            pass

    if val is None:
        return ""

    # Numeric: Excel fraction or raw seconds
    if isinstance(val, (int, float)):
        try:
            f = float(val)
            if 0 < f <= 5:
                total = int(round((f % 1.0) * 86400))
            else:
                total = int(round(f))
                if total < 300 and f < 100:
                    total *= 60
            return f"{total // 60}:{total % 60:02d}" if total > 0 else ""
        except Exception:
            return ""

    s = str(val).strip().replace(",", ":")
    # HH:MM:SS
    m3 = re.match(r"^(\d+):(\d{2}):(\d{2})$", s)
    if m3:
        total = int(m3.group(1)) * 3600 + int(m3.group(2)) * 60 + int(m3.group(3))
        return f"{total // 60}:{total % 60:02d}" if total > 0 else ""
    # M:SS
    m2 = re.match(r"^(\d{1,2}):(\d{2})$", s)
    if m2:
        total = int(m2.group(1)) * 60 + int(m2.group(2))
        return f"{int(m2.group(1))}:{int(m2.group(2)):02d}" if total > 0 else ""
    # Plain digits → assume seconds
    if s.isdigit():
        total = int(s)
        return f"{total // 60}:{total % 60:02d}" if total > 0 else ""

    return ""


# ---------------------------------------------------------------------------
# Time-of-day display helpers
# ---------------------------------------------------------------------------


def format_time_display(time_str: str, lang: str = "en") -> str:
    """Format an ``HH:MM`` string for display (12 h with am/pm for EN, ``Uhr`` suffix for DE)."""
    if not time_str:
        return ""
    if lang == "de":
        return f"{time_str} Uhr"
    try:
        hh, mm = (int(x) for x in str(time_str).split(":", 1))
        suffix = "am" if hh < 12 else "pm"
        hour12 = (hh % 12) or 12
        return f"{hour12}:{mm:02d} {suffix}"
    except Exception:
        return str(time_str)


def format_duration_display(dur_str: str) -> str:
    """Append `` min`` to a duration string, or return ``""``."""
    return f"{dur_str} min" if dur_str else ""


# ---------------------------------------------------------------------------
# Season formatting
# ---------------------------------------------------------------------------


def season_sort_key(s: Any) -> int:
    """Extract numeric season number for sorting, e.g. ``'Season 19'`` → ``19``."""
    try:
        return int(str(s).lower().replace("season", "").strip())
    except Exception:
        return 0


def format_season_display(s: Any) -> str:
    """Human-readable season label.

    * Seasons 1–20 → ``Season N``
    * Seasons 21+  → ``YYYY: Season N`` (6 per year starting 2026)
    """
    if s is None or (isinstance(s, float) and pd.isna(s)):
        return "Unknown Season"
    num = season_sort_key(s)
    if num <= 0:
        return str(s)
    if num >= 21:
        offset = num - 21
        year = 2026 + (offset // 6)
        season_in_year = (offset % 6) + 1
        return f"{year}: Season {season_in_year}"
    return f"Season {num}"
