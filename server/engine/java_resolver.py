"""
Java module/package resolver for import graph analysis.

This module provides resolution of Java imports to files/classes, handling:
- Single type imports (import com.example.MyClass)
- Wildcard imports (import com.example.*)
- Static imports (import static com.example.MyClass.method)
- Standard library (java.*, javax.*)
- Third-party libraries detection
"""

import os
from dataclasses import dataclass
from typing import Optional, List, Dict, Set
from pathlib import Path


@dataclass(frozen=True)
class ResolveResult:
    """Result of resolving an import specifier."""
    module: str              # canonical module/class name, e.g., "com.example.MyClass"
    file_path: Optional[str] # resolved file path if it maps to a file
    kind: str                # "class_file"|"package"|"stdlib"|"third_party"|"missing"
    meta: dict               # extra info (search_path, tried_paths, etc.)


# Java standard library packages (java.* and javax.*)
JAVA_STDLIB_PACKAGES = {
    # java.* packages
    'java.applet', 'java.awt', 'java.beans', 'java.io', 'java.lang', 
    'java.math', 'java.net', 'java.nio', 'java.rmi', 'java.security',
    'java.sql', 'java.text', 'java.time', 'java.util',
    # javax.* packages
    'javax.accessibility', 'javax.annotation', 'javax.crypto', 'javax.imageio',
    'javax.management', 'javax.naming', 'javax.net', 'javax.print',
    'javax.script', 'javax.security', 'javax.sound', 'javax.sql',
    'javax.swing', 'javax.tools', 'javax.transaction', 'javax.xml',
    # Common Jakarta EE packages (formerly javax)
    'jakarta.servlet', 'jakarta.persistence', 'jakarta.enterprise',
    'jakarta.inject', 'jakarta.validation', 'jakarta.ws', 'jakarta.xml',
}

# Common third-party packages
JAVA_COMMON_THIRD_PARTY = {
    'org.springframework', 'org.hibernate', 'org.apache', 'org.junit',
    'org.mockito', 'org.slf4j', 'org.json', 'com.google', 'com.fasterxml',
    'io.netty', 'io.micronaut', 'io.quarkus', 'lombok',
}


