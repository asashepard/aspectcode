"""
Copy-Paste Mistake Detection Rule

This rule detects near-duplicate statements in the same block that differ only by
likely-typo identifiers or mismatched LHS/RHS pairs. These patterns often indicate
copy-paste mistakes that need review.

Common patterns detected:
- Single character typos: `total += price;` then `total += prcie;`
- Mismatched assignments: `x = a; y = a;` when pattern suggests `y = b;`
- Similar statements with suspicious identifier differences

Examples:
- SUSPICIOUS: total += price; total += prcie;  # typo in 'prcie'
- SUSPICIOUS: a = foo; b = foo;                # should b = bar?
- OK: sum += a[i]; sum += b[i];               # meaningful difference

The rule provides suggest-only diagnostics to flag potential issues for review.
"""

from typing import Iterable, List, Tuple, Optional

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugCopyPasteMistRule:
    """
    Rule to detect near-duplicate statements that likely result from copy-paste mistakes.
    
    Analyzes statements within the same block for suspicious patterns:
    1. Statements with identical structure but single-character typos
    2. Consecutive assignments with same RHS but different LHS
    
    Provides suggest-only diagnostics for manual review.
    """
    
    meta = RuleMeta(
        id="bug.copy_paste_mist",
        category="bug",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects near-duplicate statements that differ by likely typos or mismatched LHS/RHS pairs—surfaces probable copy-paste mistakes.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Heuristic configuration
    MAX_STMT_TOKENS = 30
    MIN_IDENT_LEN = 2
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze file for copy-paste mistakes in statement blocks."""
        if not ctx.syntax_tree:
            return
            
        yield from self._analyze_syntax_tree(ctx, ctx.syntax_tree)
    
    def _analyze_syntax_tree(self, ctx: RuleContext, root) -> Iterable[Finding]:
        """Walk syntax tree to find statement blocks and analyze them."""
        for block in self._find_blocks(root):
            yield from self._scan_block(ctx, block)
    
    def _find_blocks(self, root) -> Iterable:
        """Find all blocks containing statements in the syntax tree."""
        # Use the engine's walk functionality to traverse all nodes
        if hasattr(root, 'walk'):
            for node in root.walk():
                if self._is_statement_block(node):
                    yield node
        else:
            # Fallback for simple tree structures
            yield from self._walk_node(root)
    
    def _walk_node(self, node) -> Iterable:
        """Manually walk node tree if walk() method not available."""
        if self._is_statement_block(node):
            yield node
        
        # Walk children
        if hasattr(node, 'children'):
            for child in node.children:
                yield from self._walk_node(child)
    
    def _is_statement_block(self, node) -> bool:
        """Check if node represents a block containing statements."""
        # Common block indicators across languages
        block_indicators = [
            'statements', 'body', 'block', 'suite', 'compound_statement',
            'function_body', 'if_statement', 'while_statement', 'for_statement',
            'block_statement', 'declaration_list'
        ]
        
        return any(hasattr(node, attr) for attr in block_indicators)
    
    def _scan_block(self, ctx: RuleContext, block) -> Iterable[Finding]:
        """Scan a statement block for copy-paste patterns."""
        statements = self._get_statements(block)
        if len(statements) < 2:
            return
        
        # Build signatures for each statement
        signatures = []
        for stmt in statements:
            sig, identifiers = self._build_signature(ctx, stmt)
            if sig and identifiers:
                signatures.append((stmt, sig, identifiers))
        
        # Compare adjacent statements for suspicious patterns
        for i in range(len(signatures) - 1):
            stmt1, sig1, ids1 = signatures[i]
            stmt2, sig2, ids2 = signatures[i + 1]
            
            # Skip if signatures don't match or identifier counts differ
            if sig1 != sig2 or len(ids1) != len(ids2):
                continue
            
            # Find identifier mismatches
            mismatches = []
            for id1, id2 in zip(ids1, ids2):
                text1 = self._get_identifier_text(ctx, id1)
                text2 = self._get_identifier_text(ctx, id2)
                if text1 != text2:
                    mismatches.append((id1, id2, text1, text2))
            
            # Check for single typo mismatch
            if len(mismatches) == 1:
                _, id2_token, text1, text2 = mismatches[0]
                if self._looks_like_typo(text1, text2):
                    start_byte, end_byte = self._get_node_span(ctx, stmt2)
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Near-duplicate statements differ by '{text2}' vs '{text1}'—possible copy-paste typo.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="info",
                        meta={
                            "suspicious_identifier": text2,
                            "expected_identifier": text1,
                            "pattern": "single_typo"
                        }
                    )
                # Check for LHS/RHS mismatch pattern if not a typo
                elif self._has_lhs_rhs_mismatch(ctx, ids1, ids2):
                    start_byte, end_byte = self._get_node_span(ctx, stmt2)
                    yield Finding(
                        rule=self.meta.id,
                        message="Consecutive assignments look copy-pasted (same RHS, different LHS). Verify referenced identifiers.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="info",
                        meta={
                            "pattern": "lhs_rhs_mismatch"
                        }
                    )
    
    def _get_statements(self, block) -> List:
        """Extract statements from a block node."""
        # Try common statement container attributes
        for attr in ['statements', 'body', 'children']:
            if hasattr(block, attr):
                stmts = getattr(block, attr)
                if isinstance(stmts, list):
                    return stmts
        return []
    
    def _build_signature(self, ctx: RuleContext, stmt) -> Tuple[str, List]:
        """Build a normalized signature for a statement."""
        tokens = self._get_statement_tokens(ctx, stmt)
        if len(tokens) > self.MAX_STMT_TOKENS:
            tokens = tokens[:self.MAX_STMT_TOKENS]
        
        identifiers = []
        signature_parts = []
        
        for token in tokens:
            text = self._get_token_text(ctx, token)
            
            if self._is_identifier_token(ctx, token, text):
                if len(text) >= self.MIN_IDENT_LEN:
                    identifiers.append(token)
                    signature_parts.append("ID")
            elif self._is_literal_token(ctx, token):
                signature_parts.append("LIT")
            elif self._is_operator_token(text):
                signature_parts.append(text)
        
        signature = " ".join(signature_parts)
        return signature, identifiers
    
    def _get_statement_tokens(self, ctx: RuleContext, stmt) -> List:
        """Get tokens for a statement using language adapter."""
        try:
            # First try to use the statement's own tokens if available
            if hasattr(stmt, 'tokens'):
                return stmt.tokens
            
            # Try to use language adapter's token iteration if available
            adapter = ctx.registry.get_adapter(ctx.language)
            if hasattr(adapter, 'iter_tokens'):
                tokens = list(adapter.iter_tokens(stmt))
                if tokens:  # Only return if we got tokens
                    return tokens
            
            # Fallback: try to extract tokens from text
            return self._extract_tokens_from_text(ctx, stmt)
        except Exception:
            return []
    
    def _extract_tokens_from_text(self, ctx: RuleContext, stmt) -> List:
        """Fallback token extraction from statement text."""
        # This is a simplified fallback - in practice, the language adapters
        # would provide proper token iteration
        start_byte, end_byte = self._get_node_span(ctx, stmt)
        if start_byte is not None and end_byte is not None:
            stmt_text = ctx.text[start_byte:end_byte]
            # Very simple tokenization - split on whitespace and common delimiters
            import re
            tokens = re.findall(r'\w+|[^\w\s]', stmt_text)
            # Create simple token objects
            return [{'text': t, 'type': 'token'} for t in tokens if t.strip()]
        return []
    
    def _get_token_text(self, ctx: RuleContext, token) -> str:
        """Get text content of a token."""
        if isinstance(token, dict):
            return token.get('text', '')
        elif hasattr(token, 'text'):
            return token.text
        elif hasattr(token, 'value'):
            return str(token.value)
        else:
            return str(token)
    
    def _is_identifier_token(self, ctx: RuleContext, token, text: str) -> bool:
        """Check if token represents an identifier."""
        if isinstance(token, dict):
            return token.get('type') == 'identifier' or text.isidentifier()
        
        # Check common identifier indicators
        if hasattr(token, 'is_identifier'):
            return token.is_identifier
        elif hasattr(token, 'kind'):
            return token.kind in {'identifier', 'name', 'variable'}
        elif hasattr(token, 'type'):
            return token.type in {'identifier', 'name', 'variable'}
        
        # Fallback: check if text looks like identifier
        return text.isidentifier() if text else False
    
    def _is_literal_token(self, ctx: RuleContext, token) -> bool:
        """Check if token represents a literal value."""
        if isinstance(token, dict):
            return token.get('type') in {'number', 'string', 'boolean', 'literal'}
        
        if hasattr(token, 'kind'):
            return token.kind in {'integer', 'float', 'string', 'char', 'boolean', 'nil', 'null', 'literal'}
        elif hasattr(token, 'type'):
            return token.type in {'integer', 'float', 'string', 'char', 'boolean', 'nil', 'null', 'literal'}
        
        return False
    
    def _is_operator_token(self, text: str) -> bool:
        """Check if text represents an operator or delimiter."""
        operators = {
            "=", "+=", "-=", "*=", "/=", "==", "!=", "<", ">", "<=", ">=",
            ".", "->", "[", "]", "(", ")", "+", "-", "*", "/", "%", "|", "&", "^",
            "&&", "||", "!", "~", "<<", ">>", "::", "?", ":", ";", ",", "{", "}"
        }
        return text in operators
    
    def _get_identifier_text(self, ctx: RuleContext, token) -> str:
        """Get the text of an identifier token."""
        return self._get_token_text(ctx, token)
    
    def _looks_like_typo(self, text1: str, text2: str) -> bool:
        """Check if two identifiers look like a typo of each other."""
        # Same length within 1 character
        if abs(len(text1) - len(text2)) > 1:
            return False
        
        # Same first character (common pattern)
        if text1 and text2 and text1[0] != text2[0]:
            return False
        
        # Calculate simple edit distance
        edit_distance = self._simple_edit_distance(text1, text2)
        
        # Allow 1-2 edits depending on length
        if len(text1) <= 3 or len(text2) <= 3:
            return edit_distance <= 1
        else:
            return edit_distance <= 2
    
    def _simple_edit_distance(self, s1: str, s2: str) -> int:
        """Calculate simple edit distance between two strings."""
        if len(s1) == 0:
            return len(s2)
        if len(s2) == 0:
            return len(s1)
        
        # Create matrix
        matrix = [[0] * (len(s2) + 1) for _ in range(len(s1) + 1)]
        
        # Initialize base cases
        for i in range(len(s1) + 1):
            matrix[i][0] = i
        for j in range(len(s2) + 1):
            matrix[0][j] = j
        
        # Fill matrix
        for i in range(1, len(s1) + 1):
            for j in range(1, len(s2) + 1):
                if s1[i-1] == s2[j-1]:
                    cost = 0
                else:
                    cost = 1
                
                matrix[i][j] = min(
                    matrix[i-1][j] + 1,      # deletion
                    matrix[i][j-1] + 1,      # insertion
                    matrix[i-1][j-1] + cost  # substitution
                )
        
        return matrix[len(s1)][len(s2)]
    
    def _has_lhs_rhs_mismatch(self, ctx: RuleContext, ids1: List, ids2: List) -> bool:
        """Check for LHS/RHS mismatch pattern in assignments."""
        if len(ids1) < 2 or len(ids2) < 2:
            return False
        
        # Assume first identifier is LHS, last is RHS for assignment patterns
        lhs1 = self._get_identifier_text(ctx, ids1[0])
        lhs2 = self._get_identifier_text(ctx, ids2[0])
        rhs1 = self._get_identifier_text(ctx, ids1[-1])
        rhs2 = self._get_identifier_text(ctx, ids2[-1])
        
        # Different LHS but same RHS suggests copy-paste error
        return lhs1 != lhs2 and rhs1 == rhs2
    
    def _get_node_span(self, ctx: RuleContext, node) -> Tuple[Optional[int], Optional[int]]:
        """Get byte span of a syntax node."""
        try:
            # Try to use language adapter for span calculation
            adapter = ctx.registry.get_adapter(ctx.language)
            if hasattr(adapter, 'node_span'):
                return adapter.node_span(node)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return node.start_byte, node.end_byte
            elif hasattr(node, 'span'):
                span = node.span
                if hasattr(span, 'start') and hasattr(span, 'end'):
                    return span.start, span.end
            else:
                # Fallback: try to estimate from text position
                return self._estimate_node_span(ctx, node)
        except Exception:
            return None, None
    
    def _estimate_node_span(self, ctx: RuleContext, node) -> Tuple[Optional[int], Optional[int]]:
        """Fallback span estimation."""
        # This is a very basic fallback - real implementations would use
        # proper syntax tree traversal to find node positions
        return None, None


# Register the rule
_rule = BugCopyPasteMistRule()
RULES = [_rule]


