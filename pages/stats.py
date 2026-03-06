"""
pages/stats.py
==============
Statistiken Tab — Charts, Graphs, Vergleiche.

Hierher gehört (aus app.py):
  Layout-Teile:
  - Der "Stats"-Tab-Inhalt (dbc.Card mit id="stats-container")  [app.py ~2479]
  - Hero-Selector Dropdowns (detailed hero selectors)
  - Rollen-Zuweisung UI  [app.py ~2228–2252]
  - Comparison-Switches

  Callbacks:
  - update_all_graphs()              [app.py ~5825]  ← größter Stats-Callback
  - build_detailed_hero_selectors()  [app.py ~4594]
  - compute_role_stats()             [app.py ~5149]
  - show_role_assignment_history()   [app.py ~5384]
  - update_role_history_count()      [app.py ~5621]
  - toggle_role_history_controls()   [app.py ~5695]
  - populate_role_assignment_options()[app.py ~4789]
  - enforce_role_limits()            [app.py ~4846]
  - generate_comparison_switches()   [app.py ~4873]
  - reset_compare_switches()         [app.py ~4897]
  - toggle_view_type_visibility()    [app.py ~4901]
  - toggle_slider()                  [app.py ~4910]
  - update_filter_options()          [app.py ~4754]
  - localize_role_assign()           [app.py ~4000]

  Helper-Funktionen:
  - create_stat_card()               [app.py ~4171]
  - get_map_image_url()              [app.py ~4067]
  - get_hero_image_url()             [app.py ~4099]
  - create_comparison_fig()          [app.py ~6234]  (inner fn → extrahieren)
  - style_fig()                      [app.py ~5852]  (inner fn → extrahieren)

Wichtig:
  - Plotly Figures: `import plotly.graph_objects as go`
  - `tr(key, lang)` importieren aus utils/i18n.py
"""

import dash
from dash import html, dcc, callback, Input, Output, State
import plotly.graph_objects as go

dash.register_page(__name__, path="/stats", name="Statistiken")


def layout():
    # TODO: Tab-Inhalt aus app.py ~2479 hierher
    return html.Div("TODO: Stats Layout")


# TODO: Callbacks aus app.py ~5825, ~4594, ~5149 etc. hierher
