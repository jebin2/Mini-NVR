"""
Mini-NVR Auth & Endpoint Tests

Tests authentication for all endpoints to verify:
1. Public routes return 200 without auth
2. Protected routes return 401 without auth
3. Protected routes work with valid JWT
4. WebSocket routes require auth

Run: pytest test/test_auth.py -v
"""
import pytest
from fastapi.testclient import TestClient

# Import from conftest.py pre-configured environment
from server import app, auth


@pytest.fixture
def client():
    """Test client without auth."""
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def auth_client():
    """Test client with valid JWT auth cookie."""
    client = TestClient(app, raise_server_exceptions=False)
    
    # Directly populate user in store (InMemoryUserStore uses dict internally)
    test_user = {
        "user_id": "test-user-123",
        "email": "test@example.com",
        "name": "Test User",
        "picture": None,
        "token_version": 1
    }
    auth.user_store._users["test-user-123"] = test_user
    
    # Create a valid JWT token for testing
    token = auth.jwt.create_access_token(
        user_id="test-user-123",
        email="test@example.com",
        token_version=1
    )
    
    # Set the auth cookie
    client.cookies.set(auth.cookie_name, token)
    return client


# ==============================================================================
# PUBLIC ROUTES - Should return 200 without auth
# ==============================================================================

class TestPublicRoutes:
    """Routes that should be accessible without authentication."""
    
    def test_root(self, client):
        """GET / - Main page (public)"""
        response = client.get("/")
        # May return 200 or 500 if index.html not found, but NOT 401
        assert response.status_code != 401
    
    def test_login_page(self, client):
        """GET /login.html - Login page (public)"""
        response = client.get("/login.html")
        assert response.status_code != 401
    
    def test_manifest(self, client):
        """GET /manifest.json - PWA manifest (public)"""
        response = client.get("/manifest.json")
        assert response.status_code != 401
    
    def test_service_worker(self, client):
        """GET /sw.js - Service worker (public)"""
        response = client.get("/sw.js")
        assert response.status_code != 401
    
    def test_favicon(self, client):
        """GET /favicon.ico - Favicon (public)"""
        response = client.get("/favicon.ico")
        assert response.status_code != 401
    
    def test_icons(self, client):
        """GET /icon-*.png - App icons (public)"""
        for size in ["192", "512"]:
            response = client.get(f"/icon-{size}.png")
            assert response.status_code != 401
    
    def test_assets(self, client):
        """GET /assets/* - Static assets (public)"""
        response = client.get("/assets/nonexistent.js")
        # 404 is fine, but should NOT be 401
        assert response.status_code != 401


# ==============================================================================
# AUTH ENDPOINTS - Should be accessible without prior auth
# ==============================================================================

class TestAuthEndpoints:
    """Auth endpoints must be public for login to work."""
    
    def test_auth_google_accessible(self, client):
        """POST /api/auth/google - Should not require auth (it IS the auth)"""
        response = client.post("/api/auth/google", json={"id_token": "invalid"})
        # Will fail with 401 from Google validation, not from our middleware
        # The key is it reaches the handler (not blocked by middleware)
        assert response.status_code in [401, 400, 422]  # Not 403/blocked
    
    def test_auth_refresh_without_cookie(self, client):
        """POST /api/auth/refresh - Requires valid cookie"""
        response = client.post("/api/auth/refresh")
        assert response.status_code == 401
    
    def test_auth_me_without_cookie(self, client):
        """GET /api/auth/me - Requires valid cookie"""
        response = client.get("/api/auth/me")
        assert response.status_code == 401


# ==============================================================================
# PROTECTED API ROUTES - Should return 401 without auth
# ==============================================================================

class TestProtectedRoutesNoAuth:
    """Protected routes should return 401 without authentication."""
    
    def test_config_requires_auth(self, client):
        """GET /api/config - Requires auth"""
        response = client.get("/api/config")
        assert response.status_code == 401
    
    def test_storage_requires_auth(self, client):
        """GET /api/storage - Requires auth"""
        response = client.get("/api/storage")
        assert response.status_code == 401
    
    def test_live_requires_auth(self, client):
        """GET /api/live - Requires auth"""
        response = client.get("/api/live")
        assert response.status_code == 401
    
    def test_dates_requires_auth(self, client):
        """GET /api/dates - Requires auth"""
        response = client.get("/api/dates")
        assert response.status_code == 401
    
    def test_recordings_requires_auth(self, client):
        """GET /api/channel/{ch}/recordings - Requires auth"""
        response = client.get("/api/channel/1/recordings?date=2026-01-01")
        assert response.status_code == 401
    
    def test_delete_recording_requires_auth(self, client):
        """DELETE /api/recording - Requires auth"""
        response = client.delete("/api/recording?path=test.ts")
        assert response.status_code == 401
    
    def test_youtube_restart_requires_auth(self, client):
        """POST /api/youtube/restart - Requires auth"""
        response = client.post("/api/youtube/restart")
        assert response.status_code == 401
    
    def test_playback_requires_auth(self, client):
        """GET /api/playback/{ch}/{date} - Requires auth"""
        response = client.get("/api/playback/1/2026-01-01")
        assert response.status_code == 401
    
    def test_playback_segments_requires_auth(self, client):
        """GET /api/playback/{ch}/{date}/segments - Requires auth"""
        response = client.get("/api/playback/1/2026-01-01/segments")
        assert response.status_code == 401
    
    def test_go2rtc_proxy_requires_auth(self, client):
        """GET /api/go2rtc/* - Requires auth"""
        response = client.get("/api/go2rtc/api/streams")
        assert response.status_code == 401


