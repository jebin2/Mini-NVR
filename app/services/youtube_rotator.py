"""
YouTube Live Stream Service - Enhanced with debugging

Streams camera to YouTube and creates separate videos by pausing/resuming hourly.
Uses go2rtc's native RTMP output capability with FFmpeg audio transcoding.
"""
import threading
import time
import requests
import socket
from typing import Optional, Callable
from core import config
from core.logger import setup_logger

logger = setup_logger("youtube")

# Default pause duration when restarting stream (seconds)
PAUSE_DURATION = 10


def test_youtube_connectivity(rtmp_url: str = "a.rtmp.youtube.com", port: int = 1935) -> bool:
    """Test if YouTube RTMP server is reachable."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        result = sock.connect_ex((rtmp_url, port))
        sock.close()
        return result == 0
    except Exception as e:
        logger.error(f"[❌] Connectivity test failed: {e}")
        return False


class YouTubeStreamer(threading.Thread):
    """
    Stream camera to YouTube with periodic restart to create video segments.
    
    Each restart creates a new video on YouTube, making it easy to archive
    and playback specific time periods.
    """
    
    def __init__(
        self,
        go2rtc_api: str,
        channel: int,
        stream_key: str,
        rtmp_url: str = "rtmp://a.rtmp.youtube.com/live2",
        segment_minutes: int = 60,
        pause_seconds: int = PAUSE_DURATION,
        on_restart: Optional[Callable[[int], None]] = None
    ):
        """
        Initialize YouTube streamer.
        
        Args:
            go2rtc_api: go2rtc API URL (e.g., "http://localhost:2127")
            channel: Camera channel number to stream
            stream_key: YouTube stream key for this channel
            rtmp_url: YouTube RTMP ingest URL
            segment_minutes: Minutes between restarts (creates new video)
            pause_seconds: Seconds to pause when restarting
            on_restart: Optional callback(segment_count) on restart
        """
        super().__init__()
        self.go2rtc_api = go2rtc_api.rstrip('/')
        self.channel = channel
        self.stream_key = stream_key
        self.rtmp_url = rtmp_url.rstrip('/')
        self.segment_minutes = segment_minutes
        self.pause_seconds = pause_seconds
        self.on_restart = on_restart
        
        self.streaming = False
        self.segment_count = 0
        self.last_start_time: Optional[float] = None
        self._stop_event = threading.Event()
        self.daemon = True
        
        # Debug info
        logger.debug(f"[🔧] YouTubeStreamer initialized:")
        logger.debug(f"     go2rtc_api: {self.go2rtc_api}")
        logger.debug(f"     channel: {self.channel}")
        logger.debug(f"     rtmp_url: {self.rtmp_url}")
        logger.debug(f"     stream_key: {'*' * (len(stream_key) - 4)}{stream_key[-4:]}")
    
    @property
    def next_restart_seconds(self) -> int:
        """Seconds until next restart."""
        if not self.last_start_time:
            return 0
        elapsed = time.time() - self.last_start_time
        remaining = (self.segment_minutes * 60) - elapsed
        return max(0, int(remaining))
    
    def _get_youtube_stream_name(self) -> str:
        """Get the YouTube-ready stream name with AAC audio transcoding."""
        return f"cam{self.channel}_youtube"
    
    def _build_rtmp_destination(self) -> str:
        """Build RTMP destination URL for YouTube."""
        return f"{self.rtmp_url}/{self.stream_key}"
    
    def _verify_go2rtc_stream(self) -> bool:
        """Verify the YouTube stream exists in go2rtc."""
        youtube_stream = self._get_youtube_stream_name()
        try:
            response = requests.get(f"{self.go2rtc_api}/api/streams", timeout=5)
            if response.status_code == 200:
                streams = response.json()
                if youtube_stream in streams:
                    logger.debug(f"[✓] Stream '{youtube_stream}' found in go2rtc")
                    return True
                else:
                    logger.error(f"[❌] Stream '{youtube_stream}' NOT found in go2rtc config!")
                    logger.error(f"     Available streams: {list(streams.keys())}")
                    return False
            else:
                logger.error(f"[❌] Failed to get streams from go2rtc: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"[❌] Failed to verify go2rtc stream: {e}")
            return False
    
    def _start_stream(self) -> bool:
        """Start streaming to YouTube."""
        youtube_stream = self._get_youtube_stream_name()
        rtmp_dest = self._build_rtmp_destination()
        
        # Verify stream exists
        if not self._verify_go2rtc_stream():
            return False
        
        # Test YouTube connectivity
        rtmp_server = self.rtmp_url.split("//")[1].split("/")[0]
        logger.debug(f"[🔍] Testing connectivity to {rtmp_server}:1935...")
        if not test_youtube_connectivity(rtmp_server):
            logger.error(f"[❌] Cannot reach YouTube RTMP server {rtmp_server}:1935")
            logger.error("     Check firewall rules: sudo ufw allow out 1935/tcp")
            return False
        logger.debug(f"[✓] YouTube RTMP server is reachable")
        
        try:
            logger.debug(f"[→] Starting stream: {youtube_stream} -> YouTube")
            # Use /api/stream.flv endpoint for RTMP push (not /api/streams)
            response = requests.post(
                f"{self.go2rtc_api}/api/stream.flv",
                params={
                    "src": youtube_stream,
                    "dst": rtmp_dest
                },
                timeout=60
            )
            
            logger.debug(f"[←] go2rtc response: {response.status_code}")
            
            if response.status_code == 200:
                self.streaming = True
                self.last_start_time = time.time()
                self.segment_count += 1
                logger.info(f"[📺] cam{self.channel} -> YouTube (Segment #{self.segment_count})")
                return True
            else:
                logger.error(f"[❌] go2rtc API error: {response.status_code}")
                logger.error(f"     Response: {response.text}")
                
                # Specific error handling
                if response.status_code == 400:
                    logger.error("     Possible causes:")
                    logger.error("     - Stream name doesn't exist in go2rtc.yaml")
                    logger.error("     - Invalid RTMP URL format")
                elif response.status_code == 500:
                    logger.error("     go2rtc internal error - check go2rtc logs")
                
                return False
                
        except requests.Timeout:
            logger.error(f"[❌] Timeout connecting to go2rtc (>60s)")
            return False
        except requests.ConnectionError as e:
            logger.error(f"[❌] Cannot connect to go2rtc API at {self.go2rtc_api}")
            logger.error(f"     Error: {e}")
            return False
        except requests.RequestException as e:
            logger.error(f"[❌] Request failed: {e}")
            return False
    
    def _stop_stream(self) -> bool:
        """Stop streaming to YouTube."""
        if not self.streaming:
            return True
            
        youtube_stream = self._get_youtube_stream_name()
        rtmp_dest = self._build_rtmp_destination()
        
        try:
            logger.debug(f"[→] Stopping stream: {youtube_stream}")
            # Use /api/stream.flv endpoint for RTMP push (not /api/streams)
            response = requests.post(
                f"{self.go2rtc_api}/api/stream.flv",
                params={
                    "src": youtube_stream,
                    "dst": ""  # Empty dst stops the stream
                },
                timeout=10
            )
            self.streaming = False
            logger.debug(f"[←] Stop response: {response.status_code}")
            return response.status_code == 200
        except requests.RequestException as e:
            logger.error(f"[❌] Error stopping stream: {e}")
            self.streaming = False
            return False
    
    def _restart_stream(self):
        """Stop and restart stream to create new YouTube video."""
        logger.info(f"[🔄] Restarting stream for cam{self.channel} (creates new video)")
        
        # Stop current stream
        self._stop_stream()
        
        # Brief pause - YouTube needs time to finalize the video
        logger.info(f"[⏸] Pausing {self.pause_seconds}s before restart...")
        time.sleep(self.pause_seconds)
        
        # Start new stream
        retry_count = 0
        while not self._stop_event.is_set() and retry_count < 3:
            if self._start_stream():
                if self.on_restart:
                    self.on_restart(self.segment_count)
                return
            retry_count += 1
            logger.warning(f"[⏳] Retry {retry_count}/3 in 5s...")
            time.sleep(5)
        
        logger.error(f"[❌] Failed to restart stream after {retry_count} attempts")
    
    def stop(self):
        """Stop the streamer thread."""
        logger.info(f"[⏹] Stopping YouTube streamer for cam{self.channel}")
        self._stop_event.set()
        self._stop_stream()
    
    def run(self):
        """Main streaming loop."""
        logger.info(f"[▶] YouTube Streamer started for cam{self.channel}")
        logger.info(f"[📋] Segment duration: {self.segment_minutes} minutes")
        logger.info(f"[⏸] Pause between segments: {self.pause_seconds}s")
        
        # Initial connection with exponential backoff
        retry_delay = 5
        max_delay = 60
        attempt = 0
        
        while not self._stop_event.is_set():
            attempt += 1
            logger.info(f"[🔌] Connection attempt #{attempt}")
            
            if self._start_stream():
                logger.info(f"[✓] Successfully connected on attempt #{attempt}")
                break
            
            logger.warning(f"[⏳] Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)
        
        # Main loop: check for restart every 10 seconds
        while not self._stop_event.is_set():
            if self.next_restart_seconds <= 0:
                self._restart_stream()
            time.sleep(10)
        
        logger.info(f"[⏹] YouTube Streamer stopped for cam{self.channel}")
    
    def get_status(self) -> dict:
        """Get current streaming status."""
        return {
            "enabled": True,
            "streaming": self.streaming,
            "channel": self.channel,
            "segment_count": self.segment_count,
            "next_restart_seconds": self.next_restart_seconds,
            "segment_duration_minutes": self.segment_minutes
        }


def create_youtube_streamers() -> list:
    """
    Factory function to create YouTubeStreamer instances from config.
    
    Creates one streamer per configured stream key.
    Returns list of streamers (empty if disabled or no keys configured).
    """
    if not config.YOUTUBE_LIVE_ENABLED:
        logger.info("[ℹ] YouTube streaming is disabled in config")
        return []
    
    logger.info("[📺] Initializing YouTube streamers...")
    
    # Test go2rtc connectivity first
    try:
        response = requests.get(f"{config.GO2RTC_API_URL}/api/streams", timeout=5)
        if response.status_code != 200:
            logger.error(f"[❌] go2rtc API not responding correctly: {response.status_code}")
            return []
        logger.info(f"[✓] go2rtc API is accessible at {config.GO2RTC_API_URL}")
    except Exception as e:
        logger.error(f"[❌] Cannot connect to go2rtc API: {e}")
        return []
    
    streamers = []
    
    # Use the YOUTUBE_STREAM_KEYS dict: {channel: stream_key}
    for channel, stream_key in config.YOUTUBE_STREAM_KEYS.items():
        streamer = YouTubeStreamer(
            go2rtc_api=config.GO2RTC_API_URL,
            channel=channel,
            stream_key=stream_key,
            rtmp_url=config.YOUTUBE_RTMP_URL,
            segment_minutes=config.YOUTUBE_ROTATION_MINUTES,
        )
        streamers.append(streamer)
        logger.info(f"[+] Configured YouTube stream: cam{channel}")
    
    if not streamers:
        logger.warning("[!] YouTube enabled but no stream keys configured (YOUTUBE_STREAM_KEY_1 to YOUTUBE_STREAM_KEY_8)")
    
    return streamers


# Legacy function for backward compatibility
def create_youtube_rotator():
    """Legacy function - returns first streamer or None."""
    streamers = create_youtube_streamers()
    return streamers[0] if streamers else None