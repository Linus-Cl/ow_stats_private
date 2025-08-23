"""Internationalization helpers and strings for the OW Stats app."""
from __future__ import annotations


def tr(key: str, lang: str) -> str:
    T = {
        "title": {"en": "Overwatch Statistics", "de": "Overwatch Statistiken"},
        "filters": {"en": "Filters", "de": "Filter"},
        "select_player": {"en": "Select player:", "de": "Spieler auswählen:"},
        "select_season": {
            "en": "Select season (overrides year/month):",
            "de": "Season auswählen (überschreibt Jahr/Monat):",
        },
        "select_year": {"en": "Select year:", "de": "Jahr auswählen:"},
        "select_month": {"en": "Select month:", "de": "Monat auswählen:"},
        "min_games": {"en": "Minimum games:", "de": "Mindestanzahl Spiele:"},
        "map_mode_stats": {"en": "Map & Mode Stats", "de": "Map & Mode Statistik"},
        "role_assign": {"en": "Role Assignment", "de": "Rollen-Zuordnung"},
        "hero_stats": {"en": "Hero Stats", "de": "Held Statistik"},
        "role_stats": {"en": "Role Stats", "de": "Rollen Statistik"},
        "heatmap": {"en": "Performance Heatmap", "de": "Performance Heatmap"},
        "trend": {"en": "Winrate Trend", "de": "Winrate Verlauf"},
        "trend_hero_filter": {
            "en": "Filter hero (optional):",
            "de": "Held filtern (optional):",
        },
        "history": {"en": "Match History", "de": "Match Verlauf"},
        "history_filter_player": {"en": "Filter by player:", "de": "Spieler filtern:"},
        "history_filter_hero": {"en": "Filter hero:", "de": "Held filtern:"},
        "update_from_cloud": {
            "en": "Update Data from Cloud",
            "de": "Daten aus Cloud aktualisieren",
        },
        "dark_mode": {"en": "Dark Mode", "de": "Dark Mode"},
        "map_winrate": {"en": "Winrate by Map", "de": "Winrate nach Map"},
        "map_plays": {"en": "Games per Map", "de": "Spiele pro Map"},
        "map_gamemode": {"en": "Gamemode Stats", "de": "Gamemode Statistik"},
        "map_attackdef": {
            "en": "Attack/Defense Stats",
            "de": "Attack/Defense Statistik",
        },
        "detailed": {"en": "Detailed", "de": "Detailliert"},
        "map_filter_opt": {
            "en": "Map filter (optional)",
            "de": "Map-Filter (optional)",
        },
        "choose_maps": {"en": "Choose maps", "de": "Maps wählen"},
        "bench": {
            "en": "Bench (exclude players)",
            "de": "Nicht dabei (Spieler ausschließen)",
        },
        "choose_players": {"en": "Choose players", "de": "Spieler wählen"},
        "tank_label": {"en": "Tank (max. 1)", "de": "Tank (max. 1 Spieler)"},
        "damage_label": {"en": "Damage (max. 2)", "de": "Damage (max. 2 Spieler)"},
        "support_label": {"en": "Support (max. 2)", "de": "Support (max. 2 Spieler)"},
        "detailed_mode": {
            "en": "Detailed mode (select heroes)",
            "de": "Detaillierter Modus (Helden wählen)",
        },
        "show_matching": {
            "en": "Show matching matches",
            "de": "Passende Matches anzeigen",
        },
        "load_more": {"en": "Load more", "de": "Mehr anzeigen"},
        "load_n_more": {"en": "Load {n} more", "de": "{n} weitere laden"},
        "all_players": {"en": "All players", "de": "Alle Spieler"},
        "no_history": {
            "en": "No match history available.",
            "de": "Keine Match History verfügbar.",
        },
        "no_games_filter": {
            "en": "No games found for this filter combination.",
            "de": "Für diese Filterkombination wurden keine Spiele gefunden.",
        },
        "only_relevant_winrate": {
            "en": "Only relevant for winrate statistics",
            "de": "Nur relevant für Winrate-Statistiken",
        },
        "season": {"en": "Season", "de": "Saison"},
        "victory": {"en": "VICTORY", "de": "SIEG"},
        "defeat": {"en": "DEFEAT", "de": "NIEDERLAGE"},
        "total_games": {"en": "Total games", "de": "Gesamtspiele"},
        "won": {"en": "Won", "de": "Gewonnen"},
        "lost": {"en": "Lost", "de": "Verloren"},
        "winrate": {"en": "Winrate", "de": "Winrate"},
        "most_played_hero": {"en": "Most played hero", "de": "Meistgespielter Held"},
        "best_wr_hero": {"en": "Best winrate (Hero)", "de": "Beste Winrate (Held)"},
        "most_played_map": {"en": "Most played map", "de": "Meistgespielte Map"},
        "best_wr_map": {"en": "Best winrate (Map)", "de": "Beste Winrate (Map)"},
        "no_data": {"en": "No data", "de": "Keine Daten"},
        "min_n_games": {"en": "Min. {n} games", "de": "Min. {n} Spiele"},
        "overall": {"en": "Overall", "de": "Gesamt"},
        "no_more_entries": {"en": "No more entries.", "de": "Keine weiteren Einträge."},
        "no_data_selection": {
            "en": "No data available for the selection",
            "de": "Keine Daten für die Auswahl verfügbar",
        },
        "stats_header": {"en": "Overall statistics", "de": "Gesamtstatistiken"},
        "compare_with": {"en": "Compare with:", "de": "Vergleiche mit:"},
        "games": {"en": "Games", "de": "Spiele"},
        "please_select_roles_first": {
            "en": "Please select players in roles first.",
            "de": "Bitte zuerst Spieler in Rollen auswählen.",
        },
        "no_data_loaded": {"en": "No data loaded.", "de": "Keine Daten geladen."},
        "no_data_selected_maps": {
            "en": "No data for selected maps.",
            "de": "Keine Daten für die gewählten Maps.",
        },
        "no_data_timeframe": {
            "en": "No data for the selected timeframe.",
            "de": "Keine Daten für den gewählten Zeitraum.",
        },
        "required_cols_missing": {
            "en": "Required columns are missing: {cols}",
            "de": "Erforderliche Spalten fehlen: {cols}",
        },
        "no_games_for_constellation": {
            "en": "No games found for this constellation.",
            "de": "Keine Spiele für diese Konstellation gefunden.",
        },
        "too_many_players": {
            "en": "Too many players selected: max 1 Tank, max 2 Damage, max 2 Support.",
            "de": "Zu viele Spieler gewählt: max 1 Tank, max 2 Damage, max 2 Support.",
        },
        "please_select_at_least_one_player": {
            "en": "Please select at least one player in any role.",
            "de": "Bitte mindestens einen Spieler in einer Rolle auswählen.",
        },
        "duplicate_players_roles": {
            "en": "Each player may appear only once across all roles.",
            "de": "Jeder Spieler darf nur einmal vorkommen (über alle Rollen).",
        },
        "too_many_players_history": {
            "en": "Too many players selected for history.",
            "de": "Zu viele Spieler gewählt für die Historie.",
        },
        "no_matching_matches": {
            "en": "No matching matches found.",
            "de": "Keine passenden Matches gefunden.",
        },
        "role_config_stats": {
            "en": "Statistics for role configuration",
            "de": "Statistik zur Rollen-Konstellation",
        },
        "bench_short": {"en": "Bench", "de": "Nicht dabei"},
        "heroes_filter": {"en": "Hero filters:", "de": "Helden-Filter:"},
        "choose_heroes_optional": {
            "en": "Choose heroes (optional)",
            "de": "Helden wählen (optional)",
        },
        "show_matching": {
            "en": "Show matching matches",
            "de": "Passende Matches anzeigen",
        },
        "invalid_date": {"en": "Invalid Date", "de": "Ungültiges Datum"},
        "unknown_map": {"en": "Unknown Map", "de": "Unbekannte Map"},
        "role_label": {"en": "Role", "de": "Rolle"},
        "players": {"en": "Players", "de": "Spieler"},
        "by": {"en": "by", "de": "nach"},
        "distribution": {"en": "Distribution", "de": "Verteilung"},
        "hero_label": {"en": "Hero", "de": "Held"},
        "map_label": {"en": "Map", "de": "Map"},
        "gamemode_label": {"en": "Gamemode", "de": "Gamemode"},
        "attackdef_label": {"en": "Attack/Defense", "de": "Attack/Defense"},
        "side": {"en": "Side", "de": "Seite"},
        "game_number": {"en": "Game number", "de": "Spielnummer"},
        "online_now": {"en": "Online", "de": "Online"},
    }
    v = T.get(key, {})
    return v.get(lang, v.get("en", key))
