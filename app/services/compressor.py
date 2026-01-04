"""
Background Compressor Service
Compresses TS recordings to H.265 and tracks in CSV.
"""

import threading
import os
import time
import glob
import subprocess
from core.config import settings
from core.logger import setup_logger
from utils.processed_videos_csv import is_in_csv, add_to_csv

logger = setup_logger("compressor", log_file="/logs/compressor.log")


class BackgroundCompressor(threading.Thread):
    """Compresses TS recordings to H.265 in-place."""
    
    def __init__(
        self, 
        record_dir: str, 
        video_codec: str = "libx265",
        crf: int = 30,
        preset: str = "medium"
    ):
        super().__init__()
        self.record_dir = record_dir
        self.video_codec = video_codec
        self.crf = crf
        self.preset = preset
        self.daemon = True
        self._running = True
        
        logger.info(
            f"Initialized BackgroundCompressor: "
            f"codec={video_codec}, crf={crf}, preset={preset}"
        )
    
    def is_file_stable(self, filepath: str, stable_seconds: int = 15) -> bool:
        """Check if file has stopped being written to."""
        try:
            mtime = os.path.getmtime(filepath)
            diff = time.time() - mtime
            return diff > stable_seconds
        except OSError:
            return False
    
    def get_file_size_mb(self, filepath: str) -> float:
        """Get file size in MB."""
        try:
            return os.path.getsize(filepath) / (1024 * 1024)
        except OSError:
            return 0.0
    
    def compress_ts(self, ts_path: str) -> bool:
        """
        Compress a TS file to H.265 in-place.
        Returns True if successful.
        """
        tmp_path = ts_path + ".tmp"
        
        logger.info(f"[⚙] Starting compression: {os.path.basename(ts_path)}")
        
        # Clean up any leftover temp file
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        
        # Build FFmpeg command
        cmd = [
            settings.ffmpeg_bin,
            "-y",
            "-i", ts_path,
            "-c:v", self.video_codec,
            "-crf", str(self.crf),
            "-preset", self.preset,
            "-c:a", "aac",
            "-f", "mpegts",  # Keep as TS format
            tmp_path
        ]
        
        try:
            start_time = time.time()
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800  # 30 minute timeout
            )
            duration = time.time() - start_time
            
            if result.returncode != 0:
                logger.error(
                    f"[✖] Compression failed for {os.path.basename(ts_path)}:\n"
                    f"{result.stderr[-1000:]}"
                )
                # Clean up temp file
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return False
            
            # Verify output exists and has content
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                logger.error(f"[✖] Compression output missing or empty: {tmp_path}")
                return False
            
            # Replace original with compressed version
            original_size = self.get_file_size_mb(ts_path)
            compressed_size = self.get_file_size_mb(tmp_path)
            
            os.replace(tmp_path, ts_path)  # Atomic replace
            
            # Add to CSV for upload tracking
            add_to_csv(ts_path, compressed_size)
            
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            
            logger.info(
                f"[✓] Compressed: {os.path.basename(ts_path)} "
                f"({original_size:.1f}MB → {compressed_size:.1f}MB, "
                f"-{compression_ratio:.0f}%, {duration:.1f}s)"
            )
            
            return True
            
        except subprocess.TimeoutExpired:
            logger.error(f"[✖] Compression timeout for {os.path.basename(ts_path)}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return False
        except Exception as e:
            logger.error(f"[✖] Compression error for {os.path.basename(ts_path)}: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            return False
    
    def run(self):
        """Main compression loop - runs continuously."""
        logger.info("[*] Background Compressor Started")
        logger.info(f"[*] Watching: {self.record_dir}")
        
        while self._running:
            try:
                # Find all TS files: record_dir/ch*/date/*.ts
                pattern = os.path.join(self.record_dir, "ch*", "*", "*.ts")
                files = glob.glob(pattern)
                
                # Filter: stable + not already in CSV
                candidates = []
                for f in files:
                    if f.endswith(".tmp"):
                        continue
                    if not self.is_file_stable(f):
                        continue
                    if is_in_csv(f):
                        continue
                    candidates.append(f)
                
                if candidates:
                    logger.debug(f"Found {len(candidates)} files to compress")
                    # Process all candidates
                    for f in candidates:
                        if not self._running:
                            break
                        self.compress_ts(f)
                else:
                    # No files to process, short sleep before next scan
                    time.sleep(5)
                    
            except Exception as e:
                logger.error(f"[!] Compressor scan error: {e}", exc_info=True)
                time.sleep(5)
        
        logger.info("[*] Background Compressor Stopped")
    
    def stop(self):
        """Stop the compressor."""
        self._running = False
