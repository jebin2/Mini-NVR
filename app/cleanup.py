import os
import time
import shutil
from datetime import datetime, timedelta
from core import config
from core.logger import setup_logger

# Use separate log file
logger = setup_logger("cleanup", "/logs/cleanup.log")

CHECK_INTERVAL = config.settings.cleanup_interval


def get_date_dirs(record_dir):
    """Get all date directories across all channels.
    
    Structure: /recordings/ch{N}/{YYYY-MM-DD}/
    Returns list of (full_path, date_obj) sorted oldest first.
    """
    date_dirs = []
    
    if not os.path.exists(record_dir):
        return date_dirs
    
    for ch_dir in os.listdir(record_dir):
        ch_path = os.path.join(record_dir, ch_dir)
        if not os.path.isdir(ch_path):
            continue
        
        for date_dir in os.listdir(ch_path):
            date_path = os.path.join(ch_path, date_dir)
            if not os.path.isdir(date_path):
                continue
            
            try:
                date_obj = datetime.strptime(date_dir, "%Y-%m-%d")
                date_dirs.append((date_path, date_obj))
            except ValueError:
                # Not a date directory, skip
                continue
    
    # Sort oldest first
    date_dirs.sort(key=lambda x: x[1])
    return date_dirs


def main():
    retention_days = config.settings.retention_days
    
    logger.info(f"[🧹] Cleanup service started")
    logger.info(f"[📁] Watching: {config.settings.record_dir}")
    logger.info(f"[📅] Retention: {retention_days} days (delete anything older)")

    while True:
        try:
            cutoff = datetime.now() - timedelta(days=retention_days)
            date_dirs = get_date_dirs(config.settings.record_dir)
            
            deleted_count = 0
            for date_path, date_obj in date_dirs:
                if date_obj < cutoff:
                    rel_path = os.path.relpath(date_path, config.settings.record_dir)
                    try:
                        shutil.rmtree(date_path)
                        deleted_count += 1
                        logger.info(f"[🗑️] Deleted old recording dir: {rel_path}")
                    except OSError as e:
                        logger.error(f"[⚠] Failed to delete {rel_path}: {e}")
            
            # Clean up empty channel directories
            if os.path.exists(config.settings.record_dir):
                for ch_dir in os.listdir(config.settings.record_dir):
                    ch_path = os.path.join(config.settings.record_dir, ch_dir)
                    if os.path.isdir(ch_path) and not os.listdir(ch_path):
                        try:
                            os.rmdir(ch_path)
                        except OSError:
                            pass
            
            if deleted_count > 0:
                logger.info(f"[✅] Cleaned up {deleted_count} old recording directories")
        except Exception as e:
            logger.error(f"[❌] Cleanup error: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
