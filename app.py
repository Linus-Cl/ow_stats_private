import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output, ctx
import dash_bootstrap_components as dbc
import requests
from io import StringIO

import constants


# Initialize app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
df = pd.DataFrame()


def load_data(use_local=True):
    global df
    if use_local:
        try:
            # First try reading as Excel
            try:
                df = pd.read_excel("local.xlsx", sheet_name=0, engine="openpyxl")
                print("Loaded data from local.xlsx")
            except:
                # Fallback to CSV if Excel fails
                df = pd.read_csv("local.xlsx")
                print("Loaded CSV data from local.xlsx")
        except Exception as e:
            print(f"Error loading local file: {e}")
            df = pd.DataFrame()  # Ensure df exists even if empty
    else:
        try:
            # Download and read CSV directly
            response = requests.get(constants.url)
            response.raise_for_status()

            df = pd.read_csv(StringIO(response.text))

            # Save as Excel for future local use
            df.to_excel("local.xlsx", index=False, engine="openpyxl")
            print("Successfully downloaded and saved as Excel!")

        except Exception as e:
            print(f"Error downloading data: {e}")
            # Don't overwrite df if download fails
            if "df" not in globals():
                df = pd.DataFrame()

    if not df.empty:
        df.columns = df.columns.str.strip()


# Load local data by default when starting
load_data(use_local=True)

# Layout
app.layout = dbc.Container(
    [
        html.H1("Overwatch Statistics", className="my-4 text-center"),
        dbc.Row(
            dbc.Col(
                dbc.Button(
                    "Update Data from Cloud",
                    id="update-data-button",
                    color="primary",
                    className="mb-3",
                    n_clicks=0,
                ),
                width={"size": 3, "offset": 9},
            )
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
                                                {
                                                    "label": constants.players[0],
                                                    "value": constants.players[0],
                                                },
                                                {
                                                    "label": constants.players[1],
                                                    "value": constants.players[1],
                                                },
                                                {
                                                    "label": constants.players[2],
                                                    "value": constants.players[2],
                                                },
                                            ],
                                            value=constants.players[0],
                                            clearable=False,
                                            className="mb-3",
                                        ),
                                        dbc.Label("Season auswählen:"),
                                        dcc.Dropdown(
                                            id="season-dropdown",
                                            options=[
                                                {"label": s, "value": s}
                                                for s in sorted(
                                                    df["Season"].dropna().unique()
                                                )
                                            ],
                                            value=None,
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                        ),
                                        dbc.Label("Jahr auswählen:"),
                                        dcc.Dropdown(
                                            id="year-dropdown",
                                            options=[
                                                {
                                                    "label": str(int(jahr)),
                                                    "value": int(jahr),
                                                }
                                                for jahr in sorted(
                                                    df["Jahr"].dropna().unique()
                                                )
                                            ],
                                            value=None,
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                        ),
                                        dbc.Label("Monat auswählen:"),
                                        dcc.Dropdown(
                                            id="month-dropdown",
                                            options=[
                                                {"label": monat, "value": monat}
                                                for monat in sorted(
                                                    df["Monat"].dropna().unique()
                                                )
                                            ],
                                            value=None,
                                            placeholder="(keine ausgewählt)",
                                            className="mb-3",
                                        ),
                                        dbc.Label("Mindestanzahl Spiele:"),
                                        dcc.Slider(
                                            id="min-games-slider",
                                            min=1,
                                            max=100,
                                            step=None,
                                            value=25,
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
                                    dcc.Graph(id="winrate-map-graph"),
                                    label="Winrate nach Map",
                                    tab_id="tab-1",
                                ),
                                dbc.Tab(
                                    dcc.Graph(id="winrate-hero-graph"),
                                    label="Winrate nach Held",
                                    tab_id="tab-2",
                                ),
                                dbc.Tab(
                                    dcc.Graph(id="winrate-role-graph"),
                                    label="Winrate nach Rolle",
                                    tab_id="tab-3",
                                ),
                                dbc.Tab(
                                    dcc.Graph(id="plays-hero-graph"),
                                    label="Spiele pro Held",
                                    tab_id="tab-4",
                                ),
                                dbc.Tab(
                                    dcc.Graph(id="performance-heatmap"),
                                    label="Performance Heatmap",
                                    tab_id="tab-5",
                                ),
                                dbc.Tab(
                                    [
                                        dbc.Label("Held filtern (optional):"),
                                        dcc.Dropdown(
                                            id="hero-filter-dropdown",
                                            placeholder="Kein Held ausgewählt",
                                            className="mb-3",
                                        ),
                                        dcc.Graph(id="winrate-over-time"),
                                    ],
                                    label="Winrate Verlauf",
                                    tab_id="tab-6",
                                ),
                            ],
                            id="tabs",
                            active_tab="tab-1",
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
                                    "Gesamtstatistiken (alle Spieler)",
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
        dcc.Store(id="data-store"),  # Store component to trigger callbacks
        html.Div(
            id="dummy-output", style={"display": "none"}
        ),  # Hidden div for callback output
    ],
    fluid=True,
)


