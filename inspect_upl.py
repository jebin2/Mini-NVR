import inspect
import sys
import os

# Add potential paths
sys.path.insert(0, os.path.expanduser("~/git/youtube_auto_pub"))

try:
    from youtube_auto_pub import YouTubeUploader
    print(inspect.getsource(YouTubeUploader.upload_video))
except ImportError:
    print("Could not import youtube_auto_pub")
except Exception as e:
    print(f"Error: {e}")
