import os
import warnings
from dataclasses import dataclass, field
from typing import List, Dict
# Load environment variables automatically
def load_env():
    """Load environment variables from .env file."""
    # core/config.py -> core -> app -> Project Root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    app_dir = os.path.dirname(current_dir)
    project_dir = os.path.dirname(app_dir)
        
    env_path = os.path.join(project_dir, ".env")
    
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    
                    if key not in os.environ:
                        os.environ[key] = value

load_env()

def get_env(name, default=None):
    return os.getenv(name, default)

def get_list_env(name, delimiter=","):
    val = get_env(name, "")
    if not val:
        return []
    return [x.strip() for x in val.split(delimiter) if x.strip()]

@dataclass
class Settings:
    # --- Global ---
    record_dir: str = field(default_factory=lambda: get_env("RECORD_DIR"))
    num_channels: int = field(default_factory=lambda: int(get_env("NUM_CHANNELS", "0")))
    skip_channels: List[int] = field(default_factory=lambda: [int(x) for x in get_list_env("SKIP_CHANNELS")])
    
    segment_duration: int = field(default_factory=lambda: int(get_env("SEGMENT_DURATION", "10")))
    max_storage_gb: int = field(default_factory=lambda: int(get_env("MAX_STORAGE_GB", "1000")))
    max_storage_exceed_allowed_gb: int = field(default_factory=lambda: int(get_env("MAX_STORAGE_EXCEED_ALLOWED_GB", "50")))
    cleanup_interval: int = field(default_factory=lambda: int(get_env("CLEANUP_INTERVAL", "60")))
    
    youtube_upload_enabled: bool = field(default_factory=lambda: get_env("YOUTUBE_UPLOAD_ENABLED", "false").lower() == "true")
    
    web_port: int = field(default_factory=lambda: int(get_env("WEB_PORT")))
    control_dir: str = "/tmp/nvr-control"
    static_dir: str = os.path.abspath("./web")
    log_file: str = field(default_factory=lambda: get_env("LOG_FILE"))
    
    # --- Recorder ---
    dvr_ip: str = field(default_factory=lambda: get_env("DVR_IP"))
    dvr_user: str = field(default_factory=lambda: get_env("DVR_USER"))
    dvr_pass: str = field(default_factory=lambda: get_env("DVR_PASS"))
    dvr_port: str = field(default_factory=lambda: get_env("DVR_PORT"))
    rtsp_url_template: str = field(default_factory=lambda: get_env("RTSP_URL_TEMPLATE"))
    ffmpeg_bin: str = field(default_factory=lambda: get_env("FFMPEG_BIN", "ffmpeg"))
    video_codec: str = field(default_factory=lambda: get_env("VIDEO_CODEC", "copy"))
    video_crf: str = field(default_factory=lambda: get_env("VIDEO_CRF", "23"))
    video_preset: str = field(default_factory=lambda: get_env("VIDEO_PRESET", "veryfast"))
    inline_transcoding: bool = field(default_factory=lambda: get_env("INLINE_TRANSCODING", "false").lower() == "true")
    
    # --- go2rtc ---
    go2rtc_api_port: int = field(default_factory=lambda: int(get_env("GO2RTC_API_PORT")))
    go2rtc_rtsp_port: int = field(default_factory=lambda: int(get_env("GO2RTC_RTSP_PORT")))
    
    @property
    def go2rtc_api_url(self) -> str:
        return f"http://localhost:{self.go2rtc_api_port}"
    
    # --- YouTube Streaming ---
    youtube_live_enabled: bool = field(default_factory=lambda: get_env("YOUTUBE_LIVE_ENABLED", "false").lower() == "true")
    youtube_sync_enabled: bool = field(default_factory=lambda: get_env("YOUTUBE_SYNC_ENABLED", "true").lower() == "true")
    youtube_rtmp_url: str = field(default_factory=lambda: get_env("YOUTUBE_RTMP_URL", "rtmp://a.rtmp.youtube.com/live2"))
    youtube_rotation_hours: float = field(default_factory=lambda: float(get_env("YOUTUBE_ROTATION_HOURS", "11")))
    youtube_live_restart_interval_hours: float = field(default_factory=lambda: float(get_env("YOUTUBE_LIVE_RESTART_INTERVAL_HOURS", "2")))
    youtube_grid: int = field(default_factory=lambda: int(get_env("YOUTUBE_GRID", "4")))
    
    # --- YouTube Upload ---
    youtube_video_privacy: str = field(default_factory=lambda: get_env("YOUTUBE_VIDEO_PRIVACY", "unlisted"))
    youtube_delete_after_upload: bool = field(default_factory=lambda: get_env("YOUTUBE_DELETE_AFTER_UPLOAD", "false").lower() == "true")
    youtube_upload_interval: int = field(default_factory=lambda: int(get_env("YOUTUBE_UPLOAD_INTERVAL", "60")))
    youtube_upload_batch_size_mb: int = field(default_factory=lambda: int(get_env("YOUTUBE_UPLOAD_BATCH_SIZE_MB", "50")))
    
    # --- Compressor ---
    compressor_enabled: bool = field(default_factory=lambda: get_env("COMPRESSOR_ENABLED", "true").lower() == "true")
    
    # --- YouTube Accounts & Encryption ---
    youtube_encrypt_path: str = field(default_factory=lambda: get_env("YOUTUBE_ENCRYPT_PATH"))
    hf_repo_id: str = field(default_factory=lambda: get_env("HF_REPO_ID"))
    hf_token: str = field(default_factory=lambda: get_env("HF_TOKEN"))
    yt_encrypt_key: str = field(default_factory=lambda: get_env("YT_ENCRYP_KEY"))
    project_dir: str = field(default_factory=lambda: get_env("PROJECT_DIR"))
    ssh_host_user: str = field(default_factory=lambda: get_env("SSH_HOST_USER", "jebin"))

    # Keys
    youtube_stream_keys: Dict[int, str] = field(init=False)
    youtube_accounts: List[Dict] = field(init=False)

    # --- Auth ---
    secret_key: str = field(init=False)
    users: Dict[str, str] = field(init=False)

    def __post_init__(self):
        # Process Channels
        self.num_channels = int(self.num_channels) if self.num_channels else 0
        
        # Stream Keys
        self.youtube_stream_keys = {}
        for i in range(1, 9):
            key = get_env(f"YOUTUBE_STREAM_KEY_{i}")
            if key:
                self.youtube_stream_keys[i] = key
                
        # YouTube Accounts (with per-account credentials)
        self.youtube_accounts = []
        i = 1
        while True:
            s = get_env(f"YOUTUBE_CLIENT_SECRET_PATH_{i}")
            t = get_env(f"YOUTUBE_TOKEN_PATH_{i}")
            if not s or not t:
                break
            self.youtube_accounts.append({
                "id": i,
                "client_secret": s,
                "token_path": t,
                "google_email": get_env(f"GOOGLE_EMAIL_{i}"),
                "google_password": get_env(f"GOOGLE_PASSWORD_{i}")
            })
            i += 1
        
        # Secret Key
        _secret = get_env("SECRET_KEY")
        if not _secret:
            warnings.warn("SECRET_KEY not set! Using insecure default.", stacklevel=2)
            _secret = "INSECURE_DEV_SECRET_CHANGE_ME"
        self.secret_key = _secret
        
        # Users
        self.users = {}
        i = 1
        while True:
            u = get_env(f"user{i}")
            p = get_env(f"pass{i}")
            if u and p:
                self.users[u] = p
                i += 1
            else:
                break
        
        # Ensure Dirs
        try:
            os.makedirs(self.control_dir, exist_ok=True)
        except OSError:
            pass

    def get_active_channels(self):
        """Get list of active channel numbers, excluding skipped ones."""
        return [c for c in range(1, self.num_channels + 1) if c not in self.skip_channels]

# Instantiate Singleton
try:
    settings = Settings()
except Exception as e:
    # If instantiation fails (e.g. bad int conversion), print error but proceed??
    # Ideally should crash if config is invalid.
    print(f"FAILED TO LOAD CONFIG: {e}")
    raise e



# Explicitly exporting 'settings'
__all__ = ["settings", "Settings"]
