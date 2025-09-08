# Patchnotes – Branch daily_report

### 2025-09-08 — flag icons
- M app.py
- M assets/theme.css
- Notes: Language switcher now uses crisp SVG flags with cleaner styling.

### 2025-09-08 — daily banner tie-break
- M app.py
- Notes: When multiple maps tie for most played, the banner now prefers the one with the higher winrate.

### 2025-09-08 — per-role winrate badges
- M app.py
- M assets/theme.css
- Notes: Player lineup shows per-role winrate badges with tooltips; badges aren’t text-selectable and use an arrow cursor.

### 2025-09-08 — daily default tab
- M app.py
- Notes: Daily Report is now the first tab and the default landing page.

### 2025-09-08 — map image fallback
- M app.py
- Notes: Safer default map image when no specific asset exists.

### 2025-08-31 — added times and duration formatting
- M app.py
- Notes: Daily and History now show the time of day for matches (EN: am/pm, DE: "Uhr"). Duration is standardized to m:ss and shown on the right in History. The Daily timeline shows a time chip only for today/future, and duplicate times on thumbnails were removed.
 - Hinweise (DE): Match-Uhrzeiten werden jetzt angezeigt (z. B. 13:15 Uhr). Die Dauer ist vereinheitlicht (m:ss) und steht rechts in der Historie. Auf der Daily-Timeline erscheint die Zeit nur für heute/zukünftig; doppelte Zeiten auf Thumbnails wurden entfernt.

### 2025-08-30 — Daily Report tab, date selection, and UX polish
- New Daily Report tab with:
  - Visual banner using “Map of the day” background; improved text contrast in light mode.
  - Hero spotlights: “Most played hero”, “Biggest Flex” (with up to three hero avatars and translated “Distinct heroes”), “One Trick Pony” (portrait, games), and dynamic “<Hero>-Carry” (portrait, WR, games).
  - Player lineup grid with roles, top hero, games, W/L, and winrate.
  - Compact timeline: horizontal map tiles with W/L colored borders and small connectors; tiles are clickable and jump to the corresponding card in match history with smooth scroll.
- Date selection and behavior:
  - Static DatePicker pinned at the top-right of the banner; localized display format (DE: DD.MM.YYYY, EN: YYYY-MM-DD) and translated placeholder (Datum/Date).
  - Prevent selecting future dates; initial visible month set to today.
  - Fallback logic: if today (or a selected date) has no games, automatically show the last active day.
    - Badge “Last active day” only appears on auto-fallback (not when the user explicitly picks a date).
    - If a user-selected date has no games, show a clear notice: “No games on selected day — Showing last active day: …”.
- Data loading and robustness:
  - Header normalization for Excel inputs: maps common English/German variants to canonical columns (Win Lose, Map, Match ID, Datum; plus per-player Role/Hero), parses dates, and sorts by Match ID descending.
- Internationalization (i18n):
  - Added/used keys: newest_first, last_active_day, distinct_heroes, no_games_selected, showing_last_active, most_played_hero, map_of_the_day, date_placeholder; Daily tab label localized.
- Dark mode and styling:
  - DatePicker over banner made more visible: compact “pill” look, subtle halo/shadow, hover/focus ring.
  - Dark mode calendar popover, grid, and nav arrows darkened; outside/disabled dates styled for readability.
  - Dark mode DatePicker input/placeholder colors adjusted so “Date/Datum” is clearly readable.

---

# Patchnotes – Branch main

### 2025-08-23 — In-App Patchnotes-Seite hinzugefügt
- Änderungen:
  - Neue Seite unter /patchnotes mit automatisch erkannter Sprache (DE/EN) und nutzerfreundlichen Beschreibungen in ganzen Sätzen
  - Untechnische Darstellung ohne Commit-IDs/Autoren/Dateilisten
  - Dezenter Footer-Link in der App, der die aktuelle Sprache berücksichtigt
  - Spezifische Mappings für häufige Änderungen (z. B. Sync-Button, Historien-Filter, Angriff/Verteidigung in der Historie)
- Hinweis: Diese Einträge werden dynamisch aus dem Git-Verlauf gefiltert; irrelevante Commits werden ausgeblendet

Generated from repository history on 2025-08-23. One section per commit (newest first). Status codes: A=Added, M=Modified, D=Deleted, R=Renamed.

