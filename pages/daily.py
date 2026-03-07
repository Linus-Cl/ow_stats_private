"""
pages/daily.py
==============
Callback for the Daily Report tab — the single largest callback in the app.
Renders a banner with map image, spotlight cards (hero, flex, OTP, carry),
player lineup, and a visual match timeline.
"""

from __future__ import annotations

import os
import re

import dash_bootstrap_components as dbc
import pandas as pd
from dash import Input, Output, dcc, html, no_update

import config
from data import loader
from utils.assets import get_hero_image_url, get_map_image_url
from utils.filters import is_valid_hero
from utils.formatting import (
    compose_datetime,
    format_duration_display,
    format_time_display,
    parse_duration,
    parse_time,
)
from utils.i18n import tr


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


def register_callbacks(app) -> None:  # noqa: C901 – faithful 1-to-1 migration
    """Register the daily-report callback on *app*."""

    @app.callback(
        Output("daily-summary", "children"),
        Output("daily-report-container", "children"),
        Input("tabs", "active_tab"),
        Input("lang-store", "data"),
        Input("daily-date", "date"),
        Input("server-update-token", "data"),
        prevent_initial_call=False,
    )
    def render_daily_report(active_tab, lang_data, selected_date, _token):
        lang = (lang_data or {}).get("lang", "en")
        if active_tab != "tab-daily":
            return no_update, no_update

        loader.reload()
        df = loader.get_df()
        if df.empty or "Datum" not in df.columns:
            return html.Div(tr("no_data", lang)), []

        dff = df

        # Allow test override
        _fake = os.environ.get("FAKE_TODAY")
        if _fake:
            try:
                today = pd.to_datetime(_fake, errors="raise").normalize()
            except Exception:
                today = pd.Timestamp.now().normalize()
        else:
            today = pd.Timestamp.now().normalize()

        is_fallback = False
        fallback_notice = None

        if selected_date:
            try:
                target_day = pd.to_datetime(selected_date).normalize()
            except Exception:
                target_day = today
        else:
            target_day = today

        dff_day = dff[dff["Datum"].dt.normalize() == target_day].copy()
        if dff_day.empty:
            dff_no_na = dff.dropna(subset=["Datum"]).copy()
            if not dff_no_na.empty:
                last_day = dff_no_na["Datum"].dt.normalize().max()
                target_day = last_day
                dff_day = dff[dff["Datum"].dt.normalize() == target_day].copy()
                if not selected_date:
                    is_fallback = True
                else:
                    last_day_str = (
                        target_day.strftime("%d.%m.%Y")
                        if lang == "de"
                        else target_day.strftime("%Y-%m-%d")
                    )
                    fallback_notice = html.Div(
                        f"{tr('no_games_selected', lang)} — {tr('showing_last_active', lang)}: {last_day_str}",
                        style={
                            "fontSize": "0.9em",
                            "fontWeight": 600,
                            "color": "#f3f4f6",
                            "textShadow": "0 1px 2px rgba(0,0,0,0.6)",
                            "background": "rgba(0,0,0,0.35)",
                            "padding": "4px 8px",
                            "borderRadius": "6px",
                            "display": "inline-block",
                            "marginBottom": "6px",
                        },
                    )
            else:
                return html.Div(tr("no_games_today", lang)), []

        if "Win Lose" not in dff_day.columns:
            msg = tr("required_cols_missing", lang).format(cols="Win Lose")
            return html.Div(msg), []

        wl = dff_day["Win Lose"].astype(str).str.lower().str.strip()
        dff_day["_win"] = wl.isin(["win", "victory", "sieg"])
        hero_cols = [c for c in dff_day.columns if c.endswith(" Hero")]
        role_cols = [c for c in dff_day.columns if c.endswith(" Rolle")]

        # Compose display datetime for ordering
        dff_day["_dt_show"] = dff_day.apply(compose_datetime, axis=1)

        total_games = int(len(dff_day))
        wins = int(dff_day["_win"].sum())
        losses = total_games - wins
        wr = (wins / total_games * 100.0) if total_games else 0.0

        # ── Top map ────────────────────────────────────────────────────────
        top_map = _find_top_map(dff_day, lang)
        top_map_wr = None
        if top_map:
            sub_map = dff_day[dff_day["Map"].astype(str) == str(top_map)]
            if not sub_map.empty:
                top_map_wr = float(sub_map["_win"].mean() * 100.0)

        # ── Top hero ──────────────────────────────────────────────────────
        top_hero, top_hero_wr, top_hero_games = _find_top_hero(dff_day, hero_cols)

        # ── Banner ─────────────────────────────────────────────────────────
        banner_children = []
        if top_map:
            banner_children.append(
                _build_map_banner(
                    top_map,
                    top_map_wr,
                    target_day,
                    today,
                    is_fallback,
                    fallback_notice,
                    total_games,
                    wins,
                    losses,
                    wr,
                    lang,
                )
            )
        else:
            banner_children.append(
                html.Div(
                    dbc.Alert(
                        [
                            html.H4(
                                tr("daily_report", lang),
                                className="mb-1",
                                style={"color": "#0b1320", "textShadow": "none"},
                            ),
                            html.Div(
                                f"{tr('games_today', lang)}: {total_games} • {tr('wins', lang)}: {wins} • {tr('losses', lang)}: {losses} • {tr('winrate_today', lang)}: {wr:.1f}%",
                                style={"color": "#0b1320"},
                            ),
                            fallback_notice if fallback_notice else html.Div(),
                        ],
                        color="primary",
                        className="mb-0",
                        style={"paddingRight": "140px"},
                    ),
                    style={"position": "relative"},
                )
            )

        # ── Spotlight cards ────────────────────────────────────────────────
        spotlight_cards: list = []
        if top_hero is not None:
            spotlight_cards.append(
                _hero_spotlight_card(top_hero, top_hero_wr, top_hero_games, lang)
            )

        # Per-player stats
        player_rows = _compute_player_rows(dff_day, hero_cols, lang)

        if player_rows:
            # Biggest Flex
            hero_usage = _compute_hero_usage(dff_day)
            dfu = (
                pd.DataFrame(hero_usage)
                if hero_usage
                else pd.DataFrame(
                    columns=[
                        "player",
                        "distinct",
                        "top_hero",
                        "top_hero_games",
                        "total_games",
                    ]
                )
            )

            if not dfu.empty:
                spotlight_cards.append(_biggest_flex_card(dfu, dff_day, lang))
                spotlight_cards.append(_otp_card(dfu, lang))

            # Hero-Carry
            carry_card = _hero_carry_card(dff_day, lang)
            if carry_card:
                spotlight_cards.append(carry_card)

        # ── Player lineup ──────────────────────────────────────────────────
        lineup_cards = _build_lineup_cards(player_rows, lang)

        # ── Timeline ───────────────────────────────────────────────────────
        timeline = _build_timeline(dff_day, target_day, today, lang)

        # ── Assemble ───────────────────────────────────────────────────────
        summary = banner_children[0]
        content = [
            (
                dbc.Row(spotlight_cards, className="mt-3 g-3")
                if spotlight_cards
                else html.Div()
            ),
            html.H4(tr("lineup_today", lang), className="mt-4 mb-2"),
            (
                dbc.Row(lineup_cards, className="g-3")
                if lineup_cards
                else dbc.Alert(tr("no_data", lang), color="secondary")
            ),
            html.Div(
                [
                    html.H4(tr("timeline_today", lang), className="mb-2 me-2"),
                    html.Small(tr("newest_first", lang), className="text-muted"),
                ],
                className="d-flex align-items-baseline mt-4",
            ),
            timeline,
        ]
        return summary, content


