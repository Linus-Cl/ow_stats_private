"""
api/routes.py
=============
Flask/Dash Server-Routes: REST API für das Input-Frontend.

Hierher gehört (aus app.py):
  - _verify_pin()                  [app.py ~3391]
  - _get_next_match_id_combined()  [app.py ~3403]
  - api_mappings()                 [app.py ~3423]   → GET /api/mappings
  - api_get_matches()              [app.py ~3438]   → GET /api/matches
  - api_create_match()             [app.py ~3456]   → POST /api/matches
  - api_update_match()             [app.py ~3486]   → PUT /api/matches/<id>
  - api_delete_match()             [app.py ~3513]   → DELETE /api/matches/<id>
  - api_get_config()               [app.py ~3531]   → GET /api/config
  - api_set_config()               [app.py ~3541]   → POST /api/config
  - api_export_excel()             [app.py ~3556]   → GET /api/export
  - api_change_token()             [app.py ~3575]   → POST /api/change-token
  - api_sse_stream()               [app.py ~3587]   → GET /api/stream (SSE)
  - input_page()                   [app.py ~3747]   → GET /input

  Außerdem:
  - _self_ping_loop()              [app.py ~1701]   → Background-Thread
    (alternativ: in app.py behalten beim Server-Start)
  - _handle_index_error()          [app.py ~116]
  - bye()                          [app.py ~130]    → GET /bye

Wichtig:
  - server = app.server  (Flask-Instanz, aus app.py importieren)
  - `from data.loader import _jsonl_read, _jsonl_write, ...` etc.
  - PIN-Validierung: immer über _verify_pin() — NIEMALS PIN im Code hardcoden
"""

# TODO: Flask-Routes aus app.py ~3384–3747 hierher verschieben
# Beispiel:
#
# from app import server   ← oder server separat definieren
# from data.loader import _jsonl_read, _jsonl_upsert, _jsonl_delete
#
# @server.route("/api/matches", methods=["GET"])
# def api_get_matches():
#     ...
