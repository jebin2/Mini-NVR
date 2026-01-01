import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from api.routes import router as api_router
from utils.helpers import is_file_live
from api.auth import router as auth_router
from api.go2rtc_proxy import router as go2rtc_router, ws_router as go2rtc_ws_router
from core import config
from core.logger import setup_logger

logger = setup_logger("server")

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from core.security import limiter

app = FastAPI(title="NVR UI")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware to allow requests from voidall.com domains
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"https://.*\.?voidall\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Range", "Accept-Ranges", "Content-Type", "Date"],
)

app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

# Mount API
app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")
# go2rtc proxy: WebSocket router first (specific path), then HTTP router (catch-all)
app.include_router(go2rtc_ws_router, prefix="/api/go2rtc")
app.include_router(go2rtc_router, prefix="/api/go2rtc")

# --- Static & File Serving ---

@app.get("/")
def serve_ui():
    index_path = os.path.join(config.STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>NVR UI Error</h1><p>index.html not found.</p>")

@app.get("/login.html")
def serve_login():
    return serve_static(config.STATIC_DIR, "login.html", "text/html")

@app.get("/{filename}")
def serve_root_files(filename: str):
    """Serve PWA files and other root assets."""
    allowed = {
        "sw.js": "application/javascript",
        "manifest.json": "application/manifest+json",
        "icon-192.png": "image/png",
        "icon-512.png": "image/png",
        "favicon.ico": "image/x-icon"
    }
    
    if filename in allowed:
        return serve_static(config.STATIC_DIR, filename, allowed[filename])
        
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/recordings/{path:path}")
def serve_video(path: str):
    # Security check to prevent directory traversal
    abs_path = os.path.abspath(os.path.join(config.RECORD_DIR, path))
    if not abs_path.startswith(os.path.abspath(config.RECORD_DIR)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    # Determine correct MIME type
    if path.lower().endswith('.mp4'):
        media_type = "video/mp4"
    else:
        media_type = "video/x-matroska"
    
    # Explicit CORS headers for video responses (Cloudflare may cache before middleware applies)
    cors_headers = {
        "Access-Control-Allow-Origin": "https://www.voidall.com",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type, Date",
    }
        
    # Fix for LocalProtocolError: Too much data for declared Content-Length
    # If file is live (growing), FileResponse sets Content-Length to X but might read X+Y bytes.
    # Use StreamingResponse for live files to avoid setting Content-Length (uses Chunked encoding).
    if is_file_live(abs_path):
        # Allow JellyJump to see Content-Length even for live files
        file_size = os.path.getsize(abs_path)
        cors_headers["Content-Length"] = str(file_size)

        def iter_file():
            bytes_remaining = file_size
            with open(abs_path, "rb") as f:
                while bytes_remaining > 0:
                    read_size = min(64 * 1024, bytes_remaining)
                    chunk = f.read(read_size)
                    if not chunk:
                        break
                    yield chunk
                    bytes_remaining -= len(chunk)

        return StreamingResponse(iter_file(), media_type=media_type, headers=cors_headers)

    return FileResponse(abs_path, media_type=media_type, headers=cors_headers)

@app.get("/css/{path:path}")
def serve_css(path: str):
    return serve_static(os.path.join(config.STATIC_DIR, "css"), path, "text/css")

@app.get("/js/{path:path}")
def serve_js(path: str):
    return serve_static(os.path.join(config.STATIC_DIR, "js"), path, "application/javascript")

def serve_static(base_dir, path, media_type):
    # Security check
    abs_base = os.path.abspath(base_dir)
    abs_path = os.path.abspath(os.path.join(abs_base, path))
    
    if not abs_path.startswith(abs_base):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    return FileResponse(abs_path, media_type=media_type)

if __name__ == "__main__":
    logger.info(f"Starting NVR on port {config.WEB_PORT}...")
    logger.info(f"Recordings: {os.path.abspath(config.RECORD_DIR)}")
    logger.info(f"Static: {config.STATIC_DIR}")
    uvicorn.run(app, host="0.0.0.0", port=config.WEB_PORT)