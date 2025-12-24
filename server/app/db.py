"""
Database access layer for alpha signup and token management.
Uses asyncpg for async Postgres access.
"""

import hashlib
import secrets
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
            SELECT id, email, "createdAt"
            FROM "AlphaUser"
            WHERE email = $1
            """,
            email.lower(),
        )
        if row:
            return {"id": row["id"], "email": row["email"], "created_at": row["createdAt"]}
        return None


async def create_alpha_user(email: str) -> dict:
    """
    Create a new alpha user.
    Returns dict with id, email, created_at.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO "AlphaUser" (email, "createdAt", "updatedAt")
            VALUES ($1, NOW(), NOW())
            RETURNING id, email, "createdAt"
            """,
            email.lower(),
        )
        return {"id": row["id"], "email": row["email"], "created_at": row["createdAt"]}


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
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO "ApiToken" ("alphaUserId", "tokenHash", name, "createdAt", "updatedAt")
            VALUES ($1, $2, $3, NOW(), NOW())
            RETURNING id, name, "createdAt", "updatedAt"
            """,
            alpha_user_id,
            token_hash,
            name,
        )
        return {
            "id": row["id"],
            "name": row["name"],
            "created_at": row["createdAt"],
            "updated_at": row["updatedAt"],
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
            FROM "ApiToken" t
            JOIN "AlphaUser" u ON t."alphaUserId" = u.id
            WHERE t."tokenHash" = $1
              AND t."revokedAt" IS NULL
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
            FROM "ApiToken" t
            JOIN "User" u ON t."userId" = u.id
            WHERE t."tokenHash" = $1
              AND t."revokedAt" IS NULL
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
    """Update ApiToken.lastUsedAt (and updatedAt) if it is stale.

    Returns True if a row was updated, False otherwise.
    Intended to be called after a token has already been validated.
    """
    if min_interval_seconds <= 0:
        min_interval_seconds = 0

    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE "ApiToken"
            SET "lastUsedAt" = NOW(), "updatedAt" = NOW()
            WHERE "tokenHash" = $1
              AND "revokedAt" IS NULL
              AND (
                "lastUsedAt" IS NULL
                OR "lastUsedAt" < (NOW() - ($2 * INTERVAL '1 second'))
              )
            RETURNING id
            """,
            token_hash,
            int(min_interval_seconds),
        )
        return row is not None


async def revoke_api_token(token_id: str) -> bool:
    """
    Revoke an API token by setting revokedAt.
    Idempotent: returns True if token exists (even if already revoked).
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            UPDATE "ApiToken"
            SET "revokedAt" = COALESCE("revokedAt", NOW()), "updatedAt" = NOW()
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
            UPDATE "ApiToken"
            SET "revokedAt" = COALESCE("revokedAt", NOW()), "updatedAt" = NOW()
            WHERE "tokenHash" = $1
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
            SELECT "revokedAt"
            FROM "ApiToken"
            WHERE "tokenHash" = $1
            """,
            token_hash,
        )
        # Token exists and has a revokedAt timestamp
        return row is not None and row["revokedAt"] is not None


async def get_tokens_for_alpha_user(alpha_user_id: str, include_revoked: bool = False) -> list[dict]:
    """Get tokens for an alpha user (optionally including revoked tokens)."""
    async with get_connection() as conn:
        where_clause = "\"alphaUserId\" = $1" if include_revoked else "\"alphaUserId\" = $1 AND \"revokedAt\" IS NULL"
        rows = await conn.fetch(
            f"""
            SELECT id, name, "createdAt", "lastUsedAt", "revokedAt"
            FROM "ApiToken"
            WHERE {where_clause}
            ORDER BY "createdAt" DESC
            """,
            alpha_user_id,
        )
        return [
            {
                "id": row["id"],
                "name": row["name"],
                "created_at": row["createdAt"],
                "last_used_at": row["lastUsedAt"],
                "revoked_at": row["revokedAt"],
            }
            for row in rows
        ]
