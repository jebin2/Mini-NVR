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
WEB_PORT = int(get_env("WEB_PORT", 8000))
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

# Ensure dirs
os.makedirs(CONTROL_DIR, exist_ok=True)

# Auth
SECRET_KEY = get_env("SECRET_KEY", "dev_secret")
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
