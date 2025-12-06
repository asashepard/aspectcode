"""
Tree-Sitter Compatibility Layer

This module provides compatibility wrappers that allow rules written for raw tree-sitter API
to work with our current RuleContext system. This enables the 43 missing rules to work
without requiring complete rewrites.

The key insight is that many rules expect:
1. node.type, node.text, node.children attributes
2. Methods like node_span(), walk_nodes()
3. Raw tree-sitter node navigation patterns

This compatibility layer bridges those expectations with our current system.
"""

from typing import Iterator, Any, Union, List, Optional, Tuple
from engine.types import RuleContext


class MockScopeGraph:
    """Mock ScopeGraph for compatibility with rules that expect scopes."""
    
    def __init__(self):
        """Initialize with empty scopes."""
        self._scopes = {}  # Dict, not list - rules expect .items()
        self._symbols = {}
    
    def has_refs_to(self, symbol) -> bool:
        """Check if symbol has references - always return False for safety."""
        return False
    
    def refs_to(self, symbol) -> List:
        """Get references to symbol - always return empty list for safety."""
        return []
    
    def get_symbol(self, name: str):
        """Get symbol by name - return None for safety."""
        return None
    
    def symbols_in_scope(self, scope_id) -> List:
        """Get symbols in a given scope - return empty list for mock."""
        return []
    
    def refs_in_scope(self, scope_id) -> List:
        """Get refs in a given scope - return empty list for mock."""
        return []
    
    def descendants_of(self, scope_id) -> List:
        """Get descendant scope IDs - return empty list for mock."""
        return []
    
    def resolve_visible(self, scope_id, name):
        """Resolve visible symbol - return None for mock."""
        return None
    
    def iter_symbols(self, **kwargs):
        """Iterate over all symbols - return empty iterator.
        
        Args:
            **kwargs: Accept any keyword arguments (like 'kind') for compatibility
        """
        return iter([])


class MockRegistry:
    """Mock registry for compatibility with rules that expect adapter registry."""
    
    def __init__(self, adapter):
        self.adapter = adapter
        
    def get_adapter(self, language: str):
        """Get adapter for language - return the current adapter."""
        return self.adapter


