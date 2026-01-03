"""
Naming conventions and helper functions for YouTube uploads.
Centralizes logic for CSV filenames, content formatting, and parsing.
"""

import os
from datetime import datetime
from typing import Optional, Dict

def get_youtube_csv_filename(recordings_dir: str, date_str: str) -> str:
    """Returns the absolute path for a daily YouTube uploads CSV file."""
    return os.path.join(recordings_dir, f"youtube_uploads_{date_str}.csv")

def parse_youtube_csv_filename(filename: str) -> Optional[str]:
    """
    Extracts the date string from a YouTube uploads CSV filename.
    Returns None if the filename doesn't match the expected pattern.
    """
    basename = os.path.basename(filename)
    if not basename.startswith("youtube_uploads_") or not basename.endswith(".csv"):
        return None
    
    # Format: youtube_uploads_YYYY-MM-DD.csv
    # Length of "youtube_uploads_" is 16
    # Length of ".csv" is 4
    date_str = basename[16:-4]
    
    # Basic validation of date format (YYYY-MM-DD)
    if len(date_str) != 10 or date_str[4] != '-' or date_str[7] != '-':
        return None
        
    return date_str

def format_youtube_csv_line(
    channel_name: str,
    date_str: str,
    time_str: str,
    url: str,
    status: str = "synced",
    camera_name: str = "Unknown"
) -> str:
    """
    Formats a single line for the YouTube uploads CSV.
    Ensures consistent column order: Channel, Date, Time, URL, Status, Camera
    """
    return f"{channel_name},{date_str},{time_str},{url},{status},{camera_name}\n"

def parse_youtube_csv_line(line: str) -> Optional[Dict[str, str]]:
    """
    Parses a line from the YouTube uploads CSV.
    Handles legacy lines (missing camera) gracefully.
    """
    parts = line.strip().split(',')
    if len(parts) < 4:
        return None
        
    result = {
        "channel": parts[0].strip(),
        "date": parts[1].strip(),
        "time": parts[2].strip(),
        "url": parts[3].strip(),
        "status": parts[4].strip() if len(parts) > 4 else "synced",
        "camera": parts[5].strip() if len(parts) > 5 else "Unknown"
    }
    return result

def extract_camera_from_title(title: str) -> str:
    """
    Extracts the camera name from a video title.
    Expected format: "Channel X - Date (Time)" or similar.
    Returns "Unknown" if extraction fails.
    """
    try:
        if ' - ' in title:
            return title.split(' - ')[0].strip()
        return "Unknown"
    except Exception:
        return "Unknown"
