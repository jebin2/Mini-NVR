from fastapi import Request, HTTPException, status, Depends

# No longer needed: check_csrf, is_session_valid - handled by GoogleAuthMiddleware

def get_current_user(request: Request):
    """
    Dependency to get the current authenticated user.
    New Flow: Rely on GoogleAuthMiddleware to have populated request.state.user
    """
    if hasattr(request.state, "user") and request.state.user:
        return request.state.user

    # Middleware should have handled 401 for protected routes?
    # If not, or if this is used in a route not covered by middleware whitelist logic but still needs user:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated"
    )
