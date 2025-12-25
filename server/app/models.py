from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel

# ---- Core Models for Tree-sitter Engine ----

class Violation(BaseModel):
    id: str
    rule: str
    severity: Literal["low","medium","high"] = "medium"
    explain: str
    locations: List[str] = []

class ValidateResponse(BaseModel):
    verdict: Literal["safe","risky","unknown"]
    violations: List[Violation] = []
    metrics: Dict[str, Any] = {}

# ---- Indexing Models ----

class FileIndexEntry(BaseModel):
    """Metadata for a file in the repository index."""
    path: str  # Relative path from repo root
    language: Literal["python", "typescript", "javascript", "other"] = "other"
    size: int  # File size in bytes
    sha256: str  # Content hash
    newline: str = "LF"  # Newline style

class IndexRequest(BaseModel):
    """Request to build or update repository index."""
    repo_root: Optional[str] = None  # Repository root path
    root: Optional[str] = None  # Alternative field name for compatibility
    files: Optional[List[FileIndexEntry]] = None  # Specific files to index (optional)
    include_patterns: Optional[List[str]] = None  # File patterns to include
    exclude_patterns: Optional[List[str]] = None  # File patterns to exclude
    respect_gitignore: bool = True
    max_bytes: int = 5_000_000  # Skip files larger than this
    
    def get_repo_root(self) -> Optional[str]:
        """Get repository root from either field name."""
        return self.repo_root or self.root

class IndexResult(BaseModel):
    """Result of repository indexing operation."""
    snapshot_id: str  # Unique identifier for this snapshot
    file_count: int  # Number of files indexed
    bytes_indexed: int  # Total bytes processed
    took_ms: int  # Indexing time in milliseconds
    processing_time_ms: int  # Alias for took_ms (for extension compatibility)
    dependency_count: int = 0  # Number of dependencies found
    skipped_files: int = 0  # Files skipped (too large, binary, etc.)
    parse_errors: int = 0  # Files that failed parsing

class ValidateFullRequest(BaseModel):
    """Request for full repository validation using tree-sitter."""
    snapshot_id: Optional[str] = None  # Snapshot to validate against
    repo_root: Optional[str] = None  # Primary field name for repository root
    paths: Optional[List[str]] = None  # Optional scope filter (files or directories)
    languages: Optional[List[str]] = None  # Languages to process (default: all)
    modes: Optional[List[str]] = None  # Validation modes (deprecated)
    profile: Optional[str] = None  # Rule profile to use (default: alpha_default)
    enable_project_graph: bool = True  # Enable dependency graph for Tier 2 rules (default: True)

class DeltaRequest(BaseModel):
    """Request to apply file changes to existing snapshot."""
    snapshot_id: str  # Snapshot to update
    root: str  # Repository root path
    changed_files: Optional[List[FileIndexEntry]] = None  # Files that changed
    removed_files: Optional[List[str]] = None  # Files that were deleted

class SnapshotInfo(BaseModel):
    """Information about a repository snapshot."""
    snapshot_id: str
    root_path: str  # Repository root path
    created_at: str  # ISO timestamp
    file_count: int
    bytes_indexed: int

