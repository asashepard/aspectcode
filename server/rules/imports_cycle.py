"""
Rule: imports.cycle

Detects circular import dependencies using strongly connected component (SCC) analysis.
Shows minimal cycle path and suggests fixes for breaking cycles.

Supports: Python, TypeScript, JavaScript, Go, Java, C#, Rust
"""

from pathlib import Path
from typing import Iterator, List, Dict, Any, Set, Optional, Tuple
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext, Edit


class ImportsCycleRule:
    """
    Detect circular import dependencies using project import graph SCC analysis.
    
    Examples of cycles:
    
    Simple 2-module cycle:
        # file_a.py
        from file_b import func_b  # Creates cycle
        
        # file_b.py 
        from file_a import func_a  # Completes cycle
    
    Complex multi-module cycle:
        A → B → C → D → A
        
    The rule uses strongly connected component detection to find all cycles
    and reports the minimal cycle path for each problematic import.
    """
    
    @property
    def meta(self) -> RuleMeta:
        return RuleMeta(
            id="imports.cycle",
            category="imports", 
            tier=2,  # Requires project graph
            priority="P1",
            autofix_safety="suggest-only",
            description="Circular import detected",
            langs=["python", "typescript", "javascript", "go", "java", "csharp", "rust"]
        )
    
    @property
    def requires(self) -> Requires:
        return Requires(
            raw_text=True,   # Need text for range calculation
            syntax=True,     # Need syntax tree to find import statements  
            scopes=False,
            project_graph=True  # This rule needs import graph analysis
        )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect import cycles using basic dependency tracking."""
        if not ctx.tree:
            return
            
        # Get language ID
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
            
        # Extract imports from current file
        imports = self._extract_imports(ctx)
        
        # Build simple dependency graph
        if hasattr(ctx, 'file_path') and ctx.file_path:
            current_file = Path(ctx.file_path)
            project_root = self._find_project_root(current_file)
            
            # Check for potential cycles
            for import_target in imports:
                if self._could_create_cycle(current_file, import_target, project_root):
                    # Find the import statement in the file
                    import_nodes = self._find_import_nodes(ctx, import_target)
                    for node in import_nodes:
                        start_byte, end_byte = self._get_node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Importing '{import_target}' may create a circular dependency�this can cause import errors.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )
    
    def _extract_imports(self, ctx):
        """Extract import statements from the current file."""
        imports = []
        file_text = getattr(ctx, 'text', '') or getattr(ctx, 'raw_text', '')
        
        # Simple text-based import extraction
        import_patterns = {
            'python': [
                r'from\s+([\w.]+)\s+import',
                r'import\s+([\w.]+)'
            ],
            'typescript': [
                r'import.*from\s+["\']([^"\']+)["\']',
                r'import\s+["\']([^"\']+)["\']'
            ],
            'javascript': [
                r'import.*from\s+["\']([^"\']+)["\']',
                r'require\(["\']([^"\']+)["\']\)'
            ]
        }
        
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
            
        if language in import_patterns:
            import re
            for pattern in import_patterns[language]:
                matches = re.findall(pattern, file_text)
                imports.extend(matches)
        
        return imports
    
    def _find_project_root(self, current_file):
        """Find the project root directory."""
        path = current_file.parent
        
        # Look for common project indicators
        indicators = ['package.json', 'pyproject.toml', 'setup.py', '.git', 'Cargo.toml']
        
        while path.parent != path:  # Not at filesystem root
            if any((path / indicator).exists() for indicator in indicators):
                return path
            path = path.parent
            
        return current_file.parent  # Fallback to file's directory
    
    def _could_create_cycle(self, current_file, import_target, project_root):
        """Simple heuristic to detect potential cycles."""
        # If importing from a parent directory that could import back
        if '..' in import_target:
            return True
        
        # If importing from a sibling that has the same base name
        current_stem = current_file.stem
        if current_stem.lower() in import_target.lower():
            return True
            
        return False
    
    def _find_import_nodes(self, ctx, import_target):
        """Find AST nodes for specific import."""
        nodes = []
        if hasattr(ctx, 'tree') and ctx.tree:
            for node in self._walk_tree(ctx.tree.root_node):
                node_text = self._get_node_text(node, ctx)
                if import_target in node_text and any(keyword in node_text for keyword in ['import', 'require', 'from']):
                    nodes.append(node)
        return nodes
    
    def _walk_tree(self, node):
        """Walk the syntax tree."""
        yield node
        for child in getattr(node, 'children', []):
            yield from self._walk_tree(child)
    
    def _get_node_text(self, node, ctx):
        """Get text from a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        return ""
    
    def _get_node_span(self, node):
        """Get byte span of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte + 10)
        return start_byte, end_byte

class ImportsCycleSimpleRule:
    """Find circular imports involving this file."""
    
    meta = RuleMeta(
        id="imports.cycle.simple",
        category="imports", 
        tier=1,
        priority="P1",
        autofix_safety="suggest-only",
        description="Basic circular import detection using direct import analysis",
        langs=["python", "typescript", "javascript", "go", "java", "csharp", "rust"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=False,
        project_graph=False
    )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect import cycles using basic dependency tracking."""
        if not ctx.tree:
            return
            
        # Get language ID
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
            
        # Extract imports from current file
        imports = self._extract_imports(ctx)
        
        # Build simple dependency graph
        if hasattr(ctx, 'file_path') and ctx.file_path:
            current_file = Path(ctx.file_path)
            project_root = self._find_project_root(current_file)
            
            # Check for potential cycles
            for import_target in imports:
                if self._could_create_cycle(current_file, import_target, project_root):
                    # Find the import statement in the file
                    import_nodes = self._find_import_nodes(ctx, import_target)
                    for node in import_nodes:
                        start_byte, end_byte = self._get_node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Importing '{import_target}' may create a circular dependency�this can cause import errors.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )
    
    def _extract_imports(self, ctx):
        """Extract import statements from the current file."""
        imports = []
        file_text = getattr(ctx, 'text', '') or getattr(ctx, 'raw_text', '')
        
        # Simple text-based import extraction
        import_patterns = {
            'python': [
                r'from\s+([\w.]+)\s+import',
                r'import\s+([\w.]+)'
            ],
            'typescript': [
                r'import.*from\s+["\']([^"\']+)["\']',
                r'import\s+["\']([^"\']+)["\']'
            ],
            'javascript': [
                r'import.*from\s+["\']([^"\']+)["\']',
                r'require\(["\']([^"\']+)["\']\)'
            ]
        }
        
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
            
        if language in import_patterns:
            import re
            for pattern in import_patterns[language]:
                matches = re.findall(pattern, file_text)
                imports.extend(matches)
        
        return imports
    
    def _find_project_root(self, current_file):
        """Find the project root directory."""
        path = current_file.parent
        
        # Look for common project indicators
        indicators = ['package.json', 'pyproject.toml', 'setup.py', '.git', 'Cargo.toml']
        
        while path.parent != path:  # Not at filesystem root
            if any((path / indicator).exists() for indicator in indicators):
                return path
            path = path.parent
            
        return current_file.parent  # Fallback to file's directory
    
    def _could_create_cycle(self, current_file, import_target, project_root):
        """Simple heuristic to detect potential cycles."""
        # If importing from a parent directory that could import back
        if '..' in import_target:
            return True
        
        # If importing from a sibling that has the same base name
        current_stem = current_file.stem
        if current_stem.lower() in import_target.lower():
            return True
            
        return False
    
    def _find_import_nodes(self, ctx, import_target):
        """Find AST nodes for specific import."""
        nodes = []
        if hasattr(ctx, 'tree') and ctx.tree:
            for node in self._walk_tree(ctx.tree.root_node):
                node_text = self._get_node_text(node, ctx)
                if import_target in node_text and any(keyword in node_text for keyword in ['import', 'require', 'from']):
                    nodes.append(node)
        return nodes
    
    def _walk_tree(self, node):
        """Walk the syntax tree."""
        yield node
        for child in getattr(node, 'children', []):
            yield from self._walk_tree(child)
    
    def _get_node_text(self, node, ctx):
        """Get text from a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        return ""
    
    def _get_node_span(self, node):
        """Get byte span of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte + 10)
        return start_byte, end_byte

