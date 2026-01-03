"""
YouTube Uploader Service
Uploads NVR recordings to YouTube using CSV-based tracking.
Batches consecutive TS segments by channel and uploads when threshold is reached.
Processes channels round-robin style - one batch per channel per iteration.
"""

import os
import time
import tempfile
import subprocess
import logging
from datetime import datetime
from typing import List, Optional, Dict
from youtube_auto_pub import VideoMetadata
from services.youtube_accounts import YouTubeAccountManager
from utils.processed_videos_csv import (
    get_pending_by_channel,
    mark_uploaded,
    delete_uploaded_files
)
from core.config import settings

logger = logging.getLogger("yt_upload")


class YouTubeUploaderService:
    """Uploads NVR recordings to YouTube with batch support."""
    
    def __init__(
        self,
        recordings_dir: str = "/recordings",
        privacy_status: str = "unlisted",
        delete_after_upload: bool = False,
        batch_size_mb: int = 50
    ):
        self.recordings_dir = recordings_dir
        self.privacy_status = privacy_status
        self.delete_after_upload = delete_after_upload
        self.batch_size_mb = batch_size_mb
        self.manager = YouTubeAccountManager()
        self._running = False
        self.upload_count = 0
    
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
    
    def _format_duration(self, seconds: float) -> str:
        """Format duration as HH:MM:SS or MM:SS."""
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
    
    def _concatenate_segments(self, ts_paths: List[str], output_path: str) -> bool:
        """
        Concatenate multiple TS segments into a single MP4 file.
        Returns True if successful.
        """
        if not ts_paths:
            return False
        
        # Create concat file list
        concat_file = output_path + ".txt"
        try:
            with open(concat_file, "w") as f:
                for ts_path in ts_paths:
                    # Escape single quotes in path
                    escaped_path = ts_path.replace("'", "'\\''")
                    f.write(f"file '{escaped_path}'\n")
            
            # FFmpeg concat demuxer
            cmd = [
                settings.ffmpeg_bin,
                "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", concat_file,
                "-c", "copy",  # No re-encoding
                "-movflags", "+faststart",
                output_path
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode != 0:
                logger.error(f"Concat failed: {result.stderr[:500]}")
                return False
            
            return os.path.exists(output_path) and os.path.getsize(output_path) > 0
            
        except Exception as e:
            logger.error(f"Concatenation error: {e}")
            return False
        finally:
            # Clean up concat file
            if os.path.exists(concat_file):
                try:
                    os.remove(concat_file)
                except OSError:
                    pass
    
    def _parse_batch_metadata(self, rows: List[dict]) -> dict:
        """Parse metadata from a batch of video rows."""
        if not rows:
            return {}
        
        first_path = rows[0]["video_path"]
        last_path = rows[-1]["video_path"]
        
        # Parse: ch1/2026-01-03/193627.ts
        parts = first_path.split("/")
        channel = parts[0].replace("ch", "Channel ") if len(parts) >= 1 else "Unknown"
        date_str = parts[1] if len(parts) >= 2 else datetime.now().strftime("%Y-%m-%d")
        
        # Extract start/end times from filenames
        first_filename = os.path.splitext(os.path.basename(first_path))[0]
        last_filename = os.path.splitext(os.path.basename(last_path))[0]
        
        start_time = f"{first_filename[:2]}:{first_filename[2:4]}:{first_filename[4:6]}" if len(first_filename) == 6 else first_filename
        end_time = f"{last_filename[:2]}:{last_filename[2:4]}:{last_filename[4:6]}" if len(last_filename) == 6 else last_filename
        
        return {
            "channel": channel,
            "date": date_str,
            "start_time": start_time,
            "end_time": end_time,
            "segment_count": len(rows)
        }
    
    def _upload_batch(self, rows: List[dict], account_id: int = 1) -> Optional[str]:
        """
        Upload a batch of TS segments to YouTube.
        Returns video ID if successful.
        """
        if not rows:
            return None
        
        # Get full paths
        ts_paths = [
            os.path.join(self.recordings_dir, row["video_path"])
            for row in rows
        ]
        
        # Verify all files exist
        for path in ts_paths:
            if not os.path.exists(path):
                logger.warning(f"Missing file: {path}")
                return None
        
        # Get YouTube account
        account = self.manager.get_account(account_id)
        if not account:
            account = self.manager.accounts[0] if self.manager.accounts else None
        
        if not account:
            logger.error("No YouTube account available")
            return None
        
        service = account.get_service()
        if not service:
            logger.error(f"Account {account.account_id}: No valid service")
            try:
                with open("need_auth.info", "w") as f:
                    f.write(f"Account {account.account_id}")
            except Exception as e:
                logger.error(f"Failed to create need_auth.info: {e}")
            return None
        
        # Create temp MP4
        info = self._parse_batch_metadata(rows)
        temp_dir = tempfile.gettempdir()
        temp_mp4 = os.path.join(
            temp_dir,
            f"nvr_upload_{info['date']}_{info['start_time'].replace(':', '')}.mp4"
        )
        
        logger.info(
            f"Concatenating {len(ts_paths)} segments: "
            f"{info['start_time']} - {info['end_time']}"
        )
        
        if not self._concatenate_segments(ts_paths, temp_mp4):
            logger.error("Failed to concatenate segments")
            return None
        
        try:
            # Get duration
            duration = self._get_video_duration(temp_mp4)
            duration_str = self._format_duration(duration)
            
            # Build metadata
            title = f"{info['channel']} - {info['date']} ({info['start_time']} - {info['end_time']})"
            description = (
                f"Security camera recording\n"
                f"Date: {info['date']}\n"
                f"Time: {info['start_time']} - {info['end_time']}\n"
                f"Duration: {duration_str}\n"
                f"Segments: {info['segment_count']}"
            )
            
            metadata = VideoMetadata(
                title=title,
                description=description,
                tags=["NVR", "security", "camera"],
                privacy_status=self.privacy_status,
                category_id="22"
            )
            
            logger.info(f"Uploading: {title}")
            
            video_id = account.uploader.upload_video(
                service=service,
                video_path=temp_mp4,
                metadata=metadata
            )
            
            if video_id:
                logger.info(f"Uploaded: https://youtube.com/watch?v={video_id}")
                
                # Mark all segments as uploaded in CSV
                video_paths = [row["video_path"] for row in rows]
                mark_uploaded(video_paths)
                
                self.upload_count += 1
                return video_id
                
        except Exception as e:
            logger.error(f"Upload failed: {e}")
        finally:
            # Clean up temp MP4
            if os.path.exists(temp_mp4):
                try:
                    os.remove(temp_mp4)
                except OSError:
                    pass
        
        return None
    
    def _get_batch_for_channel(self, rows: List[dict]) -> Optional[List[dict]]:
        """
        Get a batch ready for upload from a channel's pending rows.
        Returns batch if cumulative size >= threshold, None otherwise.
        """
        batch = []
        total_size = 0.0
        
        for row in rows:
            size = float(row.get("size_mb", 0))
            batch.append(row)
            total_size += size
            
            if total_size >= self.batch_size_mb:
                return batch
        
        # Not enough for a batch yet
        return None
    
    def run(self):
        """Main upload loop - runs continuously, round-robin through channels."""
        self._running = True
        logger.info("=" * 50)
        logger.info("YouTube Uploader Service Started")
        logger.info(f"Watching: {self.recordings_dir}")
        logger.info(f"Privacy: {self.privacy_status}")
        logger.info(f"Batch size: {self.batch_size_mb}MB")
        logger.info("=" * 50)
        
        while self._running:
            try:
                pending_by_channel = get_pending_by_channel()
                uploaded_any = False
                
                # Round-robin through channels
                for channel in sorted(pending_by_channel.keys()):
                    if not self._running:
                        break
                    
                    rows = pending_by_channel[channel]
                    batch = self._get_batch_for_channel(rows)
                    
                    if batch:
                        logger.info(f"Processing {channel}: {len(batch)} segments")
                        self._upload_batch(batch)
                        uploaded_any = True
                        # Move to next channel after one batch
                
                # Delete uploaded files if configured
                if self.delete_after_upload:
                    delete_uploaded_files(self.recordings_dir)
                
                # If nothing was uploaded, short sleep before next scan
                if not uploaded_any:
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"Scan error: {e}")
                time.sleep(5)
        
        logger.info("YouTube Uploader Service Stopped")
    
    def stop(self):
        """Stop the upload service."""
        self._running = False
