"""Repository indexing utilities for walking files and building snapshots."""

import os
import time
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from pathlib import Path
import fnmatch
import subprocess
from dataclasses import dataclass

from ..models import IndexRequest, IndexResult, FileIndexEntry, DeltaRequest
from ..storage import (
    get_storage, RepositorySnapshot, FileSnapshot
)
from .parsing import (
    get_parser, detect_language, compute_file_hash, detect_newline_style
)


logger = logging.getLogger(__name__)


@dataclass
class IndexStats:
    """Statistics from indexing operation."""
    files_processed: int = 0
    bytes_processed: int = 0
    files_skipped: int = 0
    parse_errors: int = 0
    elapsed_ms: int = 0


class RepositoryIndexer:
    """Handles repository scanning and snapshot building."""
    
    def __init__(self):
        self.storage = get_storage()
    
    def build_index(self, request: IndexRequest) -> Tuple[str, IndexStats]:
        """Build a complete repository index."""
        start_time = time.time()
        stats = IndexStats()
        
        logger.info(f"Starting index build for {request.get_repo_root()}")
        
        try:
            # Create new snapshot
            snapshot_id = self.storage.create_snapshot(request.get_repo_root())
            
            # Get files to index
            if request.files:
                files_to_process = request.files
                logger.info(f"Using provided file list: {len(files_to_process)} files")
            else:
                files_to_process = self._discover_files(request)
                logger.info(f"Discovered {len(files_to_process)} files")
            
            # Process files in batches for better performance
            file_snapshots: Dict[str, FileSnapshot] = {}
            dependency_graph: Dict[str, Set[str]] = {}
            
            batch_size = 50
            for i in range(0, len(files_to_process), batch_size):
                batch = files_to_process[i:i + batch_size]
                batch_results = self._process_file_batch(
                    request.get_repo_root(), batch, request.max_bytes
                )
                
                for file_snap, deps in batch_results:
                    if file_snap:
                        file_snapshots[file_snap.path] = file_snap
                        if deps:
                            dependency_graph[file_snap.path] = deps
                        stats.files_processed += 1
                        stats.bytes_processed += file_snap.size
                    else:
                        stats.files_skipped += 1
            
            # Update snapshot with all files
            self.storage.update_snapshot(snapshot_id, file_snapshots, dependency_graph)
            
            stats.elapsed_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"Index build complete: {stats.files_processed} files, "
                f"{stats.bytes_processed} bytes, {stats.elapsed_ms}ms"
            )
            
            return snapshot_id, stats
            
        except Exception as e:
            logger.error(f"Index build failed: {e}")
            raise
    
    def apply_delta(self, request: DeltaRequest) -> Tuple[str, IndexStats]:
        """Apply file changes to existing snapshot."""
        start_time = time.time()
        stats = IndexStats()
        
        logger.info(f"Applying delta to snapshot {request.snapshot_id}")
        
        try:
            # Check if snapshot exists
            snapshot = self.storage.get_snapshot(request.snapshot_id)
            if not snapshot:
                raise ValueError(f"Snapshot {request.snapshot_id} not found")
            
            # Remove deleted files
            if request.removed_files:
                self.storage.remove_files(request.snapshot_id, request.removed_files)
                logger.info(f"Removed {len(request.removed_files)} files")
            
            # Process changed files
            if request.changed_files:
                batch_results = self._process_file_batch(
                    request.repo_root, request.changed_files, max_bytes=5_000_000
                )
                
                file_snapshots: Dict[str, FileSnapshot] = {}
                dependency_graph: Dict[str, Set[str]] = {}
                
                for file_snap, deps in batch_results:
                    if file_snap:
                        file_snapshots[file_snap.path] = file_snap
                        if deps:
                            dependency_graph[file_snap.path] = deps
                        stats.files_processed += 1
                        stats.bytes_processed += file_snap.size
                    else:
                        stats.files_skipped += 1
                
                # Update snapshot
                self.storage.update_snapshot(request.snapshot_id, file_snapshots, dependency_graph)
            
            stats.elapsed_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"Delta applied: {stats.files_processed} files updated, "
                f"{stats.elapsed_ms}ms"
            )
            
            return request.snapshot_id, stats
            
        except Exception as e:
            logger.error(f"Delta application failed: {e}")
            raise
    
    def _discover_files(self, request: IndexRequest) -> List[FileIndexEntry]:
        """Discover files in repository using git and filesystem walk."""
        root_path = Path(request.get_repo_root())
        files = []
        
        # Try to use git to get file list (respects .gitignore)
        if request.respect_gitignore:
            try:
                git_files = self._get_git_tracked_files(request.get_repo_root())
                if git_files:
                    logger.info(f"Using git file list: {len(git_files)} files")
                    for rel_path in git_files:
                        full_path = root_path / rel_path
                        if full_path.exists() and self._should_include_file(rel_path, request):
                            files.append(self._create_file_entry(full_path, rel_path))
                    return files
            except Exception as e:
                logger.warning(f"Git file discovery failed, falling back to filesystem: {e}")
        
        # Fall back to filesystem walk with directory pruning
        logger.info("Using filesystem walk for file discovery")
        
        # Directories to skip entirely (prune from walk)
        skip_dirs = {
            '.git', 'node_modules', '.venv', 'venv', 'env', '__pycache__',
            'site-packages', 'dist-packages', '.pytest_cache', '.mypy_cache',
            '.tox', 'htmlcov', 'coverage', '.eggs', 'build', 'dist', 'target',
            '.next', '.turbo', '.cache', 'e2e', 'playwright', 'cypress'
        }
        
        for dirpath, dirnames, filenames in os.walk(root_path):
            # Prune directories in-place to avoid walking into them
            dirnames[:] = [d for d in dirnames if d not in skip_dirs and not d.endswith('.egg-info')]
            
            for filename in filenames:
                full_path = Path(dirpath) / filename
                try:
                    rel_path = str(full_path.relative_to(root_path)).replace(os.sep, '/')
                    if self._should_include_file(rel_path, request):
                        files.append(self._create_file_entry(full_path, rel_path))
                except (ValueError, OSError) as e:
                    logger.debug(f"Skipping file {full_path}: {e}")
                    continue
        
        return files
    
    def _get_git_tracked_files(self, repo_root: str) -> List[str]:
        """Get list of tracked files from git."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return [line.strip() for line in result.stdout.splitlines() if line.strip()]
            else:
                logger.warning(f"git ls-files failed: {result.stderr}")
                return []
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
            logger.warning(f"Git command failed: {e}")
            return []
    
    def _should_include_file(self, rel_path: str, request: IndexRequest) -> bool:
        """Check if file should be included in index."""
        # Directories to always skip (check path components)
        skip_dirs = {
            '.git', 'node_modules', '.venv', 'venv', 'env', '__pycache__',
            'site-packages', 'dist-packages', '.pytest_cache', '.mypy_cache',
            '.tox', 'htmlcov', 'coverage', '.eggs', 'build', 'dist', 'target',
            '.next', '.turbo', '.cache', 'e2e', 'playwright', 'cypress'
        }
        
        # Quick check: if any path component is in skip_dirs, exclude it
        path_parts = rel_path.replace('\\', '/').split('/')
        for part in path_parts[:-1]:  # Check all directories (not the filename)
            if part in skip_dirs or part.endswith('.egg-info'):
                return False
        
        # Skip common ignore file patterns
        ignore_patterns = [
            "*.pyc", "*.pyo", ".coverage", "coverage.xml",
            "*.log", "*.tmp", "*.swp", ".DS_Store", "Thumbs.db"
        ]
        
        # Add user-specified exclude patterns
        if request.exclude_patterns:
            ignore_patterns.extend(request.exclude_patterns)
        
        # Check against ignore patterns (file-level only now)
        filename = path_parts[-1] if path_parts else rel_path
        for pattern in ignore_patterns:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return False
        
        # Check include patterns if specified
        if request.include_patterns:
            included = False
            for pattern in request.include_patterns:
                if fnmatch.fnmatch(rel_path, pattern):
                    included = True
                    break
            if not included:
                return False
        
        # For MVP, focus on Python files primarily
        language = detect_language(rel_path)
        if language not in ["python", "typescript", "javascript"]:
            # Skip non-code files for now
            return False
        
        return True
    
    def _create_file_entry(self, full_path: Path, rel_path: str) -> FileIndexEntry:
        """Create file index entry from path."""
        try:
            stat = full_path.stat()
            size = stat.st_size
            
            # Read file to compute hash and detect newlines
            try:
                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                sha256 = compute_file_hash(content)
                newline = detect_newline_style(content)
            except (UnicodeDecodeError, IOError):
                # Binary file or read error - create entry but mark for skipping
                sha256 = "binary"
                newline = "LF"
            
            return FileIndexEntry(
                path=rel_path,
                language=detect_language(rel_path),
                size=size,
                sha256=sha256,
                newline=newline
            )
            
        except OSError as e:
            logger.warning(f"Failed to stat file {full_path}: {e}")
            # Return a minimal entry
            return FileIndexEntry(
                path=rel_path,
                language="other",
                size=0,
                sha256="error",
                newline="LF"
            )
    
    def _process_file_batch(
        self, root: str, file_entries: List[FileIndexEntry], max_bytes: int
    ) -> List[Tuple[Optional[FileSnapshot], Optional[Set[str]]]]:
        """Process a batch of files and extract their IR."""
        results = []
        
        for entry in file_entries:
            try:
                result = self._process_single_file(root, entry, max_bytes)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to process file {entry.path}: {e}")
                results.append((None, None))
        
        return results
    
    def _process_single_file(
        self, root: str, entry: FileIndexEntry, max_bytes: int
    ) -> Tuple[Optional[FileSnapshot], Optional[Set[str]]]:
        """Process a single file and extract its IR."""
        # Skip large files
        if entry.size > max_bytes:
            logger.debug(f"Skipping large file {entry.path}: {entry.size} bytes")
            return None, None
        
        # Skip binary files
        if entry.sha256 == "binary":
            logger.debug(f"Skipping binary file {entry.path}")
            return None, None
        
        # Read file content
        full_path = Path(root) / entry.path
        try:
            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except (IOError, OSError) as e:
            logger.warning(f"Failed to read {entry.path}: {e}")
            return None, None
        
        # Parse file using appropriate parser
        parser = get_parser(entry.language)
        ir = parser.summarize(str(full_path), content)
        
        # Extract dependencies from imports
        dependencies = self._extract_dependencies(entry.path, ir, root)
        
        # Create file snapshot
        snapshot = FileSnapshot(
            path=entry.path,
            language=entry.language,
            size=entry.size,
            sha256=entry.sha256,
            newline=entry.newline,
            content_hash=compute_file_hash(content),
            content=content,  # Store actual content for detector analysis
            ir=ir,
            indexed_at=time.time()
        )
        
        return snapshot, dependencies
    
    def _extract_dependencies(self, file_path: str, ir: Dict[str, Any], root: str) -> Set[str]:
        """Extract file dependencies from IR imports."""
        dependencies = set()
        
        if "imports" not in ir:
            return dependencies
        
        root_path = Path(root)
        file_dir = (root_path / file_path).parent
        
        for import_info in ir["imports"]:
            if import_info.get("type") == "from_import":
                # Handle relative imports
                module = import_info.get("module", "")
                if module.startswith("."):
                    # Relative import - resolve to actual path
                    dep_path = self._resolve_relative_import(file_dir, module, root_path)
                    if dep_path:
                        dependencies.add(dep_path)
                else:
                    # Absolute import - try to find in project
                    dep_path = self._resolve_absolute_import(module, root_path)
                    if dep_path:
                        dependencies.add(dep_path)
            
            elif import_info.get("type") == "import":
                # Direct module import
                module = import_info.get("module", "")
                dep_path = self._resolve_absolute_import(module, root_path)
                if dep_path:
                    dependencies.add(dep_path)
        
        return dependencies
    
    def _resolve_relative_import(self, file_dir: Path, module: str, root_path: Path) -> Optional[str]:
        """Resolve relative import to file path."""
        try:
            # Count leading dots to determine level
            level = 0
            for char in module:
                if char == '.':
                    level += 1
                else:
                    break
            
            # Start from appropriate directory
            current_dir = file_dir
            for _ in range(level - 1):
                current_dir = current_dir.parent
                if current_dir < root_path:
                    return None
            
            # Add module path
            remaining = module[level:]
            if remaining:
                target_path = current_dir / remaining.replace('.', os.sep)
            else:
                target_path = current_dir
            
            # Check for .py file or package
            candidates = [
                target_path.with_suffix('.py'),
                target_path / '__init__.py'
            ]
            
            for candidate in candidates:
                if candidate.exists() and candidate.is_relative_to(root_path):
                    return str(candidate.relative_to(root_path)).replace(os.sep, '/')
            
            return None
            
        except (ValueError, OSError):
            return None
    
    def _resolve_absolute_import(self, module: str, root_path: Path) -> Optional[str]:
        """Resolve absolute import to file path within project."""
        try:
            # Convert module path to file path
            module_path = root_path / module.replace('.', os.sep)
            
            # Check for .py file or package
            candidates = [
                module_path.with_suffix('.py'),
                module_path / '__init__.py'
            ]
            
            for candidate in candidates:
                if candidate.exists() and candidate.is_relative_to(root_path):
                    return str(candidate.relative_to(root_path)).replace(os.sep, '/')
            
            return None
            
        except (ValueError, OSError):
            return None


# Global indexer instance
_indexer: Optional[RepositoryIndexer] = None


def get_indexer() -> RepositoryIndexer:
    """Get global indexer instance."""
    global _indexer
    if _indexer is None:
        _indexer = RepositoryIndexer()
    return _indexer

