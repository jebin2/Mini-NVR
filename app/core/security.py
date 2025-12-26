from slowapi import Limiter
from slowapi.util import get_remote_address
import secrets
import json
import os
from core import config

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Persistent Session Store
# We store in RECORD_DIR because it is a mounted volume.
SESSION_FILE = os.path.join(config.RECORD_DIR, "sessions.json")
ACTIVE_SESSIONS = {}

def load_sessions():
    """Load sessions from disk on startup."""
    global ACTIVE_SESSIONS
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, 'r') as f:
                ACTIVE_SESSIONS = json.load(f)
        except (json.JSONDecodeError, OSError):
            ACTIVE_SESSIONS = {}

def save_sessions():
    """Save sessions to disk."""
    try:
        # Atomic write safely
        tmp_file = SESSION_FILE + ".tmp"
        with open(tmp_file, 'w') as f:
            json.dump(ACTIVE_SESSIONS, f)
        os.rename(tmp_file, SESSION_FILE)
    except OSError:
        pass

# Initialize on module load
load_sessions()

def create_session_token():
    return secrets.token_hex(32)

def add_session(username, token):
    if username not in ACTIVE_SESSIONS:
        ACTIVE_SESSIONS[username] = []
    ACTIVE_SESSIONS[username].append(token)
    save_sessions()

def remove_session(username, token):
    if username in ACTIVE_SESSIONS and token in ACTIVE_SESSIONS[username]:
        ACTIVE_SESSIONS[username].remove(token)
        save_sessions()

def is_session_valid(username, token):
    return username in ACTIVE_SESSIONS and token in ACTIVE_SESSIONS[username]
