from fastapi import APIRouter, Query, Path, HTTPException, Depends
from core import config
from services import store
from api.deps import get_current_user
import re

router = APIRouter(dependencies=[Depends(get_current_user)])

@router.get("/config")
def get_config():
    return {
        "numChannels": config.NUM_CHANNELS,
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
    if channel is not None and channel > config.NUM_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Invalid channel. Max is {config.NUM_CHANNELS}")
    return {"dates": store.get_available_dates(channel)}

@router.get("/channel/{ch}/recordings")
def get_recordings(
    ch: int = Path(..., ge=1, description="Channel number"), 
    date: str = Query(..., description="Date in YYYY-MM-DD format")
):
    # Validate channel bounds
    if ch > config.NUM_CHANNELS:
        raise HTTPException(status_code=400, detail=f"Invalid channel. Max is {config.NUM_CHANNELS}")
    
    # Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    return {"recordings": store.get_recordings_for_date(ch, date)}

