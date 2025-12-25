"""Rate limiter configuration shared across all routers."""

import hashlib
from typing import Optional
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address


def get_rate_limit_key(request: Request) -> str:
    """
    Get rate limit key from request.
    
    Uses API key if available, otherwise falls back to IP address.
    API keys are hashed to avoid storing raw secrets.
    """
    api_key = request.headers.get("X-API-Key")
    authz = request.headers.get("Authorization")

    bearer_token: Optional[str] = None
    if authz and authz.lower().startswith("bearer "):
        bearer_token = authz.split(" ", 1)[1].strip() or None

    token = api_key or bearer_token
    if token:
        # Avoid using raw secrets as limiter keys.
        return "key:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
    return get_remote_address(request)


limiter = Limiter(key_func=get_rate_limit_key)
