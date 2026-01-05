"""
Storage utility functions shared by cleanup and backup services.
"""
import os
import glob


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


def get_all_ts_files(path, sort_by="mtime"):
    """
    Get all .ts files in a directory recursively.
    
    Args:
        path: Directory to scan
        sort_by: "mtime" (modification time) or "ctime" (creation time), oldest first
    
    Returns:
        List of absolute file paths sorted by time (oldest first)
    """
    files = glob.glob(os.path.join(path, "**/*.ts"), recursive=True)
    
    if sort_by == "ctime":
        return sorted(files, key=lambda f: os.path.getctime(f))
    else:
        return sorted(files, key=lambda f: os.path.getmtime(f))


def cleanup_old_files(directory, max_gb, logger, cleanup_percent=0.10):
    """
    Delete oldest .ts files from a directory until 10% of max_gb is freed.
    
    Args:
        directory: Directory to clean up
        max_gb: Maximum allowed storage in GB
        logger: Logger instance for output
        cleanup_percent: Fraction of max_gb to free (default 10%)
    
    Returns:
        Number of files deleted
    """
    current_size = get_size_gb(directory)
    
    if current_size <= max_gb:
        return 0
    
    # Delete cleanup_percent of max storage to create headroom
    target_bytes = (max_gb * (1024 ** 3)) * cleanup_percent
    deleted_bytes = 0
    deleted_count = 0
    
    files = get_all_ts_files(directory, sort_by="mtime")
    logger.info(f"[📊] Storage {current_size:.2f} GB exceeds limit {max_gb} GB")
    logger.info(f"[🗑️] Deleting ~{target_bytes / (1024**2):.0f} MB ({cleanup_percent*100:.0f}% of {max_gb} GB)...")
    
    for f in files:
        if deleted_bytes >= target_bytes:
            break
        try:
            f_size = os.path.getsize(f)
            os.remove(f)
            deleted_bytes += f_size
            deleted_count += 1
            
            # Clean empty parent directories
            parent = os.path.dirname(f)
            if parent != directory and os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent)
        except OSError as e:
            logger.warning(f"[⚠️] Failed to delete {f}: {e}")
    
    logger.info(f"[✓] Deleted {deleted_count} files ({deleted_bytes / (1024**2):.0f} MB)")
    return deleted_count
