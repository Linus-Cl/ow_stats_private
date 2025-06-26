import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, ctx, State, ALL
import dash_bootstrap_components as dbc
import requests
from io import StringIO
import re

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
        df.columns = df.columns.str.strip()
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


# Initial data load
load_data(use_local=True)


# --- Layout (Unchanged) ---
app.layout = dbc.Container(
    [
        dcc.Store(id="history-display-count-store", data={"count": 10}),
        dbc.Row(
            [
                dbc.Col(
                    html.Img(
                        src="https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Overwatch_circle_logo.svg/1024px-Overwatch_circle_logo.svg.png",
                        height="50px",
                    ),
                    width="auto",
                ),
                dbc.Col(html.H1("Overwatch Statistics", className="my-4"), width=True),
                dbc.Col(
                    dbc.Button(
                        "Update Data from Cloud",
                        id="update-data-button",
                        color="primary",
                        className="mt-4",
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
                                    "Filter", className="bg-primary text-white"
                                ),
                                dbc.CardBody(
                                    [
                                        dbc.Label("Spieler auswählen:"),
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
                                            "Season auswählen (überschreibt Jahr/Monat):"
                                        ),
                                        dcc.Dropdown(
                                            id="season-dropdown",
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                            clearable=True,
                                        ),
                                        dbc.Label("Jahr auswählen:"),
                                        dcc.Dropdown(
                                            id="year-dropdown",
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                            clearable=True,
                                        ),
                                        dbc.Label("Monat auswählen:"),
                                        dcc.Dropdown(
                                            id="month-dropdown",
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                            clearable=True,
                                        ),
                                        dbc.Label("Mindestanzahl Spiele:"),
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
                                                        options=[
                                                            {
                                                                "label": "Winrate nach Map",
                                                                "value": "winrate",
                                                            },
                                                            {
                                                                "label": "Spiele pro Map",
                                                                "value": "plays",
                                                            },
                                                            {
                                                                "label": "Gamemode Statistik",
                                                                "value": "gamemode",
                                                            },
                                                            {
                                                                "label": "Attack/Defense Statistik",
                                                                "value": "attackdef",
                                                            },
                                                        ],
                                                    ),
                                                    width=4,
                                                ),
                                                dbc.Col(
                                                    html.Div(
                                                        dbc.Switch(
                                                            id="map-view-type",
                                                            label="Detailliert",
                                                            value=False,
                                                            className="mt-1",
                                                        ),
                                                        id="map-view-type-container",
                                                        style={"margin-bottom": "20px"},
                                                    ),
                                                    width=4,
                                                    className="d-flex align-items-center",
                                                ),
                                            ]
                                        ),
                                        dcc.Graph(id="map-stat-graph"),
                                    ],
                                ),
                                dbc.Tab(
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
                                            options=[
                                                {
                                                    "label": "Winrate nach Held",
                                                    "value": "winrate",
                                                },
                                                {
                                                    "label": "Spiele pro Held",
                                                    "value": "plays",
                                                },
                                            ],
                                        ),
                                        dcc.Graph(id="hero-stat-graph"),
                                    ],
                                ),
                                dbc.Tab(
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
                                            options=[
                                                {
                                                    "label": "Winrate nach Rolle",
                                                    "value": "winrate",
                                                },
                                                {
                                                    "label": "Spiele pro Rolle",
                                                    "value": "plays",
                                                },
                                            ],
                                        ),
                                        dcc.Graph(id="role-stat-graph"),
                                    ],
                                ),
                                dbc.Tab(
                                    dcc.Graph(id="performance-heatmap"),
                                    label="Performance Heatmap",
                                    tab_id="tab-heatmap",
                                ),
                                dbc.Tab(
                                    label="Winrate Verlauf",
                                    tab_id="tab-trend",
                                    children=[
                                        dbc.Label("Held filtern (optional):"),
                                        dcc.Dropdown(
                                            id="hero-filter-dropdown",
                                            placeholder="Kein Held ausgewählt",
                                            className="mb-3",
                                        ),
                                        dcc.Graph(id="winrate-over-time"),
                                    ],
                                ),
                                dbc.Tab(
                                    label="Match Verlauf",
                                    tab_id="tab-history",
                                    children=[
                                        dbc.Row(
                                            [
                                                dbc.Col(width=6),
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
                                                    width=3,
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
                                            className="my-3",
                                        ),
                                        html.Div(
                                            id="history-list-container",
                                            style={
                                                "maxHeight": "1000px",
                                                "overflowY": "auto",
                                            },
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
                                    id="stats-header", className="bg-primary text-white"
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
    ],
    fluid=True,
)


# --- Helper Functions (Unchanged) ---
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
    if data.empty or group_col not in data.columns:
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
    history_items, last_season = [], None
    for idx, game in games_df.iterrows():
        if pd.isna(game.get("Map")):
            continue
        current_season = game.get("Season")
        if pd.notna(current_season) and current_season != last_season:
            match = re.search(r"\d+", str(current_season))
            season_text = f"Season {match.group(0)}" if match else str(current_season)
            history_items.append(
                dbc.Alert(
                    season_text, color="primary", className="my-4 text-center fw-bold"
                )
            )
            last_season = current_season
        player_list_items = []
        for p in constants.players:
            hero = game.get(f"{p} Hero")
            if pd.notna(hero) and hero != "nicht dabei":
                role = game.get(f"{p} Rolle", "N/A")
                player_list_items.append(
                    dbc.ListGroupItem(
                        [
                            html.Div(p, className="fw-bold"),
                            html.Div(f"{hero} ({role})", className="text-muted"),
                        ],
                        className="d-flex justify-content-between align-items-center",
                    )
                )
        result_color, result_text = (
            ("success", "VICTORY")
            if game.get("Win Lose") == "Win"
            else ("danger", "DEFEAT")
        )
        date_str = ""
        if pd.notna(game.get("Datum")):
            try:
                date_str = game["Datum"].strftime("%d.%m.%Y")
            except AttributeError:
                date_str = "Invalid Date"
        map_name, gamemode = game.get("Map", "Unknown Map"), game.get("Gamemode", "")
        card = dbc.Card(
            [
                dbc.CardHeader(
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.H5(
                                        f"{map_name} — {gamemode}", className="mb-0"
                                    ),
                                    html.Small(date_str, className="text-muted"),
                                ]
                            ),
                            dbc.Badge(
                                result_text, color=result_color, className="ms-auto"
                            ),
                        ],
                        className="d-flex justify-content-between align-items-center",
                    )
                ),
                dbc.CardBody(dbc.ListGroup(player_list_items, flush=True)),
            ],
            className="mb-3",
        )
        history_items.append(card)
    return history_items


