#!/usr/bin/env python3
"""
YouTube Live Streaming Service
Manages FFmpeg processes to stream RTSP cameras to YouTube.
Supports Grid mode (combining cameras) and Multi-Key mode.
Restarts streams every 11 hours.
Uses canvas-based approach for maximum stability.
"""
import os
import sys
import time
import signal
import subprocess
import logging
import math
import threading
import re
from datetime import datetime
from logging.handlers import RotatingFileHandler
from services.youtube_video_sync import YouTubeVideoSync
from core import config

# ============================================
# Configuration
# ============================================

def get_env(name, default=None):
    return os.getenv(name, default)

YOUTUBE_LIVE_ENABLED = get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"
YOUTUBE_RTMP_URL = get_env("YOUTUBE_RTMP_URL")
YOUTUBE_GRID = int(get_env("YOUTUBE_GRID"))
NUM_CHANNELS = int(get_env("NUM_CHANNELS"))

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
        # Stream health monitoring
        self.last_frame_time = None
        self.error_count = 0
        self.rtmp_errors = []
        # Frame stall detection - track actual frame count, not just output
        self.last_frame_count = 0
        self.last_frame_count_time = None
    
    def build_cmd(self):
        rtmp = f"{YOUTUBE_RTMP_URL}/{self.job.key}"
        
        cmd = [
            "ffmpeg",
            "-hide_banner", "-loglevel", "warning",
            "-stats",  # Output encoding stats continuously (for health monitoring)
            "-stats_period", "5",  # Stats every 5 seconds
            "-threads", "0"  # Use all CPU cores
        ]
        
        # Inputs - with proper per-input RTSP flags and error handling
        for cam_idx in self.job.cameras:
            rtsp = f"rtsp://127.0.0.1:{GO2RTC_RTSP_PORT}/cam{cam_idx}"
            cmd.extend([
                "-rtsp_transport", "tcp",
                "-rtsp_flags", "prefer_tcp",
                "-timeout", "5000000",  # 5 second timeout (microseconds)
                "-fflags", "+genpts+igndts+discardcorrupt+nobuffer",  # Better live handling
                "-flags", "low_delay",  # Reduce latency
                "-thread_queue_size", "1024",  # Input buffer for stability
                "-err_detect", "ignore_err",  # Ignore decoding errors
                "-max_delay", "500000",  # 0.5 second max delay
                "-probesize", "1000000",  # For stream detection
                "-analyzeduration", "1000000",
                "-i", rtsp
            ])
            
        # Audio Source (Silent but required by YouTube)
        audio_input_idx = len(self.job.cameras)
        cmd.extend(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"])
        
        # Filter / Mapping
        if len(self.job.cameras) == 1:
            # Single camera - scale to 2560x1440 with proper aspect ratio handling
            filter_complex = "[0:v]scale=2560:1440:force_original_aspect_ratio=decrease,pad=2560:1440:(ow-iw)/2:(oh-ih)/2,fps=25,setsar=1[v]"
            cmd.extend(["-filter_complex", filter_complex])
            cmd.extend(["-map", "[v]", "-map", f"{audio_input_idx}:a"])
        else:
            # Grid Layout - CANVAS APPROACH for stability
            n = len(self.job.cameras)
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            
            log.info(f"📐 Creating {rows}x{cols} grid for {n} cameras using CANVAS method")
            
            # Calculate cell dimensions for 2560x1440 output
            cell_w = 2560 // cols
            cell_h = 1440 // rows
            
            log.info(f"📏 Cell size: {cell_w}x{cell_h}")
            
            # Build filter complex with canvas approach
            filter_parts = []
            
            # Step 1: Normalize each camera to cell size with same settings
            for i in range(n):
                filter_parts.append(
                    f"[{i}:v]scale={cell_w}:{cell_h}:force_original_aspect_ratio=decrease,"
                    f"pad={cell_w}:{cell_h}:(ow-iw)/2:(oh-ih)/2,"
                    f"fps=25,setsar=1[v{i}]"
                )
            
            # Step 2: Create blank canvas at 2560x1440
            filter_parts.append(
                f"color=c=black:s=2560x1440:r=25[base]"
            )
            
            # Step 3: Overlay each normalized camera onto canvas
            current_layer = "base"
            for i in range(n):
                row = i // cols
                col = i % cols
                x = col * cell_w
                y = row * cell_h
                
                next_layer = f"tmp{i}" if i < n - 1 else "v"
                # eof_action=pass: Keep going if this camera dies
                # repeatlast=1: Repeat last frame if camera freezes
                filter_parts.append(
                    f"[{current_layer}][v{i}]overlay={x}:{y}:eof_action=pass:repeatlast=1[{next_layer}]"
                )
                current_layer = next_layer
            
            filter_complex = ";".join(filter_parts)
            
            log.info(f"🎨 Canvas layout: {rows}x{cols} grid with {cell_w}x{cell_h} cells")
            log.debug(f"Filter: {filter_complex}")
            
            cmd.extend(["-filter_complex", filter_complex])
            cmd.extend(["-map", "[v]", "-map", f"{audio_input_idx}:a"])

        # Encoding Settings - OPTIMIZED FOR YOUTUBE
        cmd.extend([
            # Video codec settings
            "-c:v", "libx264", 
            "-preset", "ultrafast",  # Changed from "veryfast" for less CPU
            "-tune", "zerolatency",
            "-profile:v", "main",           # Better compatibility than "high"
            "-level", "4.2",                # Higher resolution support
            "-pix_fmt", "yuv420p",
            
            # Bitrate settings (YouTube recommends 13.5 Mbps for 1440p)
            "-b:v", "10000k",   # 10 Mbps target
            "-maxrate", "12000k",  # Allow bursts up to 12 Mbps
            "-bufsize", "16000k",  # 2 seconds of buffer at max rate
            
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
            "-f", "flv",
            "-flvflags", "no_duration_filesize",
            rtmp
        ])
        
        return cmd

    def _log_ffmpeg_output(self):
        """Monitor FFmpeg output in real-time and detect stream health"""
        try:
            for line in self.process.stdout:
                line = line.strip()
                if not line:
                    continue
                
                # Update last activity time for ANY output
                self.last_frame_time = time.time()
                
                # Check for RTMP errors indicating YouTube rejected stream
                rtmp_error_indicators = [
                    "Connection refused",
                    "Server error",
                    "RTMP error",
                    "Failed to update header",
                    "I/O error",
                    "Broken pipe",
                    "Connection reset",
                    "Unable to write frame",
                    "Cannot read RTMP handshake",
                    "Connection timed out",
                    "End of file",
                    "Write error",
                    "Input/output error"
                ]
                
                if any(indicator.lower() in line.lower() for indicator in rtmp_error_indicators):
                    self.error_count += 1
                    self.rtmp_errors.append(line)
                    log.error(f"FFmpeg RTMP ERROR ({self.error_count}): {line}")
                    
                    # If we get multiple RTMP errors, stream is likely rejected
                    if self.error_count >= 3:
                        log.error(f"❌ Multiple RTMP errors detected - YouTube likely rejected stream")
                
                # Log errors (but filter out recoverable ones)
                elif "error" in line.lower() and not any(x in line.lower() for x in ["deprecated", "recoverable"]):
                    log.error(f"FFmpeg ERROR: {line}")
                # Log warnings (but reduce noise)
                elif "warning" in line.lower():
                    log.debug(f"FFmpeg WARNING: {line}")
                # Progress indicators - extract frame count for stall detection
                elif any(x in line.lower() for x in ["frame=", "fps=", "time=", "bitrate=", "speed="]):
                    # Extract frame count to detect stalls
                    frame_match = re.search(r'frame=\s*(\d+)', line)
                    if frame_match:
                        current_frame = int(frame_match.group(1))
                        # Only update timestamp if frame count actually increased
                        if current_frame > self.last_frame_count:
                            self.last_frame_count = current_frame
                            self.last_frame_count_time = time.time()
                    
                    # Only log progress every 30 seconds to reduce spam
                    if not hasattr(self, '_last_progress_log'):
                        self._last_progress_log = 0
                    if time.time() - self._last_progress_log > 30:
                        log.debug(f"FFmpeg progress: {line}")
                        self._last_progress_log = time.time()
                else:
                    log.debug(f"FFmpeg: {line}")
        except Exception as e:
            log.error(f"Error monitoring FFmpeg output: {e}")

    def start(self):
        if self.process and self.process.poll() is None:
            self.stop()
        
        # Reset health monitoring counters
        self.error_count = 0
        self.rtmp_errors = []
        self.last_frame_time = time.time()
        # Reset frame stall detection
        self.last_frame_count = 0
        self.last_frame_count_time = time.time()
            
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
                bufsize=1,  # Line buffered
                start_new_session=True  # Create new process group so we can kill all children
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
            
            return True
            
        except Exception as e:
            log.error(f"❌ Failed to start stream: {e}")
            return False

    def stop(self):
        if not self.process:
            log.debug("stop() called but no process exists")
            return
            
        pid = self.process.pid
        log.info(f"⏹ Stopping stream for cams {self.job.cameras} (PID: {pid})...")
        # -----------------------------------------------

        try:
            # Step 1: Get process group ID
            pgid = os.getpgid(pid)
            log.info(f"📌 Process group ID: {pgid}")
            
            # Step 2: Send SIGTERM to entire process group
            log.info(f"🔪 Sending SIGTERM to process group {pgid}...")
            os.killpg(pgid, signal.SIGTERM)
            
            # Step 3: Wait for graceful shutdown
            log.info(f"⏳ Waiting up to 10s for process to exit...")
            self.process.wait(timeout=10)
            log.info(f"✅ Process {pid} stopped gracefully")
            
        except subprocess.TimeoutExpired:
            log.warning(f"⚠️ Process {pid} didn't exit in 10s, force killing...")
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
                log.info(f"💀 Sent SIGKILL to process group {pgid}")
            except Exception as e:
                log.warning(f"killpg failed: {e}, killing process directly")
                self.process.kill()
                
        except Exception as e:
            log.warning(f"⚠️ Graceful stop failed: {e}, force killing...")
            try:
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGKILL)
                log.info(f"💀 Sent SIGKILL to process group {pgid}")
            except Exception as e2:
                log.warning(f"killpg failed: {e2}, killing process directly")
                self.process.kill()
                
        self.process = None
        log.info(f"✅ Stream stopped for cams {self.job.cameras}")

    def is_running(self):
        return self.process and self.process.poll() is None


    def check_stream_health(self):
        """Check stream health without YouTube API"""
        if not self.is_running():
            return False
        
        # Don't check health during initial startup (first 2 minutes)
        if not self.start_time or (time.time() - self.start_time) < 120:
            return True  # Assume healthy during initialization
        
        # Method 1: Check for multiple RTMP errors
        if self.error_count >= 5:
            log.error(f"❌ Stream unhealthy: {self.error_count} RTMP errors detected")
            return False
        
        # Method 2: Check if FFmpeg is stalled (no output for 2 minutes)
        if self.last_frame_time:
            time_since_activity = time.time() - self.last_frame_time
            if time_since_activity > 120:  # 2 minutes
                log.error(f"❌ Stream unhealthy: No FFmpeg activity for {int(time_since_activity)}s")
                return False
        
        # Method 3: Check if frame count stopped increasing (encoding stalled)
        # This catches cases where FFmpeg is running but not encoding new frames
        if self.last_frame_count_time:
            time_since_frame_increase = time.time() - self.last_frame_count_time
            if time_since_frame_increase > 60:  # 60 seconds with no new frames
                log.error(f"❌ Stream unhealthy: Frame count stuck at {self.last_frame_count} for {int(time_since_frame_increase)}s (encoding stalled)")
                return False
        
        return True

class StreamManager:
    def __init__(self):
        self.streamers = []
        self.video_sync = YouTubeVideoSync(recordings_dir=RECORD_DIR)
        
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
        
        # Map cameras to keys - using active channels from config
        available_cameras = config.get_active_channels()
        
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
                log.info(f"🔄 Restarting stream in 10 seconds...")
                time.sleep(10)
                s.start()
            elif not s.check_stream_health():
                # YouTube rejected the stream or it's not live anymore
                log.warning(f"⚠️ YouTube health check failed for {s.job}")
                log.info(f"🔄 Restarting stream to recover...")
                s.stop()
                time.sleep(10)
                s.start()
            else:
                # Periodic health log
                if s.start_time and (time.time() - s.start_time) > 300:  # 5 minutes
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
    log.info("🎬 YouTube Streaming Service (Canvas-Based)")
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
    
    # Sync YouTube videos to CSV (non-blocking)
    log.info("📺 Syncing YouTube videos to CSV...")
    threading.Thread(target=manager.video_sync.sync_to_csv, daemon=True).start()
        
    log.info("All streams started. Monitoring...")
        
    # Monitoring loop
    while True:
        manager.monitor()
        time.sleep(10)

if __name__ == "__main__":
    main()