# ---------------------------------------------------------------------------
# Private helpers (extracted for readability, not complexity reduction)
# ---------------------------------------------------------------------------


def _find_top_map(dff_day, lang):
    if "Map" not in dff_day.columns or dff_day.empty:
        return None
    counts = dff_day["Map"].astype(str).value_counts()
    if counts.empty:
        return None
    max_plays = counts.max()
    contenders = [m for m, c in counts.items() if c == max_plays]
    if len(contenders) == 1:
        return contenders[0]
    best, best_wr = None, -1.0
    for m in contenders:
        sub = dff_day[dff_day["Map"].astype(str) == str(m)]
        wr_m = float(sub["_win"].mean() * 100.0) if not sub.empty else 0.0
        if wr_m > best_wr:
            best, best_wr = m, wr_m
    return best


def _find_top_hero(dff_day, hero_cols):
    if not hero_cols:
        return None, None, None
    all_h = pd.concat([dff_day[c].astype(str) for c in hero_cols], ignore_index=True)
    all_h = all_h[all_h.map(is_valid_hero)]
    if all_h.empty:
        return None, None, None
    top = all_h.value_counts().idxmax()
    mask_any = None
    top_l = str(top).strip().lower()
    for c in hero_cols:
        m = dff_day[c].astype(str).str.strip().str.lower() == top_l
        mask_any = (mask_any | m) if mask_any is not None else m
    sub = dff_day[mask_any] if mask_any is not None else dff_day.iloc[0:0]
    hero_wr = float(sub["_win"].mean() * 100.0) if not sub.empty else None
    hero_games = int(mask_any.sum()) if mask_any is not None else None
    return top, hero_wr, hero_games


