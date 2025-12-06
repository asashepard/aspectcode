"""
Rule: imports.missing_file_target

Detects imports that cannot be resolved to any file or module using resolver and filesystem checks.
Provides detailed information about resolution attempts and suggested fixes with tried paths.

Supports: Python, TypeScript, JavaScript
"""

from typing import Iterator, List, Dict, Any, Tuple, Optional, Set
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext, Edit
import os
import os.path


class ImportsMissingFileTargetRule:
    """
    Detect imports that cannot be resolved to files or modules.
    
    Uses resolver + filesystem checks to identify imports that fail to resolve,
    showing all tried paths and providing helpful suggestions.
    
    Examples of missing imports:
    
    Python:
        from nonexistent_module import func  # Module doesn't exist
        import missing.submodule            # Submodule path not found
        from .missing import item           # Relative import target missing
        
    TypeScript/JavaScript:
        import { func } from './missing'     # File doesn't exist
        import * as mod from '../nonexistent'  # Path not found
        const mod = require('missing-package') # Package not available
    """
    
    @property
    def meta(self) -> RuleMeta:
        return RuleMeta(
            id="imports.missing_file_target",
            category="imports", 
            tier=2,  # Requires project graph
            priority="P0",
            autofix_safety="suggest-only",
            description="Unresolvable import target",
            langs=["python", "typescript", "javascript"]
        )
    
    @property
    def requires(self) -> Requires:
        return Requires(
            raw_text=False,
            syntax=True,
            scopes=False,
            project_graph=True  # This rule needs import resolution
        )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find unresolvable imports in the file."""
        if not ctx.project_graph:
            return
        
        # Check if this is a supported file type
        if not self._is_supported_file(ctx.file_path):
            return
        
        resolver, import_graph, symbol_index = ctx.project_graph
        
        # Get configuration
        config = getattr(ctx, 'config', {})
        ignore_external = config.get('imports.missing_file_target.ignore_external', True)
        
        # Extract imports from the file using the adapter
        try:
            if not ctx.adapter or not ctx.tree:
                return
                
            imports = ctx.adapter.iter_imports(ctx.tree)
            
            for import_info in imports:
                # Extract import details based on language
                import_details = self._extract_import_details(import_info, ctx.file_path)
                if not import_details:
                    continue
                
                module_name, level, names, import_range = import_details
                
                # Build full module name for relative imports
                resolve_module = self._build_resolve_module(module_name, level)
                
                # Resolve the import using the resolver
                resolution_result = self._resolve_import(resolver, ctx.file_path, resolve_module, names)
                
                # Check if it's missing
                if resolution_result.get("kind") == "missing" or not resolution_result.get("resolved"):
                    # Apply ignore_external filter
                    if ignore_external and self._looks_like_external(module_name, ctx.file_path):
                        continue
                    
                    # Perform additional filesystem checks to get tried paths
                    tried_paths = self._get_tried_paths(ctx.file_path, module_name, level, resolver)
                    
                    # Create finding for missing import
                    finding = Finding(
                        rule=self.meta.id,
                        message=self._format_error_message(module_name, level, ctx.file_path),
                        severity="error", 
                        file=ctx.file_path,
                        start_byte=import_range[0],
                        end_byte=import_range[1],
                        autofix=None,  # Suggest-only
                        meta={
                            "module": module_name,
                            "level": level,
                            "is_relative": level > 0,
                            "tried_paths": tried_paths,
                            "file_type": self._get_file_type(ctx.file_path),
                            "import_type": "from" if level > 0 else "import",
                            "suggestions": self._generate_suggestions(module_name, level, tried_paths, ctx.file_path),
                            "resolution_details": resolution_result
                        }
                    )
                    yield finding
                    
        except Exception as e:
            # Silently handle adapter errors to avoid breaking the analysis
            pass
    
    def _is_supported_file(self, file_path: str) -> bool:
        """Check if the file type is supported by this rule."""
        supported_extensions = {
            '.py',      # Python
            '.ts',      # TypeScript 
            '.tsx',     # TypeScript React
            '.js',      # JavaScript
            '.jsx',     # JavaScript React
            '.mjs',     # ES Module JavaScript
        }
        
        ext = os.path.splitext(file_path)[1].lower()
        return ext in supported_extensions
    
    def _get_file_type(self, file_path: str) -> str:
        """Get the file type for language-specific handling."""
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.py':
            return 'python'
        elif ext in ['.ts', '.tsx']:
            return 'typescript'
        elif ext in ['.js', '.jsx', '.mjs']:
            return 'javascript'
        else:
            return 'unknown'
    
    def _extract_import_details(self, import_info, file_path: str) -> Optional[Tuple[str, int, List[str], Tuple[int, int]]]:
        """Extract import details from import_info, handling different languages."""
        try:
            # Try to get module name from various attributes
            module_name = None
            for attr in ['module', 'target', 'source', 'path']:
                if hasattr(import_info, attr):
                    value = getattr(import_info, attr)
                    if value:
                        module_name = str(value)
                        break
            
            if not module_name:
                return None
            
            # Get level (for Python relative imports)
            level = getattr(import_info, 'level', 0)
            
            # Get imported names
            names = getattr(import_info, 'names', [])
            if names and not isinstance(names, list):
                names = [names]
            
            # Get import range
            import_range = self._get_import_range(import_info)
            
            return (module_name, level, names, import_range)
            
        except Exception:
            return None
    
    def _get_import_range(self, import_info) -> Tuple[int, int]:
        """Get byte range of the import statement."""
        # Try common range attributes
        if hasattr(import_info, 'range') and import_info.range:
            if isinstance(import_info.range, tuple) and len(import_info.range) == 2:
                return import_info.range
        
        # Try start/end attributes
        start_byte = getattr(import_info, 'start_byte', 0)
        end_byte = getattr(import_info, 'end_byte', 0)
        
        # Ensure we have numeric values for comparison
        start_byte = start_byte if start_byte is not None else 0
        end_byte = end_byte if end_byte is not None else 0
        
        if end_byte > start_byte:
            return (start_byte, end_byte)
        
        # Fallback to position attributes
        start_pos = getattr(import_info, 'start', 0)
        end_pos = getattr(import_info, 'end', 0)
        
        # Ensure we have numeric values for comparison
        start_pos = start_pos if start_pos is not None else 0
        end_pos = end_pos if end_pos is not None else 0
        
        if end_pos > start_pos:
            return (start_pos, end_pos)
        
        return (0, 0)
    
    def _build_resolve_module(self, module_name: str, level: int) -> str:
        """Build the module name for resolution."""
        if level > 0:
            # Relative import
            return "." * level + module_name
        else:
            return module_name
    
    def _resolve_import(self, resolver, file_path: str, module_name: str, names: List[str]) -> Dict[str, Any]:
        """Resolve import using the resolver with detailed result."""
        try:
            # Try using resolver if available
            if hasattr(resolver, 'resolve'):
                result = resolver.resolve(file_path, module_name, names)
                if hasattr(result, 'kind'):
                    return {
                        "kind": result.kind,
                        "resolved": result.kind != "missing",
                        "meta": getattr(result, 'meta', {})
                    }
            
            # Fallback: try to resolve manually
            resolved_path = self._manual_resolve(file_path, module_name)
            return {
                "kind": "resolved" if resolved_path else "missing",
                "resolved": bool(resolved_path),
                "meta": {"resolved_path": resolved_path} if resolved_path else {}
            }
            
        except Exception:
            return {"kind": "missing", "resolved": False, "meta": {}}
    
    def _manual_resolve(self, file_path: str, module_name: str) -> Optional[str]:
        """Manual import resolution for fallback."""
        file_dir = os.path.dirname(file_path)
        
        # Handle relative imports (starting with dots)
        if module_name.startswith('.'):
            level = 0
            while level < len(module_name) and module_name[level] == '.':
                level += 1
            
            # Go up directories based on level
            current_dir = file_dir
            for _ in range(level - 1):
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == current_dir:  # Can't go up further
                    return None
                current_dir = parent_dir
            
            # Get the module part after dots
            module_part = module_name[level:] if level < len(module_name) else ""
            if module_part:
                return self._try_resolve_in_directory(current_dir, module_part)
            else:
                return current_dir if os.path.isdir(current_dir) else None
        
        else:
            # Absolute import - try in current directory first, then up the tree
            return self._try_resolve_in_directory(file_dir, module_name)
    
    def _try_resolve_in_directory(self, directory: str, module_name: str) -> Optional[str]:
        """Try to resolve a module in a specific directory."""
        if not os.path.isdir(directory):
            return None
        
        # Convert module.submodule to path
        module_parts = module_name.split('.')
        
        # Try as file
        file_path = os.path.join(directory, *module_parts[:-1], module_parts[-1] + '.py')
        if os.path.isfile(file_path):
            return file_path
        
        # Try as package directory with __init__.py
        package_path = os.path.join(directory, *module_parts)
        init_path = os.path.join(package_path, '__init__.py')
        if os.path.isfile(init_path):
            return init_path
        
        # Try JS/TS files
        for ext in ['.js', '.ts', '.jsx', '.tsx', '.mjs']:
            file_path = os.path.join(directory, *module_parts[:-1], module_parts[-1] + ext)
            if os.path.isfile(file_path):
                return file_path
        
        return None
    
    def _get_tried_paths(self, file_path: str, module_name: str, level: int, resolver) -> List[str]:
        """Get list of paths that were tried during resolution."""
        tried_paths = []
        file_dir = os.path.dirname(file_path)
        file_type = self._get_file_type(file_path)
        
        if level > 0:
            # Relative import
            current_dir = file_dir
            for _ in range(level - 1):
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == current_dir:
                    break
                current_dir = parent_dir
            
            # Add tried paths for relative import
            tried_paths.extend(self._generate_tried_paths(current_dir, module_name, file_type))
        else:
            # Absolute import
            tried_paths.extend(self._generate_tried_paths(file_dir, module_name, file_type))
            
            # Also try parent directories
            current_dir = file_dir
            for _ in range(3):  # Try up to 3 levels up
                parent_dir = os.path.dirname(current_dir)
                if parent_dir == current_dir:
                    break
                tried_paths.extend(self._generate_tried_paths(parent_dir, module_name, file_type))
                current_dir = parent_dir
        
        return tried_paths[:10]  # Limit to 10 tried paths
    
    def _generate_tried_paths(self, directory: str, module_name: str, file_type: str) -> List[str]:
        """Generate list of paths that would be tried for a module."""
        paths = []
        module_parts = module_name.split('.')
        
        if file_type == 'python':
            # Python file
            paths.append(os.path.join(directory, *module_parts[:-1], module_parts[-1] + '.py'))
            # Python package
            paths.append(os.path.join(directory, *module_parts, '__init__.py'))
        
        elif file_type in ['typescript', 'javascript']:
            # TypeScript/JavaScript files
            extensions = ['.ts', '.tsx', '.js', '.jsx', '.mjs'] if file_type == 'typescript' else ['.js', '.jsx', '.mjs']
            
            for ext in extensions:
                paths.append(os.path.join(directory, *module_parts[:-1], module_parts[-1] + ext))
            
            # Index files
            for ext in extensions:
                paths.append(os.path.join(directory, *module_parts, 'index' + ext))
        
        return paths
    
    def _format_error_message(self, module_name: str, level: int, file_path: str) -> str:
        """Format error message based on import type and language."""
        file_type = self._get_file_type(file_path)
        
        if level > 0:
            return f"Unresolvable relative import target '{module_name}'"
        else:
            return f"Unresolvable import target '{module_name}'"
    def _looks_like_external(self, module_name: str, file_path: str) -> bool:
        """
        Heuristic to determine if a module looks like it should be external.
        Used when ignore_external=True to avoid flagging likely third-party imports.
        """
        file_type = self._get_file_type(file_path)
        
        # Skip relative imports (they should be internal)
        if module_name.startswith('.'):
            return False
        
        if file_type == 'python':
            # Common Python third-party packages
            python_externals = [
                # Data science
                'numpy', 'pandas', 'scipy', 'matplotlib', 'sklearn', 'seaborn', 'plotly',
                # Web frameworks
                'django', 'flask', 'fastapi', 'tornado', 'pyramid', 'bottle',
                # Testing
                'pytest', 'unittest', 'nose', 'mock', 'hypothesis',
                # Utilities
                'requests', 'click', 'pydantic', 'sqlalchemy', 'celery', 'redis',
                # Development
                'black', 'flake8', 'mypy', 'pylint', 'isort',
                # Standard library (shouldn't be missing, but might be)
                'os', 'sys', 'json', 'datetime', 'collections', 'itertools', 'functools'
            ]
            first_part = module_name.split('.')[0].lower()
            return first_part in python_externals
        
        elif file_type in ['typescript', 'javascript']:
            # Common Node.js/npm packages
            js_externals = [
                # React ecosystem
                'react', 'react-dom', 'react-router', 'redux', 'react-redux',
                # Vue ecosystem  
                'vue', 'vuex', 'vue-router',
                # Angular
                '@angular', 'angular',
                # Utilities
                'lodash', 'underscore', 'moment', 'axios', 'fetch',
                # Build tools
                'webpack', 'babel', 'typescript', 'eslint', 'prettier',
                # Testing
                'jest', 'mocha', 'chai', 'sinon', 'enzyme',
                # Node.js built-ins
                'fs', 'path', 'os', 'crypto', 'http', 'https', 'url', 'util'
            ]
            
            # Check for scoped packages (@scope/package)
            if module_name.startswith('@'):
                return True
            
            first_part = module_name.split('.')[0].split('/')[0].lower()
            return first_part in js_externals
        
        return False
    
    def _generate_suggestions(self, module_name: str, level: int, tried_paths: List[str], file_path: str) -> List[str]:
        """Generate helpful suggestions for fixing missing imports."""
        suggestions = []
        file_type = self._get_file_type(file_path)
        
        # Check for similar files in tried paths
        for tried_path in tried_paths[:5]:
            directory = os.path.dirname(tried_path)
            if os.path.isdir(directory):
                similar_files = self._find_similar_files(directory, os.path.basename(tried_path), file_type)
                for similar in similar_files:
                    suggestions.append(f"Did you mean '{similar}'?")
                    if len(suggestions) >= 2:  # Limit similarity suggestions
                        break
        
        # Language-specific suggestions
        if file_type == 'python':
            if level > 0:
                suggestions.append("Check if the relative import path is correct")
                suggestions.append("Verify the package structure exists")
            else:
                suggestions.append("Check if the module is installed (pip install)")
                suggestions.append("Verify the module name spelling")
                
        elif file_type in ['typescript', 'javascript']:
            if module_name.startswith('.'):
                suggestions.append("Check if the relative file path exists")
                suggestions.append("Verify file extensions (.ts, .js, .tsx, .jsx)")
            else:
                suggestions.append("Check if the package is installed (npm install)")
                suggestions.append("Verify the package name in package.json")
        
        # Generic suggestions
        if not suggestions:
            suggestions.extend([
                "Check if the import path is correct",
                "Verify the target file exists",
                "Ensure proper file extensions"
            ])
        
        return suggestions[:4]  # Limit to 4 suggestions
    
    def _find_similar_files(self, directory: str, target_name: str, file_type: str) -> List[str]:
        """Find files similar to the target name."""
        if not os.path.isdir(directory):
            return []
        
        try:
            files = os.listdir(directory)
            similar = []
            
            # Remove extension from target for comparison
            target_base = os.path.splitext(target_name)[0]
            
            for file in files:
                if file.startswith('.'):
                    continue
                    
                file_base = os.path.splitext(file)[0]
                
                # Check for appropriate file types
                if file_type == 'python' and not file.endswith('.py'):
                    continue
                elif file_type in ['typescript', 'javascript'] and not any(file.endswith(ext) for ext in ['.ts', '.tsx', '.js', '.jsx', '.mjs']):
                    continue
                
                # Simple similarity check
                if self._similar_name(target_base, file_base):
                    similar.append(file_base)
            
            return similar[:2]  # Limit to 2 similar files
            
        except OSError:
            return []
    
    def _similar_name(self, name1: str, name2: str) -> bool:
        """Simple similarity check for module names."""
        if len(name1) != len(name2):
            # Allow length difference of 1 for common typos
            if abs(len(name1) - len(name2)) != 1:
                return False
        
        # Allow 1 character difference for names > 3 chars
        if min(len(name1), len(name2)) <= 3:
            return name1.lower() == name2.lower()
        
        # Count differences
        shorter = name1 if len(name1) <= len(name2) else name2
        longer = name2 if len(name1) <= len(name2) else name1
        
        differences = 0
        i = j = 0
        
        while i < len(shorter) and j < len(longer):
            if shorter[i].lower() != longer[j].lower():
                differences += 1
                if differences > 1:
                    return False
                # Skip character in longer string for length difference
                if len(shorter) != len(longer):
                    j += 1
                    continue
            i += 1
            j += 1
        
        # Account for remaining characters in longer string
        differences += len(longer) - j
        
        return differences <= 1


# Export rule in RULES list for auto-discovery
RULES = [ImportsMissingFileTargetRule]