class JavaResolver:
    """Resolves Java import specifiers to classes and files."""
    
    def __init__(self, project_roots: List[str], extra_paths: Optional[List[str]] = None):
        """
        Initialize resolver with project roots and optional extra paths.
        
        Args:
            project_roots: List of directories to search for project classes
            extra_paths: Additional classpath entries
        """
        self.project_roots = [os.path.abspath(root) for root in project_roots]
        self.extra_paths = extra_paths or []
        
        # Build search paths for source files
        self.source_paths = self._find_source_roots()
        
        # Cache for performance
        self._canonical_cache: Dict[str, Optional[str]] = {}
        self._resolve_cache: Dict[tuple, ResolveResult] = {}
        self._package_cache: Dict[str, str] = {}  # file -> package
    
    def _find_source_roots(self) -> List[str]:
        """Find Java source roots (src/main/java, src, etc.)."""
        source_roots = []
        
        for root in self.project_roots:
            # Check common Maven/Gradle source directories
            common_paths = [
                os.path.join(root, 'src', 'main', 'java'),
                os.path.join(root, 'src', 'test', 'java'),
                os.path.join(root, 'src'),
                root,  # Direct source in root
            ]
            
            for path in common_paths:
                if os.path.isdir(path):
                    # Check if it looks like a Java source root
                    # (contains .java files or package directories)
                    if self._looks_like_source_root(path):
                        if path not in source_roots:
                            source_roots.append(path)
        
        # If no source roots found, use project roots directly
        if not source_roots:
            source_roots = self.project_roots.copy()
        
        return source_roots
    
    def _looks_like_source_root(self, path: str) -> bool:
        """Check if directory looks like a Java source root."""
        try:
            for item in os.listdir(path):
                item_path = os.path.join(path, item)
                if item.endswith('.java'):
                    return True
                if os.path.isdir(item_path):
                    # Check for package-like directory structure
                    if item[0].islower() or item == 'META-INF':
                        return True
        except OSError:
            pass
        return False
    
    def canonical_module_for_file(self, file_path: str) -> Optional[str]:
        """
        Compute canonical fully-qualified class name for a Java file.
        
        Args:
            file_path: Absolute path to a Java file
            
        Returns:
            Fully qualified class name (e.g., "com.example.MyClass") or None
        """
        file_path = os.path.abspath(file_path)
        
        if file_path in self._canonical_cache:
            return self._canonical_cache[file_path]
        
        result = None
        
        # First, try to extract package from file content
        package = self._extract_package_from_file(file_path)
        
        if package is not None:
            # Get class name from file name
            class_name = os.path.basename(file_path)
            if class_name.endswith('.java'):
                class_name = class_name[:-5]
            
            if package:
                result = f"{package}.{class_name}"
            else:
                result = class_name
        else:
            # Fallback: derive from path relative to source root
            for source_root in self.source_paths:
                if file_path.startswith(source_root + os.sep):
                    rel_path = os.path.relpath(file_path, source_root)
                    
                    # Convert path to package.ClassName
                    if rel_path.endswith('.java'):
                        rel_path = rel_path[:-5]
                    
                    result = rel_path.replace(os.sep, '.')
                    break
        
        self._canonical_cache[file_path] = result
        return result
    
    def _extract_package_from_file(self, file_path: str) -> Optional[str]:
        """Extract package declaration from Java file."""
        if file_path in self._package_cache:
            return self._package_cache[file_path]
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                # Read first 50 lines to find package declaration
                for i, line in enumerate(f):
                    if i > 50:
                        break
                    
                    line = line.strip()
                    
                    # Skip comments
                    if line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                        continue
                    
                    # Look for package declaration
                    if line.startswith('package '):
                        # Extract package name
                        package_line = line[8:]  # Remove 'package '
                        if package_line.endswith(';'):
                            package_line = package_line[:-1]
                        package = package_line.strip()
                        self._package_cache[file_path] = package
                        return package
                    
                    # If we hit a class/interface/enum declaration, no package
                    if any(line.startswith(kw) for kw in ['class ', 'interface ', 'enum ', 'public class', 'public interface', 'public enum']):
                        self._package_cache[file_path] = ''
                        return ''
        except (OSError, IOError):
            pass
        
        return None
    
    def resolve(self, from_file: str, import_spec: str, imported_names: Optional[List[str]] = None) -> ResolveResult:
        """
        Resolve a Java import specifier to a class/file.
        
        Args:
            from_file: Absolute path to file containing the import
            import_spec: Import specifier (e.g., "com.example.MyClass", "java.util.*")
            imported_names: Names being imported (for static imports)
            
        Returns:
            ResolveResult with resolution information
        """
        cache_key = (from_file, import_spec, tuple(imported_names or []))
        if cache_key in self._resolve_cache:
            return self._resolve_cache[cache_key]
        
        result = self._resolve_uncached(from_file, import_spec, imported_names)
        self._resolve_cache[cache_key] = result
        return result
    
    def _resolve_uncached(self, from_file: str, import_spec: str, imported_names: Optional[List[str]]) -> ResolveResult:
        """Perform uncached resolution."""
        tried_paths = []
        
        # Check if it's a standard library import
        if self._is_stdlib(import_spec):
            return ResolveResult(
                module=import_spec,
                file_path=None,
                kind="stdlib",
                meta={"stdlib": True}
            )
        
        # Check if it's a known third-party import
        if self._is_third_party(import_spec):
            return ResolveResult(
                module=import_spec,
                file_path=None,
                kind="third_party",
                meta={"third_party": True}
            )
        
        # Handle wildcard imports
        is_wildcard = import_spec.endswith('.*')
        if is_wildcard:
            package = import_spec[:-2]  # Remove .*
            result = self._resolve_package(package, tried_paths)
            if result:
                return result
        else:
            # Single class import
            result = self._resolve_class(import_spec, tried_paths)
            if result:
                return result
        
        # Not found - might be third-party
        return ResolveResult(
            module=import_spec,
            file_path=None,
            kind="third_party",  # Assume it's third-party if not found
            meta={"tried_paths": tried_paths}
        )
    
    def _is_stdlib(self, import_spec: str) -> bool:
        """Check if import is from Java standard library."""
        # java.* and javax.* are stdlib
        if import_spec.startswith('java.') or import_spec.startswith('javax.'):
            return True
        
        # Check against known stdlib packages
        for pkg in JAVA_STDLIB_PACKAGES:
            if import_spec.startswith(pkg + '.') or import_spec == pkg:
                return True
        
        return False
    
    def _is_third_party(self, import_spec: str) -> bool:
        """Check if import is from common third-party libraries."""
        for pkg in JAVA_COMMON_THIRD_PARTY:
            if import_spec.startswith(pkg + '.') or import_spec == pkg:
                return True
        return False
    
    def _resolve_class(self, class_name: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Resolve a fully qualified class name to a file."""
        # Convert class name to file path
        class_path = class_name.replace('.', os.sep) + '.java'
        
        for source_root in self.source_paths:
            file_path = os.path.join(source_root, class_path)
            tried_paths.append(file_path)
            
            if os.path.isfile(file_path):
                canonical = self.canonical_module_for_file(file_path)
                return ResolveResult(
                    module=canonical or class_name,
                    file_path=file_path,
                    kind="class_file",
                    meta={"source_root": source_root}
                )
        
        # Also check extra paths
        for extra_path in self.extra_paths:
            file_path = os.path.join(extra_path, class_path)
            tried_paths.append(file_path)
            
            if os.path.isfile(file_path):
                canonical = self.canonical_module_for_file(file_path)
                return ResolveResult(
                    module=canonical or class_name,
                    file_path=file_path,
                    kind="class_file",
                    meta={"source_root": extra_path}
                )
        
        return None
    
    def _resolve_package(self, package_name: str, tried_paths: List[str]) -> Optional[ResolveResult]:
        """Resolve a package name to a directory."""
        # Convert package name to directory path
        package_path = package_name.replace('.', os.sep)
        
        for source_root in self.source_paths:
            dir_path = os.path.join(source_root, package_path)
            tried_paths.append(dir_path)
            
            if os.path.isdir(dir_path):
                return ResolveResult(
                    module=package_name + ".*",
                    file_path=dir_path,
                    kind="package",
                    meta={"source_root": source_root, "is_wildcard": True}
                )
        
        return None
    
    def clear_caches(self):
        """Clear all internal caches."""
        self._canonical_cache.clear()
        self._resolve_cache.clear()
        self._package_cache.clear()
