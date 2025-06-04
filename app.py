import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import requests

# load excel sheet from url
# url = "https://1drv.ms/x/c/52e69849288833a4/EcGhp7beEihJvXlvTDTu7TcBSwvjQkkS4fvYQubSeZHOPQ?e=SQ5bJc&download=1"
# response = requests.get(url)

# with open("local.xlsx", "wb") as f:
#     f.write(response.content)

df = pd.read_excel("local.xlsx", sheet_name="Daten")

df.columns = df.columns.str.strip()

# Initialize app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Layout
app.layout = dbc.Container(
    [
        html.H1("Overwatch Statistics", className="my-4 text-center"),
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
                                                {"label": "Steven", "value": "Steven"},
                                                {"label": "Phil", "value": "Phil"},
                                                {"label": "Bobo", "value": "Bobo"},
                                            ],
                                            value="Steven",
                                            clearable=False,
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
                                            className="mb-3",
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
                                    "Gesamtstatistiken",
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
    ],
    fluid=True,
)


def filter_data(player):
    temp = df[df["Win Lose"].isin(["Win", "Lose"])].copy()

    if player != "all":
        role_col = f"{player} Rolle"
        hero_col = f"{player} Hero"

        # Filter for player participation
        temp = temp[temp[role_col].notna() & (temp[role_col] != "nicht dabei")]
        temp["Hero"] = temp[hero_col].str.strip()
        temp["Rolle"] = temp[role_col].str.strip()
    else:
        # Combine data for all players
        hero_data = []

        for p in ["Steven", "Phil", "Bobo"]:
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

    # Clean data
    if not temp.empty:
        temp = temp[temp["Hero"].notna()]
        temp = temp[temp["Hero"] != ""]

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
    [
        Output("winrate-map-graph", "figure"),
        Output("winrate-hero-graph", "figure"),
        Output("winrate-role-graph", "figure"),
        Output("stats-container", "children"),
    ],
    [Input("player-dropdown", "value"), Input("min-games-slider", "value")],
)
def update_all_graphs(player, min_games):
    temp = filter_data(player)
    data_all = filter_data("all")

    map_fig = px.bar(title="Keine Map-Daten verfügbar")
    hero_fig = px.bar(title="Keine Held-Daten verfügbar")
    role_fig = px.bar(title="Keine Rollen-Daten verfügbar")
    stats = html.Div("Keine Daten verfügbar")

    if not temp.empty:
        # === Corrected total game count ===
        if player == "all":
            # Use unique matches (e.g., by "Datum" and "Map" combination)
            unique_games = temp[["Datum", "Map"]].drop_duplicates()
        else:
            # Each row is already a unique match for the player
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

    if not data_all.empty:
        # === Corrected total game count ===

        unique_games = data_all[["Datum", "Map"]].drop_duplicates()

        unique_games = data_all.drop_duplicates(subset=["Datum", "Map"])
        total_games = unique_games.shape[0]
        wins = unique_games[unique_games["Win Lose"] == "Win"].shape[0]
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
                    width=4,
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
                    width=4,
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
                    width=4,
                ),
            ],
            className="mb-2",
        )
    return map_fig, hero_fig, role_fig, stats


if __name__ == "__main__":
    app.run(debug=False)
