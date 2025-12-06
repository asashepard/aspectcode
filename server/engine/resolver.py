"""
Python module resolver for import graph analysis.

This module provides resolution of Python imports to files/modules, handling:
- Absolute and relative imports
- Package hierarchies and namespace packages (PEP 420)
- Standard library and third-party module detection
- Missing/unresolvable import detection
"""

import os
import sys
import sysconfig
import site
from dataclasses import dataclass
from typing import Optional, List, Dict, Set
from pathlib import Path


@dataclass(frozen=True)
class ResolveResult:
    """Result of resolving an import specifier."""
    module: str              # canonical module name, e.g., "pkg.sub.mod"
    file_path: Optional[str] # resolved file path if it maps to a file/module
    kind: str                # "module_file"|"package_init"|"namespace_pkg"|"builtin"|"stdlib"|"third_party"|"missing"
    meta: dict               # extra info (search_path, tried_paths, etc.)


class PythonResolver:
    """Resolves Python import specifiers to modules and files."""
    
    def __init__(self, project_roots: List[str], extra_sys_path: Optional[List[str]] = None):
        """
        Initialize resolver with project roots and optional extra sys.path entries.
        
        Args:
            project_roots: List of directories to search for project modules
            extra_sys_path: Additional sys.path entries (e.g., from config)
        """
        self.project_roots = [os.path.abspath(root) for root in project_roots]
        self.extra_sys_path = extra_sys_path or []
        
        # Build search paths: project roots + extra + stdlib + site-packages
        self.search_paths = []
        self.search_paths.extend(self.project_roots)
        self.search_paths.extend(self.extra_sys_path)
        
        # Get stdlib and site-packages paths
        self.stdlib_paths = self._get_stdlib_paths()
        self.site_packages = self._get_site_packages()
        
        # Add stdlib to search for identification
        self.search_paths.extend(self.stdlib_paths)
        self.search_paths.extend(self.site_packages)
        
        # Cache for performance
        self._canonical_cache: Dict[str, Optional[str]] = {}
        self._resolve_cache: Dict[tuple, ResolveResult] = {}
        
        # Builtin modules (no file path)
        self.builtin_modules = set(sys.builtin_module_names)
    
    def _get_stdlib_paths(self) -> List[str]:
        """Get standard library paths."""
        paths = []
        try:
            stdlib_path = sysconfig.get_path('stdlib')
            if stdlib_path and os.path.exists(stdlib_path):
                paths.append(stdlib_path)
        except:
            pass
        return paths
    
    def _get_site_packages(self) -> List[str]:
        """Get site-packages paths."""
        paths = []
        try:
            for path in site.getsitepackages():
                if os.path.exists(path):
                    paths.append(path)
        except:
            pass
        
        # Also try site.getusersitepackages()
        try:
            user_site = site.getusersitepackages()
            if user_site and os.path.exists(user_site):
                paths.append(user_site)
        except:
            pass
        
        return paths
    
    def canonical_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Compute canonical module name for a Python file.
        
        Args:
            file_path: Absolute path to a Python file
            
        Returns:
            Canonical module name (e.g., "pkg.sub.mod") or None if not in project
        """
        file_path = os.path.abspath(file_path)
        
        if file_path in self._canonical_cache:
            return self._canonical_cache[file_path]
        
        result = None
        
        # Try each project root
        for root in self.project_roots:
            if file_path.startswith(root + os.sep) or file_path == root:
                rel_path = os.path.relpath(file_path, root)
                
                # Convert path to module name
                if rel_path.endswith('.py'):
                    rel_path = rel_path[:-3]
                elif rel_path.endswith('__init__.py'):
                    rel_path = os.path.dirname(rel_path)
                
                # Convert to module name
                if rel_path == '.':
                    # Root module (shouldn't happen for normal files)
                    continue
                
                module_parts = rel_path.replace(os.sep, '.').split('.')
                result = '.'.join(part for part in module_parts if part)
                break
        
        self._canonical_cache[file_path] = result
        return result
    
    def resolve(self, from_file: str, module: str, imported_names: Optional[List[str]] = None) -> ResolveResult:
        """
        Resolve an import specifier to a module/file.
        
        Args:
            from_file: Absolute path to file containing the import
            module: Module specifier (e.g., "pkg.sub", "..relative")
            imported_names: Names being imported (for from imports)
            
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
        """Internal uncached resolve implementation."""
        tried_paths = []
        
        # Handle relative imports
        if module.startswith('.'):
            return self._resolve_relative(from_file, module, imported_names, tried_paths)
        
        # Handle builtin modules
        if module in self.builtin_modules:
            return ResolveResult(
                module=module,
                file_path=None,
                kind="builtin",
                meta={"tried_paths": tried_paths}
            )
        
        # Try to resolve as absolute import
        return self._resolve_absolute(module, imported_names, tried_paths)
    
    def _resolve_relative(self, from_file: str, module: str, imported_names: Optional[List[str]], tried_paths: List[str]) -> ResolveResult:
        """Resolve relative import (starts with dots)."""
        # Count leading dots to determine level
        level = 0
        for char in module:
            if char == '.':
                level += 1
            else:
                break
        
        # Get the remaining module part after dots
        relative_module = module[level:] if level < len(module) else ""
        
        # Get canonical module name of the importing file
        from_module = self.canonical_module_for_file(from_file)
        if not from_module:
            return ResolveResult(
                module=module,
                file_path=None,
                kind="missing",
                meta={"tried_paths": tried_paths, "error": "Cannot resolve relative import: file not in project"}
            )
        
        # Compute base module for relative import
        from_parts = from_module.split('.')
        if level > len(from_parts):
            return ResolveResult(
                module=module,
                file_path=None,
                kind="missing",
                meta={"tried_paths": tried_paths, "error": f"Relative import level {level} exceeds module depth {len(from_parts)}"}
            )
        
        # Go up 'level' levels from current module
        base_parts = from_parts[:-level] if level > 0 else from_parts
        
        # Add the relative module part
        if relative_module:
            target_module = '.'.join(base_parts + [relative_module])
        else:
            target_module = '.'.join(base_parts)
        
        # Resolve the computed absolute module
        return self._resolve_absolute(target_module, imported_names, tried_paths)
    
    def _resolve_absolute(self, module: str, imported_names: Optional[List[str]], tried_paths: List[str]) -> ResolveResult:
        """Resolve absolute module import."""
        module_parts = module.split('.')
        
        # Try each search path
        for search_path in self.search_paths:
            # Try module file (e.g., pkg/sub/mod.py)
            module_file = os.path.join(search_path, *module_parts) + '.py'
            tried_paths.append(module_file)
            
            if os.path.isfile(module_file):
                kind = self._classify_path_kind(search_path, module_file)
                return ResolveResult(
                    module=module,
                    file_path=module_file,
                    kind=kind,
                    meta={"tried_paths": tried_paths, "search_path": search_path}
                )
            
            # Try package __init__.py (e.g., pkg/sub/mod/__init__.py)
            package_init = os.path.join(search_path, *module_parts, '__init__.py')
            tried_paths.append(package_init)
            
            if os.path.isfile(package_init):
                kind = self._classify_path_kind(search_path, package_init)
                return ResolveResult(
                    module=module,
                    file_path=package_init,
                    kind=kind,
                    meta={"tried_paths": tried_paths, "search_path": search_path}
                )
            
            # Try namespace package (directory without __init__.py)
            namespace_dir = os.path.join(search_path, *module_parts)
            tried_paths.append(namespace_dir + '/ (namespace)')
            
            if os.path.isdir(namespace_dir) and not os.path.exists(os.path.join(namespace_dir, '__init__.py')):
                kind = self._classify_path_kind(search_path, namespace_dir)
                if kind in ("module_file", "package_init"):  # project paths
                    kind = "namespace_pkg"
                
                return ResolveResult(
                    module=module,
                    file_path=None,  # namespace packages don't have a single file
                    kind=kind,
                    meta={"tried_paths": tried_paths, "search_path": search_path, "namespace_dir": namespace_dir}
                )
        
        # Module not found anywhere
        return ResolveResult(
            module=module,
            file_path=None,
            kind="missing",
            meta={"tried_paths": tried_paths}
        )
    
    def _classify_path_kind(self, search_path: str, resolved_path: str) -> str:
        """Classify the kind of resolved path."""
        # Check if it's in project roots
        for root in self.project_roots:
            if search_path == root or search_path.startswith(root + os.sep):
                if resolved_path.endswith('__init__.py'):
                    return "package_init"
                else:
                    return "module_file"
        
        # Check if it's in stdlib
        for stdlib_path in self.stdlib_paths:
            if search_path == stdlib_path or search_path.startswith(stdlib_path + os.sep):
                return "stdlib"
        
        # Check if it's in site-packages
        for site_path in self.site_packages:
            if search_path == site_path or search_path.startswith(site_path + os.sep):
                return "third_party"
        
        # Default to third_party for extra_sys_path
        return "third_party"

