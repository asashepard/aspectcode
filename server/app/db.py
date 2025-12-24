"""
Database access layer for alpha signup and token management.
Uses asyncpg for async Postgres access.
"""

import hashlib
import secrets
import uuid
from datetime import datetime
from typing import Optional, Any
from contextlib import asynccontextmanager

# asyncpg is optional - only needed when DATABASE_URL is configured
try:
    import asyncpg  # pyright: ignore[reportMissingImports]
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None  # type: ignore
    ASYNCPG_AVAILABLE = False

from .settings import settings, DATABASE_URL


# Connection pool (initialized on startup)
_pool: Any = None


async def init_pool() -> None:
    """Initialize the database connection pool. Call during app startup."""
    global _pool
    if DATABASE_URL:
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError(
                "asyncpg is required for database access. Install with: pip install asyncpg"
            )
        _pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=2,
            max_size=10,
        )


async def close_pool() -> None:
    """Close the database connection pool. Call during app shutdown."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_connection():
    """Get a database connection from the pool."""
    if _pool is None:
        raise RuntimeError("Database pool not initialized. Call init_pool() first.")
    async with _pool.acquire() as conn:
        yield conn


def hash_token(raw_token: str) -> str:
    """Hash a raw API token using SHA-256."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def generate_api_key(prefix: str = "") -> tuple[str, str]:
    """
    Generate a new API key with an optional prefix.
    
    Prefixes help humans distinguish token types at a glance:
    - "ac_alpha_" for alpha/free tier tokens
    - "ac_live_" for production/paid tokens
    - "ac_test_" for development/testing
    
    Returns (raw_token, token_hash).
    """
    random_part = secrets.token_urlsafe(32)
    raw_token = f"{prefix}{random_part}" if prefix else random_part
    token_hash = hash_token(raw_token)
    return raw_token, token_hash


# --- Alpha User Operations ---


async def get_alpha_user_by_email(email: str) -> Optional[dict]:
    """
    Get an alpha user by email.
    Returns dict with id, email, created_at or None if not found.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT id, email, created_at
            FROM alpha_users
            WHERE email = $1
            """,
            email.lower(),
        )
        if row:
            return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}
        return None


async def create_alpha_user(email: str) -> dict:
    """
    Create a new alpha user.
    Returns dict with id, email, created_at.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO alpha_users (email, created_at, updated_at)
            VALUES ($1, NOW(), NOW())
            RETURNING id, email, created_at
            """,
            email.lower(),
        )
        return {"id": row["id"], "email": row["email"], "created_at": row["created_at"]}


async def get_or_create_alpha_user(email: str) -> dict:
    """
    Get an existing alpha user or create a new one.
    Returns dict with id, email, created_at.
    """
    user = await get_alpha_user_by_email(email)
    if user:
        return user
    return await create_alpha_user(email)


# --- API Token Operations ---

# Token prefix for Aspect Code API keys
TOKEN_PREFIX = "ac_"


async def create_api_token(
    alpha_user_id: str,
    name: str = "default",
    prefix: str = TOKEN_PREFIX,
) -> tuple[str, dict]:
    """
    Create a new API token for an alpha user.

    Returns (raw_token, token_row_dict).
    The raw token is only available at creation time; only the hash is stored.
    """
    raw_token, token_hash = generate_api_key(prefix=prefix)
    token_row = await create_api_token_with_hash(alpha_user_id=alpha_user_id, token_hash=token_hash, name=name)
    return raw_token, token_row


async def create_api_token_with_hash(
    alpha_user_id: str,
    token_hash: str,
    name: str = "default",
) -> dict:
    """Create a new API token using a pre-computed token hash (admin/internal use)."""
    token_id = str(uuid.uuid4())
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO api_tokens (id, alpha_user_id, token_hash, name, created_at, updated_at)
            VALUES ($1, $2, $3, $4, NOW(), NOW())
            RETURNING id, name, created_at, updated_at
            """,
            token_id,
            alpha_user_id,
            token_hash,
            name,
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


async def get_alpha_user_by_token_hash(token_hash: str) -> Optional[dict]:
    """
    Look up an alpha user by their API token hash.
    Returns dict with user info and token info, or None if not found.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.email, t.id as token_id, t.name as token_name
            FROM api_tokens t
            JOIN alpha_users u ON t.alpha_user_id = u.id
            WHERE t.token_hash = $1
              AND t.revoked_at IS NULL
            """,
            token_hash,
        )
        if row:
            return {
                "user_id": row["id"],
                "email": row["email"],
                "token_id": row["token_id"],
                "token_name": row["token_name"],
            }
        return None


async def get_user_by_token_hash(token_hash: str) -> Optional[dict]:
    """
    Look up a paid user by their API token hash.
    Returns dict with user info and token info, or None if not found.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.id, u.email, t.id as token_id, t.name as token_name
            FROM api_tokens t
            JOIN users u ON t.user_id = u.id
            WHERE t.token_hash = $1
              AND t.revoked_at IS NULL
            """,
            token_hash,
        )
        if row:
            return {
                "user_id": row["id"],
                "email": row["email"],
                "token_id": row["token_id"],
                "token_name": row["token_name"],
            }
        return None


async def touch_token_last_used(token_hash: str, min_interval_seconds: int = 60) -> bool:
    """Update api_tokens.last_used_at (and updated_at) if it is stale.

    Returns True if a row was updated, False otherwise.
    Intended to be called after a token has already been validated.
    """
    if min_interval_seconds <= 0:
        min_interval_seconds = 0

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET last_used_at = NOW(), updated_at = NOW()
            WHERE token_hash = $1
              AND revoked_at IS NULL
              AND (
                last_used_at IS NULL
                OR last_used_at < (NOW() - ($2 * INTERVAL '1 second'))
              )
            RETURNING id
            """,
            token_hash,
            int(min_interval_seconds),
        )
        return row is not None


