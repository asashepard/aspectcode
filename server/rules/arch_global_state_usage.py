"""Detect direct use of global/singleton mutable state or static service locators.

PURPOSE: This is a KB-enriching rule. It maps shared state locations to help
AI coding agents understand stateful dependencies in the codebase.
Contributes to .aspect/architecture.md "Shared State" section.
"""

from typing import Iterator

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class ArchGlobalStateUsageRule:
    """Map global/singleton mutable state locations for KB enrichment."""
    
    meta = RuleMeta(
        id="arch.global_state_usage",
        category="arch",
        tier=1,
        priority="P3",
        autofix_safety="suggest-only",
        display_mode="kb-only",  # KB-enriching: not shown in Problems panel
        description="Map global/singleton mutable state locations for architectural context",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    requires = Requires(syntax=True, scopes=True, raw_text=True)

    # Only flag patterns that are CLEARLY mutable global state or service locators
    # Be conservative to avoid false positives on legitimate constants, config, etc.
    SINGLETON_CALLS = {
        "java": {"getInstance", "getDefault"},
        "csharp": {"get_Instance", "get_Default", "get_Current"},
        "cpp": {"Instance", "GetInstance"},
        "swift": {"shared"},
        "python": set(),  # Python rarely uses getInstance patterns
        "go": set(),  # Go idioms differ
        "rust": set(),  # Rust uses different patterns
        "ruby": set(),
    }

    # Only flag clearly mutable global state, not constants/config
    GLOBAL_SYMBOL_HINTS = {
        "python": set(),  # Disabled for Python - too many false positives on CONSTANTS
        "javascript": set(),  # Disabled - window/document access is normal browser code
        "typescript": set(),  # Disabled - window/document access is normal browser code
        "go": set(),  # Go globals are idiomatic
        "java": set(),  # Removed System, Runtime, Logger - legitimate usage
        "csharp": set(),  # Removed Environment, ConfigurationManager - legitimate  
        "cpp": {"g_"},  # Only flag g_ prefix - clear global indicator
        "c": {"g_"},
        "ruby": {"$"},  # Ruby $ globals are legitimately flaggable
        "rust": set(),  # Rust has strong safety guarantees
        "swift": set(),  # Removed common singletons - often legitimate
    }

    GLOBAL_ASSIGNMENTS = {
        "python": ["=", "+=", "-=", "*=", "/="],
        "javascript": ["=", "+=", "-=", "*=", "/="],
        "typescript": ["=", "+=", "-=", "*=", "/="],
        "go": ["=", ":=", "+=", "-="],
        "java": ["=", "+=", "-=", "*=", "/="],
        "cpp": ["=", "+=", "-=", "*=", "/="],
        "c": ["=", "+=", "-=", "*=", "/="],
        "csharp": ["=", "+=", "-=", "*=", "/="],
        "ruby": ["=", "+=", "-=", "*=", "/="],
        "rust": ["=", "+=", "-=", "*=", "/="],
        "swift": ["=", "+=", "-=", "*=", "/="],
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for global state usage patterns."""
        if not ctx.syntax:
            return

        lang = ctx.language
        if lang not in self.GLOBAL_SYMBOL_HINTS:
            return

        # Walk the syntax tree looking for global state usage
        for node in ctx.walk_nodes():
            # Check for global variable access
            if self._is_global_reference(ctx, node, lang):
                start_pos, end_pos = ctx.node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message="Accessing global variable directly—consider passing it as a parameter instead.",
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="warning",
                )
                continue

            # Check for singleton/service-locator access
            if self._is_singleton_access(ctx, node, lang):
                # Get the span of the access part
                access_node = self._get_access_node(node)
                start_pos, end_pos = ctx.node_span(access_node)
                yield Finding(
                    rule=self.meta.id,
                    message="Using singleton pattern here—consider dependency injection for easier testing.",
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="warning",
                )

    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        def walk(node):
            yield node
            children = getattr(node, "children", [])
            if children:
                for child in children:
                    yield from walk(child)
        
        root = getattr(tree, "root_node", tree)
        yield from walk(root)

    def _is_global_reference(self, ctx: RuleContext, node, lang: str) -> bool:
        """Check if node represents a global variable reference."""
        node_type = getattr(node, "type", "")
        
        # Look for identifier/name nodes or assignment expressions containing globals
        if node_type not in {"identifier", "name", "variable_name", "assignment_expression", "member_expression"}:
            return False

        # Get the node text
        text = getattr(node, "text", "")
        if isinstance(text, bytes):
            text = text.decode()
        text = str(text)

        # For assignment expressions, check if they contain global symbols
        if node_type == "assignment_expression":
            # Check if it looks like a global symbol assignment
            if self._contains_global_symbol_assignment(text, lang):
                # Check if we're inside a function/method
                if self._inside_function_scope(node):
                    return True
            return False

        # For identifiers, check if it looks like a global symbol
        if not self._looks_like_global_symbol(text, lang):
            return False

        # Check if we're inside a function/method (not at module level)
        if not self._inside_function_scope(node):
            return False

        # Check if it's being assigned to (mutation) or accessed
        if self._is_assignment_target(node, lang) or lang in {"python", "javascript", "typescript"}:
            return True

        return False

    def _contains_global_symbol_assignment(self, text: str, lang: str) -> bool:
        """Check if assignment text contains a global symbol."""
        hints = self.GLOBAL_SYMBOL_HINTS.get(lang, set())
        for hint in hints:
            if hint in text:
                # Check for assignment patterns
                assignment_ops = self.GLOBAL_ASSIGNMENTS.get(lang, ["="])
                for op in assignment_ops:
                    if f"{hint}[" in text and op in text:  # Array/dict assignment
                        return True
                    if f"{hint}." in text and op in text:  # Property assignment
                        return True
                    if f"{hint} {op}" in text:  # Direct assignment
                        return True
        return False

    def _looks_like_global_symbol(self, name: str, lang: str) -> bool:
        """Check if a symbol name looks like a mutable global (not a constant)."""
        if not name:
            return False

        # Check against known global symbol hints (now very limited)
        hints = self.GLOBAL_SYMBOL_HINTS.get(lang, set())
        for hint in hints:
            if hint in name or name.startswith(hint):
                return True

        # Language-specific patterns - ONLY flag clear mutation patterns
        if lang in {"c", "cpp"}:
            # C/C++ globals with g_ prefix are clear indicators
            return name.startswith(('g_', 'G_'))
        elif lang == "ruby":
            # Ruby globals start with $
            return name.startswith('$')

        # Don't flag UPPER_CASE names - they're typically constants, not mutable state
        # Don't flag _private names - they're legitimate encapsulation
        return False

    def _inside_function_scope(self, node) -> bool:
        """Check if node is inside a function/method scope."""
        current = node
        while current:
            node_type = getattr(current, "type", "")
            if node_type in {
                "function_definition", "method_declaration", "function_declaration",
                "arrow_function", "function_expression", "method_definition",
                "constructor_declaration", "function_item"
            }:
                return True
            current = getattr(current, "parent", None)
        return False

    def _is_assignment_target(self, node, lang: str) -> bool:
        """Check if node is the target of an assignment."""
        parent = getattr(node, "parent", None)
        if not parent:
            return False

        parent_type = getattr(parent, "type", "")
        parent_text = getattr(parent, "text", "")
        if isinstance(parent_text, bytes):
            parent_text = parent_text.decode()
        parent_text = str(parent_text)

        # Check for assignment expressions
        if parent_type in {"assignment_expression", "assignment", "augmented_assignment"}:
            # Check if this node is the left side
            left = getattr(parent, "left", None) or getattr(parent, "target", None)
            if left == node:
                return True

        # Check for assignment operators in text
        assignment_ops = self.GLOBAL_ASSIGNMENTS.get(lang, ["="])
        for op in assignment_ops:
            if f" {op} " in parent_text or f"{op}=" in parent_text:
                # Simple heuristic: if node appears before the operator
                node_text = getattr(node, "text", "")
                if isinstance(node_text, bytes):
                    node_text = node_text.decode()
                node_pos = parent_text.find(str(node_text))
                op_pos = parent_text.find(op)
                if node_pos != -1 and op_pos != -1 and node_pos < op_pos:
                    return True

        return False

    def _is_singleton_access(self, ctx: RuleContext, node, lang: str) -> bool:
        """Check if node represents singleton/service-locator access.
        
        Only flag clear service-locator anti-patterns, not legitimate singleton usage.
        """
        node_type = getattr(node, "type", "")
        
        # Look for call expressions and member expressions
        if node_type not in {
            "call_expression", "method_invocation", "member_expression",
            "property_access_expression", "field_expression", "selector_expression",
            "member_access_expression"
        }:
            return False

        # Get the text of the node
        text = getattr(node, "text", "")
        if isinstance(text, bytes):
            text = text.decode()
        text = str(text)

        # Check for singleton method calls (very limited set now)
        singleton_calls = self.SINGLETON_CALLS.get(lang, set())
        for call in singleton_calls:
            if f".{call}(" in text:
                return True

        # Check for known global/singleton objects (very limited set now)
        global_hints = self.GLOBAL_SYMBOL_HINTS.get(lang, set())
        for hint in global_hints:
            if hint in text:
                # Only flag clear patterns
                if lang in {"javascript", "typescript"}:
                    # Only flag direct window/globalThis property access that modifies state
                    if text.startswith(f"{hint}.") and "=" in text:
                        return True
                elif lang == "ruby" and text.startswith("$"):
                    return True

        return False

    def _get_access_node(self, node):
        """Get the most relevant node for span reporting."""
        # For calls, return the callee if available
        callee = getattr(node, "callee", None)
        if callee:
            return callee
        
        # For member expressions, return the property/field
        prop = getattr(node, "property", None) or getattr(node, "field", None)
        if prop:
            return prop
            
        return node

    def _looks_constant(self, name: str, lang: str) -> bool:
        """Check if a name looks like a constant (and thus OK to access globally)."""
        if not name:
            return False
            
        # All uppercase is typically a constant
        if name.isupper():
            return True
            
        # Language-specific constant patterns
        if lang in {"java", "csharp", "cpp", "typescript"}:
            # These languages often use PascalCase for constants
            if name[0].isupper() and '_' not in name:
                return True
                
        return False


# Register the rule
_rule = ArchGlobalStateUsageRule()
RULES = [_rule]


