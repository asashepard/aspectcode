"""Repository snapshot storage with in-memory caching and optional SQLite persistence."""

from __future__ import annotations
from typing import Dict, List, Optional, Any, Set
import uuid
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
import logging
from dataclasses import dataclass, asdict

from .models import SnapshotInfo, FileIndexEntry


logger = logging.getLogger(__name__)


@dataclass
class FileSnapshot:
    """Complete snapshot of a single file."""
    path: str
    language: str
    size: int
    sha256: str
    newline: str
    content_hash: str  # Hash of the actual content for change detection
    content: str  # Actual file content for detector analysis
    ir: Dict[str, Any]  # Parsed intermediate representation
    indexed_at: str  # ISO timestamp
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileSnapshot':
        return cls(**data)


@dataclass 
class RepositorySnapshot:
    """Complete snapshot of repository state."""
    snapshot_id: str
    root_path: str
    created_at: str
    last_updated: str
    files: Dict[str, FileSnapshot]  # path -> file snapshot
    dependency_graph: Dict[str, Set[str]]  # path -> set of paths it imports from
    
    def get_info(self) -> SnapshotInfo:
        """Get summary information about this snapshot."""
        total_bytes = 0
        
        for file_snap in self.files.values():
            total_bytes += file_snap.size
        
        return SnapshotInfo(
            snapshot_id=self.snapshot_id,
            root_path=self.root_path,
            created_at=self.created_at,
            file_count=len(self.files),
            bytes_indexed=total_bytes
        )
    
    def get_files_by_language(self, language: str) -> List[FileSnapshot]:
        """Get all files of a specific language."""
        return [fs for fs in self.files.values() if fs.language == language]
    
    def get_dependencies(self, path: str) -> Set[str]:
        """Get files that the given path depends on."""
        return self.dependency_graph.get(path, set())
    
    def get_dependents(self, path: str) -> Set[str]:
        """Get files that depend on the given path."""
        dependents = set()
        for file_path, deps in self.dependency_graph.items():
            if path in deps:
                dependents.add(file_path)
        return dependents


