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
        
        self._check_dependencies()
    
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
            config = YouTubeConfig(
                encrypt_path=self.encrypt_path,
                hf_repo_id=self.hf_repo_id,
                hf_token=self.hf_token,
                encryption_key=self.encryption_key,
                # Running on host with display - enable Neko
                is_docker=False,
                has_display=True,
                headless_mode=False,
                docker_name="nvr_youtube_auto_pub",
                google_email=os.environ.get("GOOGLE_EMAIL"),
                google_password=os.environ.get("GOOGLE_PASSWORD"),
            )
            
            self._uploader = YouTubeUploader(config)
            self.log("[NVR Uploader] ✓ YouTube uploader initialized")
            return True
            
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Failed to initialize uploader: {e}")
            self.last_error = str(e)
            return False
    
    def _get_service(self):
        """Get authenticated YouTube API service."""
        if self._service is not None:
            return self._service
        
        if self._uploader is None:
            if not self._init_uploader():
                return None
        
        try:
            # youtube_auto_pub expects just filenames, not full paths
            import shutil
            
            token_filename = os.path.basename(self.token_path)
            client_filename = os.path.basename(self.client_secret_path)
            
            # Copy client_secret to encrypt folder if it exists locally
            if os.path.exists(self.client_secret_path):
                dest = os.path.join(self.encrypt_path, client_filename)
                if not os.path.exists(dest):
                    shutil.copy2(self.client_secret_path, dest)
                    self.log(f"[NVR Uploader] Copied {client_filename} to encrypt folder")
            
            self._service = self._uploader.get_service(
                token_path=token_filename,
                client_path=client_filename
            )
            self.log("[NVR Uploader] ✓ YouTube API service authenticated")
            return self._service
        except Exception as e:
            # Only log auth errors once per batch scan attempts or implement backoff?
            # For now standard logging
            self.log(f"[NVR Uploader] ✗ Failed to get YouTube service: {e}")
            self.last_error = str(e)
            self._service = None
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
        """Group pending files into batches by Channel and Date, splitting if > limit."""
        # Pattern: recordings_dir/ch*/date/*.mp4
        pattern = os.path.join(self.recordings_dir, "ch*", "*", "*.mp4")
        all_mp4s = glob.glob(pattern)
        
        # Grouping dictionary: key=(channel, date), value=[files]
        groups: Dict[tuple, List[str]] = {}
        
        for mp4_path in all_mp4s:
            if self._is_uploaded(mp4_path):
                continue
            if not self._is_file_stable(mp4_path):
                continue
            if mp4_path.endswith(".tmp"): # Skip temp files from converter
                continue
                
            info = self._parse_video_path(mp4_path)
            key = (info['channel'], info['date'])
            
            if key not in groups:
                groups[key] = []
            groups[key].append(mp4_path)
        
        final_batches = []
        
        for (channel, date), files in groups.items():
            if not files:
                continue
                
            sorted_files = sorted(files)
            
            # Check total duration and split if necessary
            current_batch_files = []
            current_duration = 0.0
            split_batches = []
            
            for file_path in sorted_files:
                duration = self._get_video_duration(file_path)
                
                # If adding this file would exceed limit, finalize current batch
                if current_duration + duration > self.MAX_DURATION_SECONDS and current_batch_files:
                    split_batches.append(current_batch_files)
                    current_batch_files = []
                    current_duration = 0.0
                
                current_batch_files.append(file_path)
                current_duration += duration
            
            # Append last batch
            if current_batch_files:
                split_batches.append(current_batch_files)
            
            # Create VideoBatch objects
            total_parts = len(split_batches)
            for i, batch_files in enumerate(split_batches):
                part_number = i + 1
                # Only use "parts" if we actually split
                if total_parts > 1:
                     batch_obj = VideoBatch(channel, date, batch_files, part_number, total_parts)
                else:
                     batch_obj = VideoBatch(channel, date, batch_files)
                
                final_batches.append(batch_obj)
                
        return sorted(final_batches, key=lambda b: (b.channel, b.date, b.part_number))

    def _merge_videos(self, batch: VideoBatch) -> Optional[str]:
        """Merge videos in batch into a single file using ffmpeg concat."""
        if not batch.files:
            return None
            
        # If only one file, no actual merge needed, but we treat it as "merged"
        if len(batch.files) == 1:
            return batch.files[0]
            
        try:
            # Create list file
            list_path = os.path.join(self.recordings_dir, f"concat_list_{os.getpid()}.txt")
            
            # Add part suffix to merged filename if needed
            part_suffix = ""
            if batch.total_parts > 1:
                part_suffix = f"_p{batch.part_number}"
                
            merged_output = os.path.join(
                self.recordings_dir, 
                f"merged_{batch.files[0].split(os.sep)[-2]}_{len(batch.files)}files{part_suffix}.mp4"
            )
            
            with open(list_path, 'w') as f:
                for file_path in batch.files:
                    # FFmpeg concat requires absolute paths
                    f.write(f"file '{file_path}'\n")
            
            self.log(f"[NVR Uploader] ⚙ Merging {len(batch.files)} clips for {batch.channel} (Part {batch.part_number}/{batch.total_parts})...")
            
            # Run ffmpeg concat
            cmd = [
                "ffmpeg", 
                "-y", "-v", "error",
                "-f", "concat",
                "-safe", "0",
                "-i", list_path,
                "-c", "copy",
                merged_output
            ]
            
            subprocess.run(cmd, check=True)
            
            # Cleanup list
            os.remove(list_path)
            
            batch.merged_path = merged_output # Mark for deletion later
            return merged_output
            
        except subprocess.CalledProcessError as e:
            self.log(f"[NVR Uploader] ✗ Merge failed: {e}")
            if os.path.exists(list_path):
                os.remove(list_path)
            return None
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Error during merge prep: {e}")
            return None

    def _generate_description(self, batch: VideoBatch) -> str:
        """Generate description with timestamps."""
        desc_lines = [
            f"Security camera recording for {batch.channel}",
            f"Date: {batch.date}"
        ]
        
        if batch.total_parts > 1:
            desc_lines.append(f"Part {batch.part_number} of {batch.total_parts}")
            
        desc_lines.extend([
            f"Merged clips: {len(batch.files)}",
            "",
            "Timeline:"
        ])
        
        current_time = 0.0
        
        for file_path in batch.files:
            info = self._parse_video_path(file_path)
            duration = self._get_video_duration(file_path)
            
            # Format elapsed time as HH:MM:SS
            m, s = divmod(int(current_time), 60)
            h, m = divmod(m, 60)
            if h > 0:
                ts = f"{h:02d}:{m:02d}:{s:02d}"
            else:
                ts = f"{m:02d}:{s:02d}"
                
            desc_lines.append(f"{ts} - {info['time']}")
            current_time += duration
            
        desc_lines.append("")
        desc_lines.append("Recorded by Mini-NVR")
        
        return "\n".join(desc_lines)

    def _process_batch(self, batch: VideoBatch) -> bool:
        """Process a single batch: Merge -> Upload -> Finalize."""
        
        # 1. Merge
        upload_path = self._merge_videos(batch)
        if not upload_path:
            return False
            
        # 2. Metadata
        description = self._generate_description(batch)
        
        # Construct Title
        # Title: Channel X - Date - FirstTime - LastTime [(Part X)]
        first_info = self._parse_video_path(batch.files[0])
        last_info = self._parse_video_path(batch.files[-1])
        
        title = f"{batch.channel} - {batch.date} ({first_info['time']} to {last_info['time']})"
        if batch.total_parts > 1:
            title += f" (Part {batch.part_number}/{batch.total_parts})"
        
        metadata = VideoMetadata(
            title=title,
            description=description,
            tags=["NVR", "security", "camera", batch.channel.replace(" ", ""), "merged"],
            privacy_status=self.privacy_status,
            category_id="22"
        )
        
        # 3. Upload
        service = self._get_service()
        if not service:
            return False
            
        try:
            self.log(f"[NVR Uploader] 📤 Uploading batch: {title}")
            video_id = self._uploader.upload_video(
                service=service,
                video_path=upload_path,
                metadata=metadata
            )
            
            if video_id:
                self.log(f"[NVR Uploader] ✓ Uploaded: https://youtube.com/watch?v={video_id}")
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
            
            # Check for generic authentication errors
            if "auth" in err_str.lower() or "token" in err_str.lower():
                self.log("[NVR Uploader] ! Authentication issue detected, resetting service...")
                self._service = None
                return False

            # Check for YouTube Upload Limit
            # Error usually looks like: <HttpError 400 ... reason': 'uploadLimitExceeded' ...>
            if "uploadLimitExceeded" in err_str:
                 self.log("[NVR Uploader] 🛑 DAILY UPLOAD LIMIT REACHED. Pausing uploads for 12 hours.")
                 # Sleep for 12 hours or just stop trying for a long time
                 # For safety, let's sleep 1 hour in loop or just return False and let the main loop handle it.
                 # But sticking to the plan: explicit sleep here to block this thread.
                 time.sleep(12 * 3600) 
                 return False
            
            return False

    def stop(self):
        """Stop the upload service."""
        self._running = False
        self.log("[NVR Uploader] ⏹ Stopping...")
    
    def run(self):
        """Main upload loop."""
        self._running = True
        
        self.log("[NVR Uploader] =========================================")
        self.log("[NVR Uploader] YouTube NVR Upload Service Started (Batch Mode)")
        self.log("[NVR Uploader] =========================================")
        self.log(f"[NVR Uploader] 📁 Watching: {self.recordings_dir}")
        self.log(f"[NVR Uploader] 🔒 Privacy: {self.privacy_status}")
        self.log(f"[NVR Uploader] ⏱ Scan interval: {self.scan_interval}s")
        
        if not os.path.isdir(self.recordings_dir):
            self.log(f"[NVR Uploader] ✗ Recordings directory not found: {self.recordings_dir}")
            return
        
        time.sleep(5)
        
        while self._running:
            try:
                batches = self._find_batches()
                
                if batches:
                    self.log(f"[NVR Uploader] 📋 Found {len(batches)} batches pending upload")
                
                for batch in batches:
                    if not self._running:
                        break
                    
                    # Log batch details
                    self.log(f"[NVR Uploader] > Processing batch {batch.channel} {batch.date}: {len(batch.files)} files")
                    
                    if self._process_batch(batch):
                         # If successful, maybe short sleep
                         time.sleep(5)
                    else:
                         # If failed, longer sleep or continue?
                         # Continue to next batch, maybe it was a file specific issue
                         time.sleep(5)
                    
            except Exception as e:
                self.log(f"[NVR Uploader] ✗ Scan error: {e}")
                self.last_error = str(e)
            
            for _ in range(self.scan_interval):
                if not self._running:
                    break
                time.sleep(1)
        
        self.log("[NVR Uploader] ⏹ Service Stopped")


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
    recordings_dir = os.path.join(project_dir, "recordings")
    client_secret_path = os.environ.get("YOUTUBE_CLIENT_SECRET_PATH", "./ytktclient_secret.json")
    token_path = os.environ.get("YOUTUBE_TOKEN_PATH", "./ytkttoken.json")
    encrypt_path = os.environ.get("YOUTUBE_ENCRYPT_PATH", "./encrypt")
    privacy_status = os.environ.get("YOUTUBE_VIDEO_PRIVACY", "unlisted")
    delete_after_upload = os.environ.get("YOUTUBE_DELETE_AFTER_UPLOAD", "false").lower() == "true"
    scan_interval = int(os.environ.get("YOUTUBE_UPLOAD_INTERVAL", "60"))
    hf_repo_id = os.environ.get("HF_REPO_ID", "jebin2/Data")
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
