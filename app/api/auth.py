from fastapi import APIRouter, Request, HTTPException, status, Response
from pydantic import BaseModel
from core import config
from core.security import limiter, add_session, create_session_token, remove_session

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

@router.post("/login")
@limiter.limit("5/minute")
def login(creds: LoginRequest, request: Request, response: Response):
    if creds.username in config.USERS and config.USERS[creds.username] == creds.password:
        # Create server-side session token
        token = create_session_token()
        add_session(creds.username, token)
        
        request.session["user"] = creds.username
        request.session["token"] = token
        
        # Set a separate CSRF cookie for the frontend to read
        # It doesn't need to be secret, just unique and match the header in future requests.
        # We can reuse the session token or generate a new one. 
        # For Double Submit, the cookie is readable by JS.
        response.set_cookie(
            key="csrf_token",
            value=token,
            httponly=False, # Must be false so JS can read it to put in header
            samesite="lax",
            secure=False # Set to True if using HTTPS
        )
        
        return {"message": "Logged in"}
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials"
    )

@router.post("/logout")
def logout(request: Request, response: Response):
    user = request.session.get("user")
    token = request.session.get("token")
    if user and token:
        remove_session(user, token)
        
    request.session.clear()
    response.delete_cookie("csrf_token")
    return {"message": "Logged out"}

@router.get("/me")
def me(request: Request):
    user = request.session.get("user")
    # Note: Full validation happens in deps.get_current_user for protected routes.
    # checking here for UI convenience
    if user:
         return {"user": user}
    return {"user": None}