def filter_data(player, season=None, month=None, year=None):
    global df
    temp = df[df["Win Lose"].isin(["Win", "Lose"])].copy()

    # Prioritize Season
    if season:
        temp = temp[temp["Season"] == season]
    elif year:
        if month:
            temp = temp[(temp["Jahr"] == year) & (temp["Monat"] == month)]
        else:
            temp = temp[temp["Jahr"] == year]
    elif month:
        temp = temp[temp["Monat"] == month]

    # Player-Handling
    if player != "all":
        role_col = f"{player} Rolle"
        hero_col = f"{player} Hero"
        temp = temp[temp[role_col].notna() & (temp[role_col] != "nicht dabei")]
        temp["Hero"] = temp[hero_col].str.strip()
        temp["Rolle"] = temp[role_col].str.strip()
    else:
        hero_data = []
        for p in constants.players:
            role_col = f"{p} Rolle"
            hero_col = f"{p} Hero"
            player_matches = temp[
                temp[role_col].notna() & (temp[role_col] != "nicht dabei")
            ].copy()
            if not player_matches.empty:
                player_matches["Hero"] = player_matches[hero_col].str.strip()
                player_matches["Rolle"] = player_matches[role_col].str.strip()
                player_matches["Spieler"] = p
                hero_data.append(player_matches)
        temp = pd.concat(hero_data) if hero_data else pd.DataFrame()

    if not temp.empty:
        temp = temp[temp["Hero"].notna() & (temp["Hero"] != "")]

    return temp


def calculate_winrate(data, group_col):
    if data.empty or group_col not in data.columns:
        return pd.DataFrame(columns=[group_col, "Win", "Lose", "Winrate", "Spiele"])

    # Clean group column
    data[group_col] = data[group_col].str.strip()
    data = data[data[group_col].notna()]
    data = data[data[group_col] != ""]

    grouped = data.groupby([group_col, "Win Lose"]).size().reset_index(name="Anzahl")
    pivot = grouped.pivot(index=group_col, columns="Win Lose", values="Anzahl").fillna(
        0
    )
    pivot["Winrate"] = pivot["Win"] / (pivot["Win"] + pivot["Lose"])
    pivot["Spiele"] = pivot["Win"] + pivot["Lose"]
    pivot = pivot.reset_index()

    return pivot.sort_values("Winrate", ascending=False)


