#!/usr/bin/env python3
"""
YouTube Video Segmentation Service

Restarts go2rtc every 11 hours to create separate YouTube videos.
Runs inside mini-nvr container.
"""
import os
import sys
import time
import subprocess
import logging
from logging.handlers import RotatingFileHandler

# ============================================
# Configuration
# ============================================

ROTATION_HOURS = int(os.getenv("YOUTUBE_ROTATION_HOURS", "11"))
ROTATION_SECONDS = ROTATION_HOURS * 3600
YOUTUBE_ENABLED = os.getenv("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"

# ============================================
# Logging Setup
# ============================================

def setup_logger():
    log_dir = "/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("yt_restart")
    logger.setLevel(logging.DEBUG)
    
    fmt = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    fh = RotatingFileHandler(
        f"{log_dir}/youtube_restart.log",
        maxBytes=5*1024*1024,  # 5MB
        backupCount=2
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

log = setup_logger()

# go2rtc API
GO2RTC_API_PORT = int(os.getenv("GO2RTC_API_PORT", "2127"))
GO2RTC_API_URL = f"http://127.0.0.1:{GO2RTC_API_PORT}"

# ============================================
# Stream Trigger
# ============================================

def trigger_youtube_stream():
    """Trigger the YouTube stream to start via go2rtc API."""
    import urllib.request
    import urllib.error
    
    # This call triggers go2rtc to start the exec command for cam1_youtube
    url = f"{GO2RTC_API_URL}/api/streams?src=cam1_youtube"
    
    try:
        req = urllib.request.Request(url, method='GET')
        with urllib.request.urlopen(req, timeout=10) as response:
            log.info(f"✅ YouTube stream triggered successfully")
            return True
    except urllib.error.URLError as e:
        log.error(f"❌ Failed to trigger stream: {e}")
        return False
    except Exception as e:
        log.error(f"❌ Error triggering stream: {e}")
        return False

# ============================================
# Main Logic
# ============================================

def restart_go2rtc():
    """Restart go2rtc container using docker CLI."""
    log.info("🔄 Restarting go2rtc for new video segment...")
    
    try:
        result = subprocess.run(
            ["docker", "restart", "go2rtc"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            log.info("✅ go2rtc restarted successfully")
            log.info("📺 New YouTube video segment started")
            return True
        else:
            log.error(f"❌ Failed to restart go2rtc: {result.stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        log.error("❌ Timeout waiting for go2rtc restart")
        return False
    except FileNotFoundError:
        log.error("❌ Docker CLI not found - is docker.io installed?")
        return False
    except Exception as e:
        log.error(f"❌ Error restarting go2rtc: {e}")
        return False


def wait_for_go2rtc():
    """Wait for go2rtc API to be ready."""
    import urllib.request
    
    url = f"{GO2RTC_API_URL}/api"
    for i in range(60):
        try:
            urllib.request.urlopen(url, timeout=2)
            log.info(f"✅ go2rtc ready ({i}s)")
            return True
        except:
            time.sleep(1)
    
    log.error("❌ go2rtc not ready after 60s")
    return False


def main():
    log.info("=" * 50)
    log.info("🎬 YouTube Video Segmentation Service Starting")
    log.info("=" * 50)
    
    if not YOUTUBE_ENABLED:
        log.info("YouTube Live disabled (YOUTUBE_LIVE_ENABLED != true)")
        log.info("Exiting...")
        return
    
    log.info(f"Restart interval: {ROTATION_HOURS} hours")
    
    # Wait for go2rtc
    if not wait_for_go2rtc():
        return
    
    # Initial trigger
    log.info("📺 Starting YouTube stream...")
    time.sleep(5)  # Give go2rtc a moment
    trigger_youtube_stream()
    
    segment = 1
    
    while True:
        log.info(f"📡 Segment #{segment} - Next restart in {ROTATION_HOURS} hours...")
        
        time.sleep(ROTATION_SECONDS)
        
        log.info(f"⏰ Time for segment #{segment + 1}")
        if restart_go2rtc():
            time.sleep(10)  # Wait for go2rtc to restart
            trigger_youtube_stream()
            segment += 1


if __name__ == "__main__":
    main()
