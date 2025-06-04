# Overwatch Stats Dashboard (WIP)

A simple dashboard to track Overwatch match statistics for me and my friends.

## Current Features
- Win rates by map
- Win rates by hero (with min games filter)
- Win rates by role
- Win rates over time (by hero)
- role/map heatmap
- Filter by player 

## How to Use
1. Put your Overwatch stats in `local.xlsx` (see example format below) or use excel from the cloud (OneDrive) and use the commented url
2. Install requirements:  
   `pip install pandas plotly dash dash-bootstrap-components`
3. Run:  
   `python app.py`
4. Open `http://127.0.0.1:8050` in your browser

## Data Format
Your Excel file needs these columns at minimum:
- Match ID
- Win Lose (Win/Lose)
- Map
- For each player: `{Name} Rolle` and `{Name} Hero` columns
- Season
- Year
- Month