def _build_map_banner(
    top_map,
    top_map_wr,
    target_day,
    today,
    is_fallback,
    fallback_notice,
    total_games,
    wins,
    losses,
    wr,
    lang,
):
    return html.Div(
        [
            html.Div(
                [
                    (
                        html.Div(
                            dbc.Badge(tr("last_active_day", lang), color="warning"),
                            className="mb-2",
                        )
                        if is_fallback
                        else html.Div()
                    ),
                    (fallback_notice if fallback_notice else html.Div()),
                    html.H3(
                        (
                            tr("today_summary", lang)
                            if target_day == today
                            else (
                                target_day.strftime("%d.%m.%Y")
                                if lang == "de"
                                else target_day.strftime("%Y-%m-%d")
                            )
                        ),
                        className="mb-1",
                    ),
                    html.H1(
                        f"{wins}-{losses}  •  {wr:.1f}% "
                        + (
                            tr("winrate_today", lang)
                            if target_day == today
                            else tr("winrate", lang)
                        ),
                        className="mb-2",
                    ),
                    html.Div(
                        f"{(tr('games_today', lang) if target_day == today else tr('games', lang))}: {total_games}",
                        style={
                            "fontSize": "1.05em",
                            "fontWeight": 700,
                            "color": "#f3f4f6",
                            "textShadow": "0 1px 2px rgba(0,0,0,0.6)",
                            "background": "rgba(0,0,0,0.35)",
                            "padding": "4px 8px",
                            "borderRadius": "6px",
                            "display": "inline-block",
                        },
                    ),
                ],
                style={
                    "position": "relative",
                    "zIndex": 2,
                    "color": "#f9fafb",
                    "textShadow": "0 1px 2px rgba(0,0,0,0.6)",
                },
            ),
            # Dark overlay
            html.Div(
                style={
                    "position": "absolute",
                    "inset": 0,
                    "background": "linear-gradient(180deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.55) 100%)",
                    "zIndex": 1,
                }
            ),
            # Map pill
            html.Div(
                [
                    html.Span(
                        f"{tr('map_of_the_day', lang)}: {top_map}",
                        style={"fontWeight": 700},
                    ),
                    html.Span(
                        (
                            f"  •  {tr('winrate', lang)}: {top_map_wr:.1f}%"
                            if top_map_wr is not None
                            else ""
                        ),
                        className="text-muted",
                        style={"marginLeft": "6px"},
                    ),
                ],
                style={
                    "position": "absolute",
                    "right": "12px",
                    "bottom": "12px",
                    "zIndex": 3,
                    "background": "rgba(0,0,0,0.55)",
                    "backdropFilter": "blur(4px)",
                    "color": "#e5e7eb",
                    "padding": "6px 10px",
                    "borderRadius": "8px",
                    "boxShadow": "0 4px 12px rgba(0,0,0,0.35)",
                    "fontSize": "0.95em",
                },
            ),
        ],
        style={
            "position": "relative",
            "padding": "24px",
            "borderRadius": "10px",
            "overflow": "hidden",
            "backgroundImage": f"url('{get_map_image_url(top_map)}')",
            "backgroundSize": "cover",
            "backgroundPosition": "center",
            "minHeight": "220px",
            "display": "flex",
            "alignItems": "flex-end",
            "boxShadow": "0 8px 24px rgba(0,0,0,0.35)",
        },
    )


