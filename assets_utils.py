"""Asset path helpers for heroes and maps."""
from __future__ import annotations
import os
import re


def get_map_image_url(map_name):
    if not isinstance(map_name, str):
        return "/assets/maps/default.png"
    cleaned_name = map_name.lower().replace(" ", "_").replace("'", "")
    for ext in [".jpg", ".png"]:
        image_filename = f"{cleaned_name}{ext}"
        asset_path = f"/assets/maps/{image_filename}"
        local_path = os.path.join("assets", "maps", image_filename)
        if os.path.exists(local_path):
            return asset_path
    return "/assets/maps/default.png"


def get_hero_image_url(hero_name):
    if not isinstance(hero_name, str):
        return "/assets/heroes/default_hero.png"
    base_name = hero_name.lower()
    potential = set()
    cleaned_base = base_name.replace(".", "").replace(":", "").replace("ú", "u")
    potential.add(cleaned_base.replace(" ", "_"))
    potential.add(cleaned_base.replace(" ", ""))
    potential.add(re.sub(r"[^a-z0-9]", "", base_name))
    for name in potential:
        if not name:
            continue
        for ext in [".png", ".jpg", ".jpeg"]:
            image_filename = f"{name}{ext}"
            asset_path = f"/assets/heroes/{image_filename}"
            local_path = os.path.join("assets", "heroes", image_filename)
            if os.path.exists(local_path):
                return asset_path
    return "/assets/heroes/default_hero.png"
