"""
Aspect Code Server Authentication

API key-based authentication with support for:
- Environment-based keys (for admin/service accounts)
- Database-backed tokens (for alpha and production users)
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from typing import Optional
from packaging import version

from .settings import settings, DATABASE_URL
from . import db


# Security headers
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
client_version_header = APIKeyHeader(name="X-AspectCode-Client-Version", auto_error=False)


class UserContext(BaseModel):
    """
    Authenticated user context.
    """
    api_key: str
    client_version: Optional[str] = None
    
    # DB-backed auth fields
    user_id: Optional[str] = None
    email: Optional[str] = None
    token_id: Optional[str] = None
    is_alpha: bool = False  # True if authenticated via alpha_users
    
    # Future fields for paid tiers:
    # plan: str = "free"
    # rate_limit_override: Optional[int] = None


async def _lookup_db_token(api_key: str) -> Optional[dict]:
    """
    Look up an API key in the database.
    
    Returns user info dict if found, None otherwise.
    Respects the mode setting (alpha/prod/both).
    """
    if not DATABASE_URL:
        return None
    
    try:
        token_hash = db.hash_token(api_key)
        
        # Try alpha users first in alpha or both mode
        if settings.mode in ("alpha", "both"):
            result = await db.get_alpha_user_by_token_hash(token_hash)
            if result:
                return {
                    "user_id": result["user_id"],
                    "email": result["email"],
                    "token_id": result["token_id"],
                    "is_alpha": True,
                }
        
        # Try paid users in prod or both mode
        if settings.mode in ("prod", "both"):
            result = await db.get_user_by_token_hash(token_hash)
            if result:
                return {
                    "user_id": result["user_id"],
                    "email": result["email"],
                    "token_id": result["token_id"],
                    "is_alpha": False,
                }
    except RuntimeError as e:
        # Database pool not initialized - fall through to env-based keys
        print(f"[auth] Database lookup skipped (pool not ready): {e}")
        return None
    except Exception as e:
        # Log but don't crash - fall through to env-based keys
        print(f"[auth] Database lookup error: {e}")
        return None
    
    return None


async def get_current_user(
    api_key: Optional[str] = Depends(api_key_header),
    client_version: Optional[str] = Depends(client_version_header),
) -> UserContext:
    """
    Validate API key and return user context.
    
    Authentication order:
    1. Check settings.api_keys for admin/service keys
    2. If not found, query database for token
    """
    
    # Check if API key is provided
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Set X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    
    # First, check environment-based admin keys
    if api_key in settings.api_keys:
        _check_client_version(client_version)
        return UserContext(api_key=api_key, client_version=client_version)
    
    # Try database lookup
    db_user = await _lookup_db_token(api_key)
    if db_user:
        _check_client_version(client_version)
        return UserContext(
            api_key=api_key,
            client_version=client_version,
            user_id=db_user["user_id"],
            email=db_user["email"],
            token_id=db_user["token_id"],
            is_alpha=db_user["is_alpha"],
        )
    
    # Check if the token exists but was revoked
    try:
        if DATABASE_URL:
            token_hash = db.hash_token(api_key)
            is_revoked = await db.is_token_revoked(token_hash)
            if is_revoked:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="API key has been revoked. Please contact support for a new key.",
                )
    except HTTPException:
        raise  # Re-raise the 403
    except Exception as e:
        print(f"[auth] Error checking revoked status: {e}")
        # Fall through to generic invalid key error
    
    # No valid authentication found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid API key.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def _check_client_version(client_version: Optional[str]) -> None:
    """Enforce minimum client version if configured."""
    if settings.min_client_version and client_version:
        try:
            if version.parse(client_version) < version.parse(settings.min_client_version):
                raise HTTPException(
                    status_code=status.HTTP_426_UPGRADE_REQUIRED,
                    detail=f"Client version {client_version} is too old. Minimum required: {settings.min_client_version}. Please update your Aspect Code extension.",
                )
        except version.InvalidVersion:
            # Invalid version string - allow through but log
            pass
