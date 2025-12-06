"""
Core types for the Aspect Code Tree-sitter engine.

This module provides shared dataclasses and types used across the engine,
adapters, and rules.
"""

from dataclasses import dataclass, replace
from typing import Any, Dict, Iterable, List, Literal, Optional, Protocol, Tuple, Union, Callable
from abc import ABC, abstractmethod


# Type aliases for clarity
Severity = Literal["info", "warn", "error"]
Priority = Literal["P0", "P1", "P2"] 
Tier = Literal[0, 1, 2]
FileRange = Tuple[int, int, int, int]  # (start_line, start_col, end_line, end_col) 1-based
NodeRange = Tuple[int, int]  # (start_byte, end_byte) 0-based

# Surface determines where rule findings appear:
# - "kb": KB generation only (.aspect/ files), not shown to users
# - "user": User-facing findings panel and debug reports only
# - "both": Appears in both KB and user-facing outputs (default)
Surface = Literal["kb", "user", "both"]


@dataclass(frozen=True)
class Edit:
    """A suggested edit to fix an issue."""
    start_byte: int
    end_byte: int
    replacement: str


@dataclass(frozen=True)
class Finding:
    """A finding represents an issue detected by a rule."""
    rule: str
    message: str
    file: str
    start_byte: int
    end_byte: int
    severity: Severity
    autofix: Optional[List[Edit]] = None
    meta: Optional[Dict[str, Any]] = None
    
    def _replace(self, **kwargs):
        """Provide NamedTuple-like _replace method for compatibility."""
        return replace(self, **kwargs)


@dataclass(frozen=True)
class RuleMeta:
    """Metadata about a rule.
    
    Attributes:
        id: Unique rule identifier (e.g., "arch.entry_point")
        category: Rule category for grouping
        tier: Analysis tier (0=syntax, 1=scopes, 2=project_graph)
        priority: P0/P1/P2 priority level
        autofix_safety: Whether autofix is safe/caution/suggest-only
        description: Human-readable description
        langs: List of supported languages
        surface: Where findings appear:
            - "kb": KB generation only (.aspect/ files), hidden from users
            - "user": User-facing findings panel only
            - "both": Appears in both (default)
    """
    id: str
    category: str
    tier: Tier
    priority: Priority
    autofix_safety: Literal["safe", "caution", "suggest-only"]
    description: str = ""
    langs: List[str] = None  # ["python"], ["ts", "js"], etc.
    surface: Surface = "both"  # Where findings appear: "kb", "user", or "both"
    
    def __post_init__(self):
        if self.langs is None:
            object.__setattr__(self, 'langs', [])


@dataclass(frozen=True)
class Requires:
    """Represents requirements that a rule needs to run."""
    raw_text: bool = False
    syntax: bool = True
    scopes: bool = False         # Tier 1
    project_graph: bool = False  # Tier 2
    

@dataclass
class RuleContext:
    """Context passed to rules during execution."""
    file_path: str
    text: str
    tree: Any
    adapter: 'LanguageAdapter'  # Forward reference
    config: Dict[str, Any]
    # Placeholders for future tiers (wire as None for now)
    scopes: Any = None
    project_graph: Any = None  # Tier 2: (resolver, import_graph, symbol_index)
    
    def __post_init__(self):
        """Initialize compatibility layer after construction."""
        self._enhanced_context = None
    
    def _get_enhanced_context(self):
        """Get enhanced context with tree-sitter compatibility."""
        if self._enhanced_context is None:
            try:
                from .tree_sitter_compat import make_compatible_context
                self._enhanced_context = make_compatible_context(self)
            except ImportError:
                # Fallback if compatibility layer not available
                self._enhanced_context = self
        return self._enhanced_context
    
    # Compatibility properties for rules with different naming conventions
    @property
    def syntax(self):
        """Enhanced syntax with tree-sitter compatibility."""
        enhanced = self._get_enhanced_context()
        if enhanced != self and hasattr(enhanced, '_get_syntax'):
            return enhanced._get_syntax()
        return self.tree
    
    @property
    def syntax_tree(self):
        """Enhanced syntax_tree with tree-sitter compatibility."""
        enhanced = self._get_enhanced_context()
        if enhanced != self and hasattr(enhanced, '_get_syntax_tree'):
            return enhanced._get_syntax_tree()
        return self.tree
        
    @property
    def raw_text(self):
        """Alias for text (compatibility with older rules)."""
        return self.text
    
    @property
    def language(self):
        """Get language from adapter (compatibility with older rules)."""
        return self.adapter.language_id if self.adapter else None
    
    @property
    def registry(self):
        """Get adapter registry for compatibility."""
        return self.adapter if self.adapter else None
    
    def get_text(self, start_byte: int, end_byte: int) -> str:
        """Get text slice from byte positions."""
        enhanced = self._get_enhanced_context()
        if enhanced != self and hasattr(enhanced, 'get_text'):
            return enhanced.get_text(start_byte, end_byte)
        
        # Fallback implementation
        text = self.text
        if isinstance(text, str):
            # Convert to bytes for proper slicing, then back to string
            text_bytes = text.encode('utf-8')
            slice_bytes = text_bytes[start_byte:end_byte]
            return slice_bytes.decode('utf-8', errors='ignore')
        elif isinstance(text, bytes):
            return text[start_byte:end_byte].decode('utf-8', errors='ignore')
        else:
            return str(text)[start_byte:end_byte]
    
    def node_span(self, node) -> tuple:
        """Get byte span of a node (start_byte, end_byte)."""
        enhanced = self._get_enhanced_context()
        if enhanced != self and hasattr(enhanced, 'syntax') and hasattr(enhanced.syntax, 'node_span'):
            return enhanced.syntax.node_span(node)
        
        # Fallback implementation
        if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return (node.start_byte, node.end_byte)
        elif hasattr(node, 'start_pos') and hasattr(node, 'end_pos'):
            return (node.start_pos, node.end_pos)
        elif hasattr(node, 'span') and callable(node.span):
            return node.span()
        elif hasattr(node, 'range'):
            r = node.range
            if hasattr(r, 'start_byte') and hasattr(r, 'end_byte'):
                return (r.start_byte, r.end_byte)
        return (0, 0)
    
    def walk_nodes(self, start_node=None):
        """Walk all nodes in the syntax tree."""
        enhanced = self._get_enhanced_context()
        if enhanced != self and hasattr(enhanced, 'walk_nodes'):
            yield from enhanced.walk_nodes(start_node)
            return
        
        # Fallback implementation
        if not self.tree:
            return
        
        root = start_node or getattr(self.tree, 'root_node', self.tree)
        
        def walk_recursive(node):
            yield node
            children = getattr(node, 'children', [])
            if children:
                for child in children:
                    yield from walk_recursive(child)
        
        yield from walk_recursive(root)


