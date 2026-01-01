#!/usr/bin/env python3
"""
YouTube Live Streaming Service

Manages FFmpeg process that streams camera to YouTube.
Restarts every 11 hours to create separate videos.
"""
import os
import sys
import time
import signal
import subprocess
import logging
from logging.handlers import RotatingFileHandler

# ============================================
# Configuration
# ============================================

def get_env(name, default=None):
    return os.getenv(name, default)

YOUTUBE_ENABLED = get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"
YOUTUBE_RTMP_URL = get_env("YOUTUBE_RTMP_URL", "rtmp://a.rtmp.youtube.com/live2")
YOUTUBE_STREAM_KEY = get_env("YOUTUBE_STREAM_KEY_1")
YOUTUBE_GRID = int(get_env("YOUTUBE_GRID"))
ROTATION_HOURS = int(get_env("YOUTUBE_ROTATION_HOURS", "11"))
ROTATION_SECONDS = ROTATION_HOURS * 3600

GO2RTC_RTSP_PORT = int(get_env("GO2RTC_RTSP_PORT", "8554"))
GO2RTC_API_PORT = int(get_env("GO2RTC_API_PORT", "2127"))

# ============================================
# Logging
# ============================================

def setup_logger():
    log_dir = "/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("yt_stream")
    logger.setLevel(logging.DEBUG)
    
    fmt = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    fh = RotatingFileHandler(f"{log_dir}/youtube_stream.log", maxBytes=5*1024*1024, backupCount=2)
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

log = setup_logger()

# ============================================
# FFmpeg Process Management
# ============================================

class YouTubeStreamer:
    def __init__(self):
        self.process = None
        self.segment = 0
        self.start_time = None
    
    def build_cmd(self):
        """Build FFmpeg command."""
        rtsp = f"rtsp://127.0.0.1:{GO2RTC_RTSP_PORT}/cam1"
        rtmp = f"{YOUTUBE_RTMP_URL}/{YOUTUBE_STREAM_KEY}"
        
        return [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning",
            "-rtsp_transport", "tcp",
            "-i", rtsp,
            # Silent audio (YouTube requires audio)
            "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            # Video
            "-c:v", "libx264", "-preset", "veryfast", "-tune", "zerolatency",
            "-b:v", "2500k", "-maxrate", "3000k", "-bufsize", "6000k",
            "-r", "25", "-g", "50", "-pix_fmt", "yuv420p",
            # Audio
            "-c:a", "aac", "-b:a", "128k",
            "-shortest",
            "-f", "flv", rtmp
        ]
    
    def start(self):
        """Start FFmpeg process."""
        if self.process and self.process.poll() is None:
            self.stop()
        
        cmd = self.build_cmd()
        log.info("� Starting FFmpeg...")
        log.debug(f"RTSP: rtsp://127.0.0.1:{GO2RTC_RTSP_PORT}/cam1")
        log.debug(f"RTMP: {YOUTUBE_RTMP_URL}/****")
        
        try:
            self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.start_time = time.time()
            self.segment += 1
            
            # Wait briefly to verify startup
            time.sleep(5)
            if self.process.poll() is not None:
                stderr = self.process.stderr.read()
                log.error(f"❌ FFmpeg crashed on start: {stderr[-500:]}")
                return False
            
            log.info(f"✅ FFmpeg started (PID: {self.process.pid})")
            log.info(f"📺 Streaming to YouTube - Segment #{self.segment}")
            return True
            
        except Exception as e:
            log.error(f"❌ Failed to start FFmpeg: {e}")
            return False
    
    def stop(self):
        """Stop FFmpeg process."""
        if not self.process:
            return
        
        log.info("⏹ Stopping FFmpeg...")
        try:
            self.process.terminate()
            self.process.wait(timeout=10)
        except:
            self.process.kill()
        
        self.process = None
    
    def is_running(self):
        return self.process and self.process.poll() is None
    
    def needs_restart(self):
        if not self.start_time:
            return False
        return (time.time() - self.start_time) >= ROTATION_SECONDS

# ============================================
# Main
# ============================================

def wait_for_go2rtc():
    import urllib.request
    url = f"http://127.0.0.1:{GO2RTC_API_PORT}/api"
    log.info("⏳ Waiting for go2rtc...")
    for i in range(60):
        try:
            urllib.request.urlopen(url, timeout=2)
            log.info(f"✅ go2rtc ready ({i}s)")
            return True
        except:
            time.sleep(1)
    log.error("❌ go2rtc not ready")
    return False

def main():
    log.info("=" * 50)
    log.info("🎬 YouTube Streaming Service")
    log.info("=" * 50)
    
    if not YOUTUBE_ENABLED:
        log.info("YouTube disabled. Exiting.")
        return
    
    if not YOUTUBE_STREAM_KEY:
        log.error("❌ No YOUTUBE_STREAM_KEY_1")
        return
    
    log.info(f"Segment duration: {ROTATION_HOURS} hours")
    
    if not wait_for_go2rtc():
        return
    
    streamer = YouTubeStreamer()
    
    def shutdown(sig, frame):
        log.info("Shutting down...")
        streamer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Start streaming
    if not streamer.start():
        return
    
    # Main loop
    while True:
        if not streamer.is_running():
            log.warning("⚠ FFmpeg died, restarting...")
            time.sleep(5)
            streamer.start()
            continue
        
        if streamer.needs_restart():
            log.info("🔄 Time for new segment")
            streamer.stop()
            time.sleep(10)
            streamer.start()
        
        time.sleep(10)

if __name__ == "__main__":
    main()