def _hero_spotlight_card(top_hero, top_hero_wr, top_hero_games, lang):
    parts = [
        p
        for p in [
            (
                f"{tr('winrate', lang)}: {top_hero_wr:.1f}%"
                if top_hero_wr is not None
                else None
            ),
            (
                f"{tr('games', lang)}: {top_hero_games}"
                if top_hero_games is not None
                else None
            ),
        ]
        if p
    ]
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardHeader(tr("most_played_hero", lang)),
                dbc.CardBody(
                    html.Div(
                        [
                            html.Img(
                                src=get_hero_image_url(top_hero),
                                style={
                                    "width": "64px",
                                    "height": "64px",
                                    "objectFit": "cover",
                                    "borderRadius": "50%",
                                    "marginRight": "12px",
                                },
                            ),
                            html.Div(
                                [
                                    html.H5(str(top_hero), className="mb-1"),
                                    html.Small(
                                        " • ".join(parts), className="text-muted"
                                    ),
                                ]
                            ),
                        ],
                        className="d-flex align-items-center",
                    )
                ),
            ],
            className="flex-fill h-100",
        ),
        md=3,
        className="d-flex",
    )


def _compute_player_rows(dff_day, hero_cols, lang):
    rows = []
    for p in config.PLAYERS:
        role_col = f"{p} Rolle"
        if role_col not in dff_day.columns:
            continue
        mask_p = (
            dff_day[role_col].astype(str).str.strip().str.lower() != "nicht dabei"
        ) & dff_day[role_col].notna()
        if not mask_p.any():
            continue
        sub = dff_day[mask_p]
        games_p = int(len(sub))
        wins_p = int(sub["_win"].sum())
        wr_p = float(sub["_win"].mean() * 100.0) if games_p else 0.0
        roles_p = sorted(
            {
                r
                for r in sub[role_col].dropna().astype(str).str.strip()
                if r and r.lower() != "nicht dabei"
            }
        )

        role_wr_map: dict = {}
        if roles_p:
            rs = sub[role_col].dropna().astype(str).str.strip()
            rs = rs[rs.str.lower() != "nicht dabei"]
            for rn in sorted(set(rs)):
                sr = sub[rs == rn]
                if sr.empty:
                    continue
                gr = int(len(sr))
                wr_r = float(sr["_win"].mean() * 100.0)
                role_wr_map[str(rn)] = {
                    "wr": wr_r,
                    "games": gr,
                    "wins": int(sr["_win"].sum()),
                    "losses": gr - int(sr["_win"].sum()),
                }

        hero_col = f"{p} Hero"
        top_hero_p = None
        if hero_col in sub.columns:
            h = sub[hero_col].dropna().astype(str)
            h = h[h.map(is_valid_hero)]
            if not h.empty:
                top_hero_p = h.value_counts().idxmax()

        rows.append(
            {
                "player": p,
                "games": games_p,
                "wins": wins_p,
                "losses": games_p - wins_p,
                "wr": wr_p,
                "roles": roles_p,
                "role_wr": role_wr_map,
                "top_hero": top_hero_p,
            }
        )
    return rows


def _compute_hero_usage(dff_day):
    usage = []
    for p in config.PLAYERS:
        rc, hc = f"{p} Rolle", f"{p} Hero"
        if rc in dff_day.columns and hc in dff_day.columns:
            subp = dff_day[
                (dff_day[rc].astype(str).str.strip().str.lower() != "nicht dabei")
                & dff_day[hc].notna()
            ]
            heroes = subp[hc].astype(str).str.strip()
            heroes = heroes[heroes.map(is_valid_hero)]
            if not heroes.empty:
                counts = heroes.value_counts()
                usage.append(
                    {
                        "player": p,
                        "distinct": int(counts.shape[0]),
                        "top_hero": counts.idxmax(),
                        "top_hero_games": int(counts.max()),
                        "total_games": int(counts.sum()),
                    }
                )
    return usage