---

### 2025-08-23 10:55:54 +0200 — 5b7563f — added db
- Author: Linus Claußen
- Changes:
  - M .gitignore
- Notes: Adjusted ignore rules (likely to include/exclude DB files).

### 2025-08-23 10:55:21 +0200 — 8fffbc8 — Stop tracking active_sessions.db and add .gitignore to ignore local DB; ensure DB not committed again
- Author: Linus Claußen
- Changes:
  - D active_sessions.db
- Notes: Removed tracked SQLite DB; rely on .gitignore to prevent re-adding.

### 2025-08-23 10:53:25 +0200 — af8dab1 — Merge pull request #6 from Linus-Cl/new
- Author: Linus Claußen
- Notes: Merge commit.

### 2025-08-23 10:50:39 +0200 — 6037844 — language windows fix
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Fixed language selector/flags display on Windows.

### 2025-08-23 10:49:57 +0200 — 57faa15 — fixed language select
- Author: Linus Claußen
- Changes:
  - M active_sessions.db
  - M app.py
- Notes: Tweaks to language selection logic; DB file was accidentally touched in repo (later removed).

### 2025-08-23 10:44:13 +0200 — 06e529f — added live viewer counter
- Author: Linus Claußen
- Changes:
  - A active_sessions.db
  - M app.py
  - A assets/online_heartbeat.js
- Notes: Implemented live online counter with heartbeat and client unload beacon.

### 2025-08-22 22:17:15 +0200 — 5fe2025 — added missing translations
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Completed i18n strings.

### 2025-08-22 22:04:30 +0200 — fbae123 — Update readme with live demo link and clarifications
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-08-22 22:02:12 +0200 — 7aca7b1 — update readme
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-08-22 21:57:42 +0200 — d96f7c2 — Merge pull request #5 from Linus-Cl/ui
- Author: Linus Claußen
- Notes: Merge commit (added jaina and english version).

### 2025-08-22 21:57:07 +0200 — e012882 — added jaina and english version
- Author: Linus Claußen
- Changes:
  - M app.py
  - M constants.py
- Notes: Added player "Jaina" and English locale.

### 2025-08-22 21:02:05 +0200 — 7f78622 — Merge pull request #4 from Linus-Cl/ui
- Author: Linus Claußen
- Notes: Merge commit (fixed dark mode persitence).

### 2025-08-22 21:01:35 +0200 — 18952a2 — fixed dark mode persitence
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Persisted theme across sessions correctly.

### 2025-08-22 20:54:07 +0200 — ee98226 — Merge pull request #3 from Linus-Cl/ui
- Author: Linus Claußen
- Notes: Merge commit (added dark mode).

### 2025-08-22 20:53:19 +0200 — 1720815 — added dark mode
- Author: Linus Claußen
- Changes:
  - M app.py
  - A assets/theme.css
  - M readme.md
- Notes: Introduced dark mode and theme styling; docs updated.

### 2025-08-22 20:07:36 +0200 — 7273446 — Merge pull request #2 from Linus-Cl/fix/role_select
- Author: Linus Claußen
- Notes: Merge commit (fixed role filter views).

### 2025-08-22 20:07:00 +0200 — e73a94f — fixed role filter views
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Corrected role selection filters.

### 2025-08-22 19:50:23 +0200 — a97eab1 — Merge pull request #1 from Linus-Cl/auto_update
- Author: Linus Claußen
- Notes: Merge commit (auto update).

### 2025-08-22 19:49:41 +0200 — f32447b — auto update
- Author: Linus Claußen
- Changes:
  - A .github/workflows/refresh.yml
  - M .gitignore
  - M app.py
  - M constants.py
- Notes: Implemented cloud data auto-update and webhook; added CI workflow.

### 2025-08-22 13:31:05 +0200 — 00a950b — Merge branch 'player_compare'
- Author: Linus Claußen
- Notes: Merge commit.

### 2025-08-22 13:30:54 +0200 — c3ddadc — Role assignment detailed mode toggle honors hero filters; inline history auto-disable + end hint; expanded tooltips with wins/losses; minor UX tweaks
- Author: Linus Claußen
- Changes:
  - M .gitignore
  - M app.py
  - A app.py.bak.20250822-122615
  - M requirements.txt
  - A scripts/prompt_runner.py
