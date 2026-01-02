#!/usr/bin/env python3
"""
YouTube OAuth Re-authentication Script

This script runs on the HOST machine (not in Docker) to perform OAuth
authentication using the Neko browser. It authenticates each configured
YouTube account one by one.

Usage: python3 scripts/reauth.py
Logs: logs/reauth.log
"""

import os
import sys
import shutil
from datetime import datetime

# Get project directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "reauth.log")

# Ensure logs directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


class Tee:
    """Redirect stdout/stderr to both terminal and log file."""
    def __init__(self, log_path, stream):
        self.log_path = log_path
        self.stream = stream
        self.log_file = open(log_path, 'a')
    
    def write(self, data):
        if data.strip():  # Only log non-empty lines
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            # Write to original stream
            self.stream.write(data)
            self.stream.flush()
            # Write to log file with timestamp (for lines that don't have one)
            for line in data.splitlines():
                if line.strip():
                    self.log_file.write(f"{timestamp} {line}\n")
            self.log_file.flush()
        else:
            self.stream.write(data)
            self.stream.flush()
    
    def flush(self):
        self.stream.flush()
        self.log_file.flush()
    
    def close(self):
        self.log_file.close()


# Redirect stdout and stderr to log file
sys.stdout = Tee(LOG_FILE, sys.__stdout__)
sys.stderr = Tee(LOG_FILE, sys.__stderr__)


