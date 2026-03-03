"""
Firebase Firestore service layer for match data.

Handles reading/writing matches and config to Firestore.
Falls back gracefully if Firebase is not configured (no credentials).

Setup:
  1. Create a Firebase project at https://console.firebase.google.com
  2. Go to Project Settings > Service accounts > Generate new private key
  3. Save the JSON file as `firebase-credentials.json` in the project root
     OR set environment variable FIREBASE_CREDENTIALS_JSON with the JSON content
  4. pip install firebase-admin
"""

import os
import json
import time
from datetime import datetime
from typing import Optional

_firestore_db = None
_firebase_available = False

try:
    import firebase_admin
    from firebase_admin import credentials, firestore

    def _init_firebase():
        global _firestore_db, _firebase_available
        if _firestore_db is not None:
            return True

        cred = None
        # Option 1: JSON file in project root
        cred_path = os.path.join(os.path.dirname(__file__), "firebase-credentials.json")
        if os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
        else:
            # Option 2: Environment variable with JSON content
            cred_json = os.environ.get("FIREBASE_CREDENTIALS_JSON", "").strip()
            if cred_json:
                try:
                    cred_dict = json.loads(cred_json)
                    cred = credentials.Certificate(cred_dict)
                except Exception as e:
                    print(f"[Firebase] Failed to parse FIREBASE_CREDENTIALS_JSON: {e}")
                    return False

        if cred is None:
            print("[Firebase] No credentials found. Firestore disabled.")
            return False

        try:
            firebase_admin.initialize_app(cred)
            _firestore_db = firestore.client()
            _firebase_available = True
            print("[Firebase] Firestore initialized successfully.")
            return True
        except Exception as e:
            print(f"[Firebase] Init failed: {e}")
            return False

    # Try to init at import time
    _init_firebase()

except ImportError:
    print("[Firebase] firebase-admin not installed. Firestore disabled.")

    def _init_firebase():
        return False


# ============================================================
# Public API
# ============================================================

MATCHES_COLLECTION = "matches"
CONFIG_COLLECTION = "config"
CONFIG_DOC = "global"

# --- SSE token for real-time updates ---
_last_change_token = str(int(time.time() * 1000))


def is_available() -> bool:
    return _firebase_available and _firestore_db is not None


def get_last_change_token() -> str:
    return _last_change_token


def _bump_token():
    global _last_change_token
    _last_change_token = str(int(time.time() * 1000))


# ---------- Matches ----------


def save_match(match_data: dict) -> Optional[str]:
    """Save a match document to Firestore. Returns document ID or None on failure."""
    if not is_available():
        return None
    try:
        now = datetime.utcnow().isoformat() + "Z"
        match_data.setdefault("created_at", now)
        match_data["updated_at"] = now
        match_data["source"] = "webapp"

        # Use match_id as document ID for easy lookup
        doc_id = str(match_data.get("match_id", ""))
        if doc_id:
            _firestore_db.collection(MATCHES_COLLECTION).document(doc_id).set(
                match_data
            )
        else:
            ref = _firestore_db.collection(MATCHES_COLLECTION).add(match_data)
            doc_id = ref[1].id

        _bump_token()
        print(f"[Firebase] Saved match {doc_id}")
        return doc_id
    except Exception as e:
        print(f"[Firebase] save_match failed: {e}")
        return None


def get_all_matches() -> list[dict]:
    """Fetch all matches from Firestore, sorted by match_id descending."""
    if not is_available():
        return []
    try:
        docs = (
            _firestore_db.collection(MATCHES_COLLECTION)
            .order_by("match_id", direction=firestore.Query.DESCENDING)
            .stream()
        )
        results = []
        for doc in docs:
            d = doc.to_dict()
            d["_doc_id"] = doc.id
            results.append(d)
        return results
    except Exception as e:
        print(f"[Firebase] get_all_matches failed: {e}")
        return []


def get_match(match_id: int) -> Optional[dict]:
    """Fetch a single match by match_id."""
    if not is_available():
        return None
    try:
        doc = _firestore_db.collection(MATCHES_COLLECTION).document(str(match_id)).get()
        if doc.exists:
            d = doc.to_dict()
            d["_doc_id"] = doc.id
            return d
        return None
    except Exception as e:
        print(f"[Firebase] get_match failed: {e}")
        return None


def update_match(match_id: int, match_data: dict) -> bool:
    """Update an existing match. Returns True on success."""
    if not is_available():
        return False
    try:
        now = datetime.utcnow().isoformat() + "Z"
        match_data["updated_at"] = now
        _firestore_db.collection(MATCHES_COLLECTION).document(str(match_id)).set(
            match_data, merge=True
        )
        _bump_token()
        print(f"[Firebase] Updated match {match_id}")
        return True
    except Exception as e:
        print(f"[Firebase] update_match failed: {e}")
        return False


def delete_match(match_id: int) -> bool:
    """Delete a match by match_id. Returns True on success."""
    if not is_available():
        return False
    try:
        _firestore_db.collection(MATCHES_COLLECTION).document(str(match_id)).delete()
        _bump_token()
        print(f"[Firebase] Deleted match {match_id}")
        return True
    except Exception as e:
        print(f"[Firebase] delete_match failed: {e}")
        return False


def get_next_match_id() -> int:
    """Returns the next available match_id (max existing + 1)."""
    if not is_available():
        return 1
    try:
        docs = (
            _firestore_db.collection(MATCHES_COLLECTION)
            .order_by("match_id", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )
        for doc in docs:
            return int(doc.to_dict().get("match_id", 0)) + 1
        return 1
    except Exception as e:
        print(f"[Firebase] get_next_match_id failed: {e}")
        return 1


# ---------- Config (Season etc.) ----------


def get_config() -> dict:
    """Get the global config document."""
    if not is_available():
        return {}
    try:
        doc = _firestore_db.collection(CONFIG_COLLECTION).document(CONFIG_DOC).get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        print(f"[Firebase] get_config failed: {e}")
        return {}


def set_config(data: dict) -> bool:
    """Update global config (merge)."""
    if not is_available():
        return False
    try:
        _firestore_db.collection(CONFIG_COLLECTION).document(CONFIG_DOC).set(
            data, merge=True
        )
        print(f"[Firebase] Config updated: {list(data.keys())}")
        return True
    except Exception as e:
        print(f"[Firebase] set_config failed: {e}")
        return False


def get_current_season() -> str:
    """Get the current season from config, default 'Season 19'."""
    cfg = get_config()
    return cfg.get("current_season", "Season 19")
