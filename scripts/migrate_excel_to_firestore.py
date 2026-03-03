"""
Einmalig-Migration: Alle Matches aus local.xlsx → Firebase Firestore.

Ausführen: python scripts/migrate_excel_to_firestore.py

Voraussetzungen:
  - firebase-credentials.json im Projektroot vorhanden
  - pip install firebase-admin openpyxl pandas
  - Script aus dem Projektroot ausführen

Sicherheit:
  - Überschreibt nur Dokumente mit derselben Match ID (merge=False → set)
  - Bestehende Firestore-Daten mit höherer ID werden NICHT gelöscht
  - Läuft idempotent (kann mehrfach ausgeführt werden)
"""

import os
import sys
import re

# Projektroot in den Python-Pfad aufnehmen
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from datetime import datetime, date

import firebase_service

BATCH_SIZE = 400  # Firestore max 500 ops/batch; 400 als Puffer


def normalize_str(val) -> str:
    if val is None or (isinstance(val, float) and str(val) == 'nan'):
        return ""
    return str(val).strip()


def normalize_player_role(role: str) -> str:
    """Normalisiert Rollenwerte aus alten Excel-Daten."""
    mapping = {"DPS": "Damage", "Damage": "Damage", "Tank": "Tank", "Support": "Support"}
    return mapping.get(role.strip(), role.strip()) if role.strip() else ""


def row_to_match(row: dict, players: list) -> dict:
    """Konvertiert eine Excel-Zeile in das Firestore Match-Format."""

    def col(name):
        for k, v in row.items():
            if str(k).strip().lower() == name.lower():
                return v
        return None

    match_id_raw = col("Match ID")
    try:
        match_id = int(float(str(match_id_raw).strip()))
    except Exception:
        return None  # Zeile ohne gültige Match ID überspringen

    # Datum normalisieren
    datum_raw = col("Datum")
    date_str = ""
    if datum_raw:
        try:
            if isinstance(datum_raw, (datetime, date)):
                date_str = datum_raw.strftime("%Y-%m-%d") if hasattr(datum_raw, 'strftime') else str(datum_raw)[:10]
            else:
                parsed = pd.to_datetime(str(datum_raw), errors="coerce")
                if not pd.isna(parsed):
                    date_str = parsed.strftime("%Y-%m-%d")
        except Exception:
            date_str = str(datum_raw)[:10]

    # Spielerdaten
    players_data = {}
    for pname in players:
        hero_raw = normalize_str(col(f"{pname} Hero"))
        role_raw = normalize_str(col(f"{pname} Rolle"))
        if not hero_raw or hero_raw.lower() in ("", "nicht dabei", "nan"):
            hero_raw = "nicht dabei"
            role_raw = "nicht dabei"
        else:
            role_raw = normalize_player_role(role_raw)
        players_data[pname] = {"hero": hero_raw, "role": role_raw}

    result = normalize_str(col("Win Lose"))
    if not result:
        result = normalize_str(col("Ergebnis"))

    attack_def = normalize_str(col("Attack Def"))

    season = normalize_str(col("Season"))
    map_name = normalize_str(col("Map"))
    gamemode = normalize_str(col("Gamemode"))
    time_val = normalize_str(col("Time")) or normalize_str(col("Matchtime")) or ""

    now = datetime.utcnow().isoformat() + "Z"
    return {
        "match_id": match_id,
        "date": date_str,
        "time": time_val,
        "season": season,
        "map": map_name,
        "gamemode": gamemode,
        "result": result,
        "attack_defense": attack_def,
        "players": players_data,
        "source": "excel_migration",
        "created_at": now,
        "updated_at": now,
    }


def migrate():
    # ---- Firebase verbinden ----
    if not firebase_service.is_available():
        print("❌ Firebase nicht verfügbar. Prüfe firebase-credentials.json.")
        sys.exit(1)

    try:
        from firebase_admin import firestore as _fs
        db = firebase_service._firestore_db
    except Exception as e:
        print(f"❌ Firestore-Verbindung fehlgeschlagen: {e}")
        sys.exit(1)

    # ---- Excel lesen ----
    excel_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "local.xlsx")
    if not os.path.exists(excel_path):
        print(f"❌ local.xlsx nicht gefunden unter: {excel_path}")
        sys.exit(1)

    print(f"📂 Lese {excel_path} ...")
    df = pd.read_excel(excel_path, engine="openpyxl")
    df.columns = df.columns.map(lambda c: str(c).strip())
    print(f"   {len(df)} Zeilen geladen, Spalten: {list(df.columns[:8])}...")

    import constants
    players = constants.players

    # ---- Konvertieren ----
    print("🔄 Konvertiere Zeilen...")
    matches = []
    skipped = 0
    for _, row in df.iterrows():
        m = row_to_match(dict(row), players)
        if m is None:
            skipped += 1
            continue
        matches.append(m)

    print(f"   ✅ {len(matches)} Matches konvertiert, {skipped} übersprungen (fehlende ID)")

    # ---- Schon vorhandene IDs prüfen (optional, für Info) ----
    print("🔍 Prüfe bereits vorhandene Matches in Firestore...")
    existing = set()
    try:
        docs = db.collection(firebase_service.MATCHES_COLLECTION).stream()
        for doc in docs:
            d = doc.to_dict()
            if "match_id" in d:
                existing.add(int(d["match_id"]))
    except Exception as e:
        print(f"   ⚠️  Konnte vorhandene Matches nicht prüfen: {e}")

    new_matches = [m for m in matches if m["match_id"] not in existing]
    update_matches = [m for m in matches if m["match_id"] in existing]
    print(f"   → {len(new_matches)} neue, {len(update_matches)} bereits vorhanden (werden überschrieben)")

    if not matches:
        print("✅ Nichts zu migrieren.")
        return

    # ---- Batch-Upload ----
    total = len(matches)
    uploaded = 0
    errors = 0

    print(f"\n📤 Lade {total} Matches in {((total - 1) // BATCH_SIZE) + 1} Batches hoch...")
    for i in range(0, total, BATCH_SIZE):
        batch_matches = matches[i: i + BATCH_SIZE]
        batch = db.batch()
        for m in batch_matches:
            ref = db.collection(firebase_service.MATCHES_COLLECTION).document(str(m["match_id"]))
            batch.set(ref, m)
        try:
            batch.commit()
            uploaded += len(batch_matches)
            pct = int(uploaded / total * 100)
            print(f"   [{pct:3d}%] {uploaded}/{total} hochgeladen (Batch {i // BATCH_SIZE + 1})")
        except Exception as e:
            errors += len(batch_matches)
            print(f"   ❌ Batch-Fehler: {e}")

    print(f"\n{'✅' if errors == 0 else '⚠️ '} Migration abgeschlossen: {uploaded} hochgeladen, {errors} Fehler")

    if errors == 0:
        print("\n🎯 Nächster Schritt:")
        print("   Die App nutzt nun automatisch nur noch Firestore als Datenquelle.")
        print("   Excel bleibt als Notfall-Fallback erhalten, wird aber nicht mehr angezeigt.")


if __name__ == "__main__":
    migrate()
