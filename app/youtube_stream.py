#!/usr/bin/env python3
"""
YouTube Live Streaming Service
Manages FFmpeg processes to stream RTSP cameras to YouTube.
Supports Grid mode (combining cameras) and Multi-Key mode.
Restarts streams every 11 hours.
"""
import os
import sys
import time
import signal
import subprocess
import logging
import math
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from services.youtube_logger import YouTubeLogger

# ============================================
# Configuration
# ============================================

def get_env(name, default=None):
    return os.getenv(name, default)

YOUTUBE_LIVE_ENABLED = get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"
YOUTUBE_RTMP_URL = get_env("YOUTUBE_RTMP_URL")
YOUTUBE_GRID = int(get_env("YOUTUBE_GRID"))
NUM_CHANNELS = int(get_env("NUM_CHANNELS"))
ROTATION_HOURS = int(get_env("YOUTUBE_ROTATION_HOURS"))
ROTATION_SECONDS = ROTATION_HOURS * 3600

GO2RTC_RTSP_PORT = int(get_env("GO2RTC_RTSP_PORT"))
GO2RTC_API_PORT = int(get_env("GO2RTC_API_PORT"))
RECORD_DIR = get_env("RECORD_DIR")

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
# Core Logic
# ============================================

class StreamJob:
    def __init__(self, key, cameras):
        self.key = key
        self.cameras = cameras  # List of camera indices (1-based)
        
    def __str__(self):
        return f"Job(Key=...{self.key[-4:]}, Cams={self.cameras})"

