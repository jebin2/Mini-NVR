"""
HLS Playback API

Provides endpoints for generating dynamic HLS playlists for time-scroll playback.
Supports seeking to any timestamp within recorded footage.
"""
import os
import re
import glob
from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, Query, Path, Depends
from fastapi.responses import Response
from api.deps import get_current_user
from core.config import settings
from core.logger import setup_logger

logger = setup_logger("playback_api")

router = APIRouter(dependencies=[Depends(get_current_user)])


def parse_segment_time(filename: str) -> datetime | None:
    """
    Parse timestamp from HLS segment filename.
    Expected format: HHMMSS.ts
    Returns datetime for today (date comes from directory context).
    """
    match = re.match(r'^(\d{2})(\d{2})(\d{2})\.ts$', filename)
    if match:
        h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
        return datetime.now().replace(hour=h, minute=m, second=s, microsecond=0)
    return None


def get_segments_in_range(channel: int, date: str, start_time: str = None, end_time: str = None) -> list[dict]:
    """
    Get all HLS segments for a channel/date, optionally filtered by time range.
    
    Args:
        channel: Channel number (1-based)
        date: Date string in YYYY-MM-DD format
        start_time: Optional start time in HH:MM:SS format
        end_time: Optional end time in HH:MM:SS format
    
    Returns:
        List of segment info dicts sorted by time
    """
    segments = []
    
    # Build path to date folder
    date_dir = os.path.join(settings.record_dir, f"ch{channel}", date)
    
    if not os.path.exists(date_dir):
        return segments
    
    # Parse time filters if provided
    start_dt = None
    end_dt = None
    base_date = datetime.strptime(date, "%Y-%m-%d")
    
    if start_time:
        try:
            parts = start_time.split(":")
            start_dt = base_date.replace(hour=int(parts[0]), minute=int(parts[1]), second=int(parts[2]))
        except (ValueError, IndexError):
            pass
            
    if end_time:
        try:
            parts = end_time.split(":")
            end_dt = base_date.replace(hour=int(parts[0]), minute=int(parts[1]), second=int(parts[2]))
        except (ValueError, IndexError):
            pass
    
    # Scan for .ts files
    try:
        for entry in os.scandir(date_dir):
            if not entry.is_file() or not entry.name.endswith('.ts'):
                continue
            
            # Parse segment filename
            match = re.match(r'^(\d{2})(\d{2})(\d{2})\.ts$', entry.name)
            if not match:
                continue
            
            h, m, s = int(match.group(1)), int(match.group(2)), int(match.group(3))
            segment_dt = base_date.replace(hour=h, minute=m, second=s)
            
            # Apply time filters
            # Include segment if it starts after start_dt, OR if it starts before but ends after start_dt
            # (i.e., the segment contains the requested start time)
            segment_end_dt = segment_dt + timedelta(seconds=settings.segment_duration)
            if start_dt and segment_end_dt < start_dt:
                continue  # Skip segments that end before the requested start
            if end_dt and segment_dt > end_dt:
                continue
            
            # Get segment duration from file (estimate based on settings, or use ffprobe)
            segments.append({
                "filename": entry.name,
                "path": entry.path,
                "time": f"{h:02d}:{m:02d}:{s:02d}",
                "datetime": segment_dt,
                "duration": settings.segment_duration  # Use configured segment duration
            })
            
    except OSError as e:
        logger.error(f"Error scanning segments: {e}")
    
    # Sort by time
    segments.sort(key=lambda x: x["datetime"])
    return segments


