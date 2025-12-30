import os

def get_env(name, default=None):
    return os.getenv(name, default)

def get_required_env(name):
    value = os.getenv(name)
    if value is None:
        raise EnvironmentError(f"Required env var '{name}' not set")
    return value

# Global Settings
RECORD_DIR = get_env("RECORD_DIR", "./recordings")
NUM_CHANNELS = int(get_env("NUM_CHANNELS", 8))
SEGMENT_DURATION = int(get_env("SEGMENT_DURATION", 600)) 
MAX_STORAGE_GB = int(get_env("MAX_STORAGE_GB", 500))
MAX_STORAGE_EXCEED_ALLOWED_GB = int(get_env("MAX_STORAGE_EXCEED_ALLOWED_GB", 10))
YOUTUBE_UPLOAD_ENABLED = get_env("YOUTUBE_UPLOAD_ENABLED", "false").lower() == "true"
WEB_PORT = int(get_env("WEB_PORT", 2126))
CONTROL_DIR = "/tmp/nvr-control"
STATIC_DIR = "./web" # Pointing to web folder directly now, or we can copy to static. 
# Original code had "./static", but the user has a "web" folder. 
# server.py had: STATIC_DIR = "./static" and serve_ui used os.path.join(STATIC_DIR, "index.html")
# But the file list showed web/index.html. "static" might have been a runtime thing or misconfiguration.
# Given the user has `web/index.html`, I'll set STATIC_DIR to "./web" for development or "./static" for prod.
# Let's stick to "./web" since that's where the source is.
STATIC_DIR = os.path.abspath("./web")

# Recorder Specific
DVR_IP = get_env("DVR_IP")
DVR_USER = get_env("DVR_USER")
DVR_PASS = get_env("DVR_PASS")
DVR_PORT = get_env("DVR_PORT")
RTSP_URL_TEMPLATE = get_env("RTSP_URL_TEMPLATE")
FFMPEG_BIN = get_env("FFMPEG_BIN", "ffmpeg")
VIDEO_CODEC = get_env("VIDEO_CODEC", "copy")
VIDEO_CRF = get_env("VIDEO_CRF", "23")
VIDEO_PRESET = get_env("VIDEO_PRESET", "veryfast")

# go2rtc Settings
GO2RTC_API_PORT = int(get_env("GO2RTC_API_PORT", 2127))
GO2RTC_RTSP_PORT = int(get_env("GO2RTC_RTSP_PORT", 8554))
GO2RTC_API_URL = f"http://localhost:{GO2RTC_API_PORT}"

# YouTube Streaming (via go2rtc)
YOUTUBE_LIVE_ENABLED = get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true"
YOUTUBE_RTMP_URL = get_env("YOUTUBE_RTMP_URL", "rtmp://a.rtmp.youtube.com/live2")
YOUTUBE_ROTATION_MINUTES = int(get_env("YOUTUBE_ROTATION_MINUTES", 60))

# Stream keys: YOUTUBE_STREAM_KEY_1 through YOUTUBE_STREAM_KEY_8
# Each key maps to corresponding channel (key1 -> cam1, etc.)
YOUTUBE_STREAM_KEYS = {}
for i in range(1, 9):  # 1-8
    key = get_env(f"YOUTUBE_STREAM_KEY_{i}")
    if key:
        YOUTUBE_STREAM_KEYS[i] = key

# YouTube Upload Settings
# NOTE: YouTube upload now runs on HOST (not in Docker) via start.sh
# This allows Neko browser automation for OAuth re-authentication
# Config is read directly from .env by youtube_uploader/main.py

# Ensure dirs
os.makedirs(CONTROL_DIR, exist_ok=True)

# Auth
# SECRET_KEY is required for session security
_secret = get_env("SECRET_KEY")
if not _secret:
    import warnings
    warnings.warn(
        "SECRET_KEY not set! Using insecure default. "
        "Set SECRET_KEY in .env for production.", 
        stacklevel=2
    )
    _secret = "INSECURE_DEV_SECRET_CHANGE_ME"
SECRET_KEY = _secret
USERS = {}
i = 1
while True:
    u = get_env(f"user{i}")
    p = get_env(f"pass{i}")
    if u and p:
        USERS[u] = p
        i += 1
    else:
        break
