# Overwatch Stats Dashboard

A dashboard to track and visualize Overwatch match and player statistics based self logged match data in Excel or Google sheets.

A working example is live under https://retrac.pythonanywhere.com/ (initial load might take a while).

<img width="1697" alt="dashboard_screen" src="https://github.com/user-attachments/assets/533b3cc6-28ff-4119-87e7-f0026ba29543" />


## Current Features
- Win rates by map
- Win rates by hero (with min games filter)
- Win rates by role
- Win rates by attack/defense
- Win rates by Gamemode
- Win rates over time (by hero)
- Role/Map heatmap
- Filter by player
- Filter by Season or Month
- Data Updates from the cloud (Google sheets)

## Optional Branding (Logos)
- You can provide custom logos for light and dark mode.
- Place files under `assets/branding/` with these names (any of: png, jpg, jpeg, webp, svg):
   - `logo_light.{ext}` for light mode
   - `logo_dark.{ext}` for dark mode
- If `logo_dark` is missing, the light logo will be shown with a gentle invert filter in dark mode as a fallback.

## How to Use
1. Put your Overwatch stats in `local.xlsx` (see example format below) or use google sheets from the cloud and adjust the download url in `constants.py`
2. Install requirements:  
   `pip install pandas plotly dash dash-bootstrap-components requests io`
3. Run:  
   `python app.py`
4. Open `http://127.0.0.1:8050` in your browser

## Data Format
Your Excel/Google sheets file needs these columns at minimum:
- Match ID (running unique identifier)
- Win Lose (Win/Lose)
- Map
- For each player: `{Name} Rolle` and `{Name} Hero` columns
- Season
- Year
- Month