class Rule(Protocol):
    """Protocol for all rules in the engine.
    
    Rules analyze code and return findings. They should be stateless and thread-safe.
    """
    meta: RuleMeta
    requires: Requires
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit a file and return findings.
        
        Args:
            ctx: Rule context containing file path, text, tree, adapter, and config
            
        Returns:
            Iterable of findings for this file
        """
        ...


class LanguageAdapter(ABC):
    """Abstract base class for language adapters."""
    
    @property
    @abstractmethod
    def language_id(self) -> str:
        """Return the language identifier (e.g., 'python', 'typescript', 'javascript')."""
        pass
    
    @property 
    @abstractmethod
    def file_extensions(self) -> Tuple[str, ...]:
        """Return supported file extensions (e.g., ('.py',), ('.ts', '.tsx'))."""
        pass
    
    @abstractmethod
    def parse(self, text: str) -> Any:
        """Parse text and return a Tree-sitter tree. Results may be cached."""
        pass
    
    @abstractmethod
    def list_files(self, paths: List[str]) -> List[str]:
        """List all files matching this adapter's extensions in the given paths."""
        pass
    
    @abstractmethod
    def node_text(self, text: str, start_byte: int, end_byte: int) -> str:
        """Extract text between byte offsets."""
        pass
    
    @abstractmethod
    def enclosing_function(self, tree: Any, byte_offset: int) -> Optional[Dict[str, Any]]:
        """Find the function enclosing the given byte offset."""
        pass
    
    @abstractmethod
    def byte_to_linecol(self, text: str, byte: int) -> Tuple[int, int]:
        """Convert byte offset to (line, column) 1-based."""
        pass
    
    @abstractmethod
    def line_col_to_byte(self, text: str, line: int, col: int) -> int:
        """Convert (line, column) 1-based to byte offset."""
        pass
    
    @abstractmethod
    def get_source_slice(self, text: str, node_range: NodeRange) -> str:
        """Get source text for a node range (start_byte, end_byte)."""
        pass
    
    # === Scope analysis hooks (Tier-1) ===
    
    def iter_scope_nodes(self, tree: Any) -> List[Dict[str, Any]]:
        """
        Enumerate scope boundaries in the tree.
        
        Returns:
            List of dicts with keys: id, kind, start, end, parent_id
        """
        return []
    
    def iter_symbol_defs(self, tree: Any) -> List[Dict[str, Any]]:
        """
        Enumerate symbol definitions (bindings) in the tree.
        
        Returns:
            List of dicts with keys: name, kind, scope_id, start, end, meta
        """
        return []
    
    def iter_identifier_refs(self, tree: Any) -> List[Dict[str, Any]]:
        """
        Enumerate identifier references (uses) in the tree.
        
        Returns:
            List of dicts with keys: name, scope_id, byte, meta
        """
        return []
    
    def ignored_receiver_names(self) -> set[str]:
        """Return set of names that should be ignored as receivers."""
        return set()


# Info dataclasses for adapter helper methods
@dataclass(frozen=True)
class ImportInfo:
    """Information about an import statement."""
    module: str
    names: List[str]  # imported names, empty for bare imports
    is_wildcard: bool
    range: NodeRange
    alias: Optional[str] = None


@dataclass(frozen=True)
class FunctionInfo:
    """Information about a function definition."""
    name: str
    range: NodeRange
    params: List[str]
    is_async: bool = False
    decorators: List[str] = None
    
    def __post_init__(self):
        if self.decorators is None:
            object.__setattr__(self, 'decorators', [])


@dataclass(frozen=True) 
class ParamDefaultInfo:
    """Information about function parameter defaults."""
    param: str
    default_kind: str  # e.g., "mutable_default", "none", "literal"
    range: NodeRange
    default_value: Optional[str] = None


@dataclass(frozen=True)
class BinaryOpInfo:
    """Information about binary operations."""
    operator: str  # e.g., "+", "==", "&&"
    left_range: NodeRange
    right_range: NodeRange
    range: NodeRange  # Full operation range


@dataclass(frozen=True)
class AwaitInfo:
    """Information about await expressions."""
    range: NodeRange
    expression_range: Optional[NodeRange] = None  # The awaited expression


# Legacy aliases for backward compatibility
Detector = Rule  # Old name


