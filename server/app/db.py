"""
Database access layer for alpha signup and token management.
Uses asyncpg for async Postgres access.
"""

import hashlib
import secrets
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

# asyncpg is optional - only needed when DATABASE_URL is configured
try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    asyncpg = None  # type: ignore
    ASYNCPG_AVAILABLE = False

from .settings import settings, DATABASE_URL


# Connection pool (initialized on startup)
_pool = None  # type: Optional[asyncpg.Pool]


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


def generate_api_key() -> tuple[str, str]:
    """
    Generate a new API key.
    Returns (raw_token, token_hash).
    """
    raw_token = secrets.token_urlsafe(32)
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


async def create_api_token(
    alpha_user_id: str,
    token_hash: str,
    name: str = "default",
) -> dict:
    """
    Create a new API token for an alpha user.
    Returns dict with id, name, created_at.
    """
    async with get_connection() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO "ApiToken" ("alphaUserId", "tokenHash", name, "createdAt", "updatedAt")
            VALUES ($1, $2, $3, NOW(), NOW())
            RETURNING id, name, "createdAt"
            """,
            alpha_user_id,
            token_hash,
            name,
        )
        return {"id": row["id"], "name": row["name"], "created_at": row["createdAt"]}


async def get_alpha_user_by_token_hash(token_hash: str) -> Optional[dict]:
    """
    Look up an alpha user by their API token hash.
    Also updates the token's last_used_at timestamp.
    Returns dict with user info and token info, or None if not found.
    """
    async with get_connection() as conn:
        # Update last_used_at and fetch user info in one query
        row = await conn.fetchrow(
            """
            UPDATE "ApiToken" t
            SET "lastUsedAt" = NOW()
            FROM "AlphaUser" u
            WHERE t."alphaUserId" = u.id
              AND t."tokenHash" = $1
              AND t."revokedAt" IS NULL
            RETURNING u.id, u.email, t.id as token_id, t.name as token_name
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
    Also updates the token's last_used_at timestamp.
    Returns dict with user info and token info, or None if not found.
    """
    async with get_connection() as conn:
        # Update last_used_at and fetch user info in one query
        row = await conn.fetchrow(
            """
            UPDATE "ApiToken" t
            SET "lastUsedAt" = NOW()
            FROM "User" u
            WHERE t."userId" = u.id
              AND t."tokenHash" = $1
              AND t."revokedAt" IS NULL
            RETURNING u.id, u.email, t.id as token_id, t.name as token_name
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


async def revoke_api_token(token_id: str) -> bool:
    """
    Revoke an API token by setting revokedAt.
    Returns True if token was found and revoked, False otherwise.
    """
    async with get_connection() as conn:
        result = await conn.execute(
            """
            UPDATE "ApiToken"
            SET "revokedAt" = NOW(), "updatedAt" = NOW()
            WHERE id = $1 AND "revokedAt" IS NULL
            """,
            token_id,
        )
        return result == "UPDATE 1"


async def get_tokens_for_alpha_user(alpha_user_id: str) -> list[dict]:
    """
    Get all active (non-revoked) tokens for an alpha user.
    """
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, "createdAt", "lastUsedAt"
            FROM "ApiToken"
            WHERE "alphaUserId" = $1 AND "revokedAt" IS NULL
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
            }
            for row in rows
        ]
