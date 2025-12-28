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
from datetime import datetime
from typing import Optional, List

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


class NVRUploaderService:
    """
    Background service to upload Mini-NVR recordings to YouTube.
    
    Watches for MP4 files in the NVR recordings directory and uploads
    them with appropriate metadata. Uses marker files to track uploads.
    """
    
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
            # Extract the basename and ensure the file is in encrypt folder
            import shutil
            
            token_filename = os.path.basename(self.token_path)
            client_filename = os.path.basename(self.client_secret_path)
            
            # Copy client_secret to encrypt folder if it exists locally
            # (for first-time setup when HuggingFace doesn't have it yet)
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
            self.log(f"[NVR Uploader] ✗ Failed to get YouTube service: {e}")
            self.last_error = str(e)
            self._service = None
            return None
    
    def _get_metadata_dir(self) -> str:
        """Get the metadata directory for storing upload markers."""
        metadata_dir = os.path.join(self.recordings_dir, ".upload_metadata")
        if not os.path.exists(metadata_dir):
            try:
                os.makedirs(metadata_dir, exist_ok=True)
            except OSError:
                # Fall back to a directory we definitely control
                metadata_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".upload_metadata")
                os.makedirs(metadata_dir, exist_ok=True)
        return metadata_dir
    
    def _get_marker_path(self, mp4_path: str) -> str:
        """Get the .uploaded marker file path for an MP4."""
        return mp4_path + ".uploaded"
    
    def _get_fallback_marker_path(self, mp4_path: str) -> str:
        """Get fallback marker path in metadata directory."""
        # Create a unique filename based on the full path
        # Replace path separators and use the relative path from recordings_dir
        rel_path = os.path.relpath(mp4_path, self.recordings_dir)
        safe_name = rel_path.replace(os.sep, "_").replace("/", "_") + ".uploaded"
        return os.path.join(self._get_metadata_dir(), safe_name)
    
    def _is_uploaded(self, mp4_path: str) -> bool:
        """Check if MP4 has been uploaded (marker file exists)."""
        # Check both the original location and fallback location
        return (os.path.exists(self._get_marker_path(mp4_path)) or 
                os.path.exists(self._get_fallback_marker_path(mp4_path)))
    
    def _is_file_stable(self, filepath: str, stable_seconds: int = 30) -> bool:
        """Check if file has stopped being written to."""
        try:
            return (time.time() - os.path.getmtime(filepath)) > stable_seconds
        except OSError:
            return False
    
    def _mark_uploaded(self, mp4_path: str, video_id: str):
        """Create marker file after successful upload."""
        marker_content = f"video_id={video_id}\nuploaded_at={datetime.now().isoformat()}\noriginal_path={mp4_path}\n"
        
        # Try original location first (beside the MP4 file)
        marker_path = self._get_marker_path(mp4_path)
        try:
            with open(marker_path, 'w') as f:
                f.write(marker_content)
            return
        except PermissionError:
            pass  # Fall through to fallback
        except OSError as e:
            self.log(f"[NVR Uploader] ! Could not create marker at {marker_path}: {e}")
        
        # Use fallback location in metadata directory
        fallback_path = self._get_fallback_marker_path(mp4_path)
        try:
            with open(fallback_path, 'w') as f:
                f.write(marker_content)
            self.log(f"[NVR Uploader] ℹ Marker saved to metadata dir (no write access to recordings)")
        except OSError as e:
            self.log(f"[NVR Uploader] ✗ Failed to create upload marker: {e}")
    
    def _find_pending_uploads(self) -> List[str]:
        """Find MP4 files that haven't been uploaded yet."""
        # Pattern: recordings_dir/ch*/date/*.mp4
        pattern = os.path.join(self.recordings_dir, "ch*", "*", "*.mp4")
        all_mp4s = glob.glob(pattern)
        
        pending = []
        for mp4_path in all_mp4s:
            if self._is_uploaded(mp4_path):
                continue
            if not self._is_file_stable(mp4_path):
                continue
            if mp4_path.endswith(".tmp"):
                continue
            pending.append(mp4_path)
        
        return sorted(pending)
    
    def _parse_video_path(self, mp4_path: str) -> dict:
        """Parse video path to extract metadata."""
        try:
            parts = mp4_path.split(os.sep)
            filename = os.path.splitext(parts[-1])[0]
            date_str = parts[-2]
            channel_dir = parts[-3]
            
            channel = channel_dir.replace("ch", "Channel ")
            time_str = f"{filename[:2]}:{filename[2:4]}:{filename[4:6]}"
            
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
                "time": datetime.now().strftime("%H:%M:%S"),
                "filename": os.path.basename(mp4_path)
            }
    
    def _upload_video(self, mp4_path: str) -> Optional[str]:
        """Upload a single video to YouTube."""
        service = self._get_service()
        if service is None:
            return None
        
        info = self._parse_video_path(mp4_path)
        
        title = f"NVR {info['channel']} - {info['date']} {info['time']}"
        description = (
            f"Security camera recording\n"
            f"Channel: {info['channel']}\n"
            f"Date: {info['date']}\n"
            f"Time: {info['time']}\n"
            f"\nRecorded by Mini-NVR"
        )
        
        metadata = VideoMetadata(
            title=title,
            description=description,
            tags=["NVR", "security", "camera", info['channel'].replace(" ", "")],
            privacy_status=self.privacy_status,
            category_id="22"
        )
        
        try:
            self.log(f"[NVR Uploader] 📤 Uploading: {os.path.basename(mp4_path)}...")
            
            video_id = self._uploader.upload_video(
                service=service,
                video_path=mp4_path,
                metadata=metadata
            )
            
            if video_id:
                self.log(f"[NVR Uploader] ✓ Uploaded: https://youtube.com/watch?v={video_id}")
                self._mark_uploaded(mp4_path, video_id)
                self.upload_count += 1
                self.last_upload_time = time.time()
                
                if self.delete_after_upload:
                    try:
                        os.remove(mp4_path)
                        self.log(f"[NVR Uploader] 🗑 Deleted local file: {os.path.basename(mp4_path)}")
                    except OSError as e:
                        self.log(f"[NVR Uploader] ! Failed to delete {mp4_path}: {e}")
                
                return video_id
            else:
                self.log(f"[NVR Uploader] ✗ Upload failed (no video ID): {mp4_path}")
                return None
                
        except Exception as e:
            self.log(f"[NVR Uploader] ✗ Upload error for {mp4_path}: {e}")
            self.last_error = str(e)
            if "auth" in str(e).lower() or "credential" in str(e).lower():
                self._service = None
            return None
    
    def stop(self):
        """Stop the upload service."""
        self._running = False
        self.log("[NVR Uploader] ⏹ Stopping...")
    
    def run(self):
        """Main upload loop."""
        self._running = True
        
        self.log("[NVR Uploader] =========================================")
        self.log("[NVR Uploader] YouTube NVR Upload Service Started")
        self.log("[NVR Uploader] =========================================")
        self.log(f"[NVR Uploader] 📁 Watching: {self.recordings_dir}")
        self.log(f"[NVR Uploader] 🔒 Privacy: {self.privacy_status}")
        self.log(f"[NVR Uploader] ⏱ Scan interval: {self.scan_interval}s")
        self.log(f"[NVR Uploader] 🗑 Delete after upload: {self.delete_after_upload}")
        
        if not os.path.isdir(self.recordings_dir):
            self.log(f"[NVR Uploader] ✗ Recordings directory not found: {self.recordings_dir}")
            return
        
        time.sleep(5)
        
        while self._running:
            try:
                pending = self._find_pending_uploads()
                
                if pending:
                    self.log(f"[NVR Uploader] 📋 Found {len(pending)} videos to upload")
                
                for mp4_path in pending:
                    if not self._running:
                        break
                    self._upload_video(mp4_path)
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
        print("[NVR Uploader] Set YOUTUBE_UPLOAD_ENABLED=true in .env to enable")
        sys.exit(0)
    
    # Read config from env (same vars as Docker)
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
    
    # Log file (same as Mini-NVR Docker)
    log_file = os.environ.get("LOG_FILE")
    if log_file and not os.path.isabs(log_file):
        log_file = os.path.join(project_dir, log_file.lstrip("./"))
    
    # Append to same log or create separate one
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
