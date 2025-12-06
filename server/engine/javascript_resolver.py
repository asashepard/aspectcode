"""
JavaScript/Node.js module resolver for import graph analysis.

This module provides resolution of JavaScript imports to files/modules, handling:
- ES6 imports (import/export)
- CommonJS (require/module.exports)
- Relative and absolute imports
- Node.js built-in modules
- node_modules package resolution
"""

import os
import json
from dataclasses import dataclass
from typing import Optional, List, Dict, Set
from pathlib import Path


@dataclass(frozen=True)
class ResolveResult:
    """Result of resolving an import specifier."""
    module: str              # canonical module name, e.g., "pkg/sub/mod"
    file_path: Optional[str] # resolved file path if it maps to a file/module
    kind: str                # "module_file"|"package_main"|"builtin"|"third_party"|"missing"
    meta: dict               # extra info (search_path, tried_paths, etc.)


# Node.js built-in modules (core modules)
NODE_BUILTIN_MODULES = {
    'assert', 'buffer', 'child_process', 'cluster', 'crypto', 'dgram', 'dns',
    'domain', 'events', 'fs', 'http', 'https', 'net', 'os', 'path', 'punycode',
    'querystring', 'readline', 'repl', 'stream', 'string_decoder', 'timers',
    'tls', 'tty', 'url', 'util', 'v8', 'vm', 'zlib', 'process', 'console',
    # Node 12+ modules
    'worker_threads', 'perf_hooks', 'async_hooks', 'inspector', 'trace_events',
    # Node 14+ modules
    'wasi', 'diagnostics_channel',
    # Node 16+ modules
    'readline/promises', 'stream/promises', 'timers/promises', 'dns/promises',
    # Node 18+ modules
    'node:test', 'node:util',
    # Prefixed versions
    'node:assert', 'node:buffer', 'node:child_process', 'node:cluster', 
    'node:crypto', 'node:dgram', 'node:dns', 'node:domain', 'node:events',
    'node:fs', 'node:http', 'node:https', 'node:net', 'node:os', 'node:path',
    'node:querystring', 'node:readline', 'node:repl', 'node:stream',
    'node:string_decoder', 'node:timers', 'node:tls', 'node:tty', 'node:url',
    'node:util', 'node:v8', 'node:vm', 'node:zlib', 'node:process', 'node:console'
}


