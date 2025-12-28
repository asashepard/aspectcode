import time
import sys
import os
import hashlib
import asyncio
import uuid
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from pydantic import BaseModel, EmailStr

from .models import (
    ValidateResponse, IndexRequest, IndexResult, ValidateFullRequest, SnapshotInfo
)
from .storage import get_storage
from .settings import settings, DATABASE_URL
from .auth import get_current_user, UserContext
from .admin import router as admin_router
from . import db
from . import limits

# Import tree-sitter engine
try:
    # Add the server directory to the path to ensure engine module can be found
    server_dir = os.path.dirname(os.path.dirname(__file__))
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)
    TREE_SITTER_AVAILABLE = True
except ImportError as e:
    print(f"Warning: Tree-sitter engine not available: {e}")
    TREE_SITTER_AVAILABLE = False


# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    # Startup: initialize database pool if configured
    if DATABASE_URL:
        try:
            await db.init_pool()
            print("[startup] Database pool initialized successfully")
        except Exception as e:
            print(f"[startup] WARNING: Failed to initialize database pool: {e}")
            print("[startup] Database-backed authentication will not be available")
    else:
        print("[startup] No DATABASE_URL configured - running without database")
    
    # Initialize rate limiter
    try:
        await limits.init_limiter()
        print(f"[startup] Rate limiter initialized ({limits.get_limiter_type()})")
    except Exception as e:
        print(f"[startup] WARNING: Failed to initialize rate limiter: {e}")
    
    yield
    
    # Shutdown: close rate limiter
    await limits.close_limiter()
    # Shutdown: close database pool
    await db.close_pool()


app = FastAPI(
    title="Aspect Code — Tree-sitter Code Analysis",
    lifespan=lifespan
)

# Include admin router
app.include_router(admin_router)

# CORS configuration from settings
# If no origins configured, allow localhost for development
allowed_origins = settings.allowed_origins if settings.allowed_origins else [
    "http://localhost:*",
    "http://127.0.0.1:*",
    "vscode-webview://*"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key", "Authorization", "X-AspectCode-Client-Version"],
)


