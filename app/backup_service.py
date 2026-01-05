#!/usr/bin/env python3
"""
Backup Service for Mini-NVR
Copies recordings from RECORD_DIR to BACKUP_DIR using rsync for efficiency.
Runs periodically (default every 2 hours) and is managed by start_services.sh.
"""

import os
import subprocess
import time
from core import config
from core.logger import setup_logger
from utils.storage import get_size_gb, cleanup_old_files

logger = setup_logger("backup", "/logs/backup.log")


def sync_with_rsync(source_dir, dest_dir):
    """
    Sync source to destination using rsync.
    Uses rsync for efficient incremental copy.
    
    Returns:
        True if successful, False otherwise
    """
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        logger.info(f"[📁] Created backup directory: {dest_dir}")
    
    # rsync flags:
    # -a = archive mode (preserves permissions, times, etc.)
    # -v = verbose (for logging)
    # --delete = remove files from dest that don't exist in source (optional, disabled for safety)
    # Trailing slash on source means "contents of" not "the directory itself"
    cmd = [
        "rsync",
        "-av",
        "--progress",
        f"{source_dir}/",  # Trailing slash = copy contents
        f"{dest_dir}/"
    ]
    
    logger.info(f"[🔄] Running: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        
        if result.returncode == 0:
            # Count lines that look like file transfers
            lines = result.stdout.strip().split('\n')
            transferred = [l for l in lines if l and not l.startswith('sending') and not l.startswith('total')]
            logger.info(f"[✓] Rsync complete. Files processed: {len(transferred)}")
            return True
        else:
            logger.error(f"[❌] Rsync failed: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.error(f"[❌] Rsync timed out after 1 hour")
        return False
    except Exception as e:
        logger.error(f"[❌] Rsync error: {e}")
        return False


def main():
    backup_dir = config.settings.backup_dir
    max_gb = config.settings.backup_max_storage_gb
    interval = config.settings.backup_sync_interval
    
    logger.info(f"[💾] Backup service started")
    logger.info(f"[📁] Source: {config.settings.record_dir}")
    logger.info(f"[📁] Destination: {backup_dir}")
    logger.info(f"[📊] Max storage: {max_gb} GB")
    logger.info(f"[⏰] Sync interval: {interval} seconds ({interval/3600:.1f} hours)")
    
    while True:
        try:
            # Step 1: Cleanup backup if over limit (delete 10% of oldest files)
            cleanup_old_files(backup_dir, max_gb, logger)
            
            # Step 2: Sync recordings to backup using rsync
            sync_with_rsync(config.settings.record_dir, backup_dir)
            
            # Step 3: Cleanup again after sync in case new files exceeded limit
            cleanup_old_files(backup_dir, max_gb, logger)
            
        except Exception as e:
            logger.error(f"[❌] Backup failed: {e}")
        
        # Sleep until next sync
        logger.info(f"[😴] Next sync in {interval/3600:.1f} hours...")
        time.sleep(interval)


if __name__ == "__main__":
    main()
