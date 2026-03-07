"""
pages/patchnotes.py
===================
Standalone Flask route that renders a human-readable patchnotes page.
Reads ``PATCHNOTES.md`` (or the language-specific variant), parses entries,
and renders them as simple HTML cards with translated, user-friendly
descriptions.

Usage from the app entry-point::

    from pages import patchnotes
    patchnotes.register(server)
"""

from __future__ import annotations

import html as html_std
import os
import re
import subprocess

from flask import request


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------


def _detect_lang() -> str:
    """Detect language from ``?lang=`` query or ``Accept-Language`` header. Defaults to ``'de'``."""
    try:
        q = request.args.get("lang")
        if q and q.lower() in ("de", "en"):
            return q.lower()
        al = request.headers.get("Accept-Language", "").lower()
        if "de" in al and "en" not in al.split(",")[0]:
            return "de"
        if "en" in al:
            return "en"
    except Exception:
        pass
    return "de"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_relevant_file(path: str) -> bool:
    if not path:
        return False
    p = path.strip()
    if p in ("app.py", "constants.py", "config.py", "requirements.txt"):
        return True
    if (
        p.startswith("assets/")
        or p.startswith("pages/")
        or p.startswith("utils/")
        or p.startswith("api/")
    ):
        return True
    if p.endswith((".md", ".db")) or p.startswith((".github/", "scripts/")):
        return False
    if p in (".gitignore", "PATCHNOTES.md"):
        return False
    return False


