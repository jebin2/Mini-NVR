#!/usr/bin/env python3
"""
YouTube Uploader Entry Point
Wraps app.services.youtube_uploader.YouTubeUploaderService
"""

import os
import sys
import signal
import asyncio

# Get directories
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from core.config import settings
from core.logger import setup_logger
from services.youtube_uploader import YouTubeUploaderService

log = setup_logger("yt_upload", "/logs/youtube_upload.log")

async def main():
    # Env loaded by settings

    
    # Check if upload is enabled
    if not settings.youtube_upload_enabled:
        print("[NVR Uploader] YouTube upload is disabled (YOUTUBE_UPLOAD_ENABLED != true)")
        return

    # Create service
    service = YouTubeUploaderService(
        recordings_dir=settings.record_dir,
        privacy_status=settings.youtube_video_privacy,
        delete_after_upload=settings.youtube_delete_after_upload,
        batch_size_mb=settings.youtube_upload_batch_size_mb
    )
    
    # Handle graceful shutdown
    loop = asyncio.get_running_loop()
    def signal_handler():
        print(f"\n[NVR Uploader] Received signal, stopping...")
        service.stop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)
    
    # Run
    await service.run()

if __name__ == "__main__":
    asyncio.run(main())
