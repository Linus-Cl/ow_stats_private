"""
pages/stats.py
==============
Callbacks for the stats tabs: map/mode stats, hero stats, role stats,
performance heatmap, winrate trend, and the overall statistics summary.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
import plotly.express as px
import plotly.graph_objects as go
from dash import ALL, Input, Output, State, dcc, html, no_update

import config
from data import loader
from utils.assets import get_hero_image_url, get_map_image_url
from utils.filters import calculate_winrate, filter_data
from utils.i18n import tr


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def create_stat_card(
    title: str,
    image_url: str,
    main_text: str,
    sub_text: str,
) -> dbc.Col:
    """Build a single stat-card column (used in the overall stats row)."""
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
            className="h-100",
        ),
        md=3,
    )


# ---------------------------------------------------------------------------
# Callback registration
# ---------------------------------------------------------------------------


def register_callbacks(app) -> None:  # noqa: C901 – large but faithful migration
    """Register all stats-related callbacks on *app*."""

    # -- visibility toggles -------------------------------------------------

    @app.callback(
        Output("map-view-type-container", "style"),
        Input("map-stat-type", "value"),
    )
    def toggle_view_type_visibility(map_stat_type):
        if map_stat_type in ("winrate", "plays"):
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
        hero_stat = hero_stat or "winrate"
        role_stat = role_stat or "winrate"
        map_stat = map_stat or "winrate"
        if (
            (tab == "tab-hero" and hero_stat == "winrate")
            or (tab == "tab-role" and role_stat == "winrate")
            or (tab == "tab-map" and map_stat in ("winrate", "gamemode", "attackdef"))
        ):
            return False, ""
        return True, tr("only_relevant_winrate", "de")

    # -- mega graph callback ------------------------------------------------

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
        _dummy,
        _server_token,
        theme_data,
        lang_data,
    ):
        dark = bool((theme_data or {}).get("dark", False))
        lang = (lang_data or {}).get("lang", "en")

        # Robust defaults
        map_stat_type = map_stat_type or "winrate"
        hero_stat_type = hero_stat_type or "winrate"
        role_stat_type = role_stat_type or "winrate"
        map_view_type = bool(map_view_type)

        def style_fig(fig: go.Figure):
            if not isinstance(fig, go.Figure):
                return fig
            template = "plotly_dark" if dark else "plotly_white"
            paper = "#151925" if dark else "#ffffff"
            kw = {"template": template, "paper_bgcolor": paper, "plot_bgcolor": paper}
            if dark:
                kw["font_color"] = "#e5e7eb"
            fig.update_layout(**kw)
            return fig

        # Data collection
        dataframes = {player: filter_data(player, season, month, year)}
        active_compare_players: list[str] = []
        if compare_ids:
            for i, is_on in enumerate(compare_values):
                if is_on:
                    p_name = compare_ids[i]["player"]
                    active_compare_players.append(p_name)
                    dataframes[p_name] = filter_data(p_name, season, month, year)

        main_df = dataframes[player]
        title_suffix = (
            f"({player}"
            + (
                " vs " + ", ".join(active_compare_players)
                if active_compare_players
                else ""
            )
            + ")"
        )

        empty_fig = style_fig(
            go.Figure(layout={"title": tr("no_data_selection", lang)})
        )
        stats_header = f"{tr('stats_header', lang)} ({player})"

        # ── Stats container ────────────────────────────────────────────────
        stats_container: html.Div | str = html.Div(tr("no_data_selection", lang))
        if not main_df.empty:
            total = len(main_df)
            wins = len(main_df[main_df["Win Lose"] == "Win"])
            losses = total - wins
            winrate = wins / total if total else 0

            primary_stats_row = dbc.Row(
                [
                    dbc.Col(
                        dbc.Card(
                            [
                                dbc.CardHeader(tr("total_games", lang)),
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
                                    html.H4(f"{losses}", className="text-danger")
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
                                    html.H4(f"{winrate:.0%}", className="text-primary")
                                ),
                            ],
                            className="text-center h-100",
                        )
                    ),
                ],
                className="mb-4",
            )

            secondary = []
            try:
                mph = main_df["Hero"].mode()[0]
                hp = main_df["Hero"].value_counts()[mph]
                secondary.append(
                    create_stat_card(
                        tr("most_played_hero", lang),
                        get_hero_image_url(mph),
                        mph,
                        f"{hp} {tr('games', lang)}",
                    )
                )
            except (KeyError, IndexError):
                secondary.append(
                    create_stat_card(
                        tr("most_played_hero", lang),
                        get_hero_image_url(None),
                        "N/A",
                        tr("no_data", lang),
                    )
                )
            try:
                hero_wr = calculate_winrate(main_df, "Hero")
                hero_wr_f = hero_wr[hero_wr["Spiele"] >= min_games]
                bh = hero_wr_f.loc[hero_wr_f["Winrate"].idxmax()]
                secondary.append(
                    create_stat_card(
                        tr("best_wr_hero", lang),
                        get_hero_image_url(bh["Hero"]),
                        bh["Hero"],
                        f"{bh['Winrate']:.0%} ({bh['Spiele']} {tr('games', lang)})",
                    )
                )
            except (KeyError, IndexError, ValueError):
                secondary.append(
                    create_stat_card(
                        tr("best_wr_hero", lang),
                        get_hero_image_url(None),
                        "N/A",
                        tr("min_n_games", lang).format(n=min_games),
                    )
                )
            try:
                mpm = main_df["Map"].mode()[0]
                mp = main_df["Map"].value_counts()[mpm]
                secondary.append(
                    create_stat_card(
                        tr("most_played_map", lang),
                        get_map_image_url(mpm),
                        mpm,
                        f"{mp} {tr('games', lang)}",
                    )
                )
            except (KeyError, IndexError):
                secondary.append(
                    create_stat_card(
                        tr("most_played_map", lang),
                        get_map_image_url(None),
                        "N/A",
                        tr("no_data", lang),
                    )
                )
            try:
                map_wr = calculate_winrate(main_df, "Map")
                map_wr_f = map_wr[map_wr["Spiele"] >= min_games]
                bm = map_wr_f.loc[map_wr_f["Winrate"].idxmax()]
                secondary.append(
                    create_stat_card(
                        tr("best_wr_map", lang),
                        get_map_image_url(bm["Map"]),
                        bm["Map"],
                        f"{bm['Winrate']:.0%} ({bm['Spiele']} {tr('games', lang)})",
                    )
                )
            except (KeyError, IndexError, ValueError):
                secondary.append(
                    create_stat_card(
                        tr("best_wr_map", lang),
                        get_map_image_url(None),
                        "N/A",
                        tr("min_n_games", lang).format(n=min_games),
                    )
                )

            stats_container = html.Div([primary_stats_row, dbc.Row(secondary)])

        # ── i18n shortcut ──────────────────────────────────────────────────
        def trd(key, de_default, en_default):
            v = tr(key, lang)
            return v if v != key else (de_default if lang == "de" else en_default)

        attack_def_modes = ["Attack", "Defense", "Attack Attack"]
        bar_fig = go.Figure()

        # ── Map stat: detailed view ────────────────────────────────────────
        if (
            map_view_type
            and not active_compare_players
            and map_stat_type in ("winrate", "plays")
        ):
            if map_stat_type == "winrate":
                map_data = calculate_winrate(main_df, "Map")
                map_data = map_data[map_data["Spiele"] >= min_games]
                if not map_data.empty:
                    plot_df = main_df[
                        main_df["Attack Def"].isin(attack_def_modes)
                    ].copy()
                    overall_label = trd("overall", "Gesamt", "Overall")
                    plot_df["Mode"] = plot_df["Attack Def"].replace(
                        {"Attack Attack": overall_label}
                    )
                    grouped = (
                        plot_df.groupby(["Map", "Mode", "Win Lose"])
                        .size()
                        .unstack(fill_value=0)
                    )
                    for c in ("Win", "Lose"):
                        if c not in grouped:
                            grouped[c] = 0
                    grouped["Spiele"] = grouped["Win"] + grouped["Lose"]
                    grouped["Winrate"] = grouped["Win"] / grouped["Spiele"]
                    plot_data = grouped.reset_index()
                    plot_data = plot_data[plot_data["Map"].isin(map_data["Map"])]
                    if not plot_data.empty:
                        bar_fig = px.bar(
                            plot_data,
                            x="Map",
                            y="Winrate",
                            color="Mode",
                            barmode="group",
                            title=f"{tr('winrate', lang)} {tr('by', lang)} {tr('map_label', lang)} ({trd('detailed', 'Detailliert', 'Detailed')}) - {player}",
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
                                f"{tr('winrate', lang)}: %{{y:.1%}}<br>{tr('games', lang)}: %{{customdata[0]}}"
                                f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
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
                        plot_df.groupby(["Map", "Seite"])
                        .size()
                        .reset_index(name="Spiele")
                    )
                    total_plays_map = (
                        main_df.groupby("Map")
                        .size()
                        .reset_index(name="TotalSpiele")
                        .sort_values("TotalSpiele", ascending=False)
                    )
                    bar_fig = px.bar(
                        plays_by_side,
                        x="Map",
                        y="Spiele",
                        color="Seite",
                        barmode="stack",
                        title=f"{tr('games', lang)} {tr('by', lang)} {tr('map_label', lang)} ({trd('detailed', 'Detailliert', 'Detailed')}) - {player}",
                        labels={"Spiele": tr("games", lang), "Seite": tr("side", lang)},
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
                if map_stat_type in ("winrate", "gamemode", "attackdef")
                else "Spiele"
            )
            for name, df_p in dataframes.items():
                if not df_p.empty and group_col and group_col in df_p.columns:
                    if y_col == "Winrate":
                        stats = calculate_winrate(df_p, group_col)
                        stats = stats[stats["Spiele"] >= min_games]
                        if not stats.empty:
                            bar_fig.add_trace(
                                go.Bar(
                                    x=stats[group_col],
                                    y=stats[y_col],
                                    name=name,
                                    customdata=stats[["Spiele", "Win", "Lose"]],
                                    hovertemplate=(
                                        f"<b>%{{x}}</b><br>{tr('winrate', lang)}: %{{y:.1%}}"
                                        f"<br>{tr('games', lang)}: %{{customdata[0]}}"
                                        f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                                        f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                                    ),
                                )
                            )
                    else:
                        stats = (
                            df_p.groupby(group_col)
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
                                    hovertemplate=f"<b>%{{x}}</b><br>{tr('games', lang)}: %{{y}}<extra></extra>",
                                )
                            )
            group_label = {
                "Map": tr("map_label", lang),
                "Gamemode": tr("gamemode_label", lang),
                "Attack Def": tr("attackdef_label", lang),
            }.get(group_col, group_col)
            stat_label = (
                tr("winrate", lang) if y_col == "Winrate" else tr("games", lang)
            )
            bar_fig.update_layout(
                title=f"{stat_label} {tr('by', lang)} {group_label} {title_suffix}",
                barmode="group",
                yaxis_title=stat_label,
                legend_title=tr("players", lang),
            )
            if y_col == "Winrate":
                bar_fig.update_layout(yaxis_tickformat=".0%")
            if not bar_fig.data:
                bar_fig = empty_fig

        # ── compose map_stat_output ────────────────────────────────────────
        if map_stat_type == "winrate":
            map_stat_output = dbc.Row(
                dbc.Col(dcc.Graph(figure=style_fig(bar_fig)), width=12)
            )
        else:
            pie_fig = go.Figure()
            pie_col = {"gamemode": "Gamemode", "attackdef": "Attack Def"}.get(
                map_stat_type
            )
            if pie_col:
                pie_df = main_df.copy()
                if pie_col == "Attack Def":
                    pie_df = pie_df[pie_df["Attack Def"].isin(attack_def_modes)]
                pie_df = pie_df.groupby(pie_col).size().reset_index(name="Spiele")
                if not pie_df.empty:
                    disp_col = {
                        "Gamemode": tr("gamemode_label", lang),
                        "Attack Def": tr("attackdef_label", lang),
                    }.get(pie_col, pie_col)
                    pie_fig = px.pie(
                        pie_df,
                        names=pie_col,
                        values="Spiele",
                        title=f"{tr('distribution', lang)} {disp_col}",
                    )
                    share_word = "Anteil" if lang == "de" else "Share"
                    pie_fig.update_traces(
                        hovertemplate=f"<b>%{{label}}</b><br>{tr('games', lang)}: %{{value}}<br>{share_word}: %{{percent}}<extra></extra>"
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

        # ── comparison helper ──────────────────────────────────────────────
        def create_comparison_fig(stat_type, group_col):
            fig = go.Figure()
            y_col = "Winrate" if stat_type == "winrate" else "Spiele"
            for name, df_p in dataframes.items():
                if not df_p.empty:
                    if y_col == "Winrate":
                        stats = calculate_winrate(df_p, group_col)
                        stats = stats[stats["Spiele"] >= min_games]
                        if not stats.empty:
                            fig.add_trace(
                                go.Bar(
                                    x=stats[group_col],
                                    y=stats[y_col],
                                    name=name,
                                    customdata=stats[["Spiele", "Win", "Lose"]],
                                    hovertemplate=(
                                        f"<b>%{{x}}</b><br>{tr('winrate', lang)}: %{{y:.1%}}"
                                        f"<br>{tr('games', lang)}: %{{customdata[0]}}"
                                        f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                                        f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                                    ),
                                )
                            )
                    else:
                        stats = (
                            df_p.groupby(group_col)
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
                                    hovertemplate=f"<b>%{{x}}</b><br>{tr('games', lang)}: %{{y}}<extra></extra>",
                                )
                            )
            g_label = {
                "Hero": tr("hero_label", lang),
                "Rolle": tr("role_label", lang),
                "Map": tr("map_label", lang),
            }.get(group_col, group_col)
            s_label = tr("winrate", lang) if y_col == "Winrate" else tr("games", lang)
            fig.update_layout(
                title=f"{s_label} {tr('by', lang)} {g_label} {title_suffix}",
                barmode="group",
                yaxis_title=s_label,
                legend_title=tr("players", lang),
            )
            if y_col == "Winrate":
                fig.update_layout(yaxis_tickformat=".0%")
            return fig if fig.data else empty_fig

        hero_fig = style_fig(create_comparison_fig(hero_stat_type, "Hero"))
        role_fig = style_fig(create_comparison_fig(role_stat_type, "Rolle"))

        # ── heatmap ────────────────────────────────────────────────────────
        heatmap_fig = empty_fig
        if not main_df.empty:
            try:
                pivot = main_df.pivot_table(
                    index="Rolle",
                    columns="Map",
                    values="Win Lose",
                    aggfunc=lambda x: (x == "Win").sum() / len(x) if len(x) else 0,
                )
                if not pivot.empty:
                    heatmap_fig = px.imshow(
                        pivot,
                        text_auto=".0%",
                        color_continuous_scale="RdYlGn",
                        zmin=0,
                        zmax=1,
                        aspect="auto",
                        title=f"{tr('winrate', lang)} Heatmap – {player}",
                    )
                    try:
                        t_piv = (
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
                        w_piv = (
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
                        l_piv = (t_piv - w_piv).astype(int)
                        heatmap_fig.data[0].customdata = [
                            [
                                [
                                    int(t_piv.iloc[i, j]),
                                    int(w_piv.iloc[i, j]),
                                    int(l_piv.iloc[i, j]),
                                ]
                                for j in range(t_piv.shape[1])
                            ]
                            for i in range(t_piv.shape[0])
                        ]
                        heatmap_fig.update_traces(
                            hovertemplate=(
                                f"<b>{tr('map_label', lang)}: %{{x}}</b><br><b>{trd('role_label','Rolle','Role')}: %{{y}}</b>"
                                f"<br><b>{tr('winrate', lang)}: %{{z: .1%}}</b>"
                                f"<br>{tr('games', lang)}: %{{customdata[0]}}"
                                f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[1]}}"
                                f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[2]}}<extra></extra>"
                            )
                        )
                    except Exception:
                        heatmap_fig.update_traces(
                            hovertemplate=(
                                f"<b>{tr('map_label', lang)}: %{{x}}</b><br><b>{trd('role_label','Rolle','Role')}: %{{y}}</b>"
                                f"<br><b>{tr('winrate', lang)}: %{{z: .1%}}</b><extra></extra>"
                            )
                        )
            except Exception:
                pass
        heatmap_fig = style_fig(heatmap_fig)

        # ── winrate trend ──────────────────────────────────────────────────
        winrate_fig = go.Figure()
        for name, df_p in dataframes.items():
            if not df_p.empty and "Datum" in df_p.columns:
                td = df_p.dropna(subset=["Datum"]).copy()
                td.sort_values("Datum", inplace=True, ascending=True)
                if hero_filter:
                    td = td[td["Hero"] == hero_filter]
                if not td.empty:
                    td["Win"] = (td["Win Lose"] == "Win").astype(int)
                    td["GameNum"] = range(1, len(td) + 1)
                    td["CumulativeWinrate"] = td["Win"].cumsum() / td["GameNum"]
                    td["CumWins"] = td["Win"].cumsum()
                    td["CumLosses"] = td["GameNum"] - td["CumWins"]
                    winrate_fig.add_trace(
                        go.Scatter(
                            x=td["GameNum"],
                            y=td["CumulativeWinrate"],
                            mode="lines",
                            name=name,
                            customdata=td[["CumWins", "CumLosses"]].values,
                        )
                    )
        winrate_fig.update_layout(
            title=f"{trd('trend','Winrate-Verlauf','Winrate Trend')} {title_suffix}",
            yaxis_tickformat=".0%",
            yaxis_title=tr("winrate", lang),
            xaxis_title=tr("game_number", lang),
            legend_title=tr("players", lang),
        )
        winrate_fig.update_traces(
            hovertemplate=(
                f"<b>{tr('game_number', lang)}: %{{x}}</b>"
                f"<br><b>{tr('winrate', lang)}: %{{y: .1%}}</b>"
                f"<br>{trd('won','Gewonnen','Won')}: %{{customdata[0]}}"
                f"<br>{trd('lost','Verloren','Lost')}: %{{customdata[1]}}<extra></extra>"
            )
        )
        if not winrate_fig.data:
            winrate_fig = empty_fig
        winrate_fig = style_fig(winrate_fig)

        # ── hero filter dropdown options ───────────────────────────────────
        hero_options = []
        if not main_df.empty:
            for hero in sorted(main_df["Hero"].dropna().unique()):
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
