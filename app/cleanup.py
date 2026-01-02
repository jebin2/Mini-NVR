import os
import time
import glob
from core import config
from core.logger import setup_logger

logger = setup_logger("cleanup")

CHECK_INTERVAL = config.settings.cleanup_interval

def get_size_gb(path):
    """Calculate total size of directory in GB."""
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 ** 3)


def get_all_recordings(path):
    """Get all recording files sorted by creation time (oldest first)."""
    files = glob.glob(os.path.join(path, "**/*.mp4"), recursive=True)
    files += glob.glob(os.path.join(path, "**/*.mkv"), recursive=True)
    return sorted(files, key=lambda f: os.path.getctime(f))


def main():
    logger.info(f"[🧹] Cleanup service started")
    logger.info(f"[📁] Watching: {config.settings.record_dir}")
    logger.info(f"[📊] Max storage: {config.settings.max_storage_gb} GB")
    logger.info(f"[🛡️] Max exceed allowed: {config.settings.max_storage_exceed_allowed_gb} GB")
    
    if config.settings.youtube_upload_enabled:
         logger.info(f"[🔄] Cleanup strategy: YouTube Upload Aware")
         logger.info(f"    1. Stage 1 (> {config.settings.max_storage_gb} GB): Delete ONLY uploaded files")
         logger.info(f"    2. Stage 2 (> {config.settings.max_storage_gb + config.settings.max_storage_exceed_allowed_gb} GB): Delete ANY oldest files (CRITICAL)")
    else:
         logger.info(f"[🗑️] Cleanup strategy: Standard (Delete oldest when limit exceeded)")

    while True:
        size = get_size_gb(config.settings.record_dir)
        limit_stage1 = config.settings.max_storage_gb
        limit_stage2 = config.settings.max_storage_gb + config.settings.max_storage_exceed_allowed_gb
        
        logger.info(f"[📊] Current: {size:.2f} GB / {limit_stage1} GB (Crit: {limit_stage2} GB)")

        # Stage 1: Standard / Safe Cleanup
        if size > limit_stage1:
            files = get_all_recordings(config.settings.record_dir)
            
            if files:
                # Identify candidates for deletion
                files_to_delete = []
                
                if config.settings.youtube_upload_enabled:
                    # Filter: Only delete files that are uploaded
                    for f in files:
                        if "_uploaded" in os.path.basename(f):
                            files_to_delete.append(f)
                    
                    if not files_to_delete and size <= limit_stage2:
                         logger.warning(f"[🛡️] Storage full ({size:.2f} GB) but all files are pending upload. Waiting...")
                else:
                    # Standard mode: Delete oldest 50%
                    delete_count = max(1, len(files) // 2)
                    files_to_delete = files[:delete_count]
                
                # Perform Deletion
                if files_to_delete:
                    # If specific candidates found (upload aware), delete them one by one until safe
                    # But for now let's just delete a chunk of oldest safe files
                    count_to_delete = len(files_to_delete)
                    if config.settings.youtube_upload_enabled:
                         # Delete oldest 20% of safe files or at least 1, to be gentle? 
                         # Or just delete enough to get under limit?
                         # Let's delete oldest 10 safe files at a time to be responsive
                         count_to_delete = min(len(files_to_delete), 10)
                    
                    logger.info(f"[🗑️] Deleting {count_to_delete} files (Stage 1)...")
                    for f in files_to_delete[:count_to_delete]:
                        try:
                            os.remove(f)
                            logger.info(f"[🗑️] Deleted: {os.path.basename(f)}")
                            parent = os.path.dirname(f)
                            if parent != config.settings.record_dir and os.path.isdir(parent) and not os.listdir(parent):
                                os.rmdir(parent)
                        except OSError as e:
                            logger.error(f"[⚠] Could not delete {f}: {e}")
                            
        # Stage 2: Critical Cleanup (Fallback)
        # Check size again after Stage 1
        size = get_size_gb(config.settings.record_dir)
        if config.settings.youtube_upload_enabled and size > limit_stage2:
            logger.warning(f"[🚨] CRITICAL STORAGE LIMIT EXCEEDED ({size:.2f} GB > {limit_stage2} GB)")
            logger.warning("[🚨] Deleting oldest files indiscriminately to preserve system function!")
            
            files = get_all_recordings(config.settings.record_dir)
            if files:
                # Delete oldest 5 files at a time until safe
                for f in files[:5]:
                     try:
                        os.remove(f)
                        logger.info(f"[🚨] CRITICAL DELETE: {os.path.basename(f)}")
                        parent = os.path.dirname(f)
                        if parent != config.settings.record_dir and os.path.isdir(parent) and not os.listdir(parent):
                            os.rmdir(parent)
                     except OSError as e:
                        logger.error(f"[⚠] Critical delete failed {f}: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
