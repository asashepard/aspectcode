"""Performance rule: Detect excessive object creation inside loops.

Warns when code creates new objects inside tight loops where reuse/preallocation
is reasonable. Recommends hoisting allocations, reusing mutable scratch objects,
pooling, or pre-sizing collections.
"""

from typing import Iterator
from engine.types import RuleMeta, Rule, RuleContext, Finding, Requires


class PerfExcessiveObjectCreationRule:
    """Detect excessive object creation inside loops."""
    
    meta = RuleMeta(
        id="perf.excessive_object_creation",
        category="perf",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detect excessive object creation inside loops",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"],
    )
    requires = Requires(syntax=True)

    # Heuristic constructor/alloc names to emphasize (language-specific; not exhaustive)
    CONSTRUCTOR_HINTS = {
        "python": {"list", "dict", "set", "bytearray", "BytesIO", "StringIO"},
        "javascript": {"Date", "RegExp", "Map", "Set", "Array"},
        "typescript": {"Date", "RegExp", "Map", "Set", "Array"},
        "go": {"new", "make", "bytes.Buffer", "strings.Builder"},
        "java": {"StringBuilder", "ArrayList", "HashMap", "Pattern"},
        "csharp": {"StringBuilder", "List", "Dictionary", "Regex"},
        "cpp": {"std::string", "std::vector", "std::regex"},
        "ruby": {"Hash", "Array", "StringIO"},
        "rust": {"String::new", "Vec::new", "HashMap::new"},
        "swift": {"Data", "Date", "Array", "Dictionary"},
        "c": set(),  # focus on C via other perf rules; struct literal allocs are cheap stack—skip here
    }

    def visit(self, ctx) -> Iterator[Finding]:
        """Check for object creation inside loops."""
        if not hasattr(ctx, 'syntax') or not ctx.syntax:
            return
            
        lang = ctx.language
        # Walk through all nodes to find allocations in loops
        for node in ctx.walk_nodes():
            if self._in_loop(node) and self._is_allocation(node, lang):
                # Get span for the allocation expression
                start_pos, end_pos = ctx.node_span(node)
                
                # For calls, prefer highlighting the callee if available
                callee_node = self._get_callee_node(node)
                if callee_node:
                    start_pos, end_pos = ctx.node_span(callee_node)
                
                yield Finding(
                    rule=self.meta.id,
                    message=self._get_message(lang),
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="info",
                )

    def _walk_nodes(self, syntax_tree):
        """Walk all nodes in the tree."""
        return syntax_tree.walk()

    def _in_loop(self, node) -> bool:
        """Check if node is inside a loop."""
        current = node
        while current and hasattr(current, 'parent'):
            current = current.parent
            if hasattr(current, 'kind') and current.kind in {
                "for_statement", "while_statement", "for_in_statement", 
                "for_of_statement", "foreach_statement", "enhanced_for_statement", 
                "range_for_statement", "do_while_statement"
            }:
                return True
        return False

    def _is_allocation(self, node, lang: str) -> bool:
        """Check if node represents an object allocation."""
        if not hasattr(node, 'kind'):
            return False
            
        node_type = node.kind
        
        # Generic "new" / object creation / array creation
        if node_type in {
            "new_expression", "object_creation_expression", "array_creation_expression",
            "constructor_call", "instantiation_expression"
        }:
            return True
        
        # Literals that create fresh storage every iteration
        if node_type in {
            "object_literal", "array_literal", "map_literal", "slice_literal", 
            "dict_literal", "list_literal", "dictionary_literal", "array_initializer",
            "object_initializer", "composite_literal"
        }:
            return True
        
        # Special handling for different languages
        if node_type == "call_expression":
            return self._is_constructor_call(node, lang)
        
        # Go-specific allocations
        if lang == "go":
            if node_type in {"slice_expression", "map_type", "struct_literal"}:
                return True
            # Check for make() calls
            if node_type == "call_expression":
                callee_text = self._get_callee_text(node)
                if callee_text in {"make", "new"}:
                    return True
        
        # C++ specific allocations
        if lang in {"cpp", "c"}:
            if node_type in {"new_expression", "array_new_expression"}:
                return True
        
        return False

    def _is_constructor_call(self, node, lang: str) -> bool:
        """Check if call expression is a constructor call."""
        callee_text = self._get_callee_text(node)
        if not callee_text:
            return False
            
        hints = self.CONSTRUCTOR_HINTS.get(lang, set())
        for hint in hints:
            if (callee_text == hint or 
                callee_text.endswith(f".{hint}") or
                callee_text.endswith(f"::{hint}") or
                hint in callee_text):
                return True
        
        # Additional language-specific patterns
        if lang == "python":
            # Check for class instantiation patterns
            if callee_text and callee_text[0].isupper():
                return True
        
        return False

    def _get_callee_text(self, node) -> str:
        """Extract callee text from call expression."""
        if not hasattr(node, 'children') or not node.children:
            return ""
        
        # First child is usually the callee
        callee = node.children[0]
        return self._get_node_text(callee)

    def _get_node_text(self, node) -> str:
        """Get text content of a node."""
        if hasattr(node, 'text'):
            return node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
        return ""

    def _get_callee_node(self, node):
        """Get the callee node from a call expression."""
        if not hasattr(node, 'children') or not node.children:
            return None
        
        # First child is usually the callee
        callee = node.children[0]
        if hasattr(callee, 'kind') and callee.kind in {
            "identifier", "member_expression", "qualified_name", 
            "scoped_identifier", "field_expression"
        }:
            return callee
        return None

    def _get_message(self, lang: str) -> str:
        """Get language-specific diagnostic message."""
        suggestions = {
            "python": "Hoist and reuse a scratch object (e.g., list buffer) or pre-size; avoid per-iter builders.",
            "javascript": "Reuse a preallocated object/array or move construction outside the loop; consider pooling.",
            "typescript": "Reuse a preallocated object/array or move construction outside the loop; consider pooling.",
            "go": "Reuse a persistent bytes.Buffer/strings.Builder or pre-size with make(..., n).",
            "java": "Reuse a StringBuilder/collection per loop, or pre-size (new ArrayList(capacity)).",
            "csharp": "Reuse a StringBuilder/collection or use object pooling; pre-size lists/dictionaries.",
            "cpp": "Reuse buffers/containers, reserve() capacity, or avoid heap new in the loop.",
            "ruby": "Reuse a Hash/Array or StringIO across iterations instead of creating new each time.",
            "rust": "Reuse String/Vec/HashMap and call clear()/reserve() instead of new per iteration.",
            "swift": "Reuse Data/Array/Dictionary buffers or preallocate capacity.",
            "c": "Consider reusing buffers; avoid malloc in tight loops.",
        }
        suggestion = suggestions.get(lang, "Consider reusing objects instead of creating new ones each iteration.")
        return f"Object creation inside loop; consider reuse/preallocation. {suggestion}"


# Export rule for registration
RULES = [PerfExcessiveObjectCreationRule()]


