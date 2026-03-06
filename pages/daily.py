"""
pages/daily.py
==============
Daily Report Tab — Layout + Callbacks.

Hierher gehört (aus app.py):
  Layout-Teile:
  - Der "Daily Report"-Tab-Inhalt (dcc.Tab mit id="tab-daily")
    [app.py ~2006–2090]
  - Banner-Bereich mit DatePicker + Score-Anzeige
  - Map-Timeline (timeline_component)  [app.py ~1386]
  - Player-Lineup Grid (Rollen-Karten)  [app.py ~419–1095]
  - Hero Spotlights (Most Played, Flex, OTP etc.)  [app.py ~800–1095]

  Callbacks:
  - render_daily_report()          [app.py ~178]  ← größter Callback
  - on_view_last_active_day()      [app.py ~4711]
  - on_timeline_tile_click()       [app.py ~5031]
  - localize_daily_date()          [app.py ~4037]
  - _sync_datepicker_bounds()      [app.py ~4054]

  Helper-Funktionen (inner functions → hier extrahieren):
  - _is_valid_hero()               [app.py ~273]
  - _extract_time_str()            [app.py ~280]
  - _compose_dt()                  [app.py ~319]
  - _fmt_hhmm_from_val()           [app.py ~1096]
  - _fmt_hhmm_from_dict()          [app.py ~1104]
  - _fmt_duration_from_dict()      [app.py ~1148]

Wichtig:
  - Alle Component-IDs müssen den Prefix "daily-" behalten (z.B. "daily-report-container")
  - `tr(key, lang)` importieren aus utils/i18n.py
  - DataFrame beziehen via `from data.loader import get_df`
"""

import dash
from dash import html, dcc, callback, Input, Output, State

dash.register_page(__name__, path="/", name="Daily Report")


def layout():
    # TODO: Tab-Inhalt aus app.py ~2006–2090 hierher
    return html.Div("TODO: Daily Report Layout")


# TODO: Callbacks aus app.py ~178 und ~4711 hierher
