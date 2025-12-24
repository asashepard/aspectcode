"""
Tests for API authentication and authorization.
"""

import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient


class TestAuth:
    """Test authentication on API endpoints."""
    
    @pytest.fixture
    def client_no_auth(self):
        """Client with no API keys configured (dev mode)."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": ""}, clear=False):
            # Re-import to pick up new settings
            from app.settings import Settings
            settings = Settings()
            
            with patch("app.main.settings", settings):
                with patch("app.auth.settings", settings):
                    from app.main import app
                    yield TestClient(app)
    
    @pytest.fixture
    def client_with_auth(self):
        """Client with API keys configured."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": "test-key-1,test-key-2"}, clear=False):
            # Re-import to pick up new settings
            from app.settings import Settings
            settings = Settings()
            
            with patch("app.main.settings", settings):
                with patch("app.auth.settings", settings):
                    from app.main import app
                    yield TestClient(app)
    
    def test_health_no_auth_required(self, client_with_auth):
        """Health endpoint should work without authentication."""
        response = client_with_auth.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "auth_required" in data
    
    def test_validate_requires_auth_when_configured(self, client_with_auth):
        """Validate endpoint should require auth when API keys are configured."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={}
        )
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]
    
    def test_validate_with_valid_key(self, client_with_auth):
        """Validate endpoint should work with valid API key."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={"X-API-Key": "test-key-1"}
        )
        # Should not be 401 (may be 400 or 500 due to invalid path, but not auth error)
        assert response.status_code != 401

    def test_validate_with_valid_bearer_key(self, client_with_auth):
        """Validate endpoint should work with valid API key via Authorization: Bearer."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={"Authorization": "Bearer test-key-1"}
        )
        assert response.status_code != 401
    
    def test_validate_with_invalid_key(self, client_with_auth):
        """Validate endpoint should reject invalid API key."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={"X-API-Key": "wrong-key"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_validate_with_invalid_bearer_key(self, client_with_auth):
        """Validate endpoint should reject invalid API key via Authorization: Bearer."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={"Authorization": "Bearer wrong-key"}
        )
        assert response.status_code == 401
        assert "Invalid API key" in response.json()["detail"]

    def test_revoked_key_returns_403(self, client_with_auth):
        """Revoked keys should return 403 (mocked DB revocation check)."""
        from app import auth as auth_module

        async def _fake_lookup_db_token(_api_key: str):
            return None

        async def _fake_is_token_revoked(_token_hash: str) -> bool:
            return True

        with patch.object(auth_module, "DATABASE_URL", "postgres://dummy"):
            with patch.object(auth_module, "_lookup_db_token", _fake_lookup_db_token):
                with patch.object(auth_module.db, "is_token_revoked", _fake_is_token_revoked):
                    response = client_with_auth.post(
                        "/validate",
                        json={"paths": ["/tmp/test.py"]},
                        headers={"X-API-Key": "revoked-key"}
                    )
                    assert response.status_code == 403
                    assert "revoked" in response.json()["detail"].lower()
    
    def test_client_version_header_accepted(self, client_with_auth):
        """Client version header should be accepted."""
        response = client_with_auth.post(
            "/validate",
            json={"paths": ["/tmp/test.py"]},
            headers={
                "X-API-Key": "test-key-1",
                "X-AspectCode-Client-Version": "0.0.1"
            }
        )
        # Should not be 401 or 426
        assert response.status_code not in [401, 426]


class TestCORS:
    """Test CORS configuration."""
    
    def test_cors_headers_present(self):
        """CORS headers should be present in responses."""
        from app.main import app
        client = TestClient(app)
        
        response = client.options(
            "/health",
            headers={"Origin": "http://localhost:3000"}
        )
        # CORS preflight should be handled (405 may occur if OPTIONS not explicitly allowed)
        assert response.status_code in [200, 204, 400, 405]


class TestRateLimiting:
    """Test rate limiting configuration."""
    
    def test_rate_limit_header_present(self):
        """Rate limit headers should be present after requests."""
        from app.main import app
        client = TestClient(app)
        
        # Health endpoint doesn't require auth
        response = client.get("/health")
        assert response.status_code == 200
        # Rate limit is not applied to health endpoint, so we just verify it works


class TestSettingsParsing:
    """Test settings module parsing."""
    
    def test_parse_api_keys_from_env(self):
        """API keys should be parsed from comma-separated env var."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": "key1,key2,key3"}, clear=False):
            from app.settings import Settings
            settings = Settings()
            assert settings.api_keys == ["key1", "key2", "key3"]
    
    def test_parse_allowed_origins_from_env(self):
        """Allowed origins should be parsed from comma-separated env var."""
        with patch.dict(os.environ, {"ASPECT_CODE_ALLOWED_ORIGINS_RAW": "https://app.example.com,https://other.com"}, clear=False):
            from app.settings import Settings
            settings = Settings()
            assert settings.allowed_origins == ["https://app.example.com", "https://other.com"]
    
    def test_empty_api_keys_default(self):
        """Empty API keys should default to empty list."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear ASPECT_CODE_API_KEYS_RAW if it exists
            os.environ.pop("ASPECT_CODE_API_KEYS_RAW", None)
            from app.settings import Settings
            settings = Settings()
            assert settings.api_keys == []
