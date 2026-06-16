"""
api/routes.py
=============
All Flask (server-side) routes: REST API for match CRUD, config, export,
SSE stream, health check, input page, bye (session close).

Call ``register(server)`` from the app entry-point to mount every route
onto the Flask ``server`` instance.
"""

from __future__ import annotations

import json
import os
import threading
import time
from io import BytesIO

from flask import request, Response, send_file

import config
import mappings
import firebase_service
from data import loader, state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _verify_pin():
    """Check PIN from header. Returns error tuple or ``None`` if OK."""
    pin = request.headers.get("X-Input-Pin", "")
    if pin != config.INPUT_PIN:
        return (
            json.dumps({"ok": False, "error": "unauthorized"}),
            401,
            {"Content-Type": "application/json"},
        )
    return None


def _json(data, status: int = 200):
    return (json.dumps(data, default=str), status, {"Content-Type": "application/json"})


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def register(server):
    """Mount all API / utility routes onto *server*."""

    # --- Health / misc -------------------------------------------------------

    @server.route("/health")
    def health_check():
        return _json({"ok": True})

    @server.route("/bye", methods=["POST"])
    def bye():
        try:
            payload = request.get_json(silent=True) or {}
            sid = payload.get("session_id")
            if sid:
                state.delete_session(sid)
            return _json({"ok": True})
        except Exception as e:
            return _json({"ok": False, "error": str(e)}, 500)

    # --- Input page ----------------------------------------------------------

    @server.route("/input")
    def input_page():
        path = os.path.join(
            os.path.dirname(__file__), os.pardir, "assets", "input.html"
        )
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            return (
                content,
                200,
                {
                    "Content-Type": "text/html; charset=utf-8",
                    "Cache-Control": "no-store, no-cache, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        except FileNotFoundError:
            return ("Input page not found", 404)

    # --- Mappings (public, no PIN) -------------------------------------------

    @server.route("/api/mappings")
    def api_mappings():
        data = mappings.to_json_mappings()
        data["players"] = config.PLAYERS
        data["currentSeason"] = (
            firebase_service.get_current_season()
            if firebase_service.is_available()
            else config.DEFAULT_SEASON
        )
        data["nextMatchId"] = loader.get_next_match_id()
        data["firebaseAvailable"] = firebase_service.is_available()
        return _json(data)

    # --- Match CRUD ----------------------------------------------------------

    @server.route("/api/matches", methods=["GET"])
    def api_get_matches():
        err = _verify_pin()
        if err:
            return err
        limit = int(request.args.get("limit", 30))
        matches = loader.jsonl_read()
        matches.sort(key=lambda m: int(m.get("match_id") or 0), reverse=True)
        return _json(matches[:limit])

    @server.route("/api/matches", methods=["POST"])
    def api_create_match():
        err = _verify_pin()
        if err:
            return err
        data = request.get_json(silent=True)
        if not data:
            return _json({"ok": False, "error": "no data"}, 400)

        loader.jsonl_append(data)
        loader.patch_with_match(data)
        threading.Thread(
            target=firebase_service.save_match, args=(data,), daemon=True
        ).start()
        return _json({"ok": True, "doc_id": str(data.get("match_id", ""))}, 201)

    @server.route("/api/matches/<int:match_id>", methods=["PUT"])
    def api_update_match(match_id):
        err = _verify_pin()
        if err:
            return err
        data = request.get_json(silent=True)
        if not data:
            return _json({"ok": False, "error": "no data"}, 400)

        data["match_id"] = match_id
        loader.jsonl_upsert(data)
        loader.patch_with_match(data)
        threading.Thread(
            target=firebase_service.update_match, args=(match_id, data), daemon=True
        ).start()
        return _json({"ok": True})

    @server.route("/api/matches/<int:match_id>", methods=["DELETE"])
    def api_delete_match(match_id):
        err = _verify_pin()
        if err:
            return err
        loader.jsonl_delete(match_id)
        loader.remove_row(match_id)
        threading.Thread(
            target=firebase_service.delete_match, args=(match_id,), daemon=True
        ).start()
        return _json({"ok": True})

    # --- Config --------------------------------------------------------------

    @server.route("/api/config", methods=["GET"])
    def api_get_config():
        err = _verify_pin()
        if err:
            return err
        cfg = firebase_service.get_config() if firebase_service.is_available() else {}
        return _json(cfg)

    @server.route("/api/config", methods=["POST"])
    def api_set_config():
        err = _verify_pin()
        if err:
            return err
        data = request.get_json(silent=True) or {}
        ok = firebase_service.set_config(data)
        return _json({"ok": ok}, 200 if ok else 500)

    # --- Export --------------------------------------------------------------

    @server.route("/api/export-excel")
    def api_export_excel():
        err = _verify_pin()
        if err:
            return err
        merged = loader.build_merged_df()
        buf = BytesIO()
        merged.to_excel(buf, index=False, engine="openpyxl")
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name="ow_stats_export.xlsx",
        )

    # --- Change-token / SSE --------------------------------------------------

    @server.route("/api/change-token")
    def api_change_token():
        token = (
            firebase_service.get_last_change_token()
            if firebase_service.is_available()
            else "0"
        )
        return _json({"token": token})

    @server.route("/api/stream")
    def api_sse_stream():
        def generate():
            last_token = ""
            while True:
                token = (
                    firebase_service.get_last_change_token()
                    if firebase_service.is_available()
                    else "0"
                )
                if token != last_token:
                    last_token = token
                    yield f"data: {json.dumps({'token': token})}\n\n"
                time.sleep(2)

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # --- Error handler -------------------------------------------------------

    @server.errorhandler(IndexError)
    def _handle_index_error(e):
        try:
            p = request.path or ""
        except Exception:
            p = ""
        if p.endswith("/_dash-update-component"):
            return ("", 204)
        return ("", 500)