async def revoke_api_token(token_id: str) -> bool:
    """
    Revoke an API token by setting revoked_at.
    Idempotent: returns True if token exists (even if already revoked).
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
            WHERE id = $1
            RETURNING id
            """,
            token_id,
        )
        return row is not None


async def revoke_api_token_by_hash(token_hash: str) -> bool:
    """Idempotently revoke a token by its hash. Returns True if token exists."""
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
            WHERE token_hash = $1
            RETURNING id
            """,
            token_hash,
        )
        return row is not None


async def is_token_revoked(token_hash: str) -> bool:
    """
    Check if a token exists but has been revoked.
    Returns True if token exists and is revoked, False otherwise.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            SELECT revoked_at
            FROM api_tokens
            WHERE token_hash = $1
            """,
            token_hash,
        )
        # Token exists and has a revoked_at timestamp
        return row is not None and row["revoked_at"] is not None


async def get_tokens_for_alpha_user(alpha_user_id: str, include_revoked: bool = False) -> list[dict]:
    """Get tokens for an alpha user (optionally including revoked tokens)."""
    async with get_connection() as conn:
        where_clause = "alpha_user_id = $1" if include_revoked else "alpha_user_id = $1 AND revoked_at IS NULL"
        rows = await conn.fetch(
            f"""
            SELECT id, name, created_at, last_used_at, revoked_at
            FROM api_tokens
            WHERE {where_clause}
            ORDER BY created_at DESC
            """,
            alpha_user_id,
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]


# --- Admin Token Management ---


async def create_api_token_for_admin(
    alpha_user_id: str | None = None,
    user_id: str | None = None,
    name: str = "default",
) -> tuple[str, dict]:
    """
    Create an API token for admin purposes.
    
    Accepts either alpha_user_id, user_id, or neither.
    Returns (raw_token, token_row_dict).
    """
    raw_token, token_hash = generate_api_key(prefix="ac_")  # Unpack tuple correctly
    token_id = str(uuid.uuid4())
    
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO api_tokens (
                id, alpha_user_id, user_id, token_hash, name, 
                created_at, updated_at
            )
            VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
            RETURNING id, created_at
            """,
            token_id,
            alpha_user_id,
            user_id,
            token_hash,
            name,
        )
        
        return raw_token, {
            "id": row["id"],
            "created_at": row["created_at"],
        }


async def revoke_api_token_by_id(token_id: str) -> dict | None:
    """
    Revoke a token by its database ID.
    
    Returns token info with revoked_at, or None if token not found.
    Idempotent - if already revoked, returns existing revoked_at.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET revoked_at = COALESCE(revoked_at, NOW()), updated_at = NOW()
            WHERE id = $1
            RETURNING id, revoked_at
            """,
            token_id,
        )
        
        if row is None:
            return None
        
        return {
            "id": row["id"],
            "revoked_at": row["revoked_at"],
        }


async def list_api_tokens(
    alpha_user_id: str | None = None,
    user_id: str | None = None,
    include_revoked: bool = True,
) -> list[dict]:
    """
    List API tokens with optional filtering.
    
    Filters:
    - alpha_user_id: Filter by alpha user
    - user_id: Filter by paid user
    - include_revoked: Include revoked tokens (default: True)
    
    Returns list of token metadata (never includes raw token or hash).
    """
    async with get_connection() as conn:
        conditions = []
        params = []
        param_idx = 1
        
        if alpha_user_id is not None:
            conditions.append(f'alpha_user_id = ${param_idx}')
            params.append(alpha_user_id)
            param_idx += 1
        
        if user_id is not None:
            conditions.append(f'user_id = ${param_idx}')
            params.append(user_id)
            param_idx += 1
        
        if not include_revoked:
            conditions.append('revoked_at IS NULL')
        
        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        
        rows = await conn.fetch(
            f"""
            SELECT 
                id, name, alpha_user_id, user_id,
                created_at, last_used_at, revoked_at
            FROM api_tokens
            {where_clause}
            ORDER BY created_at DESC
            """,
            *params,
        )
        
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "alpha_user_id": row["alpha_user_id"],
                "user_id": row["user_id"],
                "created_at": row["created_at"],
                "last_used_at": row["last_used_at"],
                "revoked_at": row["revoked_at"],
            }
            for row in rows
        ]
