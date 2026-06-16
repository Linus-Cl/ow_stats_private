"""
pages/patchnotes.py
===================
Renders /patchnotes from PATCHNOTES.md.

Each entry in the markdown has the form:

    ### 2026-03-08 — some title
    - Notes: English description here.
    - Hinweise (DE): Deutsche Beschreibung hier.

Language is detected from ?lang= or Accept-Language.
"""

from __future__ import annotations
import html as html_std
import os

from flask import request


def _detect_lang() -> str:
    try:
        q = request.args.get("lang")
        if q and q.lower() in ("de", "en"):
            return q.lower()
        al = request.headers.get("Accept-Language", "").lower()
        if al.startswith("de"):
            return "de"
        if "en" in al:
            return "en"
    except Exception:
        pass
    return "de"


def _parse(md: str) -> list[dict]:
    entries: list[dict] = []
    current: dict | None = None
    for line in md.splitlines():
        if line.startswith("### "):
            if current:
                entries.append(current)
            parts = line[4:].split(" — ", 1)
            current = {
                "date": parts[0].strip(),
                "title": parts[1].strip() if len(parts) > 1 else "",
                "en": "",
                "de": "",
            }
            continue
        if current is None:
            continue
        stripped = line.strip()
        lo = stripped.lower()
        if lo.startswith("- notes:"):
            current["en"] = stripped.split(":", 1)[1].strip()
        elif lo.startswith("- hinweise"):
            current["de"] = stripped.split(":", 1)[1].strip()
    if current:
        entries.append(current)
    return entries


def register(server):
    @server.route("/patchnotes")
    def patchnotes_page():
        lang = _detect_lang()
        md_path = "PATCHNOTES.md"
        if not os.path.exists(md_path):
            body = "<p>Keine Patchnotes gefunden.</p>" if lang == "de" else "<p>No patch notes found.</p>"
            return _page(lang, body)
        with open(md_path, "r", encoding="utf-8") as f:
            md = f.read()
        entries = _parse(md)
        cards = []
        for e in entries:
            text = (e["de"] if lang == "de" else e["en"]).strip()
            if not text:
                continue
            date = e["date"]
            try:
                y, m, d = date.split("-")
                nice = f"{d}.{m}.{y}" if lang == "de" else date
            except Exception:
                nice = date
            cards.append(
                "<div class='c'>"
                f"<h2>{html_std.escape(e['title'])}</h2>"
                f"<div class='meta'>{html_std.escape(nice)}</div>"
                f"<p>{html_std.escape(text)}</p>"
                "</div>"
            )
        body = "\n".join(cards) if cards else (
            "<p>Keine Einträge.</p>" if lang == "de" else "<p>No entries.</p>"
        )
        return _page(lang, body)


def _page(lang: str, body: str) -> tuple:
    heading = "Aktualisierungen" if lang == "de" else "Updates"
    out = (
        "<!doctype html>\n"
        f'<html lang="{lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Patchnotes</title>\n"
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<style>\n"
        "body{font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;"
        "max-width:820px;margin:32px auto;padding:0 16px;color:#1f2937;background:#f9fafb}\n"
        "h1{font-size:22px;margin:0 0 18px}\n"
        ".c{border:1px solid #e5e7eb;border-radius:8px;padding:12px 16px;margin:10px 0;background:#fff}\n"
        "h2{font-size:15px;font-weight:600;margin:0 0 2px}\n"
        ".meta{color:#6b7280;font-size:12px;margin-bottom:6px}\n"
        "p{margin:0;font-size:14px;line-height:1.6;color:#374151}\n"
        "</style>\n"
        "</head>\n"
        "<body>\n"
        f"<h1>{heading}</h1>\n"
        f"{body}\n"
        "</body>\n"
        "</html>"
    )
    return (out, 200, {"Content-Type": "text/html; charset=utf-8"})
