import threading
import os
import time
import glob
import subprocess
from core.config import settings
from core.logger import setup_logger

logger = setup_logger("converter", log_file="/logs/converter.log")

class BackgroundConverter(threading.Thread):
    def __init__(self, record_dir, interval=30, video_codec="copy", crf=23, preset="veryfast"):
        super().__init__()
        self.record_dir = record_dir
        self.interval = interval
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.daemon = True # Kills thread when main program exits
        logger.info(f"Initialized BackgroundConverter with interval={interval}s, codec={video_codec}, crf={crf}, preset={preset}")

    def is_file_stable(self, filepath):
        """Check if file has stopped growing/being written to."""
        try:
            mtime = os.path.getmtime(filepath)
            now = time.time()
            diff = now - mtime
            is_stable = diff > 15
            logger.debug(f"Checking stability for {os.path.basename(filepath)}: mtime={mtime}, now={now}, diff={diff:.2f}s, stable={is_stable}")
            return is_stable
        except OSError as e:
            logger.warning(f"OS error checking stability for {filepath}: {e}")
            return False

    def convert_to_mp4(self, mkv_path):
        mp4_path = os.path.splitext(mkv_path)[0] + ".mp4"
        tmp_path = mp4_path + ".tmp"
        
        logger.info(f"Processing candidate: {mkv_path}")

        # Skip if MP4 exists already
        if os.path.exists(mp4_path):
            logger.debug(f"Skipping {mkv_path} - MP4 already exists: {mp4_path}")
            return
        
        # Clean up any leftover temp file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Removed leftover tmp file: {tmp_path}")
            except OSError as e:
                logger.warning(f"Failed to remove leftover tmp file {tmp_path}: {e}")

        logger.info(f"[⚙] Starting conversion for: {os.path.basename(mkv_path)}")

        # Base arguments
        base_args = [
            settings.ffmpeg_bin,
            "-y", 
            "-i", mkv_path,
        ]
        
        # Encoding arguments
        encoding_args = []
        if self.video_codec == "copy":
             encoding_args.extend(["-c:v", "copy"])
        else:
             encoding_args.extend([
                 "-c:v", self.video_codec,
                 "-crf", str(self.crf),
                 "-preset", self.preset
             ])

        encoding_args.extend([
            "-c:a", "aac",
            "-movflags", "+faststart",
            "-f", "mp4",
            tmp_path
        ])

        def run_ffmpeg(extra_flags=[]):
            cmd = base_args + extra_flags + encoding_args
            cmd_str = " ".join(cmd)
            logger.debug(f"Executing FFmpeg command: {cmd_str}")
            return subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=1800
            )

        # Attempt 1: Standard conversion
        start_time = time.time()
        result = run_ffmpeg(["-v", "error"])
        duration = time.time() - start_time

        if result.returncode != 0:
            logger.warning(f"[!] Standard conversion failed for {mkv_path}. Duration: {duration:.2f}s. stderr: {result.stderr[:500]}")
            
            # Check for corruption signs
            corruption_errors = [
                "Invalid data found when processing input",
                "EBML header parsing failed",
                "moov atom not found",
                "matroska,webm"
            ]
            
            if any(err in result.stderr for err in corruption_errors) or result.returncode != 0:
                logger.info(f"[params] Check: {mkv_path} appears corrupted. Attempting recovery...")
                
                # Attempt 2: Recovery calculation
                # -err_detect ignore_err: ignore decoding errors
                logger.info(f"Attempting recovery for {mkv_path} with -err_detect ignore_err")
                result = run_ffmpeg(["-v", "error", "-err_detect", "ignore_err"])
                
                if result.returncode != 0:
                    logger.error(f"[✖] Recovery failed for {mkv_path}. Deleting unrecoverable file.")
                    try:
                        os.remove(mkv_path)
                        logger.info(f"[🗑] Deleted corrupted file: {os.path.basename(mkv_path)}")
                    except OSError as e:
                        logger.error(f"[!] Failed to delete corrupted file: {e}")
                    
                    # Clean up temp
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                            logger.info(f"Cleaned up temp file after failure: {tmp_path}")
                        except OSError as e:
                            logger.error(f"Failed to remove temp file {tmp_path}: {e}")
                    return
        else:
             logger.info(f"FFmpeg process completed successfully in {duration:.2f}s")

        # Explicit check if file was created successfully
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            try:
                os.rename(tmp_path, mp4_path)  # Atomic rename
                logger.info(f"Renamed {os.path.basename(tmp_path)} to {os.path.basename(mp4_path)}")
                
                os.remove(mkv_path)  # Delete original MKV
                logger.info(f"Deleted original MKV: {os.path.basename(mkv_path)}")
                
                logger.info(f"[✓] Successfully Converted: {os.path.basename(mp4_path)}")
            except OSError as e:
                logger.error(f"[!] Failed to finalize conversion (rename/delete): {e}")
        else:
            logger.error(f"Conversion failed: Output file missing or empty: {tmp_path}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                    logger.info(f"Removed invalid temp file: {tmp_path}")
                except OSError as e:
                    logger.warning(f"Failed to remove invalid temp file {tmp_path}: {e}")

    def run(self):
        logger.info("[*] Background Converter Started")
        while True:
            try:
                # Find all MKV files in the structure: record_dir/ch*/date/*.mkv
                pattern = os.path.join(self.record_dir, "ch*", "*", "*.mkv")
                files = glob.glob(pattern)
                
                if files:
                    logger.debug(f"Found {len(files)} MKV files scanned.")
                
                for f in files:
                    if self.is_file_stable(f):
                        self.convert_to_mp4(f)
                        
            except Exception as e:
                logger.error(f"[!] Converter scan error: {e}", exc_info=True)
            
            # Sleep but log it periodically if nothing is happening? 
            # Actually, let's just sleep quietly unless debug is on.
            time.sleep(self.interval)
