
import os
import csv
import sys
import logging
from datetime import datetime
from youtube_auto_pub import YouTubeConfig, YouTubeUploader

# Setup logger for this module
logger = logging.getLogger("yt_logger")

class YouTubeLogger:
    def __init__(self, credentials_path="ytktclient_secret.json", token_path="ytkttoken.json", recordings_dir="/recordings"):
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.recordings_dir = recordings_dir
        self.csv_path = os.path.join(recordings_dir, "youtube_uploads.csv")
        self.service = None
        
        # Load additional config from Env or Defaults
        self.encrypt_path = os.getenv("ENCRYPT_PATH")
        self.hf_repo_id = os.getenv("HF_REPO_ID")
        self.hf_token = os.getenv("HF_TOKEN")
        self.encryption_key = os.getenv("ENCRYPTION_KEY")
        self.project_path = os.getenv("PROJECT_DIR")
        
        # Initialize Uploader for Auth
        self._init_uploader()

    def _init_uploader(self):
        try:
            # We use existing paths or env vars
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
        except Exception as e:
            logger.error(f"❌ Failed to init YouTubeUploader: {e}")
            self.uploader = None

    def _get_service(self):
        """Get authenticated YouTube API service via youtube_auto_pub."""
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
            logger.error(f"❌ Failed to get YouTube service: {e}")
            return None

    def get_live_video_id(self, broadcast_status="active"):
        """
        Find the current live stream's Video ID.
        Note: This finds *any* active broadcast for the channel.
        If we have multiple keys streaming to the same channel, this might be ambiguous,
        but typically 'active' is what we want.
        """
        service = self._get_service()
        if not service:
            return None

        try:
            # We need to find the broadcast that is currently 'active'
            # broadcastType='all' to find persistent or event-based
            request = service.liveBroadcasts().list(
                part="id,snippet",
                broadcastStatus=broadcast_status,
                broadcastType="all",
                maxResults=5
            )
            response = request.execute()

            items = response.get('items', [])
            if not items:
                logger.info("ℹ️ No active live broadcasts found.")
                return None
            
            # Return the first one found
            video_id = items[0]['id']
            title = items[0]['snippet']['title']
            logger.info(f"✅ Found active broadcast: {title} ({video_id})")
            return video_id

        except Exception as e:
            logger.error(f"❌ Failed to fetch live broadcast ID: {e}")
            return None

    def log_live(self, channel_name, start_time, video_id):
        """
        Log live stream start to CSV.
        Format: Channel,Date,TimeRange,URL,Timestamp
        For Live: TimeRange = "StartTime-..."
        Timestamp column = "yt live"
        """
        if not video_id:
            return

        date_str = start_time.strftime("%Y-%m-%d")
        time_str = start_time.strftime("%H:%M:%S")
        time_range = f"{time_str}-..."
        youtube_url = f"https://youtube.com/watch?v={video_id}"
        timestamp_col = "yt live"

        self._write_csv(channel_name, date_str, time_range, youtube_url, timestamp_col)

    def log_vod(self, channel_name, start_time, end_time, video_id):
        """
        Log VOD (completed stream) to CSV.
        Format: Channel,Date,TimeRange,URL,Timestamp
        Timestamp column = "yt vod" (or current time if preferred, but user said 'uploaded links')
        """
        if not video_id:
            return

        date_str = start_time.strftime("%Y-%m-%d")
        start_str = start_time.strftime("%H:%M:%S")
        end_str = end_time.strftime("%H:%M:%S")
        time_range = f"{start_str}-{end_str}"
        youtube_url = f"https://youtube.com/watch?v={video_id}"
        timestamp_col = "yt vod" # distinguishing from uploader's "2025-..."

        self._write_csv(channel_name, date_str, time_range, youtube_url, timestamp_col)

    def _write_csv(self, channel, date, time_range, url, status_col):
        """Append line to CSV."""
        try:
            line = f"{channel},{date},{time_range},{url},{status_col}\n"
            with open(self.csv_path, 'a') as f:
                f.write(line)
            logger.info(f"📝 Logged to CSV: {line.strip()}")
        except Exception as e:
            logger.error(f"❌ Failed to write to CSV: {e}")
