"""Patchnotes helpers: reading git log, parsing, and minimal markdown to HTML."""
from __future__ import annotations
import subprocess
import os
import re
import html as html_std
from typing import Any


def is_relevant_file(path: str) -> bool:
    if not path:
        return False
    p = path.strip()
    if p == "app.py":
        return True
    if p.startswith("assets/"):
        return True
    if p == "constants.py":
        return True
    if p == "requirements.txt":
        return True
    if p.endswith(".md"):
        return False
    if p.endswith(".db"):
        return False
    if p.startswith(".github/"):
        return False
    if p.startswith("scripts/"):
        return False
    if p == ".gitignore":
        return False
    if p == "PATCHNOTES.md":
        return False
    return False


def get_patchnotes_commits(max_count: int = 100) -> list[dict[str, Any]]:
    try:
        cmd = [
            "git",
            "log",
            f"-n{max_count}",
            "--date=iso",
            "--pretty=format:%H\t%ad\t%an\t%s",
            "--no-pager",
            "--name-only",
        ]
        out = subprocess.check_output(
            cmd,
            cwd=os.path.dirname(__file__) or ".",
            stderr=subprocess.STDOUT,
        )
        text = out.decode("utf-8", errors="ignore")
    except Exception:
        return []

    commits: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        if "\t" in line and len(line.split("\t")) >= 4:
            if current:
                commits.append(current)
            parts = line.split("\t", 4)
            current = {
                "hash": parts[0],
                "date": parts[1],
                "author": parts[2],
                "subject": parts[3],
                "files": [],
                "relevant": False,
            }
        else:
            if current and line.strip():
                current["files"].append(line.strip())
    if current:
        commits.append(current)

    for c in commits:
        c["relevant"] = any(is_relevant_file(f) for f in c.get("files", []))
    return commits


def md_to_html(md_text: str) -> str:
    lines = md_text.splitlines()
    html_parts: list[str] = []
    in_ul = False
    for raw in lines:
        line = raw.rstrip("\n")
        if line.strip() == "---":
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append("<hr/>")
            continue
        if line.startswith("# "):
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append(f"<h1>{html_std.escape(line[2:].strip())}</h1>")
            continue
        if line.startswith("### "):
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append(f"<h3>{html_std.escape(line[4:].strip())}</h3>")
            continue
        if line.startswith("- "):
            if not in_ul:
                html_parts.append("<ul>")
                in_ul = True
            html_parts.append(f"<li>{html_std.escape(line[2:].strip())}</li>")
            continue
        if not line.strip():
            if in_ul:
                html_parts.append("</ul>")
                in_ul = False
            html_parts.append("<br/>")
            continue
        html_parts.append(f"<p>{html_std.escape(line)}</p>")
    if in_ul:
        html_parts.append("</ul>")
    return "\n".join(html_parts)
