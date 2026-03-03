"""
Overwatch 2 data mappings: Hero→Role, Map→Gamemode, Map→Attack/Defense logic.
Used by both the Python backend and exported as JSON for the JS input page.
"""

# ============================================================
# Hero → Role mapping (all current OW2 heroes as of Season 19)
# ============================================================
HERO_ROLE_MAP: dict[str, str] = {
    # --- Tank ---
    "D.Va": "Tank",
    "Dva": "Tank",
    "Doomfist": "Tank",
    "Hazard": "Tank",
    "Junkerqueen": "Tank",
    "Junker Queen": "Tank",
    "Mauga": "Tank",
    "Orisa": "Tank",
    "Ramattra": "Tank",
    "Reinhardt": "Tank",
    "Roadhog": "Tank",
    "Sigma": "Tank",
    "Winston": "Tank",
    "Wrecking Ball": "Tank",
    "Zarya": "Tank",
    # --- Damage ---
    "Ashe": "Damage",
    "Bastion": "Damage",
    "Cassidy": "Damage",
    "Echo": "Damage",
    "Freja": "Damage",
    "Genji": "Damage",
    "Hanzo": "Damage",
    "Junkrat": "Damage",
    "Mei": "Damage",
    "Pharah": "Damage",
    "Reaper": "Damage",
    "Sojourn": "Damage",
    "Soldier 76": "Damage",
    "Soldier": "Damage",
    "Sombra": "Damage",
    "Symmetra": "Damage",
    "Torbjörn": "Damage",
    "Torbjorn": "Damage",
    "Tracer": "Damage",
    "Venture": "Damage",
    "Widowmaker": "Damage",
    "Wuyang": "Damage",
    # --- Support ---
    "Ana": "Support",
    "Baptiste": "Support",
    "Baptist": "Support",
    "Brigitte": "Support",
    "Illari": "Support",
    "Juno": "Support",
    "Kiriko": "Support",
    "Lifeweaver": "Support",
    "Lucio": "Support",
    "Lúcio": "Support",
    "Mercy": "Support",
    "Moira": "Support",
    "Zenyatta": "Support",
    "Zen": "Support",
}

# Normalized lookup (lowercase, stripped) for fuzzy matching
_HERO_ROLE_NORM: dict[str, str] = {
    k.strip().lower(): v for k, v in HERO_ROLE_MAP.items()
}


def get_role_for_hero(hero_name: str) -> str | None:
    """Return role for a hero name, case-insensitive. None if unknown."""
    if not hero_name:
        return None
    return _HERO_ROLE_NORM.get(hero_name.strip().lower())


# Canonical hero list (display names, sorted)
ALL_HEROES: list[str] = sorted(
    set(
        [
            "Ana",
            "Ashe",
            "Baptiste",
            "Bastion",
            "Brigitte",
            "Cassidy",
            "D.Va",
            "Doomfist",
            "Echo",
            "Freja",
            "Genji",
            "Hanzo",
            "Hazard",
            "Illari",
            "Junker Queen",
            "Junkrat",
            "Juno",
            "Kiriko",
            "Lifeweaver",
            "Lúcio",
            "Mauga",
            "Mei",
            "Mercy",
            "Moira",
            "Orisa",
            "Pharah",
            "Ramattra",
            "Reaper",
            "Reinhardt",
            "Roadhog",
            "Sigma",
            "Sojourn",
            "Soldier 76",
            "Sombra",
            "Symmetra",
            "Torbjörn",
            "Tracer",
            "Venture",
            "Widowmaker",
            "Winston",
            "Wrecking Ball",
            "Wuyang",
            "Zarya",
            "Zenyatta",
        ]
    )
)


