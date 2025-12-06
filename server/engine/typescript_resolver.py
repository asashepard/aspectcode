"""
TypeScript module resolver for import graph analysis.

Extends the JavaScript resolver with TypeScript-specific features:
- TypeScript file extensions (.ts, .tsx, .d.ts)
- Type-only imports
- Declaration files
"""

import os
from typing import Optional, List
from .javascript_resolver import JavaScriptResolver, ResolveResult


class TypeScriptResolver(JavaScriptResolver):
    """Resolves TypeScript import specifiers to modules and files."""
    
    def __init__(self, project_roots: List[str], extra_paths: Optional[List[str]] = None):
        """
        Initialize resolver with project roots and optional extra paths.
        
        Args:
            project_roots: List of directories to search for project modules
            extra_paths: Additional paths to search
        """
        super().__init__(project_roots, extra_paths)
    
    def canonical_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Compute canonical module name for a TypeScript file.
        
        Args:
            file_path: Absolute path to a TypeScript file
            
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
                
                # Remove TypeScript extensions
                for ext in ['.ts', '.tsx', '.d.ts', '.js', '.jsx', '.mjs', '.cjs']:
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
    
    def _try_file_extensions(self, base_path: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Try to find file with various TypeScript/JavaScript extensions."""
        # Remove extension if already present
        for ext in ['.ts', '.tsx', '.d.ts', '.js', '.jsx', '.mjs', '.cjs', '.json']:
            if base_path.endswith(ext):
                base_path = base_path[:-len(ext)]
                break
        
        # Try TypeScript extensions first, then JavaScript
        extensions = ['.ts', '.tsx', '.d.ts', '.js', '.jsx', '.mjs', '.cjs', '.json', '']
        
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
        """Try to find index file in directory (TypeScript or JavaScript)."""
        if not os.path.isdir(dir_path):
            return None
        
        # Try TypeScript index files first
        index_names = ['index.ts', 'index.tsx', 'index.d.ts', 'index.js', 'index.jsx', 'index.mjs', 'index.cjs']
        
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
        """Load and cache package.json file, handling TypeScript-specific fields."""
        if path in self._package_json_cache:
            return self._package_json_cache[path]
        
        try:
            import json
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._package_json_cache[path] = data
                return data
        except Exception:
            return {}
