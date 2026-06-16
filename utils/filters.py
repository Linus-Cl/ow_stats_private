"""
utils/filters.py
================
Shared data-filtering and winrate-calculation helpers used across multiple
page modules (stats, roles, history, …).
"""

from __future__ import annotations

import pandas as pd

import config
from data import loader


# ---------------------------------------------------------------------------
# Core data filter
# ---------------------------------------------------------------------------


def filter_data(
    player: str,
    season: str | None = None,
    month: str | None = None,
    year: int | str | None = None,
) -> pd.DataFrame:
    """Return a filtered copy of the global DataFrame for *player*.

    Applies season **or** year/month filters, then restricts to rows where
    the player actually participated (non-bench).  Result has synthetic
    ``Hero`` and ``Rolle`` columns for convenient downstream grouping.
    """
    df = loader.get_df()
    if df.empty:
        return pd.DataFrame()

    temp = df[df["Win Lose"].isin(["Win", "Lose"])].copy()

    # Time-range filter: season takes precedence
    if season:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]

    role_col = f"{player} Rolle"
    hero_col = f"{player} Hero"
    if role_col not in temp.columns or hero_col not in temp.columns:
        return pd.DataFrame()

    temp = temp[temp[role_col].notna() & (temp[role_col] != "nicht dabei")]
    if temp.empty:
        return pd.DataFrame()

    temp["Hero"] = temp[hero_col].str.strip()
    temp["Rolle"] = temp[role_col].str.strip()
    return temp[temp["Hero"].notna() & (temp["Hero"] != "")]


# ---------------------------------------------------------------------------
# Winrate calculation
# ---------------------------------------------------------------------------


def calculate_winrate(
    data: pd.DataFrame,
    group_col: str,
) -> pd.DataFrame:
    """Group *data* by *group_col* and compute Win/Lose/Winrate/Spiele columns."""
    empty = pd.DataFrame(columns=[group_col, "Win", "Lose", "Winrate", "Spiele"])
    if data.empty or not isinstance(group_col, str) or group_col not in data.columns:
        return empty

    data = data.copy()
    data[group_col] = data[group_col].astype(str).str.strip()
    data = data[data[group_col].notna() & (data[group_col] != "")]
    if data.empty:
        return empty

    grouped = (
        data.groupby([group_col, "Win Lose"], observed=False)
        .size()
        .unstack(fill_value=0)
    )
    if "Win" not in grouped:
        grouped["Win"] = 0
    if "Lose" not in grouped:
        grouped["Lose"] = 0
    grouped["Spiele"] = grouped["Win"] + grouped["Lose"]
    grouped["Winrate"] = grouped["Win"] / grouped["Spiele"]
    return grouped.reset_index().sort_values("Winrate", ascending=False)


# ---------------------------------------------------------------------------
# Helpers shared between role-assignment and other pages
# ---------------------------------------------------------------------------


_INVALID_HERO_VALUES = frozenset({"nicht dabei", "none", "nan", ""})


def is_valid_hero(x: str) -> bool:
    """Return ``True`` if the value represents a real hero pick (not bench/empty)."""
    s = str(x).strip().lower()
    return bool(s) and s not in _INVALID_HERO_VALUES


def is_valid_hero_series(s: "pd.Series") -> "pd.Series":
    """Vectorised version of :func:`is_valid_hero` for a whole Series."""
    normed = s.astype(str).str.strip().str.lower()
    return normed.ne("") & ~normed.isin(_INVALID_HERO_VALUES) & s.notna()
