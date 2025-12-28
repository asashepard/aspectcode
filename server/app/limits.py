"""
Per-API-Key Rate Limiting (Alpha Version)

In-memory rate limiting for alpha:
- RPM (requests per minute) per API key with sliding window
- Concurrency limiting per API key with auto-expiring leases
- Daily cap per API key (resets at midnight UTC)
- IP-based fallback for unauthenticated requests

Limits reset on deploy (in-memory only). For production DDoS
protection, use Cloud Armor at the edge.
"""

import asyncio
import hashlib
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Literal
from dataclasses import dataclass

from .settings import settings


# Instance tracking for debugging
INSTANCE_ID = uuid.uuid4().hex[:8]
STARTUP_TIME = time.time()


def get_instance_id() -> str:
    """Get unique instance ID for this server process."""
    return INSTANCE_ID


def get_uptime_seconds() -> int:
    """Get server uptime in seconds."""
    return int(time.time() - STARTUP_TIME)


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    reason: Optional[Literal["rpm", "concurrency", "daily_cap"]] = None
    retry_after: int = 5  # seconds until client should retry
    current: int = 0
    limit: int = 0
    # Extra fields for daily cap
    reset_at_utc: Optional[str] = None


def _get_today_key() -> str:
    """Get today's date key in UTC (YYYY-MM-DD)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _seconds_until_midnight_utc() -> int:
    """Calculate seconds until next UTC midnight."""
    now = datetime.now(timezone.utc)
    midnight = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    next_midnight = midnight + timedelta(days=1)
    return max(1, int((next_midnight - now).total_seconds()))


class RateLimiter:
    """
    Simple in-memory rate limiter.
    
    Tracks per-principal:
    - RPM: sliding window of request timestamps (last 60s)
    - Concurrency: active request count with auto-expiring leases
    - Daily: count of requests per day (prunes old days)
    """
    
    def __init__(self):
        # RPM: principal_id -> list of timestamps
        self._rpm: Dict[str, list] = {}
        # Concurrency: principal_id -> dict of {request_id: expires_at}
        self._concurrency: Dict[str, Dict[str, float]] = {}
        # Daily: (principal_id, date_key) -> count
        self._daily: Dict[str, int] = {}
        self._lock = asyncio.Lock()
        self._last_prune_day: str = ""
    
    def _cleanup_rpm(self, principal_id: str, now: float) -> None:
        """Remove RPM entries older than 60 seconds."""
        if principal_id in self._rpm:
            cutoff = now - 60
            self._rpm[principal_id] = [ts for ts in self._rpm[principal_id] if ts > cutoff]
    
    def _cleanup_concurrency(self, principal_id: str, now: float) -> None:
        """Remove expired concurrency leases."""
        if principal_id in self._concurrency:
            self._concurrency[principal_id] = {
                req_id: expires
                for req_id, expires in self._concurrency[principal_id].items()
                if expires > now
            }
    
    def _prune_old_days(self, today: str) -> None:
        """Remove daily buckets older than yesterday (keep 2 days max)."""
        if self._last_prune_day == today:
            return  # Already pruned today
        
        # Calculate yesterday's key
        yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
        
        # Remove keys that are neither today nor yesterday
        keys_to_remove = [
            key for key in self._daily.keys()
            if not (key.endswith(today) or key.endswith(yesterday))
        ]
        for key in keys_to_remove:
            del self._daily[key]
        
        self._last_prune_day = today
    
    async def check_daily_cap(self, principal_id: str) -> RateLimitResult:
        """Check if daily cap is exceeded (doesn't increment - that happens on success)."""
        async with self._lock:
            today = _get_today_key()
            self._prune_old_days(today)
            
            daily_key = f"{principal_id}:{today}"
            current = self._daily.get(daily_key, 0)
            daily_cap = settings.daily_cap
            
            if current >= daily_cap:
                retry_after = _seconds_until_midnight_utc()
                next_midnight = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ) + timedelta(days=1)
                
                return RateLimitResult(
                    allowed=False,
                    reason="daily_cap",
                    retry_after=retry_after,
                    current=current,
                    limit=daily_cap,
                    reset_at_utc=next_midnight.isoformat(),
                )
            
            return RateLimitResult(
                allowed=True,
                current=current,
                limit=daily_cap,
            )
    
    async def increment_daily(self, principal_id: str) -> None:
        """Increment daily counter after successful request."""
        async with self._lock:
            today = _get_today_key()
            daily_key = f"{principal_id}:{today}"
            self._daily[daily_key] = self._daily.get(daily_key, 0) + 1
    
    async def check_rpm(self, principal_id: str) -> RateLimitResult:
        """Check and increment RPM counter. Returns whether request is allowed."""
        async with self._lock:
            now = time.time()
            self._cleanup_rpm(principal_id, now)
            
            if principal_id not in self._rpm:
                self._rpm[principal_id] = []
            
            current = len(self._rpm[principal_id])
            rpm_limit = settings.rate_limit
            
            if current >= rpm_limit:
                # Calculate when oldest entry expires
                oldest = min(self._rpm[principal_id]) if self._rpm[principal_id] else now
                retry_after = max(1, int(oldest + 60 - now))
                return RateLimitResult(
                    allowed=False,
                    reason="rpm",
                    retry_after=retry_after,
                    current=current,
                    limit=rpm_limit,
                )
            
            # Allow and record
            self._rpm[principal_id].append(now)
            return RateLimitResult(
                allowed=True,
                current=current + 1,
                limit=rpm_limit,
            )
    
    async def acquire_concurrency(self, principal_id: str, request_id: str) -> RateLimitResult:
        """Try to acquire a concurrency slot."""
        async with self._lock:
            now = time.time()
            self._cleanup_concurrency(principal_id, now)
            
            if principal_id not in self._concurrency:
                self._concurrency[principal_id] = {}
            
            current = len(self._concurrency[principal_id])
            max_conc = settings.max_concurrent
            
            if current >= max_conc:
                return RateLimitResult(
                    allowed=False,
                    reason="concurrency",
                    retry_after=5,
                    current=current,
                    limit=max_conc,
                )
            
            # Acquire slot with 2-minute TTL (safety net)
            self._concurrency[principal_id][request_id] = now + 120
            return RateLimitResult(
                allowed=True,
                current=current + 1,
                limit=max_conc,
            )
    
    async def release_concurrency(self, principal_id: str, request_id: str) -> None:
        """Release a concurrency slot."""
        async with self._lock:
            if principal_id in self._concurrency:
                self._concurrency[principal_id].pop(request_id, None)
    
    async def get_usage(self, principal_id: str) -> dict:
        """Get current usage for a principal (for /limits endpoint)."""
        async with self._lock:
            now = time.time()
            today = _get_today_key()
            
            self._cleanup_rpm(principal_id, now)
            self._cleanup_concurrency(principal_id, now)
            
            rpm_count = len(self._rpm.get(principal_id, []))
            conc_count = len(self._concurrency.get(principal_id, {}))
            daily_key = f"{principal_id}:{today}"
            daily_count = self._daily.get(daily_key, 0)
            
            return {
                "rpm": {
                    "used": rpm_count,
                    "limit": settings.rate_limit,
                    "remaining": max(0, settings.rate_limit - rpm_count),
                    "window_seconds": 60,
                },
                "concurrency": {
                    "in_use": conc_count,
                    "limit": settings.max_concurrent,
                    "remaining": max(0, settings.max_concurrent - conc_count),
                },
                "daily": {
                    "used": daily_count,
                    "limit": settings.daily_cap,
                    "remaining": max(0, settings.daily_cap - daily_count),
                    "reset_seconds": _seconds_until_midnight_utc(),
                },
            }
    
    def get_stats(self) -> dict:
        """Get overall limiter stats for debugging."""
        return {
            "principals_tracked": len(self._rpm),
            "daily_buckets": len(self._daily),
        }


