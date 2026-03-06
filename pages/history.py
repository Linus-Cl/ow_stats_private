"""
pages/history.py
================
Match History Tab — Layout + Callbacks.

Hierher gehört (aus app.py):
  Layout-Teile:
  - Der "Match History"-Tab-Inhalt  [app.py ~2034–2107]
  - Filter-Controls (Spieler, Season, Monat, Hero, Gamemode)
  - History-Liste (generate_history_layout_simple)  [app.py ~4285]

  Callbacks:
  - update_history_display()             [app.py ~4945]
  - update_match_history_hero_options()  [app.py ~5077]
  - on_timeline_tile_click()             gemeinsam mit daily (oder hier nochmal)

  Helper-Funktionen:
  - generate_history_layout_simple()     [app.py ~4285]
  - calculate_winrate()                  [app.py ~4231]  ← ggf. nach data/loader.py

Wichtig:
  - Filter-IDs: "history-player-filter", "history-season-filter" etc.
  - `tr(key, lang)` importieren aus utils/i18n.py
"""

import dash
from dash import html, dcc, callback, Input, Output, State

dash.register_page(__name__, path="/history", name="Match History")


def layout():
    # TODO: Tab-Inhalt aus app.py ~2034–2107 hierher
    return html.Div("TODO: History Layout")


# TODO: Callbacks aus app.py ~4945 und ~5077 hierher
