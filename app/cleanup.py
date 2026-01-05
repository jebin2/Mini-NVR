import os
import time
from core import config
from core.logger import setup_logger
from utils.processed_videos_csv import get_uploaded_videos
from utils.storage import get_size_gb, get_all_ts_files

# Use separate log file
logger = setup_logger("cleanup", "/logs/cleanup.log")

CHECK_INTERVAL = config.settings.cleanup_interval


def get_all_recordings(path):
    """Get all recording files sorted by creation time (oldest first)."""
    return get_all_ts_files(path, sort_by="ctime")


def main():
    logger.info(f"[🧹] Cleanup service started")
    logger.info(f"[📁] Watching: {config.settings.record_dir}")
    logger.info(f"[📊] Max storage: {config.settings.max_storage_gb} GB")
    
    # Log Strategy
    if config.settings.youtube_upload_enabled:
         logger.info(f"[🔄] Strategy: Delete 10% of storage when full (Prefer Uploaded > Oldest)")
    else:
         logger.info(f"[🗑️] Strategy: Delete 10% of storage when full")

    while True:
        size = get_size_gb(config.settings.record_dir)
        limit = config.settings.max_storage_gb
        
        # Only log if near/over limit or periodically
        if size > limit:
            logger.info(f"[📊] Storage usage: {size:.2f} GB (Limit: {limit} GB)")
            
            files = get_all_recordings(config.settings.record_dir)
            if files:
                # 1. Calculate Target: 10% of ALLOCATED STORAGE (not current usage, or file count)
                # target_gb = limit * 0.10
                # Using 10% of limit ensures we drop well below the limit
                target_bytes = (limit * (1024 ** 3)) * 0.10
                target_mb = target_bytes / (1024 ** 2)
                
                logger.info(f"[⚠️] Limit exceeded. Plan to delete up to {target_mb:.2f} MB (10% of {limit} GB)...")
                
                files_to_delete = []
                deleted_bytes_tally = 0

                # 2. Select Files Strategy
                
                # Helper to add file if we need space
                def add_candidate(f):
                    nonlocal deleted_bytes_tally
                    try:
                        f_size = os.path.getsize(f)
                        files_to_delete.append(f)
                        deleted_bytes_tally += f_size
                        return True
                    except OSError:
                        return False # File might have vanished

                if config.settings.youtube_upload_enabled:
                    # Priority: Uploaded Files
                    uploaded_paths = set(get_uploaded_videos())
                    
                    # Sort files into two buckets, preserving age order (oldest first)
                    uploaded_candidates = []
                    other_candidates = []
                    
                    for f in files:
                        rel = os.path.relpath(f, config.settings.record_dir)
                        if rel in uploaded_paths:
                            uploaded_candidates.append(f)
                        else:
                            other_candidates.append(f)
                    
                    # Fill quota from uploaded first
                    for f in uploaded_candidates:
                        if deleted_bytes_tally >= target_bytes:
                            break
                        add_candidate(f)
                    
                    # If strictly needed, fill remainder from others
                    if deleted_bytes_tally < target_bytes:
                        remainder_mb = (target_bytes - deleted_bytes_tally) / (1024**2)
                        logger.warning(f"[🚨] Not enough uploaded files. Deleting ~{remainder_mb:.2f} MB of non-uploaded files to free space.")
                        for f in other_candidates:
                            if deleted_bytes_tally >= target_bytes:
                                break
                            add_candidate(f)
                else:
                    # Standard Mode: Just oldest files until target size reached
                    for f in files:
                        if deleted_bytes_tally >= target_bytes:
                            break
                        add_candidate(f)
                
                # 3. Execute Deletion
                logger.info(f"[🗑️] Executing deletion of {len(files_to_delete)} files (~{deleted_bytes_tally / (1024**2):.2f} MB)...")
                
                for f in files_to_delete:
                    try:
                        os.remove(f)
                        # Log relative path to distinguish channels
                        rel_path = os.path.relpath(f, config.settings.record_dir)
                        logger.info(f"[🗑️] Deleted: {rel_path}")
                        
                        # Clean empty parents
                        parent = os.path.dirname(f)
                        if parent != config.settings.record_dir and os.path.isdir(parent) and not os.listdir(parent):
                            os.rmdir(parent)
                    except OSError as e:
                        logger.error(f"[⚠] Failed to delete {f}: {e}")
        else:
            # Healthy
            # logger.debug(f"[✓] Storage healthy: {size:.2f} GB")
            pass

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