def _biggest_flex_card(dfu, dff_day, lang):
    flex_row = dfu.sort_values(
        ["distinct", "total_games"], ascending=[False, False]
    ).iloc[0]
    fp = flex_row["player"]
    rc, hc = f"{fp} Rolle", f"{fp} Hero"
    top3 = []
    if rc in dff_day.columns and hc in dff_day.columns:
        sp = dff_day[
            (dff_day[rc].astype(str).str.strip().str.lower() != "nicht dabei")
            & dff_day[hc].notna()
        ]
        if not sp.empty:
            vc = (
                sp[hc]
                .astype(str)
                .str.strip()
                .pipe(lambda s: s[s.map(is_valid_hero)])
                .value_counts()
            )
            top3 = list(vc.index[:3])
    avatars = []
    for i, h in enumerate(top3 or []):
        avatars.append(
            html.Img(
                src=get_hero_image_url(h),
                title=str(h),
                style={
                    "width": "42px",
                    "height": "42px",
                    "borderRadius": "50%",
                    "objectFit": "cover",
                    "border": "2px solid rgba(255,255,255,0.85)",
                    "boxShadow": "0 1px 4px rgba(0,0,0,0.35)",
                    "marginLeft": "-10px" if i > 0 else "0",
                },
            )
        )
    if not avatars:
        avatars = [
            html.Img(
                src="/assets/heroes/default_hero.png",
                style={
                    "width": "42px",
                    "height": "42px",
                    "borderRadius": "50%",
                    "objectFit": "cover",
                    "border": "2px solid rgba(255,255,255,0.85)",
                },
            )
        ]
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardHeader(tr("biggest_flex", lang)),
                dbc.CardBody(
                    html.Div(
                        [
                            html.Div(
                                avatars, className="d-flex align-items-center me-3"
                            ),
                            html.Div(
                                [
                                    html.H5(str(fp), className="mb-1"),
                                    html.Small(
                                        f"{tr('games', lang)}: {int(flex_row['total_games'])} • {tr('distinct_heroes', lang)}: {int(flex_row['distinct'])}",
                                        className="text-muted",
                                    ),
                                ]
                            ),
                        ],
                        className="d-flex align-items-center",
                    )
                ),
            ],
            className="flex-fill h-100",
        ),
        md=3,
        className="d-flex",
    )


def _otp_card(dfu, lang):
    otp = dfu.sort_values(
        ["top_hero_games", "total_games"], ascending=[False, False]
    ).iloc[0]
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardHeader(tr("one_trick_pony", lang)),
                dbc.CardBody(
                    html.Div(
                        [
                            html.Img(
                                src=get_hero_image_url(otp["top_hero"]),
                                style={
                                    "width": "64px",
                                    "height": "64px",
                                    "objectFit": "cover",
                                    "borderRadius": "50%",
                                    "marginRight": "12px",
                                },
                            ),
                            html.Div(
                                [
                                    html.H5(
                                        f"{otp['player']} – {otp['top_hero']}",
                                        className="mb-1",
                                    ),
                                    html.Small(
                                        f"{tr('games', lang)}: {int(otp['top_hero_games'])}",
                                        className="text-muted",
                                    ),
                                ]
                            ),
                        ],
                        className="d-flex align-items-center",
                    )
                ),
            ],
            className="flex-fill h-100",
        ),
        md=3,
        className="d-flex",
    )