# --- Global Instance ---

_limiter: Optional[RateLimiter] = None


async def init_limiter() -> None:
    """Initialize the rate limiter on startup."""
    global _limiter
    if settings.limits_enabled:
        _limiter = RateLimiter()
        print(f"[limits] In-memory rate limiter initialized (instance={INSTANCE_ID})")
        print(f"[limits] Config: {settings.rate_limit} RPM, {settings.max_concurrent} concurrent, {settings.daily_cap} daily cap")
    else:
        _limiter = None
        print("[limits] Rate limiting disabled")


async def close_limiter() -> None:
    """Cleanup on shutdown (no-op for in-memory)."""
    global _limiter
    _limiter = None


def get_limiter() -> Optional[RateLimiter]:
    """Get the global limiter instance."""
    return _limiter


def get_limiter_type() -> str:
    """Get limiter type for health endpoint."""
    if _limiter is None:
        return "disabled"
    return "memory"


# --- Helper: Compute Principal ID ---

def get_principal_id(api_key: Optional[str] = None, client_ip: Optional[str] = None) -> str:
    """
    Get a stable principal ID for rate limiting.
    
    Uses full SHA-256 hash of API key if present, otherwise IP address.
    This ensures consistency across all rate limit checks.
    """
    if api_key:
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        return f"key:{key_hash}"
    if client_ip:
        return f"ip:{client_ip}"
    return "unknown"


def hash_principal_for_logging(principal_id: str) -> str:
    """
    Create a short hash of principal_id for logging.
    Safe to log - doesn't reveal the API key.
    """
    return hashlib.sha256(principal_id.encode()).hexdigest()[:12]


# --- 429 Response Helpers ---

def make_rate_limit_response(
    reason: Literal["rpm", "concurrency", "daily_cap"],
    result: RateLimitResult,
    request_id: str,
) -> dict:
    """
    Create a standardized 429 response body.
    """
    base = {
        "error": "rate_limited",
        "reason": reason,
        "retry_after_seconds": result.retry_after,
        "request_id": request_id,
    }
    
    if reason == "rpm":
        base["limit"] = result.limit
        base["used"] = result.current
        base["window_seconds"] = 60
    elif reason == "concurrency":
        base["max_concurrent"] = result.limit
        base["in_use"] = result.current
    elif reason == "daily_cap":
        base["daily_cap"] = result.limit
        base["used_today"] = result.current
        base["reset_at_utc"] = result.reset_at_utc
    
    return base
