#!/usr/bin/env python3
"""
YouTube NVR Uploader Service

Standalone service that watches Mini-NVR recordings directory and uploads
MP4 files to YouTube. Runs on host machine (not in Docker) to enable
Neko browser automation for OAuth and automatic re-authentication.

Configuration is read from Mini-NVR's .env file (same env vars as Docker).
"""

import glob
import os
import signal
import sys
import time
import subprocess
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict

# Try to import youtube_auto_pub - either installed or from sibling directory
try:
    from youtube_auto_pub import YouTubeConfig, YouTubeUploader, VideoMetadata
except ImportError:
    # Fallback: try loading from sibling git directory
    youtube_auto_pub_path = os.path.expanduser("~/git/youtube_auto_pub")
    if os.path.isdir(youtube_auto_pub_path):
        sys.path.insert(0, youtube_auto_pub_path)
        from youtube_auto_pub import YouTubeConfig, YouTubeUploader, VideoMetadata
    else:
        print("[NVR Uploader] ✗ youtube_auto_pub not found!")
        print("[NVR Uploader] Install with: pip install git+https://github.com/jebin2/youtube_auto_pub.git")
        print(f"[NVR Uploader] Or ensure it exists at: {youtube_auto_pub_path}")
        sys.exit(1)


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


class VideoBatch:
    """Represents a collection of video files to be merged and uploaded together."""
    def __init__(self, channel: str, date: str, files: List[str], part_number: int = 1, total_parts: int = 1):
        self.channel = channel
        self.date = date
        self.files = sorted(files)  # Ensure chronological order
        self.part_number = part_number
        self.total_parts = total_parts
        self.merged_path: Optional[str] = None
        
    @property
    def id(self) -> str:
        return f"{self.channel}_{self.date}_part{self.part_number}_of_{self.total_parts}"

# -----------------------------------------------------------------------------
# Monkeypatch YouTubeUploader.upload_video to propagate exceptions
# -----------------------------------------------------------------------------
from googleapiclient.http import MediaFileUpload

def monkeypatched_upload_video(self, service, video_path, metadata, thumbnail_path=None):
    """
    Monkeypatched version of upload_video that allows exceptions to propagate
    so we can catch 'uploadLimitExceeded'.
    """
    request_body = {
        'snippet': {
            'categoryId': metadata.category_id,
            'title': metadata.title[:100],  # Max 100 chars
            'description': metadata.description,
            'tags': metadata.tags,
        },
        'status': {
            'privacyStatus': metadata.privacy_status,
            'madeForKids': metadata.made_for_kids,
            'selfDeclaredMadeForKids': metadata.made_for_kids,
        }
    }
    
    if metadata.publish_at:
        request_body['status']['publishAt'] = metadata.publish_at

    # Upload the video
    media_file = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = service.videos().insert(
        part='snippet,status',
        body=request_body,
        media_body=media_file
    )

    print(f"[Uploader] Uploading video: {video_path}")
    response = None
    
    # Intentionally removed the try/except block here
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f'[Uploader] Uploaded {int(status.progress() * 100)}% of the video.')

    video_id = response['id']
    print(f'[Uploader] Video uploaded successfully with ID: {video_id}')

    # Upload thumbnail if provided
    if thumbnail_path and video_id:
        self.set_thumbnail(service, video_id, thumbnail_path)

    return video_id

# Apply the monkeypatch
if 'YouTubeUploader' in globals():
    YouTubeUploader.upload_video = monkeypatched_upload_video
elif 'youtube_auto_pub' in sys.modules:
    sys.modules['youtube_auto_pub'].YouTubeUploader.upload_video = monkeypatched_upload_video
# -----------------------------------------------------------------------------