def _load_patchnotes_md(lang: str) -> str | None:
    candidates = (
        ["PATCHNOTES.de.md", "PATCHNOTES.md"]
        if lang == "de"
        else ["PATCHNOTES.en.md", "PATCHNOTES.md"]
    )
    for name in candidates:
        if os.path.exists(name):
            try:
                with open(name, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                continue
    return None


def _parse_patchnotes_entries(md_text: str) -> list[dict]:
    entries: list[dict] = []
    lines = md_text.splitlines()
    current: dict | None = None
    for line in lines:
        if line.startswith("### "):
            if current:
                entries.append(current)
            header = line[4:].strip()
            date_part = header.split(" — ")[0].strip()
            date_norm = date_part.split(" ")[0]
            subject = header.split(" — ")[-1].strip()
            current = {
                "date": date_norm,
                "subject": subject,
                "files": [],
                "notes": "",
                "notes_en": "",
                "notes_de": "",
            }
            continue
        if current is not None:
            m = re.match(r"\s*-\s+([AMDZR])\s+(.+)$", line)
            if m:
                current["files"].append(m.group(2).strip())
            elif line.strip().lower().startswith("- notes:"):
                note = line.split(":", 1)[1].strip() if ":" in line else ""
                current["notes"] = note
                current["notes_en"] = note
            elif line.strip().lower().startswith("- hinweise"):
                note = line.split(":", 1)[1].strip() if ":" in line else ""
                current["notes_de"] = note
    if current:
        entries.append(current)
    return entries


# ---------------------------------------------------------------------------
# Subject beautification  &  change description  (i18n mapping)
# ---------------------------------------------------------------------------

# fmt: off
_SUBJECT_MAP: list[tuple[str, dict[str, str]]] = [
    ("flag icons",                    {"de": "Sprach-Flags in hoher Qualität",              "en": "High-quality language flags"}),
    ("daily banner tie-break",        {"de": "Banner: Gleichstand per Winrate auflösen",    "en": "Banner: tie-break by winrate"}),
    ("per-role winrate badges",       {"de": "Rollenspezifische Winrate-Badges",            "en": "Per-role winrate badges"}),
    ("daily default tab",             {"de": "Tagesreport als Startansicht",                "en": "Daily Report as default tab"}),
    ("map image fallback",            {"de": "Robuster Kartenbild-Fallback",                "en": "Robust map image fallback"}),
    ("sync button",                   {"de": "Sync-Button hinzugefügt",                    "en": "Added sync button"}),
    ("update button",                 {"de": "Sync-Button hinzugefügt",                    "en": "Added sync button"}),
    ("refresh button",                {"de": "Sync-Button hinzugefügt",                    "en": "Added sync button"}),
    ("reload button",                 {"de": "Sync-Button hinzugefügt",                    "en": "Added sync button"}),
    ("filter to history",             {"de": "Filter für Historie",                         "en": "History filter"}),
    ("history filter",                {"de": "Filter für Historie",                         "en": "History filter"}),
    ("filter history",                {"de": "Filter für Historie",                         "en": "History filter"}),
    ("added filter to history",       {"de": "Filter für Historie",                         "en": "History filter"}),
    ("attack/def to history",         {"de": "Angriff/Verteidigung in der Historie",        "en": "Attack/Defense in history"}),
    ("attack-def to history",         {"de": "Angriff/Verteidigung in der Historie",        "en": "Attack/Defense in history"}),
    ("attack def to history",         {"de": "Angriff/Verteidigung in der Historie",        "en": "Attack/Defense in history"}),
    ("atk/def to history",            {"de": "Atk/Def in der Historie",                    "en": "Atk/Def in history"}),
    ("patchnotes",                    {"de": "Patchnotes-Seite",                            "en": "Patch notes page"}),
    ("patch notes",                   {"de": "Patchnotes-Seite",                            "en": "Patch notes page"}),
    ("footer link",                   {"de": "Link im Seitenfuß",                          "en": "Footer link"}),
    ("webhook",                       {"de": "Sicherer Webhook für Datenupdate",            "en": "Secure webhook for data update"}),
    ("broadcast",                     {"de": "Updates in allen offenen Sitzungen",          "en": "Updates across all open sessions"}),
    ("update token",                  {"de": "Updates in allen offenen Sitzungen",          "en": "Updates across all open sessions"}),
    ("server-update-token",           {"de": "Updates in allen offenen Sitzungen",          "en": "Updates across all open sessions"}),
    ("data_token",                    {"de": "Updates in allen offenen Sitzungen",          "en": "Updates across all open sessions"}),
    ("map thumbnail",                 {"de": "Breitere Karten-Vorschaubilder",              "en": "Wider map thumbnails"}),
    ("map width",                     {"de": "Breitere Karten-Vorschaubilder",              "en": "Wider map thumbnails"}),
    ("disabled slider",               {"de": "Dezenter Stil für deaktivierte Regler",       "en": "Subtler style for disabled sliders"}),
    ("branding",                      {"de": "Branding/Logo aktualisiert",                  "en": "Branding/logo updated"}),
    ("logo",                          {"de": "Branding/Logo aktualisiert",                  "en": "Branding/logo updated"}),
    ("added live viewer counter",     {"de": "Live-Zähler für geöffnete Seiten",            "en": "Live viewer counter"}),
    ("language windows fix",          {"de": "Sprachauswahl – Windows Fix",                 "en": "Language selection – Windows fix"}),
    ("fixed language select",         {"de": "Sprachauswahl verbessert",                    "en": "Improved language selection"}),
    ("added jaina and english version", {"de": "Neue Spielerin Jaina & englische Sprache",  "en": "Added Jaina & English version"}),
    ("fixed dark mode persitence",    {"de": "Dunkelmodus bleibt erhalten",                 "en": "Dark mode persistence fixed"}),
    ("added dark mode",               {"de": "Dunkelmodus hinzugefügt",                     "en": "Added dark mode"}),
    ("fixed role filter views",       {"de": "Rollenfilter verbessert",                     "en": "Improved role filter views"}),
    ("auto update",                   {"de": "Automatische Datenaktualisierung",            "en": "Automatic data update"}),
    ("added images to history",       {"de": "Bilder in der Match-Historie",                "en": "Images in match history"}),
    ("added history and comparison mode", {"de": "Historie & Vergleich hinzugefügt",        "en": "Added history & comparison"}),
    ("added wr over time",            {"de": "Winrate-Verlauf hinzugefügt",                 "en": "Added winrate over time"}),
    ("added new stat",                {"de": "Neue Statistik hinzugefügt",                  "en": "Added new statistic"}),
    ("added season / date select",    {"de": "Filter nach Season/Datum",                    "en": "Season/date filters"}),
    ("fixed detailed view",           {"de": "Detailansicht korrigiert",                    "en": "Fixed detailed view"}),
    ("added attack def stats",        {"de": "Angriff/Verteidigung-Statistik",              "en": "Attack/Defense stats"}),
    ("added heatmap",                 {"de": "Heatmap verbessert",                          "en": "Heatmap improved"}),
    ("daily report",                  {"de": "Tagesreport",                                 "en": "Daily Report"}),
    ("added times",                   {"de": "Uhrzeiten und Spieldauer",                    "en": "Match times and duration"}),
]

_DESCRIPTION_MAP: list[tuple[str, dict[str, str]]] = [
    ("flag icons",                    {"de": "Die Sprachauswahl nutzt jetzt gestochen scharfe SVG-Flags und wirkt visuell ruhiger.",
                                       "en": "The language switcher now uses crisp SVG flags with a cleaner look."}),
    ("daily banner tie-break",        {"de": "Bei gleich vielen gespielten Maps entscheidet jetzt die höhere Winrate, welche Map im Banner gezeigt wird.",
                                       "en": "If multiple maps tie on plays, the banner now prefers the one with the higher win rate."}),
    ("per-role winrate badges",       {"de": "Im Tagesreport zeigt die Aufstellung pro Spieler farbige Badges mit Rollenzuordnung und Winrate. Tooltips nennen Spiele sowie Siege/Niederlagen.",
                                       "en": "In the daily report, each player now has color-coded badges showing role and win rate. Tooltips include games and W/L."}),
    ("daily default tab",             {"de": "Der Tagesreport ist jetzt die erste Registerkarte und die Standard-Startseite.",
                                       "en": "The Daily Report is now the first tab and the default landing page."}),
    ("map image fallback",            {"de": "Fehlt ein spezifisches Bild für eine Map, wird zuverlässig ein neutrales Standardbild angezeigt.",
                                       "en": "If a specific map image is missing, a safe default image is shown reliably."}),
    ("sync button",                   {"de": "Neuer Sync-Button: Damit kannst du die Daten jederzeit manuell aktualisieren.",
                                       "en": "New sync button: You can manually refresh the data at any time."}),
    ("filter to history",             {"de": "In der Match-Historie gibt es jetzt einen Filter.",
                                       "en": "The match history now has a filter."}),
    ("history filter",                {"de": "Die Historie lässt sich nun filtern.",
                                       "en": "You can now filter the history to narrow down entries."}),
    ("filter history",                {"de": "Für die Historie steht ein Filter zur Verfügung.",
                                       "en": "A filter is available for history so you can find entries faster."}),
    ("added filter to history",       {"de": "Die Historie hat jetzt einen Filter.",
                                       "en": "History now includes a filter for a more focused view."}),
    ("attack/def to history",         {"de": "In der Match-Historie wird nun zwischen Angriff und Verteidigung unterschieden.",
                                       "en": "The match history now distinguishes between attack and defense."}),
    ("attack-def to history",         {"de": "Die Historie zeigt jetzt Angriff und Verteidigung getrennt an.",
                                       "en": "History now shows attack and defense separately."}),
    ("attack def to history",         {"de": "Angriff/Verteidigung ist in der Historie als eigene Information verfügbar.",
                                       "en": "Attack/Defense is now available in history as its own information."}),
    ("atk/def to history",            {"de": "Atk/Def ist in der Historie sichtbar.",
                                       "en": "Atk/Def is visible in history to better classify matches."}),
    ("update button",                 {"de": "Neuer Sync-Button: Manuelles Aktualisieren der Daten ist jetzt direkt möglich.",
                                       "en": "New sync button: Manual data refresh is now available."}),
    ("refresh button",                {"de": "Neuer Sync-Button zum manuellen Aktualisieren der Daten.",
                                       "en": "New sync button to manually refresh the data."}),
    ("reload button",                 {"de": "Neuer Sync-Button zum manuellen Nachladen der Daten.",
                                       "en": "New sync button to manually reload the data."}),
    ("patchnotes",                    {"de": "Es gibt jetzt eine eigene Patchnotes-Seite mit verständlichen Beschreibungen.",
                                       "en": "There is now a dedicated patch notes page with clear descriptions."}),
    ("patch notes",                   {"de": "Eine neue Patchnotes-Seite fasst Änderungen in ganzen Sätzen zusammen.",
                                       "en": "A new patch notes page summarizes changes in full sentences."}),
    ("footer link",                   {"de": "Im Seitenfuß gibt es einen dezenten Link zu den Patchnotes.",
                                       "en": "A subtle link to the patch notes is now available in the footer."}),
    ("webhook",                       {"de": "Ein sicherer, geheimer Webhook kann die Datenaktualisierung von außen anstoßen.",
                                       "en": "A secure, secret webhook can trigger data updates from outside."}),
    ("broadcast",                     {"de": "Wenn Daten aktualisiert werden, bekommen alle Tabs die Änderung automatisch mit.",
                                       "en": "When data updates, all open browser tabs pick up the change automatically."}),
    ("update token",                  {"de": "Datenaktualisierungen werden nun zuverlässig an alle Sitzungen verteilt.",
                                       "en": "Data updates are now reliably broadcast to all sessions."}),
    ("server-update-token",           {"de": "Offene Sitzungen synchronisieren sich automatisch bei Datenänderungen.",
                                       "en": "Open sessions automatically synchronize on data changes."}),
    ("data_token",                    {"de": "Updates werden über einen gemeinsamen Server-Token an alle Clients verteilt.",
                                       "en": "Updates are distributed to all clients via a shared server token."}),
    ("map thumbnail",                 {"de": "Karten-Vorschaubilder sind jetzt breiter.",
                                       "en": "Map thumbnails are wider now."}),
    ("map width",                     {"de": "Die Breite der Karten-Vorschaubilder wurde erhöht.",
                                       "en": "Increased the width of map thumbnails."}),
    ("disabled slider",               {"de": "Deaktivierte Schieberegler wirken im Dunkelmodus dezenter.",
                                       "en": "Disabled sliders look subtler in dark mode."}),
    ("branding",                      {"de": "Branding/Logo angepasst.",
                                       "en": "Branding/logo updated."}),
    ("logo",                          {"de": "Logo überarbeitet und sauber eingebunden.",
                                       "en": "Logo refined and embedded cleanly."}),
    ("added live viewer counter",     {"de": "Es gibt jetzt einen Live-Zähler, der zeigt, wie viele Nutzer die Seite geöffnet haben.",
                                       "en": "There is now a live counter showing how many users currently have the page open."}),
    ("language windows fix",          {"de": "Die Sprachanzeige funktioniert nun auch zuverlässig unter Windows.",
                                       "en": "Language display now works reliably on Windows."}),
    ("fixed language select",         {"de": "Die Sprachauswahl wurde stabiler und klarer gestaltet.",
                                       "en": "The language selector has been made more stable and clearer."}),
    ("added jaina and english version", {"de": "Neue Spielerin Jaina hinzugefügt und die App ist nun auf Englisch verfügbar.",
                                         "en": "Added new player Jaina and provided a complete English version of the app."}),
    ("fixed dark mode persitence",    {"de": "Der Dunkelmodus bleibt jetzt zuverlässig erhalten.",
                                       "en": "Dark mode now reliably persists, even after a restart."}),
    ("added dark mode",               {"de": "Ein Dunkelmodus sorgt für bessere Lesbarkeit bei wenig Licht.",
                                       "en": "A dark mode improves readability in low-light conditions."}),
    ("fixed role filter views",       {"de": "Die Rollenauswahl wurde korrigiert.",
                                       "en": "Role selection was corrected."}),
    ("auto update",                   {"de": "Daten werden nun automatisch aus der Cloud aktualisiert.",
                                       "en": "Data now updates automatically from the cloud."}),
    ("added images to history",       {"de": "Die Match-Historie zeigt jetzt Bilder für Karten und Helden.",
                                       "en": "Match history now shows images for maps and heroes."}),
    ("added history and comparison mode", {"de": "Es gibt eine Historie sowie einen Vergleichsmodus.",
                                           "en": "Added history and comparison mode."}),
    ("added wr over time",            {"de": "Die Winrate wird jetzt über die Zeit visualisiert.",
                                       "en": "Win rate over time is now visualized."}),
    ("added new stat",                {"de": "Neue Kennzahlen wurden ergänzt.",
                                       "en": "New metrics were added."}),
    ("added season / date select",    {"de": "Filter nach Season und Datum erleichtern die Auswertung.",
                                       "en": "Season and date filters make targeted analysis easier."}),
    ("fixed detailed view",           {"de": "Die Detailansicht wurde korrigiert.",
                                       "en": "The detailed view was fixed."}),
    ("added attack def stats",        {"de": "Angriffs- und Verteidigungsstatistiken wurden ergänzt.",
                                       "en": "Added attack and defense statistics."}),
    ("added heatmap",                 {"de": "Die Heatmap wurde eingeführt bzw. verbessert.",
                                       "en": "Introduced or improved the heatmap."}),
    ("added times",                   {"de": "Die Match-Uhrzeiten werden jetzt angezeigt. Die Dauer ist vereinheitlicht.",
                                       "en": "Match time of day is now displayed. Duration is standardized."}),
    ("daily report",                  {"de": "Tagesreport",
                                       "en": "Daily Report"}),
]
# fmt: on


def _beautify_subject(subj: str, lang: str) -> str:
    s = (subj or "").strip().lower()
    for key, loc in _SUBJECT_MAP:
        if key in s:
            return loc.get(lang, loc.get("en", subj))
    return subj[:1].upper() + subj[1:]


def _describe_change(subj: str, files: list[str] | None, lang: str) -> str:
    s = (subj or "").strip().lower()
    for key, loc in _DESCRIPTION_MAP:
        if key in s:
            return loc.get(lang, loc.get("en", ""))
    return ""


# ---------------------------------------------------------------------------
# Flask route
# ---------------------------------------------------------------------------


def register(server):
    """Mount ``/patchnotes`` onto *server*."""

    @server.route("/patchnotes")
    def patchnotes_page():
        lang = _detect_lang()
        md = _load_patchnotes_md(lang)

        parts = [
            "<!doctype html>",
            "<html><head><meta charset='utf-8'><title>Patchnotes</title>",
            "<meta name='viewport' content='width=device-width, initial-scale=1'>",
            "<style>body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu;max-width:820px;margin:24px auto;padding:0 14px;color:#222} "
            ".c{border:1px solid #e5e7eb;border-radius:8px;padding:10px 12px;margin:10px 0;background:#fff} "
            ".meta{color:#6b7280;font-size:12px;margin-top:2px} h1{font-size:20px;margin:0 0 14px} "
            "h2{font-size:15px;margin:4px 0} a{color:#0366d6;text-decoration:none} a:hover{text-decoration:underline}</style>",
            "</head><body>",
            ("<h1>Aktualisierungen</h1>" if lang == "de" else "<h1>Updates</h1>"),
        ]

        if not md:
            parts.append(
                "<p>Keine Patchnotes gefunden.</p>"
                if lang == "de"
                else "<p>No patch notes found.</p>"
            )
            parts.append("</body></html>")
            return ("\n".join(parts), 200, {"Content-Type": "text/html; charset=utf-8"})

        entries = _parse_patchnotes_entries(md)
        rendered = 0
        for e in entries:
            files = e.get("files", [])
            subj_raw = e.get("subject", "")
            is_relevant = any(_is_relevant_file(f) for f in files) or bool(
                _describe_change(subj_raw, files, lang)
            )
            if not is_relevant:
                continue

            subj = _beautify_subject(subj_raw, lang)
            d = e.get("date") or ""
            try:
                y, m, da = d.split("-")
                nice_date = f"{da}.{m}.{y}"
            except Exception:
                nice_date = d
            meta = f"{nice_date} • " + ("Web-Update" if lang == "de" else "Web update")
            desc = _describe_change(subj_raw, files, lang)
            if not desc:
                notes_en = (e.get("notes_en") or e.get("notes") or "").strip()
                notes_de = (e.get("notes_de") or "").strip()
                desc = notes_de if lang == "de" else notes_en
            if not desc:
                continue

            parts.append(
                f"<div class='c'><h2>{html_std.escape(subj)}</h2>"
                f"<div class='meta'>{html_std.escape(meta)}</div>"
                f"<p>{html_std.escape(desc)}</p></div>"
            )
            rendered += 1
            if rendered >= 30:
                break

        if rendered == 0:
            parts.append(
                "<p>Keine Einträge.</p>" if lang == "de" else "<p>No entries.</p>"
            )
        parts.append("</body></html>")
        return ("\n".join(parts), 200, {"Content-Type": "text/html; charset=utf-8"})
