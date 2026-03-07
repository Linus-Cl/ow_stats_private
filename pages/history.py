"""
pages/history.py
================
Callbacks and helpers for the Match History tab.
"""

from __future__ import annotations

import re

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, ctx, html, no_update
from dash.exceptions import PreventUpdate

import config
from data import loader
from utils.assets import get_hero_image_url, get_map_image_url
from utils.formatting import (
    format_duration_display,
    format_season_display,
    format_time_display,
    parse_duration,
    parse_time,
)
from utils.i18n import tr


# ---------------------------------------------------------------------------
# History card builder
# ---------------------------------------------------------------------------


def generate_history_layout_simple(
    games_df: pd.DataFrame,
    lang: str = "en",
) -> list:
    """Build a list of ``dbc.Card`` elements for each match in *games_df*."""
    if games_df.empty:
        return [dbc.Alert(tr("no_history", lang), color="info")]

    history_items: list = []
    last_season = None

    for _idx, game in games_df.iterrows():
        if pd.isna(game.get("Map")):
            continue

        # Season separator
        current_season = game.get("Season")
        if pd.notna(current_season) and current_season != last_season:
            history_items.append(
                dbc.Alert(
                    format_season_display(current_season),
                    color="secondary",
                    className="my-4 text-center fw-bold",
                )
            )
            last_season = current_season

        map_name = game.get("Map", tr("unknown_map", lang))
        gamemode = game.get("Gamemode", "")
        att_def = game.get("Attack Def")
        map_image_url = get_map_image_url(map_name)
        date_str = (
            game["Datum"].strftime("%d.%m.%Y")
            if pd.notna(game.get("Datum"))
            else tr("invalid_date", lang)
        )
        result_color, result_text = (
            ("success", "VICTORY")
            if game.get("Win Lose") == "Win"
            else ("danger", "DEFEAT")
        )

        time_str = parse_time(game)
        dur_str = parse_duration(game)
        time_disp = format_time_display(time_str, lang)
        dur_disp = format_duration_display(dur_str)

        parts = [str(gamemode).strip() or "", date_str]
        if time_disp:
            parts.append(time_disp)
        # Omit "Attack Attack" (symmetric maps have no real attack/defense side)
        # and any residual "N/A" values – users don't need to see those.
        _ad = str(att_def).strip() if pd.notna(att_def) else ""
        if _ad and _ad.lower() not in ("attack attack", "n/a", "na", ""):
            parts.append(_ad)
        att_def_string = " • ".join(p for p in parts if p)

        # Player list
        player_list_items = []
        for p in config.PLAYERS:
            hero = game.get(f"{p} Hero")
            if pd.notna(hero) and hero != "nicht dabei":
                role = game.get(f"{p} Rolle", "N/A")
                player_list_items.append(
                    dbc.ListGroupItem(
                        html.Div(
                            [
                                html.Img(
                                    src=get_hero_image_url(hero),
                                    style={
                                        "width": "40px",
                                        "height": "40px",
                                        "borderRadius": "50%",
                                        "objectFit": "cover",
                                        "marginRight": "15px",
                                    },
                                ),
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
                                    className="d-flex justify-content-between align-items-center w-100",
                                ),
                            ],
                            className="d-flex align-items-center",
                        )
                    )
                )

        # Card anchor
        anchor_id = None
        try:
            if pd.notna(game.get("Match ID")):
                anchor_id = f"match-{int(game.get('Match ID'))}"
        except Exception:
            pass

        card_kw: dict = {"className": "mb-3"}
        if anchor_id:
            card_kw["id"] = anchor_id

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
                                        html.Div(
                                            [
                                                (
                                                    html.Small(
                                                        dur_disp,
                                                        className="text-muted me-2",
                                                        style={"whiteSpace": "nowrap"},
                                                    )
                                                    if dur_disp
                                                    else html.Div()
                                                ),
                                                dbc.Badge(
                                                    result_text,
                                                    color=result_color,
                                                    className="ms-auto",
                                                    style={"height": "fit-content"},
                                                ),
                                            ],
                                            className="d-flex align-items-center",
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
            **card_kw,
        )
        history_items.append(card)

    return history_items


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


