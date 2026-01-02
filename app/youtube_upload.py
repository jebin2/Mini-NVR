#!/usr/bin/env python3
"""
YouTube Uploader Entry Point
Wraps app.services.youtube_uploader.YouTubeUploaderService
"""

import os
import sys
import signal
import time

# Get directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# If script is in app/, Project Dir is parent
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

# Add current dir (app) to path so we can import services
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Also add project dir for youtube_auto_pub if installed via git submodule/folder
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

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

def main():
    # Load .env file
    env_path = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_path):
        env = load_env_file(env_path)
        for key, value in env.items():
            os.environ.setdefault(key, value)
    
    # Check if upload is enabled
    if os.environ.get("YOUTUBE_UPLOAD_ENABLED", "false").lower() != "true":
        print("[NVR Uploader] YouTube upload is disabled (YOUTUBE_UPLOAD_ENABLED != true)")
        return

    # Import service AFTER path setup
    try:
        from services.youtube_uploader import YouTubeUploaderService
    except ImportError as e:
        print(f"[NVR Uploader] ❌ Failed to import service: {e}")
        # Debug: print sys.path
        print(f"sys.path: {sys.path}")
        sys.exit(1)

    # Config
    # RECORD_DIR is /recordings in Docker, fallback to project_dir/recordings on host
    recordings_dir = os.environ.get("RECORD_DIR", os.path.join(PROJECT_DIR, "recordings"))
    privacy_status = os.environ.get("YOUTUBE_VIDEO_PRIVACY", "unlisted")
    delete_after = os.environ.get("YOUTUBE_DELETE_AFTER_UPLOAD", "false").lower() == "true"
    scan_interval = int(os.environ.get("YOUTUBE_UPLOAD_INTERVAL", "60"))
    
    # Create service
    service = YouTubeUploaderService(
        recordings_dir=recordings_dir,
        privacy_status=privacy_status,
        delete_after_upload=delete_after,
        scan_interval=scan_interval
    )
    
    # Handle graceful shutdown
    def signal_handler(signum, frame):
        print(f"\n[NVR Uploader] Received signal {signum}, stopping...")
        service.stop()
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run
    service.run()

if __name__ == "__main__":
    main()
