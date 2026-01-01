import threading
import os
import time
import glob
import subprocess
from core import config
from core.logger import setup_logger

logger = setup_logger("converter")

class BackgroundConverter(threading.Thread):
    def __init__(self, record_dir, interval=30, video_codec="copy", crf=23, preset="veryfast"):
        super().__init__()
        self.record_dir = record_dir
        self.interval = interval
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.daemon = True # Kills thread when main program exits

    def is_file_stable(self, filepath):
        """Check if file has stopped growing/being written to."""
        try:
            # If modified more than 15 seconds ago, assume recording is done
            return (time.time() - os.path.getmtime(filepath)) > 15
        except OSError:
            return False

    def convert_to_mp4(self, mkv_path):
        mp4_path = os.path.splitext(mkv_path)[0] + ".mp4"
        tmp_path = mp4_path + ".tmp"
        
        # Skip if MP4 exists already
        if os.path.exists(mp4_path):
            return
        
        # Clean up any leftover temp file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        logger.info(f"[⚙] Converting: {os.path.basename(mkv_path)}...")

        # Base arguments
        base_args = [
            config.FFMPEG_BIN,
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
            return subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=300
            )

        # Attempt 1: Standard conversion
        result = run_ffmpeg(["-v", "error"])

        if result.returncode != 0:
            logger.warning(f"[!] Standard conversion failed for {mkv_path}. stderr: {result.stderr[:200]}")
            
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
                        except OSError:
                            pass
                    return

        # Explicit check if file was created successfully
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
            try:
                os.rename(tmp_path, mp4_path)  # Atomic rename
                os.remove(mkv_path)  # Delete original MKV
                logger.info(f"[✓] Converted: {os.path.basename(mp4_path)}")
            except OSError as e:
                logger.error(f"[!] Failed to finalize conversion (rename/delete): {e}")
        else:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def run(self):
        logger.info("[*] Background Converter Started")
        while True:
            try:
                # Find all MKV files in the structure: record_dir/ch*/date/*.mkv
                pattern = os.path.join(self.record_dir, "ch*", "*", "*.mkv")
                files = glob.glob(pattern)
                
                for f in files:
                    if self.is_file_stable(f):
                        self.convert_to_mp4(f)
                        
            except Exception as e:
                logger.error(f"[!] Converter scan error: {e}")
            
            time.sleep(self.interval)
