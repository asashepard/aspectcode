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
    """Update api_tokens.last_used_at, updated_at, and increment request_count.

    Returns True if a row was updated, False otherwise.
    Intended to be called after a token has already been validated.
    
    The request_count is always incremented, but last_used_at only updates
    if stale (to avoid excessive timestamp writes).
    """
    if min_interval_seconds <= 0:
        min_interval_seconds = 0

    async with get_connection() as conn:
        # Always increment request_count, but only update last_used_at if stale
        row = await conn.fetchrow(
            """
            UPDATE api_tokens
            SET 
                request_count = COALESCE(request_count, 0) + 1,
                updated_at = NOW(),
                last_used_at = CASE 
                    WHEN last_used_at IS NULL 
                         OR last_used_at < (NOW() - ($2 * INTERVAL '1 second'))
                    THEN NOW()
                    ELSE last_used_at
                END
            WHERE token_hash = $1
              AND revoked_at IS NULL
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
            SELECT id, name, created_at, last_used_at, revoked_at,
                   COALESCE(request_count, 0) as request_count
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
                "request_count": row["request_count"],
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
                created_at, last_used_at, revoked_at,
                COALESCE(request_count, 0) as request_count
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
                "request_count": row["request_count"],
            }
            for row in rows
        ]


async def get_platform_metrics() -> dict:
    """
    Get aggregate platform metrics for admin dashboard.
    
    Returns:
        Dict with total_requests, active_keys, total_keys, 
        daily_active_users, weekly_active_users, monthly_active_users,
        total_alpha_users, dormant_users, avg_requests_per_user
    """
    async with get_connection() as conn:
        # Get token/request metrics
        token_stats = await conn.fetchrow(
            """
            SELECT 
                COALESCE(SUM(COALESCE(request_count, 0)), 0) as total_requests,
                COUNT(*) FILTER (WHERE revoked_at IS NULL) as active_keys,
                COUNT(*) as total_keys,
                COUNT(DISTINCT alpha_user_id) FILTER (
                    WHERE revoked_at IS NULL 
                    AND last_used_at >= NOW() - INTERVAL '1 day'
                ) as daily_active_users,
                COUNT(DISTINCT alpha_user_id) FILTER (
                    WHERE revoked_at IS NULL 
                    AND last_used_at >= NOW() - INTERVAL '7 days'
                ) as weekly_active_users,
                COUNT(DISTINCT alpha_user_id) FILTER (
                    WHERE revoked_at IS NULL 
                    AND last_used_at >= NOW() - INTERVAL '30 days'
                ) as monthly_active_users,
                COUNT(DISTINCT alpha_user_id) FILTER (
                    WHERE revoked_at IS NULL 
                    AND alpha_user_id IS NOT NULL
                    AND (last_used_at IS NULL 
                         OR last_used_at < NOW() - INTERVAL '30 days')
                ) as dormant_users
            FROM api_tokens
            """
        )
        
        # Get total alpha users
        alpha_count = await conn.fetchval(
            "SELECT COUNT(*) FROM alpha_users"
        )
        
        # Calculate average requests per active user (30 days)
        avg_requests = await conn.fetchval(
            """
            SELECT COALESCE(AVG(user_total), 0)
            FROM (
                SELECT alpha_user_id, SUM(request_count) as user_total
                FROM api_tokens
                WHERE revoked_at IS NULL
                  AND last_used_at >= NOW() - INTERVAL '30 days'
                GROUP BY alpha_user_id
            ) as user_totals
            """
        )
        
        return {
            "total_requests": int(token_stats["total_requests"]),
            "active_keys": int(token_stats["active_keys"]),
            "total_keys": int(token_stats["total_keys"]),
            "daily_active_users": int(token_stats["daily_active_users"]),
            "weekly_active_users": int(token_stats["weekly_active_users"]),
            "monthly_active_users": int(token_stats["monthly_active_users"]),
            "total_alpha_users": int(alpha_count or 0),
            "dormant_users": int(token_stats["dormant_users"]),
            "avg_requests_per_user": round(float(avg_requests or 0), 1),
        }


# --- API Request Logging (Phase 2 Metrics) ---


async def log_api_request(
    token_id: str,
    endpoint: str,
    repo_root: Optional[str],
    language: Optional[str],
    files_count: int,
    autofix_requested: bool,
    response_time_ms: int,
    findings_count: int,
    rule_ids: list[str],
    status: str,
    error_type: Optional[str] = None,
) -> None:
    """
    Log an API request for metrics tracking.
    
    This is fire-and-forget - failures don't affect the request.
    """
    try:
        async with get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO api_request_logs (
                    token_id, endpoint, repo_root, language, files_count,
                    autofix_requested, response_time_ms, findings_count,
                    rule_ids, status, error_type, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                """,
                token_id,
                endpoint,
                repo_root[:500] if repo_root else None,
                language,
                files_count,
                autofix_requested,
                response_time_ms,
                findings_count,
                rule_ids,
                status,
                error_type,
            )
    except Exception as e:
        # Log but don't fail - this is best-effort
        print(f"[db] Failed to log API request: {e}")


async def get_top_triggered_rules(days: int = 30, limit: int = 10) -> list[dict]:
    """Get most frequently triggered rules in the last N days."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                rule_id,
                COUNT(*) as trigger_count
            FROM api_request_logs,
            LATERAL unnest(rule_ids) as rule_id
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
              AND status = 'success'
            GROUP BY rule_id
            ORDER BY trigger_count DESC
            LIMIT $2
            """,
            days,
            limit,
        )
        
        total = sum(row["trigger_count"] for row in rows)
        return [
            {
                "rule_id": row["rule_id"],
                "count": row["trigger_count"],
                "percentage": round(100.0 * row["trigger_count"] / total, 1) if total > 0 else 0,
            }
            for row in rows
        ]