class TreeSitterNode:
    """Compatibility wrapper that provides tree-sitter API on our existing nodes."""
    
    def __init__(self, original_node: Any, ctx: RuleContext):
        """Wrap an existing node with tree-sitter compatible API."""
        self._node = original_node
        self._ctx = ctx
        
    @property
    def type(self) -> str:
        """Get node type in tree-sitter format."""
        if hasattr(self._node, 'type'):
            return str(self._node.type)
        elif hasattr(self._node, 'node_type'):
            return str(self._node.node_type)
        elif hasattr(self._node, 'kind'):
            return str(self._node.kind)
        elif hasattr(self._node, '__class__'):
            return self._node.__class__.__name__.lower()
        else:
            return 'unknown'
    
    @property
    def kind(self) -> str:
        """Get node kind - alias for type."""
        return self.type
    
    @property
    def text(self) -> Union[str, bytes]:
        """Get node text in tree-sitter format."""
        if hasattr(self._node, 'text'):
            text = self._node.text
            if isinstance(text, bytes):
                return text
            return str(text).encode('utf-8')
        elif hasattr(self._node, 'source_text'):
            text = self._node.source_text
            if isinstance(text, bytes):
                return text
            return str(text).encode('utf-8')
        elif hasattr(self._ctx, 'raw_text') and hasattr(self._node, 'start_byte') and hasattr(self._node, 'end_byte'):
            # Extract from context raw_text
            start = getattr(self._node, 'start_byte', 0)
            end = getattr(self._node, 'end_byte', start)
            if isinstance(self._ctx.raw_text, str):
                return self._ctx.raw_text[start:end].encode('utf-8')
            else:
                return self._ctx.raw_text[start:end]
        else:
            return b''
    
    @property 
    def children(self) -> List['TreeSitterNode']:
        """Get child nodes in tree-sitter format."""
        children = []
        
        if hasattr(self._node, 'children'):
            for child in self._node.children:
                children.append(TreeSitterNode(child, self._ctx))
        elif hasattr(self._node, 'child_nodes'):
            for child in self._node.child_nodes:
                children.append(TreeSitterNode(child, self._ctx))
        elif hasattr(self._node, '__iter__'):
            try:
                for child in self._node:
                    children.append(TreeSitterNode(child, self._ctx))
            except TypeError:
                pass
                
        return children
    
    def walk(self) -> 'TreeCursor':
        """Return a TreeCursor-like object for DFS traversal (tree-sitter compatible)."""
        return TreeCursor(self)
    
    def __iter__(self) -> Iterator['TreeSitterNode']:
        """Make node iterable - yields all descendant nodes.""" 
        return self._walk_iter()
    
    def _walk_iter(self) -> Iterator['TreeSitterNode']:
        """Walk all descendant nodes including self using iterative traversal to avoid recursion limit."""
        # Use iterative DFS to avoid recursion limit
        stack = [self]
        visited = set()
        
        while stack:
            current = stack.pop()
            
            # Prevent infinite loops by tracking visited nodes  
            node_id = id(current._node) if hasattr(current, '_node') else id(current)
            if node_id in visited:
                continue
            visited.add(node_id)
            
            yield current
            
            # Add children to stack (in reverse order for DFS)
            children = current.children
            for child in reversed(children):
                child_id = id(child._node) if hasattr(child, '_node') else id(child)
                if child_id not in visited:
                    stack.append(child)
    
    @property
    def parent(self) -> Optional['TreeSitterNode']:
        """Get parent node in tree-sitter format."""
        if hasattr(self._node, 'parent'):
            parent = self._node.parent
            if parent:
                return TreeSitterNode(parent, self._ctx)
        return None
    
    @property
    def start_byte(self) -> int:
        """Get start byte position."""
        if hasattr(self._node, 'start_byte'):
            return int(self._node.start_byte)
        elif hasattr(self._node, 'start_pos'):
            return int(self._node.start_pos)
        else:
            return 0
    
    @property
    def end_byte(self) -> int:
        """Get end byte position."""
        if hasattr(self._node, 'end_byte'):
            return int(self._node.end_byte)
        elif hasattr(self._node, 'end_pos'):
            return int(self._node.end_pos)
        else:
            return self.start_byte + len(self.text)
    
    def __getattr__(self, name: str) -> Any:
        """Fallback to original node for any missing attributes."""
        return getattr(self._node, name)
    
    def __eq__(self, other) -> bool:
        """Check equality with other nodes."""
        if isinstance(other, TreeSitterNode):
            return self._node == other._node
        return self._node == other


class TreeCursor:
    """Tree-sitter compatible TreeCursor for node traversal."""
    
    def __init__(self, root_node: TreeSitterNode):
        """Initialize cursor starting at root node."""
        self.root = root_node
        self.current = root_node
        self.stack = []
        
    def __iter__(self):
        """Make cursor iterable using DFS traversal."""
        yield from self._dfs_iter()
        
    def _dfs_iter(self):
        """Depth-first traversal iterator."""
        visited = set()
        stack = [self.root]
        
        while stack:
            node = stack.pop()
            node_id = id(node)
            
            if node_id in visited:
                continue
                
            visited.add(node_id)
            yield node
            
            # Add children in reverse order to maintain left-to-right traversal
            for child in reversed(node.children):
                if id(child) not in visited:
                    stack.append(child)
    
    def goto_first_child(self) -> bool:
        """Move to first child if available."""
        if self.current.children:
            self.stack.append(self.current)
            self.current = self.current.children[0]
            return True
        return False
    
    def goto_next_sibling(self) -> bool:
        """Move to next sibling if available."""
        if not self.stack:
            return False
        
        parent = self.stack[-1]
        try:
            current_index = parent.children.index(self.current)
            if current_index + 1 < len(parent.children):
                self.current = parent.children[current_index + 1]
                return True
        except ValueError:
            pass
        return False
    
    def goto_parent(self) -> bool:
        """Move to parent node."""
        if self.stack:
            self.current = self.stack.pop()
            return True
        return False


