"""
C# namespace/type resolver for import graph analysis.

This module provides resolution of C# using directives to files/types, handling:
- Using directives (using System.Collections.Generic)
- Using aliases (using MyList = System.Collections.Generic.List<int>)
- Using static (using static System.Math)
- Global using (global using System)
- .NET standard library detection
- Third-party library detection (NuGet packages)
"""

import os
import re
from dataclasses import dataclass
from typing import Optional, List, Dict, Set
from pathlib import Path


@dataclass(frozen=True)
class ResolveResult:
    """Result of resolving a using directive."""
    module: str              # canonical namespace/type name, e.g., "System.Collections.Generic"
    file_path: Optional[str] # resolved file path if it maps to a file
    kind: str                # "type_file"|"namespace"|"stdlib"|"third_party"|"missing"
    meta: dict               # extra info (search_path, tried_paths, etc.)


# .NET standard library namespaces
DOTNET_STDLIB_NAMESPACES = {
    # System namespaces
    'System', 'System.Collections', 'System.Collections.Generic',
    'System.Collections.Concurrent', 'System.Collections.ObjectModel',
    'System.ComponentModel', 'System.Configuration', 'System.Data',
    'System.Diagnostics', 'System.Drawing', 'System.Dynamic',
    'System.Globalization', 'System.IO', 'System.IO.Compression',
    'System.Linq', 'System.Media', 'System.Net', 'System.Net.Http',
    'System.Numerics', 'System.Reflection', 'System.Resources',
    'System.Runtime', 'System.Runtime.CompilerServices',
    'System.Runtime.InteropServices', 'System.Security',
    'System.Security.Cryptography', 'System.Text', 'System.Text.Json',
    'System.Text.RegularExpressions', 'System.Threading',
    'System.Threading.Tasks', 'System.Web', 'System.Windows',
    'System.Xml', 'System.Xml.Linq',
    # Microsoft namespaces
    'Microsoft.CSharp', 'Microsoft.Extensions', 'Microsoft.Win32',
    'Microsoft.VisualBasic',
}

# Common third-party namespaces (NuGet packages)
DOTNET_COMMON_THIRD_PARTY = {
    'Newtonsoft.Json', 'NLog', 'Serilog', 'AutoMapper', 'Dapper',
    'FluentValidation', 'MediatR', 'Polly', 'Moq', 'NUnit',
    'xUnit', 'MSTest', 'EntityFramework', 'Microsoft.EntityFrameworkCore',
    'Microsoft.AspNetCore', 'Microsoft.Azure', 'StackExchange.Redis',
    'MongoDB.Driver', 'Npgsql', 'MySql.Data', 'RestSharp',
}


