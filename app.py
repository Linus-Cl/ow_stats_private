"""Dash Overwatch Stats App"""

# Standard library
import os
import re
from io import StringIO, BytesIO
import hashlib
import json
import subprocess
import html as html_std

# Third-party
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate
import uuid
import sqlite3
import time
import threading
from flask import request

# --- Local Imports ---
import constants


# --- App Initialization ---
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
)
server = app.server
df = pd.DataFrame()
# In-Memory cache markers for conditional downloads
_last_etag = None
_last_modified = None
_last_hash = None
LIGHT_LOGO_SRC = None
DARK_LOGO_SRC = None
DARK_LOGO_INVERT = True


@server.route("/bye", methods=["POST"])
def bye():
    try:
        payload = request.get_json(silent=True) or {}
        sid = payload.get("session_id")
        if sid:
            conn = sqlite3.connect(ACTIVE_DB)
            try:
                cur = conn.cursor()
                cur.execute("DELETE FROM active_sessions WHERE session_id = ?", (sid,))
                conn.commit()
            finally:
                conn.close()
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}, 500


# --- Active sessions (live online counter) ---
ACTIVE_DB = os.path.join(os.path.dirname(__file__), "active_sessions.db")


def _init_active_db():
    try:
        conn = sqlite3.connect(ACTIVE_DB)
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS active_sessions (
                session_id TEXT PRIMARY KEY,
                last_seen INTEGER
            )
            """
        )
        # Shared app state (for cross-worker tokens)
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


# --- Daily Report ---
@app.callback(
    Output("daily-summary", "children"),
    Output("daily-report-container", "children"),
    Input("tabs", "active_tab"),
    Input("lang-store", "data"),
    Input("daily-date", "date"),
    prevent_initial_call=False,
)
def render_daily_report(active_tab, lang_data, selected_date):
    lang = (lang_data or {}).get("lang", "en")
    if active_tab != "tab-daily":
        return no_update, no_update
    if df.empty or "Datum" not in df.columns:
        return html.Div(tr("no_data", lang)), []

    # Filter to target day (today by default, or selected date if provided; else auto-fallback to last active)
    dff = df.copy()
    dff["Datum"] = pd.to_datetime(dff["Datum"], errors="coerce")
    # Allow test override of 'today' via env var FAKE_TODAY=YYYY-MM-DD
    _fake = os.environ.get("FAKE_TODAY")
    if _fake:
        try:
            today = pd.to_datetime(_fake, errors="raise").normalize()
        except Exception:
            today = pd.Timestamp.now().normalize()
    else:
        today = pd.Timestamp.now().normalize()
    # Track whether we auto-fell back to the most recent active day
    is_fallback = False
    fallback_notice = None
    selected_date_dt = None
    # If a date is selected, prefer it
    if selected_date:
        try:
            selected_date_dt = pd.to_datetime(selected_date).normalize()
            target_day = selected_date_dt
        except Exception:
            target_day = today
    else:
        target_day = today
    dff_day = dff[(dff["Datum"].dt.normalize() == target_day)].copy()
    if dff_day.empty:
        # Auto-fallback to the most recent day with matches
        dff_no_na = dff.dropna(subset=["Datum"]).copy()
        if not dff_no_na.empty:
            last_day = dff_no_na["Datum"].dt.normalize().max()
            target_day = last_day
            dff_day = dff[(dff["Datum"].dt.normalize() == target_day)].copy()
            # If user didn't select a date, it's a silent fallback; if they did, show a notice
            if not selected_date:
                is_fallback = True
            else:
                # Build a concise notice line about the fallback
                last_day_str = target_day.strftime("%d.%m.%Y") if lang == "de" else target_day.strftime("%Y-%m-%d")
                fallback_notice = html.Div(
                    f"{tr('no_games_selected', lang) if tr('no_games_selected', lang) != 'no_games_selected' else 'No games on selected day'} — "
                    + f"{tr('showing_last_active', lang) if tr('showing_last_active', lang) != 'showing_last_active' else 'Showing last active day'}: {last_day_str}",
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

    # Normalize outcome and bench markers
    if "Win Lose" not in dff_day.columns:
        # Required column missing for daily report
        msg = tr("required_cols_missing", lang).format(cols="Win Lose") if tr("required_cols_missing", lang) != "required_cols_missing" else "Required columns are missing: Win Lose"
        return html.Div(msg), []
    wl = dff_day["Win Lose"].astype(str).str.lower().str.strip()
    dff_day["_win"] = wl.isin(["win", "victory", "sieg"])  # boolean
    hero_cols = [c for c in dff_day.columns if c.endswith(" Hero")]
    role_cols = [c for c in dff_day.columns if c.endswith(" Rolle")]

    # Remove bench marker in hero aggregations
    def _is_valid_hero(x: str) -> bool:
        s = str(x).strip().lower()
        return bool(s) and s not in ("nicht dabei", "none", "nan")

    # Helper: robust time extraction (row-wise)
    time_candidates = ["Uhrzeit", "Zeit", "Time", "Startzeit"]

    def _extract_time_str(row) -> str:
        dt = row.get("Datum")
        if pd.notna(dt) and isinstance(dt, pd.Timestamp):
            if dt.hour or dt.minute or dt.second:
                return dt.strftime("%H:%M")
        for name in time_candidates:
            if name in row.index:
                v = row[name]
                if pd.isna(v):
                    continue
                # Excel numeric time (fraction of day)
                if isinstance(v, (int, float)):
                    try:
                        frac = float(v)
                        # keep only fractional part
                        frac = frac % 1.0
                        secs = int(round(frac * 86400))
                        h = secs // 3600
                        m = (secs % 3600) // 60
                        if 0 <= h < 24 and 0 <= m < 60:
                            return f"{h:02d}:{m:02d}"
                    except Exception:
                        pass
                # String forms like 9:30, 0930, 09:30
                s = str(v).strip()
                m = re.match(r"^(\d{1,2}):(\d{2})", s)
                if m:
                    hh = int(m.group(1))
                    mm = int(m.group(2))
                    if 0 <= hh < 24 and 0 <= mm < 60:
                        return f"{hh:02d}:{mm:02d}"
                if re.fullmatch(r"\d{3,4}", s):
                    s2 = s.zfill(4)
                    hh = int(s2[:2])
                    mm = int(s2[2:])
                    if 0 <= hh < 24 and 0 <= mm < 60:
                        return f"{hh:02d}:{mm:02d}"
        return "--:--"

    def _compose_dt(row) -> pd.Timestamp | None:
        base = row.get("Datum")
        if pd.notna(base) and isinstance(base, pd.Timestamp):
            if base.hour or base.minute or base.second:
                return base
        tstr = _extract_time_str(row)
        if tstr != "--:--" and pd.notna(row.get("Datum")) and isinstance(row.get("Datum"), pd.Timestamp):
            try:
                h, m = tstr.split(":")
                return pd.Timestamp(year=row["Datum"].year, month=row["Datum"].month, day=row["Datum"].day, hour=int(h), minute=int(m))
            except Exception:
                return row.get("Datum") if isinstance(row.get("Datum"), pd.Timestamp) else None
        return row.get("Datum") if isinstance(row.get("Datum"), pd.Timestamp) else None

    # Compose display datetime for ordering and first/last detection
    dff_day["_dt_show"] = dff_day.apply(_compose_dt, axis=1)

    # Key totals
    total_games = int(len(dff_day))
    wins = int(dff_day["_win"].sum())
    losses = total_games - wins
    wr = (wins / total_games * 100.0) if total_games else 0.0
    # Time display removed: skip computing per-match times

    # Top map and top hero of the day
    top_map = None
    top_map_wr = None
    if "Map" in dff_day.columns:
        top_map = dff_day["Map"].astype(str).value_counts().idxmax()
        sub_map = dff_day[dff_day["Map"].astype(str) == str(top_map)]
        if not sub_map.empty:
            top_map_wr = float(sub_map["_win"].mean() * 100.0)

    top_hero = None
    top_hero_wr = None
    top_hero_games = None
    if hero_cols:
        all_heroes = []
        for c in hero_cols:
            all_heroes.append(dff_day[c].astype(str))
        heroes_series = pd.concat(all_heroes, ignore_index=True)
        heroes_series = heroes_series[heroes_series.map(_is_valid_hero)]
        if not heroes_series.empty:
            top_hero = heroes_series.value_counts().idxmax()
            # Any match where any player played that hero counts once
            mask_any = None
            top_hero_l = str(top_hero).strip().lower()
            for c in hero_cols:
                m = dff_day[c].astype(str).str.strip().str.lower() == top_hero_l
                mask_any = (mask_any | m) if mask_any is not None else m
            sub_hero = dff_day[mask_any] if mask_any is not None else dff_day.iloc[0:0]
            if not sub_hero.empty:
                top_hero_wr = float(sub_hero["_win"].mean() * 100.0)
                top_hero_games = int(mask_any.sum())

    # Summary banner with big visual
    banner_children = []
    if top_map:
        banner_children.append(
            html.Div(
                [
                    html.Div(
                        [
                            (html.Div(
                                dbc.Badge(tr("last_active_day", lang), color="warning"),
                                className="mb-2",
                            ) if is_fallback else html.Div()),
                            (fallback_notice if fallback_notice is not None else html.Div()),
                            html.H3(
                                tr("today_summary", lang)
                                if target_day == today
                                else (target_day.strftime("%d.%m.%Y") if lang == "de" else target_day.strftime("%Y-%m-%d")),
                                className="mb-1",
                            ),
                            html.H1(
                                f"{wins}-{losses}  •  {wr:.1f}% " + (
                                    tr('winrate_today', lang) if target_day == today else tr('winrate', lang)
                                ),
                                className="mb-2",
                            ),
                            html.Div(
                                f"{(tr('games_today', lang) if target_day == today else tr('games', lang))}: {total_games}",
                                className="",
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
                            # Improve readability on bright images (light mode)
                            "color": "#f9fafb",
                            "textShadow": "0 1px 2px rgba(0,0,0,0.6)",
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
        )
        # dark overlay
        banner_children[-1].children.append(
            html.Div(
                style={
                    "position": "absolute",
                    "inset": 0,
                    "background": "linear-gradient(180deg, rgba(0,0,0,0.05) 0%, rgba(0,0,0,0.55) 100%)",
                    "zIndex": 1,
                }
            )
        )
        # map of the day pill (bottom-right)
        banner_children[-1].children.append(
            html.Div(
                [
                    html.Span(
                        f"{tr('map_of_the_day', lang)}: {top_map}",
                        style={"fontWeight": 700},
                    ),
                    html.Span(
                        f"  •  {tr('winrate', lang)}: {top_map_wr:.1f}%" if top_map_wr is not None else "",
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
            )
        )
    else:
    # Fallback banner with date picker on top-right
        banner_children.append(
            html.Div(
                [
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
                            (fallback_notice if fallback_notice is not None else html.Div()),
                        ],
                        color="primary",
                        className="mb-0",
                        style={"paddingRight": "140px"},  # space for picker
                    ),
                ],
                style={"position": "relative"},
            )
        )

    # Spotlight cards: Map of the day, Hero spotlight, MVP, Workhorse
    spotlight_cards = []
    # Map of the day card removed (now displayed in banner)
    if top_hero is not None:
        spotlight_cards.append(
            dbc.Col(
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
                                                " • ".join(
                                                    [
                                                        part
                                                        for part in [
                                                            (f"{tr('winrate', lang)}: {top_hero_wr:.1f}%" if top_hero_wr is not None else None),
                                                            (f"{tr('games', lang)}: {top_hero_games}" if top_hero_games is not None else None),
                                                        ]
                                                        if part
                                                    ]
                                                ),
                                                className="text-muted",
                                            ),
                                        ]
                                    ),
                                ],
                                className="d-flex align-items-center",
                            )
                        ),
                    ]
                , className="flex-fill h-100"),
                md=3,
                className="d-flex",
            )
        )

    # Per-player today stats for MVP/Workhorse and lineup
    player_rows = []
    for p in constants.players:
        # player participated today if their own role column exists and is not 'nicht dabei'
        role_col_name = f"{p} Rolle"
        if role_col_name not in dff_day.columns:
            continue
        mask_p = dff_day[role_col_name].astype(str).str.strip().str.lower() != "nicht dabei"
        mask_p = mask_p & dff_day[role_col_name].notna()
        if not mask_p.any():
            continue
        sub = dff_day[mask_p]
        games_p = int(len(sub))
        wins_p = int(sub["_win"].sum())
        losses_p = games_p - wins_p
        wr_p = float(sub["_win"].mean() * 100.0) if games_p else 0.0
        # roles played
        roles_p = sub[role_col_name].dropna().astype(str).str.strip().tolist()
        roles_p = sorted({r for r in roles_p if r and r.lower() != "nicht dabei"})
        # top hero for this player
        hero_col_name = f"{p} Hero"
        top_hero_p = None
        if hero_col_name in sub.columns:
            h = sub[hero_col_name].dropna().astype(str)
            h = h[h.map(_is_valid_hero)]
            if not h.empty:
                top_hero_p = h.value_counts().idxmax()
        player_rows.append({
            "player": p,
            "games": games_p,
            "wins": wins_p,
            "losses": losses_p,
            "wr": wr_p,
            "roles": roles_p,
            "top_hero": top_hero_p,
        })

    # Biggest Flex, One Trick Pony, and Hero-Carry
    if player_rows:
        dfp = pd.DataFrame(player_rows)
        # Compute per-player hero usage counts within the day
        hero_usage = []
        for p in constants.players:
            role_col = f"{p} Rolle"
            hero_col = f"{p} Hero"
            if role_col in dff_day.columns and hero_col in dff_day.columns:
                subp = dff_day[(dff_day[role_col].astype(str).str.strip().str.lower() != "nicht dabei") & dff_day[hero_col].notna()]
                heroes = subp[hero_col].astype(str).str.strip()
                heroes = heroes[heroes.map(_is_valid_hero)]
                if not heroes.empty:
                    counts = heroes.value_counts()
                    hero_usage.append({
                        "player": p,
                        "distinct": int(counts.shape[0]),
                        "top_hero": counts.idxmax(),
                        "top_hero_games": int(counts.max()),
                        "total_games": int(counts.sum()),
                    })
        dfu = pd.DataFrame(hero_usage) if hero_usage else pd.DataFrame(columns=["player","distinct","top_hero","top_hero_games","total_games"]) 

        # Biggest Flex: most distinct heroes
        if not dfu.empty:
            flex_row = dfu.sort_values(["distinct","total_games"], ascending=[False, False]).iloc[0]
            # Compute up to 3 most-played heroes for the flex player to show as a compact image stack
            _flex_player = flex_row["player"]
            _role_col = f"{_flex_player} Rolle"
            _hero_col = f"{_flex_player} Hero"
            top3_heroes = []
            if _role_col in dff_day.columns and _hero_col in dff_day.columns:
                _subp = dff_day[(dff_day[_role_col].astype(str).str.strip().str.lower() != "nicht dabei") & dff_day[_hero_col].notna()]
                if not _subp.empty:
                    vc = (
                        _subp[_hero_col]
                        .astype(str)
                        .str.strip()
                        .pipe(lambda s: s[s.map(_is_valid_hero)])
                        .value_counts()
                    )
                    top3_heroes = list(vc.index[:3])
            # Build overlapping image avatars (fallback to default if none)
            avatar_imgs = []
            if top3_heroes:
                for i, h in enumerate(top3_heroes):
                    avatar_imgs.append(
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
                                "marginLeft": ("-10px" if i > 0 else "0"),
                            },
                        )
                    )
            else:
                avatar_imgs.append(
                    html.Img(
                        src="/assets/heroes/default_hero.png",
                        style={
                            "width": "42px",
                            "height": "42px",
                            "borderRadius": "50%",
                            "objectFit": "cover",
                            "border": "2px solid rgba(255,255,255,0.85)",
                            "boxShadow": "0 1px 4px rgba(0,0,0,0.35)",
                        },
                    )
                )
            spotlight_cards.append(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(tr("biggest_flex", lang) if tr("biggest_flex", lang) != "biggest_flex" else "Biggest Flex"),
                            dbc.CardBody(
                                html.Div(
                                    [
                                        html.Div(avatar_imgs, className="d-flex align-items-center me-3"),
                                        html.Div(
                                            [
                                                html.H5(str(flex_row["player"]), className="mb-1"),
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
                        ]
                    , className="flex-fill h-100"),
                    md=3,
                    className="d-flex",
                )
            )

        # One Trick Pony: max games on a single hero
        if not dfu.empty:
            otp_row = dfu.sort_values(["top_hero_games","total_games"], ascending=[False, False]).iloc[0]
            otp_title = tr("one_trick_pony", lang) if tr("one_trick_pony", lang) != "one_trick_pony" else "One Trick Pony"
            spotlight_cards.append(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(otp_title),
                            dbc.CardBody(
                                html.Div(
                                    [
                                        html.Img(
                                            src=get_hero_image_url(otp_row["top_hero"]),
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
                                                html.H5(f"{otp_row['player']} – {otp_row['top_hero']}", className="mb-1"),
                                                html.Small(
                                                    f"{tr('games', lang)}: {int(otp_row['top_hero_games'])}",
                                                    className="text-muted",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="d-flex align-items-center",
                                )
                            ),
                        ]
                    , className="flex-fill h-100"),
                    md=3,
                    className="d-flex",
                )
            )

        # Hero-Carry: player-hero combo with highest winrate (min 2 games; fallback 1)
        best_combo = None
        best_wr = -1.0
        best_games = 0
        best_player = None
        best_hero = None
        for p in constants.players:
            role_col = f"{p} Rolle"
            hero_col = f"{p} Hero"
            if role_col not in dff_day.columns or hero_col not in dff_day.columns:
                continue
            subp = dff_day[(dff_day[role_col].astype(str).str.strip().str.lower() != "nicht dabei") & dff_day[hero_col].notna()]
            if subp.empty:
                continue
            g = subp.groupby(subp[hero_col].astype(str).str.strip())
            for hero, grp in g:
                if not _is_valid_hero(hero):
                    continue
                games_n = int(len(grp))
                wr_val = float((grp["_win"].mean() * 100.0) if games_n else 0.0)
                # prefer >=2 games; fallback if nothing qualifies
                prefer = (games_n >= 2)
                if best_combo is None:
                    best_combo = prefer
                    best_wr, best_games, best_player, best_hero = wr_val, games_n, p, hero
                else:
                    if prefer and not best_combo:
                        best_combo = True
                        best_wr, best_games, best_player, best_hero = wr_val, games_n, p, hero
                    elif prefer == best_combo:
                        if (wr_val > best_wr) or (wr_val == best_wr and games_n > best_games):
                            best_wr, best_games, best_player, best_hero = wr_val, games_n, p, hero
        if best_player is not None and best_hero is not None:
            # Dynamic title with hero name, e.g., "Tracer-Carry"
            carry_title = f"{best_hero}-Carry"
            spotlight_cards.append(
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(carry_title),
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
                                                html.H5(f"{best_player} – {best_hero}", className="mb-1"),
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
                        ]
                    , className="flex-fill h-100"),
                    md=3,
                    className="d-flex",
                )
            )

    # Player lineup grid
    lineup_cards = []
    role_color = {"Tank": "warning", "Damage": "danger", "Support": "success"}
    for r in player_rows:
        badges = [
            dbc.Badge(role, color=role_color.get(role, "secondary"), className="me-1")
            for role in r["roles"]
        ]
        lineup_cards.append(
            dbc.Col(
                dbc.Card(
                    [
                        dbc.CardBody(
                            html.Div(
                                [
                                    html.Img(
                                        src=get_hero_image_url(r.get("top_hero")) if r.get("top_hero") else "/assets/heroes/default_hero.png",
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
                                                f"{tr('games', lang)}: {r['games']} • {int(r['wins'])}-{int(r['losses'])} • {tr('winrate', lang)} {r['wr']:.1f}%",
                                                className="text-muted",
                                            ),
                                        ]
                                    ),
                                ],
                                className="d-flex align-items-center",
                            )
                        )
                    ]
                ),
                md=4,
            )
        )

    # Timeline as horizontal strip with small map tiles and arrows
    timeline_list_items = []
    # Build robust sort key: prefer extracted datetime, fallback to Datum, then Match ID; newest first
    dff_day["_dt_sort"] = dff_day["_dt_show"]
    if "Datum" in dff_day.columns:
        _mask_na = dff_day["_dt_sort"].isna()
        dff_day.loc[_mask_na, "_dt_sort"] = dff_day.loc[_mask_na, "Datum"]
    dff_day["_dt_has"] = dff_day["_dt_sort"].notna().astype(int)
    _sort_cols = ["_dt_has", "_dt_sort"]
    _asc = [False, False]
    if "Match ID" in dff_day.columns:
        _sort_cols.append("Match ID")
        _asc.append(False)
    dff_today_sorted = dff_day.sort_values(_sort_cols, ascending=_asc)
    tiles = []
    records = dff_today_sorted.to_dict(orient="records")
    for idx, game in enumerate(records):
        map_name = str(game.get("Map", tr("unknown_map", lang)))
        _mid = game.get("Match ID")
        victory = bool(game.get("_win"))
        img_src = get_map_image_url(map_name)
        border_col = "#16a34a" if victory else "#dc2626"
        tile = html.Div(
            [
                html.Div(
                    html.Img(
                        src=img_src,
                        style={
                            "width": "100%",
                            "height": "100%",
                            "objectFit": "cover",
                            "display": "block",
                        },
                        title=f"{map_name} • " + (tr("victory", lang) if victory else tr("defeat", lang)),
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
            ],
            id={"type": "timeline-tile", "matchId": int(_mid) if (pd.notna(_mid)) else -1},
            n_clicks=0,
            style={"flex": "0 0 auto", "cursor": "pointer"},
        )
        tiles.append(tile)
        # Connector line between tiles, skip after last element
        if idx < len(records) - 1:
            tiles.append(
                html.Div(
                    # small arrowhead pointing left (triangle only)
                    style={
                        "width": 0,
                        "height": 0,
                        "borderTop": "6px solid transparent",
                        "borderBottom": "6px solid transparent",
                        "borderRight": "8px solid rgba(156,163,175,0.7)",
                        "marginTop": "25px",  # vertically center near tile middle
                        "flex": "0 0 auto",
                    },
                    title="",
                )
            )
    timeline_component = html.Div(
        tiles,
        style={
            "display": "flex",
            "alignItems": "flex-start",
            "gap": "8px",
            "flexWrap": "wrap",
            "padding": "6px 2px",
        },
    )

    # Assemble content
    summary = banner_children[0]
    content = [
        dbc.Row(spotlight_cards, className="mt-3 g-3") if spotlight_cards else html.Div(),
        html.H4(tr("lineup_today", lang), className="mt-4 mb-2"),
        dbc.Row(lineup_cards, className="g-3") if lineup_cards else dbc.Alert(tr("no_data", lang), color="secondary"),
    html.Div([
        html.H4(tr("timeline_today", lang), className="mb-2 me-2"),
        html.Small(tr("newest_first", lang), className="text-muted")
    ], className="d-flex align-items-baseline mt-4"),
    timeline_component,
    ]

    return summary, content


def _upsert_heartbeat(session_id: str):
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
        # Opportunistic cleanup: drop entries older than 2x active window (default 40s)
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


def _count_active(within_seconds: int = None) -> int:
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


_init_active_db()


def _set_app_state(key: str, value: str):
    try:
        conn = sqlite3.connect(ACTIVE_DB)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO app_state(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def _get_app_state(key: str) -> str | None:
    conn = sqlite3.connect(ACTIVE_DB)
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM app_state WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


# --- i18n helper ---
def tr(key: str, lang: str) -> str:
    T = {
        "title": {"en": "Overwatch Statistics", "de": "Overwatch Statistiken"},
        "filters": {"en": "Filters", "de": "Filter"},
        "select_player": {"en": "Select player:", "de": "Spieler auswählen:"},
        "select_season": {
            "en": "Select season (overrides year/month):",
            "de": "Season auswählen (überschreibt Jahr/Monat):",
        },
        "select_year": {"en": "Select year:", "de": "Jahr auswählen:"},
        "select_month": {"en": "Select month:", "de": "Monat auswählen:"},
        "min_games": {"en": "Minimum games:", "de": "Mindestanzahl Spiele:"},
        "map_mode_stats": {"en": "Map & Mode Stats", "de": "Map & Mode Statistik"},
        "role_assign": {"en": "Role Assignment", "de": "Rollen-Zuordnung"},
        "hero_stats": {"en": "Hero Stats", "de": "Held Statistik"},
        "role_stats": {"en": "Role Stats", "de": "Rollen Statistik"},
        "heatmap": {"en": "Performance Heatmap", "de": "Performance Heatmap"},
        "trend": {"en": "Winrate Trend", "de": "Winrate Verlauf"},
        "trend_hero_filter": {
            "en": "Filter hero (optional):",
            "de": "Held filtern (optional):",
        },
        "history": {"en": "Match History", "de": "Match Verlauf"},
        "history_filter_player": {"en": "Filter by player:", "de": "Spieler filtern:"},
        "history_filter_hero": {"en": "Filter hero:", "de": "Held filtern:"},
        "update_from_cloud": {
            "en": "Update Data from Cloud",
            "de": "Daten aus Cloud aktualisieren",
        },
        "dark_mode": {"en": "Dark Mode", "de": "Dark Mode"},
        "map_winrate": {"en": "Winrate by Map", "de": "Winrate nach Map"},
        "map_plays": {"en": "Games per Map", "de": "Spiele pro Map"},
        "map_gamemode": {"en": "Gamemode Stats", "de": "Gamemode Statistik"},
        "map_attackdef": {
            "en": "Attack/Defense Stats",
            "de": "Attack/Defense Statistik",
        },
        "detailed": {"en": "Detailed", "de": "Detailliert"},
        "map_filter_opt": {
            "en": "Map filter (optional)",
            "de": "Map-Filter (optional)",
        },
        "choose_maps": {"en": "Choose maps", "de": "Maps wählen"},
        "bench": {
            "en": "Bench (exclude players)",
            "de": "Nicht dabei (Spieler ausschließen)",
        },
        "choose_players": {"en": "Choose players", "de": "Spieler wählen"},
        "tank_label": {"en": "Tank (max. 1)", "de": "Tank (max. 1 Spieler)"},
        "damage_label": {"en": "Damage (max. 2)", "de": "Damage (max. 2 Spieler)"},
        "support_label": {"en": "Support (max. 2)", "de": "Support (max. 2 Spieler)"},
        "detailed_mode": {
            "en": "Detailed mode (select heroes)",
            "de": "Detaillierter Modus (Helden wählen)",
        },
        "show_matching": {
            "en": "Show matching matches",
            "de": "Passende Matches anzeigen",
        },
        "load_more": {"en": "Load more", "de": "Mehr anzeigen"},
        "load_n_more": {"en": "Load {n} more", "de": "{n} weitere laden"},
        "all_players": {"en": "All players", "de": "Alle Spieler"},
        "no_history": {
            "en": "No match history available.",
            "de": "Keine Match History verfügbar.",
        },
        "no_games_filter": {
            "en": "No games found for this filter combination.",
            "de": "Für diese Filterkombination wurden keine Spiele gefunden.",
        },
        "only_relevant_winrate": {
            "en": "Only relevant for winrate statistics",
            "de": "Nur relevant für Winrate-Statistiken",
        },
        "season": {"en": "Season", "de": "Saison"},
        "victory": {"en": "VICTORY", "de": "SIEG"},
        "defeat": {"en": "DEFEAT", "de": "NIEDERLAGE"},
        "total_games": {"en": "Total games", "de": "Gesamtspiele"},
        "won": {"en": "Won", "de": "Gewonnen"},
        "lost": {"en": "Lost", "de": "Verloren"},
        "winrate": {"en": "Winrate", "de": "Winrate"},
        "most_played_hero": {"en": "Most played hero", "de": "Meistgespielter Held"},
        "best_wr_hero": {"en": "Best winrate (Hero)", "de": "Beste Winrate (Held)"},
        "most_played_map": {"en": "Most played map", "de": "Meistgespielte Map"},
        "best_wr_map": {"en": "Best winrate (Map)", "de": "Beste Winrate (Map)"},
        "no_data": {"en": "No data", "de": "Keine Daten"},
        "min_n_games": {"en": "Min. {n} games", "de": "Min. {n} Spiele"},
        "overall": {"en": "Overall", "de": "Gesamt"},
        "no_more_entries": {"en": "No more entries.", "de": "Keine weiteren Einträge."},
        "no_data_selection": {
            "en": "No data available for the selection",
            "de": "Keine Daten für die Auswahl verfügbar",
        },
        "stats_header": {"en": "Overall statistics", "de": "Gesamtstatistiken"},
        "compare_with": {"en": "Compare with:", "de": "Vergleiche mit:"},
        "games": {"en": "Games", "de": "Spiele"},
        "please_select_roles_first": {
            "en": "Please select players in roles first.",
            "de": "Bitte zuerst Spieler in Rollen auswählen.",
        },
        "no_data_loaded": {"en": "No data loaded.", "de": "Keine Daten geladen."},
        "no_data_selected_maps": {
            "en": "No data for selected maps.",
            "de": "Keine Daten für die gewählten Maps.",
        },
        "no_data_timeframe": {
            "en": "No data for the selected timeframe.",
            "de": "Keine Daten für den gewählten Zeitraum.",
        },
        "required_cols_missing": {
            "en": "Required columns are missing: {cols}",
            "de": "Erforderliche Spalten fehlen: {cols}",
        },
        "no_games_for_constellation": {
            "en": "No games found for this constellation.",
            "de": "Keine Spiele für diese Konstellation gefunden.",
        },
        "too_many_players": {
            "en": "Too many players selected: max 1 Tank, max 2 Damage, max 2 Support.",
            "de": "Zu viele Spieler gewählt: max 1 Tank, max 2 Damage, max 2 Support.",
        },
        "please_select_at_least_one_player": {
            "en": "Please select at least one player in any role.",
            "de": "Bitte mindestens einen Spieler in einer Rolle auswählen.",
        },
        "duplicate_players_roles": {
            "en": "Each player may appear only once across all roles.",
            "de": "Jeder Spieler darf nur einmal vorkommen (über alle Rollen).",
        },
        "too_many_players_history": {
            "en": "Too many players selected for history.",
            "de": "Zu viele Spieler gewählt für die Historie.",
        },
        "no_matching_matches": {
            "en": "No matching matches found.",
            "de": "Keine passenden Matches gefunden.",
        },
        "role_config_stats": {
            "en": "Statistics for role configuration",
            "de": "Statistik zur Rollen-Konstellation",
        },
        "bench_short": {"en": "Bench", "de": "Nicht dabei"},
        "heroes_filter": {"en": "Hero filters:", "de": "Helden-Filter:"},
        "choose_heroes_optional": {
            "en": "Choose heroes (optional)",
            "de": "Helden wählen (optional)",
        },
        "show_matching": {
            "en": "Show matching matches",
            "de": "Passende Matches anzeigen",
        },
        "invalid_date": {"en": "Invalid Date", "de": "Ungültiges Datum"},
        "unknown_map": {"en": "Unknown Map", "de": "Unbekannte Map"},
        "role_label": {"en": "Role", "de": "Rolle"},
        "players": {"en": "Players", "de": "Spieler"},
        "by": {"en": "by", "de": "nach"},
        "distribution": {"en": "Distribution", "de": "Verteilung"},
        "hero_label": {"en": "Hero", "de": "Held"},
        "map_label": {"en": "Map", "de": "Map"},
        "gamemode_label": {"en": "Gamemode", "de": "Gamemode"},
        "attackdef_label": {"en": "Attack/Defense", "de": "Attack/Defense"},
        "side": {"en": "Side", "de": "Seite"},
        "game_number": {"en": "Game number", "de": "Spielnummer"},
        "online_now": {"en": "Online", "de": "Online"},
    "daily_report": {"en": "Daily Report", "de": "Tagesreport"},
    "today_summary": {"en": "Today", "de": "Heute"},
    "no_games_today": {"en": "No games today", "de": "Heute keine Spiele"},
        "view_last_active_day_q": {
            "en": "Do you want to view the last active day ({date}, {n} games)?",
            "de": "Möchtest du den letzten aktiven Tag ansehen ({date}, {n} Spiele)?",
        },
        "view_last_active_day_btn": {"en": "Show", "de": "Anzeigen"},
    "wins": {"en": "Wins", "de": "Siege"},
    "losses": {"en": "Losses", "de": "Niederlagen"},
    "winrate_today": {"en": "Winrate today", "de": "Winrate heute"},
    "games_today": {"en": "Games today", "de": "Spiele heute"},
    "map_of_the_day": {"en": "Map of the day", "de": "Map des Tages"},
    "hero_spotlight": {"en": "Hero spotlight", "de": "Held im Fokus"},
    "biggest_flex": {"en": "Biggest Flex", "de": "Größter Flex"},
    "one_trick_pony": {"en": "One Trick Pony", "de": "One Trick Pony"},
    "hero_carry": {"en": "Hero Carry", "de": "Hero Carry"},
    "lineup_today": {"en": "Lineup", "de": "Aufstellung"},
    "timeline_today": {"en": "Timeline", "de": "Zeitverlauf"},
    "first_match": {"en": "First match", "de": "Erstes Spiel"},
    "last_match": {"en": "Last match", "de": "Letztes Spiel"},
    "newest_first": {"en": "Newest first", "de": "Neueste zuerst"},
    "last_active_day": {"en": "Last active day", "de": "Letzter aktiver Tag"},
    "distinct_heroes": {"en": "Distinct heroes", "de": "Verschiedene Helden"},
    "select_day": {"en": "Select day:", "de": "Tag wählen:"},
    "no_games_selected": {"en": "No games on selected day", "de": "Keine Spiele am gewählten Tag"},
    "showing_last_active": {"en": "Showing last active day", "de": "Zeige letzten aktiven Tag"},
    "date_placeholder": {"en": "Date", "de": "Datum"},
    }
    v = T.get(key, {})
    return v.get(lang, v.get("en", key))


# --- Data Loading ---
def load_data(use_local=True):
    """
    Loads data and performs a definitive sort by 'Match ID' descending.
    This ensures the most recent game is always at the top.
    """
    global df
    if use_local:
        try:
            df = pd.read_excel("local.xlsx", engine="openpyxl")
            print("Loaded data from local.xlsx")
        except Exception as e:
            print(f"Error loading local file: {e}")
            df = pd.DataFrame()
    else:
        try:
            response = requests.get(constants.url)
            response.raise_for_status()
            df = pd.read_csv(StringIO(response.text))
            df.to_excel("local.xlsx", index=False, engine="openpyxl")
            print("Successfully downloaded and saved as Excel!")
        except Exception as e:
            print(f"Error downloading data: {e}")
            if "df" not in globals():
                df = pd.DataFrame()

    if not df.empty:
        # Normalize all column names to strings and strip whitespace first
        df.columns = df.columns.map(lambda c: str(c).strip())

        # Build a robust rename map for common synonyms and localized headers
        def _norm_key(s: str) -> str:
            return re.sub(r"[^a-z0-9]", "", s.lower())

        base_map = {
            "winlose": "Win Lose",
            "ergebnis": "Win Lose",
            "map": "Map",
            "karte": "Map",
            "matchid": "Match ID",
            "match": "Match ID",
            "datum": "Datum",
            "date": "Datum",
        }
        ren = {}
        for col in list(df.columns):
            key = _norm_key(col)
            if key in base_map:
                ren[col] = base_map[key]
                continue
            # Per-player Role/Hero columns (handle English/German variants)
            for p in getattr(constants, "players", []):
                if not isinstance(p, str):
                    continue
                # Role
                if key == _norm_key(f"{p} rolle") or key == _norm_key(f"{p} role"):
                    ren[col] = f"{p} Rolle"
                    break
                # Hero
                if key == _norm_key(f"{p} hero") or key == _norm_key(f"{p} held"):
                    ren[col] = f"{p} Hero"
                    break
        if ren:
            df.rename(columns=ren, inplace=True)

        # VALIDATE REQUIRED COLUMNS (after normalization)
        required = ["Win Lose", "Map", "Match ID"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"Warnung: Fehlende Pflichtspalten: {missing}")
        if "Attack Def" in df.columns:
            df["Attack Def"] = df["Attack Def"].str.strip()
        if "Datum" in df.columns:
            df["Datum"] = pd.to_datetime(df["Datum"], errors="coerce")

        if "Match ID" in df.columns:
            df["Match ID"] = pd.to_numeric(df["Match ID"], errors="coerce")
            df.sort_values("Match ID", ascending=False, inplace=True)
            df.reset_index(drop=True, inplace=True)
            print("DataFrame sorted by Match ID (descending).")
        else:
            print("Warning: 'Match ID' column not found. History may not be in order.")

        # Normalize role labels across all per-player role columns
        role_map = {
            "DPS": "Damage",
            "Damage": "Damage",
            "Tank": "Tank",
            "Support": "Support",
        }
        for col in df.columns:
            if str(col).endswith(" Rolle"):
                df[col] = df[col].astype(str).str.strip()
                df[col] = df[col].replace(role_map)


load_data(use_local=True)


# --- Minimal Cloud Updater (no UI changes) ---
def _fetch_update_from_cloud(force: bool = False) -> bool:
    """Return True if data updated, otherwise False. Uses ETag/Last-Modified and content hash in memory.
    Keeps UI unchanged and only refreshes when something changed."""
    global _last_etag, _last_modified, _last_hash
    headers = {}
    if not force:
        if _last_etag:
            headers["If-None-Match"] = _last_etag
        if _last_modified:
            headers["If-Modified-Since"] = _last_modified
    # Prefer OneDrive Excel if configured; otherwise use Google Drive CSV
    use_onedrive = bool(getattr(constants, "ONEDRIVE_SHARE_URL", "").strip())
    if use_onedrive:
        share_url = constants.ONEDRIVE_SHARE_URL.strip()
        # Force direct download and add a cache-busting query so CDN doesn't serve stale content
        base = share_url + ("&" if ("?" in share_url) else "?") + constants.ONEDRIVE_FORCE_DOWNLOAD_PARAM
        cb = str(int(time.time()))
        dl_url = base + ("&" if ("?" in base) else "?") + "cb=" + cb
        try:
            # First, hit the view URL (no download) to nudge OneDrive to surface the latest version
            view_headers = {"Cache-Control": "no-cache", "Pragma": "no-cache", "Accept": "text/html,application/xhtml+xml"}
            try:
                requests.get(share_url, headers=view_headers, timeout=15)
            except Exception:
                pass
            # Then request the download, avoiding conditional headers (ETag/Last-Modified)
            req_headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
            resp = requests.get(dl_url, headers=req_headers, timeout=30)
        except Exception as e:
            print(f"OneDrive fetch failed: {e}")
            return False

        if resp.status_code == 304:
            return False
        if resp.status_code != 200:
            print(f"OneDrive fetch HTTP {resp.status_code}")
            return False

        content_bytes = resp.content or b""
        new_hash = hashlib.sha256(content_bytes).hexdigest()
        if not force and _last_hash and new_hash == _last_hash:
            return False

        try:
            # Read Excel from bytes and save a normalized copy
            tmp_df = pd.read_excel(BytesIO(content_bytes), engine="openpyxl")
            tmp_df.to_excel("local.xlsx", index=False, engine="openpyxl")
            load_data(use_local=True)
        except Exception as e:
            print(f"OneDrive download ok, but parse/save failed: {e}")
            return False

        _last_etag = resp.headers.get("ETag", _last_etag)
        _last_modified = resp.headers.get("Last-Modified", _last_modified)
        _last_hash = new_hash
        return True
    else:
        try:
            resp = requests.get(constants.url, headers=headers, timeout=20)
        except Exception as e:
            print(f"Cloud fetch failed: {e}")
            return False

        if resp.status_code == 304:
            # Not modified
            return False
        if resp.status_code != 200:
            print(f"Cloud fetch HTTP {resp.status_code}")
            return False

        text = resp.text or ""
        new_hash = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()
        if not force and _last_hash and new_hash == _last_hash:
            return False

        try:
            tmp_df = pd.read_csv(StringIO(text))
            tmp_df.to_excel("local.xlsx", index=False, engine="openpyxl")
            # Reload and normalize via existing loader
            load_data(use_local=True)
        except Exception as e:
            print(f"Download ok, but parse/save failed: {e}")
            return False

        _last_etag = resp.headers.get("ETag", _last_etag)
        _last_modified = resp.headers.get("Last-Modified", _last_modified)
        _last_hash = new_hash
        return True


# One-time lazy cloud check at startup (conditional; no UI impact)
try:
    _ = os.environ.get("DISABLE_STARTUP_CLOUD_CHECK", "0")
    if _ not in ("1", "true", "TRUE"):
        # Perform a conditional (non-forced) fetch; set token if updated
        if _fetch_update_from_cloud(force=False):
            try:
                if _last_hash:
                    _set_app_state("data_token", _last_hash)
            except Exception:
                pass
except Exception:
    pass


# --- Background updater (server-side) ---
def _background_updater():
    try:
        interval_s = max(5, int(float(os.environ.get("AUTO_UPDATE_MINUTES", constants.AUTO_UPDATE_MINUTES)) * 60))
    except Exception:
        interval_s = 300
    while True:
        try:
            updated = _fetch_update_from_cloud(force=False)
            if updated and _last_hash:
                try:
                    _set_app_state("data_token", _last_hash)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(interval_s)


try:
    if os.environ.get("ENABLE_BG_UPDATER", "1") in ("1", "true", "TRUE"):
        t = threading.Thread(target=_background_updater, daemon=True)
        t.start()
except Exception:
    pass


# --- Branding Helpers (optional custom logos) ---
def _resolve_brand_logo_sources():
    """
    Checks assets/branding/ for optional custom logos:
    - logo_light.(png|jpg|jpeg|webp|svg)
    - logo_dark.(png|jpg|jpeg|webp|svg)
    Returns tuple (light_src, dark_src, dark_invert) where sources are /assets paths.
    dark_invert True means apply CSS invert filter as fallback when no dark asset is provided.
    """
    exts = ["png", "jpg", "jpeg", "webp", "svg"]
    assets_dir = os.path.join("assets", "branding")
    light_src = None
    dark_src = None
    if os.path.isdir(assets_dir):
        for ext in exts:
            p = os.path.join(assets_dir, f"logo_light.{ext}")
            if os.path.exists(p):
                light_src = f"/assets/branding/logo_light.{ext}"
                break
        for ext in exts:
            p = os.path.join(assets_dir, f"logo_dark.{ext}")
            if os.path.exists(p):
                dark_src = f"/assets/branding/logo_dark.{ext}"
                break
    # Fallbacks
    default_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Overwatch_circle_logo.svg/1024px-Overwatch_circle_logo.svg.png"
    if not light_src:
        light_src = default_src
    dark_invert = False
    if not dark_src:
        # Use same as light and invert as a last resort
        dark_src = light_src
        dark_invert = True
    return light_src, dark_src, dark_invert


# Resolve once at startup
try:
    LIGHT_LOGO_SRC, DARK_LOGO_SRC, DARK_LOGO_INVERT = _resolve_brand_logo_sources()
except Exception as _e:
    LIGHT_LOGO_SRC = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Overwatch_circle_logo.svg/1024px-Overwatch_circle_logo.svg.png"
    DARK_LOGO_SRC = LIGHT_LOGO_SRC
    DARK_LOGO_INVERT = True

# Force specific dark theme logo per user request
DARK_LOGO_SRC = "https://upload.wikimedia.org/wikipedia/commons/thumb/7/70/Overwatch_circle_logo2.svg/640px-Overwatch_circle_logo2.svg.png"
DARK_LOGO_INVERT = False


# --- Secure refresh endpoint for external triggers (e.g., GitHub Actions) ---
@server.route("/refresh-data", methods=["POST"])
def refresh_data_route():
    # Verify token from header or query param
    provided = request.headers.get("X-Refresh-Token") or request.args.get("token")
    expected = os.environ.get("REFRESH_TOKEN")
    if not expected or provided != expected:
        return (
            json.dumps({"ok": False, "error": "unauthorized"}),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        updated = _fetch_update_from_cloud(force=True)
        if updated:
            try:
                if _last_hash:
                    _set_app_state("data_token", _last_hash)
            except Exception:
                pass
        return (
            json.dumps(
                {
                    "ok": True,
                    "updated": bool(updated),
                    "timestamp": str(pd.Timestamp.now()),
                }
            ),
            200,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        return (
            json.dumps({"ok": False, "error": str(e)}),
            500,
            {"Content-Type": "application/json"},
        )


# --- Layout ---
app.layout = html.Div(
    [
    dcc.Location(id="url"),
        dcc.Store(id="history-display-count-store", data={"count": 10}),
        dcc.Store(id="role-history-count-store", data={"count": 10}),
        # Persist the chosen theme locally (light/dark)
        dcc.Store(id="theme-store", data={"dark": False}, storage_type="local"),
        # Persist the chosen language locally (en/de), default to English
        dcc.Store(id="lang-store", data={"lang": "en"}, storage_type="local"),
        # Per-tab client id for live counter (session storage)
        dcc.Store(id="client-id", storage_type="session"),
        # Server-side update token (reflects last data update on server)
        dcc.Store(id="server-update-token", storage_type="memory"),
        # Hidden target for clientside side-effects
        html.Div(id="theme-body-sync", style={"display": "none"}),
    # Hidden ack for scroll-into-view clientside callback
    html.Div(id="dummy-scroll-ack", style={"display": "none"}),
        # Hidden heartbeat output for server-side tracking
        html.Div(id="heartbeat-dummy", style={"display": "none"}),
        # Hidden periodic auto-update (no UI elements added)
        dcc.Interval(
            id="auto-update-tick",
            interval=(
                int(
                    float(
                        os.environ.get(
                            "AUTO_UPDATE_MINUTES", constants.AUTO_UPDATE_MINUTES
                        )
                    )
                    * 60
                    * 1000
                )
            ),
        ),
        # Poll the server update token so all sessions pick up data changes
        dcc.Interval(
            id="server-update-poll",
            interval=int(os.environ.get("POLL_UPDATE_SECONDS", "10")) * 1000,
            n_intervals=0,
        ),
        # Init client id once per tab
        dcc.Interval(id="client-init", interval=1000, n_intervals=0, max_intervals=1),
        # Heartbeat every 15s
        dcc.Interval(id="heartbeat", interval=10000, n_intervals=0),
        # Refresh visible count more frequently
        dcc.Interval(id="active-count-refresh", interval=5000, n_intervals=0),
        dbc.Container(
            [
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                [
                                    # Brand logos with optional custom assets support
                                    html.Img(
                                        src=LIGHT_LOGO_SRC,
                                        height="50px",
                                        className="brand-logo light-only",
                                    ),
                                    html.Img(
                                        src=DARK_LOGO_SRC,
                                        height="50px",
                                        className=(
                                            "brand-logo dark-only "
                                            + ("invert" if DARK_LOGO_INVERT else "")
                                        ).strip(),
                                    ),
                                ]
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            html.H1(
                                "Overwatch Statistics",
                                className="my-4",
                                id="title-main",
                            ),
                            width=True,
                        ),
                        dbc.Col(
                            dbc.Button(
                                id="update-data-button",
                                color="primary",
                                className="mt-4",
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Switch(
                                id="theme-toggle",
                                value=False,
                                className="mt-4",
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            dbc.Button(
                                                html.Img(
                                                    src="https://flagcdn.com/w20/gb.png",
                                                    title="English",
                                                    alt="English",
                                                    style={
                                                        "height": "16px",
                                                        "width": "auto",
                                                    },
                                                ),
                                                id="btn-lang-en",
                                                color="secondary",
                                                outline=True,
                                                size="sm",
                                                className="me-1",
                                            ),
                                            dbc.Button(
                                                html.Img(
                                                    src="https://flagcdn.com/w20/de.png",
                                                    title="Deutsch",
                                                    alt="Deutsch",
                                                    style={
                                                        "height": "16px",
                                                        "width": "auto",
                                                    },
                                                ),
                                                id="btn-lang-de",
                                                color="secondary",
                                                outline=True,
                                                size="sm",
                                            ),
                                        ],
                                        className="d-flex flex-row mt-4 mb-1",
                                    ),
                                    dbc.Badge(
                                        id="online-counter",
                                        color="secondary",
                                        className="mt-1",
                                    ),
                                ],
                                className="d-flex flex-column align-items-start",
                            ),
                            width="auto",
                        ),
                    ],
                    align="center",
                    className="mb-3",
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            id="filter-header",
                                            className="bg-primary text-white",
                                            children="Filter",
                                        ),
                                        dbc.CardBody(
                                            [
                                                dbc.Label(
                                                    "Spieler auswählen:",
                                                    id="label-player",
                                                ),
                                                dcc.Dropdown(
                                                    id="player-dropdown",
                                                    options=[
                                                        {"label": p, "value": p}
                                                        for p in constants.players
                                                    ],
                                                    value=constants.players[0],
                                                    clearable=False,
                                                    className="mb-3",
                                                ),
                                                dbc.Label(
                                                    "Season auswählen (überschreibt Jahr/Monat):",
                                                    id="label-season",
                                                ),
                                                dcc.Dropdown(
                                                    id="season-dropdown",
                                                    placeholder="(keine ausgewählt)",
                                                    className="mb-3",
                                                    clearable=True,
                                                ),
                                                dbc.Label(
                                                    "Jahr auswählen:", id="label-year"
                                                ),
                                                dcc.Dropdown(
                                                    id="year-dropdown",
                                                    placeholder="(keine ausgewählt)",
                                                    className="mb-3",
                                                    clearable=True,
                                                ),
                                                dbc.Label(
                                                    "Monat auswählen:", id="label-month"
                                                ),
                                                dcc.Dropdown(
                                                    id="month-dropdown",
                                                    placeholder="(keine ausgewählt)",
                                                    className="mb-3",
                                                    clearable=True,
                                                ),
                                                dbc.Label(
                                                    "Mindestanzahl Spiele:",
                                                    id="label-min-games",
                                                ),
                                                dcc.Slider(
                                                    id="min-games-slider",
                                                    min=1,
                                                    max=100,
                                                    step=None,
                                                    value=5,
                                                    marks={
                                                        1: "1",
                                                        5: "5",
                                                        10: "10",
                                                        25: "25",
                                                        50: "50",
                                                        75: "75",
                                                        100: "100",
                                                    },
                                                    included=False,
                                                    className="mb-1",
                                                ),
                                                html.Div(
                                                    id="slider-hint",
                                                    className="text-muted",
                                                    style={"fontSize": "0.85em"},
                                                ),
                                                html.Hr(),
                                                html.Div(
                                                    id="compare-switches-container",
                                                    className="mt-3",
                                                ),
                                            ]
                                        ),
                                    ],
                                    className="mb-4",
                                )
                            ],
                            width=3,
                        ),
                        dbc.Col(
                            [
                                dbc.Tabs(
                                    [
                                        dbc.Tab(
                                            id="tab-comp-map",
                                            label="Map & Mode Statistik",
                                            tab_id="tab-map",
                                            children=[
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            dcc.Dropdown(
                                                                id="map-stat-type",
                                                                value="winrate",
                                                                clearable=False,
                                                                style={
                                                                    "width": "100%",
                                                                    "margin-bottom": "20px",
                                                                },
                                                                options=[],
                                                            ),
                                                            width=4,
                                                        ),
                                                        dbc.Col(
                                                            html.Div(
                                                                dbc.Switch(
                                                                    id="map-view-type",
                                                                    value=False,
                                                                    className="mt-1",
                                                                ),
                                                                id="map-view-type-container",
                                                                style={
                                                                    "margin-bottom": "20px"
                                                                },
                                                            ),
                                                            width=4,
                                                            className="d-flex align-items-center",
                                                        ),
                                                    ]
                                                ),
                                                html.Div(id="map-stat-container"),
                                            ],
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-role-assign",
                                            label="Rollen-Zuordnung",
                                            tab_id="tab-role-assign",
                                            children=[
                                                html.P(
                                                    id="role-assign-help",
                                                    children="",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                dbc.Label(
                                                                    id="label-map-filter",
                                                                    children="Map-Filter (optional)",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="role-map-filter",
                                                                    placeholder="Maps wählen",
                                                                    multi=True,
                                                                    clearable=True,
                                                                ),
                                                            ],
                                                            width=6,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                dbc.Label(
                                                                    id="label-bench",
                                                                    children="Nicht dabei (Spieler ausschließen)",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="assign-bench",
                                                                    options=[],
                                                                    placeholder="Spieler wählen",
                                                                    clearable=True,
                                                                    multi=True,
                                                                ),
                                                            ],
                                                            width=6,
                                                        ),
                                                    ],
                                                    className="mb-3",
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            [
                                                                dbc.Label(
                                                                    id="label-tank",
                                                                    children="Tank (max. 1 Spieler)",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="assign-tank",
                                                                    options=[],
                                                                    placeholder="Spieler wählen",
                                                                    clearable=True,
                                                                    multi=True,
                                                                ),
                                                            ],
                                                            width=4,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                dbc.Label(
                                                                    id="label-damage",
                                                                    children="Damage (max. 2 Spieler)",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="assign-damage",
                                                                    options=[],
                                                                    placeholder="Spieler wählen",
                                                                    clearable=True,
                                                                    multi=True,
                                                                ),
                                                            ],
                                                            width=4,
                                                        ),
                                                        dbc.Col(
                                                            [
                                                                dbc.Label(
                                                                    id="label-support",
                                                                    children="Support (max. 2 Spieler)",
                                                                ),
                                                                dcc.Dropdown(
                                                                    id="assign-support",
                                                                    options=[],
                                                                    placeholder="Spieler wählen",
                                                                    clearable=True,
                                                                    multi=True,
                                                                ),
                                                            ],
                                                            width=4,
                                                        ),
                                                    ],
                                                    className="mb-3",
                                                ),
                                                # Detaillierter Modus: Heldenauswahl je Spieler
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            dbc.Label(
                                                                id="label-detailed-mode",
                                                                children="Detaillierter Modus (Helden wählen)",
                                                            ),
                                                            width="auto",
                                                        ),
                                                        dbc.Col(
                                                            dbc.Switch(
                                                                id="role-detailed-toggle",
                                                                value=False,
                                                            ),
                                                            width="auto",
                                                        ),
                                                    ],
                                                    className="align-items-center mb-2",
                                                ),
                                                html.Div(
                                                    id="role-detailed-hero-selectors",
                                                    className="mb-3",
                                                ),
                                                html.Div(id="role-assign-result"),
                                                html.Hr(),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            dbc.Label(
                                                                "Passende Matches anzeigen"
                                                            ),
                                                            width="auto",
                                                        ),
                                                        dbc.Col(
                                                            dbc.Switch(
                                                                id="role-history-toggle",
                                                                value=False,
                                                            ),
                                                            width="auto",
                                                        ),
                                                    ],
                                                    className="align-items-center mb-2",
                                                ),
                                                html.Div(id="role-assign-history"),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            dcc.Dropdown(
                                                                id="role-history-load-amount-dropdown",
                                                                options=[
                                                                    {
                                                                        "label": "10 weitere laden",
                                                                        "value": 10,
                                                                    },
                                                                    {
                                                                        "label": "25 weitere laden",
                                                                        "value": 25,
                                                                    },
                                                                    {
                                                                        "label": "50 weitere laden",
                                                                        "value": 50,
                                                                    },
                                                                ],
                                                                value=10,
                                                                clearable=False,
                                                            ),
                                                            width={
                                                                "size": 3,
                                                                "offset": 3,
                                                            },
                                                        ),
                                                        dbc.Col(
                                                            dbc.Button(
                                                                "Mehr anzeigen",
                                                                id="role-history-load-more",
                                                                color="secondary",
                                                                className="w-100",
                                                            ),
                                                            width=3,
                                                        ),
                                                    ],
                                                    className="my-3 align-items-center",
                                                    justify="center",
                                                ),
                                            ],
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-daily",
                                            label="Daily Report",
                                            tab_id="tab-daily",
                                            children=[
                                                # Static, overlaid date picker positioned relative within the summary wrapper
                                                html.Div(
                                                    [
                                                        html.Div(
                                                            dcc.DatePickerSingle(
                                                                id="daily-date",
                                                                display_format="YYYY-MM-DD",
                                                                max_date_allowed=pd.Timestamp.now().normalize().date(),
                                                                initial_visible_month=pd.Timestamp.now().normalize().date(),
                                                                clearable=True,
                                                                placeholder="Date",
                                                                className="daily-date-picker",
                                                            ),
                                                            style={
                                                                "position": "absolute",
                                                                "top": "10px",
                                                                "right": "10px",
                                                                "zIndex": 4,
                                                                "padding": "2px",
                                                                "borderRadius": "999px",
                                                                "background": "radial-gradient(closest-side, rgba(255,255,255,0.5), rgba(255,255,255,0) 70%)",
                                                            },
                                                        ),
                                                        html.Div(id="daily-summary", className="mb-3"),
                                                    ],
                                                    style={"position": "relative"},
                                                ),
                                                html.Div(id="daily-report-container"),
                                            ],
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-hero",
                                            label="Held Statistik",
                                            tab_id="tab-hero",
                                            children=[
                                                dcc.Dropdown(
                                                    id="hero-stat-type",
                                                    value="winrate",
                                                    clearable=False,
                                                    style={
                                                        "width": "300px",
                                                        "margin-bottom": "20px",
                                                    },
                                                    options=[],
                                                ),
                                                dcc.Graph(id="hero-stat-graph"),
                                            ],
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-role",
                                            label="Rollen Statistik",
                                            tab_id="tab-role",
                                            children=[
                                                dcc.Dropdown(
                                                    id="role-stat-type",
                                                    value="winrate",
                                                    clearable=False,
                                                    style={
                                                        "width": "300px",
                                                        "margin-bottom": "20px",
                                                    },
                                                    options=[],
                                                ),
                                                dcc.Graph(id="role-stat-graph"),
                                            ],
                                        ),
                                        dbc.Tab(
                                            dcc.Graph(id="performance-heatmap"),
                                            id="tab-comp-heatmap",
                                            label="Performance Heatmap",
                                            tab_id="tab-heatmap",
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-trend",
                                            label="Winrate Verlauf",
                                            tab_id="tab-trend",
                                            children=[
                                                dbc.Label(
                                                    "Held filtern (optional):",
                                                    id="label-hero-filter-trend",
                                                ),
                                                dcc.Dropdown(
                                                    id="hero-filter-dropdown",
                                                    placeholder="Kein Held ausgewählt",
                                                    className="mb-3",
                                                ),
                                                dcc.Graph(id="winrate-over-time"),
                                            ],
                                        ),
                                        dbc.Tab(
                                            id="tab-comp-history",
                                            label="Match Verlauf",
                                            tab_id="tab-history",
                                            children=[
                                                dbc.Card(
                                                    dbc.CardBody(
                                                        [
                                                            dbc.Row(
                                                                [
                                                                    dbc.Col(
                                                                        [
                                                                            dbc.Label(
                                                                                "Spieler filtern:",
                                                                                id="label-history-player",
                                                                            ),
                                                                            dcc.Dropdown(
                                                                                id="player-dropdown-match-verlauf",
                                                                                options=[
                                                                                    {
                                                                                        "label": "Alle Spieler",
                                                                                        "value": "ALL",
                                                                                    }
                                                                                ]
                                                                                + [
                                                                                    {
                                                                                        "label": player,
                                                                                        "value": player,
                                                                                    }
                                                                                    for player in constants.players
                                                                                ],
                                                                                value="ALL",
                                                                                clearable=False,
                                                                            ),
                                                                        ],
                                                                        width=6,
                                                                    ),
                                                                    dbc.Col(
                                                                        [
                                                                            dbc.Label(
                                                                                "Held filtern:",
                                                                                id="label-history-hero",
                                                                            ),
                                                                            dcc.Dropdown(
                                                                                id="hero-filter-dropdown-match",
                                                                                placeholder="Alle Helden",
                                                                                clearable=True,
                                                                            ),
                                                                        ],
                                                                        width=6,
                                                                    ),
                                                                ]
                                                            )
                                                        ]
                                                    ),
                                                    className="mb-3",
                                                ),
                                                html.Div(
                                                    id="history-list-container",
                                                    style={
                                                        "maxHeight": "1000px",
                                                        "overflowY": "auto",
                                                    },
                                                ),
                                                dbc.Row(
                                                    [
                                                        dbc.Col(
                                                            dcc.Dropdown(
                                                                id="history-load-amount-dropdown",
                                                                options=[
                                                                    {
                                                                        "label": "10 weitere laden",
                                                                        "value": 10,
                                                                    },
                                                                    {
                                                                        "label": "25 weitere laden",
                                                                        "value": 25,
                                                                    },
                                                                    {
                                                                        "label": "50 weitere laden",
                                                                        "value": 50,
                                                                    },
                                                                ],
                                                                value=10,
                                                                clearable=False,
                                                            ),
                                                            width={
                                                                "size": 3,
                                                                "offset": 3,
                                                            },
                                                        ),
                                                        dbc.Col(
                                                            dbc.Button(
                                                                "Load More",
                                                                id="load-more-history-button",
                                                                color="secondary",
                                                                className="w-100",
                                                            ),
                                                            width=3,
                                                        ),
                                                    ],
                                                    className="my-3 align-items-center",
                                                    justify="center",
                                                ),
                                            ],
                                        ),
                                    ],
                                    id="tabs",
                                    active_tab="tab-map",
                                )
                            ],
                            width=9,
                        ),
                    ]
                ),
                dbc.Row(
                    [
                        dbc.Col(
                            [
                                dbc.Card(
                                    [
                                        dbc.CardHeader(
                                            id="stats-header",
                                            className="bg-primary text-white",
                                        ),
                                        dbc.CardBody([html.Div(id="stats-container")]),
                                    ]
                                )
                            ],
                            width=12,
                        )
                    ],
                    className="mt-4",
                ),
                html.Div(id="dummy-output", style={"display": "none"}),
                html.Div(
                    [
                        html.A(
                            id="patchnotes-link",
                            children="Patchnotes",
                            href="/patchnotes",
                            style={
                                "color": "#6c757d",
                                "textDecoration": "none",
                                "fontSize": "0.85em",
                            },
                        )
                    ],
                    className="text-center my-3",
                ),
            ],
            fluid=True,
        ),
    ],
    id="theme-root",
    className="",
)


# Smooth scroll to hash target after content renders (retries briefly)
app.clientside_callback(
        """
        function(hash) {
                if (!hash || typeof hash !== 'string' || hash.length < 2) { return window.dash_clientside.no_update; }
                const targetId = hash.substring(1);
                let attempts = 0;
                function tryScroll(){
                    const el = document.getElementById(targetId);
                    if (el){
                         el.scrollIntoView({behavior: 'smooth', block: 'center'});
                         return;
                    }
                    attempts += 1;
                    if (attempts < 20){ // retry up to ~1s
                         setTimeout(tryScroll, 50);
                    }
                }
                setTimeout(tryScroll, 0);
                return "ok";
        }
        """,
        Output("dummy-scroll-ack", "children"),
        Input("url", "hash")
)

# --- Patchnotes (from git log) ---
def _is_relevant_file(path: str) -> bool:
    if not path:
        return False
    p = path.strip()
    if p == "app.py":
        return True
    if p.startswith("assets/"):
        return True
    if p == "constants.py":
        return True
    if p == "requirements.txt":
        return True
    if p.endswith(".md"):
        return False
    if p.endswith(".db"):
        return False
    if p.startswith(".github/"):
        return False
    if p.startswith("scripts/"):
        return False
    if p == ".gitignore":
        return False
    if p == "PATCHNOTES.md":
        return False
    return False


def _get_patchnotes_commits(max_count: int = 100) -> list[dict]:
    try:
        cmd = [
            "git",
            "log",
            f"-n{max_count}",
            "--date=iso",
            "--pretty=format:%H\t%ad\t%an\t%s",
            "--name-only",
        ]
        out = subprocess.check_output(
            cmd,
            cwd=os.path.dirname(__file__) or ".",
            stderr=subprocess.STDOUT,
        )
        text = out.decode("utf-8", errors="ignore")
    except Exception as e:
        # Git nicht verfügbar – späterer Fallback liest PATCHNOTES.md
        return []

    commits = []
    current = None
    for line in text.splitlines():
        if "\t" in line and len(line.split("\t")) >= 4:
            if current:
                commits.append(current)
            parts = line.split("\t", 3)
            current = {
                "hash": parts[0],
                "date": parts[1],
                "author": parts[2],
                "subject": parts[3],
                "files": [],
                "relevant": False,
            }
        else:
            if current and line.strip():
                current["files"].append(line.strip())
    if current:
        commits.append(current)

    for c in commits:
        c["relevant"] = any(_is_relevant_file(f) for f in c.get("files", []))
    return commits


def _md_to_html(md_text: str) -> str:
    """Very small Markdown->HTML for our PATCHNOTES.md subset."""
    lines = md_text.splitlines()
    html_parts = []
    in_ul = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip() == "---":
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append("<hr/>")
            continue
        if line.startswith("# "):
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append(f"<h1>{html_std.escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("### "):
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append(f"<h3>{html_std.escape(line[4:].strip())}</h3>")
            continue
        if line.startswith("- "):
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append(f"<li>{html_std.escape(line[2:].strip())}</li>")
            continue
        if not line.strip():
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append("<br/>")
            continue
        # Paragraph fallback
        html_parts.append(f"<p>{html_std.escape(line)}</p>")
    if in_ul:
        html_parts.append("</ul>")
    return "\n".join(html_parts)


def _load_patchnotes_md(lang: str) -> str | None:
    """Load language-specific patchnotes MD if available, else default."""
    for name in (
        ["PATCHNOTES.de.md", "PATCHNOTES.md"]
        if lang == "de"
        else ["PATCHNOTES.en.md", "PATCHNOTES.md"]
    ):
        if os.path.exists(name):
            try:
                with open(name, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return None


def _parse_patchnotes_entries(md_text: str) -> list[dict]:
    """Parse our generated PATCHNOTES.md into entries with date, subject, notes, files."""
    entries = []
    lines = md_text.splitlines()
    i = 0
    current = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("### "):
            # finalize previous
            if current:
                entries.append(current)
            header = line[4:].strip()
            # Expected format: YYYY-MM-DD ... — <hash> — <subject>
            date_part = header.split(" — ")[0].strip()
            # normalize date to YYYY-MM-DD
            date_norm = date_part.split(" ")[0]
            subject = header.split(" — ")[-1].strip()
            current = {"date": date_norm, "subject": subject, "files": [], "notes": ""}
            i += 1
            continue
        if current is not None:
            # capture files from lines like "- M app.py" "- A assets/..."
            m = re.match(r"\s*-\s+([AMDZR])\s+(.+)$", line)
            if m:
                current["files"].append(m.group(2).strip())
            elif line.strip().lower().startswith("- notes:") or line.strip().startswith(
                "- Notes:"
            ):
                # Notes line like "- Notes: ..."
                note = line.split(":", 1)[1].strip() if ":" in line else ""
                current["notes"] = note
            elif line.startswith("### "):
                # handled above
                pass
        i += 1
    if current:
        entries.append(current)
    return entries


def _beautify_subject(subj: str, lang: str) -> str:
    s = (subj or "").strip().lower()
    mapping = [
        # Explicit UI actions and common synonyms
        ("sync button", {"de": "Sync-Button hinzugefügt", "en": "Added sync button"}),
        ("update button", {"de": "Sync-Button hinzugefügt", "en": "Added sync button"}),
        (
            "refresh button",
            {"de": "Sync-Button hinzugefügt", "en": "Added sync button"},
        ),
        ("reload button", {"de": "Sync-Button hinzugefügt", "en": "Added sync button"}),
        ("filter to history", {"de": "Filter für Historie", "en": "History filter"}),
        ("history filter", {"de": "Filter für Historie", "en": "History filter"}),
        ("filter history", {"de": "Filter für Historie", "en": "History filter"}),
        (
            "added filter to history",
            {"de": "Filter für Historie", "en": "History filter"},
        ),
        (
            "attack/def to history",
            {
                "de": "Angriff/Verteidigung in der Historie",
                "en": "Attack/Defense in history",
            },
        ),
        (
            "attack-def to history",
            {
                "de": "Angriff/Verteidigung in der Historie",
                "en": "Attack/Defense in history",
            },
        ),
        (
            "attack def to history",
            {
                "de": "Angriff/Verteidigung in der Historie",
                "en": "Attack/Defense in history",
            },
        ),
        (
            "atk/def to history",
            {
                "de": "Angriff/Verteidigung in der Historie",
                "en": "Attack/Defense in history",
            },
        ),
        ("patchnotes", {"de": "Patchnotes-Seite", "en": "Patch notes page"}),
        ("patch notes", {"de": "Patchnotes-Seite", "en": "Patch notes page"}),
        ("footer link", {"de": "Link im Seitenfuß", "en": "Footer link"}),
        (
            "webhook",
            {
                "de": "Sicherer Webhook für Datenupdate",
                "en": "Secure webhook for data update",
            },
        ),
        (
            "broadcast",
            {
                "de": "Updates in allen offenen Sitzungen",
                "en": "Updates across all open sessions",
            },
        ),
        (
            "update token",
            {
                "de": "Updates in allen offenen Sitzungen",
                "en": "Updates across all open sessions",
            },
        ),
        (
            "server-update-token",
            {
                "de": "Updates in allen offenen Sitzungen",
                "en": "Updates across all open sessions",
            },
        ),
        (
            "data_token",
            {
                "de": "Updates in allen offenen Sitzungen",
                "en": "Updates across all open sessions",
            },
        ),
        (
            "map thumbnail",
            {"de": "Breitere Karten-Vorschaubilder", "en": "Wider map thumbnails"},
        ),
        (
            "map width",
            {"de": "Breitere Karten-Vorschaubilder", "en": "Wider map thumbnails"},
        ),
        (
            "disabled slider",
            {
                "de": "Dezenter Stil für deaktivierte Regler",
                "en": "Subtler style for disabled sliders",
            },
        ),
        (
            "branding",
            {"de": "Branding/Logo aktualisiert", "en": "Branding/logo updated"},
        ),
        ("logo", {"de": "Branding/Logo aktualisiert", "en": "Branding/logo updated"}),
        (
            "added live viewer counter",
            {"de": "Live-Zähler für geöffnete Seiten", "en": "Live viewer counter"},
        ),
        (
            "language windows fix",
            {
                "de": "Sprachauswahl – Windows Fix",
                "en": "Language selection – Windows fix",
            },
        ),
        (
            "fixed language select",
            {"de": "Sprachauswahl verbessert", "en": "Improved language selection"},
        ),
        (
            "added jaina and english version",
            {
                "de": "Neue Spielerin Jaina & englische Sprache",
                "en": "Added Jaina & English version",
            },
        ),
        (
            "fixed dark mode persitence",
            {"de": "Dunkelmodus bleibt erhalten", "en": "Dark mode persistence fixed"},
        ),
        ("added dark mode", {"de": "Dunkelmodus hinzugefügt", "en": "Added dark mode"}),
        (
            "fixed role filter views",
            {"de": "Rollenfilter verbessert", "en": "Improved role filter views"},
        ),
        (
            "auto update",
            {"de": "Automatische Datenaktualisierung", "en": "Automatic data update"},
        ),
        (
            "added images to history",
            {"de": "Bilder in der Match-Historie", "en": "Images in match history"},
        ),
        (
            "added history and comparison mode",
            {
                "de": "Historie & Vergleich hinzugefügt",
                "en": "Added history & comparison",
            },
        ),
        (
            "added wr over time",
            {"de": "Winrate-Verlauf hinzugefügt", "en": "Added winrate over time"},
        ),
        (
            "added new stat",
            {"de": "Neue Statistik hinzugefügt", "en": "Added new statistic"},
        ),
        (
            "added season / date select",
            {"de": "Filter nach Season/Datum", "en": "Season/date filters"},
        ),
        (
            "fixed detailed view",
            {"de": "Detailansicht korrigiert", "en": "Fixed detailed view"},
        ),
        (
            "added attack def stats",
            {"de": "Angriff/Verteidigung-Statistik", "en": "Attack/Defense stats"},
        ),
        ("added heatmap", {"de": "Heatmap verbessert", "en": "Heatmap improved"}),
        # Daily Report feature umbrella
        (
            "daily report",
            {
                "de": "Tagesreport",
                "en": "Daily Report",
            },
        ),
    ]
    for key, loc in mapping:
        if key in s:
            return loc.get(lang, loc.get("en"))
    # Fallback: erste Buchstaben groß
    return subj[:1].upper() + subj[1:]


def _detect_lang() -> str:
    """Detect language from query (?lang=) or Accept-Language header. Defaults to 'de'."""
    try:
        q = request.args.get("lang")
        if q:
            ql = q.lower()
            if ql in ("de", "en"):
                return ql
        al = request.headers.get("Accept-Language", "")
        al = al.lower()
        if "de" in al and not "en" in al.split(",")[0]:
            return "de"
        if "en" in al:
            return "en"
    except Exception:
        pass
    return "de"


def _describe_change(subj: str, files: list[str] | None, lang: str) -> str:
    s = (subj or "").strip().lower()
    files = files or []

    def de(x: str) -> str:
        return x

    def en(x: str) -> str:
        return x

    mapping = [
        (
            "sync button",
            {
                "de": "Neuer Sync-Button: Damit kannst du die Daten jederzeit manuell aktualisieren – besonders hilfreich, wenn automatische Updates pausieren.",
                "en": "New sync button: You can manually refresh the data at any time – especially useful when automatic updates are paused.",
            },
        ),
        (
            "filter to history",
            {
                "de": "In der Match-Historie gibt es jetzt einen Filter. So kannst du die Liste eingrenzen und schneller finden, was dich interessiert.",
                "en": "The match history now has a filter. This lets you narrow the list and find what you need faster.",
            },
        ),
        (
            "history filter",
            {
                "de": "Die Historie lässt sich nun filtern, damit du Einträge gezielt eingrenzen kannst.",
                "en": "You can now filter the history to narrow down entries.",
            },
        ),
        (
            "filter history",
            {
                "de": "Für die Historie steht ein Filter zur Verfügung, um Einträge schneller zu finden.",
                "en": "A filter is available for history so you can find entries faster.",
            },
        ),
        (
            "added filter to history",
            {
                "de": "Die Historie hat jetzt einen Filter – für eine fokussierte Ansicht.",
                "en": "History now includes a filter for a more focused view.",
            },
        ),
        (
            "attack/def to history",
            {
                "de": "In der Match-Historie wird nun zwischen Angriff und Verteidigung unterschieden.",
                "en": "The match history now distinguishes between attack and defense.",
            },
        ),
        (
            "attack-def to history",
            {
                "de": "Die Historie zeigt jetzt Angriff und Verteidigung getrennt an.",
                "en": "History now shows attack and defense separately.",
            },
        ),
        (
            "attack def to history",
            {
                "de": "Angriff/Verteidigung ist in der Historie als eigene Information verfügbar.",
                "en": "Attack/Defense is now available in history as its own information.",
            },
        ),
        (
            "atk/def to history",
            {
                "de": "Atk/Def ist in der Historie sichtbar, um Matches besser einzuordnen.",
                "en": "Atk/Def is visible in history to better classify matches.",
            },
        ),
        (
            "update button",
            {
                "de": "Neuer Sync-Button: Manuelles Aktualisieren der Daten ist jetzt direkt möglich.",
                "en": "New sync button: Manual data refresh is now available.",
            },
        ),
        (
            "refresh button",
            {
                "de": "Neuer Sync-Button zum manuellen Aktualisieren der Daten.",
                "en": "New sync button to manually refresh the data.",
            },
        ),
        (
            "reload button",
            {
                "de": "Neuer Sync-Button zum manuellen Nachladen der Daten.",
                "en": "New sync button to manually reload the data.",
            },
        ),
        (
            "patchnotes",
            {
                "de": "Es gibt jetzt eine eigene Patchnotes-Seite mit verständlichen Beschreibungen – unauffällig im Footer verlinkt.",
                "en": "There is now a dedicated patch notes page with clear descriptions – subtly linked in the footer.",
            },
        ),
        (
            "patch notes",
            {
                "de": "Eine neue Patchnotes-Seite fasst Änderungen in ganzen Sätzen zusammen.",
                "en": "A new patch notes page summarizes changes in full sentences.",
            },
        ),
        (
            "footer link",
            {
                "de": "Im Seitenfuß gibt es einen dezenten Link zu den Patchnotes.",
                "en": "A subtle link to the patch notes is now available in the footer.",
            },
        ),
        (
            "webhook",
            {
                "de": "Ein sicherer, geheimer Webhook kann die Datenaktualisierung von außen anstoßen (z. B. über einen Scheduler).",
                "en": "A secure, secret webhook can trigger data updates from outside (e.g., via a scheduler).",
            },
        ),
        (
            "broadcast",
            {
                "de": "Wenn Daten aktualisiert werden, bekommen alle geöffneten Browser-Tabs die Änderung automatisch mit.",
                "en": "When data updates, all open browser tabs now pick up the change automatically.",
            },
        ),
        (
            "update token",
            {
                "de": "Datenaktualisierungen werden nun zuverlässig an alle Sitzungen verteilt.",
                "en": "Data updates are now reliably broadcast to all sessions.",
            },
        ),
        (
            "server-update-token",
            {
                "de": "Offene Sitzungen synchronisieren sich automatisch bei Datenänderungen.",
                "en": "Open sessions automatically synchronize on data changes.",
            },
        ),
        (
            "data_token",
            {
                "de": "Updates werden über einen gemeinsamen Server-Token an alle Clients verteilt.",
                "en": "Updates are distributed to all clients via a shared server token.",
            },
        ),
        (
            "map thumbnail",
            {
                "de": "Karten-Vorschaubilder sind jetzt breiter – die Zeilenhöhe bleibt gleich für eine ruhige Liste.",
                "en": "Map thumbnails are wider now – row height remains the same for a calm list.",
            },
        ),
        (
            "map width",
            {
                "de": "Die Breite der Karten-Vorschaubilder wurde erhöht, ohne die Höhe zu vergrößern.",
                "en": "Increased the width of map thumbnails without increasing row height.",
            },
        ),
        (
            "disabled slider",
            {
                "de": "Deaktivierte Schieberegler wirken im Dunkelmodus dezenter und bleiben gut lesbar.",
                "en": "Disabled sliders look subtler in dark mode while staying readable.",
            },
        ),
        (
            "branding",
            {
                "de": "Branding/Logo angepasst; Größen und Abstände bleiben erhalten.",
                "en": "Branding/logo updated; sizes and spacing preserved.",
            },
        ),
        (
            "logo",
            {
                "de": "Logo überarbeitet und sauber eingebunden.",
                "en": "Logo refined and embedded cleanly.",
            },
        ),
        (
            "added live viewer counter",
            {
                "de": "Es gibt jetzt einen Live-Zähler, der zeigt, wie viele Nutzer die Seite aktuell geöffnet haben.",
                "en": "There is now a live counter showing how many users currently have the page open.",
            },
        ),
        (
            "language windows fix",
            {
                "de": "Die Sprachanzeige funktioniert nun auch zuverlässig unter Windows.",
                "en": "Language display now works reliably on Windows as well.",
            },
        ),
        (
            "fixed language select",
            {
                "de": "Die Sprachauswahl wurde stabiler und klarer gestaltet.",
                "en": "The language selector has been made more stable and clearer.",
            },
        ),
        (
            "added jaina and english version",
            {
                "de": "Neue Spielerin Jaina hinzugefügt und die komplette App ist nun zusätzlich auf Englisch verfügbar.",
                "en": "Added new player Jaina and provided a complete English version of the app.",
            },
        ),
        (
            "fixed dark mode persitence",
            {
                "de": "Der Dunkelmodus bleibt jetzt zuverlässig erhalten – auch nach einem Neustart.",
                "en": "Dark mode now reliably persists, even after a restart.",
            },
        ),
        (
            "added dark mode",
            {
                "de": "Ein Dunkelmodus sorgt für bessere Lesbarkeit bei wenig Licht.",
                "en": "A dark mode improves readability in low-light conditions.",
            },
        ),
        (
            "fixed role filter views",
            {
                "de": "Die Rollenauswahl wurde korrigiert, sodass Überbelegungen vermieden und nicht verfügbare Spieler ausgeblendet werden.",
                "en": "Role selection was corrected to prevent over-picking and hide unavailable players.",
            },
        ),
        (
            "auto update",
            {
                "de": "Daten werden nun automatisch aus der Cloud aktualisiert; ein manueller Button steht zusätzlich bereit.",
                "en": "Data now updates automatically from the cloud; a manual button is available as well.",
            },
        ),
        (
            "added images to history",
            {
                "de": "Die Match-Historie zeigt jetzt passende Bilder für Karten und Helden.",
                "en": "Match history now shows corresponding images for maps and heroes.",
            },
        ),
        (
            "added history and comparison mode",
            {
                "de": "Es gibt eine Historie sowie einen Vergleichsmodus, um Entwicklungen besser nachzuvollziehen.",
                "en": "Added history and comparison mode to better track changes over time.",
            },
        ),
        (
            "added wr over time",
            {
                "de": "Die Winrate wird jetzt über die Zeit visualisiert.",
                "en": "Win rate over time is now visualized.",
            },
        ),
        (
            "added new stat",
            {
                "de": "Neue Kennzahlen wurden ergänzt, um Analysen zu verfeinern.",
                "en": "New metrics were added to refine analysis.",
            },
        ),
        (
            "added season / date select",
            {
                "de": "Filter nach Season und Datum erleichtern die gezielte Auswertung.",
                "en": "Season and date filters make targeted analysis easier.",
            },
        ),
        (
            "fixed detailed view",
            {
                "de": "Die Detailansicht wurde korrigiert und ist nun übersichtlicher.",
                "en": "The detailed view was fixed and is now clearer.",
            },
        ),
        (
            "added attack def stats",
            {
                "de": "Angriffs- und Verteidigungsstatistiken wurden ergänzt.",
                "en": "Added attack and defense statistics.",
            },
        ),
        (
            "added heatmap",
            {
                "de": "Die Heatmap wurde eingeführt bzw. verbessert.",
                "en": "Introduced or improved the heatmap.",
            },
        ),
        (
            "daily report",
            {"de": "Tagesreport", "en": "Daily Report"},
        ),
    ]
    for key, loc in mapping:
        if key in s:
            return loc.get(lang, loc.get("en"))
    # Keine generischen Texte mehr – wenn nichts Spezifisches erkannt wird, leer zurückgeben
    return ""


@server.route("/patchnotes")
def patchnotes_page():
    # Sprache automatisch erkennen (Query > Accept-Language > de)
    lang = _detect_lang()
    md = _load_patchnotes_md(lang)
    parts = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Patchnotes</title>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu;max-width:820px;margin:24px auto;padding:0 14px;color:#222} .c{border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;margin:10px 0;background:#fff} .meta{color:#6b7280;font-size:12px;margin-top:2px} h1{font-size:20px;margin:0 0 14px} h2{font-size:15px;margin:4px 0} a{color:#0366d6;text-decoration:none} a:hover{text-decoration:underline}</style>",
        "</head><body>",
        ("<h1>Aktualisierungen</h1>" if lang == "de" else "<h1>Updates</h1>"),
    ]
    if not md:
        parts.append(
            "<p>Keine Patchnotes gefunden.</p>"
            if lang == "de"
            else "<p>No patch notes found.</p>"
        )
        parts.append("</body></html>")
        return ("\n".join(parts), 200, {"Content-Type": "text/html; charset=utf-8"})

    # Parse entries and render minimal, user-friendly cards
    entries = _parse_patchnotes_entries(md)
    # relevance: file-based or mapping-based
    rendered = 0
    for e in entries:
        files = e.get("files", [])
        subj_raw = e.get("subject", "")
        is_relevant = any(_is_relevant_file(f) for f in files) or bool(
            _describe_change(subj_raw, files, lang)
        )
        if not is_relevant:
            continue
        subj = _beautify_subject(subj_raw, lang)
        # format date
        d = e.get("date") or ""
        try:
            y, m, da = d.split("-")
            nice_date = f"{da}.{m}.{y}"
        except Exception:
            nice_date = d
        meta = f"{nice_date} • " + ("Web-Update" if lang == "de" else "Web update")
        desc = _describe_change(subj_raw, files, lang)
        if not desc:
            # fallback to notes only if language matches (simple heuristic)
            notes = (e.get("notes") or "").strip()
            if lang == "en" and notes and re.search(r"[A-Za-z]", notes):
                desc = notes
            elif lang == "de" and notes and re.search(r"[A-Za-z]", notes):
                # notes are likely English – skip to avoid mixed language
                desc = ""
        if not desc:
            continue
        parts.append(
            f"<div class='c'><h2>{html_std.escape(subj)}</h2><div class='meta'>{html_std.escape(meta)}</div><p>{html_std.escape(desc)}</p></div>"
        )
        rendered += 1
        if rendered >= 30:
            break
    if rendered == 0:
        parts.append("<p>Keine Einträge.</p>" if lang == "de" else "<p>No entries.</p>")
    parts.append("</body></html>")
    return ("\n".join(parts), 200, {"Content-Type": "text/html; charset=utf-8"})


# --- Theme toggle (light/dark) ---
@app.callback(
    Output("theme-store", "data"),
    Input("theme-toggle", "value"),
    State("theme-store", "data"),
    prevent_initial_call=True,
)
def persist_theme_toggle(is_dark, data):
    data = data or {}
    data["dark"] = bool(is_dark)
    return data


@app.callback(Output("theme-root", "className"), Input("theme-store", "data"))
def apply_theme(data):
    dark = bool((data or {}).get("dark", False))
    return "dark" if dark else ""


app.clientside_callback(
    """
    function(data) {
        const dark = data && data.dark ? true : false;
        const doc = document.documentElement;
        const body = document.body;
        if (dark) {
            doc.style.backgroundColor = '#0f1115';
            body.style.backgroundColor = '#0f1115';
            doc.style.colorScheme = 'dark';
        } else {
            doc.style.backgroundColor = '#ffffff';
            body.style.backgroundColor = '#ffffff';
            doc.style.colorScheme = 'light';
        }
        return '';
    }
    """,
    Output("theme-body-sync", "children"),
    Input("theme-store", "data"),
)


@app.callback(
    Output("theme-toggle", "value"),
    Input("theme-store", "data"),
    prevent_initial_call=False,
)
def sync_toggle_from_store(data):
    return bool((data or {}).get("dark", False))


# --- Language toggle (en/de) ---
@app.callback(
    Output("lang-store", "data"),
    Input("btn-lang-en", "n_clicks"),
    Input("btn-lang-de", "n_clicks"),
    State("lang-store", "data"),
    prevent_initial_call=True,
)
def set_language(n_en, n_de, data):
    data = data or {"lang": "en"}
    trigger = ctx.triggered_id
    if trigger == "btn-lang-en":
        data["lang"] = "en"
    elif trigger == "btn-lang-de":
        data["lang"] = "de"
    return data


@app.callback(
    Output("title-main", "children"),
    Output("filter-header", "children"),
    Output("label-player", "children"),
    Output("label-season", "children"),
    Output("label-year", "children"),
    Output("label-month", "children"),
    Output("label-min-games", "children"),
    Output("tab-comp-map", "label"),
    Output("tab-comp-daily", "label"),
    Output("tab-comp-role-assign", "label"),
    Output("tab-comp-hero", "label"),
    Output("tab-comp-role", "label"),
    Output("tab-comp-heatmap", "label"),
    Output("tab-comp-trend", "label"),
    Output("label-hero-filter-trend", "children"),
    Output("tab-comp-history", "label"),
    Output("label-history-player", "children"),
    Output("label-history-hero", "children"),
    Input("lang-store", "data"),
)
def apply_language_texts(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    if lang == "de":
        return (
            "Overwatch Statistiken",
            "Filter",
            "Spieler auswählen:",
            "Season auswählen (überschreibt Jahr/Monat):",
            "Jahr auswählen:",
            "Monat auswählen:",
            "Mindestanzahl Spiele:",
            "Map & Mode Statistik",
            "Tagesreport",
            "Rollen-Zuordnung",
            "Held Statistik",
            "Rollen Statistik",
            "Performance Heatmap",
            "Winrate Verlauf",
            "Held filtern (optional):",
            "Match Verlauf",
            "Spieler filtern:",
            "Held filtern:",
        )
    # English default
    return (
        "Overwatch Statistics",
        "Filters",
        "Select player:",
        "Select season (overrides year/month):",
        "Select year:",
        "Select month:",
        "Minimum games:",
        "Map & Mode Stats",
        "Daily Report",
        "Role Assignment",
        "Hero Stats",
        "Role Stats",
        "Performance Heatmap",
        "Winrate Trend",
        "Filter hero (optional):",
        "Match History",
        "Filter by player:",
        "Filter hero:",
    )


@app.callback(
    Output("update-data-button", "children"),
    Output("theme-toggle", "label"),
    Input("lang-store", "data"),
)
def apply_language_controls(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    if lang == "de":
        return "Daten aus Cloud aktualisieren", "Dark Mode"
    return "Update Data from Cloud", "Dark Mode"


@app.callback(
    Output("map-stat-type", "options"),
    Output("map-stat-type", "value"),
    Output("map-view-type", "label"),
    Output("hero-stat-type", "options"),
    Output("hero-stat-type", "value"),
    Output("role-stat-type", "options"),
    Output("role-stat-type", "value"),
    Output("role-map-filter", "placeholder"),
    Output("assign-bench", "placeholder"),
    Output("assign-tank", "placeholder"),
    Output("assign-damage", "placeholder"),
    Output("assign-support", "placeholder"),
    Output("role-history-load-amount-dropdown", "options"),
    Output("role-history-load-amount-dropdown", "value"),
    Output("role-history-load-more", "children"),
    Output("player-dropdown-match-verlauf", "options"),
    Output("player-dropdown-match-verlauf", "value"),
    Input("lang-store", "data"),
)
def localize_controls(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    map_opts = [
        {"label": tr("map_winrate", lang), "value": "winrate"},
        {"label": tr("map_plays", lang), "value": "plays"},
        {"label": tr("map_gamemode", lang), "value": "gamemode"},
        {"label": tr("map_attackdef", lang), "value": "attackdef"},
    ]
    hero_opts = [
        {
            "label": tr("map_winrate", lang).replace(
                "Map", "Hero" if lang == "en" else "Held"
            ),
            "value": "winrate",
        },
        {
            "label": tr("map_plays", lang).replace(
                "Map", "Hero" if lang == "en" else "Held"
            ),
            "value": "plays",
        },
    ]
    role_opts = [
        {
            "label": tr("map_winrate", lang).replace(
                "Map", "Role" if lang == "en" else "Rolle"
            ),
            "value": "winrate",
        },
        {
            "label": tr("map_plays", lang).replace(
                "Map", "Role" if lang == "en" else "Rolle"
            ),
            "value": "plays",
        },
    ]
    load_amounts = [10, 25, 50]
    load_opts = [
        {"label": tr("load_n_more", lang).format(n=n), "value": n} for n in load_amounts
    ]
    load_more_label = tr("load_more", lang)
    # Player dropdown (history): include ALL option + players
    hist_player_options = [{"label": tr("all_players", lang), "value": "ALL"}] + [
        {"label": p, "value": p} for p in constants.players
    ]
    return (
        map_opts,
        "winrate",  # default value
        tr("detailed", lang),
        hero_opts,
        "winrate",  # default value
        role_opts,
        "winrate",  # default value
        tr("choose_maps", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        load_opts,
        load_amounts[0],
        load_more_label,
        hist_player_options,
        "ALL",
    )


@app.callback(
    Output("role-assign-help", "children"),
    Output("label-map-filter", "children"),
    Output("label-bench", "children"),
    Output("label-tank", "children"),
    Output("label-damage", "children"),
    Output("label-support", "children"),
    Output("label-detailed-mode", "children"),
    Input("lang-store", "data"),
)
def localize_role_assign(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    return (
        "",  # role-assign-help intentionally blank per request
        tr("map_filter_opt", lang),
        tr("bench", lang),
        tr("tank_label", lang),
        tr("damage_label", lang),
        tr("support_label", lang),
        tr("detailed_mode", lang),
    )


# Make footer Patchnotes link follow current UI language
@app.callback(
    Output("patchnotes-link", "children"),
    Output("patchnotes-link", "href"),
    Input("lang-store", "data"),
)
def localize_patchnotes_link(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    text = "Patchnotes" if lang == "de" else "Patch notes"
    href = f"/patchnotes?lang={lang}"
    return text, href


# Localize the daily date selector format only (no label in UI)
@app.callback(
    Output("daily-date", "display_format"),
    Output("daily-date", "placeholder"),
    Input("lang-store", "data"),
)
def localize_daily_date(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    fmt = "DD.MM.YYYY" if lang == "de" else "YYYY-MM-DD"
    ph = tr("date_placeholder", lang) if tr("date_placeholder", lang) != "date_placeholder" else ("Datum" if lang == "de" else "Date")
    return fmt, ph


# Keep date picker within bounds and in a sane month view
@app.callback(
    Output("daily-date", "max_date_allowed"),
    Output("daily-date", "initial_visible_month"),
    Input("lang-store", "data"),
)
def _sync_datepicker_bounds(_lang_data):
    today = pd.Timestamp.now().normalize().date()
    return today, today


# --- Helper Functions ---


def get_map_image_url(map_name):
    """
    Generates a URL for a map's background image.
    Assumes images are in 'assets/maps/' and named like 'map_name.png'.
    """
    if not isinstance(map_name, str):
        return "/assets/maps/default.jpg"  # Fallback for non-string input

    # Clean the map name to create a valid filename
    # e.g., "King's Row" -> "kings_row"
    cleaned_name = map_name.lower().replace(" ", "_").replace("'", "")

    # Check for both .jpg and .png extensions
    for ext in [".jpg", ".png"]:
        image_filename = f"{cleaned_name}{ext}"
        # The path Dash uses to serve from the assets folder
        asset_path = f"/assets/maps/{image_filename}"
        # The actual file system path to check if the file exists
        local_path = os.path.join("assets", "maps", image_filename)

        if os.path.exists(local_path):
            return asset_path

    # If no specific image is found, return the default
    return "/assets/maps/default.png"


def get_hero_image_url(hero_name):
    """
    Generates a URL for a hero's portrait with more robust, flexible checking.
    It tries multiple common filename variations and checks for both .png and .jpg.
    """
    if not isinstance(hero_name, str):
        return "/assets/heroes/default_hero.png"

    base_name = hero_name.lower()

    # --- Create a list of potential filenames to try ---
    potential_names = []

    # 1. Standard cleaning (e.g., "d.va" -> "dva", "lúcio" -> "lucio")
    cleaned_base = base_name.replace(".", "").replace(":", "").replace("ú", "u")

    # 2. Add variations for spaces (e.g., "soldier 76" -> "soldier_76" AND "soldier76")
    potential_names.append(cleaned_base.replace(" ", "_"))
    potential_names.append(cleaned_base.replace(" ", ""))

    # 3. Add a super-aggressive cleaning as a final fallback (removes all non-letters/numbers)
    potential_names.append(re.sub(r"[^a-z0-9]", "", base_name))

    # Remove any duplicate names that may have been generated
    potential_names = list(set(potential_names))

    # --- Now, check if a file exists for any of these variations ---
    for name in potential_names:
        if not name:
            continue  # Skip if cleaning resulted in an empty string

        for ext in [".png", ".jpg", ".jpeg"]:  # Check for all common image extensions
            image_filename = f"{name}{ext}"
            asset_path = f"/assets/heroes/{image_filename}"
            local_path = os.path.join("assets", "heroes", image_filename)

            if os.path.exists(local_path):
                # We found a match! Return it immediately.
                return asset_path

    # If after all that, we still can't find it, return the default.
    return "/assets/heroes/default_hero.png"


def create_stat_card(title, image_url, main_text, sub_text):
    """
    Erstellt eine einzelne, schön formatierte Statistik-Karte.
    """
    return dbc.Col(
        dbc.Card(
            [
                dbc.CardHeader(title),
                dbc.CardBody(
                    html.Div(
                        [
                            html.Img(
                                src=image_url,
                                style={
                                    "width": "60px",
                                    "height": "60px",
                                    "objectFit": "cover",
                                    "borderRadius": "8px",
                                    "marginRight": "15px",
                                },
                            ),
                            html.Div(
                                [
                                    html.H5(main_text, className="mb-0"),
                                    html.Small(sub_text, className="text-muted"),
                                ]
                            ),
                        ],
                        className="d-flex align-items-center",
                    )
                ),
            ],
            className="h-100",  # Stellt sicher, dass alle Karten in einer Reihe die gleiche Höhe haben
        ),
        md=3,
    )


def filter_data(player, season=None, month=None, year=None):
    global df
    if df.empty:
        return pd.DataFrame()
    temp = df[df["Win Lose"].isin(["Win", "Lose"])].copy()
    if season:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None:
            temp = temp[temp["Monat"] == month]
    role_col, hero_col = f"{player} Rolle", f"{player} Hero"
    if role_col not in temp.columns or hero_col not in temp.columns:
        return pd.DataFrame()
    temp = temp[temp[role_col].notna() & (temp[role_col] != "nicht dabei")]
    if temp.empty:
        return pd.DataFrame()
    temp["Hero"], temp["Rolle"] = temp[hero_col].str.strip(), temp[role_col].str.strip()
    return temp[temp["Hero"].notna() & (temp["Hero"] != "")]


def calculate_winrate(data, group_col):
    if data.empty or not isinstance(group_col, str) or group_col not in data.columns:
        return pd.DataFrame(columns=[group_col, "Win", "Lose", "Winrate", "Spiele"])
    data[group_col] = data[group_col].astype(str).str.strip()
    data = data[data[group_col].notna() & (data[group_col] != "")]
    if data.empty:
        return pd.DataFrame(columns=[group_col, "Win", "Lose", "Winrate", "Spiele"])
    grouped = data.groupby([group_col, "Win Lose"]).size().unstack(fill_value=0)
    if "Win" not in grouped:
        grouped["Win"] = 0
    if "Lose" not in grouped:
        grouped["Lose"] = 0
    grouped["Spiele"] = grouped["Win"] + grouped["Lose"]
    grouped["Winrate"] = grouped["Win"] / grouped["Spiele"]
    return grouped.reset_index().sort_values("Winrate", ascending=False)


def generate_history_layout_simple(games_df):
    if games_df.empty:
        return [dbc.Alert("Keine Match History verfügbar.", color="info")]

    history_items = []
    last_season = None

    for idx, game in games_df.iterrows():
        if pd.isna(game.get("Map")):
            continue

        current_season = game.get("Season")
        if pd.notna(current_season) and current_season != last_season:
            match = re.search(r"\d+", str(current_season))
            season_text = f"Season {match.group(0)}" if match else str(current_season)
            history_items.append(
                dbc.Alert(
                    season_text, color="secondary", className="my-4 text-center fw-bold"
                )
            )
            last_season = current_season

        map_name = game.get("Map", "Unknown Map")
        gamemode = game.get("Gamemode", "")
        att_def = game.get("Attack Def")
        map_image_url = get_map_image_url(map_name)
        date_str = (
            game["Datum"].strftime("%d.%m.%Y")
            if pd.notna(game.get("Datum"))
            else "Invalid Date"
        )
        result_color, result_text = (
            ("success", "VICTORY")
            if game.get("Win Lose") == "Win"
            else ("danger", "DEFEAT")
        )
        if att_def == "Attack Attack":
            att_def_string = f"{gamemode} • {date_str}"
        else:
            att_def_string = f"{gamemode} • {date_str} • {att_def}"

        # --- REVISED PLAYER LIST SECTION ---
        player_list_items = []
        for p in constants.players:
            hero = game.get(f"{p} Hero")
            if pd.notna(hero) and hero != "nicht dabei":
                role = game.get(f"{p} Rolle", "N/A")
                hero_image_url = get_hero_image_url(hero)  # Get the portrait URL

                player_list_items.append(
                    dbc.ListGroupItem(
                        # Use flexbox to align the avatar and the text content
                        html.Div(
                            [
                                # 1. The Hero Portrait (Avatar)
                                html.Img(
                                    src=hero_image_url,
                                    style={
                                        "width": "40px",
                                        "height": "40px",
                                        "borderRadius": "50%",  # Makes the image circular
                                        "objectFit": "cover",
                                        "marginRight": "15px",
                                    },
                                ),
                                # 2. A div to hold the player info and hero name
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.Span(p, className="fw-bold"),
                                                html.Span(
                                                    f" ({role})",
                                                    className="text-muted",
                                                    style={"fontSize": "0.9em"},
                                                ),
                                            ]
                                        ),
                                        html.Div(hero),
                                    ],
                                    # This inner flexbox pushes the player name and hero name apart
                                    className="d-flex justify-content-between align-items-center w-100",
                                ),
                            ],
                            # This outer flexbox aligns the image with the text block
                            className="d-flex align-items-center",
                        )
                    )
                )

        anchor_id = None
        try:
            if pd.notna(game.get("Match ID")):
                anchor_id = f"match-{int(game.get('Match ID'))}"
        except Exception:
            anchor_id = None
        card = dbc.Card(
            dbc.Row(
                [
                    dbc.Col(
                        html.Img(
                            src=map_image_url,
                            className="img-fluid rounded-start h-100",
                            style={"objectFit": "cover"},
                        ),
                        md=3,
                    ),
                    dbc.Col(
                        [
                            dbc.CardHeader(
                                html.Div(
                                    [
                                        html.Div(
                                            [
                                                html.H5(
                                                    f"{map_name}", className="mb-0"
                                                ),
                                                html.Small(
                                                    att_def_string,
                                                    className="text-muted",
                                                ),
                                            ]
                                        ),
                                        dbc.Badge(
                                            result_text,
                                            color=result_color,
                                            className="ms-auto",
                                            style={"height": "fit-content"},
                                        ),
                                    ],
                                    className="d-flex justify-content-between align-items-center",
                                )
                            ),
                            dbc.CardBody(
                                dbc.ListGroup(player_list_items, flush=True),
                                className="p-0",
                            ),
                        ],
                        md=9,
                    ),
                ],
                className="g-0",
            ),
            className="mb-3",
            id=anchor_id,
        )
        history_items.append(card)

    return history_items


# --- Callbacks ---
@app.callback(
    Output("role-detailed-hero-selectors", "children"),
    Input("role-detailed-toggle", "value"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input("lang-store", "data"),
)
def build_detailed_hero_selectors(
    detail_on, tank_vals, dmg_vals, sup_vals, season, month, year, lang_data
):
    lang = (lang_data or {}).get("lang", "en")
    if not detail_on:
        return None

    tank = tank_vals or []
    dmg = dmg_vals or []
    sup = sup_vals or []
    selected_players = []
    role_by_player = {}
    if len(tank) == 1:
        selected_players.append(tank[0])
        role_by_player[tank[0]] = "Tank"
    for p in dmg:
        selected_players.append(p)
        role_by_player[p] = "Damage"
    for p in sup:
        selected_players.append(p)
        role_by_player[p] = "Support"

    if not selected_players:
        return dbc.Alert(tr("please_select_roles_first", lang), color="info")

    global df
    if df.empty:
        return dbc.Alert(tr("no_data_loaded", lang), color="danger")

    # Zeitrahmen filtern
    temp = df.copy()
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]

    cols = []
    for p in selected_players:
        role = role_by_player.get(p)
        hero_col = f"{p} Hero"
        role_col = f"{p} Rolle"
        options = []
        if hero_col in temp.columns and role_col in temp.columns:
            subset = temp[(temp[hero_col].notna()) & (temp[hero_col] != "nicht dabei")]
            if role:
                subset = subset[subset[role_col] == role]
            heroes = sorted(subset[hero_col].dropna().unique())
            options = [
                {
                    "label": html.Div(
                        [
                            html.Img(
                                src=get_hero_image_url(h),
                                style={
                                    "height": "22px",
                                    "marginRight": "8px",
                                    "borderRadius": "50%",
                                },
                            ),
                            html.Span(h),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    "value": h,
                }
                for h in heroes
            ]
        cols.append(
            dbc.Col(
                [
                    dbc.Label(f"{p} – {role}" if role else p),
                    dcc.Dropdown(
                        id={"type": "detailed-hero", "player": p},
                        options=options,
                        placeholder=tr("choose_heroes_optional", lang),
                        multi=True,
                        clearable=True,
                    ),
                ],
                md=4,
            )
        )

    return dbc.Row(cols, className="g-3")


@app.callback(
    Output("dummy-output", "children"),
    Input("update-data-button", "n_clicks"),
    Input("auto-update-tick", "n_intervals"),
    prevent_initial_call=True,
)
def update_data(n_clicks, n_intervals):
    triggered = ctx.triggered_id if ctx.triggered_id else None
    if triggered == "update-data-button" and (n_clicks or 0) > 0:
        updated = _fetch_update_from_cloud(force=True)
        if updated:
            # Persist a server-wide token so all workers/sessions can detect the change
            try:
                if _last_hash:
                    _set_app_state("data_token", _last_hash)
            except Exception:
                pass
            return f"Data updated at {pd.Timestamp.now()}"
        return no_update
    if triggered == "auto-update-tick":
        updated = _fetch_update_from_cloud(force=False)
        if updated:
            try:
                if _last_hash:
                    _set_app_state("data_token", _last_hash)
            except Exception:
                pass
            return f"Data updated at {pd.Timestamp.now()}"
        return no_update
    return no_update



@app.callback(
    Output("year-dropdown", "value", allow_duplicate=True),
    Output("month-dropdown", "value", allow_duplicate=True),
    Input("btn-view-last-active-day", "n_clicks"),
    prevent_initial_call=True,
)
def on_view_last_active_day(n):
    if not n:
        raise PreventUpdate
    if df.empty or "Datum" not in df.columns:
        raise PreventUpdate
    dff = df.dropna(subset=["Datum"]).copy()
    if dff.empty:
        raise PreventUpdate
    last = dff["Datum"].max()
    return int(last.year), int(last.month)

@app.callback(
    Output("server-update-token", "data"),
    Input("server-update-poll", "n_intervals"),
    State("server-update-token", "data"),
    prevent_initial_call=False,
)
def poll_server_update_token(_n, current_token):
    # Read the server-wide token from the shared DB (cross-worker safe)
    token = _get_app_state("data_token") or ""
    # Only trigger downstream updates when the token changed.
    if token != (current_token or ""):
        return token
    return no_update


@app.callback(
    Output("season-dropdown", "options"),
    Output("month-dropdown", "options"),
    Output("year-dropdown", "options"),
    Input("dummy-output", "children"),
)
def update_filter_options(_):
    if df.empty:
        return [], [], []
    season_options = [
        {"label": s, "value": s}
        for s in sorted(df["Season"].dropna().unique(), reverse=True)
    ]
    month_options = [
        {"label": m, "value": m} for m in sorted(df["Monat"].dropna().unique())
    ]
    year_options = [
        {"label": str(int(y)), "value": int(y)}
        for y in sorted(df["Jahr"].dropna().unique())
    ]
    return season_options, month_options, year_options


@app.callback(
    Output("assign-tank", "options"),
    Output("assign-damage", "options"),
    Output("assign-support", "options"),
    Output("assign-bench", "options"),
    Output("role-map-filter", "options"),
    Input("dummy-output", "children"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
)
def populate_role_assignment_options(_, tank_vals, dmg_vals, sup_vals, bench_vals):
    # Players
    if df.empty:
        players = constants.players
        maps = []
    else:
        players = [
            col.replace(" Rolle", "") for col in df.columns if col.endswith(" Rolle")
        ]
        players = players or constants.players
        maps = sorted([m for m in df.get("Map", pd.Series()).dropna().unique()])

    tank_vals = tank_vals or []
    dmg_vals = dmg_vals or []
    sup_vals = sup_vals or []
    bench_vals = bench_vals or []
    selected_any = set(tank_vals + dmg_vals + sup_vals + bench_vals)

    def build_opts(max_count: int, current: list[str]):
        role_full = len(current) >= max_count
        res = []
        for p in players:
            disabled = False
            if p in selected_any and p not in current:
                disabled = True
            if role_full and p not in current:
                disabled = True
            res.append({"label": p, "value": p, "disabled": disabled})
        return res

    tank_opts = build_opts(1, tank_vals)
    dmg_opts = build_opts(2, dmg_vals)
    sup_opts = build_opts(2, sup_vals)
    bench_opts = []
    for p in players:
        bench_opts.append(
            {
                "label": p,
                "value": p,
                "disabled": p in (set(tank_vals) | set(dmg_vals) | set(sup_vals)),
            }
        )

    map_opts = [{"label": m, "value": m} for m in maps]
    return tank_opts, dmg_opts, sup_opts, bench_opts, map_opts


@app.callback(
    Output("assign-tank", "value"),
    Output("assign-damage", "value"),
    Output("assign-support", "value"),
    Output("assign-bench", "value"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
)
def enforce_role_limits(tank_vals, dmg_vals, sup_vals, bench_vals):
    tank_vals = (tank_vals or [])[:1]
    dmg_vals = (dmg_vals or [])[:2]
    sup_vals = (sup_vals or [])[:2]
    bench_vals = bench_vals or []
    seen = set()

    def uniq(lst):
        out = []
        for x in lst:
            if x not in seen:
                out.append(x)
                seen.add(x)
        return out

    tank_vals = uniq(tank_vals)
    dmg_vals = uniq(dmg_vals)
    sup_vals = uniq(sup_vals)
    bench_vals = [b for b in bench_vals if b not in seen]
    return tank_vals, dmg_vals, sup_vals, bench_vals


@app.callback(
    Output("compare-switches-container", "children"),
    Input("player-dropdown", "value"),
    Input("lang-store", "data"),
)
def generate_comparison_switches(selected_player, lang_data):
    other_players = [p for p in constants.players if p != selected_player]
    if not other_players:
        return None
    lang = (lang_data or {}).get("lang", "en")
    switches = [html.Label(tr("compare_with", lang), className="fw-bold")]
    for player in other_players:
        switches.append(
            dbc.Switch(
                id={"type": "compare-switch", "player": player},
                label=player,
                value=False,
                className="mt-1",
            )
        )
    return switches


@app.callback(
    Output({"type": "compare-switch", "player": ALL}, "value"),
    Input("player-dropdown", "value"),
    State({"type": "compare-switch", "player": ALL}, "value"),
    prevent_initial_call=True,
)
def reset_compare_switches(selected_player, switch_values):
    return [False] * len(switch_values)


@app.callback(
    Output("map-view-type-container", "style"), Input("map-stat-type", "value")
)
def toggle_view_type_visibility(map_stat_type):
    if map_stat_type in ["winrate", "plays"]:
        return {"display": "block"}
    return {"display": "none"}


@app.callback(
    Output("min-games-slider", "disabled"),
    Output("slider-hint", "children"),
    Input("tabs", "active_tab"),
    Input("hero-stat-type", "value"),
    Input("role-stat-type", "value"),
    Input("map-stat-type", "value"),
)
def toggle_slider(tab, hero_stat, role_stat, map_stat):
    # Ensure robust defaults on initial render when dropdown values can be None
    hero_stat = hero_stat or "winrate"
    role_stat = role_stat or "winrate"
    map_stat = map_stat or "winrate"
    if (
        (tab == "tab-hero" and hero_stat == "winrate")
        or (tab == "tab-role" and role_stat == "winrate")
        or (tab == "tab-map" and map_stat in ["winrate", "gamemode", "attackdef"])
    ):
        return False, ""
    return True, "Nur relevant für Winrate-Statistiken"


@app.callback(
    Output("history-list-container", "children"),
    Output("history-display-count-store", "data"),
    Input("load-more-history-button", "n_clicks"),
    Input("history-display-count-store", "data"),
    Input("player-dropdown-match-verlauf", "value"),
    Input("hero-filter-dropdown-match", "value"),
    Input("dummy-output", "children"),
    State("history-display-count-store", "data"),
    State("history-load-amount-dropdown", "value"),
)
def update_history_display(
    n_clicks, store_data_in, player_name, hero_name, _, current_store, load_amount
):
    global df
    if df.empty:
        return [dbc.Alert("Keine Match History verfügbar.", color="danger")], {
            "count": 10
        }

    triggered_id = ctx.triggered_id if ctx.triggered_id else "dummy-output"

    # Reset count if filters change, otherwise increment
    if triggered_id in [
        "player-dropdown-match-verlauf",
        "hero-filter-dropdown-match",
        "dummy-output",
    ]:
        new_count = 10
    elif triggered_id == "history-display-count-store":
        # External update of count (e.g., from timeline click)
        new_count = int((store_data_in or {}).get("count", current_store.get("count", 10)))
    else:  # triggered by "load-more-history-button"
        new_count = current_store.get("count", 10) + load_amount

    filtered_df = df.copy()

    # Filter by player
    if player_name and player_name != "ALL":
        player_hero_col = f"{player_name} Hero"
        if player_hero_col in filtered_df.columns:
            # Filter for games the player participated in
            filtered_df = filtered_df[
                filtered_df[player_hero_col].notna()
                & (filtered_df[player_hero_col] != "nicht dabei")
            ]

            # Filter by hero for that specific player
            if hero_name:
                filtered_df = filtered_df[filtered_df[player_hero_col] == hero_name]

    # If a hero is selected but no specific player, filter for any player playing that hero
    elif hero_name and (not player_name or player_name == "ALL"):
        # Check all player hero columns
        hero_cols = [
            f"{p} Hero" for p in constants.players if f"{p} Hero" in filtered_df.columns
        ]
        # Create a boolean mask. True if any of the hero columns for a row equals the hero_name
        mask = filtered_df[hero_cols].eq(hero_name).any(axis=1)
        filtered_df = filtered_df[mask]

    games_to_show = filtered_df.head(new_count)
    history_layout = generate_history_layout_simple(games_to_show)

    if games_to_show.empty:
        history_layout = [
            dbc.Alert(
                "Für diese Filterkombination wurden keine Spiele gefunden.",
                color="info",
            )
        ]

    return history_layout, {"count": new_count}


# Jump from Daily timeline tile to the corresponding Match History card
@app.callback(
    Output("tabs", "active_tab", allow_duplicate=True),
    Output("history-display-count-store", "data", allow_duplicate=True),
    Output("url", "hash", allow_duplicate=True),
    Input({"type": "timeline-tile", "matchId": ALL}, "n_clicks"),
    State({"type": "timeline-tile", "matchId": ALL}, "id"),
    prevent_initial_call=True,
)
def on_timeline_tile_click(clicks, ids):
    # Find which tile was clicked
    if not clicks or not ids:
        raise PreventUpdate
    target_mid = None
    for c, ident in zip(clicks, ids):
        if (c or 0) > 0 and isinstance(ident, dict):
            mid = ident.get("matchId")
            if isinstance(mid, int) and mid > 0:
                target_mid = mid
                break
    if not target_mid:
        raise PreventUpdate

    # Ensure the target card exists within the current loaded count; if not, bump count to include it.
    # We assume history shows latest first (df sorted by Match ID desc); determine index of target.
    try:
        tmp = df.copy()
        if "Match ID" in tmp.columns:
            tmp["Match ID"] = pd.to_numeric(tmp["Match ID"], errors="coerce")
            tmp = tmp.sort_values("Match ID", ascending=False).reset_index(drop=True)
            pos = tmp.index[tmp["Match ID"] == target_mid]
            needed = int(pos[0]) + 1 if len(pos) else 10
        else:
            needed = 50
    except Exception:
        needed = 50

    # Cap to a reasonable chunk (multiples of 10)
    needed = int(((needed + 9) // 10) * 10)
    return "tab-history", {"count": needed}, f"#match-{target_mid}"


@app.callback(
    Output("hero-filter-dropdown-match", "options"),
    Output("hero-filter-dropdown-match", "value"),
    Input("player-dropdown-match-verlauf", "value"),
    Input("dummy-output", "children"),
    State("hero-filter-dropdown-match", "value"),
)
def update_match_history_hero_options(selected_player, _, current_hero):
    if df.empty:
        return [], None

    if not selected_player or selected_player == "ALL":
        # Show all heroes from all players if no player is selected
        all_heroes = set()
        for p in constants.players:
            hero_col = f"{p} Hero"
            if hero_col in df.columns:
                all_heroes.update(
                    df[df[hero_col].notna() & (df[hero_col] != "nicht dabei")][
                        hero_col
                    ].unique()
                )
        heroes = sorted(list(all_heroes))
    else:
        # Show heroes for the selected player
        player_hero_col = f"{selected_player} Hero"
        if player_hero_col in df.columns:
            heroes = sorted(
                df[
                    df[player_hero_col].notna() & (df[player_hero_col] != "nicht dabei")
                ][player_hero_col].unique()
            )
        else:
            heroes = []

    hero_options = []
    for hero in heroes:
        hero_options.append(
            {
                "label": html.Div(
                    [
                        html.Img(
                            src=get_hero_image_url(hero),
                            style={
                                "height": "25px",
                                "marginRight": "10px",
                                "borderRadius": "50%",
                            },
                        ),
                        html.Span(hero),
                    ],
                    style={"display": "flex", "alignItems": "center"},
                ),
                "value": hero,
            }
        )

    # Check if the current hero is still valid
    if current_hero and current_hero in heroes:
        return hero_options, current_hero

    return hero_options, None


@app.callback(
    Output("role-assign-result", "children"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
    Input("role-map-filter", "value"),
    Input("role-detailed-toggle", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input({"type": "detailed-hero", "player": ALL}, "value"),
    State({"type": "detailed-hero", "player": ALL}, "id"),
    Input("lang-store", "data"),
)
def compute_role_stats(
    tank_vals,
    dmg_vals,
    sup_vals,
    bench_vals,
    maps_selected,
    detail_on,
    season,
    month,
    year,
    hero_values,
    hero_ids,
    lang_data,
):
    lang = (lang_data or {}).get("lang", "en")
    # Normalize inputs to lists
    tank = tank_vals or []
    dmg = dmg_vals or []
    sup = sup_vals or []

    # Limits: allow partial selections
    if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
        return dbc.Alert(tr("too_many_players", lang), color="warning")
    if len(tank) + len(dmg) + len(sup) == 0:
        return dbc.Alert(tr("please_select_at_least_one_player", lang), color="info")

    # Uniqueness
    bench = bench_vals or []
    all_players = tank + dmg + sup + bench
    if len(set(all_players)) != len(all_players):
        return dbc.Alert(tr("duplicate_players_roles", lang), color="warning")

    global df
    if df.empty:
        return dbc.Alert(tr("no_data_loaded", lang), color="danger")

    # Apply timeframe filters
    temp = df.copy()
    # Apply map filter
    if maps_selected:
        temp = temp[temp["Map"].isin(maps_selected)]
        if temp.empty:
            return dbc.Alert(tr("no_data_selected_maps", lang), color="info")
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]
    if temp.empty:
        return dbc.Alert(tr("no_data_timeframe", lang), color="info")

    # Verify required columns
    required_cols = ["Win Lose", "Map"]
    for p in all_players:
        required_cols += [f"{p} Rolle", f"{p} Hero"]
    missing = [c for c in required_cols if c not in temp.columns]
    if missing:
        return dbc.Alert(
            tr("required_cols_missing", lang).format(cols=missing), color="danger"
        )

    # Build mask for chosen players only
    mask = pd.Series(True, index=temp.index)
    # Optional: aus Detailmodus gewählte Helden je Spieler
    selected_heroes = {}
    if detail_on:
        try:
            if hero_values is not None and hero_ids is not None:
                for vals, _id in zip(hero_values, hero_ids):
                    p = _id.get("player") if isinstance(_id, dict) else None
                    if p and vals:
                        selected_heroes[p] = set(vals)
        except Exception:
            selected_heroes = {}
    # Exclude bench players
    for p in bench:
        mask = mask & (temp[f"{p} Hero"].isna() | (temp[f"{p} Hero"] == "nicht dabei"))

    if len(tank) == 1:
        p = tank[0]
        mask = mask & temp[f"{p} Rolle"].eq("Tank")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in dmg:
        mask = mask & temp[f"{p} Rolle"].eq("Damage")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in sup:
        mask = mask & temp[f"{p} Rolle"].eq("Support")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])

    filtered = temp[mask]
    if filtered.empty:
        return dbc.Alert(tr("no_games_for_constellation", lang), color="info")

    counts = filtered["Win Lose"].value_counts()
    wins, losses = counts.get("Win", 0), counts.get("Lose", 0)
    total = wins + losses
    wr = wins / total if total else 0

    header_badge = dbc.Badge(
        f"{wr:.0%}",
        color=("success" if wr >= 0.5 else "danger" if total else "secondary"),
        className="ms-auto",
        pill=True,
    )

    role_pills = []
    if tank:
        role_pills.append(
            dbc.Badge(f"Tank: {', '.join(tank)}", color="primary", className="me-2")
        )
    if dmg:
        role_pills.append(
            dbc.Badge(f"Damage: {', '.join(dmg)}", color="info", className="me-2")
        )
    if sup:
        role_pills.append(dbc.Badge(f"Support: {', '.join(sup)}", color="success"))
    if bench:
        role_pills.append(
            dbc.Badge(
                f"{tr('bench_short', lang)}: {', '.join(bench)}",
                color="secondary",
                className="ms-2",
            )
        )

    # Optional: aktive Helden-Filter anzeigen
    hero_filters_block = None
    if selected_heroes:
        hero_lines = [
            html.Div(f"{p}: {', '.join(sorted(list(heroes)))}", className="small")
            for p, heroes in selected_heroes.items()
        ]
        hero_filters_block = html.Div(
            [
                html.Small(tr("heroes_filter", lang), className="text-muted d-block"),
                *hero_lines,
            ],
            className="mb-2",
        )

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [html.Strong(tr("role_config_stats", lang)), header_badge],
                    className="d-flex align-items-center",
                )
            ),
            dbc.CardBody(
                [
                    html.Div(role_pills, className="mb-2"),
                    hero_filters_block,
                    dbc.Row(
                        [
                            dbc.Col(
                                dbc.Card(
                                    [
                                        dbc.CardHeader(tr("games", lang)),
                                        dbc.CardBody(html.H4(f"{total}")),
                                    ],
                                    className="text-center h-100",
                                )
                            ),
                            dbc.Col(
                                dbc.Card(
                                    [
                                        dbc.CardHeader(tr("won", lang)),
                                        dbc.CardBody(
                                            html.H4(f"{wins}", className="text-success")
                                        ),
                                    ],
                                    className="text-center h-100",
                                )
                            ),
                            dbc.Col(
                                dbc.Card(
                                    [
                                        dbc.CardHeader(tr("lost", lang)),
                                        dbc.CardBody(
                                            html.H4(
                                                f"{losses}", className="text-danger"
                                            )
                                        ),
                                    ],
                                    className="text-center h-100",
                                )
                            ),
                            dbc.Col(
                                dbc.Card(
                                    [
                                        dbc.CardHeader(tr("winrate", lang)),
                                        dbc.CardBody(
                                            html.H4(
                                                f"{wr:.0%}", className="text-primary"
                                            )
                                        ),
                                    ],
                                    className="text-center h-100",
                                )
                            ),
                        ],
                        className="g-3",
                    ),
                ]
            ),
        ],
        className="mb-2",
    )


@app.callback(
    Output("role-assign-history", "children"),
    Input("role-history-count-store", "data"),
    Input("role-history-toggle", "value"),
    Input("role-detailed-toggle", "value"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
    Input("role-map-filter", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    State({"type": "detailed-hero", "player": ALL}, "value"),
    State({"type": "detailed-hero", "player": ALL}, "id"),
    Input("lang-store", "data"),
)
def show_role_assignment_history(
    count_store,
    show,
    detail_on,
    tank_vals,
    dmg_vals,
    sup_vals,
    bench_vals,
    maps_selected,
    season,
    month,
    year,
    hero_values,
    hero_ids,
    lang_data,
):
    lang = (lang_data or {}).get("lang", "en")
    if not show:
        return None
    # wie viele Einträge anzeigen
    display_count = 10
    try:
        if isinstance(count_store, dict):
            display_count = int(count_store.get("count", 10))
        elif isinstance(count_store, (int, float)):
            display_count = int(count_store)
    except Exception:
        display_count = 10
    tank = tank_vals or []
    dmg = dmg_vals or []
    sup = sup_vals or []
    bench = bench_vals or []

    if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
        return dbc.Alert(tr("too_many_players_history", lang), color="warning")

    all_players = tank + dmg + sup + bench
    if len(all_players) == 0:
        return dbc.Alert(tr("please_select_at_least_one_player", lang), color="info")
    if len(set(all_players)) != len(all_players):
        return dbc.Alert(tr("duplicate_players_roles", lang), color="warning")

    global df
    if df.empty:
        return dbc.Alert(tr("no_data_loaded", lang), color="danger")

    temp = df.copy()
    if maps_selected:
        temp = temp[temp["Map"].isin(maps_selected)]
        if temp.empty:
            return dbc.Alert(tr("no_data_selected_maps", lang), color="info")
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]
    if temp.empty:
        return dbc.Alert(tr("no_data_timeframe", lang), color="info")

    # Required columns
    for p in all_players:
        for c in [f"{p} Rolle", f"{p} Hero"]:
            if c not in temp.columns:
                return dbc.Alert(
                    tr("required_cols_missing", lang).format(cols=c), color="danger"
                )

    mask = pd.Series(True, index=temp.index)
    # Optional: aus Detailmodus gewählte Helden je Spieler
    selected_heroes = {}
    if detail_on:
        try:
            if hero_values is not None and hero_ids is not None:
                for vals, _id in zip(hero_values, hero_ids):
                    p = _id.get("player") if isinstance(_id, dict) else None
                    if p and vals:
                        selected_heroes[p] = set(vals)
        except Exception:
            selected_heroes = {}
    for p in bench:
        mask = mask & (temp[f"{p} Hero"].isna() | (temp[f"{p} Hero"] == "nicht dabei"))
    if len(tank) == 1:
        p = tank[0]
        mask = mask & temp[f"{p} Rolle"].eq("Tank")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in dmg:
        mask = mask & temp[f"{p} Rolle"].eq("Damage")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in sup:
        mask = mask & temp[f"{p} Rolle"].eq("Support")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])

    full_subset = temp[mask].copy()
    total_full = len(full_subset)
    # Sortiere nach Match ID absteigend, falls vorhanden, und slice nach display_count
    if "Match ID" in full_subset.columns:
        full_subset.sort_values("Match ID", ascending=False, inplace=True)
    subset = full_subset.head(display_count)
    if subset.empty:
        return dbc.Alert(tr("no_matching_matches", lang), color="info")

    # Kompakte Liste mit Map-Thumbnail, Ergebnis-Badge und Spielerlinien
    # Ermittele alle bekannten Spieler aus den Spaltennamen (robust ggü. constants.players)
    known_players = sorted(
        {
            c.replace(" Hero", "").replace(" Rolle", "")
            for c in full_subset.columns
            if c.endswith(" Hero") or c.endswith(" Rolle")
        }
    )
    items = []
    for _, row in subset.iterrows():
        map_name = row.get("Map", tr("unknown_map", lang))
        map_img = get_map_image_url(map_name)
        date_str = (
            row["Datum"].strftime("%d.%m.%Y")
            if "Datum" in subset.columns and pd.notna(row.get("Datum"))
            else tr("invalid_date", lang)
        )
        result = row.get("Win Lose")
        badge = dbc.Badge(
            tr("victory", lang) if result == "Win" else tr("defeat", lang),
            color=("success" if result == "Win" else "danger"),
            className="ms-2",
        )
        role_lines = []
        for p in tank:
            role_lines.append(
                html.Div(f"Tank: {p} • {row.get(f'{p} Hero', '—')}", className="small")
            )
        for p in dmg:
            role_lines.append(
                html.Div(
                    f"Damage: {p} • {row.get(f'{p} Hero', '—')}", className="small"
                )
            )
        for p in sup:
            role_lines.append(
                html.Div(
                    f"Support: {p} • {row.get(f'{p} Hero', '—')}", className="small"
                )
            )

        # Unzugeordnete, aber aktive Spieler (nicht auf der Bank) ebenfalls anzeigen
        selected_and_bench = set(
            (tank or []) + (dmg or []) + (sup or []) + (bench or [])
        )
        other_players = [p for p in known_players if p not in selected_and_bench]
        for p in other_players:
            hero_val = row.get(f"{p} Hero")
            role_val = row.get(f"{p} Rolle")
            if pd.notna(hero_val) and hero_val != "nicht dabei":
                role_label = (
                    role_val
                    if isinstance(role_val, str) and role_val
                    else tr("role_label", lang)
                )
                role_lines.append(
                    html.Div(f"{role_label}: {p} • {hero_val}", className="small")
                )

        items.append(
            dbc.ListGroupItem(
                dbc.Row(
                    [
                        dbc.Col(
                            html.Img(
                                src=map_img,
                                style={
                                    "width": "120px",
                                    "height": "60px",
                                    "objectFit": "cover",
                                    "borderRadius": "6px",
                                },
                            ),
                            width=2,
                        ),
                        dbc.Col(
                            [
                                html.Div(
                                    [
                                        html.Strong(map_name),
                                        html.Span(
                                            f" • {date_str}",
                                            className="text-muted",
                                            style={"marginLeft": "6px"},
                                        ),
                                        badge,
                                    ],
                                    className="d-flex align-items-center",
                                ),
                                html.Div(role_lines),
                            ]
                        ),
                    ],
                    className="align-items-center",
                )
            )
        )
    components = [dbc.ListGroup(items, flush=True)]
    # Hinweis wenn Ende erreicht
    if display_count >= total_full:
        components.append(
            html.Div(
                tr("no_more_entries", lang),
                className="text-muted small mt-2",
            )
        )

    return html.Div(components)


@app.callback(
    Output("role-history-count-store", "data"),
    Input("role-history-load-more", "n_clicks"),
    Input("role-history-toggle", "value"),
    Input("role-detailed-toggle", "value"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
    Input("role-map-filter", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input({"type": "detailed-hero", "player": ALL}, "value"),
    State("role-history-count-store", "data"),
    State("role-history-load-amount-dropdown", "value"),
)
def update_role_history_count(
    n_clicks,
    toggle,
    detail_on,
    tank_vals,
    dmg_vals,
    sup_vals,
    bench_vals,
    maps_selected,
    season,
    month,
    year,
    detailed_hero_values,
    current_store,
    load_amount,
):
    # Basiswert
    base = 10
    if not isinstance(current_store, dict):
        current_store = {"count": base}

    triggered = ctx.triggered_id

    # Reset bei Filter-/Toggle-Änderungen oder wenn Toggle aus ist
    reset_triggers = {
        "role-history-toggle",
        "role-detailed-toggle",
        "assign-tank",
        "assign-damage",
        "assign-support",
        "assign-bench",
        "role-map-filter",
        "season-dropdown",
        "month-dropdown",
        "year-dropdown",
    }

    if not toggle:
        return {"count": base}

    if isinstance(triggered, dict) or triggered in reset_triggers:
        return {"count": base}

    # Nur erhöhen, wenn Button geklickt wurde und Toggle an ist
    if triggered == "role-history-load-more" and toggle:
        step = load_amount or base
        try:
            step = int(step)
        except Exception:
            step = base
        new_count = int(current_store.get("count", base)) + step
        return {"count": new_count}

    # Fallback: unverändert
    return current_store


@app.callback(
    Output("role-history-load-more", "disabled"),
    Output("role-history-load-amount-dropdown", "disabled"),
    Input("role-history-toggle", "value"),
    Input("role-history-count-store", "data"),
    Input("role-detailed-toggle", "value"),
    Input("assign-tank", "value"),
    Input("assign-damage", "value"),
    Input("assign-support", "value"),
    Input("assign-bench", "value"),
    Input("role-map-filter", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    State({"type": "detailed-hero", "player": ALL}, "value"),
    State({"type": "detailed-hero", "player": ALL}, "id"),
)
def toggle_role_history_controls(
    show_history,
    count_store,
    detail_on,
    tank_vals,
    dmg_vals,
    sup_vals,
    bench_vals,
    maps_selected,
    season,
    month,
    year,
    hero_values,
    hero_ids,
):
    # Dropdown (Menge) bleibt nur vom Toggle abhängig
    dropdown_disabled = not bool(show_history)
    # Button ist aus, wenn Toggle aus oder alle Einträge gezeigt werden
    if not show_history:
        return True, dropdown_disabled

    # Anzeigeanzahl ermitteln
    display_count = 10
    try:
        if isinstance(count_store, dict):
            display_count = int(count_store.get("count", 10))
        elif isinstance(count_store, (int, float)):
            display_count = int(count_store)
    except Exception:
        display_count = 10

    tank = tank_vals or []
    dmg = dmg_vals or []
    sup = sup_vals or []
    bench = bench_vals or []

    global df
    if df.empty:
        # Keine Daten -> Button ausblenden
        return True, dropdown_disabled

    temp = df.copy()
    # Apply map filter first
    if maps_selected:
        temp = temp[temp["Map"].isin(maps_selected)]
        if temp.empty:
            return True, dropdown_disabled
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]

    if temp.empty:
        return True, dropdown_disabled

    all_players = tank + dmg + sup + bench
    # Spaltenprüfung
    for p in all_players:
        for c in [f"{p} Rolle", f"{p} Hero"]:
            if c not in temp.columns:
                return True, dropdown_disabled

    mask = pd.Series(True, index=temp.index)
    selected_heroes = {}
    if detail_on:
        try:
            if hero_values is not None and hero_ids is not None:
                for vals, _id in zip(hero_values, hero_ids):
                    p = _id.get("player") if isinstance(_id, dict) else None
                    if p and vals:
                        selected_heroes[p] = set(vals)
        except Exception:
            selected_heroes = {}

    # Exclude bench players
    for p in bench:
        mask = mask & (temp[f"{p} Hero"].isna() | (temp[f"{p} Hero"] == "nicht dabei"))

    if len(tank) == 1:
        p = tank[0]
        mask = mask & temp[f"{p} Rolle"].eq("Tank")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in dmg:
        mask = mask & temp[f"{p} Rolle"].eq("Damage")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
    for p in sup:
        mask = mask & temp[f"{p} Rolle"].eq("Support")
        mask = mask & temp[f"{p} Hero"].notna() & (temp[f"{p} Hero"] != "nicht dabei")
        if p in selected_heroes:
            mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])

    total_full = int(mask.sum())
    # Button deaktivieren, wenn nichts mehr zu laden ist
    button_disabled = display_count >= total_full or total_full == 0
    return button_disabled, dropdown_disabled


@app.callback(
    Output("map-stat-container", "children"),
    Output("hero-stat-graph", "figure"),
    Output("role-stat-graph", "figure"),
    Output("performance-heatmap", "figure"),
    Output("stats-header", "children"),
    Output("stats-container", "children"),
    Output("winrate-over-time", "figure"),
    Output("hero-filter-dropdown", "options"),
    Input("player-dropdown", "value"),
    Input("min-games-slider", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input("hero-filter-dropdown", "value"),
    Input("hero-stat-type", "value"),
    Input("role-stat-type", "value"),
    Input("map-stat-type", "value"),
    Input("map-view-type", "value"),
    Input({"type": "compare-switch", "player": ALL}, "value"),
    State({"type": "compare-switch", "player": ALL}, "id"),
    Input("dummy-output", "children"),
    Input("server-update-token", "data"),
    Input("theme-store", "data"),
    Input("lang-store", "data"),
)
def update_all_graphs(
    player,
    min_games,
    season,
    month,
    year,
    hero_filter,
    hero_stat_type,
    role_stat_type,
    map_stat_type,
    map_view_type,
    compare_values,
    compare_ids,
    _,
    _server_token,
    theme_data,
    lang_data,
):
    # Theme helper for figures
    dark = bool((theme_data or {}).get("dark", False))

    # Robust defaults in case dropdown values are None during initial render or race conditions
    map_stat_type = map_stat_type or "winrate"
    hero_stat_type = hero_stat_type or "winrate"
    role_stat_type = role_stat_type or "winrate"
    map_view_type = bool(map_view_type)

    def style_fig(fig: go.Figure):
        if not isinstance(fig, go.Figure):
            return fig
        template = "plotly_dark" if dark else "plotly_white"
        paper = "#151925" if dark else "#ffffff"
        plot = paper
        layout_kwargs = {
            "template": template,
            "paper_bgcolor": paper,
            "plot_bgcolor": plot,
        }
        if dark:
            layout_kwargs["font_color"] = "#e5e7eb"
        fig.update_layout(**layout_kwargs)
        return fig

    dataframes = {player: filter_data(player, season, month, year)}
    active_compare_players = []
    if compare_ids:
        for i, is_on in enumerate(compare_values):
            if is_on:
                p_name = compare_ids[i]["player"]
                active_compare_players.append(p_name)
                dataframes[p_name] = filter_data(p_name, season, month, year)
    main_df = dataframes[player]
    title_suffix = f"({player}{' vs ' + ', '.join(active_compare_players) if active_compare_players else ''})"
    # Use i18n for empty figure title
    lang_for_text = (lang_data or {}).get("lang", "en")
    empty_fig = go.Figure(layout={"title": tr("no_data_selection", lang_for_text)})
    empty_fig = style_fig(empty_fig)
    # Localize statistics header
    stats_header = f"{tr('stats_header', lang_for_text)} ({player})"

    stats_container = html.Div(tr("no_data_selection", lang_for_text))
    if not main_df.empty:
        total, wins = len(main_df), len(main_df[main_df["Win Lose"] == "Win"])
        losses, winrate = total - wins, wins / total if total > 0 else 0

        # --- REVISED: Primary Stats Row with subtle colors ---
        primary_stats_row = dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(tr("total_games", lang_for_text)),
                            dbc.CardBody(html.H4(f"{total}")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(tr("won", lang_for_text)),
                            dbc.CardBody(html.H4(f"{wins}", className="text-success")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(tr("lost", lang_for_text)),
                            dbc.CardBody(html.H4(f"{losses}", className="text-danger")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(tr("winrate", lang_for_text)),
                            dbc.CardBody(
                                html.H4(f"{winrate:.0%}", className="text-primary")
                            ),
                        ],
                        className="text-center h-100",
                    )
                ),
            ],
            className="mb-4",  # Add margin to separate the rows
        )

        # --- Row 2: "Best Of" Stats (no changes here) ---
        secondary_stat_cards = []
        try:
            most_played_hero = main_df["Hero"].mode()[0]
            hero_plays = main_df["Hero"].value_counts()[most_played_hero]
            card = create_stat_card(
                tr("most_played_hero", lang_for_text),
                get_hero_image_url(most_played_hero),
                most_played_hero,
                f"{hero_plays} {tr('games', lang_for_text)}",
            )
        except (KeyError, IndexError):
            card = create_stat_card(
                tr("most_played_hero", lang_for_text),
                get_hero_image_url(None),
                "N/A",
                tr("no_data", lang_for_text),
            )
        secondary_stat_cards.append(card)
        try:
            hero_wr = calculate_winrate(main_df, "Hero")
            hero_wr_filtered = hero_wr[hero_wr["Spiele"] >= min_games]
            best_hero = hero_wr_filtered.loc[hero_wr_filtered["Winrate"].idxmax()]
            card = create_stat_card(
                tr("best_wr_hero", lang_for_text),
                get_hero_image_url(best_hero["Hero"]),
                best_hero["Hero"],
                f"{best_hero['Winrate']:.0%} ({best_hero['Spiele']} {tr('games', lang_for_text)})",
            )
        except (KeyError, IndexError, ValueError):
            card = create_stat_card(
                tr("best_wr_hero", lang_for_text),
                get_hero_image_url(None),
                "N/A",
                tr("min_n_games", lang_for_text).format(n=min_games),
            )
        secondary_stat_cards.append(card)
        try:
            most_played_map = main_df["Map"].mode()[0]
            map_plays = main_df["Map"].value_counts()[most_played_map]
            card = create_stat_card(
                tr("most_played_map", lang_for_text),
                get_map_image_url(most_played_map),
                most_played_map,
                f"{map_plays} {tr('games', lang_for_text)}",
            )
        except (KeyError, IndexError):
            card = create_stat_card(
                tr("most_played_map", lang_for_text),
                get_map_image_url(None),
                "N/A",
                tr("no_data", lang_for_text),
            )
        secondary_stat_cards.append(card)
        try:
            map_wr = calculate_winrate(main_df, "Map")
            map_wr_filtered = map_wr[map_wr["Spiele"] >= min_games]
            best_map = map_wr_filtered.loc[map_wr_filtered["Winrate"].idxmax()]
            card = create_stat_card(
                tr("best_wr_map", lang_for_text),
                get_map_image_url(best_map["Map"]),
                best_map["Map"],
                f"{best_map['Winrate']:.0%} ({best_map['Spiele']} {tr('games', lang_for_text)})",
            )
        except (KeyError, IndexError, ValueError):
            card = create_stat_card(
                tr("best_wr_map", lang_for_text),
                get_map_image_url(None),
                "N/A",
                tr("min_n_games", lang_for_text).format(n=min_games),
            )
        secondary_stat_cards.append(card)

        stats_container = html.Div([primary_stats_row, dbc.Row(secondary_stat_cards)])

    # (The rest of the function remains completely unchanged)
    map_stat_output = None

    # Localized translation with defaults helper
    def trd(key, de_default, en_default):
        v = tr(key, lang_for_text)
        return v if v != key else (de_default if lang_for_text == "de" else en_default)

    attack_def_modes = ["Attack", "Defense", "Attack Attack"]
    bar_fig = go.Figure()
    if (
        map_view_type
        and not active_compare_players
        and map_stat_type in ["winrate", "plays"]
    ):
        if map_stat_type == "winrate":
            map_data = calculate_winrate(main_df, "Map")
            map_data = map_data[map_data["Spiele"] >= min_games]
            if not map_data.empty:
                plot_df = main_df[main_df["Attack Def"].isin(attack_def_modes)].copy()
                overall_label = trd("overall", "Gesamt", "Overall")
                plot_df["Mode"] = plot_df["Attack Def"].replace(
                    {"Attack Attack": overall_label}
                )
                grouped = (
                    plot_df.groupby(["Map", "Mode", "Win Lose"])
                    .size()
                    .unstack(fill_value=0)
                )
                if "Win" not in grouped:
                    grouped["Win"] = 0
                if "Lose" not in grouped:
                    grouped["Lose"] = 0
                grouped["Spiele"] = grouped["Win"] + grouped["Lose"]
                grouped["Winrate"] = grouped["Win"] / grouped["Spiele"]
                plot_data = grouped.reset_index()
                plot_data = plot_data[plot_data["Map"].isin(map_data["Map"])]
                if not plot_data.empty:
                    # Localized labels
                    detailed_label = trd("detailed", "Detailliert", "Detailed")
                    bar_fig = px.bar(
                        plot_data,
                        x="Map",
                        y="Winrate",
                        color="Mode",
                        barmode="group",
                        title=f"{tr('winrate', lang_for_text)} {tr('by', lang_for_text)} {tr('map_label', lang_for_text)} ({detailed_label}) - {player}",
                        category_orders={
                            "Map": map_data["Map"].tolist(),
                            "Mode": [overall_label, "Attack", "Defense"],
                        },
                        custom_data=["Spiele", "Win", "Lose"],
                        color_discrete_map={
                            overall_label: "lightslategrey",
                            "Attack": "#EF553B",
                            "Defense": "#636EFA",
                        },
                    )
                    bar_fig.update_traces(
                        hovertemplate=(
                            f"{tr('winrate', lang_for_text)}: %{{y:.1%}}"
                            f"<br>{tr('games', lang_for_text)}: %{{customdata[0]}}"
                            f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                            f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                        )
                    )
                    bar_fig.update_layout(yaxis_tickformat=".0%")
                else:
                    bar_fig = empty_fig
            else:
                bar_fig = empty_fig
        elif map_stat_type == "plays":
            if not main_df.empty:
                plot_df = main_df.copy()
                plot_df["Seite"] = plot_df["Attack Def"].apply(
                    lambda x: x if x in attack_def_modes else "Andere Modi"
                )
                plays_by_side = (
                    plot_df.groupby(["Map", "Seite"]).size().reset_index(name="Spiele")
                )
                total_plays_map = (
                    main_df.groupby("Map")
                    .size()
                    .reset_index(name="TotalSpiele")
                    .sort_values("TotalSpiele", ascending=False)
                )
                detailed_label = trd("detailed", "Detailliert", "Detailed")
                bar_fig = px.bar(
                    plays_by_side,
                    x="Map",
                    y="Spiele",
                    color="Seite",
                    barmode="stack",
                    title=f"{tr('games', lang_for_text)} {tr('by', lang_for_text)} {tr('map_label', lang_for_text)} ({detailed_label}) - {player}",
                    labels={
                        "Spiele": tr("games", lang_for_text),
                        "Seite": tr("side", lang_for_text),
                    },
                    category_orders={"Map": list(total_plays_map["Map"])},
                    color_discrete_map={
                        "Attack": "#EF553B",
                        "Defense": "#00CC96",
                        "Attack Attack": "#636EFA",
                    },
                )
                bar_fig.update_traces(
                    hovertemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>"
                )
            else:
                bar_fig = empty_fig
    else:
        group_col = {
            "winrate": "Map",
            "plays": "Map",
            "gamemode": "Gamemode",
            "attackdef": "Attack Def",
        }.get(map_stat_type)
        y_col = (
            "Winrate"
            if map_stat_type in ["winrate", "gamemode", "attackdef"]
            else "Spiele"
        )
        for name, df_to_plot in dataframes.items():
            if not df_to_plot.empty and group_col and group_col in df_to_plot.columns:
                if y_col == "Winrate":
                    stats = calculate_winrate(df_to_plot, group_col)
                    stats = stats[stats["Spiele"] >= min_games]
                    if not stats.empty:
                        bar_fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                customdata=stats[["Spiele", "Win", "Lose"]],
                                hovertemplate=(
                                    f"<b>%{{x}}</b><br>{tr('winrate', lang_for_text)}: %{{y:.1%}}"
                                    f"<br>{tr('games', lang_for_text)}: %{{customdata[0]}}"
                                    f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                                    f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                                ),
                            )
                        )
                else:
                    stats = (
                        df_to_plot.groupby(group_col)
                        .size()
                        .reset_index(name="Spiele")
                        .sort_values("Spiele", ascending=False)
                    )
                    if not stats.empty:
                        bar_fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                hovertemplate=f"<b>%{{x}}</b><br>{tr('games', lang_for_text)}: %{{y}}<extra></extra>",
                            )
                        )
        # Build a safe, human-friendly title even if something was None previously
        safe_map_title = (map_stat_type or "winrate").title().replace("def", "Def")
        # Localize title/group labels
        group_label_local = {
            "Map": tr("map_label", lang_for_text),
            "Gamemode": tr("gamemode_label", lang_for_text),
            "Attack Def": tr("attackdef_label", lang_for_text),
        }.get(group_col, group_col)
        stat_label_local = (
            tr("winrate", lang_for_text)
            if y_col == "Winrate"
            else tr("games", lang_for_text)
        )
        bar_fig.update_layout(
            title=f"{stat_label_local} {tr('by', lang_for_text)} {group_label_local} {title_suffix}",
            barmode="group",
            yaxis_title=stat_label_local,
            legend_title=tr("players", lang_for_text),
        )
        if y_col == "Winrate":
            bar_fig.update_layout(yaxis_tickformat=".0%")
        if not bar_fig.data:
            bar_fig = empty_fig
    if map_stat_type == "winrate":
        map_stat_output = dbc.Row(
            dbc.Col(dcc.Graph(figure=style_fig(bar_fig)), width=12)
        )
    else:
        pie_fig = go.Figure()
        pie_data_col = None
        if map_stat_type == "gamemode":
            pie_data_col = "Gamemode"
        elif map_stat_type == "attackdef":
            pie_data_col = "Attack Def"
        if pie_data_col:
            pie_data = main_df.copy()
            if pie_data_col == "Attack Def":
                pie_data = pie_data[pie_data["Attack Def"].isin(attack_def_modes)]
            pie_data = pie_data.groupby(pie_data_col).size().reset_index(name="Spiele")
            if not pie_data.empty:
                pie_fig = px.pie(
                    pie_data,
                    names=pie_data_col,
                    values="Spiele",
                    title=f"{tr('distribution', lang_for_text)} {({'Gamemode': tr('gamemode_label', lang_for_text), 'Attack Def': tr('attackdef_label', lang_for_text)}.get(pie_data_col, pie_data_col))}",
                )
                pie_fig.update_traces(
                    hovertemplate=(
                        f"<b>%{{label}}</b><br>{tr('games', lang_for_text)}: %{{value}}<br>"
                        f"{'Anteil' if lang_for_text=='de' else 'Share'}: %{{percent}}<extra></extra>"
                    )
                )
            else:
                pie_fig = empty_fig
        if map_stat_type == "plays":
            map_stat_output = dbc.Row(
                [dbc.Col(dcc.Graph(figure=style_fig(bar_fig)), width=12)]
            )
        else:
            map_stat_output = dbc.Row(
                [
                    dbc.Col(dcc.Graph(figure=style_fig(bar_fig)), width=7),
                    dbc.Col(dcc.Graph(figure=style_fig(pie_fig)), width=5),
                ]
            )

    def create_comparison_fig(stat_type, group_col):
        fig = go.Figure()
        y_col = "Winrate" if stat_type == "winrate" else "Spiele"
        for name, df_to_plot in dataframes.items():
            if not df_to_plot.empty:
                if y_col == "Winrate":
                    stats = calculate_winrate(df_to_plot, group_col)
                    stats = stats[stats["Spiele"] >= min_games]
                    if not stats.empty:
                        fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                customdata=stats[["Spiele", "Win", "Lose"]],
                                hovertemplate=(
                                    f"<b>%{{x}}</b><br>{tr('winrate', lang_for_text)}: %{{y:.1%}}"
                                    f"<br>{tr('games', lang_for_text)}: %{{customdata[0]}}"
                                    f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                                    f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                                ),
                            )
                        )
                else:
                    stats = (
                        df_to_plot.groupby(group_col)
                        .size()
                        .reset_index(name="Spiele")
                        .sort_values("Spiele", ascending=False)
                    )
                    if not stats.empty:
                        fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                hovertemplate=f"<b>%{{x}}</b><br>{tr('games', lang_for_text)}: %{{y}}<extra></extra>",
                            )
                        )
        group_label_local = {
            "Hero": tr("hero_label", lang_for_text),
            "Rolle": tr("role_label", lang_for_text),
            "Map": tr("map_label", lang_for_text),
        }.get(group_col, group_col)
        stat_label_local = (
            tr("winrate", lang_for_text)
            if y_col == "Winrate"
            else tr("games", lang_for_text)
        )
        fig.update_layout(
            title=f"{stat_label_local} {tr('by', lang_for_text)} {group_label_local} {title_suffix}",
            barmode="group",
            yaxis_title=stat_label_local,
            legend_title=tr("players", lang_for_text),
        )
        if y_col == "Winrate":
            fig.update_layout(yaxis_tickformat=".0%")
        return fig if fig.data else empty_fig

    hero_fig = create_comparison_fig(hero_stat_type, "Hero")
    role_fig = create_comparison_fig(role_stat_type, "Rolle")
    heatmap_fig = empty_fig
    if not main_df.empty:
        try:
            pivot = main_df.pivot_table(
                index="Rolle",
                columns="Map",
                values="Win Lose",
                aggfunc=lambda x: (x == "Win").sum() / len(x) if len(x) > 0 else 0,
            )
            if not pivot.empty:
                heatmap_fig = px.imshow(
                    pivot,
                    text_auto=".0%",
                    color_continuous_scale="RdYlGn",
                    zmin=0,
                    zmax=1,
                    aspect="auto",
                    title=f"{tr('winrate', lang_for_text)} Heatmap – {player}",
                )
                # Zusatzdaten für Tooltip: Spiele, Gewonnen, Verloren
                try:
                    total_pivot = (
                        main_df.pivot_table(
                            index="Rolle",
                            columns="Map",
                            values="Win Lose",
                            aggfunc="count",
                        )
                        .reindex(index=pivot.index, columns=pivot.columns)
                        .fillna(0)
                        .astype(int)
                    )
                    wins_pivot = (
                        main_df.pivot_table(
                            index="Rolle",
                            columns="Map",
                            values="Win Lose",
                            aggfunc=lambda x: (x == "Win").sum(),
                        )
                        .reindex(index=pivot.index, columns=pivot.columns)
                        .fillna(0)
                        .astype(int)
                    )
                    losses_pivot = (total_pivot - wins_pivot).astype(int)
                    customdata = [
                        [
                            [
                                int(total_pivot.iloc[i, j]),
                                int(wins_pivot.iloc[i, j]),
                                int(losses_pivot.iloc[i, j]),
                            ]
                            for j in range(total_pivot.shape[1])
                        ]
                        for i in range(total_pivot.shape[0])
                    ]
                    heatmap_fig.data[0].customdata = customdata
                    heatmap_fig.update_traces(
                        hovertemplate=(
                            f"<b>{tr('map_label', lang_for_text)}: %{{x}}</b><br><b>{trd('role_label','Rolle','Role')}: %{{y}}</b>"
                            f"<br><b>{tr('winrate', lang_for_text)}: %{{z: .1%}}</b>"
                            f"<br>{tr('games', lang_for_text)}: %{{customdata[0]}}"
                            f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                            f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                        )
                    )
                except Exception:
                    # Fallback: nur Winrate anzeigen
                    heatmap_fig.update_traces(
                        hovertemplate=(
                            f"<b>{tr('map_label', lang_for_text)}: %{{x}}</b><br><b>{trd('role_label','Rolle','Role')}: %{{y}}</b>"
                            f"<br><b>{tr('winrate', lang_for_text)}: %{{z: .1%}}</b><extra></extra>"
                        )
                    )
        except Exception:
            pass
    winrate_fig = go.Figure()
    for name, df_to_plot in dataframes.items():
        if not df_to_plot.empty and "Datum" in df_to_plot.columns:
            time_data = df_to_plot.dropna(subset=["Datum"]).copy()
            time_data.sort_values("Datum", inplace=True, ascending=True)
            if hero_filter:
                time_data = time_data[time_data["Hero"] == hero_filter]
            if not time_data.empty:
                time_data["Win"] = (time_data["Win Lose"] == "Win").astype(int)
                time_data["GameNum"] = range(1, len(time_data) + 1)
                time_data["CumulativeWinrate"] = (
                    time_data["Win"].cumsum() / time_data["GameNum"]
                )
                time_data["CumWins"] = time_data["Win"].cumsum()
                time_data["CumLosses"] = time_data["GameNum"] - time_data["CumWins"]
                winrate_fig.add_trace(
                    go.Scatter(
                        x=time_data["GameNum"],
                        y=time_data["CumulativeWinrate"],
                        mode="lines",
                        name=name,
                        customdata=time_data[["CumWins", "CumLosses"]].values,
                    )
                )
    winrate_fig.update_layout(
        title=f"{trd('trend','Winrate-Verlauf','Winrate Trend')} {title_suffix}",
        yaxis_tickformat=".0%",
        yaxis_title=tr("winrate", lang_for_text),
        xaxis_title=tr("game_number", lang_for_text),
        legend_title=tr("players", lang_for_text),
    )
    winrate_fig.update_traces(
        hovertemplate=(
            f"<b>{tr('game_number', lang_for_text)}: %{{x}}</b>"
            f"<br><b>{tr('winrate', lang_for_text)}: %{{y: .1%}}</b>"
            f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[0]}}"
            f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[1]}}<extra></extra>"
        )
    )
    if not winrate_fig.data:
        winrate_fig = empty_fig
    # Apply theme to the main figures
    hero_fig = style_fig(hero_fig)
    role_fig = style_fig(role_fig)
    heatmap_fig = style_fig(heatmap_fig)
    winrate_fig = style_fig(winrate_fig)

    hero_options = []
    if not main_df.empty:
        heroes = sorted(main_df["Hero"].dropna().unique())
        for hero in heroes:
            hero_options.append(
                {
                    "label": html.Div(
                        [
                            html.Img(
                                src=get_hero_image_url(hero),
                                style={
                                    "height": "25px",
                                    "marginRight": "10px",
                                    "borderRadius": "50%",
                                },
                            ),
                            html.Span(hero),
                        ],
                        style={"display": "flex", "alignItems": "center"},
                    ),
                    "value": hero,
                }
            )

    return (
        map_stat_output,
        hero_fig,
        role_fig,
        heatmap_fig,
        stats_header,
        stats_container,
        winrate_fig,
        hero_options,
    )


# --- Live online counter callbacks ---
@app.callback(
    Output("client-id", "data"),
    Input("client-init", "n_intervals"),
    State("client-id", "data"),
    prevent_initial_call=False,
)
def _init_client_id(_, existing):
    # Keep existing id in session storage to avoid creating duplicates on reload
    if existing:
        # Also ensure it is marked active immediately
        _upsert_heartbeat(existing)
        return existing
    try:
        sid = str(uuid.uuid4())
    except Exception:
        sid = str(time.time_ns())
    # Immediate heartbeat so the counter reflects this session right away
    _upsert_heartbeat(sid)
    return sid


@app.callback(
    Output("heartbeat-dummy", "children"),
    Input("heartbeat", "n_intervals"),
    State("client-id", "data"),
)
def _heartbeat(_n, session_id):
    _upsert_heartbeat(session_id)
    return str(int(time.time()))


@app.callback(
    Output("online-counter", "children"),
    Input("active-count-refresh", "n_intervals"),
    Input("lang-store", "data"),
    Input("client-id", "data"),
)
def _update_online_counter(_n, lang_data, _sid):
    lang = (lang_data or {}).get("lang", "en")
    count = _count_active()
    return f"{tr('online_now', lang)}: {count}"


if __name__ == "__main__":
    app.run(debug=False)