async def get_response_time_stats(days: int = 30) -> dict:
    """Get response time statistics for the last N days."""
    async with get_connection() as conn:
        stats = await conn.fetchrow(
            """
            SELECT 
                COALESCE(AVG(response_time_ms), 0) as avg_ms,
                COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY response_time_ms), 0) as p50_ms,
                COALESCE(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY response_time_ms), 0) as p95_ms,
                COALESCE(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY response_time_ms), 0) as p99_ms,
                COUNT(*) as sample_count
            FROM api_request_logs
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
              AND status = 'success'
            """,
            days,
        )
        
        return {
            "avg_ms": round(float(stats["avg_ms"]), 1),
            "p50_ms": round(float(stats["p50_ms"]), 1),
            "p95_ms": round(float(stats["p95_ms"]), 1),
            "p99_ms": round(float(stats["p99_ms"]), 1),
            "sample_count": int(stats["sample_count"]),
        }


async def get_language_breakdown(days: int = 30) -> dict:
    """Get request count by language for the last N days."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                COALESCE(language, 'unknown') as language,
                COUNT(*) as request_count
            FROM api_request_logs
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY language
            ORDER BY request_count DESC
            """,
            days,
        )
        
        total = sum(row["request_count"] for row in rows)
        return {
            row["language"]: {
                "count": row["request_count"],
                "percentage": round(100.0 * row["request_count"] / total, 1) if total > 0 else 0,
            }
            for row in rows
        }


async def get_files_analyzed_stats(days: int = 30) -> dict:
    """Get statistics on files analyzed per request."""
    async with get_connection() as conn:
        stats = await conn.fetchrow(
            """
            SELECT 
                COALESCE(AVG(files_count), 0) as avg_files,
                COALESCE(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY files_count), 0) as median_files,
                COALESCE(MAX(files_count), 0) as max_files,
                COUNT(*) as sample_count
            FROM api_request_logs
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
              AND files_count > 0
            """,
            days,
        )
        
        return {
            "avg_files": round(float(stats["avg_files"]), 1),
            "median_files": int(stats["median_files"]),
            "max_files": int(stats["max_files"]),
            "sample_count": int(stats["sample_count"]),
        }


async def get_autofix_adoption_rate(days: int = 30) -> dict:
    """Get autofix usage statistics."""
    async with get_connection() as conn:
        stats = await conn.fetchrow(
            """
            SELECT 
                COUNT(*) as total_requests,
                SUM(CASE WHEN autofix_requested THEN 1 ELSE 0 END) as autofix_requests
            FROM api_request_logs
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
              AND endpoint = 'validate'
            """,
            days,
        )
        
        total = int(stats["total_requests"])
        autofix = int(stats["autofix_requests"])
        
        return {
            "total_requests": total,
            "autofix_requests": autofix,
            "adoption_rate": round(100.0 * autofix / total, 1) if total > 0 else 0,
        }


async def get_error_timeout_rates(days: int = 30) -> dict:
    """Get error and timeout rate statistics."""
    async with get_connection() as conn:
        rows = await conn.fetch(
            """
            SELECT 
                status,
                COUNT(*) as count
            FROM api_request_logs
            WHERE created_at >= NOW() - ($1 * INTERVAL '1 day')
            GROUP BY status
            """,
            days,
        )
        
        by_status = {row["status"]: row["count"] for row in rows}
        total = sum(by_status.values())
        
        success = by_status.get("success", 0)
        error = by_status.get("error", 0)
        timeout = by_status.get("timeout", 0)
        
        return {
            "total_requests": total,
            "success_count": success,
            "error_count": error,
            "timeout_count": timeout,
            "success_rate": round(100.0 * success / total, 1) if total > 0 else 0,
            "error_rate": round(100.0 * error / total, 1) if total > 0 else 0,
            "timeout_rate": round(100.0 * timeout / total, 1) if total > 0 else 0,
        }


async def get_detailed_metrics(days: int = 30) -> dict:
    """Get all detailed metrics for admin dashboard."""
    # Get Phase 1A metrics (from api_tokens)
    basic = await get_platform_metrics()
    
    # Get Phase 2 metrics (from api_request_logs)
    try:
        top_rules = await get_top_triggered_rules(days)
        response_times = await get_response_time_stats(days)
        language_breakdown = await get_language_breakdown(days)
        files_stats = await get_files_analyzed_stats(days)
        autofix_stats = await get_autofix_adoption_rate(days)
        error_stats = await get_error_timeout_rates(days)
    except Exception as e:
        # Table may not exist yet - return empty Phase 2 data
        print(f"[db] Phase 2 metrics unavailable: {e}")
        top_rules = []
        response_times = {"avg_ms": 0, "p50_ms": 0, "p95_ms": 0, "p99_ms": 0, "sample_count": 0}
        language_breakdown = {}
        files_stats = {"avg_files": 0, "median_files": 0, "max_files": 0, "sample_count": 0}
        autofix_stats = {"total_requests": 0, "autofix_requests": 0, "adoption_rate": 0}
        error_stats = {"total_requests": 0, "success_count": 0, "error_count": 0, "timeout_count": 0, 
                      "success_rate": 0, "error_rate": 0, "timeout_rate": 0}
    
    return {
        # Phase 1A
        **basic,
        
        # Phase 2
        "top_rules": top_rules,
        "response_times": response_times,
        "language_breakdown": language_breakdown,
        "files_stats": files_stats,
        "autofix_stats": autofix_stats,
        "error_stats": error_stats,
    }
