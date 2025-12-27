"""
YouTube Live Stream Rotator Service

Manages YouTube Live streaming via go2rtc with automatic stream key rotation.
Uses go2rtc's native RTMP output capability - no additional FFmpeg process needed.

Architecture:
    DVR (RTSP) -> go2rtc (hub) -> YouTube (RTMP)
                      |
                      +-> WebRTC (live view)
                      +-> RTSP relay (recorder)
"""
import threading
import time
import requests
from typing import List, Optional, Callable
from core import config
from core.logger import setup_logger

logger = setup_logger("youtube")


class YouTubeRotator(threading.Thread):
    """
    Rotate YouTube stream keys via go2rtc API.
    
    go2rtc handles the actual RTSP->RTMP transcoding.
    This service just manages the stream destination rotation.
    """
    
    def __init__(
        self,
        go2rtc_api: str,
        channel: int,
        stream_keys: List[str],
        rtmp_url: str = "rtmp://a.rtmp.youtube.com/live2",
        rotation_minutes: int = 60,
        on_rotation: Optional[Callable[[int, str], None]] = None
    ):
        """
        Initialize YouTube rotator.
        
        Args:
            go2rtc_api: go2rtc API URL (e.g., "http://localhost:2127")
            channel: Camera channel number to stream
            stream_keys: List of YouTube stream keys to rotate between
            rtmp_url: YouTube RTMP ingest URL
            rotation_minutes: Minutes between key rotations
            on_rotation: Optional callback(key_index, key) on rotation
        """
        super().__init__()
        self.go2rtc_api = go2rtc_api.rstrip('/')
        self.channel = channel
        self.stream_keys = stream_keys
        self.rtmp_url = rtmp_url.rstrip('/')
        self.rotation_minutes = rotation_minutes
        self.on_rotation = on_rotation
        
        self.current_key_index = 0
        self.streaming = False
        self.last_rotation_time: Optional[float] = None
        self._stop_event = threading.Event()
        self.daemon = True
        
        # Validate
        if len(stream_keys) < 1:
            raise ValueError("At least one stream key required")
    
    @property
    def current_key(self) -> str:
        """Get current stream key."""
        return self.stream_keys[self.current_key_index]
    
    @property
    def next_rotation_seconds(self) -> int:
        """Seconds until next rotation."""
        if not self.last_rotation_time:
            return 0
        elapsed = time.time() - self.last_rotation_time
        remaining = (self.rotation_minutes * 60) - elapsed
        return max(0, int(remaining))
    
    def _build_rtmp_destination(self, key: str) -> str:
        """Build RTMP destination URL for go2rtc."""
        # go2rtc RTMP output format: rtmp://server/app/key#video=copy
        return f"{self.rtmp_url}/{key}#video=copy"
    
    def _add_stream_output(self, key: str) -> bool:
        """Add RTMP output to go2rtc stream via API."""
        stream_name = f"cam{self.channel}"
        rtmp_dest = self._build_rtmp_destination(key)
        
        try:
            # go2rtc API: POST /api/streams?dst=stream_name&src=output_url
            response = requests.post(
                f"{self.go2rtc_api}/api/streams",
                params={
                    "dst": stream_name,
                    "src": rtmp_dest
                },
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info(f"[📺] Streaming cam{self.channel} to YouTube (Key {self.current_key_index + 1})")
                return True
            else:
                logger.error(f"[❌] go2rtc API error: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"[❌] Failed to connect to go2rtc: {e}")
            return False
    
    def _remove_stream_output(self, key: str) -> bool:
        """Remove RTMP output from go2rtc stream."""
        stream_name = f"cam{self.channel}"
        rtmp_dest = self._build_rtmp_destination(key)
        
        try:
            # go2rtc API: DELETE /api/streams?dst=stream_name&src=output_url
            response = requests.delete(
                f"{self.go2rtc_api}/api/streams",
                params={
                    "dst": stream_name,
                    "src": rtmp_dest
                },
                timeout=10
            )
            return response.status_code == 200
        except requests.RequestException:
            return False
    
    def _rotate_key(self):
        """Rotate to next stream key."""
        old_key = self.current_key
        old_index = self.current_key_index
        
        # Calculate next key index
        self.current_key_index = (self.current_key_index + 1) % len(self.stream_keys)
        new_key = self.current_key
        
        logger.info(f"[🔄] Rotating from Key {old_index + 1} to Key {self.current_key_index + 1}")
        
        # Add new output first (overlap for seamless transition)
        if self._add_stream_output(new_key):
            # Small delay to ensure new stream is established
            time.sleep(5)
            # Remove old output
            self._remove_stream_output(old_key)
            
            if self.on_rotation:
                self.on_rotation(self.current_key_index, new_key)
        else:
            # Failed to add new, revert
            self.current_key_index = old_index
            logger.error("[❌] Rotation failed, keeping current key")
    
    def start_streaming(self) -> bool:
        """Start streaming to YouTube."""
        if self.streaming:
            return True
        
        if self._add_stream_output(self.current_key):
            self.streaming = True
            self.last_rotation_time = time.time()
            return True
        return False
    
    def stop_streaming(self):
        """Stop streaming to YouTube."""
        if not self.streaming:
            return
        
        self._remove_stream_output(self.current_key)
        self.streaming = False
        logger.info("[⏹] YouTube streaming stopped")
    
    def stop(self):
        """Stop the rotator thread."""
        self._stop_event.set()
        self.stop_streaming()
    
    def run(self):
        """Main rotation loop."""
        logger.info(f"[▶] YouTube Rotator started for cam{self.channel}")
        logger.info(f"[📋] Rotation interval: {self.rotation_minutes} minutes")
        logger.info(f"[🔑] Stream keys configured: {len(self.stream_keys)}")
        
        # Initial connection with retry
        retry_delay = 5
        while not self._stop_event.is_set():
            if self.start_streaming():
                break
            logger.warning(f"[⏳] Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)  # Exponential backoff, max 60s
        
        # Rotation loop
        while not self._stop_event.is_set():
            # Check if time for rotation
            if self.next_rotation_seconds <= 0:
                self._rotate_key()
                self.last_rotation_time = time.time()
            
            # Sleep in small intervals for responsive shutdown
            time.sleep(10)
        
        logger.info("[⏹] YouTube Rotator stopped")
    
    def get_status(self) -> dict:
        """Get current streaming status."""
        return {
            "enabled": True,
            "streaming": self.streaming,
            "channel": self.channel,
            "current_key_index": self.current_key_index + 1,
            "total_keys": len(self.stream_keys),
            "next_rotation_seconds": self.next_rotation_seconds,
            "rotation_interval_minutes": self.rotation_minutes
        }


def create_youtube_rotator() -> Optional[YouTubeRotator]:
    """
    Factory function to create YouTubeRotator from config.
    Returns None if YouTube streaming is not enabled or configured.
    """
    if not config.YOUTUBE_ENABLED:
        return None
    
    # Collect stream keys
    stream_keys = []
    if config.YOUTUBE_STREAM_KEY_1:
        stream_keys.append(config.YOUTUBE_STREAM_KEY_1)
    if config.YOUTUBE_STREAM_KEY_2:
        stream_keys.append(config.YOUTUBE_STREAM_KEY_2)
    
    if not stream_keys:
        logger.warning("[!] YouTube enabled but no stream keys configured")
        return None
    
    return YouTubeRotator(
        go2rtc_api=config.GO2RTC_API_URL,
        channel=config.YOUTUBE_CHANNEL,
        stream_keys=stream_keys,
        rtmp_url=config.YOUTUBE_RTMP_URL,
        rotation_minutes=config.YOUTUBE_ROTATION_MINUTES
    )