def generate_m3u8_playlist(segments: list[dict], base_url: str, start_dt: datetime = None) -> str:
    """
    Generate an HLS playlist (.m3u8) from a list of segments.
    
    Args:
        segments: List of segment dicts with filename and duration
        base_url: Base URL for segment files (e.g., /recordings/ch1/2026-01-03/)
    
    Returns:
        M3U8 playlist content as string
    """
    if not segments:
        # No segments - return empty playlist
        # Client-side handles informing user about no recordings
        return "#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:0\n#EXT-X-ENDLIST\n"
    
    # Calculate max duration for TARGETDURATION header
    max_duration = max(s["duration"] for s in segments)
    
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{int(max_duration) + 1}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",  # Video on Demand (complete recording)
    ]
    
    last_end_time = None
    GAP_THRESHOLD = 1.5  # Seconds

    for seg in segments:
        current_start = seg["datetime"]
        
        # Check for gap between segments - just mark discontinuity, no filler
        if last_end_time:
            gap_seconds = (current_start - last_end_time).total_seconds()
            
            if gap_seconds > GAP_THRESHOLD:
                lines.append("#EXT-X-DISCONTINUITY")

        # Add real segment
        lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{seg['datetime'].isoformat()}")
        lines.append(f"#EXTINF:{seg['duration']:.3f},")
        lines.append(f"{base_url}{seg['filename']}")
        
        last_end_time = current_start + timedelta(seconds=seg["duration"])
    
    lines.append("#EXT-X-ENDLIST")
    
    return "\n".join(lines)


@router.get("/playback/{channel}/{date}/playlist.m3u8")
def get_playback_playlist(
    channel: int = Path(..., ge=1, description="Channel number"),
    date: str = Path(..., description="Date in YYYY-MM-DD format"),
    start: str = Query(None, description="Start time in HH:MM:SS format"),
    end: str = Query(None, description="End time in HH:MM:SS format"),
):
    """
    Generate a dynamic HLS playlist for time-range playback.
    
    This enables time-scroll functionality by generating playlists
    that include only segments within the specified time range.
    
    Examples:
        - Full day: /api/playback/1/2026-01-03/playlist.m3u8
        - Time range: /api/playback/1/2026-01-03/playlist.m3u8?start=14:00:00&end=15:00:00
    """
    # Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Validate channel
    if channel not in settings.get_active_channels():
        raise HTTPException(status_code=400, detail="Invalid or skipped channel")
    
    # Get segments
    segments = get_segments_in_range(channel, date, start, end)
    
    if not segments:
        # Return empty playlist instead of 404 (player can handle empty playlist)
        return Response(
            content="#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-TARGETDURATION:0\n#EXT-X-ENDLIST\n",
            media_type="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-cache"}
        )
    
    # Build base URL for segments
    # Segments are served from /recordings/chX/YYYY-MM-DD/
    base_url = f"/recordings/ch{channel}/{date}/"
    
    # Parse start time for gap generation
    start_dt = None
    if start:
        try:
            h, m, s = map(int, start.split(':'))
            base_date = datetime.strptime(date, "%Y-%m-%d")
            start_dt = base_date.replace(hour=h, minute=m, second=s)
        except ValueError:
            pass

    # Generate playlist
    playlist_content = generate_m3u8_playlist(segments, base_url, start_dt=start_dt)
    
    return Response(
        content=playlist_content,
        media_type="application/vnd.apple.mpegurl",
        headers={
            "Cache-Control": "no-cache",  # Don't cache dynamic playlists
            "Access-Control-Allow-Origin": "*",
        }
    )


@router.get("/playback/{channel}/{date}/segments")
def get_segments_list(
    channel: int = Path(..., ge=1, description="Channel number"),
    date: str = Path(..., description="Date in YYYY-MM-DD format"),
):
    """
    Get list of available segments for a channel/date.
    
    Useful for building time scroll UI - returns segment times
    to indicate which periods have recordings.
    """
    # Validate date format
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    # Validate channel
    if channel not in settings.get_active_channels():
        raise HTTPException(status_code=400, detail="Invalid or skipped channel")
    
    segments = get_segments_in_range(channel, date)
    
    # Return simplified segment info for UI
    return {
        "channel": channel,
        "date": date,
        "segment_duration": settings.segment_duration,
        "segments": [
            {
                "time": seg["time"],
                "duration": seg["duration"]
            }
            for seg in segments
        ]
    }
