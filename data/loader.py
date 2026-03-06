"""
data/loader.py
==============
Zentrales Daten-Modul: Laden, Mergen und Cachen aller Match-Daten.

Hierher gehört (aus app.py):
  - _jsonl_read()            [app.py ~52]
  - _jsonl_write()           [app.py ~64]
  - _jsonl_append()          [app.py ~77]
  - _jsonl_upsert()          [app.py ~87]
  - _jsonl_delete()          [app.py ~102]
  - _firestore_matches_to_df()[app.py ~3611]
  - _build_merged_df()       [app.py ~3665]
  - _reload_merged_data()    [app.py ~3686]
  - _patch_df_with_match()   [app.py ~3706]
  - _remove_df_row()         [app.py ~3728]
  - filter_data()            [app.py ~4209]
  - season_sort_key()        [app.py ~4252]
  - format_season_display()  [app.py ~4260]

  Globale Variablen die hier leben:
  - _df_cache  (der gecachte DataFrame)
  - _df_lock   (threading.Lock)
"""

import pandas as pd
from functools import lru_cache

# TODO: Code aus app.py hierher verschieben
