import time
import sys
import os
import importlib.util
import hashlib
import asyncio
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .models import (
    ValidateResponse, IndexRequest, IndexResult, ValidateFullRequest, SnapshotInfo
)
from .storage import get_storage
from .settings import settings, DATABASE_URL
from .auth import get_current_user, UserContext
from .admin import router as admin_router
from .mcp import router as mcp_router
from .rate_limit import limiter
from . import db

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
    yield
    # Shutdown: close database pool
    await db.close_pool()


app = FastAPI(
    title="Aspect Code — Tree-sitter Code Analysis",
    lifespan=lifespan
)

# Include admin router
app.include_router(admin_router)

# Include MCP router for LLM agent tool access
app.include_router(mcp_router)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

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
    }


# --- Alpha Registration (disabled in production mode) ---
# API keys must be created manually via database.
# See server/scripts/ for admin tooling.


# Alpha registration endpoint removed - API keys created manually via database


@app.post("/index", response_model=IndexResult)
@limiter.limit(f"{settings.rate_limit}/minute")
def index_repository(
    request: Request,
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
@limiter.limit(f"{settings.rate_limit}/minute")
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
    return await validate_with_logging(req, user, "validate")

@app.post("/validate_tree_sitter", response_model=ValidateResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
async def validate_with_tree_sitter(
    request: Request,
    req: ValidateFullRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """Validate using the tree-sitter engine."""
    return await validate_with_logging(req, user, "validate_tree_sitter")


def _detect_language(req: ValidateFullRequest) -> str:
    """Detect primary language from request."""
    if req.languages:
        if len(req.languages) == 1:
            return req.languages[0]
        else:
            return "mixed"
    return "unknown"


def _estimate_files_count(req: ValidateFullRequest) -> int:
    """Estimate files to be analyzed from request."""
    if req.paths:
        return len(req.paths)
    return 0


async def validate_with_logging(req: ValidateFullRequest, user: UserContext, endpoint: str) -> ValidateResponse:
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
        if user.token_id and DATABASE_URL:
            response_time_ms = int((time.time() - start_time) * 1000)
            
            # Extract rule_ids from violations
            rule_ids = []
            findings_count = 0
            if response and hasattr(response, 'violations'):
                rule_ids = [v.rule for v in response.violations]
                findings_count = len(response.violations)
            
            asyncio.create_task(
                db.log_api_request(
                    token_id=user.token_id,
                    endpoint=endpoint,
                    repo_root=req.repo_root,
                    language=_detect_language(req),
                    files_count=_estimate_files_count(req),
                    response_time_ms=response_time_ms,
                    findings_count=findings_count,
                    rule_ids=rule_ids,
                    status=status,
                    error_type=error_type,
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
                "debug_violations_count": len(violations)
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
@limiter.limit(f"{settings.rate_limit}/minute")
def list_snapshots(
    request: Request,
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
@limiter.limit(f"{settings.rate_limit}/minute")
def get_storage_stats(
    request: Request,
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