@app.callback(
    Output("season-dropdown", "value"),
    Output("month-dropdown", "value"),
    Output("year-dropdown", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
)
def sync_time_filters(season, month, year):
    triggered = ctx.triggered_id

    if triggered == "season-dropdown" and season:
        return season, None, None
    elif triggered in ["month-dropdown", "year-dropdown"] and (month or year):
        return None, month, year
    return season, month, year


@app.callback(
    Output("min-games-slider", "disabled"),
    Output("slider-hint", "children"),
    Input("tabs", "active_tab"),
)
def toggle_slider(tab):
    if tab == "tab-2":
        return False, ""
    else:
        return True, "Nur relevant für 'Winrate nach Held'."


@app.callback(
    Output("dummy-output", "children"),
    Input("update-data-button", "n_clicks"),
    prevent_initial_call=True,
)
def update_data(n_clicks):
    if n_clicks > 0:
        load_data(use_local=False)
    return ""


@app.callback(
    [
        Output("winrate-map-graph", "figure"),
        Output("winrate-hero-graph", "figure"),
        Output("winrate-role-graph", "figure"),
        Output("plays-hero-graph", "figure"),
        Output("performance-heatmap", "figure"),
        Output("stats-container", "children"),
        Output("winrate-over-time", "figure"),
        Output("hero-filter-dropdown", "options"),
        Output("season-dropdown", "options"),
        Output("month-dropdown", "options"),
        Output("year-dropdown", "options"),
    ],
    [
        Input("player-dropdown", "value"),
        Input("min-games-slider", "value"),
        Input("season-dropdown", "value"),
        Input("month-dropdown", "value"),
        Input("year-dropdown", "value"),
        Input("hero-filter-dropdown", "value"),
        Input("dummy-output", "children"),  # Trigger when data is updated
    ],
)
def update_all_graphs(player, min_games, season, month, year, hero_filter, _):
    global df

    temp = filter_data(player, season, month, year)
    data_all = filter_data("all", season, month, year)
    map_fig = px.bar(title="Keine Map-Daten verfügbar")
    hero_fig = px.bar(title="Keine Held-Daten verfügbar")
    role_fig = px.bar(title="Keine Rollen-Daten verfügbar")
    plays_fig = px.bar(title="Keine Held-Spieldaten verfügbar")
    stats = html.Div("Keine Daten verfügbar")
    heatmap_fig = px.imshow([[0]], title="Keine Daten verfügbar")

    if not temp.empty:
        # === total game count ===
        if player == "all":
            unique_games = data_all
        else:
            unique_games = temp

        total_games = unique_games.shape[0]
        wins = unique_games[unique_games["Win Lose"] == "Win"].shape[0]
        winrate = wins / total_games if total_games > 0 else 0

        # === Map Winrate ===
        map_data = calculate_winrate(temp, "Map")
        if not map_data.empty:
            map_fig = px.bar(
                map_data,
                x="Map",
                y="Winrate",
                title=f"Winrate nach Map ({player if player != 'all' else 'Alle Spieler'})",
                hover_data=["Spiele"],
            )
            map_fig.update_layout(yaxis_tickformat=".0%")

        # === Hero Winrate ===
        hero_data = calculate_winrate(temp, "Hero")
        hero_data = hero_data[hero_data["Spiele"] >= min_games]
        if not hero_data.empty:
            hero_fig = px.bar(
                hero_data,
                x="Hero",
                y="Winrate",
                title=f"Winrate nach Held (min. {min_games} Spiele) ({player if player != 'all' else 'Alle Spieler'})",
                hover_data=["Spiele"],
                color="Winrate",
                color_continuous_scale="RdYlGn",
                range_color=[0, 1],
            )
            hero_fig.update_layout(yaxis_tickformat=".0%")

        # === Role Winrate ===
        role_data = calculate_winrate(temp, "Rolle")
        if not role_data.empty:
            role_fig = px.bar(
                role_data,
                x="Rolle",
                y="Winrate",
                title=f"Winrate nach Rolle ({player if player != 'all' else 'Alle Spieler'})",
                hover_data=["Spiele"],
            )
            role_fig.update_layout(yaxis_tickformat=".0%")

        # === games-per-hero ===
        hero_counts = (
            temp.groupby("Hero")
            .size()
            .reset_index(name="Spiele")
            .sort_values("Spiele", ascending=False)
        )

        if not hero_counts.empty:
            plays_fig = px.bar(
                hero_counts,
                x="Hero",
                y="Spiele",
                text="Spiele",
                title=f"Spiele pro Held ({'Alle Spieler' if player=='all' else player})",
            )
            plays_fig.update_layout(xaxis_title="", yaxis_title="Spiele")

        # === Performance Heatmap: Hero × Map Winrate ===
        if not temp.empty:
            # Create winrate pivot table
            winrate_pivot = temp.pivot_table(
                index="Rolle",
                columns="Map",
                values="Win Lose",
                aggfunc=lambda x: (x == "Win").sum() / len(x),
            ).fillna(0)

            # Create game count pivot table
            count_pivot = temp.pivot_table(
                index="Rolle",
                columns="Map",
                values="Win Lose",
                aggfunc="count",
            ).fillna(0)

            if not winrate_pivot.empty:
                # Create a list of lists for custom data containing both winrate and count
                custom_data = []
                for i in range(len(winrate_pivot)):
                    row = []
                    for j in range(len(winrate_pivot.columns)):
                        row.append([winrate_pivot.iloc[i, j], count_pivot.iloc[i, j]])
                    custom_data.append(row)

                heatmap_fig = px.imshow(
                    winrate_pivot,
                    text_auto=".0%",
                    color_continuous_scale="RdYlGn",
                    zmin=0,
                    zmax=1,
                    aspect="auto",
                    title=f"Winrate Heatmap – {player if player != 'all' else 'Alle Spieler'}",
                )

                # Add custom data to the figure
                heatmap_fig.data[0].customdata = custom_data
                heatmap_fig.data[0].hovertemplate = (
                    "<b>Role:</b> %{y}<br>"
                    "<b>Map:</b> %{x}<br>"
                    "<b>Winrate:</b> %{z:.1%}<br>"
                    "<b>Games Played:</b> %{customdata[1]:,}<extra></extra>"
                )

                heatmap_fig.update_layout(
                    xaxis_title="Map",
                    yaxis_title="Rolle",
                    margin=dict(l=40, r=20, t=60, b=40),
                )

    # === Dropdown-Optionen für Held ===
    hero_options = (
        [{"label": h, "value": h} for h in sorted(temp["Hero"].dropna().unique())]
        if not temp.empty
        else []
    )

    # === Time filter options ===
    season_options = (
        [{"label": s, "value": s} for s in sorted(df["Season"].dropna().unique())]
        if not df.empty
        else []
    )

    month_options = (
        [
            {"label": monat, "value": monat}
            for monat in sorted(df["Monat"].dropna().unique())
        ]
        if not df.empty
        else []
    )

    year_options = (
        [
            {"label": str(int(jahr)), "value": int(jahr)}
            for jahr in sorted(df["Jahr"].dropna().unique())
        ]
        if not df.empty
        else []
    )

    # === Winrate Over Time ===
    winrate_fig = px.line(title="Keine Daten verfügbar")

    if not temp.empty:
        time_data = temp.copy()

        if hero_filter:
            time_data = time_data[time_data["Hero"] == hero_filter]

        if not time_data.empty:
            time_data = time_data.sort_values("Datum").reset_index(drop=True)
            time_data["WinBinary"] = (time_data["Win Lose"] == "Win").astype(int)
            time_data["GameNumber"] = range(1, len(time_data) + 1)
            time_data["CumulativeWins"] = time_data["WinBinary"].cumsum()
            time_data["CumulativeWinrate"] = (
                time_data["CumulativeWins"] / time_data["GameNumber"]
            )

            winrate_fig = px.line(
                time_data,
                x="GameNumber",
                y="CumulativeWinrate",
                title=f"Winrate-Verlauf ({'Held: ' + hero_filter if hero_filter else player})",
            )
            winrate_fig.update_layout(
                yaxis_tickformat=".0%", yaxis_title="Winrate", xaxis_title="Spielnummer"
            )

    if not data_all.empty:
        # === Corrected total game count using Match ID ===
        total_games = data_all["Match ID"].nunique()
        wins = data_all[data_all["Win Lose"] == "Win"]["Match ID"].nunique()
        losses = data_all[data_all["Win Lose"] == "Lose"]["Match ID"].nunique()

        # === Statistics ===
        stats = dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Gesamtspiele", className="bg-info text-white"
                            ),
                            dbc.CardBody(f"{total_games}"),
                        ],
                        className="text-center",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Gewonnen", className="bg-success text-white"
                            ),
                            dbc.CardBody(f"{wins}"),
                        ],
                        className="text-center",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Verloren", className="bg-danger text-white"
                            ),
                            dbc.CardBody(f"{losses}"),
                        ],
                        className="text-center",
                    ),
                    width=3,
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader(
                                "Winrate", className="bg-warning text-white"
                            ),
                            dbc.CardBody(f"{winrate:.0%}"),
                        ],
                        className="text-center",
                    ),
                    width=3,
                ),
            ],
            className="mb-2",
        )

    return (
        map_fig,
        hero_fig,
        role_fig,
        plays_fig,
        heatmap_fig,
        stats,
        winrate_fig,
        hero_options,
        season_options,
        month_options,
        year_options,
    )


if __name__ == "__main__":
    app.run(debug=False)
