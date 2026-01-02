#!/usr/bin/env python3
"""
YouTube OAuth Re-authentication Script

Runs on HOST (not Docker) to perform OAuth authentication using Neko browser.
Authenticates each configured YouTube account sequentially.

Usage: python3 youtube_authenticate/reauth.py
Logs:  logs/reauth.log
"""

import os
import sys
import shutil
import logging
from typing import List, Dict, Optional

# Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
LOG_FILE = os.path.join(PROJECT_DIR, "logs", "reauth.log")
ENCRYPT_PATH = os.path.join(SCRIPT_DIR, "encrypt")

# Add project to path for imports
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app.core.config import settings
from youtube_auto_pub import YouTubeConfig, YouTubeUploader

def setup_logger() -> logging.Logger:
    """Configure logging to file and console."""
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    logger = logging.getLogger("reauth")
    logger.setLevel(logging.INFO)
    logger.handlers = []
    
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    
    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)
    
    # File handler
    file_handler = logging.FileHandler(LOG_FILE, mode="a")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    return logger


logger = setup_logger()


def authenticate_account(account: Dict) -> bool:
    """Authenticate a single YouTube account."""
    account_id = account["id"]
    client_secret_path = account["client_secret"]
    token_path = account["token_path"]
    
    logger.info("─" * 50)
    logger.info(f"Account {account_id}")
    logger.info("─" * 50)
    
    # Ensure encrypt directory exists
    os.makedirs(ENCRYPT_PATH, exist_ok=True)
    
    # Resolve client secret path
    if not os.path.isabs(client_secret_path):
        if client_secret_path.startswith("youtube_authenticate/"):
            client_secret_path = os.path.join(PROJECT_DIR, client_secret_path)
        else:
            client_secret_path = os.path.join(PROJECT_DIR, client_secret_path.lstrip("./"))
    
    logger.info(f"Client secret: {client_secret_path}")
    logger.info(f"Token path: {token_path}")
    logger.info(f"Encrypt path: {ENCRYPT_PATH}")
    
    # Filenames for youtube_auto_pub
    token_filename = os.path.basename(token_path)
    client_filename = os.path.basename(client_secret_path)
    docker_name = f"nvr_youtube_reauth_{account_id}"
    
    try:
        # Create YouTubeConfig for host with display
        config = YouTubeConfig(
            encrypt_path=ENCRYPT_PATH,
            hf_repo_id=settings.hf_repo_id,
            hf_token=settings.hf_token,
            encryption_key=settings.yt_encrypt_key,
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
        
        uploader = YouTubeUploader(config)
        
        # Copy client_secret to encrypt folder if not already there
        if os.path.exists(client_secret_path):
            dest = os.path.join(ENCRYPT_PATH, client_filename)
            if not os.path.exists(dest):
                shutil.copy2(client_secret_path, dest)
                logger.info(f"Copied {client_filename} to encrypt folder")
        
        logger.info(f"Starting authentication for account {account_id}...")
        logger.info("This will open a browser window for OAuth.")
        
        # Trigger auth flow
        service = uploader.get_service()
        
        if service:
            logger.info(f"✓ Account {account_id} authenticated successfully!")
            return True
        else:
            logger.error(f"✗ Account {account_id} authentication failed!")
            return False
            
    except Exception as e:
        logger.error(f"✗ Account {account_id} error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main() -> int:
    """Run OAuth authentication flow for all accounts."""
    logger.info("=" * 50)
    logger.info("YouTube OAuth Re-authentication (Multi-Account)")
    logger.info("=" * 50)
    
    accounts = settings.youtube_accounts
    
    if not accounts:
        logger.error("✗ No YouTube accounts configured!")
        logger.error("Set YOUTUBE_CLIENT_SECRET_PATH_1 and YOUTUBE_TOKEN_PATH_1")
        return 1
    
    logger.info(f"Found {len(accounts)} YouTube account(s)")
    
    success_count = 0
    for account in accounts:
        if authenticate_account(account):
            success_count += 1
    
    # Summary
    logger.info("=" * 50)
    logger.info(f"Summary: {success_count}/{len(accounts)} accounts authenticated")
    logger.info("=" * 50)
    
    if success_count == len(accounts):
        logger.info("✓ All accounts authenticated successfully!")
        return 0
    elif success_count > 0:
        logger.warning(f"⚠ {len(accounts) - success_count} account(s) failed")
        return 1
    else:
        logger.error("✗ All authentications failed!")
        return 1


if __name__ == "__main__":
    sys.exit(main())
