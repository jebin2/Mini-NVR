"""
YouTube Live Stream Service

Streams camera to YouTube and creates separate videos by pausing/resuming hourly.
Uses go2rtc's native RTMP output capability with FFmpeg audio transcoding.

Architecture:
    DVR (RTSP) -> go2rtc (hub) -> FFmpeg (audio->AAC) -> YouTube (RTMP)
                      |
                      +-> WebRTC (live view)
                      +-> RTSP relay (recorder)

Behavior:
    - Each channel gets its own stream key (1:1 mapping)
    - Every hour: stop stream briefly, then restart
    - This creates separate YouTube videos for easy archiving
"""
import threading
import time
import requests
from typing import Optional, Callable
from core import config
from core.logger import setup_logger

logger = setup_logger("youtube")

# Default pause duration when restarting stream (seconds)
PAUSE_DURATION = 10


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
    
    def _start_stream(self) -> bool:
        """Start streaming to YouTube."""
        youtube_stream = self._get_youtube_stream_name()
        rtmp_dest = self._build_rtmp_destination()
        
        try:
            response = requests.post(
                f"{self.go2rtc_api}/api/streams",
                params={
                    "src": youtube_stream,
                    "dst": rtmp_dest
                },
                timeout=60
            )
            
            if response.status_code == 200:
                self.streaming = True
                self.last_start_time = time.time()
                self.segment_count += 1
                logger.info(f"[📺] cam{self.channel} -> YouTube (Segment #{self.segment_count})")
                return True
            else:
                logger.error(f"[❌] go2rtc API error: {response.status_code} - {response.text}")
                return False
                
        except requests.RequestException as e:
            logger.error(f"[❌] Failed to connect to go2rtc: {e}")
            return False
    
    def _stop_stream(self) -> bool:
        """Stop streaming to YouTube."""
        if not self.streaming:
            return True
            
        youtube_stream = self._get_youtube_stream_name()
        rtmp_dest = self._build_rtmp_destination()
        
        try:
            response = requests.delete(
                f"{self.go2rtc_api}/api/streams",
                params={
                    "src": youtube_stream,
                    "dst": rtmp_dest
                },
                timeout=10
            )
            self.streaming = False
            return response.status_code == 200
        except requests.RequestException:
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
            time.sleep(5)
        
        logger.error(f"[❌] Failed to restart stream after {retry_count} attempts")
    
    def stop(self):
        """Stop the streamer thread."""
        self._stop_event.set()
        self._stop_stream()
    
    def run(self):
        """Main streaming loop."""
        logger.info(f"[▶] YouTube Streamer started for cam{self.channel}")
        logger.info(f"[📋] Segment duration: {self.segment_minutes} minutes")
        logger.info(f"[⏸] Pause between segments: {self.pause_seconds}s")
        
        # Initial connection with retry
        retry_delay = 5
        while not self._stop_event.is_set():
            if self._start_stream():
                break
            logger.warning(f"[⏳] Retrying in {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, 60)
        
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
    
    Creates one streamer per configured stream key:
    - YOUTUBE_STREAM_KEY_1 -> cam1
    - YOUTUBE_STREAM_KEY_2 -> cam2
    - ... up to YOUTUBE_STREAM_KEY_8 -> cam8
    
    Returns list of streamers (empty if disabled or no keys configured).
    """
    if not config.YOUTUBE_LIVE_ENABLED:
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
