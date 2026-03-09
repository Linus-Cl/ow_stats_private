"""
app.py
======
Slim orchestrator: creates the Dash application, defines the shared layout,
registers cross-cutting callbacks (theme, language, filter sidebar, online
counter), and delegates to page modules for tab-specific logic.
"""

from __future__ import annotations

import os
import threading
import time
import uuid

import dash_bootstrap_components as dbc
import pandas as pd
from dash import ALL, Dash, Input, Output, State, ctx, dcc, html, no_update
from dash.exceptions import PreventUpdate

import config
from data import loader, state
from utils.assets import DARK_LOGO_INVERT, DARK_LOGO_SRC, LIGHT_LOGO_SRC
from utils.formatting import format_season_display, season_sort_key
from utils.i18n import tr

# ── Page modules (register_callbacks is called at the bottom) ──────────────
from api import routes as api_routes
from pages import daily, history, patchnotes, roles, stats

# ---------------------------------------------------------------------------
# App & server
# ---------------------------------------------------------------------------
app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    suppress_callback_exceptions=True,
)
server = app.server

try:
    server.config["SEND_FILE_MAX_AGE_DEFAULT"] = config.STATIC_CACHE_TTL
except Exception:
    pass

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
app.layout = html.Div(
    [
        dcc.Location(id="url"),
        dcc.Store(id="history-display-count-store", data={"count": 10}),
        dcc.Store(id="role-history-count-store", data={"count": 10}),
        dcc.Store(id="theme-store", data={"dark": False}, storage_type="local"),
        dcc.Store(id="lang-store", data={"lang": "en"}, storage_type="local"),
        dcc.Store(id="client-id", storage_type="session"),
        dcc.Store(id="server-update-token", storage_type="memory"),
        dcc.Store(id="hero-collapse-states", data={}, storage_type="session"),
        html.Div(id="theme-body-sync", style={"display": "none"}),
        html.Div(id="dummy-scroll-ack", style={"display": "none"}),
        html.Div(id="heartbeat-dummy", style={"display": "none"}),
        # Effectively-disabled legacy interval (kept so callbacks don't error)
        dcc.Interval(id="auto-update-tick", interval=3600_000, max_intervals=0),
        dcc.Interval(
            id="server-update-poll",
            interval=config.POLL_UPDATE_SECONDS * 1000,
            n_intervals=0,
        ),
        dcc.Interval(id="client-init", interval=1000, n_intervals=0, max_intervals=1),
        dcc.Interval(id="heartbeat", interval=60_000, n_intervals=0),
        dcc.Interval(id="active-count-refresh", interval=60_000, n_intervals=0),
        dbc.Container(
            [
                # ── Header row ─────────────────────────────────────────────
                dbc.Row(
                    [
                        dbc.Col(
                            html.Div(
                                [
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
                                "⊕ Match eingeben",
                                id="update-data-button",
                                color="success",
                                className="mt-4",
                                href="/input",
                                external_link=True,
                            ),
                            width="auto",
                        ),
                        dbc.Col(
                            dbc.Switch(
                                id="theme-toggle", value=False, className="mt-4"
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
                                                    src="https://flagcdn.com/gb.svg",
                                                    title="English",
                                                    alt="English",
                                                    draggable=False,
                                                    className="lang-flag",
                                                    style={
                                                        "height": "20px",
                                                        "width": "auto",
                                                        "display": "block",
                                                    },
                                                ),
                                                id="btn-lang-en",
                                                color="secondary",
                                                outline=True,
                                                size="sm",
                                                className="me-1 lang-btn",
                                            ),
                                            dbc.Button(
                                                html.Img(
                                                    src="https://flagcdn.com/de.svg",
                                                    title="Deutsch",
                                                    alt="Deutsch",
                                                    draggable=False,
                                                    className="lang-flag",
                                                    style={
                                                        "height": "20px",
                                                        "width": "auto",
                                                        "display": "block",
                                                    },
                                                ),
                                                id="btn-lang-de",
                                                color="secondary",
                                                outline=True,
                                                size="sm",
                                                className="lang-btn",
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
                # ── Sidebar + Tabs ─────────────────────────────────────────
                dbc.Row(
                    [
                        # Sidebar: filters
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
                                                        for p in config.PLAYERS
                                                    ],
                                                    value=config.PLAYERS[0],
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
                                ),
                            ],
                            width=3,
                        ),
                        # Main content: tabs
                        dbc.Col(
                            [
                                dbc.Tabs(
                                    [
                                        # Daily Report
                                        dbc.Tab(
                                            id="tab-comp-daily",
                                            label="Daily Report",
                                            tab_id="tab-daily",
                                            children=[
                                                html.Div(
                                                    [
                                                        html.Div(
                                                            dcc.DatePickerSingle(
                                                                id="daily-date",
                                                                display_format="YYYY-MM-DD",
                                                                max_date_allowed=pd.Timestamp.now()
                                                                .normalize()
                                                                .date(),
                                                                initial_visible_month=pd.Timestamp.now()
                                                                .normalize()
                                                                .date(),
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
                                                        html.Div(
                                                            id="daily-summary",
                                                            className="mb-3",
                                                        ),
                                                    ],
                                                    style={"position": "relative"},
                                                ),
                                                html.Div(id="daily-report-container"),
                                            ],
                                        ),
                                        # Map & Mode
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
                                        # Role Assignment
                                        dbc.Tab(
                                            id="tab-comp-role-assign",
                                            label="Rollen-Zuordnung",
                                            tab_id="tab-role-assign",
                                            children=[
                                                html.P(
                                                    id="role-assign-help", children=""
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
                                        # Hero Stats
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
                                        # Role Stats
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
                                        # Heatmap
                                        dbc.Tab(
                                            dcc.Graph(id="performance-heatmap"),
                                            id="tab-comp-heatmap",
                                            label="Performance Heatmap",
                                            tab_id="tab-heatmap",
                                        ),
                                        # Winrate Trend
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
                                        # Match History
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
                                                                                        "label": p,
                                                                                        "value": p,
                                                                                    }
                                                                                    for p in config.PLAYERS
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
                                                            ),
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
                                    active_tab="tab-daily",
                                ),
                            ],
                            width=9,
                        ),
                    ]
                ),
                # ── Stats cards row ────────────────────────────────────────
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
                                ),
                            ],
                            width=12,
                        ),
                    ],
                    className="mt-4",
                ),
                html.Div(id="dummy-output", style={"display": "none"}),
                # Footer
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
                        ),
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


# ---------------------------------------------------------------------------
# Clientside callbacks
# ---------------------------------------------------------------------------
app.clientside_callback(
    """
    function(hash) {
        if (!hash || typeof hash !== 'string' || hash.length < 2) { return window.dash_clientside.no_update; }
        const targetId = hash.substring(1);
        let attempts = 0;
        function tryScroll(){
            const el = document.getElementById(targetId);
            if (el){ el.scrollIntoView({behavior: 'smooth', block: 'center'}); return; }
            attempts += 1;
            if (attempts < 20){ setTimeout(tryScroll, 50); }
        }
        setTimeout(tryScroll, 0);
        return "ok";
    }
    """,
    Output("dummy-scroll-ack", "children"),
    Input("url", "hash"),
)

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

# ---------------------------------------------------------------------------
# Shared callbacks — theme
# ---------------------------------------------------------------------------


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
    return "dark" if (data or {}).get("dark") else ""


@app.callback(
    Output("theme-toggle", "value"),
    Input("theme-store", "data"),
    prevent_initial_call=False,
)
def sync_toggle_from_store(data):
    return bool((data or {}).get("dark", False))


# ---------------------------------------------------------------------------
# Shared callbacks — language
# ---------------------------------------------------------------------------


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
    return (
        ("⊕ Match eingeben", "Dark Mode")
        if lang == "de"
        else ("⊕ Add Match", "Dark Mode")
    )


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
    _hero_replace = "Hero" if lang == "en" else "Held"
    _role_replace = "Role" if lang == "en" else "Rolle"
    hero_opts = [
        {
            "label": tr("map_winrate", lang).replace("Map", _hero_replace),
            "value": "winrate",
        },
        {
            "label": tr("map_plays", lang).replace("Map", _hero_replace),
            "value": "plays",
        },
    ]
    role_opts = [
        {
            "label": tr("map_winrate", lang).replace("Map", _role_replace),
            "value": "winrate",
        },
        {
            "label": tr("map_plays", lang).replace("Map", _role_replace),
            "value": "plays",
        },
    ]
    load_amounts = [10, 25, 50]
    load_opts = [
        {"label": tr("load_n_more", lang).format(n=n), "value": n} for n in load_amounts
    ]
    hist_player_opts = [{"label": tr("all_players", lang), "value": "ALL"}] + [
        {"label": p, "value": p} for p in config.PLAYERS
    ]
    return (
        map_opts,
        "winrate",
        tr("detailed", lang),
        hero_opts,
        "winrate",
        role_opts,
        "winrate",
        tr("choose_maps", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        tr("choose_players", lang),
        load_opts,
        load_amounts[0],
        tr("load_more", lang),
        hist_player_opts,
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
        "",
        tr("map_filter_opt", lang),
        tr("bench", lang),
        tr("tank_label", lang),
        tr("damage_label", lang),
        tr("support_label", lang),
        tr("detailed_mode", lang),
    )


@app.callback(
    Output("patchnotes-link", "children"),
    Output("patchnotes-link", "href"),
    Input("lang-store", "data"),
)
def localize_patchnotes_link(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    return ("Patchnotes" if lang == "de" else "Patch notes"), f"/patchnotes?lang={lang}"


@app.callback(
    Output("daily-date", "display_format"),
    Output("daily-date", "placeholder"),
    Input("lang-store", "data"),
)
def localize_daily_date(lang_data):
    lang = (lang_data or {}).get("lang", "en")
    fmt = "DD.MM.YYYY" if lang == "de" else "YYYY-MM-DD"
    ph = (
        tr("date_placeholder", lang)
        if tr("date_placeholder", lang) != "date_placeholder"
        else ("Datum" if lang == "de" else "Date")
    )
    return fmt, ph


@app.callback(
    Output("daily-date", "max_date_allowed"),
    Output("daily-date", "initial_visible_month"),
    Input("lang-store", "data"),
)
def _sync_datepicker_bounds(_lang_data):
    today = pd.Timestamp.now().normalize().date()
    return today, today


# ---------------------------------------------------------------------------
# Shared callbacks — filter sidebar
# ---------------------------------------------------------------------------


@app.callback(
    Output("season-dropdown", "options"),
    Output("month-dropdown", "options"),
    Output("year-dropdown", "options"),
    Input("dummy-output", "children"),
    Input("server-update-token", "data"),
)
def update_filter_options(_, _token):
    loader.reload()
    df = loader.get_df()
    if df.empty:
        return [], [], []
    seasons = list(df["Season"].dropna().unique()) if "Season" in df.columns else []
    seasons.sort(key=season_sort_key, reverse=True)
    season_options = [{"label": format_season_display(s), "value": s} for s in seasons]
    month_options = (
        [{"label": m, "value": m} for m in sorted(df["Monat"].dropna().unique())]
        if "Monat" in df.columns
        else []
    )
    year_options = (
        [
            {"label": str(int(y)), "value": int(y)}
            for y in sorted(df["Jahr"].dropna().unique(), reverse=True)
        ]
        if "Jahr" in df.columns
        else []
    )
    return season_options, month_options, year_options


@app.callback(
    Output("compare-switches-container", "children"),
    Input("player-dropdown", "value"),
    Input("lang-store", "data"),
)
def generate_comparison_switches(selected_player, lang_data):
    other = [p for p in config.PLAYERS if p != selected_player]
    if not other:
        return None
    lang = (lang_data or {}).get("lang", "en")
    switches = [html.Label(tr("compare_with", lang), className="fw-bold")]
    for p in other:
        switches.append(
            dbc.Switch(
                id={"type": "compare-switch", "player": p},
                label=p,
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
def reset_compare_switches(_selected_player, switch_values):
    return [False] * len(switch_values)


# ---------------------------------------------------------------------------
# Shared callbacks — data token polling & legacy update_data
# ---------------------------------------------------------------------------


@app.callback(
    Output("dummy-output", "children"),
    Input("auto-update-tick", "n_intervals"),
    prevent_initial_call=True,
)
def update_data(_n_intervals):
    return no_update


@app.callback(
    Output("server-update-token", "data"),
    Input("server-update-poll", "n_intervals"),
    State("server-update-token", "data"),
    prevent_initial_call=False,
)
def poll_server_update_token(_n, current_token):
    token = state.get_app_state("data_token") or ""
    if token != (current_token or ""):
        try:
            loader.reload()
        except Exception as exc:
            print(f"[Poll] reload warning: {exc}")
        return token
    if not current_token:
        return token
    return no_update


# ---------------------------------------------------------------------------
# Shared callbacks — online counter
# ---------------------------------------------------------------------------


@app.callback(
    Output("client-id", "data"),
    Input("client-init", "n_intervals"),
    State("client-id", "data"),
    prevent_initial_call=False,
)
def _init_client_id(_, existing):
    if existing:
        state.upsert_heartbeat(existing)
        return existing
    try:
        sid = str(uuid.uuid4())
    except Exception:
        sid = str(time.time_ns())
    state.upsert_heartbeat(sid)
    return sid


@app.callback(
    Output("heartbeat-dummy", "children"),
    Input("heartbeat", "n_intervals"),
    State("client-id", "data"),
)
def _heartbeat(_n, session_id):
    state.upsert_heartbeat(session_id)
    return str(int(time.time()))


@app.callback(
    Output("online-counter", "children"),
    Input("active-count-refresh", "n_intervals"),
    Input("lang-store", "data"),
    Input("client-id", "data"),
)
def _update_online_counter(_n, lang_data, _sid):
    lang = (lang_data or {}).get("lang", "en")
    return f"{tr('online_now', lang)}: {state.count_active()}"


# ---------------------------------------------------------------------------
# Register page-module callbacks & Flask routes
# ---------------------------------------------------------------------------
api_routes.register(server)
patchnotes.register(server)
stats.register_callbacks(app)
history.register_callbacks(app)
roles.register_callbacks(app)
daily.register_callbacks(app)


# ---------------------------------------------------------------------------
# Self-ping (keeps Render Free Tier alive)
# ---------------------------------------------------------------------------


def _self_ping_loop():
    import urllib.request

    url = os.environ.get("APP_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    health_url = url.rstrip("/") + "/health"
    time.sleep(30)
    while True:
        try:
            urllib.request.urlopen(health_url, timeout=10)
        except Exception:
            pass
        time.sleep(config.SELF_PING_INTERVAL)


try:
    threading.Thread(target=_self_ping_loop, daemon=True).start()
except Exception:
    pass


# ---------------------------------------------------------------------------
# Startup: load data
# ---------------------------------------------------------------------------
try:
    loader.reload()
    src = (
        "local JSONL"
        if os.path.exists(config.LOCAL_DATA_FILE)
        else "Firestore bootstrap"
    )
    print(f"[Startup] Data source: {src}, {len(loader.get_df())} rows loaded")
except Exception as exc:
    print(f"[Startup] Data reload warning: {exc}")


if __name__ == "__main__":
    app.run(debug=False)