# --- Callbacks ---
@app.callback(
    Output("dummy-output", "children"),
    Input("update-data-button", "n_clicks"),
    prevent_initial_call=True,
)
def update_data(n_clicks):
    if n_clicks > 0:
        load_data(use_local=False)
    return f"Data updated at {pd.Timestamp.now()}"


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
    Output("compare-switches-container", "children"), Input("player-dropdown", "value")
)
def generate_comparison_switches(selected_player):
    other_players = [p for p in constants.players if p != selected_player]
    if not other_players:
        return None
    switches = [html.Label("Vergleiche mit:", className="fw-bold")]
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


# --- NEW CALLBACK TO FIX THE BUG ---
@app.callback(
    Output({"type": "compare-switch", "player": ALL}, "value"),
    Input("player-dropdown", "value"),
    State({"type": "compare-switch", "player": ALL}, "value"),
    prevent_initial_call=True,
)
def reset_compare_switches(selected_player, switch_values):
    """
    This callback's only job is to reset all comparison switches to False
    when the main player is changed, preventing the "ghost state" bug.
    """
    # We need to return a list of `False` values, one for each switch.
    return [False] * len(switch_values)


@app.callback(
    Output("map-view-type-container", "style"), Input("map-stat-type", "value")
)
def toggle_view_type_visibility(map_stat_type):
    return {"display": "block"} if map_stat_type == "winrate" else {"display": "none"}


@app.callback(
    Output("min-games-slider", "disabled"),
    Output("slider-hint", "children"),
    Input("tabs", "active_tab"),
    Input("hero-stat-type", "value"),
    Input("role-stat-type", "value"),
    Input("map-stat-type", "value"),
)
def toggle_slider(tab, hero_stat, role_stat, map_stat):
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
    Input("dummy-output", "children"),
    State("history-display-count-store", "data"),
    State("history-load-amount-dropdown", "value"),
)
def update_history_display(n_clicks, _, current_store, load_amount):
    global df
    if df.empty:
        return [dbc.Alert("No data available to show history.", color="danger")], {
            "count": 10
        }
    triggered_id = ctx.triggered_id if ctx.triggered_id else "dummy-output"
    current_count = current_store.get("count", 10)
    if triggered_id == "load-more-history-button":
        new_count = current_count + load_amount
    else:
        new_count = 10
    games_to_show = df.head(new_count)
    history_layout = generate_history_layout_simple(games_to_show)
    return history_layout, {"count": new_count}


