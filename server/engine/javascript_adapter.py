"""
JavaScript language adapter for tree-sitter.
"""
import os
import sys
from typing import List, Tuple, Any, Optional, Dict
import tree_sitter
from .types import LanguageAdapter


def _node_text_to_str(node_text: Any) -> str:
    """Helper to convert tree-sitter node.text to string, handling bytes/str."""
    if node_text is None:
        return ""
    if isinstance(node_text, bytes):
        return node_text.decode('utf-8', errors='ignore')
    return str(node_text)


class JavaScriptAdapter(LanguageAdapter):
    """Tree-sitter adapter for JavaScript language."""
    
    def __init__(self, parser_path: Optional[str] = None):
        """Initialize JavaScript adapter with tree-sitter parser."""
        self._parser = None
        self._parser_path = parser_path
        
    @property
    def language_id(self) -> str:
        """Return the language identifier."""
        return "javascript"
    
    @property
    def file_extensions(self) -> Tuple[str, ...]:
        """Return supported file extensions."""
        return (".js", ".jsx", ".mjs")
    
    def _get_parser(self):
        """Get or create the tree-sitter parser."""
        if self._parser is None:
            try:
                # Use tree-sitter-javascript package if available
                import tree_sitter
                from tree_sitter_javascript import language
                
                JAVASCRIPT_LANGUAGE = tree_sitter.Language(language())
                
                self._parser = tree_sitter.Parser()
                self._parser.language = JAVASCRIPT_LANGUAGE
                print(f"Debug: JavaScript parser initialized successfully", file=sys.stderr)
            except ImportError as e:
                print(f"Warning: tree-sitter-javascript not available: {e}", file=sys.stderr)
                self._parser = None
            except Exception as e:
                print(f"Warning: Could not initialize JavaScript parser: {e}", file=sys.stderr)
                self._parser = None
        
        return self._parser
    
    def parse(self, text: str) -> Any:
        """Parse text and return a Tree-sitter tree."""
        parser = self._get_parser()
        if parser is None:
            return None
        
        # Handle both str and bytes input
        if isinstance(text, bytes):
            text_bytes = text
        elif isinstance(text, str):
            text_bytes = text.encode('utf-8')
        else:
            return None
        
        return parser.parse(text_bytes)
    
    def list_files(self, paths: List[str]) -> List[str]:
        """List all JavaScript files in the given paths."""
        js_files = []
        
        for path in paths:
            if os.path.isfile(path):
                if any(path.endswith(ext) for ext in self.file_extensions):
                    js_files.append(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Skip common ignore directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'node_modules']]
                    
                    for file in files:
                        if any(file.endswith(ext) for ext in self.file_extensions):
                            js_files.append(os.path.join(root, file))
        
        return js_files
    
    def node_text(self, text: str, start_byte: int, end_byte: int) -> str:
        """Extract text between byte offsets."""
        try:
            if isinstance(text, bytes):
                text_bytes = text
            else:
                text_bytes = text.encode('utf-8')
            return text_bytes[start_byte:end_byte].decode('utf-8')
        except (UnicodeDecodeError, IndexError):
            return ""
    
    def enclosing_function(self, tree: Any, byte_offset: int) -> Optional[Dict[str, Any]]:
        """Find the function enclosing the given byte offset."""
        if tree is None:
            return None
        
        def find_enclosing_function(node):
            if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                if node.start_byte <= byte_offset <= node.end_byte:
                    if hasattr(node, 'type') and node.type in ['function_declaration', 'function_expression', 'arrow_function']:
                        # Found enclosing function
                        name_node = None
                        if hasattr(node, 'children'):
                            for child in node.children:
                                if hasattr(child, 'type') and child.type == 'identifier':
                                    name_node = child
                                    break
                        
                        return {
                            'name': name_node.text.decode('utf-8') if name_node and hasattr(name_node, 'text') else 'anonymous',
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
            # Handle bytes/string
            if isinstance(text, bytes):
                text_str = text.decode('utf-8')
            else:
                text_str = text
            
            lines = text_str.split('\n')
            if line > len(lines):
                # Out of bounds - return total byte length
                if isinstance(text, bytes):
                    return len(text)
                else:
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
    
    def iter_binary_ops(self, tree):
        """Iterate over binary operations for rules like ts_loose_equality."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'binary_expression':
                # Extract the operator and operands from the binary expression
                left_node = None
                right_node = None
                operator = None
                
                for child in node.children:
                    if hasattr(child, 'type'):
                        if child.type in ['identifier', 'number', 'string', 'member_expression', 'call_expression', 'parenthesized_expression']:
                            if left_node is None:
                                left_node = child
                            else:
                                right_node = child
                        elif hasattr(child, 'text'):
                            # The operator is typically text nodes like '==', '!=', etc.
                            text = child.text.decode('utf-8')
                            if text in ['==', '!=', '===', '!==', '+', '-', '*', '/', '%', '<', '>', '<=', '>=', '&&', '||']:
                                operator = text
                
                if operator and left_node and right_node:
                    # Create binary operation info with left and right ranges
                    op_info = type('BinaryOpInfo', (), {
                        'operator': operator,
                        'range': (node.start_byte, node.end_byte),
                        'left_range': (left_node.start_byte, left_node.end_byte),
                        'right_range': (right_node.start_byte, right_node.end_byte)
                    })()
                    yield op_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_loose_equality_operators(self, tree):
        """Iterate over loose equality operators (== and !=) for the ts_loose_equality rule."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'binary_expression':
                # Check if this is a loose equality operator
                for child in node.children:
                    if hasattr(child, 'type') and child.type in ['==', '!=']:
                        # Found a loose equality operator
                        operator_info = type('OperatorInfo', (), {
                            'operator': child.text.decode('utf-8'),
                            'range': (child.start_byte, child.end_byte),
                            'full_expression_range': (node.start_byte, node.end_byte)
                        })()
                        yield operator_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_symbol_defs(self, tree):
        """
        Iterate over symbol definitions (functions, classes, variables, etc.).
        
        Yields dictionaries with:
        - name: Symbol name
        - kind: "function", "class", "method", "variable", "const"
        - start: Start byte position
        - end: End byte position
        - scope_kind: "module", "class", "function"
        - scope_id: Numeric scope id for scope analysis
        - meta: Additional metadata
        """
        if tree is None:
            return
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        
        # Scope-creating node types
        scope_types = {
            'program', 'function_declaration', 'function_expression',
            'arrow_function', 'method_definition', 'class_declaration',
            'class_expression', 'generator_function', 'generator_function_declaration',
            'statement_block'  # Added statement_block for function bodies
        }
        
        # Build scope_id map: node.id -> scope_id
        scope_id_map = {}  # node.id -> scope_id
        next_scope_id = [0]  # Use list for mutable counter in nested function
        
        def build_scope_map(node, current_scope_id):
            if not hasattr(node, 'type'):
                return
            
            # Check if this node creates a new scope
            if node.type in scope_types:
                scope_id_map[node.id] = next_scope_id[0]
                my_scope_id = next_scope_id[0]
                next_scope_id[0] += 1
            else:
                my_scope_id = current_scope_id
            
            # Recursively process children
            if hasattr(node, 'children'):
                for child in node.children:
                    build_scope_map(child, my_scope_id)
        
        # Build the scope map
        build_scope_map(root_node, 0)
        
        def find_enclosing_scope_id(node):
            """Find the scope_id for the scope that contains this node."""
            current = node
            while current is not None:
                if hasattr(current, 'id') and current.id in scope_id_map:
                    return scope_id_map[current.id]
                current = getattr(current, 'parent', None)
            return 0
        
        def visit_node(node, parent_scope='module', parent_class=None, current_scope_id=0):
            if not hasattr(node, 'type'):
                return
            
            # Check if this node has a scope - if so, use that scope_id for children
            if hasattr(node, 'id') and node.id in scope_id_map:
                current_scope_id = scope_id_map[node.id]
            
            # Function declarations: function foo() {}
            if node.type == 'function_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    # Function is defined in outer scope (parent's scope)
                    func_scope_id = find_enclosing_scope_id(node.parent) if hasattr(node, 'parent') and node.parent else 0
                    yield {
                        'name': _node_text_to_str(name_node.text),
                        'kind': 'function',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': func_scope_id,
                        'meta': {}
                    }
            
            # Class declarations: class Foo {}
            elif node.type == 'class_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    class_name = _node_text_to_str(name_node.text)
                    class_scope_id = find_enclosing_scope_id(node.parent) if hasattr(node, 'parent') and node.parent else 0
                    yield {
                        'name': class_name,
                        'kind': 'class',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': class_scope_id,
                        'meta': {}
                    }
                    
                    # Visit class body for methods
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'class_body':
                            yield from visit_node(child, parent_scope='class', parent_class=class_name, current_scope_id=current_scope_id)
            
            # Method definitions: foo() {} (inside classes)
            elif node.type == 'method_definition':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'property_identifier':
                        name_node = child
                        break
                
                if name_node:
                    method_scope_id = find_enclosing_scope_id(node.parent) if hasattr(node, 'parent') and node.parent else current_scope_id
                    yield {
                        'name': _node_text_to_str(name_node.text),
                        'kind': 'method',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': method_scope_id,
                        'meta': {'parent_class': parent_class} if parent_class else {}
                    }
            
            # Variable declarations: const/let/var x = ...
            elif node.type in ['variable_declaration', 'lexical_declaration']:
                kind_keyword = 'variable'
                for child in node.children:
                    if hasattr(child, 'type') and child.type in ['const', 'let', 'var']:
                        kind_keyword = _node_text_to_str(child.text)
                        break
                
                # Find variable_declarator children
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'variable_declarator':
                        name_node = None
                        for subchild in child.children:
                            if hasattr(subchild, 'type') and subchild.type == 'identifier':
                                name_node = subchild
                                break
                        
                        if name_node:
                            yield {
                                'name': _node_text_to_str(name_node.text),
                                'kind': 'const' if kind_keyword == 'const' else ('let' if kind_keyword == 'let' else 'variable'),
                                'start': child.start_byte,
                                'end': child.end_byte,
                                'scope_kind': parent_scope,
                                'scope_id': current_scope_id,
                                'meta': {'declaration_type': kind_keyword}
                            }
            
            # Arrow functions assigned to variables: const foo = () => {}
            # (handled via variable_declarator above)
            
            # Import declarations: import X from 'module', import { a, b } from 'module'
            elif node.type == 'import_statement':
                module_name = ''
                import_names = []
                
                for child in node.children:
                    if hasattr(child, 'type'):
                        # Get module source string
                        if child.type == 'string':
                            text = _node_text_to_str(child.text)
                            module_name = text.strip('"\'')
                        
                        # import clause contains the imported names
                        elif child.type == 'import_clause':
                            for clause_child in child.children:
                                if hasattr(clause_child, 'type'):
                                    # Default import: import X from 'module'
                                    if clause_child.type == 'identifier':
                                        import_names.append({
                                            'name': _node_text_to_str(clause_child.text),
                                            'start': clause_child.start_byte,
                                            'end': clause_child.end_byte
                                        })
                                    
                                    # Named imports: import { a, b } from 'module'
                                    elif clause_child.type == 'named_imports':
                                        for spec_child in clause_child.children:
                                            if hasattr(spec_child, 'type') and spec_child.type == 'import_specifier':
                                                # Get the local name (alias or original)
                                                local_name = None
                                                for name_child in spec_child.children:
                                                    if hasattr(name_child, 'type') and name_child.type == 'identifier':
                                                        local_name = {
                                                            'name': _node_text_to_str(name_child.text),
                                                            'start': name_child.start_byte,
                                                            'end': name_child.end_byte
                                                        }
                                                        # Last identifier is the local name (after 'as')
                                                if local_name:
                                                    import_names.append(local_name)
                                    
                                    # Namespace import: import * as X from 'module'
                                    elif clause_child.type == 'namespace_import':
                                        for ns_child in clause_child.children:
                                            if hasattr(ns_child, 'type') and ns_child.type == 'identifier':
                                                import_names.append({
                                                    'name': _node_text_to_str(ns_child.text),
                                                    'start': ns_child.start_byte,
                                                    'end': ns_child.end_byte
                                                })
                
                # Yield each imported name as an import symbol
                for imp in import_names:
                    yield {
                        'name': imp['name'],
                        'kind': 'import',
                        'start': imp['start'],
                        'end': imp['end'],
                        'scope_kind': parent_scope,
                        'scope_id': current_scope_id,
                        'meta': {'module': module_name}
                    }
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child, parent_scope, parent_class, current_scope_id)
        
        yield from visit_node(root_node, current_scope_id=0)
    
    def iter_imports(self, tree):
        """
        Iterate over import statements for import graph analysis.
        
        Yields ImportInfo objects with:
        - type: "import" or "require"
        - module: Module specifier string
        - range: (start_byte, end_byte)
        - names: List of imported names (empty for side-effect imports)
        - is_wildcard: True for namespace imports (import * as)
        """
        if tree is None:
            return
        
        def visit_node(node):
            if not hasattr(node, 'type'):
                return
            
            # ES6 import declarations: import X from 'module'
            if node.type == 'import_statement':
                module_name = ''
                import_names = []
                is_wildcard = False
                
                for child in node.children:
                    if hasattr(child, 'type'):
                        # import 'module' (side-effect import)
                        if child.type == 'string':
                            module_name = self._extract_string_value(child)
                        
                        # import { a, b } from 'module'
                        elif child.type == 'import_clause':
                            for clause_child in child.children:
                                if hasattr(clause_child, 'type'):
                                    # Default import: import X from 'module'
                                    if clause_child.type == 'identifier':
                                        import_names.append(_node_text_to_str(clause_child.text))
                                    
                                    # Named imports: import { a, b } from 'module'
                                    elif clause_child.type == 'named_imports':
                                        for spec_child in clause_child.children:
                                            if hasattr(spec_child, 'type') and spec_child.type == 'import_specifier':
                                                # Get the imported name
                                                for name_child in spec_child.children:
                                                    if hasattr(name_child, 'type') and name_child.type == 'identifier':
                                                        import_names.append(_node_text_to_str(name_child.text))
                                                        break
                                    
                                    # Namespace import: import * as X from 'module'
                                    elif clause_child.type == 'namespace_import':
                                        is_wildcard = True
                                        for ns_child in clause_child.children:
                                            if hasattr(ns_child, 'type') and ns_child.type == 'identifier':
                                                import_names.append(_node_text_to_str(ns_child.text))
                        
                        # Get module source
                        elif child.type == 'string':
                            module_name = self._extract_string_value(child)
                
                if module_name:
                    import_info = type('ImportInfo', (), {
                        'type': 'import',
                        'module': module_name,
                        'range': (node.start_byte, node.end_byte),
                        'names': import_names,
                        'is_wildcard': is_wildcard
                    })()
                    yield import_info
            
            # CommonJS require: const X = require('module')
            elif node.type == 'variable_declarator':
                # Check if RHS is a require call
                module_name = ''
                var_name = ''
                
                for child in node.children:
                    if hasattr(child, 'type'):
                        # Get variable name
                        if child.type == 'identifier':
                            var_name = _node_text_to_str(child.text)
                        
                        # Check for require() call
                        elif child.type == 'call_expression':
                            func_name = ''
                            for call_child in child.children:
                                if hasattr(call_child, 'type'):
                                    if call_child.type == 'identifier':
                                        func_name = _node_text_to_str(call_child.text)
                                    elif call_child.type == 'arguments':
                                        # Get the module string
                                        for arg_child in call_child.children:
                                            if hasattr(arg_child, 'type') and arg_child.type == 'string':
                                                module_name = self._extract_string_value(arg_child)
                                                break
                            
                            if func_name == 'require' and module_name:
                                import_info = type('ImportInfo', (), {
                                    'type': 'require',
                                    'module': module_name,
                                    'range': (node.start_byte, node.end_byte),
                                    'names': [var_name] if var_name else [],
                                    'is_wildcard': False
                                })()
                                yield import_info
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        # Start visiting from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def _extract_string_value(self, string_node):
        """Extract the actual string value from a string node."""
        if not hasattr(string_node, 'text'):
            return ''
        
        text = _node_text_to_str(string_node.text)
        # Remove quotes
        if len(text) >= 2 and text[0] in ('"', "'", '`') and text[-1] == text[0]:
            return text[1:-1]
        return text

    def iter_scope_nodes(self, tree):
        """
        Iterate over scope-defining nodes in the tree.
        
        Yields dicts with: id, kind, parent_id
        """
        if tree is None:
            return
        
        scope_id = 0
        
        def visit_node(node, parent_scope_id=None):
            nonlocal scope_id
            current_scope_id = None
            
            if hasattr(node, 'type'):
                # JavaScript scope-defining nodes
                scope_types = {
                    'program': 'module',
                    'function_declaration': 'function',
                    'arrow_function': 'function',
                    'function': 'function',
                    'method_definition': 'method',
                    'class_declaration': 'class',
                    'class': 'class',
                }
                
                if node.type in scope_types:
                    current_scope_id = scope_id
                    scope_id += 1
                    
                    yield {
                        'id': current_scope_id,
                        'kind': scope_types[node.type],
                        'parent_id': parent_scope_id
                    }
            
            # Visit children with current scope as parent
            if hasattr(node, 'children'):
                child_parent_id = current_scope_id if current_scope_id is not None else parent_scope_id
                for child in node.children:
                    yield from visit_node(child, child_parent_id)
        
        # Start from root
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)

    def iter_identifier_refs(self, tree):
        """
        Iterate over identifier references (variable usages) in the tree.
        
        Yields dicts with: name, scope_id, byte, meta
        """
        if tree is None:
            return
        
        # Track current scope as we traverse
        current_scope_id = 0
        scope_stack = [0]
        
        def visit_node(node):
            nonlocal current_scope_id
            
            if not hasattr(node, 'type'):
                return
            
            # Update scope tracking
            scope_types = ['program', 'function_declaration', 'arrow_function', 
                          'function', 'method_definition', 'class_declaration', 'class']
            if node.type in scope_types:
                if node.type != 'program':
                    current_scope_id += 1
                    scope_stack.append(current_scope_id)
            
            # Emit identifier references (but not declarations)
            if node.type == 'identifier':
                # Check if this is a reference (not a declaration)
                parent = node.parent if hasattr(node, 'parent') else None
                is_declaration = False
                
                if parent and hasattr(parent, 'type'):
                    # Skip if this is the name in a declaration
                    if parent.type in ['function_declaration', 'class_declaration', 
                                       'variable_declarator', 'method_definition']:
                        # Check if this is the name child
                        for i, child in enumerate(parent.children):
                            if child == node and i == 0:
                                is_declaration = True
                                break
                    
                    # Skip import declarations - identifiers in import_clause, import_specifier, etc.
                    if parent.type in ['import_clause', 'import_specifier', 'namespace_import']:
                        is_declaration = True
                    elif parent.type == 'named_imports':
                        is_declaration = True
                
                if not is_declaration:
                    yield {
                        'name': _node_text_to_str(node.text),
                        'scope_id': scope_stack[-1] if scope_stack else 0,
                        'byte': node.start_byte,
                        'meta': {}
                    }
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
            
            # Pop scope when exiting scope node
            if node.type in scope_types and node.type != 'program':
                if scope_stack:
                    scope_stack.pop()
        
        # Start from root
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)


# Create default instance
default_javascript_adapter = JavaScriptAdapter()

