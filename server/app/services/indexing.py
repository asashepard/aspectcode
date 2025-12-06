"""
Indexing service for the tree-sitter engine.

This module provides a clean, normalized interface for repository indexing
that abstracts the complexity of file discovery, parsing, and storage.
"""

import time
import os
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from ..models import IndexRequest, IndexResult, FileIndexEntry
from ..utils.indexer import get_indexer, IndexStats


class IndexingService:
    """Service for indexing repositories using tree-sitter."""
    
    def __init__(self):
        self._indexer = get_indexer()
    
    def index_repository(self, request: IndexRequest) -> IndexResult:
        """
        Index a repository and return the result.
        
        Args:
            request: IndexRequest with repository path and options
            
        Returns:
            IndexResult with snapshot information and statistics
        """
        start_time = time.time()
        
        try:
            repo_root = request.get_repo_root()
            if not repo_root:
                return IndexResult(
                    snapshot_id="error-no-root",
                    file_count=0,
                    bytes_indexed=0,
                    took_ms=int((time.time() - start_time) * 1000),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    dependency_count=0,
                    skipped_files=0,
                    parse_errors=1
                )
            
            # Validate repository path exists
            if not os.path.exists(repo_root):
                return IndexResult(
                    snapshot_id="error-path-not-found",
                    file_count=0,
                    bytes_indexed=0,
                    took_ms=int((time.time() - start_time) * 1000),
                    processing_time_ms=int((time.time() - start_time) * 1000),
                    dependency_count=0,
                    skipped_files=0,
                    parse_errors=1
                )
            
            # Perform indexing
            snapshot_id, stats = self._indexer.build_index(request)
            
            took_ms = int((time.time() - start_time) * 1000)
            
            return IndexResult(
                snapshot_id=snapshot_id,
                file_count=stats.files_processed,
                bytes_indexed=stats.bytes_processed,
                took_ms=took_ms,
                processing_time_ms=took_ms,  # Extension compatibility
                dependency_count=0,  # TODO: implement dependency counting
                skipped_files=stats.files_skipped,
                parse_errors=stats.parse_errors
            )
            
        except Exception as e:
            return IndexResult(
                snapshot_id=f"error-{int(time.time())}",
                file_count=0,
                bytes_indexed=0,
                took_ms=int((time.time() - start_time) * 1000),
                processing_time_ms=int((time.time() - start_time) * 1000),
                dependency_count=0,
                skipped_files=0,
                parse_errors=1
            )
    
    def index_files(self, repo_root: str, file_paths: List[str]) -> IndexResult:
        """
        Index specific files within a repository.
        
        Args:
            repo_root: Repository root path
            file_paths: List of file paths to index
            
        Returns:
            IndexResult with indexing statistics
        """
        # Create file entries for the specified files
        file_entries = []
        for file_path in file_paths:
            full_path = Path(file_path)
            
            if full_path.is_absolute():
                rel_path = str(full_path.relative_to(Path(repo_root)))
            else:
                rel_path = file_path
                full_path = Path(repo_root) / file_path
            
            if full_path.exists():
                # Create basic file entry
                try:
                    stat = full_path.stat()
                    file_entry = FileIndexEntry(
                        path=rel_path,
                        language="python",  # TODO: Detect language properly
                        size=stat.st_size,
                        sha256="placeholder",  # Will be computed during indexing
                        newline="LF"
                    )
                    file_entries.append(file_entry)
                except OSError:
                    continue  # Skip files that can't be accessed
        
        # Create request with specific files
        request = IndexRequest(
            repo_root=repo_root,
            files=file_entries
        )
        
        return self.index_repository(request)
    
    def get_indexing_status(self, snapshot_id: str) -> Dict[str, Any]:
        """
        Get status information for an indexing operation.
        
        Args:
            snapshot_id: The snapshot identifier
            
        Returns:
            Dictionary with status information
        """
        try:
            storage = self._indexer.storage
            snapshot = storage.get_snapshot(snapshot_id)
            
            if snapshot:
                return {
                    "status": "completed",
                    "snapshot_id": snapshot_id,
                    "file_count": snapshot.file_count,
                    "bytes_indexed": snapshot.bytes_indexed,
                    "created_at": snapshot.created_at
                }
            else:
                return {
                    "status": "not_found",
                    "snapshot_id": snapshot_id
                }
                
        except Exception as e:
            return {
                "status": "error",
                "snapshot_id": snapshot_id,
                "error": str(e)
            }


# Global service instance
_indexing_service = None


def get_indexing_service() -> IndexingService:
    """Get the global indexing service instance."""
    global _indexing_service
    if _indexing_service is None:
        _indexing_service = IndexingService()
    return _indexing_service


def index_repository(request: IndexRequest) -> IndexResult:
    """Convenience function to index a repository."""
    service = get_indexing_service()
    return service.index_repository(request)


def index_files(repo_root: str, file_paths: List[str]) -> IndexResult:
    """Convenience function to index specific files."""
    service = get_indexing_service()
    return service.index_files(repo_root, file_paths)


def get_indexing_status(snapshot_id: str) -> Dict[str, Any]:
    """Convenience function to get indexing status."""
    service = get_indexing_service()
    return service.get_indexing_status(snapshot_id)

