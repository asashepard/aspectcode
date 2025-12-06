"""Rule: lang.ts_loose_equality

Replaces loose equality operators (== and !=) with strict equality operators
(=== and !==) to avoid type coercion issues in TypeScript and JavaScript.

Type coercion with loose equality can lead to unexpected behavior and bugs.
Examples:
- 0 == false         # true (unexpected)
- '0' == false       # true (unexpected) 
- null == undefined  # true (can be allowed via config)
- '' == 0            # true (unexpected)

Strict equality avoids these issues:
- 0 === false        # false (expected)
- '0' === false      # false (expected)
- null === undefined # false (expected)
"""

from typing import Iterator, Optional

from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit


class TsLooseEqualityRule:
    """Replace loose equality with strict equality in TypeScript/JavaScript."""
    
    meta = RuleMeta(
        id="lang.ts_loose_equality",
        category="lang",  # Corrected from "style" to match spec
        tier=0,
        priority="P0", 
        autofix_safety="safe",
        description="Use strict equality ===/!== instead of ==/!=",
        langs=["typescript", "javascript"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find loose equality operators and provide safe autofixes."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Walk the tree to find binary expressions with loose equality
        for node in self._iter_nodes(ctx.tree):
            if self._is_loose_equality_expression(node):
                operator, operator_pos = self._extract_operator_info(node, ctx)
                if operator and self._should_fix_operator(operator, node, ctx):
                    replacement = "===" if operator == "==" else "!=="
                    
                    # Create autofix edit
                    start_byte, end_byte = operator_pos
                    autofix = [Edit(
                        start_byte=start_byte,
                        end_byte=end_byte,
                        replacement=replacement
                    )]
                    
                    # Get full expression span for the finding
                    expr_start, expr_end = self._get_node_span(node)
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Use strict equality '{replacement}' instead of '{operator}' to avoid type coercion",
                        file=ctx.file_path,
                        start_byte=expr_start,
                        end_byte=expr_end,
                        severity="warning",  # Following spec
                        autofix=autofix
                    )
    
    def _iter_nodes(self, tree):
        """Iterate through all nodes in the tree."""
        def visit_node(node):
            if node is None:
                return
                
            yield node
            
            # Visit children recursively
            for child in getattr(node, 'children', []):
                yield from visit_node(child)
        
        # Start from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def _is_loose_equality_expression(self, node) -> bool:
        """Check if this node is a binary expression with loose equality."""
        node_type = getattr(node, 'type', '') or getattr(node, 'kind', '')
        
        if node_type != 'binary_expression':
            return False
        
        # Look for loose equality operators in children
        for child in getattr(node, 'children', []):
            child_text = self._get_node_text(child)
            if child_text in ['==', '!=']:
                return True
        
        return False
    
    def _extract_operator_info(self, node, ctx: RuleContext) -> tuple:
        """Extract operator text and position from a binary expression."""
        for child in getattr(node, 'children', []):
            child_text = self._get_node_text(child, ctx)
            if child_text in ['==', '!=']:
                start_byte, end_byte = self._get_node_span(child)
                return child_text, (start_byte, end_byte)
        
        return None, (0, 0)
    
    def _should_fix_operator(self, operator: str, node, ctx: RuleContext) -> bool:
        """Determine if the operator should be fixed based on configuration."""
        # Basic implementation - could be extended with config for nullish checks
        # For now, always fix loose equality unless it's a nullish check pattern
        
        if self._is_nullish_check_pattern(node, ctx):
            # Check if nullish checks are allowed via configuration
            config = getattr(ctx, 'config', {})
            allow_nullish_checks = config.get('allow_nullish_checks', False)
            return not allow_nullish_checks
        
        return True
    
    def _is_nullish_check_pattern(self, node, ctx: RuleContext) -> bool:
        """Check if this is a nullish check pattern (== null or != null)."""
        # Get the operands to check for null/undefined comparisons
        operands = []
        operator = None
        
        for child in getattr(node, 'children', []):
            child_type = getattr(child, 'type', '') or getattr(child, 'kind', '')
            child_text = self._get_node_text(child, ctx).strip()
            
            if child_text in ['==', '!=']:
                operator = child_text
            elif child_type in ['identifier', 'null', 'undefined'] or child_text in ['null', 'undefined']:
                operands.append(child_text)
        
        # Check if one operand is null or undefined
        return any(op in ['null', 'undefined'] for op in operands) and operator in ['==', '!=']
    
    def _get_node_text(self, node, ctx: RuleContext = None) -> str:
        """Extract text from a node."""
        if not node:
            return ""
        
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Fallback: use span to extract from source
        if ctx and hasattr(ctx, 'text'):
            start_byte, end_byte = self._get_node_span(node)
            try:
                return ctx.text[start_byte:end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""
    
    def _get_node_span(self, node) -> tuple:
        """Get the start and end byte positions of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        # If no span info, try to estimate
        if start_byte == end_byte == 0:
            # Use a default span
            end_byte = start_byte + 2  # For operators like ==
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [TsLooseEqualityRule()]


