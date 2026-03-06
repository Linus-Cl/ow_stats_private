"""
pages/patchnotes.py
===================
Patchnotes Tab — Git-Log basierte Änderungshistorie.

Hierher gehört (aus app.py):
  Layout:
  - patchnotes_page()              [app.py ~3319]
  - Der Patchnotes-Tab-Inhalt      [app.py ~2411–2478]

  Helper-Funktionen:
  - _is_relevant_file()            [app.py ~2541]
  - _get_patchnotes_commits()      [app.py ~2568]
  - _md_to_html()                  [app.py ~2614]
  - _load_patchnotes_md()          [app.py ~2658]
  - _parse_patchnotes_entries()    [app.py ~2674]
  - _beautify_subject()            [app.py ~2727]
  - _detect_lang()                 [app.py ~2940]
  - _describe_change()             [app.py ~2959]

  Callbacks:
  - localize_patchnotes_link()     [app.py ~4024]

Wichtig:
  - Kein dcc.Store nötig für Patchnotes (statischer Content)
  - PATCHNOTES.md wird direkt eingelesen
"""

import dash
from dash import html, dcc, callback, Input, Output

dash.register_page(__name__, path="/patchnotes", name="Patchnotes")


def layout():
    # TODO: patchnotes_page() aus app.py ~3319 hierher
    return html.Div("TODO: Patchnotes Layout")


# TODO: Callback aus app.py ~4024 hierher