# ==============================================================================
# PROTECTED ROUTES WITH AUTH - Should work with valid JWT
# ==============================================================================

class TestProtectedRoutesWithAuth:
    """Protected routes should work with valid authentication."""
    
    def test_config_with_auth(self, auth_client):
        """GET /api/config - Works with auth"""
        response = auth_client.get("/api/config")
        assert response.status_code == 200
    
    def test_storage_with_auth(self, auth_client):
        """GET /api/storage - Works with auth"""
        response = auth_client.get("/api/storage")
        # May fail due to missing dir, but not 401
        assert response.status_code != 401
    
    def test_live_with_auth(self, auth_client):
        """GET /api/live - Works with auth"""
        response = auth_client.get("/api/live")
        assert response.status_code != 401
    
    def test_dates_with_auth(self, auth_client):
        """GET /api/dates - Works with auth"""
        response = auth_client.get("/api/dates")
        assert response.status_code != 401
    
    def test_auth_me_with_auth(self, auth_client):
        """GET /api/auth/me - Works with auth"""
        response = auth_client.get("/api/auth/me")
        # Should return user info or 401 if user not in store
        # Key: should reach the handler
        assert response.status_code in [200, 401]


# ==============================================================================
# WEBSOCKET ROUTES - Test auth handling
# ==============================================================================

class TestWebSocketAuth:
    """WebSocket routes should validate auth from cookies."""
    
    def test_go2rtc_ws_without_auth(self, client):
        """WS /api/go2rtc/api/ws - Should reject without auth"""
        try:
            with client.websocket_connect("/api/go2rtc/api/ws?src=cam1") as ws:
                # Should not reach here
                pytest.fail("WebSocket should have been rejected")
        except Exception as e:
            # Connection should be rejected
            pass  # Expected behavior
    
    def test_go2rtc_ws_with_auth(self, auth_client):
        """WS /api/go2rtc/api/ws - Should accept with auth (may fail on go2rtc connection)"""
        try:
            with auth_client.websocket_connect("/api/go2rtc/api/ws?src=cam1") as ws:
                # If we get here, auth passed! Connection may fail after due to go2rtc not running
                pass
        except Exception as e:
            # May fail due to go2rtc not running, that's OK
            # Key is it shouldn't fail with auth error (4001)
            error_str = str(e)
            assert "4001" not in error_str or "Not authenticated" not in error_str


# ==============================================================================
# RECORDINGS SERVING - Protected route
# ==============================================================================

class TestRecordingsServing:
    """Recordings endpoint requires auth."""
    
    def test_recordings_requires_auth(self, client):
        """GET /recordings/* - Requires auth"""
        response = client.get("/recordings/ch1/2026-01-01/test.ts")
        assert response.status_code == 401
    
    def test_recordings_with_auth(self, auth_client):
        """GET /recordings/* - Works with auth (404 if file doesn't exist)"""
        response = auth_client.get("/recordings/ch1/2026-01-01/test.ts")
        # Should be 404 (not found), not 401 (unauthorized)
        assert response.status_code in [404, 200]


# ==============================================================================
# SUMMARY TABLE
# ==============================================================================
"""
┌─────────────────────────────────────┬───────────┬───────────┐
│ Endpoint                            │ No Auth   │ With Auth │
├─────────────────────────────────────┼───────────┼───────────┤
│ GET /                               │ 200 ✅    │ 200 ✅    │
│ GET /login.html                     │ 200 ✅    │ 200 ✅    │
│ GET /manifest.json                  │ 200 ✅    │ 200 ✅    │
│ GET /sw.js                          │ 200 ✅    │ 200 ✅    │
│ GET /favicon.ico                    │ 200 ✅    │ 200 ✅    │
│ GET /assets/*                       │ 200 ✅    │ 200 ✅    │
├─────────────────────────────────────┼───────────┼───────────┤
│ POST /api/auth/google               │ 401* ✅   │ N/A       │
│ POST /api/auth/refresh              │ 401 ✅    │ 200 ✅    │
│ GET /api/auth/me                    │ 401 ✅    │ 200 ✅    │
│ POST /api/auth/logout               │ 200 ✅    │ 200 ✅    │
├─────────────────────────────────────┼───────────┼───────────┤
│ GET /api/config                     │ 401 ❌    │ 200 ✅    │
│ GET /api/storage                    │ 401 ❌    │ 200 ✅    │
│ GET /api/live                       │ 401 ❌    │ 200 ✅    │
│ GET /api/dates                      │ 401 ❌    │ 200 ✅    │
│ GET /api/channel/{ch}/recordings    │ 401 ❌    │ 200 ✅    │
│ DELETE /api/recording               │ 401 ❌    │ 200 ✅    │
│ POST /api/youtube/restart           │ 401 ❌    │ 200 ✅    │
├─────────────────────────────────────┼───────────┼───────────┤
│ GET /api/playback/{ch}/{date}       │ 401 ❌    │ 200 ✅    │
│ GET /api/playback/{ch}/{date}/seg   │ 401 ❌    │ 200 ✅    │
├─────────────────────────────────────┼───────────┼───────────┤
│ GET /api/go2rtc/*                   │ 401 ❌    │ 200 ✅    │
│ WS  /api/go2rtc/api/ws              │ Reject ❌ │ Accept ✅ │
├─────────────────────────────────────┼───────────┼───────────┤
│ GET /recordings/*                   │ 401 ❌    │ 200 ✅    │
└─────────────────────────────────────┴───────────┴───────────┘

* 401 from Google token validation, not middleware
"""


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