class YouTubeStreamer:
    def __init__(self, job):
        self.job = job
        self.process = None
        self.start_time = None
        self.start_datetime = None
        self.segment = 0
        self.video_id = None
        # Initialize Logger (assumes credentials in current dir or standard fallback)
        self.logger = YouTubeLogger(recordings_dir=RECORD_DIR)
    
    def build_cmd(self):
        rtmp = f"{YOUTUBE_RTMP_URL}/{self.job.key}"
        
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning"
        ]
        
        # Inputs - with proper per-input RTSP flags
        for cam_idx in self.job.cameras:
            rtsp = f"rtsp://127.0.0.1:{GO2RTC_RTSP_PORT}/cam{cam_idx}"
            cmd.extend([
                "-rtsp_transport", "tcp",
                "-rtsp_flags", "prefer_tcp",
                "-timeout", "5000000",  # 5 second timeout (microseconds)
                "-fflags", "+genpts+igndts",
                "-i", rtsp
            ])
            
        # Audio Source (Silent but required by YouTube)
        audio_input_idx = len(self.job.cameras)
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        
        # Filter / Mapping
        if len(self.job.cameras) == 1:
            # Single camera - scale to 2560x1440 with proper aspect ratio handling
            filter_complex = "[0:v]scale=2560:1440:force_original_aspect_ratio=decrease,pad=2560:1440:(ow-iw)/2:(oh-ih)/2,fps=25[v]"
            cmd.extend(["-filter_complex", filter_complex])
            cmd.extend(["-map", "[v]", "-map", f"{audio_input_idx}:a"])
        else:
            # Grid Layout
            n = len(self.job.cameras)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            
            log.info(f"📐 Creating {rows}x{cols} grid for {n} cameras")
            
            # Build xstack layout with proper syntax
            layout_parts = []
            for i in range(n):
                row = i // cols
                col = i % cols
                
                if col == 0:
                    x_pos = "0"
                else:
                    # Sum widths of cameras to the left in the same row
                    x_pos = "+".join([f"w{row*cols + j}" for j in range(col)])
                
                if row == 0:
                    y_pos = "0"
                else:
                    # Sum heights of cameras directly above in the same column
                    y_pos = "+".join([f"h{j*cols + col}" for j in range(row)])
                
                layout_parts.append(f"{x_pos}_{y_pos}")
            
            layout = "|".join(layout_parts)
            # Scale to 1440p (2560x1440) with proper aspect ratio and padding
            filter_complex = f"xstack=inputs={n}:layout={layout}[bg];[bg]scale=2560:1440:force_original_aspect_ratio=decrease,pad=2560:1440:(ow-iw)/2:(oh-ih)/2,fps=25[v]"
            
            log.info(f"🎨 xstack layout: {layout} + scale=2560:1440")
            
            cmd.extend(["-filter_complex", filter_complex])
            cmd.extend(["-map", "[v]", "-map", f"{audio_input_idx}:a"])

        # Encoding Settings - OPTIMIZED FOR YOUTUBE
        cmd.extend([
            # Video codec settings
            "-c:v", "libx264", 
            "-preset", "veryfast", 
            "-tune", "zerolatency",
            "-profile:v", "main",           # Better compatibility than "high"
            "-level", "4.2",                # Changed from 4.1 to 4.2 for higher resolution support
            "-pix_fmt", "yuv420p",
            
            # Bitrate settings
            "-b:v", "6000k", 
            "-maxrate", "8000k", 
            "-bufsize", "12000k",
            
            # Frame rate and keyframe settings (CRITICAL FOR YOUTUBE)
            "-r", "25",                     # 25 fps output
            "-g", "50",                     # Keyframe every 2 seconds (25fps * 2)
            "-keyint_min", "25",            # Minimum keyframe interval
            "-sc_threshold", "0",           # Disable scene change detection
            
            # Audio settings
            "-c:a", "aac", 
            "-b:a", "128k",
            "-ar", "44100",                 # Force audio sample rate
            "-ac", "2",                     # Force stereo
            
            # Stream settings
            "-shortest",
            "-f", "flv",
            "-flvflags", "no_duration_filesize",
            rtmp
        ])
        
        return cmd

    def _log_ffmpeg_output(self):
        """Monitor FFmpeg output in real-time"""
        try:
            for line in self.process.stdout:
                line = line.strip()
                if line:
                    if "error" in line.lower():
                        log.error(f"FFmpeg ERROR: {line}")
                    elif "warning" in line.lower():
                        log.warning(f"FFmpeg WARNING: {line}")
                    else:
                        log.debug(f"FFmpeg: {line}")
        except:
            pass

    def start(self):
        if self.process and self.process.poll() is None:
            self.stop()
            
        cmd = self.build_cmd()
        cam_str = ",".join(map(str, self.job.cameras))
        log.info(f"🎥 Starting stream for cams [{cam_str}]")
        
        # Print full command for debugging
        full_cmd = ' '.join(cmd)
        log.info(f"📝 Full FFmpeg command:")
        log.debug(full_cmd)
        
        try:
            self.process = subprocess.Popen(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.STDOUT,  # Redirect stderr to stdout
                text=True,
                bufsize=1  # Line buffered
            )
            self.start_time = time.time()
            self.start_datetime = datetime.now() # Capture valid start time
            self.segment += 1
            
            # Start background thread to monitor FFmpeg output
            monitor_thread = threading.Thread(
                target=self._log_ffmpeg_output, 
                daemon=True,
                name=f"FFmpeg-Monitor-{self.process.pid}"
            )
            monitor_thread.start()
            
            # Brief health check
            time.sleep(5)
            if self.process.poll() is not None:
                log.error(f"❌ FFmpeg crashed immediately for cams [{cam_str}]")
                return False
            
            log.info(f"✅ Stream process started (PID: {self.process.pid}) Segment #{self.segment}")
            log.info(f"⏳ Waiting 15 seconds for initial stream stabilization...")
            
            # Shorter initial wait - just enough for stream to stabilize
            time.sleep(15)
            
            # Final check
            if self.process.poll() is not None:
                log.error(f"❌ FFmpeg died during initialization")
                return False
                
            log.info(f"✅ Stream initialized. YouTube should process it within 30-60 seconds.")
            log.info(f"💡 If stream doesn't appear on YouTube, it will auto-restart in next monitoring cycle")
                
            log.info(f"🎉 Stream should be LIVE now on YouTube!")
            
            # --- LOG LIVE STREAM to CSV ---
            channel_name = f"Channel {self.job.cameras[0]}"
            try:
                self.video_id = self.logger.get_live_video_id()
                if self.video_id:
                     self.logger.log_live(channel_name, self.start_datetime, self.video_id)
                else:
                     log.warning("⚠️ Could not fetch live video ID (API might say 'incorrect broadcast status')")
            except Exception as e:
                log.error(f"⚠️ Failed to log live stream to CSV: {e}")
            # -----------------------------
            
            return True
            
        except Exception as e:
            log.error(f"❌ Failed to start stream: {e}")
            return False

    def stop(self):
        if not self.process:
            return
            
        # --- LOG VOD to CSV (before clearing process) ---
        if self.video_id and self.start_datetime:
             channel_name = f"Channel {self.job.cameras[0]}"
             try:
                 self.logger.log_vod(channel_name, self.start_datetime, datetime.now(), self.video_id)
                 log.info(f"📝 Logged VOD for {channel_name} (ID: {self.video_id})")
             except Exception as e:
                 log.error(f"⚠️ Failed to log VOD to CSV: {e}")
        # -----------------------------------------------

        log.info(f"⏹ Stopping stream for cams {self.job.cameras}...")
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
    
    def check_stream_health(self):
        """Check if stream is actually live on YouTube"""
        if not self.is_running():
            return False
        
        # Don't check health during initial startup (first 2 minutes)
        if not self.start_time or (time.time() - self.start_time) < 120:
            return True  # Assume healthy during initialization
        
        # Only check every 5 minutes to avoid API rate limits
        if not hasattr(self, '_last_health_check'):
            self._last_health_check = 0
        
        if (time.time() - self._last_health_check) < 300:  # 5 minutes
            return True  # Use cached result
        
        self._last_health_check = time.time()
        
        # Check if stream is actually live on YouTube
        try:
            video_id = self.logger.get_live_video_id()
            if not video_id:
                log.warning(f"⚠️ YouTube API reports no live video for {self.job}")
                return False
            
            # If we have a video_id but it's different from our stored one, something changed
            if self.video_id and video_id != self.video_id:
                log.warning(f"⚠️ YouTube video ID changed! Old: {self.video_id}, New: {video_id}")
                return False
            
            log.debug(f"✅ YouTube health check passed for {self.job}")
            return True
            
        except Exception as e:
            log.error(f"❌ YouTube health check failed: {e}")
            # Don't kill stream on API errors - might be temporary
            return True

