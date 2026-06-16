"""
data/loader.py
==============
Central data module: JSONL read/write, DataFrame build, reload, patch.

The module-level ``df`` holds the current merged DataFrame.
Use ``get_df()`` for read access and ``reload()`` to refresh.
"""

from __future__ import annotations

import json
import os
import threading
from typing import Optional

import pandas as pd

import config
import firebase_service

# ── Module state ───────────────────────────────────────────────────────────
df: pd.DataFrame = pd.DataFrame()
_jsonl_lock = threading.Lock()
_jsonl_last_mtime: float = 0.0


# ── Public helpers ─────────────────────────────────────────────────────────


def get_df() -> pd.DataFrame:
    """Read-only access to the current DataFrame."""
    return df


# ── JSONL I/O ──────────────────────────────────────────────────────────────


def jsonl_read() -> list[dict]:
    """Read all match dicts from the local JSONL file."""
    try:
        with open(config.LOCAL_DATA_FILE, "r", encoding="utf-8") as fh:
            return [json.loads(line) for line in fh if line.strip()]
    except FileNotFoundError:
        return []
    except Exception as exc:
        print(f"[JSONL] read error: {exc}")
        return []


def jsonl_write(matches: list[dict]) -> None:
    """Atomically overwrite the local JSONL file."""
    tmp = config.LOCAL_DATA_FILE + ".tmp"
    try:
        with _jsonl_lock:
            with open(tmp, "w", encoding="utf-8") as fh:
                for m in matches:
                    fh.write(json.dumps(m, default=str) + "\n")
            os.replace(tmp, config.LOCAL_DATA_FILE)
    except Exception as exc:
        print(f"[JSONL] write error: {exc}")


def jsonl_append(match_dict: dict) -> None:
    """Append a single match to the local JSONL file."""
    try:
        with _jsonl_lock:
            with open(config.LOCAL_DATA_FILE, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(match_dict, default=str) + "\n")
    except Exception as exc:
        print(f"[JSONL] append error: {exc}")


def jsonl_upsert(match_dict: dict) -> None:
    """Replace (or add) a match by match_id in the local JSONL file."""
    match_id = match_dict.get("match_id")
    matches = jsonl_read()
    replaced = False
    for i, m in enumerate(matches):
        if str(m.get("match_id")) == str(match_id):
            matches[i] = match_dict
            replaced = True
            break
    if not replaced:
        matches.append(match_dict)
    jsonl_write(matches)


def jsonl_delete(match_id: int) -> None:
    """Remove a match by match_id from the local JSONL file."""
    matches = jsonl_read()
    filtered = [m for m in matches if str(m.get("match_id")) != str(match_id)]
    jsonl_write(filtered)


# ── Hero name normalisation ────────────────────────────────────────────────
# Old data sometimes used shorthand or typo variants.  This map canonicalises
# them so stats, filters and image lookups all see consistent names.
_HERO_NORM: dict[str, str] = {
    "dva": "D.Va",
    "d.va": "D.Va",
    "soldier 76": "Soldier 76",
    "soldier76": "Soldier 76",
    "soldier": "Soldier 76",
    "wrecking ball": "Wrecking Ball",
    "wreckingball": "Wrecking Ball",
    "hammond": "Wrecking Ball",
    "torbjorn": "Torbjörn",
    "torbjörn": "Torbjörn",
    "lucio": "Lúcio",
    "lúcio": "Lúcio",
    "junkerqueen": "Junker Queen",
    "junker queen": "Junker Queen",
    "baptist": "Baptiste",
    "baptiste": "Baptiste",
    "zen": "Zenyatta",
    "zenyatta": "Zenyatta",
    "jetpackcat": "Jetpack Cat",
    "jetpack cat": "Jetpack Cat",
    "kings row": "King's Row",
    "king's row": "King's Row",
    "paraiso": "Paraíso",
    "paraíso": "Paraíso",
    "esperanca": "Esperança",
    "esperança": "Esperança",
}

_MAP_NORM: dict[str, str] = {
    "kings row": "King's Row",
    "king's row": "King's Row",
    "paraiso": "Paraíso",
    "paraíso": "Paraíso",
    "esperanca": "Esperança",
    "esperança": "Esperança",
    "illios": "Ilios",
    "watchpoint gibralta": "Watchpoint Gibraltar",
}


def _norm_map(name: str) -> str:
    """Return the canonical display name for a map (case-insensitive lookup)."""
    if not isinstance(name, str):
        return name
    return _MAP_NORM.get(name.strip().lower(), name.strip())


def _norm_hero(name: str) -> str:
    """Return the canonical display name for a hero (case-insensitive lookup)."""
    if not isinstance(name, str):
        return name
    return _HERO_NORM.get(name.strip().lower(), name.strip())


# ── Firestore → DataFrame conversion ──────────────────────────────────────


