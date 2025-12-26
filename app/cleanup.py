import os
import time
import glob
from core import config
from core.logger import setup_logger

logger = setup_logger("cleanup")

CHECK_INTERVAL = int(os.getenv("CLEANUP_INTERVAL", 60))

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
    logger.info(f"[📁] Watching: {config.RECORD_DIR}")
    logger.info(f"[📊] Max storage: {config.MAX_STORAGE_GB} GB")
    logger.info(f"[🗑️] Cleanup strategy: Delete oldest 50% when limit exceeded")

    while True:
        size = get_size_gb(config.RECORD_DIR)
        logger.info(f"[📊] Current: {size:.2f} GB / {config.MAX_STORAGE_GB} GB")

        if size > config.MAX_STORAGE_GB:
            files = get_all_recordings(config.RECORD_DIR)
            
            if files:
                # Delete oldest 50% of files
                delete_count = len(files) // 2
                if delete_count < 1:
                    delete_count = 1
                
                logger.info(f"[🗑️] Deleting oldest {delete_count} of {len(files)} files...")
                
                for f in files[:delete_count]:
                    try:
                        os.remove(f)
                        logger.info(f"[🗑️] Deleted: {f}")
                        # Cleanup empty parent folders
                        parent = os.path.dirname(f)
                        if parent != config.RECORD_DIR and os.path.isdir(parent) and not os.listdir(parent):
                            os.rmdir(parent)
                            logger.info(f"[🗑️] Removed empty folder: {parent}")
                    except OSError as e:
                        logger.error(f"[⚠] Could not delete {f}: {e}")
                
                new_size = get_size_gb(config.RECORD_DIR)
                logger.info(f"[✓] Freed: {size - new_size:.2f} GB")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
