"""
Tests for admin API token management endpoints.
"""

import pytest
import os
from datetime import datetime
from unittest.mock import patch
from fastapi.testclient import TestClient


class TestAdminEndpoints:
    """Test admin API token management endpoints."""
    
    @pytest.fixture
    def admin_client(self):
        """Client with admin API key configured."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": "admin-key-1"}, clear=False):
            from app.settings import Settings
            settings = Settings()
            
            with patch("app.main.settings", settings):
                with patch("app.auth.settings", settings):
                    from app.main import app
                    yield TestClient(app)
    
    @pytest.fixture
    def non_admin_client(self):
        """Client that will simulate a non-admin DB token."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": "admin-key-1"}, clear=False):
            from app.settings import Settings
            settings = Settings()
            
            with patch("app.main.settings", settings):
                with patch("app.auth.settings", settings):
                    from app.main import app
                    yield TestClient(app)

    # --- Access Control Tests ---
    
    def test_admin_endpoint_requires_auth(self, admin_client):
        """Admin endpoints should require authentication."""
        response = admin_client.get("/admin/api-tokens")
        assert response.status_code == 401
        assert "Missing API key" in response.json()["detail"]
    
    def test_admin_endpoint_rejects_non_admin_token(self, non_admin_client):
        """Admin endpoints should reject non-admin tokens with 403."""
        # Mock the DB lookup to return a non-admin user (as a dict)
        from app import auth as auth_module
        from app import db as db_module
        
        async def mock_lookup(token):
            # _lookup_db_token returns a dict, not UserContext
            return {
                "user_id": "user-1",
                "email": "user@example.com",
                "token_id": "token-1",
                "is_alpha": True,
            }
        
        async def mock_is_revoked(token_hash):
            return False
        
        with patch.object(auth_module, "_lookup_db_token", side_effect=mock_lookup):
            with patch.object(db_module, "is_token_revoked", side_effect=mock_is_revoked):
                response = non_admin_client.get(
                    "/admin/api-tokens",
                    headers={"X-API-Key": "user-db-token"}
                )
                assert response.status_code == 403
                assert "Admin access required" in response.json()["detail"]
    
    def test_admin_endpoint_accepts_admin_key(self, admin_client):
        """Admin endpoints should accept admin API keys."""
        from app import db as db_module
        
        # Mock the list function
        async def mock_list(**kwargs):
            return []
        
        with patch.object(db_module, "list_api_tokens", side_effect=mock_list):
            response = admin_client.get(
                "/admin/api-tokens",
                headers={"X-API-Key": "admin-key-1"}
            )
            assert response.status_code == 200

    # --- Create Token Tests ---
    
    def test_create_token_returns_raw_token(self, admin_client):
        """POST /admin/api-tokens should return raw token once."""
        from app import db as db_module
        
        created_at = datetime.now()
        async def mock_create(**kwargs):
            return ("ac_rawtoken123", {"id": "token-id-1", "created_at": created_at})
        
        with patch.object(db_module, "create_api_token_for_admin", side_effect=mock_create):
            response = admin_client.post(
                "/admin/api-tokens",
                json={"alpha_user_id": "alpha-1", "name": "test-token"},
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["token"] == "ac_rawtoken123"
            assert data["token_id"] == "token-id-1"
            assert "created_at" in data
    
    def test_create_token_rejects_both_user_types(self, admin_client):
        """POST /admin/api-tokens should reject both alpha_user_id and user_id."""
        response = admin_client.post(
            "/admin/api-tokens",
            json={"alpha_user_id": "alpha-1", "user_id": "user-1"},
            headers={"X-API-Key": "admin-key-1"}
        )
        
        assert response.status_code == 400
        assert "at most one" in response.json()["detail"].lower()
    
    def test_create_token_with_user_id(self, admin_client):
        """POST /admin/api-tokens should work with user_id."""
        from app import db as db_module
        
        created_at = datetime.now()
        async def mock_create(**kwargs):
            assert kwargs.get("user_id") == "user-1"
            assert kwargs.get("alpha_user_id") is None
            return ("ac_usertoken", {"id": "token-id-2", "created_at": created_at})
        
        with patch.object(db_module, "create_api_token_for_admin", side_effect=mock_create):
            response = admin_client.post(
                "/admin/api-tokens",
                json={"user_id": "user-1"},
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200
            assert response.json()["token"] == "ac_usertoken"
    
    def test_create_token_without_user_ids(self, admin_client):
        """POST /admin/api-tokens should work without any user ID."""
        from app import db as db_module
        
        created_at = datetime.now()
        async def mock_create(**kwargs):
            assert kwargs.get("user_id") is None
            assert kwargs.get("alpha_user_id") is None
            return ("ac_nouser", {"id": "token-id-3", "created_at": created_at})
        
        with patch.object(db_module, "create_api_token_for_admin", side_effect=mock_create):
            response = admin_client.post(
                "/admin/api-tokens",
                json={},
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200

    # --- Revoke Token Tests ---
    
    def test_revoke_token_success(self, admin_client):
        """POST /admin/api-tokens/{id}/revoke should revoke token."""
        from app import db as db_module
        
        revoked_at = datetime.now()
        async def mock_revoke(token_id):
            assert token_id == "token-to-revoke"
            return {"id": token_id, "revoked_at": revoked_at}
        
        with patch.object(db_module, "revoke_api_token_by_id", side_effect=mock_revoke):
            response = admin_client.post(
                "/admin/api-tokens/token-to-revoke/revoke",
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["token_id"] == "token-to-revoke"
            assert "revoked_at" in data
    
    def test_revoke_token_not_found(self, admin_client):
        """POST /admin/api-tokens/{id}/revoke should return 404 for unknown token."""
        from app import db as db_module
        
        async def mock_revoke(token_id):
            return None
        
        with patch.object(db_module, "revoke_api_token_by_id", side_effect=mock_revoke):
            response = admin_client.post(
                "/admin/api-tokens/nonexistent/revoke",
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 404
            assert "not found" in response.json()["detail"].lower()

    # --- List Tokens Tests ---
    
    def test_list_tokens_returns_metadata(self, admin_client):
        """GET /admin/api-tokens should return token metadata."""
        from app import db as db_module
        
        now = datetime.now()
        async def mock_list(**kwargs):
            return [
                {
                    "id": "token-1",
                    "name": "prod-token",
                    "alpha_user_id": "alpha-1",
                    "user_id": None,
                    "created_at": now,
                    "last_used_at": now,
                    "revoked_at": None,
                },
                {
                    "id": "token-2",
                    "name": "revoked-token",
                    "alpha_user_id": None,
                    "user_id": "user-1",
                    "created_at": now,
                    "last_used_at": None,
                    "revoked_at": now,
                },
            ]
        
        with patch.object(db_module, "list_api_tokens", side_effect=mock_list):
            response = admin_client.get(
                "/admin/api-tokens",
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert "tokens" in data
            assert len(data["tokens"]) == 2
            
            # Check first token
            t1 = data["tokens"][0]
            assert t1["id"] == "token-1"
            assert t1["name"] == "prod-token"
            assert t1["alpha_user_id"] == "alpha-1"
            assert t1["revoked_at"] is None
            
            # Check second token (revoked)
            t2 = data["tokens"][1]
            assert t2["id"] == "token-2"
            assert t2["revoked_at"] is not None
    
    def test_list_tokens_never_returns_raw_token(self, admin_client):
        """GET /admin/api-tokens should never return raw tokens."""
        from app import db as db_module
        
        async def mock_list(**kwargs):
            return [
                {
                    "id": "token-1",
                    "name": "test",
                    "alpha_user_id": None,
                    "user_id": None,
                    "created_at": datetime.now(),
                    "last_used_at": None,
                    "revoked_at": None,
                },
            ]
        
        with patch.object(db_module, "list_api_tokens", side_effect=mock_list):
            response = admin_client.get(
                "/admin/api-tokens",
                headers={"X-API-Key": "admin-key-1"}
            )
            
            data = response.json()
            # Ensure no field contains a raw token
            for token in data["tokens"]:
                assert "token" not in token
                assert "tokenHash" not in token
                assert "token_hash" not in token
    
    def test_list_tokens_with_filters(self, admin_client):
        """GET /admin/api-tokens should pass filters to DB."""
        from app import db as db_module
        
        async def mock_list(alpha_user_id=None, user_id=None, include_revoked=True):
            assert alpha_user_id == "alpha-filter"
            assert include_revoked is False
            return []
        
        with patch.object(db_module, "list_api_tokens", side_effect=mock_list):
            response = admin_client.get(
                "/admin/api-tokens",
                params={"alpha_user_id": "alpha-filter", "include_revoked": False},
                headers={"X-API-Key": "admin-key-1"}
            )
            
            assert response.status_code == 200


class TestTokenCreationIntegration:
    """Integration tests for created tokens (mocked DB)."""
    
    @pytest.fixture
    def admin_client(self):
        """Client with admin API key configured."""
        with patch.dict(os.environ, {"ASPECT_CODE_API_KEYS_RAW": "admin-key-1"}, clear=False):
            from app.settings import Settings
            settings = Settings()
            
            with patch("app.main.settings", settings):
                with patch("app.auth.settings", settings):
                    from app.main import app
                    yield TestClient(app)
    
    def test_created_token_works_for_auth(self, admin_client):
        """A newly created token should work for authentication."""
        from app import db as db_module
        from app import auth as auth_module
        from app.auth import UserContext
        
        created_at = datetime.now()
        created_token = None
        
        async def mock_create(**kwargs):
            nonlocal created_token
            created_token = "ac_newtoken123"
            return (created_token, {"id": "new-token-id", "created_at": created_at})
        
        # Create the token
        with patch.object(db_module, "create_api_token_for_admin", side_effect=mock_create):
            response = admin_client.post(
                "/admin/api-tokens",
                json={"name": "test"},
                headers={"X-API-Key": "admin-key-1"}
            )
            raw_token = response.json()["token"]
        
        # Now try to use the token (mock _lookup_db_token to return a dict)
        async def mock_lookup(token):
            if token == raw_token:
                return {
                    "user_id": "new-token-id",
                    "email": None,
                    "token_id": "new-token-id",
                    "is_alpha": True,
                }
            return None
        
        async def mock_is_revoked(token_hash):
            return False
        
        with patch.object(auth_module, "_lookup_db_token", side_effect=mock_lookup):
            with patch.object(db_module, "is_token_revoked", side_effect=mock_is_revoked):
                # The token should authenticate (may fail on path validation, but not 401)
                response = admin_client.post(
                    "/validate",
                    json={"paths": ["/tmp/test.py"]},
                    headers={"X-API-Key": raw_token}
                )
                assert response.status_code != 401
    
    def test_revoked_token_rejected(self, admin_client):
        """A revoked token should receive 403."""
        from app import db as db_module
        from app import auth as auth_module
        
        revoked_token = "ac_revokedtoken"
        
        # When a token is revoked, _lookup_db_token returns None
        # (the underlying DB queries filter out revoked tokens)
        async def mock_lookup(token):
            return None  # Token not found (because it's revoked)
        
        # But is_token_revoked returns True (token exists but is revoked)
        async def mock_is_revoked(token_hash):
            return True
        
        # Need to mock DATABASE_URL to enable the revocation check path
        with patch.object(auth_module, "DATABASE_URL", "mock://database"):
            with patch.object(auth_module, "_lookup_db_token", side_effect=mock_lookup):
                with patch.object(db_module, "is_token_revoked", side_effect=mock_is_revoked):
                    response = admin_client.post(
                        "/validate",
                        json={"paths": ["/tmp/test.py"]},
                        headers={"X-API-Key": revoked_token}
                    )
                    assert response.status_code == 403
                    assert "revoked" in response.json()["detail"].lower()
