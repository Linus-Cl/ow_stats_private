"""Branding/logo helpers."""
from __future__ import annotations
import os
from typing import Tuple


def resolve_brand_logo_sources() -> tuple[str, str, bool]:
    exts = ["png", "jpg", "jpeg", "webp", "svg"]
    assets_dir = os.path.join("assets", "branding")
    light_src = None
    dark_src = None
    if os.path.isdir(assets_dir):
        for ext in exts:
            p = os.path.join(assets_dir, f"logo_light.{ext}")
            if os.path.exists(p):
                light_src = f"/assets/branding/logo_light.{ext}"
                break
        for ext in exts:
            p = os.path.join(assets_dir, f"logo_dark.{ext}")
            if os.path.exists(p):
                dark_src = f"/assets/branding/logo_dark.{ext}"
                break
    default_src = "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/Overwatch_circle_logo.svg/1024px-Overwatch_circle_logo.svg.png"
    if not light_src:
        light_src = default_src
    dark_invert = False
    if not dark_src:
        dark_src = light_src
        dark_invert = True
    return light_src, dark_src, dark_invert
