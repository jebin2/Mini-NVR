"""
Processed Videos CSV Utilities
Tracks compression and upload status for TS recordings.
"""

import os
import csv
import threading
from typing import List, Dict, Optional
from collections import defaultdict

CSV_PATH = "/recordings/processed_videos.csv"
COLUMNS = ["video_path", "size_mb", "upload_status"]

# Thread lock for CSV operations
_csv_lock = threading.Lock()


def _ensure_csv_exists():
    """Create CSV with header if it doesn't exist."""
    if not os.path.exists(CSV_PATH):
        os.makedirs(os.path.dirname(CSV_PATH), exist_ok=True)
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writeheader()


def _read_csv() -> List[dict]:
    """Read all rows from CSV."""
    _ensure_csv_exists()
    with open(CSV_PATH, "r", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_csv(rows: List[dict]):
    """Write all rows to CSV (overwrites)."""
    _ensure_csv_exists()
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def is_in_csv(video_path: str) -> bool:
    """Check if video path exists in CSV (already compressed)."""
    with _csv_lock:
        rows = _read_csv()
        # Normalize path for comparison
        video_path = video_path.lstrip("/")
        return any(row["video_path"] == video_path for row in rows)


def add_to_csv(video_path: str, size_mb: float):
    """Add a compressed video to CSV with empty upload_status."""
    with _csv_lock:
        _ensure_csv_exists()
        # Normalize path (relative to /recordings/)
        video_path = video_path.lstrip("/")
        if video_path.startswith("recordings/"):
            video_path = video_path[len("recordings/"):]
        
        # Append to CSV
        with open(CSV_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=COLUMNS)
            writer.writerow({
                "video_path": video_path,
                "size_mb": f"{size_mb:.2f}",
                "upload_status": ""
            })


def mark_uploaded(video_paths: List[str]):
    """Mark multiple video paths as uploaded (status='done')."""
    with _csv_lock:
        rows = _read_csv()
        
        # Normalize paths for comparison
        normalized_paths = set()
        for p in video_paths:
            p = p.lstrip("/")
            if p.startswith("recordings/"):
                p = p[len("recordings/"):]
            normalized_paths.add(p)
        
        # Update status
        for row in rows:
            if row["video_path"] in normalized_paths:
                row["upload_status"] = "done"
        
        _write_csv(rows)


def get_pending_uploads() -> List[dict]:
    """Get all videos pending upload (status is empty)."""
    with _csv_lock:
        rows = _read_csv()
        return [
            row for row in rows 
            if row.get("upload_status", "") == ""
        ]


def get_pending_by_channel() -> Dict[str, List[dict]]:
    """
    Get pending uploads grouped by channel.
    Returns dict like: {"ch1": [row1, row2, ...], "ch2": [...]}
    Rows within each channel are sorted by video_path (chronological).
    """
    pending = get_pending_uploads()
    
    # Group by channel
    by_channel = defaultdict(list)
    for row in pending:
        # Extract channel from path: ch1/2026-01-03/193627.ts
        parts = row["video_path"].split("/")
        if len(parts) >= 1:
            channel = parts[0]  # "ch1"
            by_channel[channel].append(row)
    
    # Sort each channel's files by path (chronological order)
    for channel in by_channel:
        by_channel[channel].sort(key=lambda r: r["video_path"])
    
    return dict(by_channel)


def delete_uploaded_files(recordings_dir: str = "/recordings"):
    """Delete local files that have been uploaded (status='done')."""
    with _csv_lock:
        rows = _read_csv()
        remaining = []
        
        for row in rows:
            if row.get("upload_status") == "done":
                full_path = os.path.join(recordings_dir, row["video_path"])
                try:
                    if os.path.exists(full_path):
                        os.remove(full_path)
                except OSError:
                    pass
                # Don't add to remaining (remove from CSV)
            else:
                remaining.append(row)
        
        _write_csv(remaining)