# --- Rate Limiting Middleware ---
# Paths that should have rate limiting applied (billable endpoints)
RATE_LIMITED_PATHS = {"/validate", "/validate_tree_sitter", "/index"}


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from trusted proxies."""
    # Cloud Run sets X-Forwarded-For; take the first (client) IP
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    # Fallback to direct connection
    if request.client:
        return request.client.host
    return "unknown"


def _get_or_create_request_id(request: Request) -> str:
    """Get request ID from header or generate one."""
    return request.headers.get("X-Request-Id") or str(uuid.uuid4())


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces per-API-key rate limits (RPM + concurrency + daily cap).
    
    For requests without an API key, uses client IP as the principal.
    This protects against unauthenticated DDoS while still allowing
    the auth layer to return proper 401 errors.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Generate/get request ID for correlation
        request_id = _get_or_create_request_id(request)
        start_time = time.time()

        # Stash on request for downstream logging
        request.state.request_id = request_id
        request.state.client_ip = _get_client_ip(request)
        request.state.user_agent = request.headers.get("User-Agent")
        
        # Only apply rate limiting to billable paths
        if request.url.path not in RATE_LIMITED_PATHS:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        
        limiter = limits.get_limiter()
        if not limiter:
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response
        
        # Extract API key from headers
        api_key = request.headers.get("X-API-Key")
        if not api_key:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.lower().startswith("bearer "):
                api_key = auth_header[7:]
        
        # Compute principal ID (key hash or IP)
        if api_key:
            principal_id = limits.get_principal_id(api_key=api_key)
        else:
            client_ip = _get_client_ip(request)
            principal_id = limits.get_principal_id(client_ip=client_ip)
        
        principal_hash = limits.hash_principal_for_logging(principal_id)
        limited_reason = None
        try:
            # 1. Check daily cap first (cheapest check)
            daily_result = await limiter.check_daily_cap(principal_id)
            if not daily_result.allowed:
                limited_reason = "daily_cap"
                print(f"[limits] 429 daily_cap principal={principal_hash} path={request.url.path} request_id={request_id}")
                return JSONResponse(
                    status_code=429,
                    content=limits.make_rate_limit_response("daily_cap", daily_result, request_id),
                    headers={
                        "Retry-After": str(daily_result.retry_after),
                        "X-Request-Id": request_id,
                    },
                )
            
            # 2. Check RPM
            rpm_result = await limiter.check_rpm(principal_id)
            if not rpm_result.allowed:
                limited_reason = "rpm"
                print(f"[limits] 429 rpm principal={principal_hash} path={request.url.path} request_id={request_id}")
                return JSONResponse(
                    status_code=429,
                    content=limits.make_rate_limit_response("rpm", rpm_result, request_id),
                    headers={
                        "Retry-After": str(rpm_result.retry_after),
                        "X-Request-Id": request_id,
                    },
                )
            
            # 3. Acquire concurrency slot
            conc_result = await limiter.acquire_concurrency(principal_id, request_id)
            if not conc_result.allowed:
                limited_reason = "concurrency"
                print(f"[limits] 429 concurrency principal={principal_hash} path={request.url.path} request_id={request_id}")
                return JSONResponse(
                    status_code=429,
                    content=limits.make_rate_limit_response("concurrency", conc_result, request_id),
                    headers={
                        "Retry-After": str(conc_result.retry_after),
                        "X-Request-Id": request_id,
                    },
                )
            
            # Process request
            try:
                response = await call_next(request)
                
                # Increment daily counter only on successful response (2xx)
                if 200 <= response.status_code < 300:
                    await limiter.increment_daily(principal_id)
                
                # Log successful request
                duration_ms = int((time.time() - start_time) * 1000)
                print(f"[request] principal={principal_hash} path={request.url.path} status={response.status_code} duration_ms={duration_ms} request_id={request_id}")
                
                response.headers["X-Request-Id"] = request_id
                return response
            finally:
                await limiter.release_concurrency(principal_id, request_id)
        
        except Exception as e:
            # Fail open: if limiter errors, allow request through
            print(f"[limits] Middleware error: {e} request_id={request_id}")
            response = await call_next(request)
            response.headers["X-Request-Id"] = request_id
            return response


# Add rate limiting middleware
app.add_middleware(RateLimitMiddleware)


# Server version for health checks
SERVER_VERSION = "1.0.0"

@app.get("/health")
def health():
    """
    Health check endpoint - no authentication required.
    Used by load balancers and orchestrators.
    """
    return {
        "status": "ok",
        "version": SERVER_VERSION,
        "engine": "tree-sitter" if TREE_SITTER_AVAILABLE else "unavailable",
        "timestamp": int(time.time()),
        "auth_required": bool(settings.api_keys) or bool(DATABASE_URL),
        "mode": settings.mode,
        "limiter": limits.get_limiter_type(),
    }


@app.get("/limits")
async def get_limits_status(
    request: Request,
    user: UserContext = Depends(get_current_user)
):
    """
    Get current rate limit status for the authenticated user.
    Useful for debugging and testing rate limits.
    """
    limiter = limits.get_limiter()
    
    if not limiter:
        return {
            "enabled": False,
            "message": "Rate limiting is disabled",
            "instance_id": limits.get_instance_id(),
            "uptime_seconds": limits.get_uptime_seconds(),
        }
    
    try:
        # Use the same principal ID derivation as the middleware
        principal_id = limits.get_principal_id(api_key=user.api_key)
        usage = await limiter.get_usage(principal_id)
        stats = limiter.get_stats()
        return {
            "enabled": True,
            "limiter_type": limits.get_limiter_type(),
            "note": "In-memory limits reset on deploy. Limits are per-instance.",
            "instance_id": limits.get_instance_id(),
            "uptime_seconds": limits.get_uptime_seconds(),
            "config": {
                "rpm_limit": settings.rate_limit,
                "window_seconds": 60,
                "max_concurrent": settings.max_concurrent,
                "daily_cap": settings.daily_cap,
            },
            "your_usage": usage,
            "stats": stats,
        }
    except Exception as e:
        return {
            "enabled": True,
            "error": str(e),
            "instance_id": limits.get_instance_id(),
        }


# --- Alpha Registration (disabled in production mode) ---
# API keys must be created manually via database.
# See server/scripts/ for admin tooling.


# Alpha registration endpoint removed - API keys created manually via database


@app.post("/index", response_model=IndexResult)
def index_repository(
    req: IndexRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """
    Index a repository for analysis.
    
    Note: This endpoint requires the repository to exist on the server filesystem.
    In cloud deployments, this will return an error for local paths.
    Use /validate directly with paths that exist on the server.
    """
    try:
        from .services.indexing import index_repository as index_repo_service
        return index_repo_service(req)
    except Exception as e:
        # Return a valid IndexResult with error information
        return IndexResult(
            snapshot_id="error-indexing-failed",
            file_count=0,
            bytes_indexed=0,
            took_ms=0,
            processing_time_ms=0,
            dependency_count=0,
            skipped_files=0,
            parse_errors=1
        )

@app.post("/validate", response_model=ValidateResponse)
async def validate_code(
    request: Request,
    req: ValidateFullRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """
    Standard validation endpoint for tree-sitter analysis.
    
    This is the main validation endpoint that should be used going forward.
    The '/validate_tree_sitter' endpoint is maintained for backward compatibility.
    """
    return await validate_with_logging(request, req, user, "validate")

@app.post("/validate_tree_sitter", response_model=ValidateResponse)
async def validate_with_tree_sitter(
    request: Request,
    req: ValidateFullRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """Validate using the tree-sitter engine."""
    return await validate_with_logging(request, req, user, "validate_tree_sitter")


def _detect_language(req: ValidateFullRequest) -> str:
    """Detect primary language from request."""
    if req.languages:
        if len(req.languages) == 1:
            return req.languages[0]
        else:
            return "mixed"
    return "unknown"


def _languages_to_string(langs: Optional[List[str]]) -> str:
    if not langs:
        return "unknown"
    unique = sorted({l for l in langs if l})
    if not unique:
        return "unknown"
    return ",".join(unique)


def _detect_languages_for_logging(req: ValidateFullRequest, response: Optional[ValidateResponse]) -> str:
    """Detect languages for request logging.

    Preference order:
    1) Engine-detected languages (response.metrics["languages"]) when available
    2) Request-provided req.languages
    3) Infer from remote file payload (req.files)
    """

    try:
        if response and isinstance(getattr(response, "metrics", None), dict):
            langs = response.metrics.get("languages")
            if isinstance(langs, list) and langs:
                return _languages_to_string([str(x) for x in langs])
    except Exception:
        pass

    if req.languages:
        return _languages_to_string(req.languages)

    if req.files:
        inferred: List[str] = []
        for f in req.files:
            lang = getattr(f, "language", None)
            if lang:
                inferred.append(str(lang))
                continue
            path = (getattr(f, "path", "") or "").lower()
            if path.endswith(".py"):
                inferred.append("python")
            elif path.endswith((".ts", ".tsx")):
                inferred.append("typescript")
            elif path.endswith((".js", ".jsx", ".mjs", ".cjs")):
                inferred.append("javascript")
            elif path.endswith(".java"):
                inferred.append("java")
            elif path.endswith((".cs", ".csx")):
                inferred.append("csharp")

        return _languages_to_string(inferred)

    return "unknown"


def _estimate_files_count(req: ValidateFullRequest) -> int:
    """Estimate files to be analyzed from request."""
    if req.files:
        return len(req.files)
    if req.paths:
        return len(req.paths)
    return 0

def _detect_files_count_for_logging(req: ValidateFullRequest, response: Optional[ValidateResponse]) -> int:
    try:
        if response and isinstance(getattr(response, "metrics", None), dict):
            v = response.metrics.get("files_checked")
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.isdigit():
                return int(v)
    except Exception:
        pass
    return _estimate_files_count(req)


def _calculate_lines_of_code(req: ValidateFullRequest) -> int:
    """Calculate total lines of code from request files."""
    if req.files:
        return sum(
            content.count('\n') + 1 if content else 0
            for f in req.files
            if (content := getattr(f, 'content', None))
        )
    return 0


async def validate_with_logging(request: Request, req: ValidateFullRequest, user: UserContext, endpoint: str) -> ValidateResponse:
    """Validate with metrics logging."""
    start_time = time.time()
    status = "success"
    error_type = None
    response = None
    
    try:
        response = validate_with_tree_sitter_internal(req)
        if response.verdict == "unknown" and any("error" in v.rule for v in response.violations):
            status = "error"
            error_type = "validation_error"
        return response
    except asyncio.TimeoutError:
        status = "timeout"
        error_type = "timeout"
        raise
    except Exception as e:
        status = "error"
        error_type = type(e).__name__
        raise
    finally:
        # Log request metrics (fire-and-forget)
        # Always log when DATABASE_URL is configured, even for admin keys
        if DATABASE_URL:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Extract rule_ids from violations
            rule_ids = []
            findings_count = 0
            if response and hasattr(response, 'violations'):
                rule_ids = [v.rule for v in response.violations]
                findings_count = len(response.violations)
            
            # Calculate lines of code examined
            lines_of_code = _calculate_lines_of_code(req)
            
            asyncio.create_task(
                db.log_api_request(
                    token_id=user.token_id,  # May be None for admin keys
                    endpoint=endpoint,
                    language=_detect_languages_for_logging(req, response),
                    files_count=_detect_files_count_for_logging(req, response),
                    response_time_ms=response_time_ms,
                    findings_count=findings_count,
                    status=status,
                    error_type=error_type,
                    lines_of_code_examined=lines_of_code,
                    is_admin_key=user.is_admin,
                    request_id=getattr(request.state, "request_id", None),
                    client_ip=getattr(request.state, "client_ip", None),
                    user_agent=getattr(request.state, "user_agent", None),
                    token_hash=db.hash_token(user.api_key) if getattr(user, "api_key", None) else None,
                )
            )


def validate_with_tree_sitter_internal(req: ValidateFullRequest):
    """Internal validation logic."""
    start_time = time.time()
    
    if not TREE_SITTER_AVAILABLE:
        return ValidateResponse(
            verdict="unknown",
            violations=[{
                "id": "engine-error-001",
                "rule": "system_error",
                "severity": "high", 
                "explain": "Tree-sitter engine not available",
                "locations": []
            }],
            metrics={"check_ms": int((time.time() - start_time) * 1000)}
        )
    
    original_cwd = None
    try:
        # Add server directory to Python path
        server_dir = os.path.dirname(os.path.dirname(__file__))
        if server_dir not in sys.path:
            sys.path.insert(0, server_dir)
        
        # Check if files content was provided (remote validation mode)
        if req.files:
            from engine.validation import validate_files_content
            
            # Convert FileContent models to dicts for the engine
            files_data = [
                {
                    'path': f.path,
                    'content': f.content,
                    'language': f.language
                }
                for f in req.files
            ]
            
            result = validate_files_content(
                files_data,
                profile=req.profile,
                enable_project_graph=req.enable_project_graph
            )
        else:
            # Local validation mode - read files from disk
            from engine.validation import validate_paths
            
            # Determine paths to validate
            if req.paths:
                paths_to_validate = req.paths
            elif req.repo_root:
                paths_to_validate = [req.repo_root]
            else:
                return ValidateResponse(
                    verdict="unknown",
                    violations=[{
                        "id": "request-error-001",
                        "rule": "system_error", 
                        "severity": "high",
                        "explain": "Either paths, repo_root, or files must be provided",
                        "locations": []
                    }],
                    metrics={"check_ms": int((time.time() - start_time) * 1000)}
                )
            
            # Change to project root for validation
            original_cwd = os.getcwd()
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            os.chdir(root_dir)
            
            result = validate_paths(
                paths_to_validate, 
                req.languages, 
                req.profile,
                req.enable_project_graph
            )
        
        # Convert findings to violations format for extension compatibility
        violations = []
        for finding in result.get("findings", []):
            violation = {
                "id": f"ts-{abs(hash(finding['rule_id'] + finding['file_path'] + str(finding['start_byte'])))}",
                "rule": finding["rule_id"],
                "severity": "high" if finding["severity"] == "error" else "medium",
                "explain": finding["message"],
                "locations": [f"{finding['file_path']}:{finding['range']['startLine']}:{finding['range']['startCol']}-{finding['range']['endLine']}:{finding['range']['endCol']}"],
                "priority": finding.get("priority", "P1")  # Include priority for UI categorization
            }
            
            violations.append(violation)
        
        # Determine verdict
        if not violations:
            verdict = "safe"
        elif any(v["severity"] == "high" for v in violations):
            verdict = "risky"
        else:
            verdict = "risky"
        
        # Create response
        engine_language_keys: List[str] = []
        try:
            lang_stats = result.get("metrics", {}).get("languages", {})
            if isinstance(lang_stats, dict):
                engine_language_keys = sorted([str(k) for k in lang_stats.keys()])
        except Exception:
            engine_language_keys = []

        return ValidateResponse(
            verdict=verdict,
            violations=violations,
            metrics={
                "check_ms": int((time.time() - start_time) * 1000),
                "files_checked": result.get("files_scanned", 0),
                "total_files": result.get("files_scanned", 0),
                "detectors_ms": int(result.get("metrics", {}).get("rules_ms", 0)),
                "detectors_count": len(violations),
                "snapshot_id": req.snapshot_id or "tree-sitter-direct",
                "whole_repo_mode": True,
                "debug_detector_findings_count": len(result.get("findings", [])),
                "debug_violations_count": len(violations),
                "languages": engine_language_keys,
            }
        )
        
    except Exception as e:
        return ValidateResponse(
            verdict="unknown", 
            violations=[{
                "id": "engine-error-002",
                "rule": "system_error",
                "severity": "high",
                "explain": f"Tree-sitter engine error: {str(e)}",
                "locations": []
            }],
            metrics={"check_ms": int((time.time() - start_time) * 1000)}
        )
    finally:
        # Restore original directory if it was changed
        if original_cwd:
            try:
                os.chdir(original_cwd)
            except:
                pass

@app.get("/snapshots", response_model=List[SnapshotInfo])
def list_snapshots(
    user: UserContext = Depends(get_current_user)
):
    """List available snapshots for the extension."""
    try:
        storage = get_storage()
        snapshots = storage.list_snapshots()
        return [
            SnapshotInfo(
                snapshot_id=s.snapshot_id,
                root_path=s.root_path,
                created_at=s.created_at,
                file_count=s.file_count,
                bytes_indexed=s.bytes_indexed
            )
            for s in snapshots
        ]
    except Exception:
        return []

@app.get("/storage/stats")
def get_storage_stats(
    user: UserContext = Depends(get_current_user)
):
    """Get storage statistics."""
    try:
        storage = get_storage()
        return storage.get_stats()
    except Exception:
        return {"error": "Storage not available"}

def cli():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    cli()

