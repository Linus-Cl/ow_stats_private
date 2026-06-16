"""
pages/roles.py
==============
Callbacks for the Role Assignment tab: role dropdowns, detailed hero selectors,
role stats computation, role-assignment match history, and load-more controls.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import config
from data import loader
from utils.assets import get_hero_image_url, get_map_image_url
from utils.i18n import tr


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


def register_callbacks(app) -> None:  # noqa: C901
    """Register all role-assignment callbacks on *app*."""

    # -- Populate role dropdown options (mutual exclusion) -------------------

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
        df = loader.get_df()
        if df.empty:
            players = config.PLAYERS
            maps: list[str] = []
        else:
            players = [
                c.replace(" Rolle", "") for c in df.columns if c.endswith(" Rolle")
            ] or config.PLAYERS
            maps = sorted(m for m in df.get("Map", pd.Series()).dropna().unique())

        tank_vals = tank_vals or []
        dmg_vals = dmg_vals or []
        sup_vals = sup_vals or []
        bench_vals = bench_vals or []
        selected_any = set(tank_vals + dmg_vals + sup_vals + bench_vals)

        def build_opts(max_count: int, current: list[str]):
            role_full = len(current) >= max_count
            return [
                {
                    "label": p,
                    "value": p,
                    "disabled": (p in selected_any and p not in current)
                    or (role_full and p not in current),
                }
                for p in players
            ]

        tank_opts = build_opts(1, tank_vals)
        dmg_opts = build_opts(2, dmg_vals)
        sup_opts = build_opts(2, sup_vals)
        bench_opts = [
            {
                "label": p,
                "value": p,
                "disabled": p in (set(tank_vals) | set(dmg_vals) | set(sup_vals)),
            }
            for p in players
        ]
        map_opts = [{"label": m, "value": m} for m in maps]
        return tank_opts, dmg_opts, sup_opts, bench_opts, map_opts

    # -- Enforce max players per role ---------------------------------------

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
        seen: set[str] = set()

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

    # -- Detailed hero selectors per player/role ----------------------------

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
        selected_players: list[str] = []
        role_by_player: dict[str, str] = {}
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

        df = loader.get_df()
        if df.empty:
            return dbc.Alert(tr("no_data_loaded", lang), color="danger")

        temp = df.copy()
        if season and "Season" in temp.columns:
            temp = temp[temp["Season"] == season]
        if month and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]
        if year and "Jahr" in temp.columns:
            temp = temp[temp["Jahr"] == year]

        cols = []
        for p in selected_players:
            role = role_by_player.get(p)
            hero_col = f"{p} Hero"
            role_col = f"{p} Rolle"
            options = []
            if hero_col in temp.columns and role_col in temp.columns:
                subset = temp[
                    (temp[hero_col].notna()) & (temp[hero_col] != "nicht dabei")
                ]
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

    # -- Compute role stats -------------------------------------------------

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
        tank = tank_vals or []
        dmg = dmg_vals or []
        sup = sup_vals or []

        if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
            return dbc.Alert(tr("too_many_players", lang), color="warning")
        if len(tank) + len(dmg) + len(sup) == 0:
            return dbc.Alert(
                tr("please_select_at_least_one_player", lang), color="info"
            )

        bench = bench_vals or []
        all_players = tank + dmg + sup + bench
        if len(set(all_players)) != len(all_players):
            return dbc.Alert(tr("duplicate_players_roles", lang), color="warning")

        df = loader.get_df()
        if df.empty:
            return dbc.Alert(tr("no_data_loaded", lang), color="danger")

        temp = df
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

        required_cols = ["Win Lose", "Map"]
        for p in all_players:
            required_cols += [f"{p} Rolle", f"{p} Hero"]
        missing = [c for c in required_cols if c not in temp.columns]
        if missing:
            return dbc.Alert(
                tr("required_cols_missing", lang).format(cols=missing), color="danger"
            )

        mask = pd.Series(True, index=temp.index)
        selected_heroes: dict[str, set] = {}
        if detail_on:
            try:
                if hero_values and hero_ids:
                    for vals, _id in zip(hero_values, hero_ids):
                        p = _id.get("player") if isinstance(_id, dict) else None
                        if p and vals:
                            selected_heroes[p] = set(vals)
            except Exception:
                pass

        for p in bench:
            mask = mask & (
                temp[f"{p} Hero"].isna() | (temp[f"{p} Hero"] == "nicht dabei")
            )
        if len(tank) == 1:
            p = tank[0]
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Tank")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
            if p in selected_heroes:
                mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
        for p in dmg:
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Damage")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
            if p in selected_heroes:
                mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
        for p in sup:
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Support")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
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
            color="success" if wr >= 0.5 else "danger" if total else "secondary",
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

        hero_filters_block = None
        if selected_heroes:
            hero_lines = [
                html.Div(f"{p}: {', '.join(sorted(h))}", className="small")
                for p, h in selected_heroes.items()
            ]
            hero_filters_block = html.Div(
                [
                    html.Small(
                        tr("heroes_filter", lang), className="text-muted d-block"
                    ),
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
                                                html.H4(
                                                    f"{wins}", className="text-success"
                                                )
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
                                                    f"{wr:.0%}",
                                                    className="text-primary",
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

    # -- Role assignment history --------------------------------------------

    def _build_role_mask(temp, tank, dmg, sup, bench, detail_on, hero_values, hero_ids):
        """Build a boolean mask for role-filtered matches (shared logic)."""
        mask = pd.Series(True, index=temp.index)
        selected_heroes: dict[str, set] = {}
        if detail_on:
            try:
                if hero_values and hero_ids:
                    for vals, _id in zip(hero_values, hero_ids):
                        p = _id.get("player") if isinstance(_id, dict) else None
                        if p and vals:
                            selected_heroes[p] = set(vals)
            except Exception:
                pass
        for p in bench:
            mask = mask & (
                temp[f"{p} Hero"].isna() | (temp[f"{p} Hero"] == "nicht dabei")
            )
        if len(tank) == 1:
            p = tank[0]
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Tank")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
            if p in selected_heroes:
                mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
        for p in dmg:
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Damage")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
            if p in selected_heroes:
                mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
        for p in sup:
            mask = (
                mask
                & temp[f"{p} Rolle"].eq("Support")
                & temp[f"{p} Hero"].notna()
                & (temp[f"{p} Hero"] != "nicht dabei")
            )
            if p in selected_heroes:
                mask = mask & temp[f"{p} Hero"].isin(selected_heroes[p])
        return mask

    def _apply_timeframe(df, maps_selected, season, month, year):
        temp = df
        if maps_selected:
            temp = temp[temp["Map"].isin(maps_selected)]
        if season and "Season" in temp.columns:
            temp = temp[temp["Season"] == season]
        else:
            if year is not None and "Jahr" in temp.columns:
                temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
            if month is not None and "Monat" in temp.columns:
                temp = temp[temp["Monat"] == month]
        return temp

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

        display_count = 10
        try:
            if isinstance(count_store, dict):
                display_count = int(count_store.get("count", 10))
            elif isinstance(count_store, (int, float)):
                display_count = int(count_store)
        except Exception:
            pass

        tank = tank_vals or []
        dmg = dmg_vals or []
        sup = sup_vals or []
        bench = bench_vals or []

        if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
            return dbc.Alert(tr("too_many_players_history", lang), color="warning")
        all_players = tank + dmg + sup + bench
        if not all_players:
            return dbc.Alert(
                tr("please_select_at_least_one_player", lang), color="info"
            )
        if len(set(all_players)) != len(all_players):
            return dbc.Alert(tr("duplicate_players_roles", lang), color="warning")

        df = loader.get_df()
        if df.empty:
            return dbc.Alert(tr("no_data_loaded", lang), color="danger")

        temp = _apply_timeframe(df, maps_selected, season, month, year)
        if temp.empty:
            return dbc.Alert(tr("no_data_timeframe", lang), color="info")

        for p in all_players:
            for c in (f"{p} Rolle", f"{p} Hero"):
                if c not in temp.columns:
                    return dbc.Alert(
                        tr("required_cols_missing", lang).format(cols=c), color="danger"
                    )

        mask = _build_role_mask(
            temp, tank, dmg, sup, bench, detail_on, hero_values, hero_ids
        )
        full_subset = temp[mask].copy()
        total_full = len(full_subset)
        if "Match ID" in full_subset.columns:
            full_subset.sort_values("Match ID", ascending=False, inplace=True)
        subset = full_subset.head(display_count)
        if subset.empty:
            return dbc.Alert(tr("no_matching_matches", lang), color="info")

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
                color="success" if result == "Win" else "danger",
                className="ms-2",
            )
            role_lines = []
            for p in tank:
                role_lines.append(
                    html.Div(
                        f"Tank: {p} • {row.get(f'{p} Hero', '—')}", className="small"
                    )
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
            selected_and_bench = set(tank + dmg + sup + bench)
            for p in known_players:
                if p not in selected_and_bench:
                    hero_val = row.get(f"{p} Hero")
                    role_val = row.get(f"{p} Rolle")
                    if pd.notna(hero_val) and hero_val != "nicht dabei":
                        role_label = (
                            role_val
                            if isinstance(role_val, str) and role_val
                            else tr("role_label", lang)
                        )
                        role_lines.append(
                            html.Div(
                                f"{role_label}: {p} • {hero_val}", className="small"
                            )
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
                    ),
                )
            )

        components = [dbc.ListGroup(items, flush=True)]
        if display_count >= total_full:
            components.append(
                html.Div(tr("no_more_entries", lang), className="text-muted small mt-2")
            )
        return html.Div(components)

    # -- Load-more counter --------------------------------------------------

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
        base = 10
        if not isinstance(current_store, dict):
            current_store = {"count": base}
        triggered = ctx.triggered_id
        if not toggle:
            return {"count": base}
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
        if isinstance(triggered, dict) or triggered in reset_triggers:
            return {"count": base}
        if triggered == "role-history-load-more" and toggle:
            step = int(load_amount or base)
            return {"count": int(current_store.get("count", base)) + step}
        return current_store

    # -- Disable button when all entries shown ------------------------------

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
        dropdown_disabled = not bool(show_history)
        if not show_history:
            return True, dropdown_disabled

        display_count = 10
        try:
            if isinstance(count_store, dict):
                display_count = int(count_store.get("count", 10))
        except Exception:
            pass

        tank = tank_vals or []
        dmg = dmg_vals or []
        sup = sup_vals or []
        bench = bench_vals or []

        df = loader.get_df()
        if df.empty:
            return True, dropdown_disabled

        temp = _apply_timeframe(df, maps_selected, season, month, year)
        if temp.empty:
            return True, dropdown_disabled

        all_players = tank + dmg + sup + bench
        for p in all_players:
            for c in (f"{p} Rolle", f"{p} Hero"):
                if c not in temp.columns:
                    return True, dropdown_disabled

        mask = _build_role_mask(
            temp, tank, dmg, sup, bench, detail_on, hero_values, hero_ids
        )
        total_full = int(mask.sum())
        return display_count >= total_full or total_full == 0, dropdown_disabled
