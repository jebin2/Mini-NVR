from fastapi import Request, HTTPException, status, Depends
from core.security import is_session_valid, get_user_by_token

def check_csrf(request: Request):
    if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
        csrf_cookie = request.cookies.get("csrf_token")
        csrf_header = request.headers.get("X-CSRF-Token")
        
        if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF Token Mismatch"
            )

def get_current_user(request: Request, csrf_check: None = Depends(check_csrf)):
    user = request.session.get("user")
    token = request.session.get("token")
    
    
    # Check for query param token (fallback for HLS/iframes)
    if not user or not token:
        q_token = request.query_params.get("token")
        if q_token:
            user = get_user_by_token(q_token)
            if user:
                 return user
    
    if not user or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated"
        )
        
    # Server-side validation
    if not is_session_valid(user, token):
        # Invalidated session (e.g. forced logout)
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or invalid"
        )
        
    return user