class NVRUploaderService:
    """
    Background service to upload Mini-NVR recordings to YouTube.
    
    Watches for MP4 files, batches them by channel/date, merges them,
    and uploads the result with detailed timestamps.
    """
    
    # Safe limit: 11.5 hours in seconds (11.5 * 3600 = 41400)
    MAX_DURATION_SECONDS = 41400
    
    def __init__(
        self,
        recordings_dir: str,
        client_secret_path: str,
        token_path: str,
        encrypt_path: str = "./encrypt",
        privacy_status: str = "unlisted",
        delete_after_upload: bool = False,
        scan_interval: int = 60,
        hf_repo_id: str = "jebin2/Data",
        hf_token: Optional[str] = None,
        encryption_key: Optional[str] = None,
        log_file: Optional[str] = None,
    ):
        self.recordings_dir = os.path.abspath(recordings_dir)
        self.client_secret_path = client_secret_path
        self.token_path = token_path
        self.encrypt_path = encrypt_path
        self.privacy_status = privacy_status
        self.delete_after_upload = delete_after_upload
        self.scan_interval = scan_interval
        self.hf_repo_id = hf_repo_id
        self.hf_token = hf_token
        self.encryption_key = encryption_key
        self.log_file = log_file

        self._running = False
        self._uploader: Optional[YouTubeUploader] = None
        self._service = None
        
        # Statistics
        self.upload_count = 0
        self.last_upload_time: Optional[float] = None
        self.last_error: Optional[str] = None
        
        # Docker detection
        self._is_docker = self._detect_docker()
        self._reauth_triggered = False
        
        self._check_dependencies()
    
    def _detect_docker(self) -> bool:
        """Detect if running inside Docker container."""
        # Check for /.dockerenv file
        if os.path.exists('/.dockerenv'):
            return True
        # Check cgroup
        try:
            with open('/proc/1/cgroup', 'rt') as f:
                return 'docker' in f.read()
        except Exception:
            pass
        return False
    
    def _trigger_ssh_reauth(self) -> bool:
        """
        SSH to host machine to trigger reauth.py for OAuth.
        This is used when running in Docker and auth fails.
        
        Returns:
            True if reauth was triggered successfully, False otherwise.
        """
        ssh_user = os.environ.get('SSH_HOST_USER', 'jebin')
        project_dir = os.environ.get('PROJECT_DIR', '/home/jebin/git/Mini-NVR')
        python_path = f"/home/{ssh_user}/.pyenv/versions/Mini-NVR_env/bin/python"
        
        self.log(f"[NVR Uploader] 🔐 Triggering SSH reauth on host...")
        self.log(f"[NVR Uploader]    User: {ssh_user}, Project: {project_dir}")
        
        cmd = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'BatchMode=yes',
            '-o', 'ConnectTimeout=10',
            f'{ssh_user}@host.docker.internal',
            f'{python_path} {project_dir}/scripts/reauth.py'
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200  # 20 minute timeout for OAuth flow
            )
            
            if result.returncode == 0:
                self.log("[NVR Uploader] ✓ SSH reauth completed successfully!")
                return True
            else:
                self.log(f"[NVR Uploader] ✗ SSH reauth failed (exit {result.returncode})")
                if result.stderr:
                    self.log(f"[NVR Uploader]   stderr: {result.stderr[:200]}")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("[NVR Uploader] ✗ SSH reauth timed out (5 min)")
            return False
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ SSH reauth error: {e}")
            return False
    
    def log(self, message: str):
        """Log message to stdout and optionally to file."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = f"{timestamp} {message}"
        print(log_line, flush=True)
        
        if self.log_file:
            try:
                with open(self.log_file, 'a') as f:
                    f.write(log_line + "\n")
            except Exception:
                pass

    # Stale merged file cleanup threshold (10 minutes)
    STALE_MERGED_FILE_SECONDS = 600
    
    def _cleanup_stale_merged_files(self, force: bool = False):
        """
        Clean up orphaned/stale merged_*.mp4 files.
        
        These temp files can be left behind if the service crashes or is killed
        during a merge or upload operation.
        
        Args:
            force: If True, delete all merged files regardless of age (startup cleanup).
                   If False, only delete files older than STALE_MERGED_FILE_SECONDS.
        """
        pattern = os.path.join(self.recordings_dir, "merged_*.mp4")
        merged_files = glob.glob(pattern)
        
        if not merged_files:
            return
            
        cleaned = 0
        for merged_file in merged_files:
            try:
                file_age = time.time() - os.path.getmtime(merged_file)
                
                # Delete if forced (startup) or if file is stale (>10 min old)
                if force or file_age > self.STALE_MERGED_FILE_SECONDS:
                    file_size_mb = os.path.getsize(merged_file) / (1024 * 1024)
                    os.remove(merged_file)
                    age_str = f"{int(file_age // 60)}m" if file_age >= 60 else f"{int(file_age)}s"
                    self.log(f"[NVR Uploader] 🧹 Cleaned orphaned merged file: {os.path.basename(merged_file)} ({file_size_mb:.1f}MB, age: {age_str})")
                    cleaned += 1
            except OSError as e:
                self.log(f"[NVR Uploader] ⚠ Failed to clean merged file {merged_file}: {e}")
        
        if cleaned > 0:
            self.log(f"[NVR Uploader] 🧹 Cleaned {cleaned} orphaned merged file(s)")

    def _check_dependencies(self):
        """Check if FFmpeg is available."""
        try:
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run(["ffprobe", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log("[NVR Uploader] ✗ FFmpeg or FFprobe not found in path! Merging will fail.")
            sys.exit(1)
            
    def _init_uploader(self) -> bool:
        """Initialize the YouTube uploader with config."""
        try:
            
            # When running in Docker, use headless mode (no browser automation)
            # Browser-based OAuth is triggered via SSH to host
            config = YouTubeConfig(
                encrypt_path=self.encrypt_path,
                hf_repo_id=self.hf_repo_id,
                hf_token=self.hf_token,
                encryption_key=self.encryption_key,
                # Docker: headless mode, no browser automation
                # Host: can use Neko browser
                is_docker=self._is_docker,
                has_display=not self._is_docker,
                headless_mode=self._is_docker,
                docker_name="nvr_youtube_auto_pub",
                google_email=os.environ.get("GOOGLE_EMAIL"),
                google_password=os.environ.get("GOOGLE_PASSWORD"),
                project_path=os.environ.get("PROJECT_DIR"),
                client_secret_filename=os.path.basename(self.client_secret_path),
                token_filename=os.path.basename(self.token_path)
            )
            
            self._uploader = YouTubeUploader(config)
            mode = "Docker (headless)" if self._is_docker else "Host (with display)"
            self.log(f"[NVR Uploader] ✓ YouTube uploader initialized [{mode}]")
            return True
            
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Failed to initialize uploader: {e}")
            self.last_error = str(e)
            return False
    
    def _get_service(self, allow_ssh_reauth: bool = True):
        """Get authenticated YouTube API service.
        
        Args:
            allow_ssh_reauth: If True and running in Docker, trigger SSH reauth on failure.
        """
        if self._service is not None:
            return self._service
        
        if self._uploader is None:
            if not self._init_uploader():
                return None
        
        try:
            self._service = self._uploader.get_service()
            self.log("[NVR Uploader] ✓ YouTube API service authenticated")
            self._reauth_triggered = False  # Reset on successful auth
            return self._service
            
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Failed to get YouTube service: {e}")
            self.last_error = str(e)
            self._service = None
            
            # In Docker: trigger SSH reauth on host
            if self._is_docker and allow_ssh_reauth and not self._reauth_triggered:
                self.log("[NVR Uploader] 🔐 Running in Docker, triggering SSH reauth...")
                self._reauth_triggered = True
                
                if self._trigger_ssh_reauth():
                    self.log("[NVR Uploader] 🔄 Reauth complete, retrying authentication...")
                    # Reset uploader to reload credentials
                    self._uploader = None
                    time.sleep(2)  # Brief pause
                    return self._get_service(allow_ssh_reauth=False)  # Retry once
                else:
                    self.log("[NVR Uploader] ⚠ SSH reauth failed. Manual auth may be needed.")
                    self.log(f"[NVR Uploader]   Run: python3 scripts/reauth.py")
            
            return None

    def _is_uploaded(self, mp4_path: str) -> bool:
        """Check if MP4 has been uploaded."""
        # 1. Check if this IS an already uploaded file
        if mp4_path.endswith("_uploaded.mp4"):
            return True
            
        # 2. Check if the uploaded version exists (renamed)
        renamed_path = mp4_path.replace(".mp4", "_uploaded.mp4")
        if os.path.exists(renamed_path):
            return True

        # 3. Check legacy marker files (backward compatibility)
        marker_path = mp4_path + ".uploaded"
        return os.path.exists(marker_path)
    
    def _finalize_batch(self, batch: VideoBatch):
        """Handle files after successful upload (rename or delete)."""
        for mp4_path in batch.files:
            if self.delete_after_upload:
                try:
                    os.remove(mp4_path)
                    self.log(f"[NVR Uploader] 🗑 Deleted local file: {os.path.basename(mp4_path)}")
                except OSError as e:
                    self.log(f"[NVR Uploader] ! Failed to delete {mp4_path}: {e}")
            else:
                # Rename to _uploaded.mp4
                new_path = mp4_path.replace(".mp4", "_uploaded.mp4")
                try:
                    os.rename(mp4_path, new_path)
                    # self.log(f"[NVR Uploader] ✏ Renamed to: {os.path.basename(new_path)}")
                except OSError as e:
                    self.log(f"[NVR Uploader] ! Failed to rename {mp4_path}: {e}")

        # Delete the merged file if it exists
        if batch.merged_path and os.path.exists(batch.merged_path):
            try:
                os.remove(batch.merged_path)
                self.log(f"[NVR Uploader] 🧹 Removed temporary merged file")
            except OSError:
                pass

    def _is_file_stable(self, filepath: str, stable_seconds: int = 15) -> bool:
        """Check if file has stopped being written to."""
        try:
            return (time.time() - os.path.getmtime(filepath)) > stable_seconds
        except OSError:
            return False

    def _log_upload_to_csv(self, batch: VideoBatch, video_id: str):
        """Log successful upload to CSV file."""
        csv_path = os.path.join(self.recordings_dir, "youtube_uploads.csv")
        youtube_url = f"https://youtube.com/watch?v={video_id}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        try:
            with open(csv_path, 'a') as f:
                # Get info from the single file
                info = self._parse_video_path(batch.files[0])
                
                # CSV Format: Channel, Date, Time, YouTubeURL, UploadTimestamp
                # e.g. "Channel 1,2025-05-20,08:00:00,https://youtube.com/watch?v=xxx,2025-05-21 10:00:00"
                line = f"{batch.channel},{batch.date},{info['time']},{youtube_url},{timestamp}\n"
                f.write(line)
                    
            self.log(f"[NVR Uploader] 📝 Logged to CSV: {video_id}")
        except Exception as e:
            self.log(f"[NVR Uploader] ! Failed to write log CSV: {e}")
            
    def _parse_video_path(self, mp4_path: str) -> dict:
        """Parse video path to extract metadata."""
        try:
            parts = mp4_path.split(os.sep)
            filename = os.path.splitext(parts[-1])[0]
            date_str = parts[-2]
            channel_dir = parts[-3]
            
            channel = channel_dir.replace("ch", "Channel ")
            
            # Remove _uploaded suffix if present for parsing
            clean_filename = filename.replace("_uploaded", "")
            
            # Filename is usually TIME (041115)
            if len(clean_filename) == 6 and clean_filename.isdigit():
                 time_str = f"{clean_filename[:2]}:{clean_filename[2:4]}:{clean_filename[4:6]}"
            else:
                 time_str = clean_filename
            
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
            "ffprobe", 
            "-v", "error", 
            "-show_entries", "format=duration", 
            "-of", "default=noprint_wrappers=1:nokey=1", 
            filepath
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            return float(result.stdout.strip())
        except Exception:
            return 0.0

    def _find_batches(self) -> List[VideoBatch]:
        """Find pending video files and create individual batches (one file per batch)."""
        # Pattern: recordings_dir/ch*/date/*.mp4
        pattern = os.path.join(self.recordings_dir, "ch*", "*", "*.mp4")
        all_mp4s = glob.glob(pattern)
        
        pending_files = []
        
        for mp4_path in all_mp4s:
            if self._is_uploaded(mp4_path):
                continue
            if not self._is_file_stable(mp4_path):
                continue
            if mp4_path.endswith(".tmp"): # Skip temp files from converter
                continue
            
            pending_files.append(mp4_path)
        
        # Sort by path (which sorts by channel/date/time)
        pending_files = sorted(pending_files)
        
        final_batches = []
        
        for mp4_path in pending_files:
            info = self._parse_video_path(mp4_path)
            # Each file is its own batch (no merging)
            batch_obj = VideoBatch(info['channel'], info['date'], [mp4_path])
            final_batches.append(batch_obj)
                
        return final_batches

    def _get_upload_path(self, batch: VideoBatch) -> Optional[str]:
        """Get the video file path for upload (no merging, single file per batch)."""
        if not batch.files:
            return None
        # Return the single file directly - no merging
        return batch.files[0]

    def _generate_description(self, batch: VideoBatch) -> str:
        """Generate description for single video upload."""
        info = self._parse_video_path(batch.files[0])
        duration = self._get_video_duration(batch.files[0])
        
        # Format duration
        m, s = divmod(int(duration), 60)
        h, m = divmod(m, 60)
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        
        desc_lines = [
            f"Security camera recording for {batch.channel}",
            f"Date: {batch.date}",
            f"Time: {info['time']}",
            f"Duration: {duration_str}",
            "",
            "Recorded by Mini-NVR"
        ]
        
        return "\n".join(desc_lines)

    def _process_batch(self, batch: VideoBatch) -> bool:
        """Process a single video file: Upload -> Finalize (no merging)."""
        
        try:
            # 1. Get upload path (single file, no merging)
            upload_path = self._get_upload_path(batch)
            if not upload_path:
                return False
                
            # 2. Metadata
            description = self._generate_description(batch)
            
            # Construct Title: "Channel X - 2026-01-02 (11:14:03)"
            info = self._parse_video_path(batch.files[0])
            title = f"{batch.channel} - {batch.date} ({info['time']})"
            
            metadata = VideoMetadata(
                title=title,
                description=description,
                tags=["NVR", "security", "camera", batch.channel.replace(" ", "")],
                privacy_status=self.privacy_status,
                category_id="22"
            )
            
            # 3. Upload
            service = self._get_service()
            if not service:
                return False
                
            try:
                self.log(f"[NVR Uploader] 📤 Uploading: {title}")
                video_id = self._uploader.upload_video(
                    service=service,
                    video_path=upload_path,
                    metadata=metadata
                )
                
                if video_id:
                    self.log(f"[NVR Uploader] ✓ Uploaded: https://youtube.com/watch?v={video_id}")
                    self._log_upload_to_csv(batch, video_id)
                    self._finalize_batch(batch)
                    self.upload_count += 1
                    self.last_upload_time = time.time()
                    return True
                else:
                    self.log(f"[NVR Uploader] ✗ Upload failed (no video ID)")
                    return False
                    
            except Exception as e:
                err_str = str(e)
                self.log(f"[NVR Uploader] ✗ Upload error: {err_str}")
                
                if "auth" in err_str.lower() or "token" in err_str.lower():
                    self.log("[NVR Uploader] ! Authentication issue detected, resetting service...")
                    self._service = None
                    return False

                if "uploadLimitExceeded" in err_str:
                     self.log("[NVR Uploader] 🛑 DAILY UPLOAD LIMIT REACHED. Pausing uploads for 12 hours.")
                     time.sleep(12 * 3600) 
                     return False
                
                return False
                
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Process error: {e}")
            return False

    def stop(self):
        """Stop the upload service."""
        self._running = False
        self.log("[NVR Uploader] ⏹ Stopping...")
    
    def run(self):
        """Main entry point with blocking auth followed by upload loop."""
        self._running = True
        
        self.log("[NVR Uploader] =========================================")
        self.log("[NVR Uploader] YouTube NVR Upload Service Started")
        self.log("[NVR Uploader] =========================================")
        self.log(f"[NVR Uploader] 📁 Watching: {self.recordings_dir}")
        self.log(f"[NVR Uploader] 🔒 Privacy: {self.privacy_status}")
        self.log(f"[NVR Uploader] ⏱ Scan interval: {self.scan_interval}s")
        
        if not os.path.isdir(self.recordings_dir):
            self.log(f"[NVR Uploader] ✗ Recordings directory not found: {self.recordings_dir}")
            return
        
        # =====================================================================
        # STARTUP CLEANUP: Remove any orphaned merged files from previous runs
        # =====================================================================
        self.log("[NVR Uploader] 🧹 Checking for orphaned merged files...")
        self._cleanup_stale_merged_files(force=True)  # Force delete all at startup
        
        # =====================================================================
        # PHASE 1: AUTHENTICATION (BLOCKING)
        # Must complete before upload service starts
        # =====================================================================
        self.log("[NVR Uploader] ─────────────────────────────────────────────")
        self.log("[NVR Uploader] Phase 1: Authentication")
        self.log("[NVR Uploader] ─────────────────────────────────────────────")

        if not self._trigger_ssh_reauth():
            self.log("[NVR Uploader] ✗ Failed to authenticate after multiple attempts.")
            self.log("[NVR Uploader] ✗ Check your credentials and try again.")
            return

        if not self._authenticate():
            self.log("[NVR Uploader] ✗ Failed to authenticate after multiple attempts.")
            self.log("[NVR Uploader] ✗ Check your credentials and try again.")
            return
        
        self.log("[NVR Uploader] ✓ Authentication complete!")
        
        # =====================================================================
        # PHASE 2: UPLOAD SERVICE
        # Only runs after successful authentication
        # =====================================================================
        self.log("[NVR Uploader] ─────────────────────────────────────────────")
        self.log("[NVR Uploader] Phase 2: Upload Service")
        self.log("[NVR Uploader] ─────────────────────────────────────────────")
        
        self._run_upload_loop()
        
        self.log("[NVR Uploader] ⏹ Service Stopped")

    def _authenticate(self) -> bool:
        """
        Blocking authentication flow.
        
        Flow:
        1. Try to get service with existing credentials
        2. If Docker and no credentials, trigger SSH reauth on host
        3. Wait for auth to complete and files to sync
        4. Retry authentication
        
        Returns:
            True if authentication successful, False otherwise
        """
        max_attempts = 10
        
        for attempt in range(max_attempts):
            self.log(f"[NVR Uploader] 🔑 Authentication attempt {attempt + 1}/{max_attempts}...")
            
            # Try to get service (without triggering SSH reauth in _get_service)
            try:
                if self._uploader is None:
                    if not self._init_uploader():
                        raise Exception("Failed to initialize uploader")
                
                # Get service
                self._service = self._uploader.get_service()
                
                if self._service:
                    self.log("[NVR Uploader] ✓ YouTube API service authenticated")
                    return True
                    
            except Exception as e:
                self.log(f"[NVR Uploader] ✗ Auth attempt failed: {e}")
                self._service = None
            
            # If running in Docker and first failure, trigger SSH reauth
            if self._is_docker and attempt == 0 and not self._reauth_triggered:
                self.log("[NVR Uploader] 🔐 Triggering SSH reauth on host...")
                self._reauth_triggered = True
                
                if self._trigger_ssh_reauth():
                    self.log("[NVR Uploader] ✓ SSH reauth completed! Waiting for sync...")
                    # Wait for files to sync via volume mount
                    time.sleep(5)
                    # Reset uploader to pick up new credentials
                    self._uploader = None
                else:
                    self.log("[NVR Uploader] ⚠ SSH reauth failed")
            
            # Wait before retry
            if attempt < max_attempts - 1:
                self.log(f"[NVR Uploader] ⏳ Waiting 10s before retry...")
                for _ in range(10):
                    if not self._running:
                        return False
                    time.sleep(1)
        
        return False

    def _run_upload_loop(self):
        """Upload loop - only runs after successful authentication."""
        while self._running:
            try:
                # Periodic cleanup of stale merged files (>10 min old)
                # This catches files that may have been left behind during operation
                self._cleanup_stale_merged_files(force=False)
                
                batches = self._find_batches()
                
                if batches:
                    self.log(f"[NVR Uploader] 📋 Found {len(batches)} videos pending upload")
                
                for batch in batches:
                    if not self._running:
                        break
                    
                    info = self._parse_video_path(batch.files[0])
                    self.log(f"[NVR Uploader] > Processing: {batch.channel} {batch.date} ({info['time']})")
                    
                    if self._process_batch(batch):
                        time.sleep(5)
                    else:
                        time.sleep(5)
                    
            except Exception as e:
                self.log(f"[NVR Uploader] ✗ Scan error: {e}")
                self.last_error = str(e)
            
            for _ in range(self.scan_interval):
                if not self._running:
                    break
                time.sleep(1)


def main():
    """Entry point - reads config from Mini-NVR .env file."""
    # Get script directory to find .env
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(script_dir)  # Mini-NVR root
    
    # Load .env file
    env_path = os.path.join(project_dir, ".env")
    if os.path.exists(env_path):
        env = load_env_file(env_path)
        for key, value in env.items():
            os.environ.setdefault(key, value)
    
    # Check if upload is enabled
    if os.environ.get("YOUTUBE_UPLOAD_ENABLED", "false").lower() != "true":
        print("[NVR Uploader] YouTube upload is disabled (YOUTUBE_UPLOAD_ENABLED != true)")
        sys.exit(0)
    
    # Read config from env
    # RECORD_DIR is /recordings in Docker, fallback to project_dir/recordings on host
    recordings_dir = os.environ.get("RECORD_DIR", os.path.join(project_dir, "recordings"))
    client_secret_path = os.environ.get("YOUTUBE_CLIENT_SECRET_PATH")
    token_path = os.environ.get("YOUTUBE_TOKEN_PATH")
    encrypt_path = os.environ.get("YOUTUBE_ENCRYPT_PATH")
    privacy_status = os.environ.get("YOUTUBE_VIDEO_PRIVACY")
    delete_after_upload = os.environ.get("YOUTUBE_DELETE_AFTER_UPLOAD", "false").lower() == "true"
    scan_interval = int(os.environ.get("YOUTUBE_UPLOAD_INTERVAL"))
    hf_repo_id = os.environ.get("HF_REPO_ID")
    hf_token = os.environ.get("HF_TOKEN")
    encryption_key = os.environ.get("YT_ENCRYP_KEY")
    

    
    # Resolve relative paths
    if not os.path.isabs(client_secret_path):
        client_secret_path = os.path.join(project_dir, client_secret_path.lstrip("./"))
    if not os.path.isabs(encrypt_path):
        encrypt_path = os.path.join(project_dir, encrypt_path.lstrip("./"))
    
    # Log file
    log_file = os.environ.get("LOG_FILE")
    if log_file and not os.path.isabs(log_file):
        log_file = os.path.join(project_dir, log_file.lstrip("./"))
    if log_file:
        log_dir = os.path.dirname(log_file)
        log_file = os.path.join(log_dir, "youtube_uploader.log")
    
    # Create service
    service = NVRUploaderService(
        recordings_dir=recordings_dir,
        client_secret_path=client_secret_path,
        token_path=token_path,
        encrypt_path=encrypt_path,
        privacy_status=privacy_status,
        delete_after_upload=delete_after_upload,
        scan_interval=scan_interval,
        hf_repo_id=hf_repo_id,
        hf_token=hf_token,
        encryption_key=encryption_key,
        log_file=log_file,

    )
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        service.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run service
    service.run()


if __name__ == "__main__":
    main()