# ============================================================
# Map → Gamemode mapping (all current OW2 maps)
# ============================================================
MAP_GAMEMODE_MAP: dict[str, str] = {
    # Escort
    "Circuit Royal": "Escort",
    "Dorado": "Escort",
    "Havana": "Escort",
    "Junkertown": "Escort",
    "Rialto": "Escort",
    "Route 66": "Escort",
    "Shambali Monastery": "Escort",
    "Watchpoint Gibraltar": "Escort",
    "Watchpoint Gibralta": "Escort",  # typo in data
    # Hybrid
    "Blizzard World": "Hybrid",
    "Eichenwalde": "Hybrid",
    "Hollywood": "Hybrid",
    "Kings Row": "Hybrid",
    "King's Row": "Hybrid",
    "Midtown": "Hybrid",
    "Numbani": "Hybrid",
    "Paraiso": "Hybrid",
    "Paraíso": "Hybrid",
    # Control
    "Antarctic Peninsula": "Control",
    "Busan": "Control",
    "Illios": "Control",
    "Ilios": "Control",
    "Lijiang Tower": "Control",
    "Nepal": "Control",
    "Oasis": "Control",
    "Samoa": "Control",
    # Push
    "Colosseo": "Push",
    "Esperanca": "Push",
    "Esperança": "Push",
    "New Queen Street": "Push",
    "Runasapi": "Push",
    # Flashpoint
    "New Junk City": "Flashpoint",
    "Suravasa": "Flashpoint",
    "Throne of Anubis": "Flashpoint",
    # Clash
    "Hanaoka": "Clash",
    "Aatlis": "Clash",
}

# Normalized lookup
_MAP_GAMEMODE_NORM: dict[str, str] = {
    k.strip().lower(): v for k, v in MAP_GAMEMODE_MAP.items()
}

ALL_MAPS: list[str] = sorted(
    set(
        [
            "Antarctic Peninsula",
            "Blizzard World",
            "Busan",
            "Circuit Royal",
            "Colosseo",
            "Dorado",
            "Eichenwalde",
            "Esperança",
            "Hanaoka",
            "Havana",
            "Hollywood",
            "Ilios",
            "Junkertown",
            "King's Row",
            "Lijiang Tower",
            "Midtown",
            "Nepal",
            "New Junk City",
            "New Queen Street",
            "Numbani",
            "Oasis",
            "Paraíso",
            "Rialto",
            "Route 66",
            "Runasapi",
            "Samoa",
            "Shambali Monastery",
            "Suravasa",
            "Throne of Anubis",
            "Watchpoint Gibraltar",
            "Aatlis",
        ]
    )
)


def get_gamemode_for_map(map_name: str) -> str | None:
    """Return the gamemode for a map name, case-insensitive."""
    if not map_name:
        return None
    return _MAP_GAMEMODE_NORM.get(map_name.strip().lower())


# ============================================================
# Attack/Defense auto-detection
# ============================================================
# Gamemodes with classical Attack/Defense:
#   Escort, Hybrid → user must choose Attack or Defense
# Gamemodes with "Attack Attack" (symmetric):
#   Push, Flashpoint → auto "Attack Attack"
# Gamemodes with neither:
#   Control, Clash → "N/A" or skip

GAMEMODE_ATTACK_DEF: dict[str, str | None] = {
    "Escort": None,  # user must choose: Attack or Defense
    "Hybrid": None,  # user must choose: Attack or Defense
    "Control": "Attack Attack",
    "Push": "Attack Attack",
    "Flashpoint": "Attack Attack",
    "Clash": "Attack Attack",
}


def get_attack_def_for_gamemode(gamemode: str) -> str | None:
    """
    Returns automatic attack/def value if deterministic, None if user must choose.
    """
    if not gamemode:
        return None
    return GAMEMODE_ATTACK_DEF.get(gamemode)


# ============================================================
# All Seasons (for dropdown)
# ============================================================
ALL_SEASONS: list[str] = [f"Season {i}" for i in range(10, 25)]  # extend as needed


# ============================================================
# JSON export for the frontend JS
# ============================================================
def to_json_mappings() -> dict:
    """Return all mappings as a JSON-serializable dict for the /input page."""
    return {
        "heroRoleMap": {h: HERO_ROLE_MAP[h] for h in ALL_HEROES if h in HERO_ROLE_MAP},
        "allHeroes": ALL_HEROES,
        "mapGamemodeMap": {m: MAP_GAMEMODE_MAP.get(m, "") for m in ALL_MAPS},
        "allMaps": ALL_MAPS,
        "gamemodeAttackDef": GAMEMODE_ATTACK_DEF,
        "allSeasons": ALL_SEASONS,
    }
