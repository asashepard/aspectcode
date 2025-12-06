"""
perf.string_concat_in_loop rule: Warn when strings are concatenated inside loops.

Detects inefficient string concatenation patterns like:
- s += x inside loops
- s = s + x inside loops

Suggests more efficient alternatives:
- Python: collect to list + ''.join(list)
- Java/C#: StringBuilder / StringBuilder.Append
- JS/TS: push to array + arr.join('')
- Ruby: prefer String#<< or StringIO over +=
- Go: strings.Builder / bytes.Buffer
"""

from typing import Iterator
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext


class PerfStringConcatInLoopRule(Rule):
    """Detects string concatenation inside loops and suggests efficient alternatives."""
    
    meta = RuleMeta(
        id="perf.string_concat_in_loop",
        category="perf",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Warn when strings are concatenated inside loops",
        langs=["python", "java", "csharp", "javascript", "typescript", "ruby", "go"],
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx) -> Iterator[Finding]:
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return

        """Visit file and detect string concatenation inside loops."""
        if not hasattr(ctx, 'syntax') or not ctx.syntax:
            return
        
        for node in ctx.walk_nodes():
            if not self._in_loop(node):
                continue
                
            # Case A: s += expr
            if self._is_plus_equal_stringy(node, ctx):
                start_pos, end_pos = ctx.node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message=self._msg(ctx.language, "+="),
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="warning",
                )
                continue
                
            # Case B: s = s + expr
            if self._is_self_plus_expr(node, ctx):
                start_pos, end_pos = ctx.node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message=self._msg(ctx.language, "="),
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="warning",
                )
    
    def _in_loop(self, node) -> bool:
        """Check if node is inside a loop by walking up parent chain."""
        current = node
        while current:
            parent = getattr(current, 'parent', None)
            if not parent:
                break
            
            kind = getattr(parent, 'kind', '') or getattr(parent, 'type', '')
            if kind in {
                'for_statement', 'while_statement', 'for_in_statement', 
                'for_of_statement', 'foreach_statement', 'enhanced_for_statement',
                'for_loop', 'while_loop', 'range_loop'
            }:
                return True
            current = parent
        return False
    
    def _is_plus_equal_stringy(self, node, ctx) -> bool:
        """Check if node is s += expr with string-like variable."""
        kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        if kind not in {'assignment_expression', 'augmented_assignment', 'assignment'}:
            return False
        
        operator = getattr(node, 'operator', '')
        if operator != '+=':
            return False
        
        # Get left-hand side
        lhs = getattr(node, 'left', None)
        if not lhs:
            return False
        
        return self._looks_string_var(lhs, ctx)
    
    def _is_self_plus_expr(self, node, ctx) -> bool:
        """Check if node is s = s + expr with same variable on both sides."""
        kind = getattr(node, 'kind', '')
        if kind not in {'assignment_expression', 'assignment'}:
            return False
        
        operator = getattr(node, 'operator', '')
        if operator != '=':
            return False
        
        lhs = getattr(node, 'left', None)
        rhs = getattr(node, 'right', None)
        
        if not lhs or not rhs:
            return False
        
        # Check if RHS is binary + expression
        rhs_kind = getattr(rhs, 'kind', '')
        if rhs_kind not in {'binary_expression', 'binary_operator'}:
            return False
        
        rhs_operator = getattr(rhs, 'operator', '')
        if rhs_operator != '+':
            return False
        
        # Check if LHS matches RHS left operand
        lhs_id = self._id_text(lhs, ctx)
        rhs_left = getattr(rhs, 'left', None)
        rhs_left_id = self._id_text(rhs_left, ctx)
        
        if not lhs_id or lhs_id != rhs_left_id:
            return False
        
        return self._looks_string_var(lhs, ctx)
    
    def _id_text(self, node, ctx):
        """Extract identifier text from node."""
        if not node:
            return None
        
        # Try different ways to get the identifier
        identifier = getattr(node, 'identifier', None)
        if identifier:
            return ctx.syntax.token_text(identifier)
        
        name = getattr(node, 'name', None)
        if name:
            return ctx.syntax.token_text(name)
        
        # For simple identifiers, try getting text directly
        kind = getattr(node, 'kind', '')
        if kind in {'identifier', 'variable', 'name'}:
            try:
                return ctx.syntax.token_text(node)
            except:
                pass
        
        return None
    
    def _looks_string_var(self, node, ctx) -> bool:
        """Heuristic to determine if variable looks string-typed."""
        if not node:
            return False
        
        # Try to get declared type
        declared_type = getattr(node, 'declared_type', None)
        if declared_type:
            type_text = str(getattr(declared_type, 'text', '')).lower()
            if any(x in type_text for x in ('string', 'str')):
                return True
        
        # Textual fallback - look for type annotations
        try:
            # Get all tokens from the node and check for string type hints
            tokens = list(ctx.syntax.iter_tokens(node))
            if tokens:
                node_text = ''.join(ctx.syntax.token_text(t) for t in tokens)
                if any(pattern in node_text for pattern in (': string', 'String ', 'string ', 'str ')):
                    return True
        except:
            pass
        
        # For variables without clear type info, be conservative but catch common patterns
        # Check if it's a simple identifier (not a complex expression)
        kind = getattr(node, 'kind', '')
        if kind in {'identifier', 'variable', 'name'}:
            return True  # Accept simple variables - they could be strings
        
        return False
    
    def _msg(self, lang: str, op: str) -> str:
        """Generate appropriate message for the language and operation."""
        guidance = {
            "python": "collect parts in a list and ''.join(parts)",
            "java": "use StringBuilder and .append(...)",
            "csharp": "use StringBuilder and .Append(...)",
            "javascript": "push to array and .join('')",
            "typescript": "push to array and .join('')",
            "ruby": "use String#<< or StringIO",
            "go": "use strings.Builder or bytes.Buffer",
        }.get(lang, "use a string builder pattern")
        
        return f"String concatenation inside loop ({op}); prefer {guidance}."
    
    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        def walk(node):
            if node is not None:
                yield node
                children = getattr(node, 'children', [])
                for child in children:
                    yield from walk(child)
        
        root = getattr(tree, 'root_node', tree)
        yield from walk(root)


# Export the rule for registration
RULES = [PerfStringConcatInLoopRule()]


