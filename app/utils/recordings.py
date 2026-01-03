import os
import glob
import time
import subprocess
from core.config import settings
from core.logger import setup_logger
from utils.helpers import is_file_live, parse_filename, format_size
from services.metadata import MetadataCache
from utils.naming_conventions import (
    get_youtube_csv_filename,
    parse_youtube_csv_filename,
    parse_youtube_csv_line
)

logger = setup_logger("recordings")
meta_cache = MetadataCache(os.path.join(settings.record_dir, "metadata_cache.json"))

def get_video_duration(filepath):
    """
    Get duration. Optimized to be skipped for older files if needed 
    to prevent API timeout on large directories.
    """
    try:
        # Fast estimation based on file size if it matches expected bitrate could go here
        # For now, we use a quick ffprobe with a short timeout
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", filepath
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=1)
        if result.returncode == 0 and result.stdout.strip() != "N/A":
            return float(result.stdout.strip())
    except:
        pass
    return None

def get_storage_usage():
    total_size = 0
    for dirpath, _, filenames in os.walk(settings.record_dir):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    
    used_gb = round(total_size / (1024**3), 1)
    summary = f"{used_gb} GB / {settings.max_storage_gb} GB"
    return {"summary": summary, "usedGB": used_gb, "maxGB": settings.max_storage_gb}

def get_live_channels():
    channels = {}
    for ch in settings.get_active_channels():
        # Find latest HLS segment for this channel
        candidates = []
        # Check Nested HLS segments
        candidates.extend(glob.glob(os.path.join(settings.record_dir, f"ch{ch}", "*", "*.ts")))
        
        status = "OFF"
        file_path = None
        
        if candidates:
            # Get absolute newest file regardless of type
            latest_file = max(candidates, key=os.path.getctime)
            is_live = is_file_live(latest_file)
            
            # Determine logic status
            stop_file = os.path.join(settings.control_dir, f"stop_ch{ch}")
            if os.path.exists(stop_file):
                status = "OFF"
            elif is_live:
                status = "LIVE"
            else:
                status = "REC" 
            
            # Relative path for frontend
            file_path = os.path.relpath(latest_file, settings.record_dir)
        
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
        ch_path = os.path.join(settings.record_dir, f"ch{channel}")
        if os.path.exists(ch_path):
            target_dirs.append(ch_path)
    else:
        # Find all channel folders
        try:
            with os.scandir(settings.record_dir) as it:
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
            
    # Scan CSV files for cloud-only dates (or if local files are missing)
    try:
        pattern = os.path.join(settings.record_dir, "youtube_uploads_*.csv")
        for csv_file in glob.glob(pattern):
            # Extract date from filename
            date_str = parse_youtube_csv_filename(csv_file)
            if not date_str:
                continue
            
            # If date already found locally, skip expensive CSV read
            if date_str in dates:
                continue
                
            # If channel filter is active, check if this CSV contains videos for this channel
            if channel:
                target_cam = f"Channel {channel}"
                found_match = False
                try:
                    with open(csv_file, 'r') as f:
                        for line in f:
                            data = parse_youtube_csv_line(line)
                            if data and data['camera'] == target_cam:
                                found_match = True
                                break
                except Exception:
                    pass
                
                if found_match:
                    dates.add(date_str)
            else:
                # No channel filter, include date if CSV exists
                dates.add(date_str)
                
    except Exception as e:
        logger.error(f"Error scanning CSVs in get_dates: {e}")

    t3 = time.time()
    logger.info(f"[PERF] get_dates(ch={channel}) total={t3-t0:.4f}s")
    return sorted(list(dates), reverse=True)


def _get_youtube_entries_for_date(date, channel):
    """
    Get YouTube entries for a specific date and channel.
    Returns a list of parsed video objects.
    """
    entries = []
    
    # We only check the specific CSV for this date
    # No more global scanning of all CSVs
    csv_path = get_youtube_csv_filename(settings.record_dir, date)
    
    if os.path.exists(csv_path):
        target_cam = f"Channel {channel}"
        try:
            with open(csv_path, 'r') as f:
                for line in f:
                    data = parse_youtube_csv_line(line)
                    if data:
                        # Check camera match
                        # data['camera'] should be "Channel X"
                        if data['camera'] == target_cam:
                            entries.append(data)
                        # Fallback for old CSVs without camera column?
                        # If old CSV, camera is "Unknown".
                        # If user asks for Channel 1, "Unknown" won't match. 
                        # This assumes new CSV format. 
                        # If mixed content, only new entries will show up for specific channel queries.
                        # This is acceptable per "KISS" requirement.
        except Exception as e:
            logger.error(f"Failed to read CSV {csv_path}: {e}")
            
    return entries

