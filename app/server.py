import os
import uvicorn
from fastapi import FastAPI, HTTPException, Depends
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from api.routes import router as api_router
from utils.helpers import is_file_live
from api.go2rtc_proxy import router as go2rtc_router, ws_router as go2rtc_ws_router
from core import config
from core.logger import setup_logger

from google_auth_service import GoogleAuth, GoogleAuthMiddleware

logger = setup_logger("server")

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from core.security import limiter

app = FastAPI(title="NVR UI")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# 1. Initialize Auth
auth = GoogleAuth(
    client_id=os.getenv("GOOGLE_CLIENT_ID", ""),
    jwt_secret=config.settings.secret_key, # Use existing secret
    cookie_samesite="lax",
    cookie_secure=False # Set True if HTTPS
)

# 2. Add Middleware (Must wrap Auth with CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://www.voidall.com",
        "https://cctv.voidall.com",
        "https://voidall.com",
        "http://localhost:5173",  # Vite dev server
        "http://localhost:2126",  # Mini-NVR local
        "http://127.0.0.1:5173",
        "http://127.0.0.1:2126",
    ],
    allow_origin_regex=r"https://.*\.?voidall\.com",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Range", "Accept-Ranges", "Content-Type", "Date"],
)

# Add COOP header for Google Sign-In (Popups)
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    return response

app.add_middleware(
    GoogleAuthMiddleware,
    google_auth=auth,
    public_paths=[
        "/api/auth/*", # Whitelist auth endpoints
        "/login.html", 
        "/", 
        "/api/go2rtc",
        "/assets",
        "/manifest.json",
        "/sw.js",
        "/icon-192.png", 
        "/icon-512.png", 
        "/favicon.ico"
    ]
)

# Mount API
app.include_router(auth.get_router(prefix="/api/auth")) # Routes: /api/auth/google, etc.
app.include_router(api_router, prefix="/api")

# go2rtc proxy: Restored
app.include_router(go2rtc_ws_router, prefix="/api/go2rtc")
app.include_router(go2rtc_router, prefix="/api/go2rtc")

# --- Static & File Serving ---

@app.get("/")
def serve_ui():
    index_path = os.path.join(config.settings.static_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>NVR UI Error</h1><p>index.html not found.</p>")

@app.get("/login.html")
def serve_login():
    return serve_static(config.settings.static_dir, "login.html", "text/html")

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
        return serve_static(config.settings.static_dir, filename, allowed[filename])
        
    raise HTTPException(status_code=404, detail="File not found")

@app.get("/recordings/{path:path}")
def serve_video(path: str, user = Depends(auth.current_user)): # Protected
    # Security check to prevent directory traversal
    abs_path = os.path.abspath(os.path.join(config.settings.record_dir, path))
    if not abs_path.startswith(os.path.abspath(config.settings.record_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found")
        
    # Determine correct MIME type
    if path.lower().endswith('.mp4'):
        media_type = "video/mp4"
    else:
        media_type = "video/x-matroska"
    
    # Explicit CORS headers for video responses
    # Allow both voidall.com and localhost for development
    origin = "https://www.voidall.com"
    cors_headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges, Content-Type, Date",
    }
        
    if is_file_live(abs_path):
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

@app.get("/assets/{path:path}")
def serve_assets(path: str):
    """Serve Vite static assets (JS/CSS)"""
    # Determine MIME type based on extension
    media_type = "application/octet-stream"
    if path.endswith(".css"):
        media_type = "text/css"
    elif path.endswith(".js"):
        media_type = "application/javascript"
    elif path.endswith(".svg"):
        media_type = "image/svg+xml"
    
    return serve_static(os.path.join(config.settings.static_dir, "assets"), path, media_type)

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
    logger.info(f"Starting NVR on port {config.settings.web_port}...")
    logger.info(f"Recordings: {os.path.abspath(config.settings.record_dir)}")
    logger.info(f"Static: {config.settings.static_dir}")
    uvicorn.run(app, host="0.0.0.0", port=config.settings.web_port)