class CSharpResolver:
    """Resolves C# using directives to namespaces and files."""
    
    def __init__(self, project_roots: List[str], extra_paths: Optional[List[str]] = None):
        """
        Initialize resolver with project roots and optional extra paths.
        
        Args:
            project_roots: List of directories to search for project types
            extra_paths: Additional assembly/project references
        """
        self.project_roots = [os.path.abspath(root) for root in project_roots]
        self.extra_paths = extra_paths or []
        
        # Cache for performance
        self._canonical_cache: Dict[str, Optional[str]] = {}
        self._resolve_cache: Dict[tuple, ResolveResult] = {}
        self._namespace_cache: Dict[str, str] = {}  # file -> namespace
        
        # Find all source files and build namespace index
        self._namespace_to_files: Dict[str, List[str]] = {}
        self._build_namespace_index()
    
    def _build_namespace_index(self):
        """Build an index of namespaces to source files."""
        for root in self.project_roots:
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip common non-source directories
                dirnames[:] = [d for d in dirnames if d not in {
                    'bin', 'obj', 'node_modules', '.git', '.vs', 'packages'
                }]
                
                for filename in filenames:
                    if filename.endswith('.cs'):
                        file_path = os.path.join(dirpath, filename)
                        namespace = self._extract_namespace_from_file(file_path)
                        
                        if namespace:
                            if namespace not in self._namespace_to_files:
                                self._namespace_to_files[namespace] = []
                            self._namespace_to_files[namespace].append(file_path)
    
    def canonical_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Compute canonical namespace.TypeName for a C# file.
        
        Args:
            file_path: Absolute path to a C# file
            
        Returns:
            Namespace.TypeName (e.g., "MyApp.Models.User") or None
        """
        file_path = os.path.abspath(file_path)
        
        if file_path in self._canonical_cache:
            return self._canonical_cache[file_path]
        
        result = None
        
        # Extract namespace from file
        namespace = self._extract_namespace_from_file(file_path)
        
        # Get primary type name from file name
        type_name = os.path.basename(file_path)
        if type_name.endswith('.cs'):
            type_name = type_name[:-3]
        
        if namespace:
            result = f"{namespace}.{type_name}"
        else:
            result = type_name
        
        self._canonical_cache[file_path] = result
        return result
    
    def _extract_namespace_from_file(self, file_path: str) -> Optional[str]:
        """Extract namespace declaration from C# file."""
        if file_path in self._namespace_cache:
            return self._namespace_cache[file_path]
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                
                # Try file-scoped namespace (C# 10+): namespace MyNamespace;
                file_scoped_match = re.search(
                    r'^\s*namespace\s+([\w.]+)\s*;',
                    content,
                    re.MULTILINE
                )
                if file_scoped_match:
                    namespace = file_scoped_match.group(1)
                    self._namespace_cache[file_path] = namespace
                    return namespace
                
                # Try block-scoped namespace: namespace MyNamespace { ... }
                block_scoped_match = re.search(
                    r'^\s*namespace\s+([\w.]+)\s*\{',
                    content,
                    re.MULTILINE
                )
                if block_scoped_match:
                    namespace = block_scoped_match.group(1)
                    self._namespace_cache[file_path] = namespace
                    return namespace
                
                # No namespace found (global namespace)
                self._namespace_cache[file_path] = ''
                return ''
                
        except (OSError, IOError):
            pass
        
        return None
    
    def resolve(self, from_file: str, using_spec: str, imported_names: Optional[List[str]] = None) -> ResolveResult:
        """
        Resolve a C# using directive to a namespace/file.
        
        Args:
            from_file: Absolute path to file containing the using
            using_spec: Using specifier (e.g., "System.Collections.Generic")
            imported_names: Names being imported (for using static)
            
        Returns:
            ResolveResult with resolution information
        """
        cache_key = (from_file, using_spec, tuple(imported_names or []))
        if cache_key in self._resolve_cache:
            return self._resolve_cache[cache_key]
        
        result = self._resolve_uncached(from_file, using_spec, imported_names)
        self._resolve_cache[cache_key] = result
        return result
    
    def _resolve_uncached(self, from_file: str, using_spec: str, imported_names: Optional[List[str]]) -> ResolveResult:
        """Perform uncached resolution."""
        tried_paths = []
        
        # Clean up the using spec (remove alias parts if present)
        clean_spec = using_spec
        if '=' in clean_spec:
            # Using alias: using MyList = System.Collections.Generic.List<int>
            clean_spec = clean_spec.split('=', 1)[1].strip()
            # Remove generic parameters for resolution
            if '<' in clean_spec:
                clean_spec = clean_spec.split('<')[0]
        
        # Check if it's a standard library namespace
        if self._is_stdlib(clean_spec):
            return ResolveResult(
                module=clean_spec,
                file_path=None,
                kind="stdlib",
                meta={"stdlib": True}
            )
        
        # Check if it's a known third-party namespace
        if self._is_third_party(clean_spec):
            return ResolveResult(
                module=clean_spec,
                file_path=None,
                kind="third_party",
                meta={"third_party": True}
            )
        
        # Try to resolve from namespace index
        result = self._resolve_from_index(clean_spec, tried_paths)
        if result:
            return result
        
        # Try to resolve as a type file
        result = self._resolve_type(clean_spec, tried_paths)
        if result:
            return result
        
        # Not found in project - might be third-party
        return ResolveResult(
            module=clean_spec,
            file_path=None,
            kind="third_party",  # Assume third-party if not found
            meta={"tried_paths": tried_paths}
        )
    
    def _is_stdlib(self, using_spec: str) -> bool:
        """Check if using is from .NET standard library."""
        # System.* namespaces are stdlib
        if using_spec.startswith('System.') or using_spec == 'System':
            return True
        
        # Microsoft.* base namespaces
        if using_spec.startswith('Microsoft.CSharp') or using_spec.startswith('Microsoft.Win32'):
            return True
        
        # Check against known stdlib namespaces
        for ns in DOTNET_STDLIB_NAMESPACES:
            if using_spec.startswith(ns + '.') or using_spec == ns:
                return True
        
        return False
    
    def _is_third_party(self, using_spec: str) -> bool:
        """Check if using is from common third-party libraries."""
        for ns in DOTNET_COMMON_THIRD_PARTY:
            if using_spec.startswith(ns + '.') or using_spec == ns:
                return True
        return False
    
    def _resolve_from_index(self, namespace: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Resolve from the built namespace index."""
        # Exact match
        if namespace in self._namespace_to_files:
            files = self._namespace_to_files[namespace]
            if files:
                return ResolveResult(
                    module=namespace,
                    file_path=files[0],  # Return first file as representative
                    kind="namespace",
                    meta={"all_files": files, "file_count": len(files)}
                )
        
        # Try as a type within a namespace
        # e.g., "MyApp.Models.User" -> look for "User.cs" in namespace "MyApp.Models"
        if '.' in namespace:
            parent_namespace = namespace.rsplit('.', 1)[0]
            type_name = namespace.rsplit('.', 1)[1]
            
            if parent_namespace in self._namespace_to_files:
                for file_path in self._namespace_to_files[parent_namespace]:
                    basename = os.path.basename(file_path)
                    if basename == f"{type_name}.cs":
                        tried_paths.append(file_path)
                        return ResolveResult(
                            module=namespace,
                            file_path=file_path,
                            kind="type_file",
                            meta={"namespace": parent_namespace, "type_name": type_name}
                        )
        
        return None
    
    def _resolve_type(self, type_spec: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Try to resolve as a direct type file."""
        # Convert namespace.TypeName to path
        parts = type_spec.split('.')
        
        for root in self.project_roots:
            # Try direct path match
            type_path = os.path.join(root, *parts[:-1], parts[-1] + '.cs') if len(parts) > 1 else os.path.join(root, parts[0] + '.cs')
            tried_paths.append(type_path)
            
            if os.path.isfile(type_path):
                canonical = self.canonical_module_for_file(type_path)
                return ResolveResult(
                    module=canonical or type_spec,
                    file_path=type_path,
                    kind="type_file",
                    meta={"source_root": root}
                )
            
            # Try with nested directories matching namespace
            for dirpath, dirnames, filenames in os.walk(root):
                # Skip build directories
                dirnames[:] = [d for d in dirnames if d not in {'bin', 'obj', '.git', '.vs'}]
                
                type_file = parts[-1] + '.cs'
                if type_file in filenames:
                    file_path = os.path.join(dirpath, type_file)
                    tried_paths.append(file_path)
                    
                    # Verify namespace matches
                    file_namespace = self._extract_namespace_from_file(file_path)
                    expected_namespace = '.'.join(parts[:-1]) if len(parts) > 1 else ''
                    
                    if file_namespace == expected_namespace or not expected_namespace:
                        canonical = self.canonical_module_for_file(file_path)
                        return ResolveResult(
                            module=canonical or type_spec,
                            file_path=file_path,
                            kind="type_file",
                            meta={"source_root": root, "namespace": file_namespace}
                        )
        
        return None
    
    def clear_caches(self):
        """Clear all internal caches."""
        self._canonical_cache.clear()
        self._resolve_cache.clear()
        self._namespace_cache.clear()
        self._namespace_to_files.clear()
        self._build_namespace_index()
