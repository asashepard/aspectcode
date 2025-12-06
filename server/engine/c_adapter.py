"""
C language adapter for tree-sitter.
"""
import os
import sys
from typing import List, Tuple, Any, Optional, Dict
import tree_sitter
from .types import LanguageAdapter


class CAdapter(LanguageAdapter):
    """Tree-sitter adapter for C language."""
    
    def __init__(self, parser_path: Optional[str] = None):
        """Initialize C adapter with tree-sitter parser."""
        self._parser = None
        self._parser_path = parser_path
        
    @property
    def language_id(self) -> str:
        """Return the language identifier."""
        return "c"
    
    @property
    def file_extensions(self) -> Tuple[str, ...]:
        """Return supported file extensions."""
        return (".c", ".h")
    
    def _get_parser(self):
        """Get or create the tree-sitter parser."""
        if self._parser is None:
            try:
                # Use tree-sitter-c package if available
                import tree_sitter
                from tree_sitter_c import language
                
                C_LANGUAGE = tree_sitter.Language(language())
                
                self._parser = tree_sitter.Parser()
                self._parser.language = C_LANGUAGE
                print(f"Debug: C parser initialized successfully", file=sys.stderr)
            except ImportError as e:
                print(f"Warning: tree-sitter-c not available: {e}", file=sys.stderr)
                self._parser = None
            except Exception as e:
                print(f"Warning: Could not initialize C parser: {e}", file=sys.stderr)
                self._parser = None
        
        return self._parser
    
    def parse(self, text: str) -> Any:
        """Parse text and return a Tree-sitter tree."""
        parser = self._get_parser()
        if parser is None:
            return None
        
        return parser.parse(text.encode('utf-8'))
    
    def list_files(self, paths: List[str]) -> List[str]:
        """List all C files in the given paths."""
        c_files = []
        
        for path in paths:
            if os.path.isfile(path):
                if any(path.endswith(ext) for ext in self.file_extensions):
                    c_files.append(path)
            elif os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    # Skip common ignore directories
                    dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['__pycache__', 'build']]
                    
                    for file in files:
                        if any(file.endswith(ext) for ext in self.file_extensions):
                            c_files.append(os.path.join(root, file))
        
        return c_files
    
    def node_text(self, text: str, start_byte: int, end_byte: int) -> str:
        """Extract text between byte offsets."""
        try:
            return text.encode('utf-8')[start_byte:end_byte].decode('utf-8')
        except (UnicodeDecodeError, IndexError):
            return ""
    
    def enclosing_function(self, tree: Any, byte_offset: int) -> Optional[Dict[str, Any]]:
        """Find the function enclosing the given byte offset."""
        if tree is None:
            return None
        
        def find_enclosing_function(node):
            if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                if node.start_byte <= byte_offset <= node.end_byte:
                    if hasattr(node, 'type') and node.type in ['function_definition', 'function_declarator']:
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
        """Iterate over binary operations."""
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
                        if child.type in ['identifier', 'number_literal', 'string_literal', 'field_expression', 'call_expression', 'parenthesized_expression']:
                            if left_node is None:
                                left_node = child
                            else:
                                right_node = child
                        elif hasattr(child, 'text'):
                            text = child.text.decode('utf-8')
                            if text in ['==', '!=', '+', '-', '*', '/', '%', '<', '>', '<=', '>=', '&&', '||']:
                                operator = text
                
                if operator and left_node and right_node:
                    op_info = type('BinaryOpInfo', (), {
                        'operator': operator,
                        'range': (node.start_byte, node.end_byte),
                        'left_range': (left_node.start_byte, left_node.end_byte),
                        'right_range': (right_node.start_byte, right_node.end_byte)
                    })()
                    yield op_info
            
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def iter_loose_equality_operators(self, tree):
        """Iterate over loose equality operators (== and !=)."""
        if tree is None:
            return
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type == 'binary_expression':
                for child in node.children:
                    if hasattr(child, 'type') and child.type in ['==', '!=']:
                        operator_info = type('OperatorInfo', (), {
                            'operator': child.text.decode('utf-8'),
                            'range': (child.start_byte, child.end_byte),
                            'full_expression_range': (node.start_byte, node.end_byte)
                        })()
                        yield operator_info
            
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from visit_node(child)
        
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)


# Create default instance
default_c_adapter = CAdapter()

