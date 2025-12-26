import subprocess

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
