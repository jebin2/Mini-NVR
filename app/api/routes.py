from fastapi import APIRouter, Query, HTTPException, Depends
from core import config
from services import store
from api.deps import get_current_user

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
def get_dates(channel: int = Query(None)):
    """
    Get dates using directory listing.
    Assumes nested structure: recordings/chX/YYYY-MM-DD
    """
    return {"dates": store.get_available_dates(channel)}

@router.get("/channel/{ch}/recordings")
def get_recordings(ch: int, date: str):
    return {"recordings": store.get_recordings_for_date(ch, date)}