class TreeSitterSyntax:
    """Compatibility wrapper for syntax tree operations."""
    
    def __init__(self, original_syntax: Any, ctx: RuleContext):
        """Wrap existing syntax object with tree-sitter compatible API."""
        self._syntax = original_syntax
        self._ctx = ctx
    
    @property
    def root_node(self) -> TreeSitterNode:
        """Get root node in tree-sitter format."""
        if hasattr(self._syntax, 'root_node'):
            return TreeSitterNode(self._syntax.root_node, self._ctx)
        elif hasattr(self._syntax, 'root'):
            return TreeSitterNode(self._syntax.root, self._ctx)
        elif hasattr(self._syntax, 'tree'):
            return TreeSitterNode(self._syntax.tree, self._ctx)
        else:
            # Assume the syntax object itself is the root
            return TreeSitterNode(self._syntax, self._ctx)
    
    @property
    def children(self):
        """Get children for tree-sitter Tree compatibility."""
        # Trees typically don't have children, but provide root node children
        return self.root_node.children
    
    def walk(self) -> Iterator[TreeSitterNode]:
        """Walk all nodes in the tree - tree-sitter compatible API."""
        return self.walk_nodes()
    
    def node_span(self, node: Union[TreeSitterNode, Any]) -> Tuple[int, int]:
        """Get byte span of a node."""
        if isinstance(node, TreeSitterNode):
            return (node.start_byte, node.end_byte)
        elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return (node.start_byte, node.end_byte)
        elif hasattr(node, 'start_pos') and hasattr(node, 'end_pos'):
            return (node.start_pos, node.end_pos)
        else:
            # Fallback - try to get span from text length
            try:
                text = getattr(node, 'text', '')
                if isinstance(text, bytes):
                    text = text.decode('utf-8')
                return (0, len(str(text)))
            except:
                return (0, 0)
    
    def walk_nodes(self, start_node: Optional[TreeSitterNode] = None) -> Iterator[TreeSitterNode]:
        """Walk all nodes in the tree starting from start_node (or root)."""
        if start_node is None:
            start_node = self.root_node
        
        def walk_recursive(node: TreeSitterNode) -> Iterator[TreeSitterNode]:
            yield node
            for child in node.children:
                yield from walk_recursive(child)
        
        yield from walk_recursive(start_node)
    
    def __getattr__(self, name: str) -> Any:
        """Fallback to original syntax object."""
        return getattr(self._syntax, name)


