"""
YouTube Video Sync Service
Fetches all videos from multiple YouTube accounts and syncs to CSV.
"""

import os
import logging
from datetime import datetime
from youtube_auto_pub import YouTubeConfig, YouTubeUploader

logger = logging.getLogger("yt_video_sync")


def discover_youtube_accounts():
    """
    Discover all configured YouTube accounts from environment variables.
    Looks for YOUTUBE_CLIENT_SECRET_PATH_N and YOUTUBE_TOKEN_PATH_N pairs.
    """
    accounts = []
    idx = 1
    
    while True:
        client_secret = os.getenv(f"YOUTUBE_CLIENT_SECRET_PATH_{idx}")
        token_path = os.getenv(f"YOUTUBE_TOKEN_PATH_{idx}")
        
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
        client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")
        token_path = os.getenv("YOUTUBE_TOKEN")
        accounts.append({
            "id": 1,
            "client_secret": client_secret,
            "token_path": token_path
        })
    
    return accounts


class YouTubeAccountSync:
    """Syncs videos from a single YouTube account."""

    def __init__(self, account_id, credentials_path, token_path, csv_path):
        self.account_id = account_id
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.csv_path = csv_path
        self.service = None
        self.uploader = None
        self.channel_name = None

        # Shared config from env
        self.encrypt_path = os.getenv("YOUTUBE_ENCRYPT_PATH")
        self.hf_repo_id = os.getenv("HF_REPO_ID")
        self.hf_token = os.getenv("HF_TOKEN")
        self.encryption_key = os.getenv("YT_ENCRYP_KEY")
        self.project_path = os.getenv("PROJECT_DIR")

        self._init_uploader()

    def _init_uploader(self):
        """Initialize YouTube uploader for authentication."""
        try:
            config = YouTubeConfig(
                client_secret_filename=self.credentials_path,
                token_filename=self.token_path,
                headless_mode=True,
                encrypt_path=self.encrypt_path,
                hf_repo_id=self.hf_repo_id,
                hf_token=self.hf_token,
                encryption_key=self.encryption_key,
                project_path=self.project_path
            )
            self.uploader = YouTubeUploader(config)
            logger.info(f"✅ Account {self.account_id}: Initialized uploader")
        except Exception as e:
            logger.error(f"❌ Account {self.account_id}: Failed to init uploader: {e}")
            self.uploader = None

    def _get_service(self):
        """Get authenticated YouTube API service."""
        if self.service:
            return self.service

        if not self.uploader:
            self._init_uploader()
            if not self.uploader:
                return None

        try:
            self.service = self.uploader.get_service()
            return self.service
        except Exception as e:
            logger.error(f"❌ Account {self.account_id}: Failed to get service: {e}")
            return None

    def _get_channel_info(self):
        """Get channel name and uploads playlist ID."""
        service = self._get_service()
        if not service:
            return None, None

        try:
            request = service.channels().list(
                part="snippet,contentDetails",
                mine=True
            )
            response = request.execute()

            items = response.get("items", [])
            if not items:
                logger.error(f"❌ Account {self.account_id}: No channel found")
                return None, None

            channel = items[0]
            self.channel_name = channel["snippet"]["title"]
            uploads_playlist = channel["contentDetails"]["relatedPlaylists"]["uploads"]
            
            logger.info(f"📺 Account {self.account_id}: Channel '{self.channel_name}'")
            return self.channel_name, uploads_playlist

        except Exception as e:
            logger.error(f"❌ Account {self.account_id}: Failed to get channel: {e}")
            return None, None

    def fetch_videos(self, max_results=50):
        """Fetch videos from the uploads playlist."""
        channel_name, playlist_id = self._get_channel_info()
        if not playlist_id:
            return []

        service = self._get_service()
        videos = []
        next_page_token = None

        try:
            while True:
                request = service.playlistItems().list(
                    part="snippet,contentDetails",
                    playlistId=playlist_id,
                    maxResults=min(50, max_results - len(videos)),
                    pageToken=next_page_token
                )
                response = request.execute()

                for item in response.get("items", []):
                    snippet = item["snippet"]
                    videos.append({
                        "video_id": snippet["resourceId"]["videoId"],
                        "title": snippet.get("title", "Untitled"),
                        "published_at": snippet.get("publishedAt", ""),
                        "channel": channel_name or f"Account{self.account_id}"
                    })

                next_page_token = response.get("nextPageToken")
                if not next_page_token or len(videos) >= max_results:
                    break

            logger.info(f"📹 Account {self.account_id}: Fetched {len(videos)} videos")
            return videos

        except Exception as e:
            logger.error(f"❌ Account {self.account_id}: Failed to fetch videos: {e}")
            return []


