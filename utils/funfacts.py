"""
utils/funfacts.py
=================
Generates random fun-fact strings from the all-time match DataFrame.

Each fact is a complete, readable sentence in either English or German.
Call ``get_random_fact(df, lang)`` from any page callback; it returns a
single string or ``None`` if no facts can be computed.

Facts are intentionally niche — things you'd never notice just by looking
at the graphs.
"""

from __future__ import annotations

import random
from itertools import combinations
from typing import Optional

import pandas as pd

import config
from utils.filters import is_valid_hero

# ---------------------------------------------------------------------------
# Module-level cache: (n_rows, max_match_id, lang) → list[str]
# Recomputed only when the DataFrame changes (new data loaded).
# ---------------------------------------------------------------------------
_facts_cache: dict[tuple, list[str]] = {}


def _cache_key(df: pd.DataFrame, lang: str) -> tuple:
    n = len(df)
    max_id = int(df["Match ID"].max()) if ("Match ID" in df.columns and n > 0) else 0
    return (n, max_id, lang)


def get_random_fact(df: pd.DataFrame, lang: str) -> Optional[str]:
    """Return a random fun-fact string, or None if the df is too small.

    Results are cached per (row-count, latest-match-id, language) so the
    expensive computation only runs once after each data reload.
    """
    key = _cache_key(df, lang)
    if key not in _facts_cache:
        # Evict stale entries for the same lang to avoid unbounded growth
        for old_key in [k for k in _facts_cache if k[2] == lang]:
            del _facts_cache[old_key]
        _facts_cache[key] = _collect_facts(df, lang)
    facts = _facts_cache[key]
    return random.choice(facts) if facts else None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _L(en: str, de: str, lang: str) -> str:
    return de if lang == "de" else en


def _fmt(n: float | int, decimals: int = 1) -> str:
    if decimals == 0 or float(n) == int(n):
        return str(int(n))
    return f"{n:.{decimals}f}"


def _streaks(series: pd.Series) -> tuple[int, int]:
    """Return (max_win_streak, max_loss_streak) from a Win Lose series (sorted oldest→newest)."""
    win_s = loss_s = max_win = max_loss = 0
    for v in series.astype(str):
        if v == "Win":
            win_s += 1
            loss_s = 0
        else:
            loss_s += 1
            win_s = 0
        max_win = max(max_win, win_s)
        max_loss = max(max_loss, loss_s)
    return max_win, max_loss


