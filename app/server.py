import os
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from starlette.middleware.sessions import SessionMiddleware
from api.routes import router as api_router
from api.auth import router as auth_router
from core import config
from core.logger import setup_logger

logger = setup_logger("server")

from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
from core.security import limiter

app = FastAPI(title="NVR UI")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(SessionMiddleware, secret_key=config.SECRET_KEY)

# Mount API
app.include_router(auth_router, prefix="/api")
app.include_router(api_router, prefix="/api")

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
        
    return FileResponse(abs_path, media_type=media_type)

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