def log(message: str):
    """Log message to stdout (which now also goes to log file)."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"{timestamp} {message}"
    print(log_line, flush=True)


# Load .env file
def load_env_file(path: str) -> dict:
    """Load environment variables from a file."""
    env = {}
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env[key.strip()] = value.strip().strip('"\'')
    return env


def discover_youtube_accounts():
    """
    Discover all configured YouTube accounts from environment variables.
    Looks for YOUTUBE_CLIENT_SECRET_PATH_N and YOUTUBE_TOKEN_PATH_N pairs.
    """
    accounts = []
    idx = 1
    
    while True:
        client_secret = os.environ.get(f"YOUTUBE_CLIENT_SECRET_PATH_{idx}")
        token_path = os.environ.get(f"YOUTUBE_TOKEN_PATH_{idx}")
        
        if not client_secret or not token_path:
            break
            
        accounts.append({
            "id": idx,
            "client_secret": client_secret,
            "token_path": token_path
        })
        idx += 1
    
    if not accounts:
        # Fallback to legacy single-account env vars
        client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET_PATH")
        token_path = os.environ.get("YOUTUBE_TOKEN_PATH")
        if client_secret and token_path:
            accounts.append({
                "id": 1,
                "client_secret": client_secret,
                "token_path": token_path
            })
    
    return accounts


# Load environment
env_path = os.path.join(PROJECT_DIR, ".env")
if os.path.exists(env_path):
    env = load_env_file(env_path)
    for key, value in env.items():
        os.environ.setdefault(key, value)

# Try to import youtube_auto_pub
try:
    from youtube_auto_pub import YouTubeConfig, YouTubeUploader
except ImportError:
    # Fallback: try loading from sibling git directory
    youtube_auto_pub_path = os.path.expanduser("~/git/youtube_auto_pub")
    if os.path.isdir(youtube_auto_pub_path):
        sys.path.insert(0, youtube_auto_pub_path)
        from youtube_auto_pub import YouTubeConfig, YouTubeUploader
    else:
        log("[Reauth] ✗ youtube_auto_pub not found!")
        log("[Reauth] Install with: pip install git+https://github.com/jebin2/youtube_auto_pub.git")
        sys.exit(1)


def authenticate_account(account: dict) -> bool:
    """Authenticate a single YouTube account."""
    account_id = account["id"]
    client_secret_path = account["client_secret"]
    token_path = account["token_path"]
    
    log(f"[Reauth] ─────────────────────────────────────────")
    log(f"[Reauth] Account {account_id}")
    log(f"[Reauth] ─────────────────────────────────────────")
    
    # Get shared config from environment
    encrypt_path = os.environ.get("YOUTUBE_ENCRYPT_PATH")
    hf_repo_id = os.environ.get("HF_REPO_ID")
    hf_token = os.environ.get("HF_TOKEN")
    encryption_key = os.environ.get("YT_ENCRYP_KEY")
    
    # Resolve relative paths
    if encrypt_path and not os.path.isabs(encrypt_path):
        encrypt_path = os.path.join(PROJECT_DIR, encrypt_path.lstrip("./"))
    if not os.path.isabs(client_secret_path):
        client_secret_path = os.path.join(PROJECT_DIR, client_secret_path.lstrip("./"))
    
    log(f"[Reauth] Client secret: {client_secret_path}")
    log(f"[Reauth] Token path: {token_path}")
    log("")
    
    # Get filenames (not full paths - youtube_auto_pub handles this)
    token_filename = os.path.basename(token_path)
    client_filename = os.path.basename(client_secret_path)
    
    # Unique docker name for this account
    docker_name = f"nvr_youtube_reauth_{account_id}"

    try:
        # Create config - running on host with display
        config = YouTubeConfig(
            encrypt_path=encrypt_path,
            hf_repo_id=hf_repo_id,
            hf_token=hf_token,
            encryption_key=encryption_key,
            # Running on host with display - enable Neko browser
            is_docker=False,
            has_display=True,
            headless_mode=False,
            docker_name=docker_name,
            google_email=os.environ.get("GOOGLE_EMAIL"),
            google_password=os.environ.get("GOOGLE_PASSWORD"),
            project_path=PROJECT_DIR,
            client_secret_filename=client_filename,
            token_filename=token_filename
        )
        
        # Create uploader
        uploader = YouTubeUploader(config)
        
        # Copy client_secret to encrypt folder if it exists locally
        if os.path.exists(client_secret_path):
            dest = os.path.join(encrypt_path, client_filename)
            if not os.path.exists(dest):
                os.makedirs(encrypt_path, exist_ok=True)
                shutil.copy2(client_secret_path, dest)
                log(f"[Reauth] Copied {client_filename} to encrypt folder")
        
        log(f"[Reauth] Starting authentication for account {account_id}...")
        log("[Reauth] This will open a browser window for OAuth.")
        log("")
        
        # Get service (this triggers auth flow if needed)
        service = uploader.get_service()
        
        if service:
            log("")
            log(f"[Reauth] ✓ Account {account_id} authenticated successfully!")
            return True
        else:
            log(f"[Reauth] ✗ Account {account_id} authentication failed!")
            return False
            
    except Exception as e:
        log(f"[Reauth] ✗ Account {account_id} error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run OAuth authentication flow for all accounts."""
    log("=" * 50)
    log("[Reauth] YouTube OAuth Re-authentication (Multi-Account)")
    log("=" * 50)
    log("")
    
    # Discover all accounts
    accounts = discover_youtube_accounts()
    
    if not accounts:
        log("[Reauth] ✗ No YouTube accounts configured!")
        log("[Reauth] Set YOUTUBE_CLIENT_SECRET_PATH_1 and YOUTUBE_TOKEN_PATH_1")
        return 1
    
    log(f"[Reauth] Found {len(accounts)} YouTube account(s)")
    log("")
    
    # Authenticate each account one by one
    success_count = 0
    for account in accounts:
        if authenticate_account(account):
            success_count += 1
        log("")
    
    # Summary
    log("=" * 50)
    log(f"[Reauth] Summary: {success_count}/{len(accounts)} accounts authenticated")
    log("=" * 50)
    
    if success_count == len(accounts):
        log("[Reauth] ✓ All accounts authenticated successfully!")
        return 0
    elif success_count > 0:
        log(f"[Reauth] ⚠ {len(accounts) - success_count} account(s) failed")
        return 1
    else:
        log("[Reauth] ✗ All authentications failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
