"""
YouTube Accounts Module
Shared account discovery and YouTube API service management.
"""

import os
import logging
from typing import List, Dict, Optional, Any
from youtube_auto_pub import YouTubeConfig, YouTubeUploader

logger = logging.getLogger("yt_accounts")


from core.config import settings

def discover_accounts() -> List[Dict]:
    """
    Discover all configured YouTube accounts from settings.
    """
    return settings.youtube_accounts


class YouTubeAccount:
    """Single YouTube account wrapper."""
    
    def __init__(self, account_id: int, client_secret: str, token_path: str):
        self.account_id = account_id
        self.client_secret = client_secret
        self.token_path = token_path
        self.service = None
        self.uploader = None
        self.channel_name = None
        
        # Shared config from env
        # Shared config from settings
        self.encrypt_path = settings.youtube_encrypt_path
        self.hf_repo_id = settings.hf_repo_id
        self.hf_token = settings.hf_token
        self.encryption_key = settings.yt_encrypt_key
        self.project_path = settings.project_dir
        
        self._init_uploader()
    
    def _init_uploader(self):
        """Initialize YouTube uploader for this account."""
        try:
            config = YouTubeConfig(
                client_secret_filename=self.client_secret,
                token_filename=self.token_path,
                headless_mode=True,
                encrypt_path=self.encrypt_path,
                hf_repo_id=self.hf_repo_id,
                hf_token=self.hf_token,
                encryption_key=self.encryption_key,
                project_path=self.project_path
            )
            self.uploader = YouTubeUploader(config)
            logger.debug(f"Account {self.account_id}: Uploader initialized")
        except Exception as e:
            logger.error(f"Account {self.account_id}: Failed to init uploader: {e}")
            self.uploader = None
    
    def get_service(self, skip_auth_flow: bool = True) -> Optional[Any]:
        """Get authenticated YouTube API service.
        
        Args:
            skip_auth_flow: If True, return None instead of triggering browser auth
        
        Returns:
            YouTube API service or None
        """
        if self.service:
            return self.service
        
        if not self.uploader:
            self._init_uploader()
            if not self.uploader:
                return None
        
        try:
            self.service = self.uploader.get_service(skip_auth_flow=skip_auth_flow)
            if self.service:
                logger.info(f"Account {self.account_id}: Authenticated")
            return self.service
        except Exception as e:
            logger.error(f"Account {self.account_id}: Failed to get service: {e}")
            return None
    
    def get_channel_name(self) -> Optional[str]:
        """Get the channel name for this account."""
        if self.channel_name:
            return self.channel_name
        
        service = self.get_service()
        if not service:
            return None
        
        try:
            response = service.channels().list(part="snippet", mine=True).execute()
            if response.get("items"):
                self.channel_name = response["items"][0]["snippet"]["title"]
                return self.channel_name
        except Exception as e:
            logger.error(f"Account {self.account_id}: Failed to get channel name: {e}")
        
        return f"Account{self.account_id}"


class YouTubeAccountManager:
    """Manages all configured YouTube accounts."""
    
    def __init__(self):
        self.accounts: List[YouTubeAccount] = []
        self._discover_and_init()
    
    def _discover_and_init(self):
        """Discover accounts and initialize them."""
        account_configs = discover_accounts()
        
        if not account_configs:
            logger.warning("No YouTube accounts configured")
            return
        
        logger.info(f"Found {len(account_configs)} YouTube account(s)")
        
        for config in account_configs:
            account = YouTubeAccount(
                account_id=config["id"],
                client_secret=config["client_secret"],
                token_path=config["token_path"]
            )
            self.accounts.append(account)
    
    def get_account(self, account_id: int) -> Optional[YouTubeAccount]:
        """Get a specific account by ID."""
        for account in self.accounts:
            if account.account_id == account_id:
                return account
        return None
    
    def get_first_valid_service(self) -> Optional[Any]:
        """Get the first account that has a valid service."""
        for account in self.accounts:
            service = account.get_service()
            if service:
                return service
        return None
