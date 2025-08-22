"""Dash Overwatch Stats App"""

# Standard library
import os
import re
from io import StringIO
import hashlib
import json

# Third-party
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import dash_bootstrap_components as dbc
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
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
        # VALIDATE REQUIRED COLUMNS
        required = ["Win Lose", "Map", "Match ID"]
        missing = [c for c in required if c not in df.columns]
        if missing:
            print(f"Warnung: Fehlende Pflichtspalten: {missing}")

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

        # Normalize role labels across all per-player role columns
        role_map = {
            "DPS": "Damage",
            "Damage": "Damage",
            "Tank": "Tank",
            "Support": "Support",
        }
        for col in df.columns:
            if col.endswith(" Rolle"):
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
        # Perform a conditional (non-forced) fetch; ignore result silently
        _fetch_update_from_cloud(force=False)
except Exception:
    pass


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
app.layout = dbc.Container(
    [
        # Store removed (no longer needed for dropdown-based assignment)
        dcc.Store(id="history-display-count-store", data={"count": 10}),
        dcc.Store(id="role-history-count-store", data={"count": 10}),
        # Hidden periodic auto-update (no UI elements added)
        dcc.Interval(
            id="auto-update-tick",
            interval=(
                int(
                    os.environ.get("AUTO_UPDATE_MINUTES", constants.AUTO_UPDATE_MINUTES)
                )
                * 60
                * 1000
            ),
        ),
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
                                        html.Div(id="map-stat-container"),
                                    ],
                                ),
                                dbc.Tab(
                                    label="Rollen-Zuordnung",
                                    tab_id="tab-role-assign",
                                    children=[
                                        html.P(
                                            "Weise drei Spieler den Rollen zu. Jeder Spieler darf nur einmal vorkommen."
                                        ),
                                        dbc.Row(
                                            [
                                                dbc.Col(
                                                    [
                                                        dbc.Label(
                                                            "Tank (max. 1 Spieler)"
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
                                                            "Damage (max. 2 Spieler)"
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
                                                            "Support (max. 2 Spieler)"
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
                                                        "Detaillierter Modus (Helden wählen)"
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
                                                    width={"size": 3, "offset": 3},
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
                                        dbc.Card(
                                            dbc.CardBody(
                                                [
                                                    dbc.Row(
                                                        [
                                                            dbc.Col(
                                                                [
                                                                    dbc.Label(
                                                                        "Spieler filtern:"
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
                                                                        "Held filtern:"
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
                                                    width={"size": 3, "offset": 3},
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
)
def build_detailed_hero_selectors(
    detail_on, tank_vals, dmg_vals, sup_vals, season, month, year
):
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
        return dbc.Alert("Bitte zuerst Spieler in Rollen auswählen.", color="info")

    global df
    if df.empty:
        return dbc.Alert("Keine Daten geladen.", color="danger")

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
                        placeholder="Helden wählen (optional)",
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
            return f"Data updated at {pd.Timestamp.now()}"
        return no_update
    if triggered == "auto-update-tick":
        updated = _fetch_update_from_cloud(force=False)
        if updated:
            return f"Data updated at {pd.Timestamp.now()}"
        return no_update
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
    Input("dummy-output", "children"),
)
def populate_role_assignment_options(_):
    if df.empty:
        opts = [{"label": p, "value": p} for p in constants.players]
        return opts, opts, opts
    # Derive players from columns ending with ' Rolle'
    players = []
    for col in df.columns:
        if col.endswith(" Rolle"):
            players.append(col.replace(" Rolle", ""))
    players = players or constants.players
    opts = [{"label": p, "value": p} for p in players]
    return opts, opts, opts


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
    Input("player-dropdown-match-verlauf", "value"),
    Input("hero-filter-dropdown-match", "value"),
    Input("dummy-output", "children"),
    State("history-display-count-store", "data"),
    State("history-load-amount-dropdown", "value"),
)
def update_history_display(
    n_clicks, player_name, hero_name, _, current_store, load_amount
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
    Input("role-detailed-toggle", "value"),
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    Input({"type": "detailed-hero", "player": ALL}, "value"),
    State({"type": "detailed-hero", "player": ALL}, "id"),
)
def compute_role_stats(
    tank_vals, dmg_vals, sup_vals, detail_on, season, month, year, hero_values, hero_ids
):
    # Normalize inputs to lists
    tank = tank_vals or []
    dmg = dmg_vals or []
    sup = sup_vals or []

    # Limits: allow partial selections
    if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
        return dbc.Alert(
            "Zu viele Spieler gewählt: max 1 Tank, max 2 Damage, max 2 Support.",
            color="warning",
        )
    if len(tank) + len(dmg) + len(sup) == 0:
        return dbc.Alert(
            "Bitte mindestens einen Spieler in einer Rolle auswählen.", color="info"
        )

    # Uniqueness
    all_players = tank + dmg + sup
    if len(set(all_players)) != len(all_players):
        return dbc.Alert(
            "Jeder Spieler darf nur einmal vorkommen (über alle Rollen).",
            color="warning",
        )

    global df
    if df.empty:
        return dbc.Alert("Keine Daten geladen.", color="danger")

    # Apply timeframe filters
    temp = df.copy()
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]
    if temp.empty:
        return dbc.Alert("Keine Daten für den gewählten Zeitraum.", color="info")

    # Verify required columns
    required_cols = ["Win Lose"]
    for p in all_players:
        required_cols += [f"{p} Rolle", f"{p} Hero"]
    missing = [c for c in required_cols if c not in temp.columns]
    if missing:
        return dbc.Alert(f"Erforderliche Spalten fehlen: {missing}", color="danger")

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
        return dbc.Alert("Keine Spiele für diese Konstellation gefunden.", color="info")

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

    # Optional: aktive Helden-Filter anzeigen
    hero_filters_block = None
    if selected_heroes:
        hero_lines = [
            html.Div(f"{p}: {', '.join(sorted(list(heroes)))}", className="small")
            for p, heroes in selected_heroes.items()
        ]
        hero_filters_block = html.Div(
            [html.Small("Helden-Filter:", className="text-muted d-block"), *hero_lines],
            className="mb-2",
        )

    return dbc.Card(
        [
            dbc.CardHeader(
                html.Div(
                    [html.Strong("Statistik zur Rollen-Konstellation"), header_badge],
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
                                        dbc.CardHeader("Spiele"),
                                        dbc.CardBody(html.H4(f"{total}")),
                                    ],
                                    className="text-center h-100",
                                )
                            ),
                            dbc.Col(
                                dbc.Card(
                                    [
                                        dbc.CardHeader("Gewonnen"),
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
                                        dbc.CardHeader("Verloren"),
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
                                        dbc.CardHeader("Winrate"),
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
    Input("season-dropdown", "value"),
    Input("month-dropdown", "value"),
    Input("year-dropdown", "value"),
    State({"type": "detailed-hero", "player": ALL}, "value"),
    State({"type": "detailed-hero", "player": ALL}, "id"),
)
def show_role_assignment_history(
    count_store,
    show,
    detail_on,
    tank_vals,
    dmg_vals,
    sup_vals,
    season,
    month,
    year,
    hero_values,
    hero_ids,
):
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

    if len(tank) > 1 or len(dmg) > 2 or len(sup) > 2:
        return dbc.Alert("Zu viele Spieler gewählt für die Historie.", color="warning")

    all_players = tank + dmg + sup
    if len(all_players) == 0:
        return dbc.Alert("Bitte mindestens einen Spieler auswählen.", color="info")
    if len(set(all_players)) != len(all_players):
        return dbc.Alert("Doppelte Spieler in Rollen-Auswahl.", color="warning")

    global df
    if df.empty:
        return dbc.Alert("Keine Daten geladen.", color="danger")

    temp = df.copy()
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]
    if temp.empty:
        return dbc.Alert("Keine Daten für den Zeitraum.", color="info")

    # Required columns
    for p in all_players:
        for c in [f"{p} Rolle", f"{p} Hero"]:
            if c not in temp.columns:
                return dbc.Alert(
                    "Erforderliche Spalten fehlen in den Daten.", color="danger"
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
        return dbc.Alert("Keine passenden Matches gefunden.", color="info")

    # Kompakte Liste mit Map-Thumbnail, Ergebnis-Badge und Spielerlinien
    items = []
    for _, row in subset.iterrows():
        map_name = row.get("Map", "—")
        map_img = get_map_image_url(map_name)
        date_str = (
            row["Datum"].strftime("%d.%m.%Y")
            if "Datum" in subset.columns and pd.notna(row.get("Datum"))
            else "—"
        )
        result = row.get("Win Lose")
        badge = dbc.Badge(
            "VICTORY" if result == "Win" else "DEFEAT",
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

        items.append(
            dbc.ListGroupItem(
                dbc.Row(
                    [
                        dbc.Col(
                            html.Img(
                                src=map_img,
                                style={
                                    "width": "80px",
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
                "Keine weiteren Einträge.",
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

    global df
    if df.empty:
        # Keine Daten -> Button ausblenden
        return True, dropdown_disabled

    temp = df.copy()
    if season and "Season" in temp.columns:
        temp = temp[temp["Season"] == season]
    else:
        if year is not None and "Jahr" in temp.columns:
            temp = temp[pd.to_numeric(temp["Jahr"], errors="coerce") == int(year)]
        if month is not None and "Monat" in temp.columns:
            temp = temp[temp["Monat"] == month]

    if temp.empty:
        return True, dropdown_disabled

    all_players = tank + dmg + sup
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
    if compare_ids:
        for i, is_on in enumerate(compare_values):
            if is_on:
                p_name = compare_ids[i]["player"]
                active_compare_players.append(p_name)
                dataframes[p_name] = filter_data(p_name, season, month, year)
    main_df = dataframes[player]
    title_suffix = f"({player}{' vs ' + ', '.join(active_compare_players) if active_compare_players else ''})"
    empty_fig = go.Figure(layout={"title": "Keine Daten für die Auswahl verfügbar"})
    stats_header = f"Gesamtstatistiken ({player})"

    stats_container = html.Div("Keine Daten für die Auswahl verfügbar.")
    if not main_df.empty:
        total, wins = len(main_df), len(main_df[main_df["Win Lose"] == "Win"])
        losses, winrate = total - wins, wins / total if total > 0 else 0

        # --- REVISED: Primary Stats Row with subtle colors ---
        primary_stats_row = dbc.Row(
            [
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Gesamtspiele"),
                            dbc.CardBody(html.H4(f"{total}")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Gewonnen"),
                            dbc.CardBody(html.H4(f"{wins}", className="text-success")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Verloren"),
                            dbc.CardBody(html.H4(f"{losses}", className="text-danger")),
                        ],
                        className="text-center h-100",
                    )
                ),
                dbc.Col(
                    dbc.Card(
                        [
                            dbc.CardHeader("Winrate"),
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
                "Meistgespielter Held",
                get_hero_image_url(most_played_hero),
                most_played_hero,
                f"{hero_plays} Spiele",
            )
        except (KeyError, IndexError):
            card = create_stat_card(
                "Meistgespielter Held", get_hero_image_url(None), "N/A", "Keine Daten"
            )
        secondary_stat_cards.append(card)
        try:
            hero_wr = calculate_winrate(main_df, "Hero")
            hero_wr_filtered = hero_wr[hero_wr["Spiele"] >= min_games]
            best_hero = hero_wr_filtered.loc[hero_wr_filtered["Winrate"].idxmax()]
            card = create_stat_card(
                "Beste Winrate (Held)",
                get_hero_image_url(best_hero["Hero"]),
                best_hero["Hero"],
                f"{best_hero['Winrate']:.0%} ({best_hero['Spiele']} Spiele)",
            )
        except (KeyError, IndexError, ValueError):
            card = create_stat_card(
                "Beste Winrate (Held)",
                get_hero_image_url(None),
                "N/A",
                f"Min. {min_games} Spiele",
            )
        secondary_stat_cards.append(card)
        try:
            most_played_map = main_df["Map"].mode()[0]
            map_plays = main_df["Map"].value_counts()[most_played_map]
            card = create_stat_card(
                "Meistgespielte Map",
                get_map_image_url(most_played_map),
                most_played_map,
                f"{map_plays} Spiele",
            )
        except (KeyError, IndexError):
            card = create_stat_card(
                "Meistgespielte Map", get_map_image_url(None), "N/A", "Keine Daten"
            )
        secondary_stat_cards.append(card)
        try:
            map_wr = calculate_winrate(main_df, "Map")
            map_wr_filtered = map_wr[map_wr["Spiele"] >= min_games]
            best_map = map_wr_filtered.loc[map_wr_filtered["Winrate"].idxmax()]
            card = create_stat_card(
                "Beste Winrate (Map)",
                get_map_image_url(best_map["Map"]),
                best_map["Map"],
                f"{best_map['Winrate']:.0%} ({best_map['Spiele']} Spiele)",
            )
        except (KeyError, IndexError, ValueError):
            card = create_stat_card(
                "Beste Winrate (Map)",
                get_map_image_url(None),
                "N/A",
                f"Min. {min_games} Spiele",
            )
        secondary_stat_cards.append(card)

        stats_container = html.Div([primary_stats_row, dbc.Row(secondary_stat_cards)])

    # (The rest of the function remains completely unchanged)
    map_stat_output = None
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
                plot_df["Mode"] = plot_df["Attack Def"].replace(
                    {"Attack Attack": "Gesamt"}
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
                    bar_fig = px.bar(
                        plot_data,
                        x="Map",
                        y="Winrate",
                        color="Mode",
                        barmode="group",
                        title=f"Map Winrates (Detailliert) - {player}",
                        category_orders={
                            "Map": map_data["Map"].tolist(),
                            "Mode": ["Gesamt", "Attack", "Defense"],
                        },
                        custom_data=["Spiele", "Win", "Lose"],
                        color_discrete_map={
                            "Gesamt": "lightslategrey",
                            "Attack": "#EF553B",
                            "Defense": "#636EFA",
                        },
                    )
                    bar_fig.update_traces(
                        hovertemplate="Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<br>Gewonnen: %{customdata[1]}<br>Verloren: %{customdata[2]}<extra></extra>"
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
                bar_fig = px.bar(
                    plays_by_side,
                    x="Map",
                    y="Spiele",
                    color="Seite",
                    barmode="stack",
                    title=f"Spiele pro Map (Detailliert) - {player}",
                    labels={"Spiele": "Anzahl Spiele", "Seite": "Seite"},
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
                                hovertemplate="<b>%{x}</b><br>Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<br>Gewonnen: %{customdata[1]}<br>Verloren: %{customdata[2]}<extra></extra>",
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
                                hovertemplate="<b>%{x}</b><br>Spiele: %{y}<extra></extra>",
                            )
                        )
        bar_fig.update_layout(
            title=f"{map_stat_type.title().replace('def', 'Def')} nach {group_col} {title_suffix}",
            barmode="group",
            yaxis_title=y_col,
            legend_title="Spieler",
        )
        if y_col == "Winrate":
            bar_fig.update_layout(yaxis_tickformat=".0%")
        if not bar_fig.data:
            bar_fig = empty_fig
    if map_stat_type == "winrate":
        map_stat_output = dbc.Row(dbc.Col(dcc.Graph(figure=bar_fig), width=12))
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
                    title=f"Verteilung {pie_data_col}",
                )
                pie_fig.update_traces(
                    hovertemplate="<b>%{label}</b><br>Spiele: %{value}<br>Anteil: %{percent}<extra></extra>"
                )
            else:
                pie_fig = empty_fig
        if map_stat_type == "plays":
            map_stat_output = dbc.Row([dbc.Col(dcc.Graph(figure=bar_fig), width=12)])
        else:
            map_stat_output = dbc.Row(
                [
                    dbc.Col(dcc.Graph(figure=bar_fig), width=7),
                    dbc.Col(dcc.Graph(figure=pie_fig), width=5),
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
                                hovertemplate="<b>%{x}</b><br>Winrate: %{y:.1%}<br>Spiele: %{customdata[0]}<br>Gewonnen: %{customdata[1]}<br>Verloren: %{customdata[2]}<extra></extra>",
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
                            "<b>Map: %{x}</b><br><b>Rolle: %{y}</b>"
                            "<br><b>Winrate: %{z: .1%}</b>"
                            "<br>Spiele: %{customdata[0]}"
                            "<br>Gewonnen: %{customdata[1]}"
                            "<br>Verloren: %{customdata[2]}<extra></extra>"
                        )
                    )
                except Exception:
                    # Fallback: nur Winrate anzeigen
                    heatmap_fig.update_traces(
                        hovertemplate="<b>Map: %{x}</b><br><b>Rolle: %{y}</b><br><b>Winrate: %{z: .1%}</b><extra></extra>"
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
        title=f"Winrate-Verlauf {title_suffix}",
        yaxis_tickformat=".0%",
        yaxis_title="Winrate",
        xaxis_title="Spielnummer",
        legend_title="Spieler",
    )
    winrate_fig.update_traces(
        hovertemplate=(
            "<b>Spielnummer: %{x}</b>"
            "<br><b>Winrate: %{y: .1%}</b>"
            "<br>Gewonnen: %{customdata[0]}"
            "<br>Verloren: %{customdata[1]}<extra></extra>"
        )
    )
    if not winrate_fig.data:
        winrate_fig = empty_fig

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


if __name__ == "__main__":
    app.run(debug=False)
