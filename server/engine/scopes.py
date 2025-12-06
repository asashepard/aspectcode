"""
Scopes and name resolution system for Aspect Code.

This module provides a language-agnostic scopes API that can be used by rules
to analyze variable binding, references, and name shadowing across nested scopes.
"""

from dataclasses import dataclass
from typing import Iterable, Optional, Dict, List
from .types import LanguageAdapter


@dataclass(frozen=True)
class Symbol:
    """A symbol represents a name binding in a scope."""
    name: str
    kind: str            # "param"|"local"|"global"|"nonlocal"|"import"|"except"|"class"|"function"
    scope_id: int
    start_byte: int
    end_byte: int
    meta: dict


@dataclass(frozen=True)
class Ref:
    """A reference represents a use of a name in a scope."""
    name: str
    scope_id: int
    byte: int
    meta: dict


@dataclass(frozen=True)
class Scope:
    """A scope represents a namespace boundary."""
    id: int
    kind: str           # "module"|"function"|"class"|"comprehension"|"except"|"block"
    parent_id: Optional[int]


class ScopeGraph:
    """Graph of scopes, symbols, and references for a file."""
    
    def __init__(self, scopes: List[Scope], symbols: List[Symbol], refs: List[Ref]):
        self._scopes = {s.id: s for s in scopes}
        self._symbols = symbols
        self._refs = refs
        
        # Build indexes for fast lookup
        self._symbols_by_scope: Dict[int, List[Symbol]] = {}
        self._refs_by_scope: Dict[int, List[Ref]] = {}
        self._children_by_scope: Dict[int, List[int]] = {}
        
        for symbol in symbols:
            if symbol.scope_id not in self._symbols_by_scope:
                self._symbols_by_scope[symbol.scope_id] = []
            self._symbols_by_scope[symbol.scope_id].append(symbol)
            
        for ref in refs:
            if ref.scope_id not in self._refs_by_scope:
                self._refs_by_scope[ref.scope_id] = []
            self._refs_by_scope[ref.scope_id].append(ref)
            
        for scope in scopes:
            if scope.parent_id is not None:
                if scope.parent_id not in self._children_by_scope:
                    self._children_by_scope[scope.parent_id] = []
                self._children_by_scope[scope.parent_id].append(scope.id)
    
    def get_scope(self, scope_id: int) -> Optional[Scope]:
        """Get scope by ID."""
        return self._scopes.get(scope_id)
    
    def iter_symbols(self, kind: str = None) -> Iterable[Symbol]:
        """Iterate over all symbols, optionally filtered by kind."""
        for symbol in self._symbols:
            if kind is None or symbol.kind == kind:
                yield symbol
    
    def iter_refs(self) -> Iterable[Ref]:
        """Iterate over all references."""
        return iter(self._refs)
    
    def symbols_in_scope(self, scope_id: int) -> List[Symbol]:
        """Get all symbols defined in a specific scope."""
        return self._symbols_by_scope.get(scope_id, [])
    
    def refs_in_scope(self, scope_id: int) -> List[Ref]:
        """Get all references in a specific scope."""
        return self._refs_by_scope.get(scope_id, [])
    
    def resolve_visible(self, scope_id: int, name: str) -> Optional[Symbol]:
        """
        Resolve a name to the visible symbol in scope hierarchy.
        
        Searches from the given scope upward through parent scopes to find
        the first matching symbol definition.
        """
        current_scope_id = scope_id
        
        while current_scope_id is not None:
            # Look for the name in current scope
            for symbol in self.symbols_in_scope(current_scope_id):
                if symbol.name == name:
                    return symbol
            
            # Move to parent scope
            scope = self.get_scope(current_scope_id)
            current_scope_id = scope.parent_id if scope else None
            
        return None
    
    def children_of(self, scope_id: int) -> List[int]:
        """Get direct child scope IDs of a scope."""
        return self._children_by_scope.get(scope_id, [])
    
    def descendants_of(self, scope_id: int) -> List[int]:
        """Get all descendant scope IDs of a scope (recursive)."""
        descendants = []
        children = self.children_of(scope_id)
        descendants.extend(children)
        
        for child_id in children:
            descendants.extend(self.descendants_of(child_id))
            
        return descendants
    
    def has_refs_to(self, symbol: Symbol) -> bool:
        """Check if a symbol has any references in visible scopes."""
        # Check the symbol's own scope and all descendant scopes
        scope_ids_to_check = [symbol.scope_id] + self.descendants_of(symbol.scope_id)
        
        for scope_id in scope_ids_to_check:
            for ref in self.refs_in_scope(scope_id):
                if ref.name == symbol.name:
                    # Check if this ref would resolve to our symbol
                    resolved = self.resolve_visible(ref.scope_id, ref.name)
                    if resolved and resolved == symbol:
                        return True
        
        return False
    
    def refs_to(self, symbol: Symbol) -> List[Ref]:
        """Get all references to a symbol in visible scopes."""
        refs = []
        # Check the symbol's own scope and all descendant scopes
        scope_ids_to_check = [symbol.scope_id] + self.descendants_of(symbol.scope_id)
        
        for scope_id in scope_ids_to_check:
            for ref in self.refs_in_scope(scope_id):
                if ref.name == symbol.name:
                    # Check if this ref would resolve to our symbol
                    resolved = self.resolve_visible(ref.scope_id, ref.name)
                    if resolved and resolved == symbol:
                        refs.append(ref)
        
        return refs
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the scope graph."""
        return {
            "scopes": len(self._scopes),
            "symbols": len(self._symbols),
            "refs": len(self._refs),
            "imports": len([s for s in self._symbols if s.kind == "import"])
        }


def build_scopes(adapter: LanguageAdapter, tree, text: str) -> ScopeGraph:
    """
    Build a scope graph for a file using the language adapter.
    
    Args:
        adapter: Language adapter with scope analysis hooks
        tree: Parsed tree from tree-sitter
        text: Source text
        
    Returns:
        ScopeGraph containing scopes, symbols, and references
    """
    # Get raw data from adapter
    try:
        scope_dicts = list(adapter.iter_scope_nodes(tree))
        symbol_dicts = list(adapter.iter_symbol_defs(tree))
        ref_dicts = list(adapter.iter_identifier_refs(tree))
    except (AttributeError, NotImplementedError):
        # Adapter doesn't support scopes yet
        return ScopeGraph([], [], [])
    
    # Convert to dataclasses
    scopes = []
    for scope_dict in scope_dicts:
        scope = Scope(
            id=scope_dict["id"],
            kind=scope_dict["kind"],
            parent_id=scope_dict.get("parent_id")
        )
        scopes.append(scope)
    
    symbols = []
    for symbol_dict in symbol_dicts:
        symbol = Symbol(
            name=symbol_dict["name"],
            kind=symbol_dict["kind"],
            scope_id=symbol_dict.get("scope_id", 0),  # Default to module scope (0)
            start_byte=symbol_dict["start"],
            end_byte=symbol_dict["end"],
            meta=symbol_dict.get("meta", {})
        )
        symbols.append(symbol)
    
    refs = []
    for ref_dict in ref_dicts:
        ref = Ref(
            name=ref_dict["name"],
            scope_id=ref_dict.get("scope_id", 0),  # Default to module scope (0)
            byte=ref_dict["byte"],
            meta=ref_dict.get("meta", {})
        )
        refs.append(ref)
    
    return ScopeGraph(scopes, symbols, refs)