def register_callbacks(app) -> None:
    """Register match-history callbacks on *app*."""

    @app.callback(
        Output("history-list-container", "children"),
        Output("history-display-count-store", "data"),
        Input("load-more-history-button", "n_clicks"),
        Input("history-display-count-store", "data"),
        Input("player-dropdown-match-verlauf", "value"),
        Input("hero-filter-dropdown-match", "value"),
        Input("dummy-output", "children"),
        Input("server-update-token", "data"),
        Input("lang-store", "data"),
        State("history-display-count-store", "data"),
        State("history-load-amount-dropdown", "value"),
    )
    def update_history_display(
        n_clicks,
        store_data_in,
        player_name,
        hero_name,
        _dummy,
        _token,
        lang_data,
        current_store,
        load_amount,
    ):
        loader.reload()
        df = loader.get_df()
        lang = (lang_data or {}).get("lang", "en")

        if df.empty:
            return [dbc.Alert(tr("no_history", lang), color="danger")], {"count": 10}

        triggered_id = ctx.triggered_id or "dummy-output"

        if triggered_id in (
            "player-dropdown-match-verlauf",
            "hero-filter-dropdown-match",
            "dummy-output",
            "server-update-token",
        ):
            new_count = 10
        elif triggered_id == "history-display-count-store":
            new_count = int(
                (store_data_in or {}).get("count", current_store.get("count", 10))
            )
        else:
            new_count = current_store.get("count", 10) + (load_amount or 10)

        filtered_df = df

        if player_name and player_name != "ALL":
            hero_col = f"{player_name} Hero"
            if hero_col in filtered_df.columns:
                filtered_df = filtered_df[
                    filtered_df[hero_col].notna()
                    & (filtered_df[hero_col] != "nicht dabei")
                ]
                if hero_name:
                    filtered_df = filtered_df[filtered_df[hero_col] == hero_name]
        elif hero_name and (not player_name or player_name == "ALL"):
            hero_cols = [
                f"{p} Hero"
                for p in config.PLAYERS
                if f"{p} Hero" in filtered_df.columns
            ]
            mask = filtered_df[hero_cols].eq(hero_name).any(axis=1)
            filtered_df = filtered_df[mask]

        if "Match ID" in filtered_df.columns:
            filtered_df = filtered_df.sort_values("Match ID", ascending=False)
        elif "Datum" in filtered_df.columns:
            filtered_df = filtered_df.sort_values("Datum", ascending=False)

        games_to_show = filtered_df.head(new_count)
        history_layout = generate_history_layout_simple(games_to_show, lang)

        if games_to_show.empty:
            history_layout = [dbc.Alert(tr("no_games_filter", lang), color="info")]

        return history_layout, {"count": new_count}

    # -- Timeline tile click → jump to history card -------------------------

    @app.callback(
        Output("tabs", "active_tab", allow_duplicate=True),
        Output("history-display-count-store", "data", allow_duplicate=True),
        Output("url", "hash", allow_duplicate=True),
        Input({"type": "timeline-tile", "matchId": ALL}, "n_clicks"),
        State({"type": "timeline-tile", "matchId": ALL}, "id"),
        prevent_initial_call=True,
    )
    def on_timeline_tile_click(clicks, ids):
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

        df = loader.get_df()
        try:
            if "Match ID" in df.columns:
                ids_s = pd.to_numeric(df["Match ID"], errors="coerce")
                needed = int((ids_s > target_mid).sum()) + 1
            else:
                needed = 50
        except Exception:
            needed = 50
        needed = int(((needed + 9) // 10) * 10)
        return "tab-history", {"count": needed}, f"#match-{target_mid}"

    # -- Hero filter options for match history dropdown ---------------------

    @app.callback(
        Output("hero-filter-dropdown-match", "options"),
        Output("hero-filter-dropdown-match", "value"),
        Input("player-dropdown-match-verlauf", "value"),
        Input("dummy-output", "children"),
        State("hero-filter-dropdown-match", "value"),
    )
    def update_match_history_hero_options(selected_player, _, current_hero):
        df = loader.get_df()
        if df.empty:
            return [], None

        if not selected_player or selected_player == "ALL":
            all_heroes: set[str] = set()
            for p in config.PLAYERS:
                hc = f"{p} Hero"
                if hc in df.columns:
                    all_heroes.update(
                        df[df[hc].notna() & (df[hc] != "nicht dabei")][hc].unique()
                    )
            heroes = sorted(all_heroes)
        else:
            hc = f"{selected_player} Hero"
            heroes = (
                sorted(df[df[hc].notna() & (df[hc] != "nicht dabei")][hc].unique())
                if hc in df.columns
                else []
            )

        hero_options = [
            {
                "label": html.Div(
                    [
                        html.Img(
                            src=get_hero_image_url(h),
                            style={
                                "height": "25px",
                                "marginRight": "10px",
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
        if current_hero and current_hero in heroes:
            return hero_options, current_hero
        return hero_options, None
