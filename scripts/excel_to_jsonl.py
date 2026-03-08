"""
scripts/excel_to_jsonl.py
=========================
Konvertiert ow_stats_export.xlsx → local_data.jsonl (lokale Testdaten).

Ausführen (aus dem Projektroot):
    python scripts/excel_to_jsonl.py

Das Script überschreibt local_data.jsonl komplett mit allen Matches aus der Excel.
Nützlich um die lokale Entwicklungsumgebung mit echten Daten zu befüllen.
"""

import json
import os
import sys

# Projektroot in den Python-Pfad
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd

# ── Wiederverwendet die Konvertierungslogik aus dem Firestore-Migrations-Script ──
from scripts.migrate_excel_to_firestore import row_to_match

import config

EXCEL_NAME = "ow_stats_export.xlsx"
EXCEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), EXCEL_NAME
)
JSONL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), config.LOCAL_DATA_FILE
)


def main():
    if not os.path.exists(EXCEL_PATH):
        print(f"❌ {EXCEL_NAME} nicht gefunden unter: {EXCEL_PATH}")
        sys.exit(1)

    print(f"📂 Lese {EXCEL_PATH} ...")
    df = pd.read_excel(EXCEL_PATH, engine="openpyxl")
    df.columns = df.columns.map(lambda c: str(c).strip())
    print(f"   {len(df)} Zeilen, Spalten: {list(df.columns[:6])} ...")

    players = config.PLAYERS

    matches = []
    skipped = 0
    for _, row in df.iterrows():
        m = row_to_match(dict(row), players)
        if m is None:
            skipped += 1
            continue
        # Unnötige Felder fürs JSONL weglassen
        m.pop("source", None)
        m.pop("created_at", None)
        m.pop("updated_at", None)
        matches.append(m)

    print(
        f"   ✅ {len(matches)} Matches konvertiert, {skipped} übersprungen (fehlende ID)"
    )

    # Nach match_id absteigend sortieren (neueste zuerst, wie loader.py erwartet)
    matches.sort(key=lambda m: m["match_id"], reverse=True)

    print(f"📝 Schreibe {JSONL_PATH} ...")
    with open(JSONL_PATH, "w", encoding="utf-8") as fh:
        for m in matches:
            fh.write(json.dumps(m, default=str, ensure_ascii=False) + "\n")

    print(f"✅ Fertig — {len(matches)} Matches in local_data.jsonl geschrieben.")


if __name__ == "__main__":
    main()