class SnapshotStorage:
    """In-memory storage for repository snapshots with optional SQLite persistence."""
    
    def __init__(self, db_path: Optional[str] = None, enable_persistence: bool = False):
        self._snapshots: Dict[str, RepositorySnapshot] = {}
        self._lock = threading.RLock()
        self.db_path = db_path
        self.enable_persistence = enable_persistence
        
        if enable_persistence and db_path:
            self._init_db()
            self._load_from_db()
    
    def _init_db(self):
        """Initialize SQLite database schema."""
        if not self.db_path:
            return
            
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    snapshot_id TEXT PRIMARY KEY,
                    root_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    data TEXT NOT NULL  -- JSON blob
                );
                
                CREATE INDEX IF NOT EXISTS idx_snapshots_root 
                ON snapshots(root_path);
                
                CREATE INDEX IF NOT EXISTS idx_snapshots_updated 
                ON snapshots(last_updated);
            """)
            conn.commit()
        finally:
            conn.close()
    
    def _load_from_db(self):
        """Load snapshots from SQLite database into memory."""
        if not self.db_path:
            return
            
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.execute("SELECT snapshot_id, data FROM snapshots")
            for row in cursor:
                snapshot_id, data_json = row
                try:
                    data = json.loads(data_json)
                    # Reconstruct FileSnapshot objects
                    files = {}
                    for path, file_data in data.get('files', {}).items():
                        files[path] = FileSnapshot.from_dict(file_data)
                    
                    # Reconstruct dependency graph (sets need special handling)
                    dep_graph = {}
                    for path, deps_list in data.get('dependency_graph', {}).items():
                        dep_graph[path] = set(deps_list) if isinstance(deps_list, list) else deps_list
                    
                    snapshot = RepositorySnapshot(
                        snapshot_id=data['snapshot_id'],
                        root_path=data['root_path'],
                        created_at=data['created_at'],
                        last_updated=data['last_updated'],
                        files=files,
                        dependency_graph=dep_graph
                    )
                    
                    self._snapshots[snapshot_id] = snapshot
                    logger.info(f"Loaded snapshot {snapshot_id} from database")
                    
                except Exception as e:
                    logger.error(f"Failed to load snapshot {snapshot_id}: {e}")
                    
        finally:
            conn.close()
    
    def _persist_snapshot(self, snapshot: RepositorySnapshot):
        """Persist snapshot to SQLite database."""
        if not self.enable_persistence or not self.db_path:
            return
        
        # Convert to serializable format
        data = {
            'snapshot_id': snapshot.snapshot_id,
            'root_path': snapshot.root_path,
            'created_at': snapshot.created_at,
            'last_updated': snapshot.last_updated,
            'files': {path: fs.to_dict() for path, fs in snapshot.files.items()},
            'dependency_graph': {path: list(deps) for path, deps in snapshot.dependency_graph.items()}
        }
        
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT OR REPLACE INTO snapshots 
                (snapshot_id, root_path, created_at, last_updated, data)
                VALUES (?, ?, ?, ?, ?)
            """, (
                snapshot.snapshot_id,
                snapshot.root_path,
                snapshot.created_at,
                snapshot.last_updated,
                json.dumps(data)
            ))
            conn.commit()
            
        except Exception as e:
            logger.error(f"Failed to persist snapshot {snapshot.snapshot_id}: {e}")
            
        finally:
            conn.close()
    
    def create_snapshot(self, root_path: str) -> str:
        """Create a new empty snapshot."""
        with self._lock:
            snapshot_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            
            snapshot = RepositorySnapshot(
                snapshot_id=snapshot_id,
                root_path=root_path,
                created_at=now,
                last_updated=now,
                files={},
                dependency_graph={}
            )
            
            self._snapshots[snapshot_id] = snapshot
            self._persist_snapshot(snapshot)
            
            logger.info(f"Created new snapshot {snapshot_id} for {root_path}")
            return snapshot_id
    
    def get_snapshot(self, snapshot_id: str) -> Optional[RepositorySnapshot]:
        """Get snapshot by ID."""
        with self._lock:
            return self._snapshots.get(snapshot_id)
    
    def find_latest_snapshot(self, root_path: str) -> Optional[RepositorySnapshot]:
        """Find the most recent snapshot for a repository root."""
        import os
        normalized_root = os.path.normpath(root_path).lower()
        
        with self._lock:
            candidates = [
                snapshot for snapshot in self._snapshots.values()
                if os.path.normpath(snapshot.root_path).lower() == normalized_root
            ]
            if not candidates:
                logger.warning(f"No snapshot found for root: {root_path} (normalized: {normalized_root})")
                logger.info(f"Available snapshots: {[os.path.normpath(s.root_path).lower() for s in self._snapshots.values()]}")
                return None
            
            # Return the most recently created snapshot
            return max(candidates, key=lambda s: s.created_at)
    
    def update_snapshot(self, snapshot_id: str, files: Dict[str, FileSnapshot], 
                       dependency_updates: Optional[Dict[str, Set[str]]] = None) -> bool:
        """Update snapshot with new file data."""
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if not snapshot:
                return False
            
            # Update files
            snapshot.files.update(files)
            
            # Update dependency graph
            if dependency_updates:
                snapshot.dependency_graph.update(dependency_updates)
            
            # Update timestamp
            snapshot.last_updated = datetime.now(timezone.utc).isoformat()
            
            self._persist_snapshot(snapshot)
            return True
    
    def remove_files(self, snapshot_id: str, file_paths: List[str]) -> bool:
        """Remove files from snapshot."""
        with self._lock:
            snapshot = self._snapshots.get(snapshot_id)
            if not snapshot:
                return False
            
            for path in file_paths:
                snapshot.files.pop(path, None)
                snapshot.dependency_graph.pop(path, None)
                
                # Remove from other files' dependencies
                for deps in snapshot.dependency_graph.values():
                    deps.discard(path)
            
            snapshot.last_updated = datetime.now(timezone.utc).isoformat()
            self._persist_snapshot(snapshot)
            return True
    
    def list_snapshots(self, root_path: Optional[str] = None) -> List[SnapshotInfo]:
        """List all snapshots, optionally filtered by root path."""
        with self._lock:
            snapshots = []
            for snapshot in self._snapshots.values():
                if root_path is None or snapshot.root_path == root_path:
                    snapshots.append(snapshot.get_info())
            
            # Sort by last updated (newest first)
            snapshots.sort(key=lambda s: s.last_updated, reverse=True)
            return snapshots
    
    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot."""
        with self._lock:
            if snapshot_id not in self._snapshots:
                return False
            
            del self._snapshots[snapshot_id]
            
            # Remove from database
            if self.enable_persistence and self.db_path:
                conn = sqlite3.connect(self.db_path)
                try:
                    conn.execute("DELETE FROM snapshots WHERE snapshot_id = ?", (snapshot_id,))
                    conn.commit()
                finally:
                    conn.close()
            
            logger.info(f"Deleted snapshot {snapshot_id}")
            return True
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        with self._lock:
            total_files = sum(len(s.files) for s in self._snapshots.values())
            total_snapshots = len(self._snapshots)
            
            root_paths = set(s.root_path for s in self._snapshots.values())
            
            return {
                "total_snapshots": total_snapshots,
                "total_files": total_files,
                "unique_repositories": len(root_paths),
                "average_files_per_snapshot": total_files / max(total_snapshots, 1)
            }


# Global storage instance
_storage: Optional[SnapshotStorage] = None


def get_storage() -> SnapshotStorage:
    """Get global storage instance."""
    global _storage
    if _storage is None:
        # Default to in-memory only for now
        _storage = SnapshotStorage(enable_persistence=False)
    return _storage


def init_storage(db_path: Optional[str] = None, enable_persistence: bool = False):
    """Initialize global storage with custom settings."""
    global _storage
    _storage = SnapshotStorage(db_path=db_path, enable_persistence=enable_persistence)


# Legacy schema for backward compatibility (kept but unused)
LEGACY_SCHEMA = '''
CREATE TABLE IF NOT EXISTS files(
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE,
    content_hash TEXT
);
CREATE TABLE IF NOT EXISTS symbols(
    id TEXT PRIMARY KEY,
    kind TEXT,
    name TEXT,
    file TEXT,
    start INT,
    end INT
);
CREATE TABLE IF NOT EXISTS edges(
    src TEXT,
    dst TEXT,
    kind TEXT
);
CREATE INDEX IF NOT EXISTS edges_kind ON edges(kind);
CREATE TABLE IF NOT EXISTS types(
    symbol_id TEXT,
    params TEXT,
    returns TEXT,
    nullable INT
);
'''


def open_db(path: str):
    """Legacy function for backward compatibility."""
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.executescript(LEGACY_SCHEMA)
    return conn


