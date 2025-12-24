import time
import sys
import os
import importlib.util
import hashlib
from typing import Dict, Any, List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Depends, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from .models import (
    ValidateResponse, IndexRequest, IndexResult, ValidateFullRequest, SnapshotInfo,
    AutofixRequest, AutofixResponse
)
from .storage import get_storage
from .settings import settings, DATABASE_URL
from .auth import get_current_user, UserContext
from .admin import router as admin_router
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

# Rate limiter setup
# Uses API key if available, otherwise falls back to IP address
def get_rate_limit_key(request: Request) -> str:
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
    }


# --- Alpha Registration (disabled in production mode) ---
# API keys must be created manually via database.
# See server/scripts/ for admin tooling.


# Alpha registration endpoint removed - API keys created manually via database


@app.get("/patchlets/capabilities")
@limiter.limit(f"{settings.rate_limit}/minute")
def get_patchlets_capabilities(
    request: Request,
    user: UserContext = Depends(get_current_user)
):
    """Get capabilities for patchlet fixes."""
    from engine.profiles import AUTO_FIX_V1_RULE_IDS
    
    # Return the list of auto-fixable rules with metadata
    fixable_rules = [
        {
            "rule": rule_id,
            "fixable": True,
            "safe": True
        }
        for rule_id in AUTO_FIX_V1_RULE_IDS
    ]
    
    return {
        "language": "python",
        "fixable_rules": fixable_rules
    }

@app.post("/index", response_model=IndexResult)
@limiter.limit(f"{settings.rate_limit}/minute")
def index_repository(
    request: Request,
    req: IndexRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """Index a repository for analysis."""
    from .services.indexing import index_repository as index_repo_service
    return index_repo_service(req)

@app.post("/validate", response_model=ValidateResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
def validate_code(
    request: Request,
    req: ValidateFullRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """
    Standard validation endpoint for tree-sitter analysis.
    
    This is the main validation endpoint that should be used going forward.
    The '/validate_tree_sitter' endpoint is maintained for backward compatibility.
    """
    return validate_with_tree_sitter_internal(req)

@app.post("/validate_tree_sitter", response_model=ValidateResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
def validate_with_tree_sitter(
    request: Request,
    req: ValidateFullRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """Validate using the tree-sitter engine."""
    return validate_with_tree_sitter_internal(req)

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
                "locations": [],
                "fixable": False
            }],
            metrics={"check_ms": int((time.time() - start_time) * 1000)}
        )
    
    try:
        # Import validation service
        from engine.validation import validate_paths
        
        # Add server directory to Python path
        server_dir = os.path.dirname(os.path.dirname(__file__))
        if server_dir not in sys.path:
            sys.path.insert(0, server_dir)
        
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
                    "explain": "Either paths or repo_root must be provided",
                    "locations": [],
                    "fixable": False
                }],
                metrics={"check_ms": int((time.time() - start_time) * 1000)}
            )
        
        # Change to project root for validation
        original_cwd = os.getcwd()
        root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        os.chdir(root_dir)
        
        try:
            # Run validation using the clean service
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
                    "fixable": bool(finding.get("autofix")),
                    "priority": finding.get("priority", "P1")  # Include priority for UI categorization
                }
                
                # Add suggested patchlet if autofix available
                if finding.get("autofix"):
                    patchlet_mapping = {
                        "mut.default_mutable_arg": "none_guard",
                        "lang.ts_loose_equality": "strict_equality",
                        "func.async_mismatch.await_in_sync": "manual_async_fix"
                    }
                    violation["suggested_patchlet"] = patchlet_mapping.get(
                        finding["rule_id"], "generic_fix"
                    )
                
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
            
        finally:
            # Always restore original directory
            os.chdir(original_cwd)
        
    except Exception as e:
        # Restore directory on error
        try:
            os.chdir(original_cwd)
        except:
            pass
            
        return ValidateResponse(
            verdict="unknown", 
            violations=[{
                "id": "engine-error-002",
                "rule": "system_error",
                "severity": "high",
                "explain": f"Tree-sitter engine error: {str(e)}",
                "locations": [],
                "fixable": False
            }],
            metrics={"check_ms": int((time.time() - start_time) * 1000)}
        )

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

@app.post("/autofix", response_model=AutofixResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
def apply_autofixes(
    request: Request,
    req: AutofixRequest = Body(...),
    user: UserContext = Depends(get_current_user)
):
    """Apply automatic fixes to findings."""
    print(f"[DEBUG] Autofix endpoint hit! repo_root={req.repo_root}")
    
    from .services.autofix import get_autofix_service
    autofix_service = get_autofix_service()
    
    try:
        return autofix_service.apply_autofixes(req)
    except Exception as e:
        print(f"[ERROR] Autofix failed: {e}")
        import traceback
        traceback.print_exc()
        return AutofixResponse(
            fixes_applied=0,
            files_changed=0,
            took_ms=0
        )

def cli():
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

if __name__ == "__main__":
    cli()

