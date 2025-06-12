# Overwatch Stats Dashboard (WIP)

A dashboard to track Overwatch match statistics.

## Current Features
- Win rates by map
- Win rates by hero (with min games filter)
- Win rates by role
- Win rates over time (by hero)
- Role/Map heatmap
- Filter by player 
- Data Updates from the cloud (Google sheets)

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