class ImportsCycleAdvancedRule:
    """Find circular imports involving this file."""
    
    meta = RuleMeta(
        id="imports.cycle.advanced",
        category="imports", 
        tier=2,
        priority="P0",
        autofix_safety="suggest-only",
        description="Advanced circular import detection using project graph analysis",
        # Only support languages with iter_imports in their adapter
        langs=["python", "typescript", "javascript"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=False,
        project_graph=True
    )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        if not ctx.project_graph:
            return
        
        # Check if this is a supported file type
        if not self._is_supported_file(ctx.file_path):
            return
        
        # Handle both dict and tuple formats for project_graph
        pg = ctx.project_graph
        if isinstance(pg, dict):
            resolver = pg.get('resolver')
            import_graph = pg.get('import_graph')
            symbol_index = pg.get('symbol_index')
        else:
            # Legacy tuple format
            resolver, import_graph, symbol_index = pg
        
        if not resolver or not import_graph:
            return
        
        # Get configuration
        config = getattr(ctx, 'config', {})
        ignore_external = config.get('imports.cycle.ignore_external', True)
        
        # Get the canonical module name for this file
        current_module = resolver.canonical_module_for_file(ctx.file_path)
        if not current_module:
            return
        
        # Compute SCCs (strongly connected components)
        sccs = import_graph.sccs()
        
        # Find SCCs that contain cycles (more than 1 module) and include current module
        for scc in sccs:
            if len(scc) > 1 and current_module in scc:
                # This file is part of a cycle
                
                # Apply ignore_external filter by removing external modules from SCC
                if ignore_external:
                    project_scc = [mod for mod in scc if import_graph.module_file_path(mod) is not None]
                    if len(project_scc) <= 1:
                        continue  # No cycle in project modules
                    scc = project_scc
                
                # Get minimal cycle example
                cycle_edges = import_graph.minimal_cycle_example(scc)
                
                # Find import statements that contribute to the cycle
                cycle_import_ranges = self._find_cycle_import_ranges(ctx, scc, current_module)
                
                if cycle_import_ranges:
                    # Create one finding per problematic import statement
                    for start_byte, end_byte, target_module in cycle_import_ranges:
                        finding = Finding(
                            rule=self.meta.id,
                            message=self._format_cycle_message(scc, cycle_edges, target_module),
                            severity="error", 
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            autofix=None,  # Suggest-only
                            meta={
                                "current_module": current_module,
                                "cycle_modules": scc,
                                "cycle_size": len(scc),
                                "minimal_cycle": cycle_edges,
                                "target_module": target_module,
                                "cycle_description": self._describe_cycle(cycle_edges),
                                "suggestions": self._generate_cycle_suggestions(scc, cycle_edges, current_module)
                            }
                        )
                        yield finding
                else:
                    # Fallback: create a whole-file finding if we can't find specific imports
                    finding = Finding(
                        rule=self.meta.id,
                        message=self._format_cycle_message(scc, cycle_edges),
                        severity="error", 
                        file=ctx.file_path,
                        start_byte=0,  # Whole file issue
                        end_byte=len(ctx.text) if ctx.text else 1,
                        autofix=None,  # Suggest-only
                        meta={
                            "current_module": current_module,
                            "cycle_modules": scc,
                            "cycle_size": len(scc),
                            "minimal_cycle": cycle_edges,
                            "cycle_description": self._describe_cycle(cycle_edges),
                            "suggestions": self._generate_cycle_suggestions(scc, cycle_edges, current_module)
                        }
                    )
                    yield finding
                
                # Only report one cycle per file to avoid spam
                break
    
    def _is_supported_file(self, file_path: str) -> bool:
        """Check if the file type is supported by this rule."""
        supported_extensions = {
            '.py',      # Python
            '.ts',      # TypeScript 
            '.tsx',     # TypeScript React
            '.js',      # JavaScript
            '.jsx',     # JavaScript React
            '.mjs',     # ES Module JavaScript
            '.go',      # Go
            '.java',    # Java
            '.cs',      # C#
            '.rs',      # Rust
        }
        
        import os
        ext = os.path.splitext(file_path)[1].lower()
        return ext in supported_extensions
    
    def _find_cycle_import_ranges(self, ctx: RuleContext, cycle_modules: List[str], 
                                current_module: str) -> List[Tuple[int, int, str]]:
        """Find byte ranges of import statements that contribute to the cycle."""
        if not ctx.tree:
            return []
        
        # We need to find import statements in this file that import modules in the cycle
        cycle_import_ranges = []
        
        # Get the adapter to parse imports
        try:
            adapter = ctx.adapter
            if not adapter:
                return []
            
            # Parse import statements using the adapter
            # Different languages have different import syntaxes
            file_ext = self._get_file_extension(ctx.file_path)
            
            for import_info in adapter.iter_imports(ctx.tree):
                imported_module = self._extract_module_from_import(import_info, file_ext)
                
                if imported_module:
                    # Resolve relative/package imports to canonical module names
                    resolved_module = self._resolve_import_module(
                        imported_module, current_module, file_ext
                    )
                    
                    # Check if this imported module is in the cycle
                    if resolved_module in cycle_modules and resolved_module != current_module:
                        # This import contributes to the cycle
                        start_byte, end_byte = self._get_import_range(import_info)
                        if end_byte > start_byte:  # Valid range
                            cycle_import_ranges.append((start_byte, end_byte, resolved_module))
            
        except Exception:
            # Silently handle any parsing errors and fall back to whole-file detection
            pass
        
        return cycle_import_ranges
    
    def _get_file_extension(self, file_path: str) -> str:
        """Get the file extension to determine language."""
        import os
        return os.path.splitext(file_path)[1].lower()
    
    def _extract_module_from_import(self, import_info, file_ext: str) -> Optional[str]:
        """Extract module name from import info, handling different languages."""
        # Try common attribute names used by different adapters
        for attr in ['module', 'target', 'path', 'source']:
            if hasattr(import_info, attr):
                value = getattr(import_info, attr)
                if value:  # Only return if the value is not None/empty
                    return str(value)
        
        # Language-specific extraction if needed
        if file_ext in ['.py']:
            # Python: from module import name, import module
            if hasattr(import_info, 'from_module') and import_info.from_module:
                return str(import_info.from_module)
            elif hasattr(import_info, 'import_name') and import_info.import_name:
                return str(import_info.import_name)
        
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx', '.mjs']:
            # JavaScript/TypeScript: import ... from 'module', require('module')
            if hasattr(import_info, 'source') and import_info.source:
                return str(import_info.source)
            elif hasattr(import_info, 'specifier') and import_info.specifier:
                return str(import_info.specifier)
        
        elif file_ext in ['.go']:
            # Go: import "package/path"
            if hasattr(import_info, 'package_path') and import_info.package_path:
                return str(import_info.package_path)
        
        elif file_ext in ['.java']:
            # Java: import package.Class;
            if hasattr(import_info, 'class_name') and import_info.class_name:
                return str(import_info.class_name)
            elif hasattr(import_info, 'package_name') and import_info.package_name:
                return str(import_info.package_name)
        
        elif file_ext in ['.cs']:
            # C#: using Namespace;
            if hasattr(import_info, 'namespace') and import_info.namespace:
                return str(import_info.namespace)
        
        elif file_ext in ['.rs']:
            # Rust: use module::item;
            if hasattr(import_info, 'module_path') and import_info.module_path:
                return str(import_info.module_path)
        
        return None
    
    def _resolve_import_module(self, imported_module: str, current_module: str, 
                             file_ext: str) -> str:
        """Resolve relative imports to canonical module names."""
        # Python relative imports
        if file_ext == '.py' and imported_module.startswith('.'):
            if current_module:
                current_parts = current_module.split('.')
                if imported_module.startswith('..'):
                    # Parent directory imports
                    dots = len(imported_module) - len(imported_module.lstrip('.'))
                    if dots < len(current_parts):
                        base_parts = current_parts[:-dots] if dots > 0 else current_parts
                        rest = imported_module[dots:].lstrip('.')
                        if rest:
                            return '.'.join(base_parts + [rest])
                        else:
                            return '.'.join(base_parts)
                else:
                    # Single dot - same package
                    rest = imported_module[1:].lstrip('.')
                    if rest:
                        parent_parts = current_module.split('.')[:-1]
                        return '.'.join(parent_parts + [rest])
        
        # JavaScript/TypeScript relative imports
        elif file_ext in ['.js', '.jsx', '.ts', '.tsx', '.mjs'] and imported_module.startswith('.'):
            # Convert ./module or ../module to canonical names
            # This is simplified - real resolution would need the project structure
            if current_module:
                current_parts = current_module.split('/')
                if imported_module.startswith('../'):
                    # Parent directory
                    levels = imported_module.count('../')
                    rest = imported_module.replace('../', '', levels).strip('/')
                    if levels < len(current_parts):
                        base_parts = current_parts[:-levels-1] if levels > 0 else current_parts[:-1]
                        if rest:
                            return '/'.join(base_parts + [rest])
                        else:
                            return '/'.join(base_parts)
                elif imported_module.startswith('./'):
                    # Same directory
                    rest = imported_module[2:]
                    parent_parts = current_module.split('/')[:-1]
                    return '/'.join(parent_parts + [rest])
        
        # Other languages: return as-is for now
        # Real implementations would need language-specific resolution
        return imported_module
    
    def _get_import_range(self, import_info) -> Tuple[int, int]:
        """Get byte range of the import statement."""
        # Try common range attributes
        if hasattr(import_info, 'range') and import_info.range:
            if isinstance(import_info.range, tuple) and len(import_info.range) == 2:
                return import_info.range
        
        # Try start/end attributes
        start_byte = getattr(import_info, 'start_byte', 0)
        end_byte = getattr(import_info, 'end_byte', 0)
        
        if end_byte > start_byte:
            return (start_byte, end_byte)
        
        # Fallback to position attributes
        start_pos = getattr(import_info, 'start', 0)
        end_pos = getattr(import_info, 'end', 0)
        
        if end_pos > start_pos:
            return (start_pos, end_pos)
        
        return (0, 0)
    
    def _format_cycle_message(self, scc: List[str], cycle_edges: List[tuple], target_module: str = None) -> str:
        """Format a user-friendly cycle message."""
        if target_module:
            # Specific import causing cycle
            return f"Importing '{target_module}' creates a circular dependency—move shared code to a separate module."
        
        if len(cycle_edges) <= 3:
            # Short cycle - show full path
            path_parts = []
            for src, dst in cycle_edges:
                path_parts.append(src)
            # Close the cycle
            if cycle_edges:
                path_parts.append(cycle_edges[0][0])
            
            cycle_path = " → ".join(path_parts)
            return f"Circular import: {cycle_path}—refactor to break the cycle."
        else:
            # Long cycle - summarize
            return f"Circular import involving {len(scc)} modules—refactor to break the cycle."
    
    def _describe_cycle(self, cycle_edges: List[tuple]) -> str:
        """Create a human-readable cycle description."""
        if not cycle_edges:
            return "Complex cycle detected"
        
        path_parts = []
        for src, dst in cycle_edges:
            path_parts.append(src)
        
        # Close the cycle
        if cycle_edges:
            path_parts.append(cycle_edges[0][0])
        
        return " imports ".join(path_parts)
    
    def _generate_cycle_suggestions(self, scc: List[str], cycle_edges: List[tuple], 
                                  current_module: str) -> List[str]:
        """Generate suggestions for breaking the cycle."""
        suggestions = []
        
        # Common cycle-breaking strategies
        suggestions.extend([
            "Move shared functionality to a separate module",
            "Use import statements inside functions instead of at module level",
            "Reorganize code to eliminate circular dependencies"
        ])
        
        # Specific suggestions based on cycle structure
        if len(scc) == 2:
            # Simple two-module cycle
            other_module = next(mod for mod in scc if mod != current_module)
            suggestions.insert(0, f"Consider merging '{current_module}' and '{other_module}' into a single module")
        
        elif len(scc) <= 4:
            # Small cycle - suggest extracting common interface
            suggestions.insert(0, "Extract common interfaces or base classes to break the cycle")
        
        else:
            # Large cycle - suggests architectural issue
            suggestions.insert(0, "Large cycle detected - consider refactoring the module architecture")
        
        return suggestions[:4]  # Limit to 4 suggestions


# Export rule in RULES list for auto-discovery
RULES = [ImportsCycleRule(), ImportsCycleAdvancedRule()]


