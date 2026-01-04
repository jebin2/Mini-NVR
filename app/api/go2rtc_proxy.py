"""
Go2rtc Proxy Router

Proxies requests to go2rtc through Mini-NVR's authentication layer.
All routes require an authenticated session.

Supports:
- HTTP API endpoints
- WebSocket connections (for WebRTC signaling)
"""
import asyncio
import httpx
import websockets
from fastapi import APIRouter, Request, Response, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from core import config
from core.logger import setup_logger

logger = setup_logger("go2rtc_proxy")

# HTTP routes - auth handled by GoogleAuthMiddleware
router = APIRouter()

# WebSocket router - auth handled by GoogleAuthMiddleware (user in scope)
ws_router = APIRouter()

GO2RTC_HTTP = f"http://127.0.0.1:{config.settings.go2rtc_api_port}"
GO2RTC_WS = f"ws://127.0.0.1:{config.settings.go2rtc_api_port}"

# Reusable async HTTP client
_client = None

def get_client():
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=30.0)
    return _client


@ws_router.websocket("/api/ws")
async def proxy_websocket(websocket: WebSocket):
    """
    Proxy WebSocket connections for WebRTC signaling.
    Auth is validated by GoogleAuthMiddleware - user available in scope.
    """
    # Get user from middleware (set in scope by GoogleAuthMiddleware)
    user = websocket.scope.get("user")
    payload = websocket.scope.get("auth_payload")
    
    if not user:
        logger.warning("WebSocket rejected: Not authenticated (no user in scope)")
        await websocket.close(code=4001, reason="Not authenticated")
        return
    
    # Log authenticated user
    email = payload.email if payload else "unknown"
    logger.debug(f"WebSocket authenticated for user: {email}")
    
    await websocket.accept()
    
    # Get query params for go2rtc
    query_string = str(websocket.query_params) if websocket.query_params else ""
    target_url = f"{GO2RTC_WS}/api/ws"
    if query_string:
        target_url += f"?{query_string}"
    
    try:
        async with websockets.connect(target_url) as go2rtc_ws:
            async def forward_to_go2rtc():
                try:
                    while True:
                        data = await websocket.receive_text()
                        await go2rtc_ws.send(data)
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    logger.debug(f"Client->go2rtc error: {e}")
            
            async def forward_to_client():
                try:
                    async for message in go2rtc_ws:
                        await websocket.send_text(message)
                except Exception as e:
                    logger.debug(f"go2rtc->client error: {e}")
            
            # Run both directions concurrently
            await asyncio.gather(
                forward_to_go2rtc(),
                forward_to_client(),
                return_exceptions=True
            )
    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        try:
            await websocket.close(code=1011, reason="Backend error")
        except:
            pass


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy_go2rtc(path: str, request: Request):
    """
    Proxy HTTP requests to go2rtc using StreamingResponse.
    
    Supports:
    - Static files (stream.html, js, css)
    - API endpoints (/api/streams, /api/frame.jpeg, etc.)
    - WebRTC HTTP signaling (/api/webrtc)
    """
    client = get_client()
    
    # Build target URL
    target_url = f"{GO2RTC_HTTP}/{path}"
    
    # Preserve query string
    if request.query_params:
        target_url += f"?{request.query_params}"
    
    try:
        # Prepare request arguments
        kwargs = {}
        if request.method in ["POST", "PUT"]:
            # For large bodies we should probably stream, but for now just read it 
            # (signaling payloads are small)
            kwargs["content"] = await request.body()
            
        # Forward headers (excluding host/length which httpx handles)
        # Also strip upgrade headers as we handle those separately if needed
        headers = dict(request.headers)
        headers.pop("host", None)
        headers.pop("content-length", None)
        headers.pop("transfer-encoding", None)
        kwargs["headers"] = headers

        # Create upstream request
        req = client.build_request(request.method, target_url, **kwargs)
        
        # Send request and stream response
        r = await client.send(req, stream=True)
        
        # Filter response headers
        # We MUST strip Content-Length and Transfer-Encoding because Starlette/Uvicorn
        # will handle framing for the downstream streaming response.
        # Keeping upstream Content-Length can cause "Too much data" errors if
        # we stream chunks slightly differently or if framing overhead counts.
        excluded_headers = {"content-length", "transfer-encoding", "connection", "keep-alive"}
        response_headers = {
            k: v for k, v in r.headers.items() 
            if k.lower() not in excluded_headers
        }

        return StreamingResponse(
            r.aiter_bytes(),
            status_code=r.status_code,
            media_type=r.headers.get("content-type"),
            headers=response_headers,
            background=None # We could close r here if needed, but client is long-lived
        )
        
    except httpx.ConnectError:
        logger.error("Failed to connect to go2rtc")
        raise HTTPException(status_code=502, detail="go2rtc is not available")
    except httpx.TimeoutException:
        logger.error("Timeout connecting to go2rtc")
        raise HTTPException(status_code=504, detail="go2rtc request timed out")
    except Exception as e:
        logger.error(f"Proxy error: {e}")
        # Only raise if we haven't started streaming yet
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")
