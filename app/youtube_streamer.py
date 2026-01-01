#!/usr/bin/env python3
"""
YouTube Live Streamer Service

Standalone service that:
- Creates a 2x2 grid from cameras using FFmpeg
- Streams directly to YouTube RTMP
- Restarts hourly to create separate YouTube videos
- Has detailed step-by-step logging
"""
import os
import sys
import time
import signal
import subprocess
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

# ============================================
# Configuration
# ============================================

def get_env(name, default=None):
    return os.getenv(name, default)

# YouTube settings
YOUTUBE_LIVE_ENABLED = get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"
YOUTUBE_RTMP_URL = get_env("YOUTUBE_RTMP_URL")
YOUTUBE_STREAM_KEY_1 = get_env("YOUTUBE_STREAM_KEY_1")
YOUTUBE_GRID = int(get_env("YOUTUBE_GRID"))
YOUTUBE_ROTATION_MINUTES = int(get_env("YOUTUBE_ROTATION_MINUTES"))

# go2rtc settings
GO2RTC_RTSP_PORT = int(get_env("GO2RTC_RTSP_PORT"))
GO2RTC_API_PORT = int(get_env("GO2RTC_API_PORT"))

# Number of channels
NUM_CHANNELS = int(get_env("NUM_CHANNELS"))

# ============================================
# Logging Setup
# ============================================

def setup_logger():
    """Setup logger with file and console output."""
    log_dir = "/logs"
    os.makedirs(log_dir, exist_ok=True)
    
    logger = logging.getLogger("youtube_streamer")
    logger.setLevel(logging.DEBUG)
    
    # Format
    fmt = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler with rotation
    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "youtube_streamer.log"),
        maxBytes=10*1024*1024,  # 10MB
        backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(fmt)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

logger = setup_logger()

# ============================================
# FFmpeg Grid Builder
# ============================================

def build_ffmpeg_command(cameras: list, rtmp_url: str, stream_key: str) -> list:
    """
    Build FFmpeg command for grid streaming.
    
    Args:
        cameras: List of camera numbers to include in grid
        rtmp_url: YouTube RTMP base URL
        stream_key: YouTube stream key
    
    Returns:
        FFmpeg command as list
    """
    logger.debug(f"[BUILD] Building FFmpeg command for cameras: {cameras}")
    
    cmd = ["ffmpeg", "-hide_banner", "-nostats", "-re"]
    
    # Add RTSP inputs
    for cam in cameras:
        rtsp_url = f"rtsp://127.0.0.1:{GO2RTC_RTSP_PORT}/cam{cam}"
        cmd.extend(["-rtsp_transport", "tcp", "-i", rtsp_url])
        logger.debug(f"[BUILD] Added input: {rtsp_url}")
    
    # Build filter complex for 2x2 grid
    filter_parts = []
    for i, cam in enumerate(cameras):
        filter_parts.append(
            f"[{i}:v]scale=960:540:force_original_aspect_ratio=decrease,"
            f"pad=960:540:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25[v{i}]"
        )
    
    # XStack for 2x2 layout
    stream_refs = "".join(f"[v{i}]" for i in range(len(cameras)))
    filter_parts.append(f"{stream_refs}xstack=inputs={len(cameras)}:layout=0_0|w0_0|0_h0|w0_h0[v]")
    
    filter_complex = ";".join(filter_parts)
    cmd.extend(["-filter_complex", filter_complex])
    
    # Map video
    cmd.extend(["-map", "[v]"])
    
    # No audio
    cmd.append("-an")
    
    # Video encoding (optimized for YouTube Live)
    cmd.extend([
        "-c:v", "libx264",
        "-preset", "faster",
        "-tune", "zerolatency",
        "-b:v", "2500k",
        "-maxrate", "3000k",
        "-bufsize", "6000k",
        "-r", "25",
        "-g", "50",
        "-keyint_min", "50",
        "-sc_threshold", "0",
        "-pix_fmt", "yuv420p",
    ])
    
    # Output to YouTube RTMP
    rtmp_dest = f"{rtmp_url}/{stream_key}"
    cmd.extend(["-f", "flv", rtmp_dest])
    
    logger.debug(f"[BUILD] RTMP destination: {rtmp_url}/****")
    logger.info(f"[BUILD] FFmpeg command built for {len(cameras)} cameras")
    
    return cmd


# ============================================
# Streamer Class
# ============================================

