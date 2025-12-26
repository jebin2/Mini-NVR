from slowapi import Limiter
from slowapi.util import get_remote_address
import secrets
import json
import os
import bcrypt
import threading
from core import config

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)

# Session Configuration
MAX_SESSIONS_PER_USER = 5

# Persistent Session Store
# Store in /tmp to prevent access via web (not in public recordings dir)
SESSION_FILE = "/tmp/nvr_sessions.json"
ACTIVE_SESSIONS = {}
_session_lock = threading.Lock()

def load_sessions():
    """Load sessions from disk on startup."""
    global ACTIVE_SESSIONS
    with _session_lock:
        if os.path.exists(SESSION_FILE):
            try:
                with open(SESSION_FILE, 'r') as f:
                    ACTIVE_SESSIONS = json.load(f)
            except (json.JSONDecodeError, OSError, IOError):
                ACTIVE_SESSIONS = {}

def _save_sessions_unlocked():
    """Save sessions to disk. Must be called with lock held."""
    try:
        # Atomic write safely
        tmp_file = SESSION_FILE + ".tmp"
        with open(tmp_file, 'w') as f:
            json.dump(ACTIVE_SESSIONS, f)
        os.rename(tmp_file, SESSION_FILE)
    except (OSError, IOError):
        pass

# Initialize on module load
load_sessions()

def create_session_token():
    return secrets.token_hex(32)

def add_session(username, token):
    """Add a session token for user, enforcing max sessions limit."""
    with _session_lock:
        if username not in ACTIVE_SESSIONS:
            ACTIVE_SESSIONS[username] = []
        
        # Enforce session limit - remove oldest if at limit
        while len(ACTIVE_SESSIONS[username]) >= MAX_SESSIONS_PER_USER:
            ACTIVE_SESSIONS[username].pop(0)
        
        ACTIVE_SESSIONS[username].append(token)
        _save_sessions_unlocked()

def remove_session(username, token):
    with _session_lock:
        if username in ACTIVE_SESSIONS and token in ACTIVE_SESSIONS[username]:
            ACTIVE_SESSIONS[username].remove(token)
            _save_sessions_unlocked()

def is_session_valid(username, token):
    with _session_lock:
        return username in ACTIVE_SESSIONS and token in ACTIVE_SESSIONS[username]


# --- Password Hashing ---

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against a bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except (ValueError, TypeError):
        return False
