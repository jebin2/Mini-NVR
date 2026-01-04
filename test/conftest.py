"""
Pytest configuration for Mini-NVR tests.

Sets up the test environment to run outside Docker.
"""
import os
import sys
import tempfile

# Create temp directories FIRST
_temp_dir = tempfile.mkdtemp(prefix="nvr_test_")
_logs_dir = os.path.join(_temp_dir, "logs")
_recordings_dir = os.path.join(_temp_dir, "recordings")
_static_dir = os.path.join(_temp_dir, "web")
os.makedirs(_logs_dir, exist_ok=True)
os.makedirs(_recordings_dir, exist_ok=True)
os.makedirs(_static_dir, exist_ok=True)

# Create dummy static files
with open(os.path.join(_static_dir, "index.html"), "w") as f:
    f.write("<html><body>Test</body></html>")
with open(os.path.join(_static_dir, "login.html"), "w") as f:
    f.write("<html><body>Login</body></html>")
with open(os.path.join(_static_dir, "manifest.json"), "w") as f:
    f.write("{}")
with open(os.path.join(_static_dir, "sw.js"), "w") as f:
    f.write("// service worker")
with open(os.path.join(_static_dir, "favicon.ico"), "wb") as f:
    f.write(b'\x00\x00\x01\x00')  # Minimal ICO header
for size in ["192", "512"]:
    with open(os.path.join(_static_dir, f"icon-{size}.png"), "wb") as f:
        f.write(b'\x89PNG\r\n\x1a\n')  # Minimal PNG header

# Set environment BEFORE any app imports
os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
os.environ["SECRET_KEY"] = "test-secret-key-for-testing-only-32chars!"
os.environ["RECORDINGS_DIR"] = _recordings_dir
os.environ["GO2RTC_API_PORT"] = "1984"
os.environ["LOG_FILE"] = os.path.join(_logs_dir, "test.log")
os.environ["STATIC_DIR"] = _static_dir
os.environ["NUM_CHANNELS"] = "2"
os.environ["ACTIVE_CHANNELS"] = "1,2"

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'app'))
