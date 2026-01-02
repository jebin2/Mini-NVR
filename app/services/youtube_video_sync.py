"""
YouTube Video Sync Service
Fetches videos from YouTube accounts and syncs to CSV.
"""

import os
import glob
import logging
from datetime import datetime
from typing import List, Dict, Set
from services.youtube_accounts import YouTubeAccountManager

logger = logging.getLogger("yt_video_sync")


class YouTubeVideoSync:
    """Fetches videos from all YouTube accounts and syncs to per-day CSV files."""
    
    def __init__(self, recordings_dir: str = "/recordings"):
        self.recordings_dir = recordings_dir
        self.manager = YouTubeAccountManager()
    
    def _read_existing_video_ids(self) -> Set[str]:
        """Read video IDs from all daily CSV files to avoid duplicates."""
        existing_ids = set()
        
        try:
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
            logger.error(f"Failed to read CSV files: {e}")
        
        return existing_ids
    
    def _fetch_videos(self, account, max_results: int = 50) -> List[Dict]:
        """Fetch videos from an account's uploads playlist."""
        service = account.get_service()
        if not service:
            logger.error(f"Account {account.account_id}: No valid service")
            # Create trigger file for main loop
            try:
                with open("app/need_auth.info", "w") as f:
                    f.write(f"Account {account.account_id}")
            except Exception as e:
                logger.error(f"Failed to create need_auth.info: {e}")
                exit(0)
        
        try:
            # Get uploads playlist ID
            channel_response = service.channels().list(
                part="contentDetails,snippet",
                mine=True
            ).execute()
            
            if not channel_response.get("items"):
                return []
            
            channel = channel_response["items"][0]
            channel_name = channel["snippet"]["title"]
            playlist_id = channel["contentDetails"]["relatedPlaylists"]["uploads"]
            
            # Fetch videos from playlist
            videos = []
            next_page_token = None
            
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
                        "channel": channel_name
                    })
                
                next_page_token = response.get("nextPageToken")
                if not next_page_token or len(videos) >= max_results:
                    break
            
            logger.info(f"Account {account.account_id}: Fetched {len(videos)} videos")
            return videos
            
        except Exception as e:
            logger.error(f"Account {account.account_id}: Failed to fetch videos: {e}")
            return []
    
    def _write_to_csv(self, video: Dict):
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
            
            csv_file = os.path.join(self.recordings_dir, f"youtube_uploads_{date_str}.csv")
            channel = video.get("channel", "YouTube")
            url = f"https://youtube.com/watch?v={video['video_id']}"
            line = f"{channel},{date_str},{time_str},{url},synced\n"
            
            with open(csv_file, "a") as f:
                f.write(line)
            
            logger.debug(f"Added: {video['title']} -> {date_str}")
            
        except Exception as e:
            logger.error(f"Failed to write to CSV: {e}")
    
    def sync_to_csv(self) -> int:
        """Sync videos from all accounts to CSV. Returns count of new videos."""
        try:
            existing_ids = self._read_existing_video_ids()
            logger.info(f"Found {len(existing_ids)} existing videos in CSV")
            
            total_new = 0
            
            for account in self.manager.accounts:
                try:
                    videos = self._fetch_videos(account)
                    
                    for video in videos:
                        if video["video_id"] not in existing_ids:
                            self._write_to_csv(video)
                            existing_ids.add(video["video_id"])
                            total_new += 1
                            
                except Exception as e:
                    logger.error(f"Account {account.account_id} failed: {e}")
                    continue
            
            if total_new > 0:
                logger.info(f"Synced {total_new} new videos to CSV")
            else:
                logger.info("All videos already in CSV")
            
            return total_new
            
        except Exception as e:
            logger.error(f"Failed to sync: {e}")
            return 0
