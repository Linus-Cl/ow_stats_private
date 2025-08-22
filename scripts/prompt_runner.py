#!/usr/bin/env python3
"""
Simple local prompt runner for .prompts/prompts.local.yaml
- List prompts by category
- Show details of a prompt id
- (Optional) mark steps as done interactively

This runner can optionally apply selected prompts to the codebase.
"""
from __future__ import annotations
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime
import yaml

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_FILE = ROOT / ".prompts" / "prompts.local.yaml"


def load_yaml(path: Path) -> dict:
    if not path.exists():
        print(f"Prompts-Datei nicht gefunden: {path}")
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def cmd_list(data: dict) -> None:
    prompts = data.get("prompts", {})
    if not prompts:
        print("Keine Prompts definiert.")
        return
    for category, items in prompts.items():
        print(f"\n[{category}]")
        for item in items:
            print(f"- {item.get('id')}: {item.get('title')}")


def find_prompt(data: dict, pid: str) -> dict | None:
    for items in (data.get("prompts") or {}).values():
        for item in items:
            if item.get("id") == pid:
                return item
    return None


def cmd_show(data: dict, pid: str) -> None:
    item = find_prompt(data, pid)
    if not item:
        print(f"Prompt mit id '{pid}' nicht gefunden.")
        sys.exit(2)
    print(f"id: {item.get('id')}")
    print(f"title: {item.get('title')}")
    if desc := item.get("description"):
        print(f"description: {desc}")
    if pre := item.get("preconditions"):
        print("\npreconditions:")
        for p in pre:
            print(f"  - {p}")
    if steps := item.get("steps"):
        print("\nsteps:")
        for s in steps:
            print(f"  - {s}")
    if acc := item.get("acceptance"):
        print("\nacceptance:")
        for a in acc:
            print(f"  - {a}")


def backup_file(path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path.with_suffix(path.suffix + f".bak.{ts}")
    backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return backup


def apply_tidy_imports(root: Path) -> None:
    """Apply a simple imports tidy for app.py: reorder/header docstring present.
    This is idempotent and conservative; it won't touch code below imports.
    """
    app_path = root / "app.py"
    if not app_path.exists():
        print("app.py nicht gefunden.")
        sys.exit(3)
    text = app_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find import block end (first blank line after imports or before '# --- App Initialization ---')
    import_end_idx = 0
    for i, line in enumerate(lines[:200]):
        if line.strip().startswith("# --- App Initialization ---"):
            import_end_idx = i
            break
    if import_end_idx == 0:
        # Fallback: find first occurrence of 'app = Dash('
        for i, line in enumerate(lines[:400]):
            if "app = Dash(" in line:
                import_end_idx = i
                break
    if import_end_idx == 0:
        print("Konnte Importbereich nicht bestimmen – Abbruch.")
        sys.exit(4)

    header = "\n".join(lines[:import_end_idx])
    rest = "\n".join(lines[import_end_idx:])

    # Build normalized header
    normalized = (
        '"""Dash Overwatch Stats App"""\n\n'
        "# Standard library\n"
        "import os\n"
        "import re\n"
        "from io import StringIO\n\n"
        "# Third-party\n"
        "import pandas as pd\n"
        "import plotly.express as px\n"
        "import plotly.graph_objects as go\n"
        "import requests\n"
        "import dash_bootstrap_components as dbc\n"
        "from dash import ALL, Dash, Input, Output, State, ctx, dcc, html\n\n"
        "# --- Local Imports ---\n"
        "import constants\n\n"
    )

    if header.strip() == normalized.strip():
        print("tidy-imports: bereits in Ordnung.")
        return

    backup = backup_file(app_path)
    app_path.write_text(normalized + rest, encoding="utf-8")
    print(f"tidy-imports: aktualisiert. Backup: {backup}")


def apply_validate_data_loading(root: Path) -> None:
    """Inject minimal column validation into load_data (non-invasive)."""
    app_path = root / "app.py"
    text = app_path.read_text(encoding="utf-8")
    marker = "if not df.empty:"
    insert_after = text.find(marker)
    if insert_after == -1:
        print("validate-data-loading: Stelle nicht gefunden (marker). Übersprungen.")
        return
    # Check if already injected
    if "# VALIDATE REQUIRED COLUMNS" in text:
        print("validate-data-loading: bereits vorhanden.")
        return
    injection = (
        "\n        # VALIDATE REQUIRED COLUMNS\n"
        "        required = ['Win Lose', 'Map', 'Match ID']\n"
        "        missing = [c for c in required if c not in df.columns]\n"
        "        if missing:\n"
        "            print(f"
        "Warnung: Fehlende Pflichtspalten: {missing}"
        ")\n"
        "\n"
    )
    backup = backup_file(app_path)
    new_text = text.replace(marker, marker + injection, 1)
    app_path.write_text(new_text, encoding="utf-8")
    print(f"validate-data-loading: Injektion erfolgt. Backup: {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Local prompt runner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Listet alle Prompts auf")

    p_show = sub.add_parser("show", help="Zeigt Details zu einer Prompt-ID")
    p_show.add_argument("id", help="Prompt-ID, z.B. drag-drop-roles")

    p_apply = sub.add_parser("apply", help="Wendet eine Prompt-ID an (auto-edit)")
    p_apply.add_argument("id", help="Prompt-ID, z.B. tidy-imports")
    p_apply.add_argument("--yes", action="store_true", help="Ohne Rückfrage ausführen")

    args = parser.parse_args()
    data = load_yaml(PROMPTS_FILE)

    if args.cmd == "list":
        cmd_list(data)
    elif args.cmd == "show":
        cmd_show(data, args.id)
    elif args.cmd == "apply":
        pid = args.id
        if not find_prompt(data, pid):
            print(f"Prompt-ID '{pid}' nicht in {PROMPTS_FILE} gefunden.")
            sys.exit(5)
        if not args.yes:
            confirm = input(f"Wirklich '{pid}' anwenden? [y/N]: ").strip().lower()
            if confirm not in ("y", "yes"):  # abort
                print("Abgebrochen.")
                sys.exit(0)
        if pid == "tidy-imports":
            apply_tidy_imports(ROOT)
        elif pid == "validate-data-loading":
            apply_validate_data_loading(ROOT)
        else:
            print(f"Für '{pid}' ist kein apply-Handler implementiert.")
            sys.exit(6)


if __name__ == "__main__":
    main()
