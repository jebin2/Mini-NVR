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
        
        # Clean up any leftover temp file from failed previous attempt
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass

        logger.info(f"[⚙] Converting: {os.path.basename(mkv_path)}...")

        cmd = [
            config.FFMPEG_BIN,
            "-y", "-v", "error",
            "-i", mkv_path,
        ]

        if self.video_codec == "copy":
             cmd.extend(["-c:v", "copy"])       # Copy video stream (NO RE-ENCODING, FAST)
        else:
             # Re-encode with specified parameters
             cmd.extend([
                 "-c:v", self.video_codec,
                 "-crf", str(self.crf),
                 "-preset", self.preset
             ])

        cmd.extend([
            "-c:a", "aac",        # Ensure audio is AAC (Browser compatible)
            "-movflags", "+faststart", # Move metadata to front for streaming
            tmp_path  # Write to temp file first
        ])

        try:
            subprocess.run(cmd, check=True, timeout=300)
            
            # Verify success and atomically rename
            if os.path.exists(tmp_path) and os.path.getsize(tmp_path) > 0:
                os.rename(tmp_path, mp4_path)  # Atomic rename
                os.remove(mkv_path)  # Delete original MKV
                logger.info(f"[✓] Converted: {os.path.basename(mp4_path)}")
            else:
                logger.warning(f"[!] Conversion failed (empty output): {mp4_path}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                
        except Exception as e:
            logger.error(f"[!] Conversion error for {mkv_path}: {e}")
            # Clean up temp file on error
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
