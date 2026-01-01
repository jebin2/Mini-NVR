from fastapi import APIRouter, Query, Path, HTTPException, Depends
from core import config
from services import store
from api.deps import get_current_user
import re
import os

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/config")
def get_config():
    return {
        "numChannels": config.NUM_CHANNELS,
        "activeChannels": config.get_active_channels(),
        "storageLimit": config.MAX_STORAGE_GB
    }

@router.get("/storage")
def get_storage():
    return store.get_storage_usage()

@router.get("/live")
def get_live_feeds():
    return {"channels": store.get_live_channels()}

@router.get("/dates")
def get_dates(channel: int = Query(None, ge=1, description="Channel number (1-based)")):
    """
    Get dates using directory listing.
    Assumes nested structure: recordings/chX/YYYY-MM-DD
    """
    if channel is not None and channel not in config.get_active_channels():
        raise HTTPException(status_code=400, detail=f"Invalid or skipped channel.")
    return {"dates": store.get_available_dates(channel)}

@router.get("/channel/{ch}/recordings")
def get_recordings(
    ch: int = Path(..., ge=1, description="Channel number"), 
    date: str = Query(..., description="Date in YYYY-MM-DD format")
):
    # Validate channel bounds
    # Validate channel bounds
    if ch not in config.get_active_channels():
        raise HTTPException(status_code=400, detail=f"Invalid or skipped channel.")
    
    # Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    return {"recordings": store.get_recordings_for_date(ch, date)}

@router.delete("/recording")
def delete_recording(path: str = Query(..., description="Relative path to the recording file")):
    """Delete a recording file. Only works for non-live recordings."""
    # Security: Validate path doesn't have traversal attempts
    if ".." in path or path.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid path")
    
    # Build absolute path
    abs_path = os.path.abspath(os.path.join(config.RECORD_DIR, path))
    
    # Security: Ensure path is within RECORD_DIR
    if not abs_path.startswith(os.path.abspath(config.RECORD_DIR)):
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
        if parent != os.path.abspath(config.RECORD_DIR) and os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
            
        return {"message": "Deleted", "path": path}
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete: {e}")

@router.post("/youtube/restart")
def restart_youtube_stream():
    """Restart the YouTube streaming service by signaling the process."""
    import subprocess
    import signal
    
    try:
        # Find the youtube_stream.py process
        result = subprocess.run(
            ["pgrep", "-f", "youtube_stream.py"],
            capture_output=True,
            text=True
        )
        
        pids = result.stdout.strip().split('\n')
        pids = [p for p in pids if p]  # Filter empty strings
        
        if not pids:
            raise HTTPException(status_code=404, detail="YouTube stream service not running")
        
        # Kill the process - it should auto-restart via monitor.sh
        for pid in pids:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already gone
        
        return {"message": "YouTube stream restart initiated", "pids": pids}
        
    except subprocess.SubprocessError as e:
        raise HTTPException(status_code=500, detail=f"Failed to restart: {e}")
