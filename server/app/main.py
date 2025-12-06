from __future__ import annotations
import time
import sys
import os
import importlib.util
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .models import (
    ValidateResponse, IndexRequest, IndexResult, ValidateFullRequest, SnapshotInfo,
    AutofixRequest, AutofixResponse
)
from .storage import get_storage

# LLM Proxy Models
class LlmProxyRequest(BaseModel):
    systemPrompt: str | None = None
    userPrompt: str
    maxTokens: int = 2000

class LlmProxyResponse(BaseModel):
    text: str

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

app = FastAPI(title="Aspect Code — Tree-sitter Code Analysis")

# CORS for local dev (extension)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    return {"status": "ok", "engine": "tree-sitter" if TREE_SITTER_AVAILABLE else "unavailable", "timestamp": int(time.time())}

@app.post("/llm/complete", response_model=LlmProxyResponse)
def llm_complete(req: LlmProxyRequest):
    """
    LLM proxy endpoint - routes requests through backend API key.
    This prevents exposing API keys in the extension.
    """
    import httpx
    
    # Get API key from environment variable
    api_key = os.environ.get('ASPECT_CODE_LLM_API_KEY')
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="LLM service not configured. Set ASPECT_CODE_LLM_API_KEY environment variable."
        )
    
    # Get LLM config from environment (with defaults)
    model = os.environ.get('ASPECT_CODE_LLM_MODEL', 'gpt-4o-mini')
    endpoint = os.environ.get('ASPECT_CODE_LLM_ENDPOINT', 'https://api.openai.com/v1/chat/completions')
    
    # Build messages
    messages = []
    if req.systemPrompt:
        messages.append({"role": "system", "content": req.systemPrompt})
    messages.append({"role": "user", "content": req.userPrompt})
    
    try:
        # Call OpenAI API with backend key
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                endpoint,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}"
                },
                json={
                    "model": model,
                    "messages": messages,
                    "max_tokens": req.maxTokens,
                    "temperature": 0.7
                }
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"LLM API error: {response.text}"
                )
            
            data = response.json()
            if not data.get('choices') or len(data['choices']) == 0:
                raise HTTPException(status_code=500, detail="LLM returned no choices")
            
            text = data['choices'][0]['message']['content']
            return LlmProxyResponse(text=text)
            
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"LLM request failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")

@app.get("/patchlets/capabilities")
def get_patchlets_capabilities():
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
def index_repository(req: IndexRequest):
    """Index a repository for analysis."""
    from .services.indexing import index_repository as index_repo_service
    return index_repo_service(req)

@app.post("/validate", response_model=ValidateResponse)
def validate_code(req: ValidateFullRequest):
    """
    Standard validation endpoint for tree-sitter analysis.
    
    This is the main validation endpoint that should be used going forward.
    The '/validate_tree_sitter' endpoint is maintained for backward compatibility.
    """
    return validate_with_tree_sitter(req)

@app.post("/validate_tree_sitter", response_model=ValidateResponse)
def validate_with_tree_sitter(req: ValidateFullRequest):
    """Validate using the tree-sitter engine."""
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
def list_snapshots():
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
def get_storage_stats():
    """Get storage statistics."""
    try:
        storage = get_storage()
        return storage.get_stats()
    except Exception:
        return {"error": "Storage not available"}

@app.post("/autofix", response_model=AutofixResponse)
def apply_autofixes(req: AutofixRequest):
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

