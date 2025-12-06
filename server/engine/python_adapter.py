"""
Minimal Python language adapter for tree-sitter.
"""
import os
import sys
from typing import List, Tuple, Any, Optional, Dict
import tree_sitter
from .types import LanguageAdapter


class PythonAdapter(LanguageAdapter):
    """Tree-sitter adapter for Python language."""
    
    def __init__(self, parser_path: Optional[str] = None):
        """Initialize Python adapter with tree-sitter parser."""
        self._parser = None
        self._parser_path = parser_path
        
    @property
    def language_id(self) -> str:
        """Return the language identifier."""
        return "python"
    
    @property
    def file_extensions(self) -> Tuple[str, ...]:
        """Return supported file extensions."""
        return (".py", ".pyi")
    
    def _get_parser(self):
        """Get or create the tree-sitter parser."""
        if self._parser is None:
            try:
                # Use tree-sitter-python package if available
                import tree_sitter
                from tree_sitter_python import language
                
                PYTHON_LANGUAGE = tree_sitter.Language(language())
                
                self._parser = tree_sitter.Parser()
                self._parser.language = PYTHON_LANGUAGE
                print(f"Debug: Python parser initialized successfully", file=sys.stderr)
            except ImportError as e:
                print(f"Warning: tree-sitter-python not available: {e}", file=sys.stderr)
                self._parser = None
            except Exception as e:
                print(f"Warning: Could not initialize Python parser: {e}", file=sys.stderr)
                self._parser = None
        
        return self._parser
    
    def parse(self, text) -> Any:
        """Parse text and return a Tree-sitter tree."""
        parser = self._get_parser()
        if parser is None:
            return None
        
        # Handle both string and bytes input
        if isinstance(text, str):
            text_bytes = text.encode('utf-8')
        else:
            text_bytes = text  # Already bytes
        
        return parser.parse(text_bytes)
    
    def list_files(self, paths: List[str]) -> List[str]:
        """List all Python files in the given paths."""
        python_files = []
        
        for path in paths:
            if os.path.isfile(path):
                if any(path.endswith(ext) for ext in self.file_extensions):
                    python_files.append(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Skip common ignore directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules']]
                    
                    for file in files:
                        if any(file.endswith(ext) for ext in self.file_extensions):
                            python_files.append(os.path.join(root, file))
        
        return python_files
    
    def node_text(self, text: str, start_byte: int, end_byte: int) -> str:
        """Extract text between byte offsets."""
        try:
            return text.encode('utf-8')[start_byte:end_byte].decode('utf-8')
        except (UnicodeDecodeError, IndexError):
            return ""
    
    def enclosing_function(self, tree: Any, byte_offset: int) -> Optional[Dict[str, Any]]:
        """Find the function enclosing the given byte offset."""
        # Basic implementation - walk up the tree to find function_definition
        if tree is None:
            return None
        
        def find_enclosing_function(node):
            if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                if node.start_byte <= byte_offset <= node.end_byte:
                    if hasattr(node, 'type') and node.type == 'function_definition':
                        # Found enclosing function
                        name_node = None
                        if hasattr(node, 'children'):
                            for child in node.children:
                                if hasattr(child, 'type') and child.type == 'identifier':
                                    name_node = child
                                    break
                        
                        return {
                            'name': name_node.text.decode('utf-8') if name_node and hasattr(name_node, 'text') else 'unknown',
                            'start_byte': node.start_byte,
                            'end_byte': node.end_byte
                        }
                    
                    # Check children
                    if hasattr(node, 'children'):
                        for child in node.children:
                            result = find_enclosing_function(child)
                            if result:
                                return result
            return None
        
        return find_enclosing_function(tree.root_node if hasattr(tree, 'root_node') else tree)
    
    def byte_to_linecol(self, text: str, byte: int) -> Tuple[int, int]:
        """Convert byte offset to (line, column) 1-based."""
        try:
            text_bytes = text.encode('utf-8')
            if byte > len(text_bytes):
                byte = len(text_bytes)
            
            lines = text_bytes[:byte].decode('utf-8', errors='ignore').split('\n')
            line = len(lines)
            col = len(lines[-1]) + 1 if lines else 1
            return (line, col)
        except Exception:
            return (1, 1)
    
    def line_col_to_byte(self, text: str, line: int, col: int) -> int:
        """Convert (line, column) 1-based to byte offset."""
        try:
            lines = text.split('\n')
            if line > len(lines):
                return len(text.encode('utf-8'))
            
            byte_offset = 0
            for i in range(line - 1):
                if i < len(lines):
                    byte_offset += len(lines[i].encode('utf-8')) + 1  # +1 for newline
            
            if line <= len(lines):
                line_text = lines[line - 1]
                col_offset = min(col - 1, len(line_text))
                byte_offset += len(line_text[:col_offset].encode('utf-8'))
            
            return byte_offset
        except Exception:
            return 0
    
    def get_source_slice(self, text: str, node_range) -> str:
        """Get source text for a node range (start_byte, end_byte)."""
        if hasattr(node_range, 'start_byte') and hasattr(node_range, 'end_byte'):
            return self.node_text(text, node_range.start_byte, node_range.end_byte)
        elif isinstance(node_range, tuple) and len(node_range) == 2:
            return self.node_text(text, node_range[0], node_range[1])
        else:
            return ""
    
    def iter_param_defaults(self, tree):
        """Iterate over function parameters with default values."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'function_definition':
                # Find the parameters node
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'parameters':
                        # Look for default_parameter nodes
                        for param_child in child.children:
                            if hasattr(param_child, 'type') and param_child.type == 'default_parameter':
                                # Extract parameter name and default value
                                param_name = None
                                default_value = None
                                default_kind = None
                                
                                for default_child in param_child.children:
                                    if hasattr(default_child, 'type'):
                                        if default_child.type == 'identifier':
                                            param_name = default_child.text.decode('utf-8')
                                        elif default_child.type in ['list', 'dictionary', 'set']:
                                            default_kind = {'list': 'list', 'dictionary': 'dict', 'set': 'set'}.get(default_child.type, 'unknown')
                                            default_value = default_child.text.decode('utf-8')
                                        elif default_child.type == 'call' and hasattr(default_child, 'children'):
                                            # Handle set() calls
                                            first_child = default_child.children[0] if default_child.children else None
                                            if (first_child and hasattr(first_child, 'type') and 
                                                first_child.type == 'identifier' and 
                                                first_child.text.decode('utf-8') == 'set'):
                                                default_kind = 'set'
                                                default_value = default_child.text.decode('utf-8')
                                
                                if param_name and default_kind:
                                    # Create a parameter info object
                                    param_info = type('ParamInfo', (), {
                                        'param': param_name,
                                        'default_kind': default_kind,
                                        'default_value': default_value,
                                        'range': (param_child.start_byte, param_child.end_byte)
                                    })()
                                    yield param_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_await_expressions(self, tree):
        """Iterate over await expressions for the async_mismatch_await_in_sync rule."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'await':
                # Check if this is the outer await expression (has children)
                # vs the inner await keyword (no children or simple text)
                if hasattr(node, 'children') and len(node.children) > 1:
                    # This is the outer await expression node that contains the whole expression
                    await_info = type('AwaitInfo', (), {
                        'range': (node.start_byte, node.end_byte)
                    })()
                    yield await_info
                    # Don't recurse into children to avoid the inner await keyword
                    return
            
            # Visit children recursively for non-await nodes
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_functions(self, tree):
        """Iterate over function definitions for various rules."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'function_definition':
                # Extract function information
                func_name = 'anonymous'
                is_async = False
                
                for child in node.children:
                    if hasattr(child, 'type'):
                        if child.type == 'async':
                            is_async = True
                        elif child.type == 'identifier':
                            func_name = child.text.decode('utf-8')
                
                func_info = type('FunctionInfo', (), {
                    'name': func_name,
                    'is_async': is_async,
                    'range': (node.start_byte, node.end_byte)
                })()
                yield func_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_imports(self, tree):
        """Iterate over import statements for import-related rules."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type'):
                if node.type == 'import_statement':
                    # Handle 'import x, y, z' or 'import x'
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'dotted_as_names':
                            # Multiple imports
                            for name_child in child.children:
                                if hasattr(name_child, 'type') and name_child.type == 'dotted_as_name':
                                    module_name = name_child.children[0].text.decode('utf-8') if name_child.children else ''
                                    import_info = type('ImportInfo', (), {
                                        'type': 'import',
                                        'module': module_name,
                                        'range': (name_child.start_byte, name_child.end_byte),
                                        'names': [module_name],
                                        'is_wildcard': False
                                    })()
                                    yield import_info
                        elif hasattr(child, 'type') and child.type == 'dotted_name':
                            # Single import
                            module_name = child.text.decode('utf-8')
                            import_info = type('ImportInfo', (), {
                                'type': 'import',
                                'module': module_name,
                                'range': (child.start_byte, child.end_byte),
                                'names': [module_name],
                                'is_wildcard': False
                            })()
                            yield import_info
                
                elif node.type == 'import_from_statement':
                    # Handle 'from x import y' or 'from x import *'
                    module_name = ''
                    import_names = []
                    is_wildcard = False
                    found_import_keyword = False
                    
                    for child in node.children:
                        if hasattr(child, 'type'):
                            if child.type == 'dotted_name' and not found_import_keyword:
                                # This is the module name (before 'import' keyword)
                                module_name = child.text.decode('utf-8')
                            elif child.type == 'import':
                                found_import_keyword = True
                            elif child.type == 'dotted_name' and found_import_keyword:
                                # This is a single imported name (after 'import' keyword)
                                import_names.append(child.text.decode('utf-8'))
                            elif child.type == 'import_list':
                                # Multiple named imports
                                for name_child in child.children:
                                    if hasattr(name_child, 'type') and name_child.type in ['dotted_name', 'dotted_as_name']:
                                        if name_child.type == 'dotted_name':
                                            import_names.append(name_child.text.decode('utf-8'))
                                        elif name_child.type == 'dotted_as_name':
                                            import_names.append(name_child.children[0].text.decode('utf-8') if name_child.children else '')
                            elif child.type == 'wildcard_import':
                                is_wildcard = True
                                import_names = ['*']
                    
                    import_info = type('ImportInfo', (), {
                        'type': 'from_import',
                        'module': module_name,
                        'range': (node.start_byte, node.end_byte),
                        'names': import_names,
                        'is_wildcard': is_wildcard
                    })()
                    yield import_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def ignored_receiver_names(self):
        """Return names that should be ignored for shadowing detection."""
        # Common names that are acceptable to shadow in Python
        return {
            'self', 'cls', '_', '__', 'args', 'kwargs', 'super'
        }

    def iter_scope_nodes(self, tree: Any):
        """Iterate over scope-defining nodes in the tree."""
        if tree is None:
            return
        
        scope_id = 0
        
        def visit_node(node, parent_scope_id=None):
            nonlocal scope_id
            current_scope_id = None
            
            if hasattr(node, 'type'):
                # Python scope-defining nodes
                if node.type in ['module', 'function_definition', 'class_definition', 'lambda']:
                    current_scope_id = scope_id
                    scope_id += 1
                    
                    scope_kind = {
                        'module': 'module',
                        'function_definition': 'function',
                        'class_definition': 'class',
                        'lambda': 'function'
                    }.get(node.type, 'block')
                    
                    yield {
                        'id': current_scope_id,
                        'kind': scope_kind,
                        'parent_id': parent_scope_id
                    }
            
            # Visit children with current scope as parent
            if hasattr(node, 'children'):
                # Use current_scope_id if this node defined a scope, otherwise use parent_scope_id
                child_parent_id = current_scope_id if current_scope_id is not None else parent_scope_id
                for child in node.children:
                    yield from visit_node(child, child_parent_id)
        
        # Start with module scope
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)

    def iter_symbol_defs(self, tree: Any):
        """Iterate over symbol definitions (variables, functions, classes, imports)."""
        if tree is None:
            return
        
        scope_id = 0
        scope_stack = [0]  # Track current scope
        
        def visit_node(node):
            nonlocal scope_id
            
            if hasattr(node, 'type'):
                # Update scope tracking
                if node.type in ['module', 'function_definition', 'class_definition', 'lambda']:
                    if node.type != 'module':  # Module scope is always 0
                        scope_id += 1
                        scope_stack.append(scope_id)
                
                current_scope = scope_stack[-1]
                
                # Function definitions
                if node.type == 'function_definition':
                    name_node = None
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            name_node = child
                            break
                    
                    if name_node:
                        yield {
                            'name': name_node.text.decode('utf-8'),
                            'kind': 'function',
                            'scope_id': scope_stack[-2] if len(scope_stack) > 1 else 0,  # Defined in parent scope
                            'start': name_node.start_byte,
                            'end': name_node.end_byte,
                            'meta': {}
                        }
                
                # Class definitions
                elif node.type == 'class_definition':
                    name_node = None
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            name_node = child
                            break
                    
                    if name_node:
                        yield {
                            'name': name_node.text.decode('utf-8'),
                            'kind': 'class',
                            'scope_id': scope_stack[-2] if len(scope_stack) > 1 else 0,  # Defined in parent scope
                            'start': name_node.start_byte,
                            'end': name_node.end_byte,
                            'meta': {}
                        }
                
                # Import statements (simplified approach)
                elif node.type == 'import_statement':
                    # Simple import like "import os" or "import os, sys"
                    # Parse the text directly for reliability
                    line_text = node.text.decode('utf-8')
                    if line_text.startswith('import '):
                        modules = line_text[7:].strip()  # Remove "import "
                        # Split by commas for multiple imports
                        for module in modules.split(','):
                            module = module.strip()
                            if ' as ' in module:
                                module_name, alias = module.split(' as ', 1)
                                name_to_bind = alias.strip()
                                module_name = module_name.strip()
                            else:
                                # Use first part of dotted module name
                                module_name = module.strip()
                                name_to_bind = module_name.split('.')[0]
                            
                            if name_to_bind:
                                yield {
                                    'name': name_to_bind,
                                    'kind': 'import',
                                    'scope_id': current_scope,
                                    'start': node.start_byte,
                                    'end': node.end_byte,
                                    'meta': {'module': module_name}
                                }
                
                elif node.type == 'import_from_statement':
                    # From import like "from os import path" or "from typing import Dict, List"
                    # Or multi-line: "from x import (\n    a,\n    b,\n)"
                    line_text = node.text.decode('utf-8')
                    if 'from ' in line_text and ' import ' in line_text:
                        parts = line_text.split(' import ', 1)
                        if len(parts) == 2:
                            from_part = parts[0].replace('from ', '').strip()
                            import_part = parts[1].strip()
                            
                            # Remove parentheses from multi-line imports
                            if import_part.startswith('('):
                                import_part = import_part[1:]
                            if import_part.endswith(')'):
                                import_part = import_part[:-1]
                            
                            # Handle multiple imports (split by comma, clean each name)
                            for import_name in import_part.split(','):
                                # Clean up the import name: strip whitespace, newlines, etc.
                                import_name = import_name.strip().strip('\n\r\t ')
                                
                                # Skip empty entries (from trailing commas or whitespace)
                                if not import_name:
                                    continue
                                
                                if ' as ' in import_name:
                                    original_name, alias = import_name.split(' as ', 1)
                                    name_to_bind = alias.strip()
                                else:
                                    name_to_bind = import_name
                                
                                # Final cleanup - ensure no stray characters
                                name_to_bind = name_to_bind.strip().strip('()')
                                
                                if name_to_bind and name_to_bind != '*' and name_to_bind.isidentifier():
                                    yield {
                                        'name': name_to_bind,
                                        'kind': 'import',
                                        'scope_id': current_scope,
                                        'start': node.start_byte,
                                        'end': node.end_byte,
                                        'meta': {'module': from_part, 'from_import': True}
                                    }
                
                # Assignment statements (basic variable definitions)
                elif node.type == 'assignment':
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            yield {
                                'name': child.text.decode('utf-8'),
                                'kind': 'local',
                                'scope_id': current_scope,
                                'start': child.start_byte,
                                'end': child.end_byte,
                                'meta': {}
                            }
                            break  # Only first identifier for now
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
                
                # Pop scope when leaving scope-defining node
                if hasattr(node, 'type') and node.type in ['function_definition', 'class_definition', 'lambda'] and node.type != 'module':
                    if len(scope_stack) > 1:
                        scope_stack.pop()
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)

    def iter_identifier_refs(self, tree: Any):
        """Iterate over identifier references (uses of names)."""
        if tree is None:
            return
        
        scope_id = 0
        scope_stack = [0]
        
        def visit_node(node):
            nonlocal scope_id
            
            if hasattr(node, 'type'):
                # Update scope tracking
                if node.type in ['module', 'function_definition', 'class_definition', 'lambda']:
                    if node.type != 'module':
                        scope_id += 1
                        scope_stack.append(scope_id)
                
                current_scope = scope_stack[-1]
                
                # Find identifier references (but not definitions)
                if node.type == 'identifier':
                    # Check if this is a reference (not a definition)
                    parent = getattr(node, 'parent', None)
                    is_definition = False
                    
                    if parent and hasattr(parent, 'type'):
                        # Skip if it's part of a definition/declaration
                        if parent.type in ['function_definition', 'class_definition']:
                            # Check if this identifier is the name being defined
                            # For functions/classes, the name is typically the second child
                            if (hasattr(parent, 'children') and len(parent.children) > 1 and 
                                parent.children[1] == node):
                                is_definition = True
                        
                        elif parent.type == 'assignment':
                            # For assignments, check if this is the left-hand side being assigned to
                            if (hasattr(parent, 'children') and len(parent.children) > 0 and 
                                parent.children[0] == node):
                                is_definition = True
                        
                        elif parent.type in ['dotted_name', 'dotted_as_name']:
                            # Check if this is part of an import statement
                            grandparent = getattr(parent, 'parent', None)
                            if (grandparent and hasattr(grandparent, 'type') and 
                                grandparent.type in ['import_statement', 'import_from_statement']):
                                is_definition = True
                    
                    if not is_definition:
                        yield {
                            'name': node.text.decode('utf-8'),
                            'scope_id': current_scope,
                            'byte': node.start_byte,
                            'meta': {}
                        }
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
                
                # Pop scope when leaving scope-defining node
                if hasattr(node, 'type') and node.type in ['function_definition', 'class_definition', 'lambda'] and node.type != 'module':
                    if len(scope_stack) > 1:
                        scope_stack.pop()
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)


# Create default instance
default_python_adapter = PythonAdapter()

