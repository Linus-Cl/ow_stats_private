"""
utils/assets.py
===============
Asset-URL helpers for map images, hero portraits and branding logos.
All paths are returned as Dash-compatible ``/assets/…`` URLs.
"""

from __future__ import annotations

import os
import re
import unicodedata

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------
_MAP_FILENAME_ALIAS: dict[str, str] = {
    "illios": "ilios",
    "watchpoint_gibralta": "watchpoint_gibraltar",
}

_HERO_ALIAS: dict[str, str] = {
    "wreckingball": "wrecking_ball",
    "hammond": "wrecking_ball",
    "soldier76": "soldier",
    "zenyatta": "zen",
    "baptiste": "baptist",
    "torbjrn": "torbjörn",
    "lcio": "lucio",
    "jetpackcat": "jetpack_cat",
}

_IMG_EXTS = ("png", "jpg", "jpeg", "webp", "svg")


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def get_map_image_url(map_name: str) -> str:
    """Return the ``/assets/maps/<file>`` URL for *map_name* (case-insensitive, accent-safe)."""
    if not isinstance(map_name, str):
        return "/assets/maps/default.png"

    # Normalize: lowercase, strip diacritics, collapse spaces/apostrophes
    normalized = unicodedata.normalize("NFD", map_name.lower())
    stripped = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    cleaned = stripped.replace(" ", "_").replace("'", "")
    cleaned = _MAP_FILENAME_ALIAS.get(cleaned, cleaned)

    for ext in ("jpg", "png"):
        fname = f"{cleaned}.{ext}"
        if os.path.exists(os.path.join("assets", "maps", fname)):
            return f"/assets/maps/{fname}"

    return "/assets/maps/default.png"


def get_hero_image_url(hero_name: str) -> str:
    """Return the ``/assets/heroes/<file>`` URL for *hero_name* (fuzzy matching)."""
    if not isinstance(hero_name, str):
        return "/assets/heroes/default_hero.png"

    base = hero_name.lower()
    cleaned_base = base.replace(".", "").replace(":", "").replace("ú", "u")

    candidates: list[str] = list(
        {
            cleaned_base.replace(" ", "_"),
            cleaned_base.replace(" ", ""),
            re.sub(r"[^a-z0-9]", "", base),
        }
    )

    # Add alias-based canonical name
    alias_key = re.sub(r"[^a-z0-9]", "", base)
    if alias_key in _HERO_ALIAS:
        candidates.append(_HERO_ALIAS[alias_key])

    for name in candidates:
        if not name:
            continue
        for ext in ("png", "jpg", "jpeg"):
            fname = f"{name}.{ext}"
            if os.path.exists(os.path.join("assets", "heroes", fname)):
                return f"/assets/heroes/{fname}"

    return "/assets/heroes/default_hero.png"


# ---------------------------------------------------------------------------
# Branding / logo resolution
# ---------------------------------------------------------------------------


def _find_logo(basename: str) -> str | None:
    """Return the ``/assets/branding/<basename>.<ext>`` URL if the file exists."""
    brand_dir = os.path.join("assets", "branding")
    if os.path.isdir(brand_dir):
        for ext in _IMG_EXTS:
            p = os.path.join(brand_dir, f"{basename}.{ext}")
            if os.path.exists(p):
                return f"/assets/branding/{basename}.{ext}"
    return None


# Naming convention for logo files:
#   logo_dark.*  → dark-coloured logo (black/dark)  → shown on LIGHT backgrounds
#   logo_light.* → light-coloured logo (white/pale) → shown on DARK backgrounds
#
# app.py uses these as:
#   LIGHT_LOGO_SRC  (class="light-only")  → visible in light mode → needs dark logo
#   DARK_LOGO_SRC   (class="dark-only")   → visible in dark mode  → needs light logo
_logo_for_light_mode = _find_logo("logo_dark")  # dark-coloured logo on white bg
_logo_for_dark_mode = _find_logo("logo_light")  # light-coloured logo on dark bg

_fallback = "/assets/branding/logo_dark.svg"
LIGHT_LOGO_SRC = _logo_for_light_mode or _fallback
DARK_LOGO_SRC = _logo_for_dark_mode or LIGHT_LOGO_SRC
DARK_LOGO_INVERT = _logo_for_dark_mode is None  # no separate file → use CSS invert