class JavaScriptResolver:
    """Resolves JavaScript import specifiers to modules and files."""
    
    def __init__(self, project_roots: List[str], extra_paths: Optional[List[str]] = None):
        """
        Initialize resolver with project roots and optional extra paths.
        
        Args:
            project_roots: List of directories to search for project modules
            extra_paths: Additional paths to search
        """
        self.project_roots = [os.path.abspath(root) for root in project_roots]
        self.extra_paths = extra_paths or []
        
        # Cache for performance
        self._canonical_cache: Dict[str, Optional[str]] = {}
        self._resolve_cache: Dict[tuple, ResolveResult] = {}
        self._package_json_cache: Dict[str, dict] = {}
    
    def canonical_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Compute canonical module name for a JavaScript file.
        
        Args:
            file_path: Absolute path to a JavaScript file
            
        Returns:
            Canonical module name or None if not in project
        """
        file_path = os.path.abspath(file_path)
        
        if file_path in self._canonical_cache:
            return self._canonical_cache[file_path]
        
        result = None
        
        # Try each project root
        for root in self.project_roots:
            if file_path.startswith(root + os.sep) or file_path == root:
                rel_path = os.path.relpath(file_path, root)
                
                # Convert to module name (remove extension)
                module_path = rel_path.replace(os.sep, '/')
                
                # Remove extensions
                for ext in ['.js', '.jsx', '.mjs', '.cjs']:
                    if module_path.endswith(ext):
                        module_path = module_path[:-len(ext)]
                        break
                
                # Remove /index suffix
                if module_path.endswith('/index'):
                    module_path = module_path[:-6]
                
                result = module_path
                break
        
        self._canonical_cache[file_path] = result
        return result
    
    def resolve(self, from_file: str, module: str, imported_names: Optional[List[str]] = None) -> ResolveResult:
        """
        Resolve an import specifier to a module/file.
        
        Args:
            from_file: Absolute path to file containing the import
            module: Module specifier (e.g., "lodash", "./utils", "../config")
            imported_names: Names being imported (for ESM from imports)
            
        Returns:
            ResolveResult with resolution information
        """
        cache_key = (from_file, module, tuple(imported_names or []))
        if cache_key in self._resolve_cache:
            return self._resolve_cache[cache_key]
        
        result = self._resolve_uncached(from_file, module, imported_names)
        self._resolve_cache[cache_key] = result
        return result
    
    def _resolve_uncached(self, from_file: str, module: str, imported_names: Optional[List[str]]) -> ResolveResult:
        """Perform uncached resolution."""
        tried_paths = []
        
        # Check if it's a Node.js built-in module
        if self._is_builtin(module):
            return ResolveResult(
                module=module,
                file_path=None,
                kind="builtin",
                meta={"builtin": True}
            )
        
        # Relative import (starts with ./ or ../)
        if module.startswith('./') or module.startswith('../'):
            result = self._resolve_relative(from_file, module, tried_paths)
            if result:
                return result
        
        # Absolute/package import
        else:
            # Try node_modules resolution
            result = self._resolve_node_modules(from_file, module, tried_paths)
            if result:
                return result
        
        # Not found
        return ResolveResult(
            module=module,
            file_path=None,
            kind="missing",
            meta={"tried_paths": tried_paths}
        )
    
    def _is_builtin(self, module: str) -> bool:
        """Check if module is a Node.js built-in."""
        return module in NODE_BUILTIN_MODULES
    
    def _resolve_relative(self, from_file: str, module: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Resolve a relative import."""
        from_dir = os.path.dirname(os.path.abspath(from_file))
        
        # Resolve relative path
        target_path = os.path.normpath(os.path.join(from_dir, module))
        
        # Try as file with various extensions
        file_result = self._try_file_extensions(target_path, tried_paths)
        if file_result:
            return file_result
        
        # Try as directory with index file
        dir_result = self._try_directory_index(target_path, tried_paths)
        if dir_result:
            return dir_result
        
        return None
    
    def _resolve_node_modules(self, from_file: str, module: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Resolve a package from node_modules."""
        from_dir = os.path.dirname(os.path.abspath(from_file))
        
        # Walk up directory tree looking for node_modules
        current_dir = from_dir
        while True:
            node_modules = os.path.join(current_dir, 'node_modules')
            
            if os.path.isdir(node_modules):
                # Check if package exists
                package_dir = os.path.join(node_modules, module.split('/')[0])
                
                if os.path.isdir(package_dir):
                    # Handle scoped packages (@babel/core)
                    if module.startswith('@'):
                        parts = module.split('/', 2)
                        if len(parts) >= 2:
                            package_dir = os.path.join(node_modules, parts[0], parts[1])
                            subpath = parts[2] if len(parts) > 2 else None
                        else:
                            subpath = None
                    else:
                        # Handle subpath imports (lodash/get)
                        parts = module.split('/', 1)
                        subpath = parts[1] if len(parts) > 1 else None
                    
                    # Try package.json main field
                    package_json_path = os.path.join(package_dir, 'package.json')
                    if os.path.isfile(package_json_path):
                        package_json = self._load_package_json(package_json_path)
                        
                        if subpath:
                            # Subpath import - resolve relative to package
                            subpath_full = os.path.join(package_dir, subpath)
                            result = self._try_file_extensions(subpath_full, tried_paths)
                            if result:
                                return result
                            result = self._try_directory_index(subpath_full, tried_paths)
                            if result:
                                return result
                        else:
                            # Main entry point
                            main = package_json.get('main', 'index.js')
                            main_path = os.path.join(package_dir, main)
                            
                            result = self._try_file_extensions(main_path, tried_paths)
                            if result:
                                return result
                            
                            # Try module field (ES6 modules)
                            module_field = package_json.get('module')
                            if module_field:
                                module_path = os.path.join(package_dir, module_field)
                                result = self._try_file_extensions(module_path, tried_paths)
                                if result:
                                    return result
                    
                    # Fallback to index.js in package dir
                    index_path = os.path.join(package_dir, 'index')
                    result = self._try_file_extensions(index_path, tried_paths)
                    if result:
                        return result
                    
                    # If package exists but we can't resolve it, mark as third_party
                    return ResolveResult(
                        module=module,
                        file_path=None,
                        kind="third_party",
                        meta={"package_dir": package_dir}
                    )
            
            # Move up one directory
            parent = os.path.dirname(current_dir)
            if parent == current_dir:
                # Reached root
                break
            current_dir = parent
        
        return None
    
    def _try_file_extensions(self, base_path: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Try to find file with various extensions."""
        # Remove extension if already present
        for ext in ['.js', '.jsx', '.mjs', '.cjs', '.json']:
            if base_path.endswith(ext):
                base_path = base_path[:-len(ext)]
                break
        
        # Try extensions in order
        extensions = ['.js', '.jsx', '.mjs', '.cjs', '.json', '']
        
        for ext in extensions:
            file_path = base_path + ext
            tried_paths.append(file_path)
            
            if os.path.isfile(file_path):
                # Found it!
                canonical = self.canonical_module_for_file(file_path)
                
                # Determine if it's a project file or third_party
                is_project = any(file_path.startswith(root) for root in self.project_roots)
                
                return ResolveResult(
                    module=canonical or os.path.basename(file_path),
                    file_path=file_path,
                    kind="module_file" if is_project else "third_party",
                    meta={"extension": ext}
                )
        
        return None
    
    def _try_directory_index(self, dir_path: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Try to find index file in directory."""
        if not os.path.isdir(dir_path):
            return None
        
        index_names = ['index.js', 'index.jsx', 'index.mjs', 'index.cjs']
        
        for index_name in index_names:
            index_path = os.path.join(dir_path, index_name)
            tried_paths.append(index_path)
            
            if os.path.isfile(index_path):
                canonical = self.canonical_module_for_file(index_path)
                is_project = any(index_path.startswith(root) for root in self.project_roots)
                
                return ResolveResult(
                    module=canonical or os.path.basename(index_path),
                    file_path=index_path,
                    kind="module_file" if is_project else "package_main",
                    meta={"is_index": True}
                )
        
        return None
    
    def _load_package_json(self, path: str) -> dict:
        """Load and cache package.json file."""
        if path in self._package_json_cache:
            return self._package_json_cache[path]
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._package_json_cache[path] = data
                return data
        except Exception:
            return {}
    
    def clear_caches(self):
        """Clear all internal caches."""
        self._canonical_cache.clear()
        self._resolve_cache.clear()
        self._package_json_cache.clear()
