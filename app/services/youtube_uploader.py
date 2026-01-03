"""
YouTube Uploader Service
Uploads NVR recordings to YouTube.
"""

import os
import glob
import time
import subprocess
import logging
from datetime import datetime
from typing import List, Optional
from youtube_auto_pub import VideoMetadata
from services.youtube_accounts import YouTubeAccountManager
from utils.naming_conventions import (
    get_youtube_csv_filename,
    format_youtube_csv_line
)

logger = logging.getLogger("yt_upload")


class YouTubeUploaderService:
    """Uploads NVR recordings to YouTube."""
    
    def __init__(
        self,
        recordings_dir: str = "/recordings",
        privacy_status: str = "unlisted",
        delete_after_upload: bool = False,
        scan_interval: int = 60
    ):
        self.recordings_dir = recordings_dir
        self.privacy_status = privacy_status
        self.delete_after_upload = delete_after_upload
        self.scan_interval = scan_interval
        self.manager = YouTubeAccountManager()
        self._running = False
        self.upload_count = 0
    
    def _is_file_stable(self, filepath: str, stable_seconds: int = 15) -> bool:
        """Check if file has stopped being written to."""
        try:
            return (time.time() - os.path.getmtime(filepath)) > stable_seconds
        except OSError:
            return False
    
    def _is_uploaded(self, mp4_path: str) -> bool:
        """Check if file has already been uploaded."""
        if mp4_path.endswith("_uploaded.mp4"):
            return True
        renamed_path = mp4_path.replace(".mp4", "_uploaded.mp4")
        return os.path.exists(renamed_path)
    
    def _parse_video_path(self, mp4_path: str) -> dict:
        """Parse video path to extract metadata."""
        try:
            parts = mp4_path.split(os.sep)
            filename = os.path.splitext(parts[-1])[0].replace("_uploaded", "")
            date_str = parts[-2]
            channel_dir = parts[-3]
            channel = channel_dir.replace("ch", "Channel ")
            
            if len(filename) == 6 and filename.isdigit():
                time_str = f"{filename[:2]}:{filename[2:4]}:{filename[4:6]}"
            else:
                time_str = filename
            
            return {
                "channel": channel,
                "date": date_str,
                "time": time_str,
                "filename": filename
            }
        except Exception:
            return {
                "channel": "Unknown",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "time": "00:00:00",
                "filename": os.path.basename(mp4_path)
            }
    
    def _get_video_duration(self, filepath: str) -> float:
        """Get video duration in seconds using ffprobe."""
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0
    
    def find_pending_files(self) -> List[str]:
        """Find video files pending upload."""
        pattern = os.path.join(self.recordings_dir, "ch*", "*", "*.mp4")
        all_files = glob.glob(pattern)
        
        pending = []
        for f in all_files:
            if self._is_uploaded(f):
                continue
            if not self._is_file_stable(f):
                continue
            if f.endswith(".tmp"):
                continue
            pending.append(f)
        
        return sorted(pending)
    
    def upload_video(self, video_path: str, account_id: int = 1) -> Optional[str]:
        """Upload a single video to YouTube.
        
        Returns:
            Video ID if successful, None otherwise
        """
        account = self.manager.get_account(account_id)
        if not account:
            account = self.manager.accounts[0] if self.manager.accounts else None
        
        if not account:
            logger.error("No YouTube account available")
            return None
        
        service = account.get_service()
        if not service:
            logger.error(f"Account {account.account_id}: No valid service")
            # Create trigger file for main loop
            try:
                with open("need_auth.info", "w") as f:
                    f.write(f"Account {account.account_id}")
            except Exception as e:
                logger.error(f"Failed to create need_auth.info: {e}")
            return None
        
        info = self._parse_video_path(video_path)
        duration = self._get_video_duration(video_path)
        
        # Format duration
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        
        title = f"{info['channel']} - {info['date']} ({info['time']})"
        description = f"Security camera recording\nDate: {info['date']}\nTime: {info['time']}\nDuration: {duration_str}"
        
        metadata = VideoMetadata(
            title=title,
            description=description,
            tags=["NVR", "security", "camera"],
            privacy_status=self.privacy_status,
            category_id="22"
        )
        
        try:
            logger.info(f"Uploading: {title}")
            video_id = account.uploader.upload_video(
                service=service,
                video_path=video_path,
                metadata=metadata
            )
            
            if video_id:
                logger.info(f"Uploaded: https://youtube.com/watch?v={video_id}")
                self._log_to_csv(info, video_id)
                self._finalize_file(video_path)
                self.upload_count += 1
                return video_id
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
        
        return None
    
    def _log_to_csv(self, info: dict, video_id: str):
        """Log upload to per-day CSV."""
        csv_path = get_youtube_csv_filename(self.recordings_dir, info['date'])
        url = f"https://youtube.com/watch?v={video_id}"
        
        # NOTE: Uploader uses 'timestamp' for time column in original code, but format_youtube_csv_line expects just time string?
        # Original: timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Original line: f"{info['channel']},{info['date']},{info['time']},{url},{timestamp}\n"
        # Wait, the 5th column was timestamp?
        # youtube_video_sync.py uses "synced" as 5th column (status).
        # youtube_uploader.py uses timestamp as 5th column?
        # This inconsistency makes commonizing hard if we strict parse.
        
        # Let's check naming_conventions.py:
        # format_youtube_csv_line(..., time_str, url, status="synced", camera_name="Unknown")
        # It puts status in 5th column.
        
        # If I change uploader to use helper, the 5th column becomes "synced" (or I pass timestamp as status).
        # And I can pass "Channel X" as camera name?
        # info['channel'] is "Channel 1" etc.
        
        # Let's align them. Uploader adds "Channel X" as first column too.
        # And uses it as camera column too?
        
        line = format_youtube_csv_line(
            channel_name=info['channel'],
            date_str=info['date'],
            time_str=info['time'], # This is video time
            url=url,
            status=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), # Using timestamp as status?
            camera_name=info['channel'] # Duplicate channel info to camera column for consistency
        )
        
        try:
            with open(csv_path, "a") as f:
                f.write(line)
        except Exception as e:
            logger.error(f"Failed to write CSV: {e}")
    
    def _finalize_file(self, video_path: str):
        """Handle file after successful upload."""
        if self.delete_after_upload:
            try:
                os.remove(video_path)
                logger.info(f"Deleted: {os.path.basename(video_path)}")
            except OSError as e:
                logger.error(f"Failed to delete: {e}")
        else:
            new_path = video_path.replace(".mp4", "_uploaded.mp4")
            try:
                os.rename(video_path, new_path)
            except OSError as e:
                logger.error(f"Failed to rename: {e}")
    
    def run(self):
        """Main upload loop."""
        self._running = True
        logger.info("=" * 50)
        logger.info("YouTube Uploader Service Started")
        logger.info(f"Watching: {self.recordings_dir}")
        logger.info(f"Privacy: {self.privacy_status}")
        logger.info("=" * 50)
        
        while self._running:
            try:
                pending = self.find_pending_files()
                
                if pending:
                    logger.info(f"Found {len(pending)} pending files")
                
                for video_path in pending:
                    if not self._running:
                        break
                    self.upload_video(video_path)
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"Scan error: {e}")
            
            for _ in range(self.scan_interval):
                if not self._running:
                    break
                time.sleep(1)
        
        logger.info("YouTube Uploader Service Stopped")
    
    def stop(self):
        """Stop the upload service."""
        self._running = False
