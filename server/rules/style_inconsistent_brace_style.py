"""
Rule to detect and suggest fixes for inconsistent brace style.

This rule identifies opening braces that don't match the configured style (K&R or Allman)
and provides suggestions to fix them. It operates in suggest-only mode.
"""

from typing import Iterator, List, Optional, Dict, Any

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Tier, Priority
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Tier, Priority


# Supported brace styles
DEFAULT_STYLE = "kr"  # K&R: brace on same line as header
ALLMAN_STYLE = "allman"  # Allman: brace on its own line

# Control structures and declarations that typically have block braces
CONTROL_KEYWORDS = {
    b"if", b"else", b"for", b"while", b"switch", b"try", b"catch", b"finally",
    b"do", b"namespace", b"class", b"struct", b"enum", b"interface", b"func",
    b"function", b"def", b"constructor", b"destructor"
}


class StyleInconsistentBraceStyleRule(Rule):
    """Rule to enforce consistent opening-brace placement (K&R or Allman)."""
    
    meta = RuleMeta(
        id="style.inconsistent_brace_style",
        category="style",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Enforce consistent opening-brace placement (K&R or Allman) based on repo config.",
        langs=["java", "csharp", "cpp", "c", "javascript", "typescript", "go", "swift"]
    )
    
    requires = Requires(raw_text=True, syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect inconsistent brace styles."""
        # Check if this language is supported
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        # Get configured brace style, default to K&R
        config = ctx.config or {}
        style = config.get("brace_style", DEFAULT_STYLE)
        
        if style not in ["kr", "allman"]:
            # Invalid configuration, default to K&R
            style = DEFAULT_STYLE
        
        # Get all tokens from the syntax tree
        tokens = self._get_tokens_from_tree(ctx)
        if not tokens:
            return
        
        # Find opening braces and check their style
        for i, token in enumerate(tokens):
            if not self._is_opening_brace(token):
                continue
            
            # Find the preceding code token to determine context
            prev_token = self._find_previous_code_token(tokens, i)
            if not prev_token:
                continue
            
            # Determine if this is likely a block brace (not a literal)
            if not self._is_likely_block_brace(tokens, i, prev_token):
                continue
            
            # Check if the brace placement matches the configured style
            violation = self._check_brace_style(ctx, tokens, i, prev_token, style)
            if violation:
                yield violation
    
    def _get_tokens_from_tree(self, ctx: RuleContext) -> List[Dict[str, Any]]:
        """Extract tokens from the syntax tree."""
        tokens = []
        
        def traverse_node(node):
            # If this node has children, traverse them
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    traverse_node(child)
            else:
                # This is a leaf node (token)
                tokens.append({
                    'text': node.text,
                    'type': node.type,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'start_point': getattr(node, 'start_point', (0, 0)),
                    'end_point': getattr(node, 'end_point', (0, 0))
                })
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            traverse_node(ctx.tree.root_node)
        
        return tokens
    
    def _is_opening_brace(self, token: Dict[str, Any]) -> bool:
        """Check if the token is an opening brace."""
        return token['text'] == b'{'
    
    def _find_previous_code_token(self, tokens: List[Dict[str, Any]], current_idx: int) -> Optional[Dict[str, Any]]:
        """Find the previous non-whitespace, non-comment token."""
        for i in range(current_idx - 1, -1, -1):
            token = tokens[i]
            token_type = token['type']
            
            # Skip whitespace, newlines, and comments
            if token_type in ('whitespace', 'newline', 'comment', 'line_comment', 'block_comment'):
                continue
            
            return token
        
        return None
    
    def _is_likely_block_brace(self, tokens: List[Dict[str, Any]], brace_idx: int, prev_token: Dict[str, Any]) -> bool:
        """
        Determine if this brace is likely a block brace rather than a literal.
        
        This is a heuristic to avoid flagging object literals, array literals, etc.
        """
        prev_text = prev_token['text']
        prev_type = prev_token['type']
        
        # Common patterns for block braces:
        # 1. After closing parenthesis: if (...) { or function(...) {
        # 2. After keywords: class {, struct {, enum {
        # 3. After identifiers that could be class/function names
        
        if prev_text == b')':
            # This is likely a control structure or function definition
            return True
        
        if prev_type == 'identifier':
            # Could be class name, function name, etc.
            # Look back further to see if it's preceded by a control keyword
            return self._has_preceding_control_keyword(tokens, brace_idx, prev_token)
        
        if prev_text in CONTROL_KEYWORDS:
            # Direct control keyword before brace
            return True
        
        # Check for specific patterns that indicate blocks
        if prev_text in (b':', b';', b'}'):
            # Could be after class inheritance, enum value, or another block
            return True
        
        # Be conservative - if we're not sure, don't flag it
        return False
    
    def _has_preceding_control_keyword(self, tokens: List[Dict[str, Any]], brace_idx: int, identifier_token: Dict[str, Any]) -> bool:
        """Check if there's a control keyword before the identifier."""
        # Find the identifier in the token list
        identifier_idx = None
        for i in range(brace_idx):
            if tokens[i] == identifier_token:
                identifier_idx = i
                break
        
        if identifier_idx is None:
            return False
        
        # Look backwards for control keywords
        for i in range(identifier_idx - 1, max(0, identifier_idx - 10), -1):
            token = tokens[i]
            if token['type'] in ('whitespace', 'newline', 'comment', 'line_comment', 'block_comment'):
                continue
            
            if token['text'] in CONTROL_KEYWORDS:
                return True
            
            # Stop at certain tokens that would break the pattern
            if token['text'] in (b';', b'}', b'{'):
                break
        
        return False
    
    def _check_brace_style(self, ctx: RuleContext, tokens: List[Dict[str, Any]], 
                          brace_idx: int, prev_token: Dict[str, Any], style: str) -> Optional[Finding]:
        """Check if the brace placement matches the expected style."""
        brace_token = tokens[brace_idx]
        
        # Get line numbers
        prev_line = prev_token['start_point'][0]
        brace_line = brace_token['start_point'][0]
        
        # Determine if style matches expectation
        violation = False
        expected_placement = ""
        
        if style == "kr":
            # K&R: brace should be on the same line as the header
            if brace_line != prev_line:
                violation = True
                expected_placement = "same line"
        elif style == "allman":
            # Allman: brace should be on its own line (different from header)
            if brace_line == prev_line:
                violation = True
                expected_placement = "new line"
        
        if not violation:
            return None
        
        # Generate suggestion
        suggestion = self._generate_suggestion(ctx, prev_token, brace_token, style)
        
        return Finding(
            rule=self.meta.id,
            message=f"Inconsistent brace style: expected {style.upper()} placement ({expected_placement}).",
            file=ctx.file_path,
            start_byte=brace_token['start_byte'],
            end_byte=brace_token['end_byte'],
            severity="info",
            autofix=None,  # suggest-only rule
            meta={
                "style": style,
                "expected_placement": expected_placement,
                "suggestion": suggestion
            }
        )
    
    def _generate_suggestion(self, ctx: RuleContext, prev_token: Dict[str, Any], 
                           brace_token: Dict[str, Any], style: str) -> Dict[str, str]:
        """Generate a suggestion for fixing the brace style."""
        text = ctx.text
        
        # Find the line boundaries
        prev_line_start = self._find_line_start(text, prev_token['start_byte'])
        brace_line_end = self._find_line_end(text, brace_token['end_byte'])
        
        # Extract the current text
        current_text = text[prev_line_start:brace_line_end]
        
        # Generate the suggested text
        if style == "kr":
            # K&R: move brace to same line with single space
            suggested_text = self._generate_kr_suggestion(current_text, prev_token, brace_token, prev_line_start)
        else:  # allman
            # Allman: move brace to new line
            suggested_text = self._generate_allman_suggestion(current_text, prev_token, brace_token, prev_line_start)
        
        # Create unified diff
        diff = f"""--- a/current
+++ b/suggested
-{current_text}
+{suggested_text}"""
        
        rationale = f'Place opening brace according to "{style.upper()}" style.'
        
        return {
            "diff": diff,
            "rationale": rationale
        }
    
    def _find_line_start(self, text: str, byte_pos: int) -> int:
        """Find the start of the line containing the given byte position."""
        line_start = text.rfind('\n', 0, byte_pos)
        return line_start + 1 if line_start != -1 else 0
    
    def _find_line_end(self, text: str, byte_pos: int) -> int:
        """Find the end of the line containing the given byte position."""
        line_end = text.find('\n', byte_pos)
        return line_end + 1 if line_end != -1 else len(text)
    
    def _generate_kr_suggestion(self, current_text: str, prev_token: Dict[str, Any], 
                               brace_token: Dict[str, Any], line_start: int) -> str:
        """Generate K&R style suggestion (brace on same line)."""
        # Find the header part (up to the previous token)
        header_end = prev_token['end_byte'] - line_start
        header = current_text[:header_end].rstrip()
        
        # Add brace on the same line with a space
        return header + " {\n"
    
    def _generate_allman_suggestion(self, current_text: str, prev_token: Dict[str, Any], 
                                   brace_token: Dict[str, Any], line_start: int) -> str:
        """Generate Allman style suggestion (brace on new line)."""
        # Find the header part (up to the previous token)
        header_end = prev_token['end_byte'] - line_start
        header = current_text[:header_end].rstrip()
        
        # Add brace on new line
        return header + "\n{\n"


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(StyleInconsistentBraceStyleRule())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


