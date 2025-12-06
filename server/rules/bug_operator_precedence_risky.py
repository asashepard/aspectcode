"""
Operator Precedence Risk Detection Rule

This rule detects potentially confusing expressions whose meaning depends on subtle 
operator precedence rules. It flags cases where adding explicit parentheses would 
make the code's intent clearer.

Common risky patterns:
- Mixed logical operators without parentheses: `a && b || c`
- Nullish coalescing mixed with logical: `a ?? b || c` 
- Bitwise operators with comparisons: `x & MASK == 0`
- Shifts with arithmetic: `x << a + b`
- Chained comparisons in non-chaining languages: `a < b < c`
- Python `not` with membership: `not x in list`
- Ruby mixing `and/or` with `&&/||`

Examples:
- RISKY: `if (condition && flag || other) { ... }`
- CLEAR: `if ((condition && flag) || other) { ... }`

- RISKY: `value = a ?? b || c`
- CLEAR: `value = (a ?? b) || c`

- RISKY: `if (x & MASK == 0) { ... }`
- CLEAR: `if ((x & MASK) == 0) { ... }`
"""

import re
from typing import Iterable, Set, Optional, List, Dict

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugOperatorPrecedenceRiskyRule:
    """
    Detects potentially confusing operator precedence scenarios.
    
    This rule identifies expressions where the meaning depends on operator precedence
    in ways that might not be immediately obvious to readers. It suggests adding
    explicit parentheses to clarify intent.
    
    Covers multiple common pitfalls:
    - Logical operator mixing (&&/|| combinations)
    - Nullish coalescing with logical operators (?? with ||/&&)
    - Bitwise operations with comparisons
    - Shift operators with arithmetic
    - Chained comparisons in non-chaining languages
    - Python 'not' with membership operators
    - Ruby 'and/or' mixed with &&/||
    """
    
    meta = RuleMeta(
        id="bug.operator_precedence_risky",
        category="bug",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Flags expressions with potentially confusing operator precedence; suggests adding parentheses for clarity",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Patterns for different risky precedence scenarios
    RISKY_PATTERNS = {
        # Mixed logical operators (&&/|| without clear grouping)
        "logical_mix": {
            "pattern": r'(\w+|\w+\([^)]*\))\s*&&\s*(\w+|\w+\([^)]*\))\s*\|\|\s*(\w+|\w+\([^)]*\))',
            "languages": ["javascript", "typescript", "java", "csharp", "cpp", "c", "go", "swift", "rust"],
            "message": "Mixed && and || operators without parentheses; precedence may be unclear"
        },
        
        # Nullish coalescing with logical operators (JS/TS specific)
        "nullish_mix": {
            "pattern": r'(\w+|\w+\([^)]*\))\s*\?\?\s*(\w+|\w+\([^)]*\))\s*(\|\||&&)\s*(\w+|\w+\([^)]*\))',
            "languages": ["javascript", "typescript"],
            "message": "Nullish coalescing (??) mixed with logical operators without parentheses"
        },
        
        # Bitwise with comparison operators
        "bitwise_compare": {
            "pattern": r'(\w+|\w+\([^)]*\))\s*([&|^])\s*(\w+|\w+\([^)]*\))\s*(==|!=|===|!==|<=|>=|<|>)\s*(\w+|\w+\([^)]*\))',
            "languages": ["javascript", "typescript", "java", "csharp", "cpp", "c", "go", "swift", "rust"],
            "message": "Bitwise operation combined with comparison without parentheses"
        },
        
        # Shift operators with arithmetic
        "shift_arithmetic": {
            "pattern": r'(\w+|\w+\([^)]*\))\s*(<<|>>)\s*(\w+|\w+\([^)]*\))\s*([+\-])\s*(\w+|\w+\([^)]*\))',
            "languages": ["javascript", "typescript", "java", "csharp", "cpp", "c", "go", "swift", "rust"],
            "message": "Shift operation mixed with arithmetic without parentheses"
        },
        
        # Chained comparisons in non-chaining languages
        "chained_compare": {
            "pattern": r'(\w+|\w+\([^)]*\))\s*(<=|>=|<|>|==|!=|===|!==)\s*(\w+|\w+\([^)]*\))\s*(<=|>=|<|>|==|!=|===|!==)\s*(\w+|\w+\([^)]*\))',
            "languages": ["javascript", "typescript", "java", "csharp", "cpp", "c", "go", "swift"],
            "message": "Chained comparison operators; consider using && for clarity"
        },
        
        # Python not with membership
        "python_not_membership": {
            "pattern": r'\bnot\s+(\w+|\w+\([^)]*\))\s+(in|is)\s+(\w+|\w+\([^)]*\))',
            "languages": ["python"],
            "message": "Use 'not in' or 'is not' instead of 'not ... in/is' for clarity"
        },
        
        # Ruby and/or mixed with &&/||
        "ruby_mixed_logical": {
            "pattern": r'(\w+|\w+\([^)]*\))\s+(and|or)\s+(\w+|\w+\([^)]*\))\s*(\|\||&&)\s*(\w+|\w+\([^)]*\))',
            "languages": ["ruby"],
            "message": "Mixed 'and/or' with '&&/||' operators; these have different precedence"
        }
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze text for risky operator precedence patterns."""
        if ctx.language not in self.meta.langs:
            return
        
        # Analyze text using pattern matching
        yield from self._analyze_text(ctx, ctx.text, ctx.language)
    
    def _analyze_text(self, ctx: RuleContext, text: str, language: str) -> Iterable[Finding]:
        """Analyze text for operator precedence issues using regex patterns."""
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            # Skip comments and strings to avoid false positives
            if self._is_comment_or_string_line(line, language):
                continue
                
            for pattern_name, pattern_info in self.RISKY_PATTERNS.items():
                if language not in pattern_info["languages"]:
                    continue
                
                pattern = pattern_info["pattern"]
                message = pattern_info["message"]
                
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    # Skip if expression is already parenthesized
                    if self._is_safely_parenthesized(line, match):
                        continue
                    
                    # Calculate byte position
                    line_start_byte = sum(len(lines[i]) + 1 for i in range(line_num))
                    match_start = line_start_byte + match.start()
                    match_end = line_start_byte + match.end()
                    
                    finding = Finding(
                        rule=self.meta.id,
                        message=message,
                        file=ctx.file_path,
                        start_byte=match_start,
                        end_byte=match_end,
                        severity="info",
                        autofix=None,  # suggest-only
                        meta={
                            "suggestion": "Add explicit parentheses to clarify operator grouping",
                            "pattern_type": pattern_name,
                            "language": language
                        }
                    )
                    yield finding
    
    def _is_comment_or_string_line(self, line: str, language: str) -> bool:
        """Check if line is primarily a comment or string literal."""
        stripped = line.strip()
        
        # Language-specific comment patterns
        comment_patterns = {
            "python": [r'^\s*#', r'^\s*"""', r"^\s*'''"],
            "javascript": [r'^\s*//', r'^\s*/\*'],
            "typescript": [r'^\s*//', r'^\s*/\*'],
            "java": [r'^\s*//', r'^\s*/\*'],
            "csharp": [r'^\s*//', r'^\s*/\*'],
            "cpp": [r'^\s*//', r'^\s*/\*'],
            "c": [r'^\s*//', r'^\s*/\*'],
            "go": [r'^\s*//'],
            "rust": [r'^\s*//', r'^\s*/\*'],
            "swift": [r'^\s*//'],
            "ruby": [r'^\s*#']
        }
        
        patterns = comment_patterns.get(language, [])
        for pattern in patterns:
            if re.match(pattern, stripped):
                return True
        
        return False
    
    def _is_safely_parenthesized(self, line: str, match) -> bool:
        """Check if the matched expression is already safely parenthesized."""
        matched_text = match.group()
        
        # Check if the risky expression has meaningful internal grouping
        # that resolves the precedence ambiguity
        return self._has_meaningful_grouping(matched_text)
    
    def _has_meaningful_grouping(self, text: str) -> bool:
        """Check if the text has meaningful parentheses grouping that resolves precedence issues."""
        import re
        
        # For logical mix: look for (a && b) || c or a && (b || c)
        logical_safe_patterns = [
            r'\([^)]*&&[^)]*\)\s*\|\|',  # (expr && expr) ||
            r'\([^)]*\|\|[^)]*\)\s*&&',  # (expr || expr) &&
            r'&&\s*\([^)]*\|\|[^)]*\)',  # && (expr || expr)
            r'\|\|\s*\([^)]*&&[^)]*\)'   # || (expr && expr)
        ]
        
        # For nullish coalescing: look for (a ?? b) || c or a ?? (b || c)
        nullish_safe_patterns = [
            r'\([^)]*\?\?[^)]*\)\s*(\|\||&&)',  # (expr ?? expr) ||/&&
            r'(\|\||&&)\s*\([^)]*\?\?[^)]*\)',  # ||/&& (expr ?? expr)
            r'\?\?\s*\([^)]*(\|\||&&)[^)]*\)',  # ?? (expr ||/&& expr)
        ]
        
        # For bitwise: look for (a & b) == c or a & (b == c)
        bitwise_safe_patterns = [
            r'\([^)]*[&|^][^)]*\)\s*(==|!=|===|!==|<=|>=|<|>)',  # (expr & expr) ==
            r'[&|^]\s*\([^)]*(==|!=|===|!==|<=|>=|<|>)[^)]*\)'   # & (expr == expr)
        ]
        
        # For shifts: look for (a << b) + c or a << (b + c)
        shift_safe_patterns = [
            r'\([^)]*(<<|>>)[^)]*\)\s*[+\-]',  # (expr << expr) +
            r'(<<|>>)\s*\([^)]*[+\-][^)]*\)'   # << (expr + expr)
        ]
        
        # Combine all patterns
        all_patterns = logical_safe_patterns + nullish_safe_patterns + bitwise_safe_patterns + shift_safe_patterns
        
        for pattern in all_patterns:
            if re.search(pattern, text):
                return True
        
        return False


# Register the rule
_rule = BugOperatorPrecedenceRiskyRule()
RULES = [_rule]