class YouTubeStreamer:
    """
    Manages FFmpeg process for YouTube streaming.
    
    Features:
    - Direct FFmpeg → YouTube RTMP (no go2rtc API)
    - Hourly restarts to create separate videos
    - Detailed logging at each step
    - Graceful shutdown handling
    """
    
    def __init__(self, cameras: list, stream_key: str, rotation_minutes: int = 60):
        self.cameras = cameras
        self.stream_key = stream_key
        self.rotation_minutes = rotation_minutes
        self.process = None
        self.segment_count = 0
        self.start_time = None
        self.running = False
        
        logger.info(f"[INIT] YouTubeStreamer initialized")
        logger.info(f"[INIT] Cameras: {cameras}")
        logger.info(f"[INIT] Rotation: {rotation_minutes} minutes")
    
    def start(self):
        """Start the FFmpeg streaming process."""
        if self.process and self.process.poll() is None:
            logger.warning("[START] Process already running, stopping first...")
            self.stop()
        
        logger.info("[START] Starting FFmpeg process...")
        
        cmd = build_ffmpeg_command(self.cameras, YOUTUBE_RTMP_URL, self.stream_key)
        
        try:
            # Start FFmpeg with stderr capture for error logging
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            self.start_time = time.time()
            self.segment_count += 1
            self.running = True
            
            logger.info(f"[START] ✅ FFmpeg started, PID: {self.process.pid}")
            logger.info(f"[START] 📺 Streaming to YouTube (Segment #{self.segment_count})")
            
            return True
            
        except Exception as e:
            logger.error(f"[START] ❌ Failed to start FFmpeg: {e}")
            return False
    
    def stop(self):
        """Stop the FFmpeg process gracefully."""
        if not self.process:
            return
        
        logger.info("[STOP] Stopping FFmpeg process...")
        
        try:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
                logger.info("[STOP] ✅ FFmpeg stopped gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("[STOP] Force killing FFmpeg...")
                self.process.kill()
                self.process.wait()
        except Exception as e:
            logger.error(f"[STOP] Error stopping FFmpeg: {e}")
        
        self.process = None
        self.running = False
    
    def is_running(self) -> bool:
        """Check if FFmpeg process is still running."""
        if not self.process:
            return False
        return self.process.poll() is None
    
    def check_process(self):
        """Check process status and log any errors."""
        if not self.process:
            return
        
        # Check if process died
        retcode = self.process.poll()
        if retcode is not None:
            # Process exited, read stderr for errors
            stderr_output = ""
            try:
                stderr_output = self.process.stderr.read()
            except:
                pass
            
            if retcode != 0:
                logger.error(f"[CHECK] ❌ FFmpeg exited with code {retcode}")
                if stderr_output:
                    # Log last 500 chars of stderr
                    logger.error(f"[CHECK] FFmpeg stderr: {stderr_output[-500:]}")
            else:
                logger.info(f"[CHECK] FFmpeg exited normally")
            
            self.running = False
    
    def time_for_restart(self) -> bool:
        """Check if it's time for hourly restart."""
        if not self.start_time:
            return False
        elapsed = time.time() - self.start_time
        return elapsed >= (self.rotation_minutes * 60)
    
    def restart(self):
        """Restart stream to create new YouTube video."""
        logger.info(f"[RESTART] 🔄 Restarting stream (creates new YouTube video)")
        
        self.stop()
        
        # Brief pause - YouTube needs time to finalize video
        logger.info("[RESTART] ⏸ Pausing 10s before restart...")
        time.sleep(10)
        
        # Start new stream
        return self.start()


# ============================================
# Main Service
# ============================================

def wait_for_go2rtc():
    """Wait for go2rtc to be ready."""
    import urllib.request
    
    api_url = f"http://127.0.0.1:{GO2RTC_API_PORT}/api"
    max_wait = 60
    
    logger.info(f"[WAIT] Waiting for go2rtc at {api_url}...")
    
    for i in range(max_wait):
        try:
            urllib.request.urlopen(api_url, timeout=2)
            logger.info(f"[WAIT] ✅ go2rtc ready after {i}s")
            return True
        except:
            time.sleep(1)
    
    logger.error(f"[WAIT] ❌ go2rtc not ready after {max_wait}s")
    return False


def main():
    """Main entry point."""
    logger.info("=" * 50)
    logger.info("[MAIN] YouTube Streamer Service Starting")
    logger.info("=" * 50)
    
    # Check if enabled
    if not YOUTUBE_LIVE_ENABLED:
        logger.info("[MAIN] YouTube Live is disabled (YOUTUBE_LIVE_ENABLED != true)")
        logger.info("[MAIN] Exiting...")
        return
    
    # Check stream key
    if not YOUTUBE_STREAM_KEY_1:
        logger.error("[MAIN] ❌ No stream key configured (YOUTUBE_STREAM_KEY_1)")
        logger.info("[MAIN] Exiting...")
        return
    
    logger.info(f"[MAIN] YouTube Live: ENABLED")
    logger.info(f"[MAIN] Grid size: {YOUTUBE_GRID} cameras")
    logger.info(f"[MAIN] Rotation: {YOUTUBE_ROTATION_MINUTES} minutes")
    logger.info(f"[MAIN] RTMP URL: {YOUTUBE_RTMP_URL}")
    
    # Wait for go2rtc
    if not wait_for_go2rtc():
        logger.error("[MAIN] Cannot proceed without go2rtc")
        return
    
    # Determine cameras for grid
    cameras = list(range(1, min(YOUTUBE_GRID, NUM_CHANNELS) + 1))
    logger.info(f"[MAIN] Cameras in grid: {cameras}")
    
    # Create streamer
    streamer = YouTubeStreamer(
        cameras=cameras,
        stream_key=YOUTUBE_STREAM_KEY_1,
        rotation_minutes=YOUTUBE_ROTATION_MINUTES
    )
    
    # Handle signals
    def signal_handler(sig, frame):
        logger.info(f"[MAIN] Received signal {sig}, shutting down...")
        streamer.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start streaming
    if not streamer.start():
        logger.error("[MAIN] Failed to start streamer")
        return
    
    # Main loop
    logger.info("[MAIN] Entering main loop...")
    retry_delay = 5
    
    while True:
        try:
            # Check if process is still running
            streamer.check_process()
            
            if not streamer.is_running():
                logger.warning(f"[MAIN] ⚠ Stream not running, restarting in {retry_delay}s...")
                time.sleep(retry_delay)
                if streamer.start():
                    retry_delay = 5  # Reset delay on success
                else:
                    retry_delay = min(retry_delay * 2, 60)  # Exponential backoff
                continue
            
            # Check for hourly restart
            if streamer.time_for_restart():
                streamer.restart()
            
            time.sleep(10)
            
        except KeyboardInterrupt:
            logger.info("[MAIN] Interrupted, shutting down...")
            break
        except Exception as e:
            logger.error(f"[MAIN] Error in main loop: {e}")
            time.sleep(5)
    
    streamer.stop()
    logger.info("[MAIN] YouTube Streamer Service stopped")


if __name__ == "__main__":
    main()
