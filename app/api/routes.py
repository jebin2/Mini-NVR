from fastapi import APIRouter, Query, Path, HTTPException, Depends
from core import config
from utils import recordings as store # Keeping 'store' alias to minimize diff lines below? 
# Actually let's just do it right.
from utils import recordings
from api.deps import get_current_user
import re
import os

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/config")
def get_config():
    return {
        "numChannels": config.settings.num_channels,
        "activeChannels": config.settings.get_active_channels(),
        "storageLimit": config.settings.max_storage_gb
    }

@router.get("/storage")
def get_storage():
    return recordings.get_storage_usage()

@router.get("/live")
def get_live_feeds():
    return {"channels": recordings.get_live_channels()}

@router.get("/dates")
def get_dates(channel: int = Query(None, ge=1, description="Channel number (1-based)")):
    """
    Get dates using directory listing.
    Assumes nested structure: recordings/chX/YYYY-MM-DD
    """
    if channel is not None and channel not in config.settings.get_active_channels():
        raise HTTPException(status_code=400, detail=f"Invalid or skipped channel.")
    return {"dates": recordings.get_available_dates(channel)}

@router.get("/channel/{ch}/recordings")
def get_recordings(
    ch: int = Path(..., ge=1, description="Channel number"), 
    date: str = Query(..., description="Date in YYYY-MM-DD format")
):
    # Validate channel bounds
    # Validate channel bounds
    if ch not in config.settings.get_active_channels():
        raise HTTPException(status_code=400, detail=f"Invalid or skipped channel.")
    
    # Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    return {"recordings": recordings.get_recordings_for_date(ch, date)}

@router.delete("/recording")
def delete_recording(path: str = Query(..., description="Relative path to the recording file")):
    """Delete a recording file. Only works for non-live recordings."""
    # Security: Validate path doesn't have traversal attempts
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    # Build absolute path
    abs_path = os.path.abspath(os.path.join(config.settings.record_dir, path))
    
    # Security: Ensure path is within RECORD_DIR
    if not abs_path.startswith(os.path.abspath(config.settings.record_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Check file exists
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
    
    # Prevent deleting live files (modified in last 15 seconds)
    import time
    if (time.time() - os.path.getmtime(abs_path)) < 15:
        raise HTTPException(status_code=400, detail="Cannot delete live recording")
    
    # Delete the file
    try:
        os.remove(abs_path)
        
        # Clean up empty parent directories
        parent = os.path.dirname(abs_path)
        if parent != os.path.abspath(config.settings.record_dir) and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
            
        return {"message": "Deleted", "path": path}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")

@router.post("/youtube/restart")
def restart_youtube_stream():
    """Restart the YouTube streaming service by killing its process group."""
    import signal
    
    try:
        # Find youtube_stream.py process by scanning /proc
        pids = []
        for pid_dir in os.listdir('/proc'):
            if not pid_dir.isdigit():
                continue
            try:
                cmdline_path = f'/proc/{pid_dir}/cmdline'
                with open(cmdline_path, 'r') as f:
                    cmdline = f.read()
                if 'youtube_stream.py' in cmdline:
                    pids.append(int(pid_dir))
            except (IOError, OSError):
                continue  # Process may have ended
        
        if not pids:
            raise HTTPException(status_code=404, detail="YouTube stream service not running")
        
        # Kill the process group (this kills Python + all FFmpeg children)
        # monitor.sh will auto-restart the service
        for pid in pids:
            try:
                # Kill entire process group
                pgid = os.getpgid(pid)
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                # Fallback: kill just the process
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        
        return {"message": "YouTube stream restart initiated (process group killed)", "pids": pids}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart: {e}")
