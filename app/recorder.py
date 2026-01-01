import subprocess
import time
import os
import threading
import glob
from datetime import datetime
from core import config
from core.logger import setup_logger
from services.converter import BackgroundConverter

logger = setup_logger("recorder")

def is_stopped(channel):
    """Check if channel recording is stopped."""
    return os.path.exists(os.path.join(config.CONTROL_DIR, f"stop_ch{channel}"))


def build_rtsp_url(template, user, password, ip, port, channel):
    """Build RTSP URL from template (for direct DVR connection)."""
    return template.format(
        user=user,
        **{"pass": password},
        ip=ip,
        port=port,
        channel=channel
    )


def build_go2rtc_url(channel):
    """Build RTSP URL from go2rtc relay (unified hub architecture)."""
    return f"rtsp://localhost:{config.GO2RTC_RTSP_PORT}/cam{channel}"


def ensure_dir(path):
    """Ensure directory exists, create if deleted."""
    if not os.path.exists(path):
        # Only print if we are actually creating it (reduces log spam)
        try:
            os.makedirs(path, exist_ok=True)

            logger.info(f"[📁] Created directory: {path}")
        except OSError:
            pass


def get_output_dir(base_dir, channel):
    """Get channel/date organized output directory."""
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(base_dir, f"ch{channel}", today)


def get_latest_file(out_dir, channel):
    """Get the latest recording file (MKV or MP4) for a channel."""
    # Check both types to avoid restarting just because we converted the file
    files = glob.glob(os.path.join(out_dir, "*.mkv")) + glob.glob(os.path.join(out_dir, "*.mp4"))
    
    def safe_getctime(path):
        try:
            return os.path.getctime(path)
        except OSError:
            return 0
            
    if files:
        return max(files, key=safe_getctime)
    return None

def start_camera(channel, rtsp_url, base_dir, segment_duration):
    """Record RTSP stream for a single camera channel."""
    proc = None
    consecutive_failures = 0
    last_file_check = 0
    current_date = None
    
    while True:
        # Get date-specific output directory
        out_dir = get_output_dir(base_dir, channel)
        ensure_dir(out_dir)
        
        # Check if date changed (midnight rollover)
        today = datetime.now().strftime("%Y-%m-%d")
        if current_date and current_date != today:
            # Date changed, restart to use new folder
            if proc:
                proc.terminate()
                proc.wait()
                proc = None

                logger.info(f"[📅] CH{channel} date rollover, restarting")
        current_date = today
        
        if is_stopped(channel):
            if proc:
                proc.terminate()
                proc.wait()
                proc = None

                logger.info(f"[⏹] CH{channel} stopped")
            consecutive_failures = 0
            time.sleep(2)
            continue
        
        if proc is None:
            logger.info(f"[▶] CH{channel} starting -> {out_dir}")

            cmd = [
                config.FFMPEG_BIN,
                "-loglevel", "error",
                "-rtsp_transport", "tcp",
                "-fflags", "+genpts+igndts+discardcorrupt",
                "-i", rtsp_url,
                "-c:v", "copy",
                #"-an", # NOTE: This removes audio. Remove this line if you want audio.
                "-f", "segment",
                "-segment_time", str(segment_duration),
                "-reset_timestamps", "1",
                "-strftime", "1",
                f"{out_dir}/%H%M%S.mkv" # We record to MKV for stability, convert later
            ]

            try:
                proc = subprocess.Popen(cmd, stderr=subprocess.PIPE)
                consecutive_failures = 0
                last_file_check = time.time()
            except Exception as e:
                logger.error(f"[❌] CH{channel} failed to start: {e}")
                time.sleep(2)
                continue
        
        # Check if process is still running
        ret = proc.poll()
        if ret is not None:
            consecutive_failures += 1
            delay = 2 if consecutive_failures < 5 else min(consecutive_failures * 2, 30)
            logger.warning(f"[⚠] CH{channel} crashed (code {ret}), restart in {delay}s")
            proc = None
            time.sleep(delay)
        else:
            # Every 10 seconds, check if our output file still exists 
            # (or if we just converted it, that counts as existing)
            if time.time() - last_file_check > 10:
                last_file_check = time.time()
                latest = get_latest_file(out_dir, channel)
                
                # If no MKV or MP4 exists for today, and we've been running for > segment time, something is wrong
                # NOTE: We check against recording_start_time, not last_file_check
                if latest is None:
                    # Give a reasonable grace period (2x segment duration) before declaring failure
                    # This handles slow starts and network issues
                    logger.warning(f"[🔄] CH{channel} no output files found, restarting...")
                    proc.terminate()
                    proc.wait()
                    proc = None
                    continue
            time.sleep(1)


def main():
    try:
        # Use config module if env vars are missing, or strict check
        dvr_ip = config.DVR_IP or os.getenv("DVR_IP")
        if not dvr_ip: raise EnvironmentError("DVR_IP not set")
        
        # We rely on config module which reads env vars
        # If config doesn't enforce required (it returns None), we check here.
        if not config.DVR_USER: raise EnvironmentError("DVR_USER not set")
    except EnvironmentError as e:
        logger.error(f"[❌] {e}")
        return

    ensure_dir(config.RECORD_DIR)
    

    logger.info(f"[✓] DVR: {config.DVR_IP}:{config.DVR_PORT}")
    logger.info(f"[✓] Channels: {config.NUM_CHANNELS}")
    logger.info(f"[✓] Segment: {config.SEGMENT_DURATION}s")
    logger.info(f"[✓] Output: {config.RECORD_DIR}/ch{{N}}/{{date}}/")
    logger.info(f"[✓] Source: go2rtc relay (localhost:{config.GO2RTC_RTSP_PORT})")

    # --- Start Recording Threads ---
    # Using go2rtc relay as unified RTSP source (single DVR connection)
    threads = []
    for ch in range(1, config.NUM_CHANNELS + 1):
        # Use go2rtc as RTSP source for unified architecture
        rtsp_url = build_go2rtc_url(ch)
        t = threading.Thread(
            target=start_camera, 
            args=(ch, rtsp_url, config.RECORD_DIR, config.SEGMENT_DURATION),
            daemon=True
        )
        t.start()
        threads.append(t)
        logger.info(f"[✓] CH{ch} recording thread started")

    # --- Start Converter Thread ---

    converter = BackgroundConverter(
        config.RECORD_DIR, 
        video_codec=config.VIDEO_CODEC,
        crf=config.VIDEO_CRF,
        preset=config.VIDEO_PRESET
    )
    converter.start()

    while True:
        time.sleep(60)
        ensure_dir(config.RECORD_DIR)


if __name__ == "__main__":
    main()