- Notes: Role assignment and history UX improvements; backup created; tooling updates.

### 2025-07-20 20:06:07 +0200 — 96ee89b — added filter to history
- Author: Linus Claussen
- Changes:
  - M app.py
- Notes: Match history filters.

### 2025-07-20 11:47:06 +0200 — ac17da6 — Merge pull request #13 from Linus-Cl/history_attack_def
- Author: Linus Claußen
- Notes: Merge commit (added attack/def to history).

### 2025-07-20 11:46:22 +0200 — 637861e — added attack/def to history
- Author: Linus Claussen
- Changes:
  - M app.py
- Notes: Added attack/defense info in history.

### 2025-07-16 11:06:38 +0200 — c2b3c21 — fixed torb png
- Author: Linus Claussen
- Changes:
  - R assets/heroes/torbjoern.png → assets/heroes/torbjörn.png
- Notes: Corrected file name encoding for Torbjörn.

### 2025-06-28 17:51:46 +0200 — 551bef8 — Merge pull request #12 from Linus-Cl/ui
- Author: Linus Claußen
- Notes: Merge commit (added images to history).

### 2025-06-28 17:46:06 +0200 — 4f687ac — added images to history
- Author: Linus Claußen
- Changes:
  - M app.py
  - A many assets/heroes/*.png, assets/maps/*.png
  - M constants.py
- Notes: Added hero and map images; integrated into UI/history.

### 2025-06-28 11:51:35 +0200 — 81f4515 — Merge pull request #11 from Linus-Cl/ui
- Author: Linus Claußen
- Notes: Merge commit (fixed tooltips and removed piechart for games played).

### 2025-06-28 11:50:59 +0200 — 2d888d4 — fixed tooltips and removed piechart for games played
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Tooltip fixes; simplified charts.

### 2025-06-27 19:53:20 +0200 — 8d3d8b3 — Update constants.py
- Author: Linus Claußen
- Changes:
  - M constants.py
- Notes: Constants adjusted.

### 2025-06-27 19:50:35 +0200 — 8f2d814 — cleanup
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Code cleanup.

### 2025-06-27 13:30:05 +0200 — 4f47a16 — Merge pull request #10 from Linus-Cl/gemini
- Author: Linus Claußen
- Notes: Merge commit (added pies and split games view).

### 2025-06-27 13:29:28 +0200 — c30720b — added pies and split games view
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: New charts for distribution and split view.

### 2025-06-26 13:22:58 +0200 — b3bd4b4 — Merge pull request #9 from Linus-Cl/gemini
- Author: Linus Claußen
- Notes: Merge commit (added history and comparison mode).

### 2025-06-26 13:22:20 +0200 — 825af6f — added history and comparison mode
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Introduced match history and player comparison features.

### 2025-06-21 13:54:53 +0200 — baa56c5 — Update readme.md
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-06-18 13:13:21 +0200 — acfaad3 — Update readme.md
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-06-18 09:40:34 +0200 — 97b0b62 — fixed detailed view
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Bugfixes in detailed stats view.

### 2025-06-17 22:06:37 +0200 — 9234549 — added attack def stats and hover elements
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Attack/Defense stats and improved hover tooltips.

### 2025-06-12 23:37:07 +0200 — 2b34ff2 — added heatmap tooltip games played
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Heatmap shows games played in tooltip.

### 2025-06-12 23:15:02 +0200 — 41860c6 — Update readme.md
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-06-12 23:11:11 +0200 — 291d4cf — picture upload
- Author: Linus Claußen
- Changes:
  - A dashboard_screen.png
- Notes: Added screenshot.

### 2025-06-12 23:05:04 +0200 — 520fd46 — Merge pull request #8 from Linus-Cl/cleanup
- Author: Linus Claußen
- Notes: Merge commit (cleaned up refactor and adjusted readme).

### 2025-06-12 23:04:47 +0200 — fdc429d — cleaned up refactor and adjusted readme
- Author: Linus Claußen
- Changes:
  - M app.py
  - A constants.py
  - M readme.md
- Notes: Refactor and docs; introduced constants module.

### 2025-06-07 17:17:02 +0200 — c2c2180 — added losses stat
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Added losses statistic.

### 2025-06-07 17:11:27 +0200 — 83a7ddd — reorder
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: UI/chart ordering tweaks.

### 2025-06-07 17:06:45 +0200 — 51199d5 — fixed name order
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Corrected sorting for names.

### 2025-06-07 17:05:27 +0200 — a002b07 — fixed total player count
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Correct total player count logic.

### 2025-06-07 16:50:54 +0200 — 2571a2d — working hosted version
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Hosting stability adjustments.

### 2025-06-04 18:37:04 +0200 — 059691e — Merge pull request #7 from Linus-Cl/host
- Author: Linus Claußen
- Notes: Merge commit (hosting setup).

### 2025-06-04 18:36:22 +0200 — b8ab572 — hosting setup
- Author: Linus Claußen
- Changes:
  - M app.py
  - A requirements.txt
- Notes: Dependencies and hosting setup.

### 2025-06-04 18:29:26 +0200 — f356a64 — added sync button
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Added manual sync/update button.

### 2025-06-04 17:19:39 +0200 — 36f98ab — Update readme.md
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-06-04 17:19:11 +0200 — 487bb48 — Merge pull request #6 from Linus-Cl/win_ot
- Author: Linus Claußen
- Notes: Merge commit (update readme).

### 2025-06-04 17:18:37 +0200 — 522a1ae — update readme
- Author: Linus Claußen
- Changes:
  - M readme.md
- Notes: Docs update.

### 2025-06-04 16:53:29 +0200 — 0c19856 — Merge pull request #5 from Linus-Cl/win_ot
- Author: Linus Claußen
- Notes: Merge commit (cleanup).

### 2025-06-04 16:52:49 +0200 — d4eabbc — cleanup
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Code cleanup.

### 2025-06-04 16:36:43 +0200 — 3274f43 — Merge pull request #4 from Linus-Cl/win_ot
- Author: Linus Claußen
- Notes: Merge commit (added wr over time).

### 2025-06-04 16:35:41 +0200 — 77e9ada — added wr over time
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Winrate-over-time chart added.

### 2025-06-04 16:09:52 +0200 — c226a2f — Merge pull request #3 from Linus-Cl/games_played_stats
- Author: Linus Claußen
- Notes: Merge commit (disabled slider).

### 2025-06-04 16:08:30 +0200 — 7c25997 — disabled slider
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Disabled slider in certain contexts.

### 2025-06-04 15:34:13 +0200 — a3a8581 — Merge pull request #2 from Linus-Cl/games_played_stats
- Author: Linus Claußen
- Notes: Merge commit (added new stat).

### 2025-06-04 15:33:11 +0200 — c0ab7f7 — added new stat
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: New statistic added.

### 2025-06-04 15:24:07 +0200 — 6984fc0 — Merge pull request #1 from Linus-Cl/date_select
- Author: Linus Claußen
- Notes: Merge commit (added season / date select).

### 2025-06-04 15:23:15 +0200 — 4746b0f — added season / date select
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Season/year/month filters introduced.

### 2025-06-04 15:12:23 +0200 — 7e181c1 — fixed statistics
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Bugfixes in statistics calculations.

### 2025-06-04 14:09:42 +0200 — 93fe711 — added download from url
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: Download data from URL implemented.

### 2025-06-04 12:29:18 +0200 — 28706c1 — clean ignore
- Author: Linus Claußen
- Changes:
  - M .gitignore
- Notes: Cleaned ignore rules.

### 2025-06-04 12:28:17 +0200 — 33feb7c — rm data
- Author: Linus Claußen
- Changes:
  - D OW_Win_Stats.xlsx
- Notes: Removed data file from repo.

### 2025-06-04 12:25:14 +0200 — 940e811 — test
- Author: Linus Claußen
- Changes:
  - M .gitignore
  - A OW_Win_Stats.xlsx
- Notes: Test commit adding data file (later removed).

### 2025-06-04 12:22:18 +0200 — e0d0dc3 — added readme
- Author: Linus Claußen
- Changes:
  - A .gitignore
  - M app.py
  - A readme.md
- Notes: Initial README and ignore setup.

### 2025-06-04 12:14:48 +0200 — e4f9a94 — first working version
- Author: Linus Claußen
- Changes:
  - M app.py
- Notes: First working version milestone.

### 2025-06-04 11:39:02 +0200 — f67c9c4 — init
- Author: Linus Claußen
- Changes:
  - A app.py
- Notes: Initial commit with base app.
