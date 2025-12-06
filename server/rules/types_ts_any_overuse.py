"""
Types TypeScript Any Overuse Rule

Detects overuse of TypeScript escape hatches including explicit `any` types,
`as any` casts, type assertions with `any`, and non-null assertions (`!`).
Recommends precise types, `unknown` with narrowing, generics, or proper null checks.

Rule ID: types.ts_any_overuse
Category: types
Severity: warn
Priority: P1
Languages: typescript
Autofix: suggest-only
"""

import re
from typing import Iterable, Optional

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class TypesTsAnyOveruseRule:
    """Rule to detect overuse of TypeScript escape hatches like `any` and non-null assertions."""
    
    meta = RuleMeta(
        id="types.ts_any_overuse",
        category="types",
        tier=0,  # Syntax-only analysis
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects overuse of TypeScript escape hatches (any, non-null assertions)",
        langs=["typescript"]
    )
    requires = Requires(syntax=True)

    ANY_MSG = "Avoid 'any'; prefer precise types or 'unknown' with narrowing."
    NN_MSG = "Avoid non-null assertion '!'; add a null check, use optional chaining, or refine the type."

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for TypeScript escape hatch overuse."""
        if not ctx.tree:
            return
            
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            
        for node in ctx.walk_nodes(ctx.tree.root_node):
            node_type = node.type
            
            # Check for any type usage in type annotations, references, and assertions
            if node_type in {"type_annotation", "type_identifier", "type_reference", "type_assertion"}:
                if self._type_contains_any(ctx, node):
                    yield Finding(
                        rule=self.meta.id,
                        message=self.ANY_MSG,
                        file=ctx.file_path,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        severity="warning"
                    )
            
            # Check for 'as any' expressions
            elif node_type == "as_expression":
                if self._is_as_any(ctx, node):
                    yield Finding(
                        rule=self.meta.id,
                        message=self.ANY_MSG + " (found 'as any')",
                        file=ctx.file_path,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        severity="warning"
                    )
            
            # Check for non-null expressions (value!)
            elif node_type == "non_null_expression":
                yield Finding(
                    rule=self.meta.id,
                    message=self.NN_MSG,
                    file=ctx.file_path,
                    start_byte=node.start_byte,
                    end_byte=node.end_byte,
                    severity="warning"
                )
            
            # Check for definite assignment assertions in class fields
            elif node_type in {"class_field_declaration", "property_declaration", "public_field_definition"}:
                if self._has_definite_assignment_assertion(ctx, node):
                    yield Finding(
                        rule=self.meta.id,
                        message=self.NN_MSG + " (definite assignment '!')",
                        file=ctx.file_path,
                        start_byte=node.start_byte,
                        end_byte=node.end_byte,
                        severity="warning"
                    )

    def _walk_nodes(self, node):
        """Recursively walk all nodes in the tree."""
        yield node
        for child in node.children:
            yield from self._walk_nodes(child)

    def _type_contains_any(self, ctx: RuleContext, node) -> bool:
        """Check if a type node contains the 'any' keyword."""
        node_text = self._get_node_text(ctx, node)
        
        # Use a more sophisticated check for 'any' as a standalone word
        # This handles cases like Array<any>, string | any, etc.
        # Match 'any' as a complete word (not part of another word)
        return bool(re.search(r'\bany\b', node_text))

    def _is_as_any(self, ctx: RuleContext, node) -> bool:
        """Check if an 'as' expression casts to 'any'."""
        node_text = self._get_node_text(ctx, node)
        
        # Look for 'as any' pattern
        return "as" in node_text and "any" in node_text

    def _has_definite_assignment_assertion(self, ctx: RuleContext, node) -> bool:
        """Check if a class field has a definite assignment assertion (!)."""
        node_text = self._get_node_text(ctx, node)
        
        # Look for field!: pattern (! before the colon)
        if ":" not in node_text:
            return False
            
        # Split on colon and check if the left part contains !
        field_part = node_text.split(":", 1)[0]
        return "!" in field_part

    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get the text content of a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return text
        
        # Fallback: get text from source using byte positions
        if ctx.raw_text and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.raw_text[node.start_byte:node.end_byte]
        
        return ""


# Register the rule for auto-discovery
_rule = TypesTsAnyOveruseRule()
RULES = [_rule]