def _hero_carry_card(dff_day, lang):
    best_combo, best_wr, best_games, best_player, best_hero = None, -1.0, 0, None, None
    for p in config.PLAYERS:
        rc, hc = f"{p} Rolle", f"{p} Hero"
        if rc not in dff_day.columns or hc not in dff_day.columns:
            continue
        subp = dff_day[
            (dff_day[rc].astype(str).str.strip().str.lower() != "nicht dabei")
            & dff_day[hc].notna()
        ]
        if subp.empty:
            continue
        for hero, grp in subp.groupby(subp[hc].astype(str).str.strip()):
            if not is_valid_hero(hero):
                continue
            gn = int(len(grp))
            wrv = float(grp["_win"].mean() * 100.0) if gn else 0.0
            prefer = gn >= 2
            if best_combo is None:
                best_combo, best_wr, best_games, best_player, best_hero = (
                    prefer,
                    wrv,
                    gn,
                    p,
                    hero,
                )
            elif prefer and not best_combo:
                best_combo, best_wr, best_games, best_player, best_hero = (
                    True,
                    wrv,
                    gn,
                    p,
                    hero,
                )
            elif prefer == best_combo and (
                wrv > best_wr or (wrv == best_wr and gn > best_games)
            ):
                best_wr, best_games, best_player, best_hero = wrv, gn, p, hero
    if not best_player or not best_hero:
        return None
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardHeader(f"{best_hero}-Carry"),
                dbc.CardBody(
                    html.Div(
                        [
                            html.Img(
                                src=get_hero_image_url(best_hero),
                                style={
                                    "width": "64px",
                                    "height": "64px",
                                    "objectFit": "cover",
                                    "borderRadius": "50%",
                                    "marginRight": "12px",
                                },
                            ),
                            html.Div(
                                [
                                    html.H5(
                                        f"{best_player} – {best_hero}", className="mb-1"
                                    ),
                                    html.Small(
                                        f"{tr('games', lang)}: {best_games} • {tr('winrate', lang)}: {best_wr:.1f}%",
                                        className="text-muted",
                                    ),
                                ]
                            ),
                        ],
                        className="d-flex align-items-center",
                    )
                ),
            ],
            className="flex-fill h-100",
        ),
        md=3,
        className="d-flex",
    )


def _build_lineup_cards(player_rows, lang):
    role_color = {"Tank": "warning", "Damage": "danger", "Support": "success"}
    cards = []
    for r in player_rows:
        badges = []
        role_wr = r.get("role_wr") or {}
        if role_wr:
            for role in sorted(role_wr):
                st = role_wr[role]
                label = f"{role} {st['wr']:.0f}%"
                safe_id = re.sub(
                    r"[^a-z0-9_-]", "-", f"rb-{r['player']}-{role}".lower()
                )
                badges.append(
                    dbc.Badge(
                        label,
                        id=safe_id,
                        color=role_color.get(role, "secondary"),
                        className="role-badge me-1",
                        pill=True,
                    )
                )
                if st.get("games") is not None:
                    badges.append(
                        dbc.Tooltip(
                            f"{tr('games', lang)}: {st['games']} • {st['wins']}-{st['losses']}",
                            target=safe_id,
                            placement="top",
                            delay={"show": 150, "hide": 50},
                        )
                    )
        else:
            badges = [
                dbc.Badge(
                    role,
                    color=role_color.get(role, "secondary"),
                    className="role-badge me-1",
                )
                for role in r["roles"]
            ]

        cards.append(
            dbc.Col(
                dbc.Card(
                    dbc.CardBody(
                        html.Div(
                            [
                                html.Img(
                                    src=(
                                        get_hero_image_url(r["top_hero"])
                                        if r.get("top_hero")
                                        else "/assets/heroes/default_hero.png"
                                    ),
                                    style={
                                        "width": "54px",
                                        "height": "54px",
                                        "borderRadius": "50%",
                                        "objectFit": "cover",
                                        "marginRight": "12px",
                                    },
                                ),
                                html.Div(
                                    [
                                        html.Div(html.Strong(r["player"])),
                                        html.Div(badges, className="mb-1"),
                                        html.Small(
                                            f"{tr('games', lang)}: {r['games']} • {r['wins']}-{r['losses']} • {tr('winrate', lang)} {r['wr']:.1f}%",
                                            className="text-muted",
                                        ),
                                    ]
                                ),
                            ],
                            className="d-flex align-items-center",
                        )
                    )
                ),
                md=4,
            )
        )
    return cards


