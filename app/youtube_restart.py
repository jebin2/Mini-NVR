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


def main():
    log.info("=" * 50)
    log.info("🎬 YouTube Video Segmentation Service Starting")
    log.info("=" * 50)
    
    if not YOUTUBE_ENABLED:
        log.info("YouTube Live disabled (YOUTUBE_LIVE_ENABLED != true)")
        log.info("Exiting...")
        return
    
    log.info(f"Restart interval: {ROTATION_HOURS} hours")
    log.info(f"Restart interval: {ROTATION_SECONDS} seconds")
    
    segment = 0
    
    while True:
        segment += 1
        log.info(f"📡 Segment #{segment} - Next restart in {ROTATION_HOURS} hours...")
        
        time.sleep(ROTATION_SECONDS)
        
        log.info(f"⏰ Time for segment #{segment + 1}")
        restart_go2rtc()


if __name__ == "__main__":
    main()
