"""
C# language adapter for tree-sitter.
"""
import os
import sys
from typing import List, Tuple, Any, Optional, Dict
import tree_sitter
from .types import LanguageAdapter


class CSharpAdapter(LanguageAdapter):
    """Tree-sitter adapter for C# language."""
    
    def __init__(self, parser_path: Optional[str] = None):
        """Initialize C# adapter with tree-sitter parser."""
        self._parser = None
        self._parser_path = parser_path
        
    @property
    def language_id(self) -> str:
        """Return the language identifier."""
        return "csharp"
    
    @property
    def file_extensions(self) -> Tuple[str, ...]:
        """Return supported file extensions."""
        return (".cs",)
    
    def _get_parser(self):
        """Get or create the tree-sitter parser."""
        if self._parser is None:
            try:
                # Use tree-sitter-c-sharp package if available
                import tree_sitter
                from tree_sitter_c_sharp import language
                
                CSHARP_LANGUAGE = tree_sitter.Language(language())
                
                self._parser = tree_sitter.Parser()
                self._parser.language = CSHARP_LANGUAGE
                print(f"Debug: C# parser initialized successfully", file=sys.stderr)
            except ImportError as e:
                print(f"Warning: tree-sitter-c-sharp not available: {e}", file=sys.stderr)
                self._parser = None
            except Exception as e:
                print(f"Warning: Could not initialize C# parser: {e}", file=sys.stderr)
                self._parser = None
        
        return self._parser
    
    def parse(self, text: str) -> Any:
        """Parse text and return a Tree-sitter tree."""
        parser = self._get_parser()
        if parser is None:
            return None
        
        return parser.parse(text.encode('utf-8'))
    
    def list_files(self, paths: List[str]) -> List[str]:
        """List all C# files in the given paths."""
        cs_files = []
        
        for path in paths:
            if os.path.isfile(path):
                if any(path.endswith(ext) for ext in self.file_extensions):
                    cs_files.append(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Skip common ignore directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'bin', 'obj']]
                    
                    for file in files:
                        if any(file.endswith(ext) for ext in self.file_extensions):
                            cs_files.append(os.path.join(root, file))
        
        return cs_files
    
    def node_text(self, text: str, start_byte: int, end_byte: int) -> str:
        """Extract text between byte offsets."""
        try:
            return text.encode('utf-8')[start_byte:end_byte].decode('utf-8')
        except (UnicodeDecodeError, IndexError):
            return ""
    
    def enclosing_function(self, tree: Any, byte_offset: int) -> Optional[Dict[str, Any]]:
        """Find the method enclosing the given byte offset."""
        if tree is None:
            return None
        
        def find_enclosing_method(node):
            if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                if node.start_byte <= byte_offset <= node.end_byte:
                    if hasattr(node, 'type') and node.type in ['method_declaration', 'constructor_declaration']:
                        # Found enclosing method
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
                            result = find_enclosing_method(child)
                            if result:
                                return result
            return None
        
        return find_enclosing_method(tree.root_node if hasattr(tree, 'root_node') else tree)
    
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
                        if child.type in ['identifier', 'integer_literal', 'string_literal', 'member_access_expression', 'invocation_expression', 'parenthesized_expression']:
                            if left_node is None:
                                left_node = child
                            else:
                                right_node = child
                        elif hasattr(child, 'text'):
                            # The operator is typically text nodes like '==', '!=', etc.
                            text = child.text.decode('utf-8')
                            if text in ['==', '!=', '+', '-', '*', '/', '%', '<', '>', '<=', '>=', '&&', '||']:
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

    def _node_text_to_str(self, node_text):
        """Helper to convert tree-sitter node.text to string."""
        if node_text is None:
            return ""
        if isinstance(node_text, bytes):
            return node_text.decode('utf-8', errors='ignore')
        return str(node_text)

    def iter_scope_nodes(self, tree):
        """Iterate over scope-defining nodes in the tree."""
        if tree is None:
            return
        
        scope_id = 0
        
        def visit_node(node, parent_scope_id=None):
            nonlocal scope_id
            current_scope_id = None
            
            if hasattr(node, 'type'):
                # C# scope-defining nodes
                scope_types = {
                    'compilation_unit': 'module',
                    'namespace_declaration': 'namespace',
                    'class_declaration': 'class',
                    'struct_declaration': 'struct',
                    'interface_declaration': 'interface',
                    'enum_declaration': 'enum',
                    'method_declaration': 'method',
                    'constructor_declaration': 'constructor',
                    'property_declaration': 'property',
                    'block': 'block',
                    'for_statement': 'for',
                    'foreach_statement': 'foreach',
                    'while_statement': 'while',
                    'try_statement': 'try',
                    'catch_clause': 'catch',
                }
                
                if node.type in scope_types:
                    current_scope_id = scope_id
                    scope_id += 1
                    
                    yield {
                        'id': current_scope_id,
                        'kind': scope_types[node.type],
                        'parent_id': parent_scope_id
                    }
            
            # Visit children
            if hasattr(node, 'children'):
                child_parent_id = current_scope_id if current_scope_id is not None else parent_scope_id
                for child in node.children:
                    yield from visit_node(child, child_parent_id)
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)

    def iter_symbol_defs(self, tree):
        """Iterate over symbol definitions (methods, classes, variables, etc.)."""
        if tree is None:
            return
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        
        # Scope-creating node types
        scope_types = {
            'compilation_unit', 'class_declaration', 'struct_declaration',
            'method_declaration', 'constructor_declaration', 'block',
            'lambda_expression', 'for_statement', 'foreach_statement',
            'while_statement', 'if_statement', 'try_statement', 'catch_clause',
            'namespace_declaration', 'local_function_statement'
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
            
            # Class declarations
            if node.type == 'class_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    class_name = self._node_text_to_str(name_node.text)
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
                    
                    # Visit class body
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'declaration_list':
                            yield from visit_node(child, parent_scope='class', parent_class=class_name, current_scope_id=current_scope_id)
            
            # Method declarations
            elif node.type == 'method_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    method_scope_id = find_enclosing_scope_id(node.parent) if hasattr(node, 'parent') and node.parent else current_scope_id
                    yield {
                        'name': self._node_text_to_str(name_node.text),
                        'kind': 'method',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': method_scope_id,
                        'meta': {'parent_class': parent_class} if parent_class else {}
                    }
            
            # Constructor declarations
            elif node.type == 'constructor_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    ctor_scope_id = find_enclosing_scope_id(node.parent) if hasattr(node, 'parent') and node.parent else current_scope_id
                    yield {
                        'name': self._node_text_to_str(name_node.text),
                        'kind': 'constructor',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': ctor_scope_id,
                        'meta': {'parent_class': parent_class} if parent_class else {}
                    }
            
            # Field declarations
            elif node.type == 'field_declaration':
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'variable_declaration':
                        for subchild in child.children:
                            if hasattr(subchild, 'type') and subchild.type == 'variable_declarator':
                                name_node = None
                                for n in subchild.children:
                                    if hasattr(n, 'type') and n.type == 'identifier':
                                        name_node = n
                                        break
                                
                                if name_node:
                                    yield {
                                        'name': self._node_text_to_str(name_node.text),
                                        'kind': 'field',
                                        'start': subchild.start_byte,
                                        'end': subchild.end_byte,
                                        'scope_kind': parent_scope,
                                        'scope_id': current_scope_id,
                                        'meta': {'parent_class': parent_class} if parent_class else {}
                                    }
            
            # Property declarations
            elif node.type == 'property_declaration':
                name_node = None
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'identifier':
                        name_node = child
                        break
                
                if name_node:
                    yield {
                        'name': self._node_text_to_str(name_node.text),
                        'kind': 'property',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': current_scope_id,
                        'meta': {'parent_class': parent_class} if parent_class else {}
                    }
            
            # Local variable declarations
            elif node.type == 'local_declaration_statement':
                for child in node.children:
                    if hasattr(child, 'type') and child.type == 'variable_declaration':
                        for subchild in child.children:
                            if hasattr(subchild, 'type') and subchild.type == 'variable_declarator':
                                name_node = None
                                for n in subchild.children:
                                    if hasattr(n, 'type') and n.type == 'identifier':
                                        name_node = n
                                        break
                                
                                if name_node:
                                    yield {
                                        'name': self._node_text_to_str(name_node.text),
                                        'kind': 'variable',
                                        'start': subchild.start_byte,
                                        'end': subchild.end_byte,
                                        'scope_kind': parent_scope,
                                        'scope_id': current_scope_id,
                                        'meta': {}
                                    }
            
            # Using directives (imports)
            elif node.type == 'using_directive':
                # using System.IO;
                name_parts = []
                for child in node.children:
                    if hasattr(child, 'type'):
                        if child.type == 'qualified_name':
                            name_parts = self._get_qualified_name(child)
                        elif child.type == 'identifier':
                            name_parts = [self._node_text_to_str(child.text)]
                
                if name_parts:
                    # Use the last part as the name
                    name = name_parts[-1]
                    full_module = '.'.join(name_parts[:-1]) if len(name_parts) > 1 else ''
                    
                    yield {
                        'name': name,
                        'kind': 'import',
                        'start': node.start_byte,
                        'end': node.end_byte,
                        'scope_kind': parent_scope,
                        'scope_id': current_scope_id,
                        'meta': {'module': full_module}
                    }
            
            # Visit children recursively
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child, parent_scope, parent_class, current_scope_id)
        
        yield from visit_node(root_node, current_scope_id=0)
    
    def _get_qualified_name(self, node):
        """Extract parts from a qualified_name node."""
        parts = []
        
        def collect_parts(n):
            if hasattr(n, 'type'):
                if n.type == 'identifier':
                    parts.append(self._node_text_to_str(n.text))
                elif n.type == 'qualified_name':
                    if hasattr(n, 'children'):
                        for child in n.children:
                            collect_parts(child)
        
        collect_parts(node)
        return parts

    def iter_identifier_refs(self, tree):
        """Iterate over identifier references (variable usages) in the tree."""
        if tree is None:
            return
        
        current_scope_id = 0
        scope_stack = [0]
        
        def visit_node(node):
            nonlocal current_scope_id
            
            if not hasattr(node, 'type'):
                return
            
            # Update scope tracking
            scope_types = ['class_declaration', 'method_declaration', 'constructor_declaration', 'block']
            if node.type in scope_types:
                current_scope_id += 1
                scope_stack.append(current_scope_id)
            
            # Emit identifier references (but not declarations)
            if node.type == 'identifier':
                parent = node.parent if hasattr(node, 'parent') else None
                is_declaration = False
                
                if parent and hasattr(parent, 'type'):
                    # Skip declaration names
                    if parent.type in ['class_declaration', 'method_declaration', 
                                       'constructor_declaration', 'variable_declarator',
                                       'parameter', 'catch_declaration', 'property_declaration']:
                        for i, child in enumerate(parent.children):
                            if child == node:
                                if parent.type == 'variable_declarator' and i == 0:
                                    is_declaration = True
                                elif parent.type == 'parameter':
                                    is_declaration = True
                                elif parent.type in ['class_declaration', 'method_declaration', 
                                                     'constructor_declaration', 'property_declaration']:
                                    is_declaration = True
                                break
                    
                    # Skip using directive identifiers
                    if parent.type in ['using_directive', 'qualified_name']:
                        is_declaration = True
                
                if not is_declaration:
                    yield {
                        'name': self._node_text_to_str(node.text),
                        'scope_id': scope_stack[-1] if scope_stack else 0,
                        'byte': node.start_byte,
                        'meta': {}
                    }
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
            
            # Pop scope
            if node.type in scope_types:
                if scope_stack:
                    scope_stack.pop()
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)


# Create default instance
default_csharp_adapter = CSharpAdapter()