@app.callback(
    Output("map-stat-graph", "figure"),
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
):
    dataframes = {player: filter_data(player, season, month, year)}
    active_compare_players = []
    if compare_ids:  # compare_ids can be empty on first load
        for i, is_on in enumerate(compare_values):
            if is_on:
                p_name = compare_ids[i]["player"]
                active_compare_players.append(p_name)
                dataframes[p_name] = filter_data(p_name, season, month, year)
    main_df = dataframes[player]
    title_suffix = f"({player}{' vs ' + ', '.join(active_compare_players) if active_compare_players else ''})"
    empty_fig = go.Figure(layout={"title": "Keine Daten für die Auswahl verfügbar"})
    stats_header = f"Gesamtstatistiken ({player})"
    if not main_df.empty:
        total, wins = len(main_df), len(main_df[main_df["Win Lose"] == "Win"])
        losses, winrate = total - wins, wins / total if total > 0 else 0
        stats_container = dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [dbc.CardHeader("Gesamtspiele"), dbc.CardBody(f"{total}")],
                        className="text-center",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [dbc.CardHeader("Gewonnen"), dbc.CardBody(f"{wins}")],
                        className="text-center bg-success text-white",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [dbc.CardHeader("Verloren"), dbc.CardBody(f"{losses}")],
                        className="text-center bg-danger text-white",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [dbc.CardHeader("Winrate"), dbc.CardBody(f"{winrate:.0%}")],
                        className="text-center bg-warning",
                    ),
                    width=3,
                ),
            ]
        )
    else:
        stats_container = html.Div("Keine Daten für die Auswahl verfügbar.")
    map_fig = go.Figure()
    if map_stat_type == "winrate" and map_view_type and not active_compare_players:
        map_data = calculate_winrate(main_df, "Map")
        map_data = map_data[map_data["Spiele"] >= min_games]
        if not map_data.empty and "Attack Def" in main_df.columns:
            attack_def_data = main_df[
                main_df["Attack Def"].isin(["Attack", "Defense"])
            ].copy()
            combined_data = []
            for _, map_row in map_data.iterrows():
                map_name = map_row["Map"]
                combined_data.append(
                    {
                        "Map": map_name,
                        "Mode": "Overall",
                        "Winrate": map_row["Winrate"],
                        "Spiele": map_row["Spiele"],
                    }
                )
                map_specific_ad = attack_def_data[attack_def_data["Map"] == map_name]
                if not map_specific_ad.empty:
                    ad_stats = calculate_winrate(map_specific_ad, "Attack Def")
                    for _, row in ad_stats.iterrows():
                        combined_data.append(
                            {
                                "Map": map_name,
                                "Mode": row["Attack Def"],
                                "Winrate": row["Winrate"],
                                "Spiele": row["Spiele"],
                            }
                        )
            if combined_data:
                combined_df = pd.DataFrame(combined_data)
                map_fig = px.bar(
                    combined_df,
                    x="Map",
                    y="Winrate",
                    color="Mode",
                    barmode="group",
                    title=f"Map Winrates (Detailliert) - {player}",
                    category_orders={"Mode": ["Overall", "Attack", "Defense"]},
                    custom_data=["Spiele"],
                )
                map_fig.update_traces(
                    hovertemplate="Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<extra></extra>"
                )
                map_fig.update_layout(yaxis_tickformat=".0%")
            else:
                map_fig = empty_fig
        else:
            map_fig = empty_fig
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
                        map_fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                customdata=stats[["Spiele"]],
                                hovertemplate="<b>%{x}</b><br>Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<extra></extra>",
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
                        map_fig.add_trace(
                            go.Bar(
                                x=stats[group_col],
                                y=stats[y_col],
                                name=name,
                                hovertemplate="<b>%{x}</b><br>Spiele: %{y}<extra></extra>",
                            )
                        )
        map_fig.update_layout(
            title=f"{map_stat_type.title().replace('def', 'Def')} nach {group_col} {title_suffix}",
            barmode="group",
            yaxis_title=y_col,
            legend_title="Spieler",
        )
        if y_col == "Winrate":
            map_fig.update_layout(yaxis_tickformat=".0%")
        if not map_fig.data:
            map_fig = empty_fig

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
                                customdata=stats[["Spiele"]],
                                hovertemplate="<b>%{x}</b><br>Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<extra></extra>",
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
                                hovertemplate="<b>%{x}</b><br>Spiele: %{y}<extra></extra>",
                            )
                        )
        fig.update_layout(
            title=f"{stat_type.title()} nach {group_col} {title_suffix}",
            barmode="group",
            yaxis_title=y_col,
            legend_title="Spieler",
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
                    title=f"Winrate Heatmap – {player}",
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
                winrate_fig.add_trace(
                    go.Scatter(
                        x=time_data["GameNum"],
                        y=time_data["CumulativeWinrate"],
                        mode="lines",
                        name=name,
                    )
                )
    winrate_fig.update_layout(
        title=f"Winrate-Verlauf {title_suffix}",
        yaxis_tickformat=".0%",
        yaxis_title="Winrate",
        xaxis_title="Spielnummer",
        legend_title="Spieler",
    )
    if not winrate_fig.data:
        winrate_fig = empty_fig
    hero_options = (
        [{"label": h, "value": h} for h in sorted(main_df["Hero"].dropna().unique())]
        if not main_df.empty
        else []
    )
    return (
        map_fig,
        hero_fig,
        role_fig,
        heatmap_fig,
        stats_header,
        stats_container,
        winrate_fig,
        hero_options,
    )


if __name__ == "__main__":
    app.run(debug=True)