def _collect_facts(df: pd.DataFrame, lang: str) -> list[str]:  # noqa: C901
    if df.empty or "Win Lose" not in df.columns:
        return []

    facts: list[str] = []
    d = df.copy()
    d["_win"] = d["Win Lose"].astype(str) == "Win"

    total = len(d)
    wins = int(d["_win"].sum())
    losses = total - wins

    # ── Streaks ─────────────────────────────────────────────────────────────
    if "Match ID" in d.columns:
        sorted_wl = d.sort_values("Match ID")["Win Lose"]
        max_win, max_loss = _streaks(sorted_wl)
        if max_win >= 5:
            facts.append(
                _L(
                    f"Your longest win streak is {max_win} games — and your longest loss streak is {max_loss}.",
                    f"Eure längste Siegesserie: {max_win} Spiele. Eure längste Niederlagenserie: {max_loss}.",
                    lang,
                )
            )
        if max_loss >= 8:
            facts.append(
                _L(
                    f"You once lost {max_loss} games in a row. Whatever happened that day, we don't talk about it.",
                    f"Ihr habt einmal {max_loss} Spiele hintereinander verloren. Was auch immer damals passiert ist – wir reden nicht darüber.",
                    lang,
                )
            )

    # ── Milestone countdown ──────────────────────────────────────────────────
    milestones = [500, 1000, 2000, 3000, 5000, 7500, 10000]
    next_ms = next((m for m in milestones if m > total), ((total // 1000) + 1) * 1000)
    remaining = next_ms - total
    if remaining <= 200:
        facts.append(
            _L(
                f"Only {remaining} more games until the {next_ms:,}-match milestone.",
                f"Nur noch {remaining} Spiele bis zum {next_ms:,}-Match-Meilenstein.",
                lang,
            )
        )
    elif total >= 100:
        facts.append(
            _L(
                f"{total:,} games played in total. {remaining} left until {next_ms:,}.",
                f"{total:,} Spiele insgesamt. Noch {remaining} bis {next_ms:,}.",
                lang,
            )
        )

    # ── Nemesis map (heavily played, mediocre WR) ───────────────────────────
    if "Map" in d.columns:
        map_counts = d["Map"].astype(str).value_counts()
        eligible = map_counts[map_counts >= 30].index
        if len(eligible) >= 3:
            map_wr = (
                d[d["Map"].astype(str).isin(eligible)]
                .groupby(d["Map"].astype(str))["_win"]
                .mean()
                * 100
            )
            plays_norm = map_counts[eligible] / map_counts[eligible].max()
            wr_inv = 1 - (map_wr / 100)
            nemesis_score = plays_norm * wr_inv
            nemesis_map = nemesis_score.idxmax()
            nemesis_n = int(map_counts[nemesis_map])
            nemesis_wr = map_wr[nemesis_map]
            facts.append(
                _L(
                    f"Your nemesis map is {nemesis_map}: {nemesis_n:,} games played, only {_fmt(nemesis_wr)}% winrate.",
                    f"Eure Nemesis-Map ist {nemesis_map}: {nemesis_n:,} Spiele gespielt, nur {_fmt(nemesis_wr)}% Winrate.",
                    lang,
                )
            )

    # ── Best map (high play count + high WR) ────────────────────────────────
    if "Map" in d.columns:
        map_counts = d["Map"].astype(str).value_counts()
        eligible = map_counts[map_counts >= 30].index
        if len(eligible) >= 2:
            map_wr = (
                d[d["Map"].astype(str).isin(eligible)]
                .groupby(d["Map"].astype(str))["_win"]
                .mean()
                * 100
            )
            best_map = map_wr.idxmax()
            best_wr = map_wr[best_map]
            best_n = int(map_counts[best_map])
            facts.append(
                _L(
                    f"Your stomping ground: {best_map} at {_fmt(best_wr)}% winrate over {best_n:,} games.",
                    f"Eure Lieblingsmap: {best_map} mit {_fmt(best_wr)}% Winrate über {best_n:,} Spiele.",
                    lang,
                )
            )

    # ── Attack vs Defense gap ────────────────────────────────────────────────
    if "Attack Def" in d.columns:
        att = d[d["Attack Def"].astype(str) == "Attack"]
        deff = d[d["Attack Def"].astype(str) == "Defense"]
        if len(att) >= 50 and len(deff) >= 50:
            att_wr = att["_win"].mean() * 100
            def_wr = deff["_win"].mean() * 100
            diff = att_wr - def_wr
            if abs(diff) >= 5:
                if diff > 0:
                    facts.append(
                        _L(
                            f"On attack you win {_fmt(att_wr)}%, on defense only {_fmt(def_wr)}% — {_fmt(abs(diff))} percentage points better when pushing.",
                            f"Als Angreifer gewinnt ihr {_fmt(att_wr)}%, als Verteidiger nur {_fmt(def_wr)}% – {_fmt(abs(diff))} Prozentpunkte stärker im Angriff.",
                            lang,
                        )
                    )
                else:
                    facts.append(
                        _L(
                            f"You're actually better on defense ({_fmt(def_wr)}%) than on attack ({_fmt(att_wr)}%) — unconventional.",
                            f"Als Verteidiger seid ihr mit {_fmt(def_wr)}% sogar besser als im Angriff ({_fmt(att_wr)}%) – ungewöhnlich.",
                            lang,
                        )
                    )

    # ── Best calendar week ever ──────────────────────────────────────────────
    if "KW" in d.columns and "Jahr" in d.columns:
        kw_counts = d.groupby(["Jahr", "KW"]).size()
        if not kw_counts.empty:
            top_kw = kw_counts.idxmax()
            top_kw_n = int(kw_counts.max())
            if top_kw_n >= 30:
                facts.append(
                    _L(
                        f"Your most intense week: calendar week {int(top_kw[1])} of {int(top_kw[0])} — {top_kw_n} games in 7 days.",
                        f"Eure intensivste Woche: KW {int(top_kw[1])} {int(top_kw[0])} – {top_kw_n} Spiele in 7 Tagen.",
                        lang,
                    )
                )

    # ── Late night winrate ───────────────────────────────────────────────────
    if "Time" in d.columns:
        d["_hour"] = pd.to_numeric(
            d["Time"].astype(str).str.split(":").str[0], errors="coerce"
        )
        late = d[d["_hour"] >= 22]
        prime = d[(d["_hour"] >= 19) & (d["_hour"] < 22)]
        if len(late) >= 15 and len(prime) >= 30:
            late_wr = late["_win"].mean() * 100
            prime_wr = prime["_win"].mean() * 100
            diff = late_wr - prime_wr
            if abs(diff) >= 4:
                if diff > 0:
                    facts.append(
                        _L(
                            f"Late night gaming (22:00+) actually works: {_fmt(late_wr)}% WR vs {_fmt(prime_wr)}% in prime time.",
                            f"Late-Night-Gaming (ab 22 Uhr) funktioniert: {_fmt(late_wr)}% WR vs. {_fmt(prime_wr)}% zur Primetime.",
                            lang,
                        )
                    )
                else:
                    facts.append(
                        _L(
                            f"After 22:00 things fall apart: {_fmt(late_wr)}% WR, {_fmt(abs(diff))}pp below your prime-time average.",
                            f"Nach 22 Uhr läuft's schlechter: {_fmt(late_wr)}% WR – {_fmt(abs(diff))} Prozentpunkte unter der Primetime.",
                            lang,
                        )
                    )

    # ── Pain heroes (many games, below 50% WR) ──────────────────────────────
    for player in config.PLAYERS:
        hero_col = f"{player} Hero"
        if hero_col not in d.columns:
            continue
        active = d[d[hero_col].astype(str).apply(is_valid_hero)].copy()
        if active.empty:
            continue
        hero_counts = active[hero_col].astype(str).value_counts()
        eligible_h = hero_counts[hero_counts >= 20].index
        if eligible_h.empty:
            continue
        sub = active[active[hero_col].astype(str).isin(eligible_h)]
        hero_wr = sub.groupby(sub[hero_col].astype(str))["_win"].mean() * 100
        pain = hero_wr[hero_wr < 48]
        if not pain.empty:
            worst_h = pain.idxmin()
            worst_wr = pain[worst_h]
            worst_n = int(hero_counts[worst_h])
            facts.append(
                _L(
                    f"{player} has played {worst_h} {worst_n:,} times at only {_fmt(worst_wr)}% WR. Classic masochism.",
                    f"{player} hat {worst_h} {worst_n:,}-mal gespielt – bei nur {_fmt(worst_wr)}% Winrate. Echter Masochismus.",
                    lang,
                )
            )

    # ── Hero duo synergy (vectorised — no iterrows) ─────────────────────────
    hero_cols = [f"{p} Hero" for p in config.PLAYERS if f"{p} Hero" in d.columns]
    player_names_duo = [c.replace(" Hero", "") for c in hero_cols]
    if len(hero_cols) >= 2:
        duo_total: dict[str, int] = {}
        duo_wins_d: dict[str, int] = {}
        for (p1, c1), (p2, c2) in combinations(zip(player_names_duo, hero_cols), 2):
            v1 = d[c1].astype(str).map(is_valid_hero)
            v2 = d[c2].astype(str).map(is_valid_hero)
            sub = d.loc[v1 & v2, [c1, c2, "_win"]]
            if sub.empty:
                continue
            # Vectorised key: "P1:Hero1|P2:Hero2" — p1 always sorted before p2
            # because combinations() preserves insertion order
            key_ser = (
                p1 + ":" + sub[c1].astype(str) + "|" + p2 + ":" + sub[c2].astype(str)
            )
            grp = sub.groupby(key_ser.values)["_win"].agg(total="count", wins="sum")
            for key_str, grow in grp.iterrows():
                duo_total[key_str] = duo_total.get(key_str, 0) + int(grow["total"])
                duo_wins_d[key_str] = duo_wins_d.get(key_str, 0) + int(grow["wins"])

        duo_wr_map = {
            k: duo_wins_d.get(k, 0) / v for k, v in duo_total.items() if v >= 15
        }
        if duo_wr_map:
            best_key_str = max(duo_wr_map, key=duo_wr_map.get)
            best_wr = duo_wr_map[best_key_str] * 100
            best_n = duo_total[best_key_str]
            p1_str, p2_str = best_key_str.split("|")
            p1_name, h1 = p1_str.split(":", 1)
            p2_name, h2 = p2_str.split(":", 1)
            if best_wr >= 70:
                facts.append(
                    _L(
                        f"{p1_name} on {h1} + {p2_name} on {h2}: {_fmt(best_wr)}% WR over {best_n} games — your secret weapon combo.",
                        f"{p1_name} auf {h1} + {p2_name} auf {h2}: {_fmt(best_wr)}% Winrate über {best_n} Spiele – eure Geheimwaffe.",
                        lang,
                    )
                )

    # ── Per-player absence rate ──────────────────────────────────────────────
    absent_rates: dict[str, float] = {}
    for player in config.PLAYERS:
        hero_col = f"{player} Hero"
        if hero_col not in d.columns:
            continue
        absent = (d[hero_col].astype(str) == "nicht dabei").sum()
        rate = absent / total * 100
        absent_rates[player] = rate

    if absent_rates:
        most_absent = max(absent_rates, key=absent_rates.get)
        most_absent_rate = absent_rates[most_absent]
        if most_absent_rate >= 20:
            present_wr_rows = d[d[f"{most_absent} Hero"].astype(str) != "nicht dabei"]
            present_wr = (
                present_wr_rows["_win"].mean() * 100
                if not present_wr_rows.empty
                else None
            )
            if present_wr is not None:
                facts.append(
                    _L(
                        f"{most_absent} was absent in {_fmt(most_absent_rate)}% of all matches. "
                        f"When they do show up, you win {_fmt(present_wr)}% of the time.",
                        f"{most_absent} war bei {_fmt(most_absent_rate)}% aller Matches nicht dabei. "
                        f"Wenn sie/er spielt, gewinnt ihr {_fmt(present_wr)}% der Zeit.",
                        lang,
                    )
                )

    # ── Season best/worst ────────────────────────────────────────────────────
    if "Season" in d.columns:
        season_counts = d["Season"].astype(str).value_counts()
        eligible_s = season_counts[season_counts >= 30].index
        if len(eligible_s) >= 3:
            season_wr = (
                d[d["Season"].astype(str).isin(eligible_s)]
                .groupby(d["Season"].astype(str))["_win"]
                .mean()
                * 100
            )
            best_s = season_wr.idxmax()
            worst_s = season_wr.idxmin()
            if season_wr[best_s] - season_wr[worst_s] >= 5:
                facts.append(
                    _L(
                        f"{best_s} was your best season ever ({_fmt(season_wr[best_s])}% WR). "
                        f"{worst_s} was the one you'd rather forget ({_fmt(season_wr[worst_s])}%).",
                        f"{best_s} war eure beste Season ({_fmt(season_wr[best_s])}% WR). "
                        f"{worst_s} war die, die ihr am liebsten vergessen würdet ({_fmt(season_wr[worst_s])}%).",
                        lang,
                    )
                )

    # ── Most active weekday ───────────────────────────────────────────────────
    if "Wochentag" in d.columns:
        day_counts = d["Wochentag"].dropna().astype(str).value_counts()
        if len(day_counts) >= 2:
            top_day = day_counts.index[0]
            least_day = day_counts.index[-1]
            top_n = int(day_counts.iloc[0])
            least_n = int(day_counts.iloc[-1])
            facts.append(
                _L(
                    f"{top_day} is game night ({top_n:,} games). "
                    f"{least_day} barely exists in your history ({least_n:,} games).",
                    f"{_translate_weekday(top_day)} ist Spieltag ({top_n:,} Spiele). "
                    f"{_translate_weekday(least_day)} existiert in eurer Historie kaum ({least_n:,} Spiele).",
                    lang,
                )
            )

    # ── Hero that only one player has ever touched ───────────────────────────
    hero_player_map: dict[str, set] = {}
    for player in config.PLAYERS:
        hero_col = f"{player} Hero"
        if hero_col not in d.columns:
            continue
        for h in d[hero_col].astype(str).unique():
            if is_valid_hero(h):
                hero_player_map.setdefault(h, set()).add(player)

    solo_heroes = [
        (h, list(pset)[0]) for h, pset in hero_player_map.items() if len(pset) == 1
    ]
    if solo_heroes:
        # pick the one with most games
        def _solo_games(h_p):
            h, p = h_p
            col = f"{p} Hero"
            return int((d[col].astype(str) == h).sum()) if col in d.columns else 0

        solo_heroes.sort(key=_solo_games, reverse=True)
        top_solo_h, top_solo_p = solo_heroes[0]
        top_solo_n = _solo_games((top_solo_h, top_solo_p))
        if top_solo_n >= 15:
            facts.append(
                _L(
                    f"{top_solo_h} has been played {top_solo_n:,} times — exclusively by {top_solo_p}. Nobody else has ever touched it.",
                    f"{top_solo_h} wurde {top_solo_n:,}-mal gespielt – ausschließlich von {top_solo_p}. Niemand sonst hat diesen Held je gewählt.",
                    lang,
                )
            )

    # ── Gamemode WR gap ──────────────────────────────────────────────────────
    if "Gamemode" in d.columns:
        gm_counts = d["Gamemode"].astype(str).value_counts()
        eligible_gm = gm_counts[gm_counts >= 50].index
        if len(eligible_gm) >= 2:
            gm_wr = (
                d[d["Gamemode"].astype(str).isin(eligible_gm)]
                .groupby(d["Gamemode"].astype(str))["_win"]
                .mean()
                * 100
            )
            best_gm = gm_wr.idxmax()
            worst_gm = gm_wr.idxmin()
            gm_diff = gm_wr[best_gm] - gm_wr[worst_gm]
            if gm_diff >= 4:
                facts.append(
                    _L(
                        f"{best_gm} is your best gamemode ({_fmt(gm_wr[best_gm])}% WR), "
                        f"{worst_gm} your worst ({_fmt(gm_wr[worst_gm])}%). "
                        f"That's a {_fmt(gm_diff)}pp gap.",
                        f"{best_gm} ist euer bester Spielmodus ({_fmt(gm_wr[best_gm])}% WR), "
                        f"{worst_gm} euer schlechtester ({_fmt(gm_wr[worst_gm])}%). "
                        f"Das sind {_fmt(gm_diff)} Prozentpunkte Unterschied.",
                        lang,
                    )
                )

    # ── Most games in a single day ───────────────────────────────────────────
    if "Datum" in d.columns:
        day_game_counts = d.dropna(subset=["Datum"]).groupby(d["Datum"].dt.date).size()
        if not day_game_counts.empty:
            busiest_day = day_game_counts.idxmax()
            busiest_n = int(day_game_counts.max())
            if busiest_n >= 20:
                day_num = busiest_day.day
                busiest_str = (
                    busiest_day.strftime("%d.%m.%Y")
                    if lang == "de"
                    else f"{busiest_day.strftime('%B')} {day_num}, {busiest_day.year}"
                )
                facts.append(
                    _L(
                        f"On {busiest_str} you played {busiest_n} games in a single day. "
                        f"That's roughly {busiest_n * 15 // 60}h{busiest_n * 15 % 60:02d}m of non-stop Overwatch.",
                        f"Am {busiest_day.strftime('%d.%m.%Y')} habt ihr {busiest_n} Spiele an einem einzigen Tag gespielt – "
                        f"das sind rund {busiest_n * 15 // 60}h{busiest_n * 15 % 60:02d}m Overwatch am Stück.",
                        lang,
                    )
                )

    # ── 4-stack paradox (all 4 players present = lower WR?) ─────────────────
    hero_cols_all = [f"{p} Hero" for p in config.PLAYERS if f"{p} Hero" in d.columns]
    if len(hero_cols_all) >= 3:
        # Vectorised: per-column boolean & instead of row-wise apply()
        full_mask = pd.Series(True, index=d.index)
        for _hc in hero_cols_all:
            full_mask = full_mask & d[_hc].astype(str).map(is_valid_hero)
        full_wr = d[full_mask]["_win"].mean() * 100 if full_mask.sum() >= 30 else None
        part_wr = (
            d[~full_mask]["_win"].mean() * 100 if (~full_mask).sum() >= 30 else None
        )
        if full_wr is not None and part_wr is not None:
            diff4 = part_wr - full_wr
            if diff4 >= 2:
                facts.append(
                    _L(
                        f"Counterintuitively, when all {len(hero_cols_all)} of you play together "
                        f"you win {_fmt(full_wr)}% — that's {_fmt(diff4)}pp worse than partial squads ({_fmt(part_wr)}%). "
                        f"More people, more problems.",
                        f"Kurioserweise gewinnt ihr mit allen {len(hero_cols_all)} Spielern gleichzeitig nur {_fmt(full_wr)}% — "
                        f"{_fmt(diff4)} Prozentpunkte schlechter als mit unvollständiger Truppe ({_fmt(part_wr)}%). "
                        f"Mehr Leute, mehr Chaos.",
                        lang,
                    )
                )
            elif full_wr - part_wr >= 2:
                facts.append(
                    _L(
                        f"When all {len(hero_cols_all)} of you squad up, you win {_fmt(full_wr)}% — "
                        f"{_fmt(full_wr - part_wr)}pp above your partial-squad average. Full stack or no stack.",
                        f"Wenn alle {len(hero_cols_all)} zusammen spielen, gewinnt ihr {_fmt(full_wr)}% — "
                        f"{_fmt(full_wr - part_wr)} Prozentpunkte über dem Teilteam-Schnitt. Entweder alle oder keiner.",
                        lang,
                    )
                )

    # ── Map with biggest attack vs defense gap ───────────────────────────────
    if "Attack Def" in d.columns and "Map" in d.columns:
        att_map = (
            d[d["Attack Def"].astype(str) == "Attack"]
            .groupby(d["Map"].astype(str))["_win"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "att_wr", "count": "att_n"})
        )
        def_map = (
            d[d["Attack Def"].astype(str) == "Defense"]
            .groupby(d["Map"].astype(str))["_win"]
            .agg(["mean", "count"])
            .rename(columns={"mean": "def_wr", "count": "def_n"})
        )
        ad_both = att_map.join(def_map, how="inner")
        ad_both = ad_both[(ad_both["att_n"] >= 20) & (ad_both["def_n"] >= 20)]
        if not ad_both.empty:
            ad_both["gap"] = (ad_both["att_wr"] - ad_both["def_wr"]) * 100
            ad_both[["att_wr", "def_wr"]] *= 100
            lopsided_map = ad_both["gap"].abs().idxmax()
            gap_val = ad_both.loc[lopsided_map, "gap"]
            a_wr = ad_both.loc[lopsided_map, "att_wr"]
            df_wr = ad_both.loc[lopsided_map, "def_wr"]
            if abs(gap_val) >= 15:
                if gap_val > 0:
                    facts.append(
                        _L(
                            f"{lopsided_map}: {_fmt(a_wr)}% WR attacking, only {_fmt(df_wr)}% defending — "
                            f"a {_fmt(gap_val)}pp swing. Attack or bust.",
                            f"{lopsided_map}: {_fmt(a_wr)}% WR im Angriff, nur {_fmt(df_wr)}% in der Verteidigung – "
                            f"{_fmt(gap_val)} Prozentpunkte Unterschied. Angriff oder nichts.",
                            lang,
                        )
                    )
                else:
                    facts.append(
                        _L(
                            f"{lopsided_map}: {_fmt(df_wr)}% WR defending, only {_fmt(a_wr)}% attacking — "
                            f"a {_fmt(abs(gap_val))}pp swing. Happy to sit back on this one.",
                            f"{lopsided_map}: {_fmt(df_wr)}% WR in der Verteidigung, nur {_fmt(a_wr)}% im Angriff – "
                            f"{_fmt(abs(gap_val))} Prozentpunkte Unterschied. Hier verteidigt ihr gerne.",
                            lang,
                        )
                    )

    # ── Worst map in a specific gamemode ────────────────────────────────────
    if "Gamemode" in d.columns and "Map" in d.columns:
        gm_map_counts = d.groupby(
            [d["Gamemode"].astype(str), d["Map"].astype(str)]
        ).size()
        gm_map_wr = (
            d.groupby([d["Gamemode"].astype(str), d["Map"].astype(str)])["_win"].mean()
            * 100
        )
        worst_map_facts = []
        for gm in ["Escort", "Hybrid"]:
            sub_counts = gm_map_counts.get(
                gm,
                (
                    pd.Series(dtype=int)
                    if not isinstance(gm_map_counts.get(gm, None), pd.Series)
                    else gm_map_counts[gm]
                ),
            )
            try:
                sub_wr = gm_map_wr[gm]
                sub_c = gm_map_counts[gm]
            except KeyError:
                continue
            eligible_maps = sub_c[sub_c >= 30].index
            if eligible_maps.empty:
                continue
            sub_wr_elig = sub_wr[sub_wr.index.isin(eligible_maps)]
            if sub_wr_elig.empty:
                continue
            worst_m_name = sub_wr_elig.idxmin()
            worst_m_wr = sub_wr_elig.min()
            worst_m_n = int(sub_c[worst_m_name])
            if worst_m_wr < 47:
                worst_map_facts.append((worst_m_wr, worst_m_name, gm, worst_m_n))
        if worst_map_facts:
            worst_map_facts.sort()
            worst_m_wr, worst_m_name, worst_gm, worst_m_n = worst_map_facts[0]
            facts.append(
                _L(
                    f"{worst_m_name} is your kryptonite: only {_fmt(worst_m_wr)}% WR "
                    f"over {worst_m_n} {worst_gm} games. The map doesn't care.",
                    f"{worst_m_name} ist euer Kryptonit: nur {_fmt(worst_m_wr)}% Winrate "
                    f"in {worst_m_n} {worst_gm}-Spielen. Die Map interessiert das nicht.",
                    lang,
                )
            )

    # ── Seasonal pattern (best vs worst month) ───────────────────────────────
    if "Monat" in d.columns:
        _MONTHS_EN = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December",
        }
        _MONTHS_DE = {
            1: "Januar",
            2: "Februar",
            3: "März",
            4: "April",
            5: "Mai",
            6: "Juni",
            7: "Juli",
            8: "August",
            9: "September",
            10: "Oktober",
            11: "November",
            12: "Dezember",
        }
        mon_counts = d["Monat"].value_counts()
        eligible_mon = mon_counts[mon_counts >= 50].index
        if len(eligible_mon) >= 4:
            mon_wr = (
                d[d["Monat"].isin(eligible_mon)].groupby(d["Monat"])["_win"].mean()
                * 100
            )
            best_mon = int(mon_wr.idxmax())
            worst_mon = int(mon_wr.idxmin())
            mon_diff = mon_wr[best_mon] - mon_wr[worst_mon]
            if mon_diff >= 4:
                facts.append(
                    _L(
                        f"{_MONTHS_EN[best_mon]} is historically your best month ({_fmt(mon_wr[best_mon])}% WR). "
                        f"{_MONTHS_EN[worst_mon]} is your summer slump ({_fmt(mon_wr[worst_mon])}%).",
                        f"{_MONTHS_DE[best_mon]} ist historisch euer bester Monat ({_fmt(mon_wr[best_mon])}% WR). "
                        f"{_MONTHS_DE[worst_mon]} ist euer Leistungstief ({_fmt(mon_wr[worst_mon])}%).",
                        lang,
                    )
                )

    # ── Hero obsession (player dominates with one hero) ──────────────────────
    for player in config.PLAYERS:
        hero_col = f"{player} Hero"
        if hero_col not in d.columns:
            continue
        active_p = d[d[hero_col].astype(str).apply(is_valid_hero)]
        if len(active_p) < 50:
            continue
        hc_p = active_p[hero_col].astype(str).value_counts()
        top_h_p = hc_p.index[0]
        top_pct = hc_p.iloc[0] / len(active_p) * 100
        if top_pct >= 25:
            facts.append(
                _L(
                    f"{player} has played {top_h_p} in {_fmt(top_pct)}% of all their active games "
                    f"({hc_p.iloc[0]:,} times total). Commitment.",
                    f"{player} hat {top_h_p} in {_fmt(top_pct)}% aller aktiven Spiele gespielt "
                    f"({hc_p.iloc[0]:,}-mal insgesamt). Nennen wir es Treue.",
                    lang,
                )
            )

    # ── Best hero ≠ most played hero ─────────────────────────────────────────
    for player in config.PLAYERS:
        hero_col = f"{player} Hero"
        if hero_col not in d.columns:
            continue
        active_p = d[d[hero_col].astype(str).apply(is_valid_hero)]
        if len(active_p) < 50:
            continue
        hc_p = active_p[hero_col].astype(str).value_counts()
        most_played_h = hc_p.index[0]
        eligible_h = hc_p[hc_p >= 20].index
        if len(eligible_h) < 2:
            continue
        sub_p = active_p[active_p[hero_col].astype(str).isin(eligible_h)]
        hero_wr_p = sub_p.groupby(sub_p[hero_col].astype(str))["_win"].mean() * 100
        best_h_p = hero_wr_p.idxmax()
        if (
            best_h_p != most_played_h
            and hero_wr_p[best_h_p] - hero_wr_p.get(most_played_h, 0) >= 8
        ):
            mp_wr = hero_wr_p.get(most_played_h)
            if mp_wr is not None:
                facts.append(
                    _L(
                        f"{player} mostly plays {most_played_h} ({_fmt(mp_wr)}% WR) but wins "
                        f"significantly more on {best_h_p} ({_fmt(hero_wr_p[best_h_p])}%). "
                        f"The data has spoken.",
                        f"{player} spielt meistens {most_played_h} ({_fmt(mp_wr)}% WR), gewinnt aber "
                        f"deutlich öfter mit {best_h_p} ({_fmt(hero_wr_p[best_h_p])}%). "
                        f"Die Daten haben gesprochen.",
                        lang,
                    )
                )

    # ── Recent form vs all-time ───────────────────────────────────────────────
    if "Match ID" in d.columns and total >= 100:
        sorted_recent = d.sort_values("Match ID", ascending=False)
        all_wr_rf = d["_win"].mean() * 100
        last50_wr = sorted_recent.head(50)["_win"].mean() * 100
        rf_diff = last50_wr - all_wr_rf
        if abs(rf_diff) >= 3:
            if rf_diff > 0:
                facts.append(
                    _L(
                        f"Your last 50 games: {_fmt(last50_wr)}% WR — {_fmt(rf_diff)}pp above your all-time average. "
                        f"Something is clicking right now.",
                        f"Eure letzten 50 Spiele: {_fmt(last50_wr)}% WR — {_fmt(rf_diff)} Prozentpunkte über eurem Allzeit-Schnitt. "
                        f"Gerade läuft's.",
                        lang,
                    )
                )
            else:
                facts.append(
                    _L(
                        f"Your last 50 games: {_fmt(last50_wr)}% WR — {_fmt(abs(rf_diff))}pp below your all-time average. "
                        f"Rough patch.",
                        f"Eure letzten 50 Spiele: {_fmt(last50_wr)}% WR — {_fmt(abs(rf_diff))} Prozentpunkte unter eurem Allzeit-Schnitt. "
                        f"Grade läuft's nicht.",
                        lang,
                    )
                )

    return facts


def _translate_weekday(day: str) -> str:
    mapping = {
        "Monday": "Montag",
        "Tuesday": "Dienstag",
        "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag",
        "Friday": "Freitag",
        "Saturday": "Samstag",
        "Sunday": "Sonntag",
    }
    return mapping.get(day, day)