def _matches_to_df(fb_matches: list[dict]) -> pd.DataFrame:
    """Convert Firestore-style match documents to a DataFrame."""
    rows: list[dict] = []
    for m in fb_matches:
        row: dict = {
            "Match ID": m.get("match_id"),
            "Win Lose": m.get("result"),
            "Map": _norm_map(m.get("map")),
            "Gamemode": m.get("gamemode"),
            "Attack Def": m.get("attack_defense"),
            "Datum": m.get("date"),
            "Season": m.get("season"),
            "Time": m.get("time"),
        }
        # Duration columns
        if "matchtime" in m:
            row["Matchtime"] = m["matchtime"]
        elif "duration" in m:
            row["Matchtime"] = m["duration"]

        players = m.get("players", {})
        for pname, pdata in players.items():
            hero_raw = pdata.get("hero", "nicht dabei")
            row[f"{pname} Hero"] = (
                _norm_hero(hero_raw) if hero_raw != "nicht dabei" else hero_raw
            )
            row[f"{pname} Rolle"] = pdata.get("role", "nicht dabei")
        # Ensure every configured player has columns
        for pname in config.PLAYERS:
            row.setdefault(f"{pname} Hero", "nicht dabei")
            row.setdefault(f"{pname} Rolle", "nicht dabei")
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)

    # Numeric match ID, sorted descending
    if "Match ID" in result.columns:
        result["Match ID"] = pd.to_numeric(result["Match ID"], errors="coerce")
        result.sort_values("Match ID", ascending=False, inplace=True)
        result.reset_index(drop=True, inplace=True)

    # Datetime + derived columns
    if "Datum" in result.columns:
        result["Datum"] = pd.to_datetime(result["Datum"], errors="coerce")
        valid = result["Datum"].notna()
        result["Jahr"] = result["Datum"].dt.year.where(valid)
        result["Monat"] = result["Datum"].dt.month.where(valid)
        result["Wochentag"] = result["Datum"].dt.day_name().where(valid)
        result["KW"] = (
            result["Datum"].dt.isocalendar().week.astype("Int64").where(valid)
        )

    # Categoricals for memory efficiency
    cat_cols = ["Win Lose", "Map", "Season", "Gamemode", "Attack Def"]
    for p in config.PLAYERS:
        cat_cols += [f"{p} Hero", f"{p} Rolle"]
    for col in cat_cols:
        if col in result.columns:
            try:
                result[col] = result[col].astype("category")
            except Exception:
                pass

    return result


# ── Build / Reload ─────────────────────────────────────────────────────────


def build_merged_df() -> pd.DataFrame:
    """Read from local JSONL (primary). Bootstrap from Firestore if empty."""
    matches = jsonl_read()
    if matches:
        return _matches_to_df(matches)
    # Bootstrap: local file missing → one-time Firestore read
    if firebase_service.is_available():
        print("[Data] Local store empty – bootstrapping from Firestore …")
        fb = firebase_service.get_all_matches()
        if fb:
            jsonl_write(fb)
            print(f"[Data] Local store written: {len(fb)} matches")
            return _matches_to_df(fb)
    return pd.DataFrame()


def reload() -> None:
    """Reload global *df* from JSONL.  Mtime-guarded (no-op when unchanged)."""
    global df, _jsonl_last_mtime
    try:
        mtime = os.path.getmtime(config.LOCAL_DATA_FILE)
    except OSError:
        mtime = 0.0

    if mtime and mtime == _jsonl_last_mtime and not df.empty:
        return  # file unchanged

    merged = build_merged_df()
    if not merged.empty:
        df = merged
        _jsonl_last_mtime = mtime


def patch_with_match(match_data: dict) -> None:
    """Update in-memory *df* after save/update – zero Firestore reads."""
    global df
    try:
        new_row = _matches_to_df([match_data])
        if new_row.empty:
            return
        mid = match_data.get("match_id")
        if mid is not None and not df.empty and "Match ID" in df.columns:
            df = df[df["Match ID"] != int(mid)].copy()
        df = pd.concat([new_row, df], ignore_index=True)
        if "Match ID" in df.columns:
            df.sort_values("Match ID", ascending=False, inplace=True)
            df.reset_index(drop=True, inplace=True)
        # Broadcast change (import here to avoid circular)
        from data.state import set_app_state
        import time as _t

        set_app_state("data_token", str(int(_t.time() * 1000)))
    except Exception as exc:
        print(f"[Data] patch_with_match failed: {exc}")


def remove_row(match_id: int) -> None:
    """Remove a row from in-memory *df* – zero Firestore reads."""
    global df
    try:
        if not df.empty and "Match ID" in df.columns:
            df = df[df["Match ID"] != match_id].reset_index(drop=True)
        from data.state import set_app_state
        import time as _t

        set_app_state("data_token", str(int(_t.time() * 1000)))
    except Exception as exc:
        print(f"[Data] remove_row failed: {exc}")


def get_next_match_id() -> int:
    """Get next match_id considering both JSONL and Firestore data."""
    max_id = 0
    if not df.empty and "Match ID" in df.columns:
        try:
            max_id = max(max_id, int(df["Match ID"].max()))
        except Exception:
            pass
    if firebase_service.is_available():
        try:
            fb_next = firebase_service.get_next_match_id()
            max_id = max(max_id, fb_next - 1)
        except Exception:
            pass
    return max_id + 1
