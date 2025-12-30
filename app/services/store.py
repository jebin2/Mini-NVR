import os
import glob
import time
from core import config
from core.logger import setup_logger
from utils.helpers import is_file_live, parse_filename, format_size
from services.media import get_video_duration
from services.metadata import MetadataCache

logger = setup_logger("store")
meta_cache = MetadataCache(os.path.join(config.RECORD_DIR, "metadata_cache.json"))

def get_storage_usage():
    total_size = 0
    for dirpath, _, filenames in os.walk(config.RECORD_DIR):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    
    used_gb = round(total_size / (1024**3), 1)
    return {"usedGB": used_gb, "maxGB": config.MAX_STORAGE_GB}

def get_live_channels():
    channels = {}
    for ch in range(1, config.NUM_CHANNELS + 1):
        # Find latest file for this channel (checking both MP4 and MKV)
        candidates = []
        for ext in ["mp4", "mkv"]:
            # Check Flat
            candidates.extend(glob.glob(os.path.join(config.RECORD_DIR, f"ch{ch}_*.{ext}")))
            # Check Nested
            candidates.extend(glob.glob(os.path.join(config.RECORD_DIR, f"ch{ch}", "*", f"*.{ext}")))
        
        status = "OFF"
        file_path = None
        
        if candidates:
            # Get absolute newest file regardless of type
            latest_file = max(candidates, key=os.path.getctime)
            is_live = is_file_live(latest_file)
            
            # Determine logic status
            stop_file = os.path.join(config.CONTROL_DIR, f"stop_ch{ch}")
            if os.path.exists(stop_file):
                status = "OFF"
            elif is_live:
                status = "LIVE"
            else:
                status = "REC" 
            
            # Relative path for frontend
            file_path = os.path.relpath(latest_file, config.RECORD_DIR)
        
        channels[ch] = {
            "status": status,
            "file": file_path if status != "OFF" else None
        }
    return channels

def get_available_dates(channel=None):
    t0 = time.time()
    dates = set()
    
    # Identify which directories to sweep
    target_dirs = []
    
    if channel:
        ch_path = os.path.join(config.RECORD_DIR, f"ch{channel}")
        if os.path.exists(ch_path):
            target_dirs.append(ch_path)
    else:
        # Find all channel folders
        try:
            with os.scandir(config.RECORD_DIR) as it:
                for entry in it:
                    if entry.is_dir() and entry.name.startswith("ch"):
                        target_dirs.append(entry.path)
        except OSError:
            pass

    t1 = time.time()
    
    # Collect dates from these folders
    items_count = 0
    for d in target_dirs:
        try:
            # os.listdir is fast for getting direct children
            items = os.listdir(d) 
            items_count += len(items)
            
            for name in items:
                # Basic validation yyyy-mm-dd
                if len(name) == 10 and name[4] == '-' and name[7] == '-':
                    dates.add(name)
        except OSError:
            pass
            
    t3 = time.time()
    logger.info(f"[PERF] get_dates(ch={channel}) total={t3-t0:.4f}s")
    return sorted(list(dates), reverse=True)

def load_youtube_map():
    """Load YouTube uploads CSV into a dictionary: rel_path -> url."""
    mapping = {}
    csv_path = os.path.join(config.RECORD_DIR, "youtube_uploads.csv")
    if os.path.exists(csv_path):
        try:
            with open(csv_path, 'r') as f:
                for line in f:
                    parts = line.strip().split(',')
                    if len(parts) >= 3:
                        # Format: path, id, url, timestamp
                        rel_path = parts[0]
                        url = parts[2]
                        mapping[rel_path] = url
        except Exception as e:
            logger.error(f"Failed to load youtube map: {e}")
    return mapping

def get_recordings_for_date(ch, date):
    recordings = []
    raw_recordings = []
    
    # Load YouTube Map
    youtube_map = load_youtube_map()
    
    # Helper to process a file entry
    def process_entry(entry):
        # Filter by extension
        if not (entry.name.endswith(".mp4") or entry.name.endswith(".mkv")):
            return
            
        full_path = entry.path
        
        # Parse metadata
        meta = parse_filename(full_path)
        if not meta: return
        
        # Filter by date if parsing succeeded (double check)
        if meta['date'] != date: return

        stat = entry.stat()
        size = stat.st_size
        mtime = stat.st_mtime
        
        raw_recordings.append({
            "full_path": full_path,
            "rel_path": os.path.relpath(full_path, config.RECORD_DIR),
            "meta": meta,
            "size": size,
            "mtime": mtime
        })

    try:
        # 1. Scan Root for Flat files: ch{ch}_{date_compact}_...
        target_date_flat = date.replace("-", "") # 20251226
        
        with os.scandir(config.RECORD_DIR) as it:
            prefix = f"ch{ch}_{target_date_flat}"
            for entry in it:
                if entry.is_file() and entry.name.startswith(prefix):
                    process_entry(entry)

        # 2. Nested Structure Search (ch1/2025-12-26/...)
        nested_dir = os.path.join(config.RECORD_DIR, f"ch{ch}", date)
        if os.path.exists(nested_dir):
            with os.scandir(nested_dir) as it:
                for entry in it:
                    if entry.is_file():
                        process_entry(entry)
                        
    except OSError:
        pass
    
    # Sort by mtime ascending
    raw_recordings.sort(key=lambda x: x['mtime'])
    
    # Logic to Determine "Live" Status (Strictly one or zero)
    now = time.time()
    live_candidates = []
    
    for i, rec in enumerate(raw_recordings):
        if (now - rec['mtime']) < 15: # 15s threshold
             live_candidates.append(i)
             
    live_index = -1
    if live_candidates:
        live_index = live_candidates[-1] # The latest one
        
    # Finalize List
    for i, rec in enumerate(raw_recordings):
        is_live = (i == live_index)
        
        duration = None
        if is_live:
             duration = None
        else:
             # Standard duration lookup
             cached_dur = meta_cache.get_duration(rec['rel_path'], rec['size'], rec['mtime'])
             if cached_dur is not None:
                 duration = cached_dur
             else:
                 dur = get_video_duration(rec['full_path'])
                 if dur is not None:
                     duration = dur
                     meta_cache.set_duration(rec['rel_path'], rec['size'], rec['mtime'], duration)

        recordings.append({
            "name": rec['rel_path'],
            "startTime": rec['meta']['time'],
            "datetime": rec['meta']['datetime'],
            "size": format_size(rec['size']),
            "duration": duration,
            "duration": duration,
            "live": is_live,
            "youtube_url": youtube_map.get(rec['rel_path'])
        })
        
    return recordings
