import os
import time
import re

def format_size(bytes_size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"

def format_duration(seconds):
    if not seconds: return ""
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0: return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def is_file_live(filepath, threshold=15):
    """Consider a file live if modified in the last `threshold` seconds."""
    try:
        return (time.time() - os.path.getmtime(filepath)) < threshold
    except (OSError, IOError):
        return False

def parse_filename(filepath):
    """
    Extracts timestamp from common NVR naming conventions.
    Supports: ch1_20251226_103000.mp4/.mkv or hierarchy ch1/2025-12-26/103000.mp4
    """
    fname = os.path.basename(filepath)
    
    # Pattern 1: Flat file (ch1_20251226_153024.mp4 OR .mkv)
    # Regex updated to ignore extension or accept both
    match = re.search(r'ch(\d+)_(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})', fname)
    if match:
        ch, Y, M, D, h, m, s = match.groups()
        return {
            "channel": int(ch),
            "date": f"{Y}-{M}-{D}",
            "time": f"{h}:{m}:{s}",
            "datetime": f"{D}/{M}/{Y} {h}:{m}:{s}"
        }

    # Pattern 2: Nested (ch1/2025-12-26/153024.mp4)
    # Assumes parent folder is date, filename is time
    try:
        parent_dir = os.path.basename(os.path.dirname(filepath)) # 2025-12-26
        if re.match(r'\d{4}-\d{2}-\d{2}', parent_dir):
            time_part = fname.replace('_uploaded', '').split('.')[0] # 153024 (removes extension automatically)
            if len(time_part) == 6:
                h, m, s = time_part[0:2], time_part[2:4], time_part[4:6]
                Y, M, D = parent_dir.split('-')
                return {
                    "channel": 0, # Extracted from caller context usually
                    "date": parent_dir,
                    "time": f"{h}:{m}:{s}",
                    "datetime": f"{D}/{M}/{Y} {h}:{m}:{s}"
                }
    except:
        pass
            
    return None