def get_recordings_for_date(ch, date):
    recordings = []
    
    # 1. Get Local Recordings
    local_recs_map = {} # Key: HH:MM:SS string -> index in recordings list
    
    try:
        # Helper to process a local file entry
        # We inline the loop logic instead of sub-function for clarity or keep it similar
        
        candidates = []
        
        # Scan Root for Flat files
        target_date_flat = date.replace("-", "") # 20251226
        with os.scandir(settings.record_dir) as it:
            prefix = f"ch{ch}_{target_date_flat}"
            for entry in it:
                if entry.is_file() and entry.name.startswith(prefix):
                    candidates.append(entry)

        # Nested Structure Search
        nested_dir = os.path.join(settings.record_dir, f"ch{ch}", date)
        if os.path.exists(nested_dir):
            with os.scandir(nested_dir) as it:
                for entry in it:
                    if entry.is_file():
                        candidates.append(entry)
                        
        # Find latest candidate based on mtime (to handle edge cases with live check)
        latest_candidate = None
        if candidates:
            try:
                latest_candidate = max(candidates, key=lambda e: e.stat().st_mtime)
            except (ValueError, OSError):
                pass

        for entry in candidates:
             is_ts = entry.name.endswith(".ts")  # HLS segments
             is_mp4 = entry.name.endswith(".mp4")
             is_mkv = entry.name.endswith(".mkv")  # Legacy
             
             if not (is_ts or is_mp4 or is_mkv):
                 continue
                 
             # Only show MKV if it is the latest file (likely currently recording - legacy)
             # For TS segments, we want to show all of them as they're the new format
             if is_mkv:
                 is_latest = (entry == latest_candidate)
                 if not is_latest:
                     continue
            
             full_path = entry.path
             meta = parse_filename(full_path)
             if not meta or meta['date'] != date:
                 continue

             stat = entry.stat()
             
             rec = {
                 "full_path": full_path,
                 "rel_path": os.path.relpath(full_path, settings.record_dir),
                 "meta": meta,
                 "size": stat.st_size,
                 "mtime": stat.st_mtime,
                 "youtube_url": None # Will be filled if match found
             }
             
             recordings.append(rec)
             local_recs_map[meta['time']] = rec

    except OSError:
        pass
        
    # 2. Get Cloud Recordings
    cloud_entries = _get_youtube_entries_for_date(date, ch)
    
    # 3. Merge Cloud Data
    for entry in cloud_entries:
        time_key = entry['time'] # HH:MM:SS
        url = entry['url']
        
        if time_key in local_recs_map:
            # Match found: Attach URL to local recording
            local_recs_map[time_key]['youtube_url'] = url
        else:
            # No local match: Add as Cloud Only
            # We need to construct a phantom meta object
            recordings.append({
                "full_path": None,
                "rel_path": f"cloud/{date}/{time_key}", # Dummy path
                "meta": {
                    "date": date,
                    "time": time_key,
                    "datetime": f"{date} {time_key}" # for sorting
                },
                "size": 0,
                "mtime": 0,
                "youtube_url": url
            })

    # 4. Sort
    recordings.sort(key=lambda x: x['meta']['datetime'])
    
    # 5. Determine Live Status & Format Result
    now = time.time()
    
    # Find latest live candidate (checking mtime only for existing files)
    live_index = -1
    for i, rec in enumerate(recordings):
        if rec['mtime'] > 0 and (now - rec['mtime']) < 15:
            live_index = i
            
    result_list = []
    for i, rec in enumerate(recordings):
        is_live = (i == live_index)
        
        duration = None
        if not is_live and rec['full_path']:
             # Standard duration lookup
             cached_dur = meta_cache.get_duration(rec['rel_path'], rec['size'], rec['mtime'])
             if cached_dur is not None:
                 duration = cached_dur
             else:
                 dur = get_video_duration(rec['full_path'])
                 if dur is not None:
                     duration = dur
                     meta_cache.set_duration(rec['rel_path'], rec['size'], rec['mtime'], duration)

        size_display = format_size(rec['size'])
        if rec['full_path'] is None:
            size_display = "Cloud Only"

        result_list.append({
            "name": rec['rel_path'],
            "startTime": rec['meta']['time'],
            "datetime": rec['meta']['datetime'],
            "size": size_display,
            "duration": duration,
            "live": is_live,
            "youtube_url": rec['youtube_url']
        })
        
    return result_list
