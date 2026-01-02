#!/usr/bin/env python3
"""
YouTube OAuth Re-authentication Script

This script runs on the HOST machine (not in Docker) to perform OAuth
authentication using the Neko browser. It authenticates each configured
YouTube account one by one.

Usage: python3 youtube_authenticate/reauth.py
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

# Add Project Dir to path to import app.utils
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Ensure logs directory exists
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)


from app.core.logger import setup_stdout_capture

# Redirect stdout and stderr to log file
setup_stdout_capture(LOG_FILE)

def log(message: str):
    """Log message to stdout (which now also goes to log file)."""
    # Tee handles timestamping in file, print handles stdout
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}", flush=True)





from app.core.config import settings

def discover_youtube_accounts():
    """
    Get configured YouTube accounts from settings.
    """
    return settings.youtube_accounts

# Env loaded automatically by importing settings

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
    
    # Get shared config from settings
    encrypt_path = settings.youtube_encrypt_path
    hf_repo_id = settings.hf_repo_id
    hf_token = settings.hf_token
    encryption_key = settings.yt_encrypt_key
    
    # Resolve relative paths
    if encrypt_path and not os.path.isabs(encrypt_path):
        encrypt_path = os.path.join(PROJECT_DIR, encrypt_path.lstrip("./"))
    if not os.path.isabs(client_secret_path):
        # Resolve relative to PROJECT_DIR (Mini-NVR root) if needed
        # But if it's relative to youtube_authenticate, we might need adjustment.
        # Assuming secrets are in main project dir or secrets dir.
        if client_secret_path.startswith("youtube_authenticate/"):
            client_secret_path = os.path.join(PROJECT_DIR, client_secret_path)
        else:
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
            google_email=settings.google_email,
            google_password=settings.google_password,
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
