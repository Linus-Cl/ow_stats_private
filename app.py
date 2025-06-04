import pandas as pd
import plotly.express as px
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc

# Daten laden
df = pd.read_excel("OW_Win_Stats.xlsx", sheet_name="Daten")

# Spalten bereinigen
df.columns = df.columns.str.strip()

# App initialisieren
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Layout
app.layout = dbc.Container(
    [
        html.H1("Overwatch Match-Analyse", className="my-4 text-center"),
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
                                                    "label": "Alle Spieler",
                                                    "value": "all",
                                                },
                                                {"label": "Steven", "value": "Steven"},
                                                {"label": "Phil", "value": "Phil"},
                                                {"label": "Bobo", "value": "Bobo"},
                                            ],
                                            value="all",
                                            clearable=False,
                                            className="mb-3",
                                        ),
                                        dbc.Label("Mindestanzahl Spiele:"),
                                        dcc.Slider(
                                            id="min-games-slider",
                                            min=1,
                                            max=10,
                                            step=1,
                                            value=3,
                                            marks={i: str(i) for i in range(1, 11)},
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
                                    "Statistiken", className="bg-primary text-white"
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


# Hilfsfunktionen
def filter_data(player, min_games=1):
    temp = df[df["Win Lose"].isin(["Win", "Lose"])].copy()

    if player != "all":
        role_col = f"{player} Rolle"
        hero_col = f"{player} Hero"

        # Filtere nach Spieler, wenn er in der Partie war
        temp = temp[temp[role_col].notna() & (temp[role_col] != "nicht dabei")]
        temp["Hero"] = temp[hero_col]
        temp["Rolle"] = temp[role_col]
    else:
        # Für "Alle Spieler" müssen wir die Daten anders aufbereiten
        hero_data = []

        for p in ["Steven", "Phil", "Bobo"]:
            role_col = f"{p} Rolle"
            hero_col = f"{p} Hero"

            player_matches = temp[
                temp[role_col].notna() & (temp[role_col] != "nicht dabei")
            ].copy()
            if not player_matches.empty:
                player_matches["Hero"] = player_matches[hero_col]
                player_matches["Rolle"] = player_matches[role_col]
                player_matches["Spieler"] = p
                hero_data.append(player_matches)

        if hero_data:
            temp = pd.concat(hero_data)
        else:
            temp = pd.DataFrame(
                columns=temp.columns.tolist() + ["Hero", "Rolle", "Spieler"]
            )

    return temp


def calculate_winrate(data, group_col):
    if group_col not in data.columns:
        return pd.DataFrame(columns=[group_col, "Win", "Lose", "Winrate", "Spiele"])

    grouped = data.groupby([group_col, "Win Lose"]).size().reset_index(name="Anzahl")
    pivot = grouped.pivot(index=group_col, columns="Win Lose", values="Anzahl").fillna(
        0
    )
    pivot["Winrate"] = pivot["Win"] / (pivot["Win"] + pivot["Lose"])
    pivot["Spiele"] = pivot["Win"] + pivot["Lose"]
    pivot = pivot.reset_index()

    return pivot.sort_values("Winrate", ascending=False)


def calculate_winrate(data, group_col):
    grouped = data.groupby([group_col, "Win Lose"]).size().reset_index(name="Anzahl")
    pivot = grouped.pivot(index=group_col, columns="Win Lose", values="Anzahl").fillna(
        0
    )
    pivot["Winrate"] = pivot["Win"] / (pivot["Win"] + pivot["Lose"])
    pivot["Spiele"] = pivot["Win"] + pivot["Lose"]
    pivot = pivot.reset_index()

    return pivot.sort_values("Winrate", ascending=False)


# Callbacks
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

    # Map Winrate
    map_data = calculate_winrate(temp, "Map")
    map_fig = px.bar(
        map_data,
        x="Map",
        y="Winrate",
        title=f"Winrate nach Map ({player if player != 'all' else 'Alle Spieler'})",
        hover_data=["Spiele"],
    )
    map_fig.update_layout(yaxis_tickformat=".0%")

    # Hero Winrate (mit Mindestanzahl Spielen)
    hero_data = calculate_winrate(temp, "Hero")
    hero_data = hero_data[hero_data["Spiele"] >= min_games]
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

    # Role Winrate
    role_data = calculate_winrate(temp, "Rolle")
    role_fig = px.bar(
        role_data,
        x="Rolle",
        y="Winrate",
        title=f"Winrate nach Rolle ({player if player != 'all' else 'Alle Spieler'})",
        hover_data=["Spiele"],
    )
    role_fig.update_layout(yaxis_tickformat=".0%")

    # Statistik-Karten
    total_games = len(temp)
    wins = len(temp[temp["Win Lose"] == "Win"])
    winrate = wins / total_games if total_games > 0 else 0

    stats = [
        dbc.Row(
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
    ]

    return map_fig, hero_fig, role_fig, stats


if __name__ == "__main__":
    app.run(debug=True)