class YouTubeVideoSync:
    """Syncs videos from all configured YouTube accounts to CSV."""

    def __init__(self, recordings_dir="/recordings"):
        self.recordings_dir = recordings_dir
        self.accounts = []
        
        # Discover and initialize all accounts
        account_configs = discover_youtube_accounts()
        logger.info(f"🔍 Found {len(account_configs)} YouTube account(s)")
        
        for acc in account_configs:
            self.accounts.append(YouTubeAccountSync(
                account_id=acc["id"],
                credentials_path=acc["client_secret"],
                token_path=acc["token_path"],
                csv_path=self.csv_path
            ))

    def _read_existing_video_ids(self):
        """Read video IDs from all daily CSV files to avoid duplicates."""
        existing_ids = set()

        try:
            # Scan all youtube_uploads_*.csv files
            import glob
            pattern = os.path.join(self.recordings_dir, "youtube_uploads_*.csv")
            for csv_file in glob.glob(pattern):
                with open(csv_file, "r") as f:
                    for line in f:
                        if "youtube.com/watch?v=" in line:
                            parts = line.split("youtube.com/watch?v=")
                            if len(parts) > 1:
                                video_id = parts[1].split(",")[0].split("&")[0].strip()
                                existing_ids.add(video_id)
        except Exception as e:
            logger.error(f"❌ Failed to read CSV files: {e}")

        return existing_ids

    def sync_to_csv(self):
        """Sync videos from all accounts to CSV."""
        try:
            existing_ids = self._read_existing_video_ids()
            logger.info(f"📄 Found {len(existing_ids)} existing videos in CSV")

            total_new = 0
            
            for account in self.accounts:
                videos = account.fetch_videos()
                
                for video in videos:
                    if video["video_id"] not in existing_ids:
                        self._write_to_csv(video)
                        existing_ids.add(video["video_id"])  # Avoid duplicates across accounts
                        total_new += 1

            if total_new > 0:
                logger.info(f"✅ Synced {total_new} new videos to CSV")
            else:
                logger.info("ℹ️ All videos already in CSV")

            return total_new

        except Exception as e:
            logger.error(f"❌ Failed to sync: {e}")
            return 0

    def _write_to_csv(self, video):
        """Write a video entry to date-specific CSV file."""
        try:
            published_at = video.get("published_at", "")
            if published_at:
                try:
                    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                    date_str = dt.strftime("%Y-%m-%d")
                    time_str = dt.strftime("%H:%M:%S")
                except:
                    date_str = published_at[:10] if len(published_at) >= 10 else "unknown"
                    time_str = "00:00:00"
            else:
                date_str = "unknown"
                time_str = "00:00:00"

            # Per-day CSV file
            csv_file = os.path.join(self.recordings_dir, f"youtube_uploads_{date_str}.csv")
            
            channel = video.get("channel", "YouTube")
            url = f"https://youtube.com/watch?v={video['video_id']}"
            line = f"{channel},{date_str},{time_str},{url},synced\n"

            with open(csv_file, "a") as f:
                f.write(line)

            logger.debug(f"📝 Added: {video['title']} -> {date_str}")

        except Exception as e:
            logger.error(f"❌ Failed to write to CSV: {e}")