class EnhancedRuleContext:
    """Enhanced RuleContext with tree-sitter compatibility methods."""
    
    def __init__(self, original_ctx: RuleContext):
        """Wrap original context with enhanced functionality."""
        self._ctx = original_ctx
        self._ts_syntax = None
        self._tree = None
    
    def _get_syntax(self) -> TreeSitterSyntax:
        """Get syntax with tree-sitter compatibility (private method)."""
        if self._ts_syntax is None and hasattr(self._ctx, 'tree') and self._ctx.tree:
            self._ts_syntax = TreeSitterSyntax(self._ctx.tree, self._ctx)
        return self._ts_syntax
    
    @property
    def syntax(self) -> TreeSitterSyntax:
        """Get syntax with tree-sitter compatibility."""
        return self._get_syntax()
    
    def _get_syntax_tree(self) -> TreeSitterSyntax:
        """Get syntax_tree (private method)."""
        return self._get_syntax()
    
    @property
    def tree(self) -> TreeSitterSyntax:
        """Get tree - alias for syntax for tree-sitter compatibility."""
        return self._get_syntax()
    
    @property
    def syntax_tree(self) -> TreeSitterSyntax:
        """Get syntax_tree - another alias for syntax."""
        return self._get_syntax()
    
    @property
    def language(self) -> str:
        """Get language identifier."""
        if hasattr(self._ctx, 'language'):
            return self._ctx.language
        elif hasattr(self._ctx, 'adapter') and hasattr(self._ctx.adapter, 'language_id'):
            lang_id = self._ctx.adapter.language_id
            # Handle both callable and non-callable language_id
            if callable(lang_id):
                return lang_id()
            else:
                return str(lang_id)
        else:
            return 'unknown'
    
    @property
    def adapter(self):
        """Get adapter with enhanced compatibility."""
        if hasattr(self._ctx, 'adapter') and self._ctx.adapter:
            # Return the original adapter - don't wrap it
            # Rules should access language_id directly as a string attribute
            return self._ctx.adapter
        return None
    
    @property
    def scopes(self) -> MockScopeGraph:
        """Get mock scopes for compatibility."""
        if not hasattr(self._ctx, 'scopes') or self._ctx.scopes is None:
            return MockScopeGraph()
        return self._ctx.scopes
    
    @property
    def registry(self) -> MockRegistry:
        """Get mock registry for compatibility."""
        return MockRegistry(self._ctx.adapter if hasattr(self._ctx, 'adapter') else None)
    
    @property
    def raw_text(self) -> str:
        """Get raw file text."""
        if hasattr(self._ctx, 'raw_text'):
            text = self._ctx.raw_text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return str(text)
        elif hasattr(self._ctx, 'text'):
            text = self._ctx.text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return str(text)
        else:
            return ''
    
    @property
    def children(self):
        """Get children for RuleContext compatibility."""
        # If the context has a node with children, return wrapped children
        if hasattr(self._ctx, 'node') and hasattr(self._ctx.node, 'children'):
            return [TreeSitterNode(child, self._ctx) for child in self._ctx.node.children]
        elif hasattr(self._ctx, 'children'):
            return [TreeSitterNode(child, self._ctx) for child in self._ctx.children]
        else:
            return []
    
    @property
    def file_path(self) -> str:
        """Get file path."""
        return getattr(self._ctx, 'file_path', '')
    
    def get_text(self, start_byte: int, end_byte: int) -> str:
        """Get text slice from byte positions."""
        text = self.raw_text
        if isinstance(text, str):
            # Convert to bytes for proper slicing, then back to string
            text_bytes = text.encode('utf-8')
            slice_bytes = text_bytes[start_byte:end_byte]
            return slice_bytes.decode('utf-8', errors='ignore')
        else:
            return text[start_byte:end_byte]
    
    def walk_nodes(self, start_node: Optional[TreeSitterNode] = None) -> Iterator[TreeSitterNode]:
        """Walk all nodes in the syntax tree."""
        if self.syntax:
            yield from self.syntax.walk_nodes(start_node)
    
    def __getattr__(self, name: str) -> Any:
        """Fallback to original context."""
        return getattr(self._ctx, name)


def make_compatible_context(ctx: RuleContext) -> EnhancedRuleContext:
    """Create a tree-sitter compatible context from existing RuleContext."""
    return EnhancedRuleContext(ctx)


def wrap_rule_visit(original_visit_method):
    """Decorator to wrap rule visit methods with compatibility layer."""
    def wrapped_visit(self, ctx: RuleContext):
        # Create enhanced context
        enhanced_ctx = make_compatible_context(ctx)
        
        # Call original visit method with enhanced context  
        result = original_visit(self, enhanced_ctx)
        
        # If result is a generator, return it directly
        if hasattr(result, '__iter__') and not isinstance(result, (str, bytes)):
            return result
        elif result is None:
            return iter([])  # Empty iterator
        else:
            return iter([result])  # Single result
    
    return wrapped_visit


# Monkey patch helpers for quick compatibility
def patch_rule_for_tree_sitter_compatibility(rule_instance):
    """Quick monkey patch to add tree-sitter compatibility to a rule."""
    if hasattr(rule_instance, 'visit'):
        original_visit = rule_instance.visit
        rule_instance.visit = wrap_rule_visit(original_visit).__get__(rule_instance, rule_instance.__class__)


def create_tree_sitter_compatible_rule(rule_class):
    """Create a new rule class with tree-sitter compatibility."""
    class CompatibleRule(rule_class):
        def visit(self, ctx: RuleContext):
            enhanced_ctx = make_compatible_context(ctx)
            return super().visit(enhanced_ctx)
    
    # Preserve metadata
    CompatibleRule.__name__ = rule_class.__name__
    CompatibleRule.__doc__ = rule_class.__doc__
    
    return CompatibleRule