class StreamManager:
    def __init__(self):
        self.streamers = []
        
    def discover_config(self):
        keys = []
        idx = 1
        while True:
            k = get_env(f"YOUTUBE_STREAM_KEY_{idx}")
            if not k:
                break
            keys.append(k)
            idx += 1
            
        if not keys:
            log.error("❌ No YOUTUBE_STREAM_KEY_* found!")
            return False
            
        log.info(f"Found {len(keys)} stream key(s)")
        log.info(f"Grid size: {YOUTUBE_GRID}, Total cameras: {NUM_CHANNELS}")
        
        # Map cameras to keys
        available_cameras = list(range(1, NUM_CHANNELS + 1))
        
        # Create jobs
        for i, key in enumerate(keys):
            if not available_cameras:
                break
            
            # Take up to YOUTUBE_GRID cameras for this key
            chunk = available_cameras[:YOUTUBE_GRID]
            available_cameras = available_cameras[YOUTUBE_GRID:]
            
            job = StreamJob(key, chunk)
            self.streamers.append(YouTubeStreamer(job))
            log.info(f"Stream {i+1}: Cameras {chunk} -> Key ending ...{key[-4:]}")
            
        if available_cameras:
            log.warning(f"⚠️ Not enough keys for all cameras! Unassigned: {available_cameras}")
            
        return True

    def monitor(self):
        for s in self.streamers:
            if not s.is_running():
                log.warning(f"⚠️ Stream died: {s.job}")
                log.info(f"🔄 Restarting stream in 5 seconds...")
                time.sleep(5)
                s.start()
            elif s.needs_restart():
                log.info(f"🔄 Scheduled rotation for stream: {s.job}")
                s.stop()
                time.sleep(5)
                s.start()
            elif not s.check_stream_health():
                # YouTube rejected the stream or it's not live anymore
                log.warning(f"⚠️ YouTube health check failed for {s.job}")
                log.info(f"🔄 Restarting stream to recover...")
                s.stop()
                time.sleep(5)
                s.start()
            else:
                # Check if stream has been running for a while (health check)
                if s.start_time and (time.time() - s.start_time) > 300:  # 5 minutes
                    # Periodic health log
                    uptime_mins = int((time.time() - s.start_time) / 60)
                    if uptime_mins % 30 == 0:  # Log every 30 minutes
                        log.info(f"💚 Stream healthy: {s.job} - Uptime: {uptime_mins} minutes")

    def stop_all(self):
        for s in self.streamers:
            s.stop()

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
            log.info("✅ go2rtc ready")
            return True
        except:
            time.sleep(1)
    log.error("❌ go2rtc not ready after 60s")
    return False

def main():
    log.info("=" * 50)
    log.info("🎬 YouTube Streaming Service (Multi/Grid)")
    log.info("=" * 50)
    
    if not YOUTUBE_LIVE_ENABLED:
        log.info("ℹ️ YouTube disabled (YOUTUBE_LIVE_ENABLED=false). Exiting.")
        return

    if not wait_for_go2rtc():
        return

    manager = StreamManager()
    if not manager.discover_config():
        return

    def shutdown(sig, frame):
        log.info("🛑 Shutting down...")
        manager.stop_all()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    # Initial start
    log.info("Starting all streams...")
    for s in manager.streamers:
        s.start()
        time.sleep(2)  # Stagger starts
        
    log.info("All streams started. Monitoring...")
        
    # Monitoring loop
    while True:
        manager.monitor()
        time.sleep(10)

if __name__ == "__main__":
    main()