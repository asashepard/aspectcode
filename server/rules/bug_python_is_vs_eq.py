"""
Python Identity vs Equality Comparison Rule

This rule detects improper use of 'is' and 'is not' operators for value comparisons
where '==' and '!=' should be used instead. Identity operators should only be used
for singletons like None, NotImplemented, and Ellipsis.

Common problematic patterns:
- Using 'is' to compare strings or numbers
- Using 'is not' for value inequality checks

Examples:
- RISKY: if x is "hello":     # unreliable, use ==
- RISKY: if count is 0:       # unreliable, use ==
- SAFE:  if x is None:        # identity check for singleton
- SAFE:  if a is b:           # legitimate identity check

The rule provides safe autofix by replacing:
- 'is' → '=='
- 'is not' → '!='
"""

import re
from typing import Iterable, Set, Optional, List, Dict, Any

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class BugPythonIsVsEqRule:
    """
    Rule to detect improper use of 'is'/'is not' for value comparisons in Python.
    
    Flags 'is' and 'is not' used to compare strings, numbers, or other value-like
    expressions where '==' and '!=' should be used instead. Allows identity 
    checks for singletons (None, NotImplemented, Ellipsis).
    
    Examples of flagged patterns:
    - if x is "hello":
    - if count is 0:
    - if value is not 3.14:
    
    Examples of safe patterns:
    - if x is None:
    - if result is NotImplemented:
    - if obj is another_obj:  # legitimate identity check
    """
    
    meta = RuleMeta(
        id="bug.python_is_vs_eq",
        category="bug",
        tier=0,
        priority="P0",
        autofix_safety="safe",
        description="Flags `is` / `is not` used to compare strings or numbers; prefer value equality (`==` / `!=`). Keep identity checks for `None` (and other singletons) unchanged.",
        langs=["python"]
    )
    
    requires = Requires(syntax=True)
    
    # Python singletons that should use identity comparison
    SINGLETONS = {"None", "True", "False", "NotImplemented", "Ellipsis"}
    
    # Patterns to detect 'is' and 'is not' comparisons
    IS_COMPARISON_PATTERNS = [
        # Match: expression is expression (more flexible)
        r'(.+?)\s+(is)\s+(?!not\s)(.+?)(?=\s*(?:$|:|\s+and\s+|\s+or\s+|\s+is\s+|\s+is\s+not\s+|,|\)|;|#))',
        # Match: expression is not expression  
        r'(.+?)\s+(is\s+not)\s+(.+?)(?=\s*(?:$|:|\s+and\s+|\s+or\s+|\s+is\s+|\s+is\s+not\s+|,|\)|;|#))',
    ]
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze Python code for improper 'is'/'is not' usage."""
        if ctx.language != "python":
            return
        
        # Use text-based analysis consistent with the codebase pattern
        yield from self._analyze_text(ctx, ctx.text)
    
    def _analyze_text(self, ctx: RuleContext, text: str) -> Iterable[Finding]:
        """Analyze text for 'is'/'is not' vs '=='/'!=' issues."""
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            # Skip comments to avoid false positives
            if self._is_comment_line(line):
                continue
            
            # Find all 'is' and 'is not' comparisons in this line
            yield from self._check_line_for_is_comparisons(ctx, line, line_num, lines)
    
    def _check_line_for_is_comparisons(self, ctx: RuleContext, line: str, line_num: int, all_lines: List[str]) -> Iterable[Finding]:
        """Check a single line for problematic 'is'/'is not' comparisons."""
        
        # Use the defined patterns
        for pattern in self.IS_COMPARISON_PATTERNS:
            for match in re.finditer(pattern, line):
                left_expr = match.group(1).strip()
                operator = match.group(2).strip()  # "is" or "is not"
                right_expr = match.group(3).strip()
                
                if self._should_flag_comparison(left_expr, right_expr):
                    # Calculate byte position for the operator
                    op_start = match.start(2)
                    op_end = match.end(2)
                    
                    byte_start, byte_end = self._calculate_byte_position(
                        all_lines, line_num, op_start, op_end
                    )
                    
                    # Determine replacement
                    replacement = "!=" if operator == "is not" else "=="
                    
                    # Create autofix edit
                    autofix = [Edit(
                        start_byte=byte_start,
                        end_byte=byte_end,
                        replacement=replacement
                    )]
                    
                    yield Finding(
                        rule=self.meta.id,
                        message="Use '==' / '!=' for value comparison; 'is' tests identity and is unreliable for strings/numbers.",
                        file=ctx.file_path,
                        start_byte=byte_start,
                        end_byte=byte_end,
                        severity="warning",
                        autofix=autofix,
                        meta={
                            "operator": operator,
                            "replacement": replacement,
                            "left_expr": left_expr,
                            "right_expr": right_expr,
                            "language": "python"
                        }
                    )
    
    def _should_flag_comparison(self, left_expr: str, right_expr: str) -> bool:
        """Determine if an 'is'/'is not' comparison should be flagged."""
        left_clean = self._clean_expression(left_expr)
        right_clean = self._clean_expression(right_expr)
        
        # Don't flag if either side is a known singleton
        if left_clean in self.SINGLETONS or right_clean in self.SINGLETONS:
            return False
        
        # Flag if either side looks like a value (string, number, etc.)
        if self._is_value_like(left_clean) or self._is_value_like(right_clean):
            return True
        
        return False
    
    def _clean_expression(self, expr: str) -> str:
        """Clean and normalize an expression for analysis."""
        # Remove leading 'if' and other control keywords
        cleaned = expr.strip()
        
        # Remove common control structure prefixes
        prefixes_to_remove = ['if ', 'elif ', 'while ', 'assert ', 'return ']
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        
        # Handle truncated parentheses from regex captures
        if cleaned.startswith('(') and not cleaned.endswith(')'):
            # Try to find if this looks like a truncated literal within parens
            inner_content = cleaned[1:]  # Remove opening paren
            if (inner_content and (
                inner_content[0].isdigit() or 
                inner_content.startswith('-') or
                inner_content.startswith('"') or 
                inner_content.startswith("'"))):
                return inner_content
        
        # Remove parentheses around the entire expression  
        while cleaned.startswith('(') and cleaned.endswith(')'):
            cleaned = cleaned[1:-1].strip()
            
        return cleaned
    
    def _is_value_like(self, expr: str) -> bool:
        """Check if an expression looks like a value (string, number, etc.)."""
        if not expr:
            return False
        
        # String literals (all forms)
        if ((expr.startswith('"') and expr.endswith('"')) or
            (expr.startswith("'") and expr.endswith("'")) or
            (expr.startswith('"""') and expr.endswith('"""')) or
            (expr.startswith("'''") and expr.endswith("'''"))):
            return True
        
        # Byte string literals
        if ((expr.startswith('b"') and expr.endswith('"')) or
            (expr.startswith("b'") and expr.endswith("'")) or
            (expr.startswith('B"') and expr.endswith('"')) or
            (expr.startswith("B'") and expr.endswith("'"))):
            return True
        
        # Raw string literals
        if ((expr.startswith('r"') and expr.endswith('"')) or
            (expr.startswith("r'") and expr.endswith("'")) or
            (expr.startswith('R"') and expr.endswith('"')) or
            (expr.startswith("R'") and expr.endswith("'"))):
            return True
        
        # f-string literals
        if ((expr.startswith('f"') and expr.endswith('"')) or
            (expr.startswith("f'") and expr.endswith("'")) or
            (expr.startswith('F"') and expr.endswith('"')) or
            (expr.startswith("F'") and expr.endswith("'"))):
            return True
        
        # Integer literals (including underscores)
        if re.match(r'^-?\d+(_\d+)*$', expr):
            return True
        
        # Float literals
        if re.match(r'^-?\d*\.\d+([eE][+-]?\d+)?$', expr) or re.match(r'^-?\d+[eE][+-]?\d+$', expr):
            return True
        
        # Complex number literals
        if re.match(r'^-?\d*\.?\d*[jJ]$', expr) or re.match(r'^-?\d+\.?\d*[jJ]$', expr):
            return True
        
        # Hexadecimal, binary, octal literals
        if re.match(r'^0[xX][0-9a-fA-F]+$', expr) or re.match(r'^0[bB][01]+$', expr) or re.match(r'^0[oO][0-7]+$', expr):
            return True
        
        return False
    
    def _is_comment_line(self, line: str) -> bool:
        """Check if a line is primarily a comment."""
        stripped = line.strip()
        return stripped.startswith('#') or not stripped
    
    def _calculate_byte_position(self, lines: List[str], line_num: int, char_start: int, char_end: int) -> tuple[int, int]:
        """Calculate byte positions from line number and character positions."""
        # Calculate the byte offset to the start of the line
        lines_before = lines[:line_num]
        byte_offset = sum(len(line.encode('utf-8')) + 1 for line in lines_before)  # +1 for newline
        
        # Add the character positions within the line (assume UTF-8 encoding)
        line_bytes = lines[line_num].encode('utf-8')
        char_to_byte_start = len(line_bytes[:char_start])
        char_to_byte_end = len(line_bytes[:char_end])
        
        return (byte_offset + char_to_byte_start, byte_offset + char_to_byte_end)


