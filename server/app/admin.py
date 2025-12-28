"""
Admin API endpoints for managing API tokens.

All endpoints require admin authentication (env-based service keys).
"""

from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from .auth import get_current_user, UserContext
from . import db


router = APIRouter(prefix="/admin", tags=["admin"])


# --- Request/Response Models ---


class CreateTokenRequest(BaseModel):
    """Request to create a new API token."""
    alpha_user_id: Optional[str] = Field(None, description="Alpha user ID to associate token with")
    user_id: Optional[str] = Field(None, description="Paid user ID to associate token with")
    name: Optional[str] = Field("default", description="Human-readable label for the token")


class CreateTokenResponse(BaseModel):
    """Response containing the newly created token (raw token returned only once)."""
    token: str = Field(..., description="Raw API token (only available at creation time)")
    token_id: str = Field(..., description="Database ID of the token")
    created_at: datetime = Field(..., description="Token creation timestamp")


class RevokeTokenResponse(BaseModel):
    """Response confirming token revocation."""
    token_id: str = Field(..., description="Database ID of the revoked token")
    revoked_at: datetime = Field(..., description="Revocation timestamp")


class TokenMetadata(BaseModel):
    """Token metadata (never includes raw token)."""
    id: str = Field(..., description="Database ID of the token")
    name: Optional[str] = Field(None, description="Human-readable label")
    alpha_user_id: Optional[str] = Field(None, description="Associated alpha user ID")
    user_id: Optional[str] = Field(None, description="Associated paid user ID")
    created_at: datetime = Field(..., description="Token creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    revoked_at: Optional[datetime] = Field(None, description="Revocation timestamp (null if active)")
    request_count: int = Field(0, description="Total number of authenticated requests")


class ListTokensResponse(BaseModel):
    """Response containing list of token metadata."""
    tokens: List[TokenMetadata]


class PlatformMetrics(BaseModel):
    """Aggregate platform metrics for admin dashboard."""
    total_requests: int = Field(..., description="Total authenticated requests across all tokens")
    active_keys: int = Field(..., description="Number of non-revoked API keys")
    total_keys: int = Field(..., description="Total API keys (including revoked)")
    daily_active_users: int = Field(..., description="Unique users active in last 24 hours")
    weekly_active_users: int = Field(..., description="Unique users active in last 7 days")
    monthly_active_users: int = Field(0, description="Unique users active in last 30 days")
    total_alpha_users: int = Field(..., description="Total registered alpha users")
    dormant_users: int = Field(0, description="Users inactive for 30+ days")
    avg_requests_per_user: float = Field(0.0, description="Average requests per active user (30 days)")


class RuleTriggerStats(BaseModel):
    """Statistics for a single rule."""
    rule_id: str = Field(..., description="Rule identifier")
    count: int = Field(..., description="Number of times triggered")
    percentage: float = Field(..., description="Percentage of all findings")


class ResponseTimeStats(BaseModel):
    """Response time statistics."""
    avg_ms: float = Field(..., description="Average response time in ms")
    p50_ms: float = Field(..., description="Median response time")
    p95_ms: float = Field(..., description="95th percentile response time")
    p99_ms: float = Field(..., description="99th percentile response time")
    sample_count: int = Field(..., description="Number of requests sampled")


class FilesStats(BaseModel):
    """Statistics on files analyzed per request."""
    avg_files: float = Field(..., description="Average files per request")
    median_files: int = Field(..., description="Median files per request")
    max_files: int = Field(..., description="Maximum files in a single request")
    sample_count: int = Field(..., description="Number of requests sampled")


class ErrorStats(BaseModel):
    """Error and timeout rate statistics."""
    total_requests: int = Field(..., description="Total requests")
    success_count: int = Field(..., description="Successful requests")
    error_count: int = Field(..., description="Failed requests")
    timeout_count: int = Field(..., description="Timed out requests")
    success_rate: float = Field(..., description="Success rate percentage")
    error_rate: float = Field(..., description="Error rate percentage")
    timeout_rate: float = Field(..., description="Timeout rate percentage")


class DetailedMetrics(BaseModel):
    """Comprehensive platform metrics for admin dashboard."""
    # Phase 1A (from api_tokens)
    total_requests: int
    active_keys: int
    total_keys: int
    daily_active_users: int
    weekly_active_users: int
    monthly_active_users: int
    total_alpha_users: int
    dormant_users: int
    avg_requests_per_user: float
    
    # Phase 2 (from api_request_logs)
    top_rules: List[RuleTriggerStats] = Field(default_factory=list)
    response_times: ResponseTimeStats
    language_breakdown: dict = Field(default_factory=dict)
    files_stats: FilesStats
    error_stats: ErrorStats


class DbInfoResponse(BaseModel):
    """DB introspection for request logging."""
    request_log_table: str
    request_log_columns: List[dict]
    recent_rows_24h: int


# --- Admin Dependency ---


async def require_admin(current_user: UserContext = Depends(get_current_user)) -> UserContext:
    """Dependency that requires admin authentication."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required. This endpoint requires a service API key.",
        )
    return current_user


# --- Endpoints ---


@router.post("/api-tokens", response_model=CreateTokenResponse)
async def create_api_token(
    request: CreateTokenRequest,
    admin: UserContext = Depends(require_admin),
):
    """
    Create a new API token.
    
    The raw token is returned only once in this response.
    Store it securely - it cannot be retrieved again.
    
    Provide at most one of `alpha_user_id` or `user_id`.
    """
    # Validate: at most one of alpha_user_id or user_id
    if request.alpha_user_id and request.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide at most one of 'alpha_user_id' or 'user_id', not both.",
        )
    
    name = request.name or "default"
    
    try:
        raw_token, token_row = await db.create_api_token_for_admin(
            alpha_user_id=request.alpha_user_id,
            user_id=request.user_id,
            name=name,
        )
        
        return CreateTokenResponse(
            token=raw_token,
            token_id=token_row["id"],
            created_at=token_row["created_at"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        print(f"[admin] Error creating token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create API token.",
        )


@router.post("/api-tokens/{token_id}/revoke", response_model=RevokeTokenResponse)
async def revoke_api_token(
    token_id: str,
    admin: UserContext = Depends(require_admin),
):
    """
    Revoke an API token.
    
    Revoked tokens will receive 403 Forbidden on subsequent requests.
    This operation is idempotent - revoking an already-revoked token is a no-op.
    """
    try:
        result = await db.revoke_api_token_by_id(token_id)
        
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Token with ID '{token_id}' not found.",
            )
        
        return RevokeTokenResponse(
            token_id=result["id"],
            revoked_at=result["revoked_at"],
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"[admin] Error revoking token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke API token.",
        )


@router.get("/api-tokens", response_model=ListTokensResponse)
async def list_api_tokens(
    alpha_user_id: Optional[str] = None,
    user_id: Optional[str] = None,
    include_revoked: bool = True,
    admin: UserContext = Depends(require_admin),
):
    """
    List API tokens with optional filtering.
    
    Query parameters:
    - `alpha_user_id`: Filter by alpha user
    - `user_id`: Filter by paid user
    - `include_revoked`: Include revoked tokens (default: true)
    
    Returns token metadata only - raw tokens are never returned.
    """
    try:
        tokens = await db.list_api_tokens(
            alpha_user_id=alpha_user_id,
            user_id=user_id,
            include_revoked=include_revoked,
        )
        
        return ListTokensResponse(
            tokens=[
                TokenMetadata(
                    id=t["id"],
                    name=t.get("name"),
                    alpha_user_id=t.get("alpha_user_id"),
                    user_id=t.get("user_id"),
                    created_at=t["created_at"],
                    last_used_at=t.get("last_used_at"),
                    revoked_at=t.get("revoked_at"),
                    request_count=t.get("request_count", 0),
                )
                for t in tokens
            ]
        )
    except Exception as e:
        print(f"[admin] Error listing tokens: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list API tokens.",
        )


@router.get("/metrics", response_model=PlatformMetrics)
async def get_metrics(
    admin: UserContext = Depends(require_admin),
):
    """
    Get aggregate platform metrics (Phase 1A - from api_tokens table).
    
    Returns usage statistics for the admin dashboard including:
    - Total authenticated requests across all tokens
    - Active/total API keys
    - Daily, weekly, and monthly active users
    - Dormant users (inactive 30+ days)
    - Average requests per active user
    - Total registered alpha users
    """
    try:
        metrics = await db.get_platform_metrics()
        return PlatformMetrics(**metrics)
    except Exception as e:
        print(f"[admin] Error fetching metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch platform metrics.",
        )


@router.get("/metrics/detailed", response_model=DetailedMetrics)
async def get_detailed_metrics(
    days: int = 30,
    admin: UserContext = Depends(require_admin),
):
    """
    Get detailed platform metrics (Phase 1A + Phase 2).
    
    Includes all Phase 1A metrics plus detailed request analytics:
    - Top triggered rules with counts
    - Response time statistics (avg, P50, P95, P99)
    - Language breakdown (Python/TypeScript/JavaScript)
    - Files analyzed per request (avg/median)
    - Error/timeout rates
    
    Note: Phase 2 metrics require the api_request_logs table.
    If not available, Phase 2 sections will have empty/zero values.
    
    Args:
        days: Number of days to aggregate (default: 30)
    """
    try:
        metrics = await db.get_detailed_metrics(days)
        
        # Transform top_rules to typed model
        top_rules = [
            RuleTriggerStats(**rule) for rule in metrics.get("top_rules", [])
        ]
        
        return DetailedMetrics(
            # Phase 1A
            total_requests=metrics["total_requests"],
            active_keys=metrics["active_keys"],
            total_keys=metrics["total_keys"],
            daily_active_users=metrics["daily_active_users"],
            weekly_active_users=metrics["weekly_active_users"],
            monthly_active_users=metrics["monthly_active_users"],
            total_alpha_users=metrics["total_alpha_users"],
            dormant_users=metrics["dormant_users"],
            avg_requests_per_user=metrics["avg_requests_per_user"],
            
            # Phase 2
            top_rules=top_rules,
            response_times=ResponseTimeStats(**metrics["response_times"]),
            language_breakdown=metrics["language_breakdown"],
            files_stats=FilesStats(**metrics["files_stats"]),
            error_stats=ErrorStats(**metrics["error_stats"]),
        )
    except Exception as e:
        print(f"[admin] Error fetching detailed metrics: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch detailed metrics.",
        )


@router.get("/db-info", response_model=DbInfoResponse)
async def get_db_info(
    admin: UserContext = Depends(require_admin),
):
    """Return which request-log table the server is using, and basic stats."""
    try:
        info = await db.get_request_log_db_info()
        return DbInfoResponse(**info)
    except Exception as e:
        print(f"[admin] Error fetching db info: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch DB info.",
        )