def _build_timeline(dff_day, target_day, today, lang):
    """Build the horizontal match-timeline strip."""
    # Sort newest first
    dff_day = dff_day.copy()
    dff_day["_dt_sort"] = dff_day["_dt_show"]
    if "Datum" in dff_day.columns:
        na_mask = dff_day["_dt_sort"].isna()
        dff_day.loc[na_mask, "_dt_sort"] = dff_day.loc[na_mask, "Datum"]
    dff_day["_dt_has"] = dff_day["_dt_sort"].notna().astype(int)
    sort_cols = ["_dt_has", "_dt_sort"]
    asc = [False, False]
    if "Match ID" in dff_day.columns:
        sort_cols.append("Match ID")
        asc.append(False)
    dff_sorted = dff_day.sort_values(sort_cols, ascending=asc)

    try:
        show_time = bool(target_day >= today)
    except Exception:
        show_time = False

    tiles = []
    records = dff_sorted.to_dict(orient="records")
    for idx, game in enumerate(records):
        map_name = str(game.get("Map", tr("unknown_map", lang)))
        _mid = game.get("Match ID")
        victory = bool(game.get("_win"))
        img_src = get_map_image_url(map_name)
        border_col = "#16a34a" if victory else "#dc2626"

        time_str = parse_time(game)
        dur_str = parse_duration(game)
        time_disp = format_time_display(time_str, lang) if show_time else ""
        dur_disp = format_duration_display(dur_str)

        tile = html.Div(
            [
                html.Div(
                    html.Div(
                        [
                            html.Img(
                                src=img_src,
                                style={
                                    "width": "100%",
                                    "height": "100%",
                                    "objectFit": "cover",
                                    "display": "block",
                                },
                                title=(
                                    f"{map_name} • "
                                    + (
                                        tr("victory", lang)
                                        if victory
                                        else tr("defeat", lang)
                                    )
                                    + (f" • {time_disp}" if time_disp else "")
                                    + (f" • {dur_disp}" if dur_disp else "")
                                ),
                            ),
                            (
                                html.Div(
                                    time_disp,
                                    style={
                                        "position": "absolute",
                                        "top": "4px",
                                        "left": "4px",
                                        "background": "rgba(0,0,0,0.6)",
                                        "color": "#e5e7eb",
                                        "fontSize": "0.70rem",
                                        "padding": "2px 6px",
                                        "borderRadius": "6px",
                                        "lineHeight": "1",
                                    },
                                )
                                if time_disp
                                else html.Div()
                            ),
                        ],
                        style={
                            "position": "relative",
                            "width": "100%",
                            "height": "100%",
                        },
                    ),
                    style={
                        "width": "84px",
                        "height": "56px",
                        "border": f"2px solid {border_col}",
                        "borderRadius": "8px",
                        "overflow": "hidden",
                        "boxShadow": "0 1px 6px rgba(0,0,0,0.3)",
                        "position": "relative",
                    },
                ),
                html.Div(
                    [
                        html.Div(
                            map_name,
                            className="text-muted",
                            style={
                                "fontSize": "0.75rem",
                                "textAlign": "center",
                                "marginTop": "4px",
                                "maxWidth": "84px",
                                "whiteSpace": "nowrap",
                                "overflow": "hidden",
                                "textOverflow": "ellipsis",
                            },
                        ),
                        (
                            html.Div(
                                dur_disp,
                                className="text-muted",
                                style={
                                    "fontSize": "0.68rem",
                                    "textAlign": "center",
                                    "marginTop": "2px",
                                    "maxWidth": "84px",
                                    "whiteSpace": "nowrap",
                                    "overflow": "hidden",
                                    "textOverflow": "ellipsis",
                                },
                            )
                            if dur_disp
                            else html.Div()
                        ),
                    ]
                ),
            ],
            id={
                "type": "timeline-tile",
                "matchId": int(_mid) if pd.notna(_mid) else -1,
            },
            n_clicks=0,
            style={"flex": "0 0 auto", "cursor": "pointer"},
        )

        tiles.append(tile)
        if idx < len(records) - 1:
            tiles.append(
                html.Div(
                    style={
                        "width": 0,
                        "height": 0,
                        "borderTop": "6px solid transparent",
                        "borderBottom": "6px solid transparent",
                        "borderRight": "8px solid rgba(156,163,175,0.7)",
                        "marginTop": "25px",
                        "flex": "0 0 auto",
                    }
                )
            )

    return html.Div(
        tiles,
        style={
            "display": "flex",
            "alignItems": "flex-start",
            "gap": "8px",
            "flexWrap": "wrap",
            "padding": "6px 2px",
        },
    )
