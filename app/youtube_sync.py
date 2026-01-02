#!/usr/bin/env python3
"""
YouTube Sync Service
Periodically syncs YouTube video metadata to CSV files.
Runs independently from streaming - requires OAuth auth.
"""
import os
import sys
import time
import signal

# Ensure project root is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

from core.config import settings
from core.logger import setup_logger
from services.youtube_video_sync import YouTubeVideoSync

log = setup_logger("yt_sync", "/logs/youtube_sync.log")


def main():
    log.info("=" * 50)
    log.info("📺 YouTube Sync Service")
    log.info("=" * 50)
    
    if not settings.youtube_sync_enabled:
        log.info("ℹ️ YouTube sync disabled (YOUTUBE_SYNC_ENABLED=false). Exiting.")
        return
    
    # Get sync interval from settings (same as stream restart interval, or default to 2 hours)
    sync_interval_hours = settings.youtube_live_restart_interval_hours or 2
    sync_interval_seconds = int(sync_interval_hours * 3600)
    
    log.info(f"⏰ Sync interval: every {sync_interval_hours} hours ({sync_interval_seconds}s)")
    log.info(f"📁 Recordings dir: {settings.record_dir}")
    
    syncer = YouTubeVideoSync(recordings_dir=settings.record_dir)
    running = True
    
    def shutdown(sig, frame):
        nonlocal running
        log.info("🛑 Shutting down...")
        running = False
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Initial sync
    log.info("🔄 Running initial sync...")
    try:
        new_videos = syncer.sync_to_csv()
        log.info(f"✅ Initial sync complete: {new_videos} new videos")
    except Exception as e:
        log.error(f"❌ Initial sync failed: {e}")
    
    # Periodic sync loop
    last_sync = time.time()
    
    while running:
        time.sleep(30)  # Check every 30 seconds
        
        elapsed = time.time() - last_sync
        if elapsed >= sync_interval_seconds:
            log.info(f"🔄 Running scheduled sync (interval: {sync_interval_hours}h)...")
            try:
                new_videos = syncer.sync_to_csv()
                log.info(f"✅ Sync complete: {new_videos} new videos")
            except Exception as e:
                log.error(f"❌ Sync failed: {e}")
            last_sync = time.time()
    
    log.info("👋 YouTube Sync Service stopped")


if __name__ == "__main__":
    main()
