"""
Bug Detection Rule: Boolean Bitwise Misuse

Flags `&` / `|` used in boolean control-flow conditions where `&&` / `||` are likely 
intended (non-short-circuit). Uses text-based analysis to detect patterns in 
if/while/for conditions when both sides are boolean-like.

This rule helps prevent logical errors by encouraging the use of short-circuit 
logical operators instead of bitwise operators in boolean contexts.
"""

import re
from typing import List, Set, Dict, Iterable, Optional, Any

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugBooleanBitwiseMisuseRule(Rule):
    """
    Rule to detect bitwise operators in boolean control-flow conditions.
    
    Flags `&` and `|` operators used in if/while/for conditions when both 
    operands appear to be boolean expressions, suggesting `&&`/`||` was intended.
    
    Examples of flagged patterns:
    - if ((a == 1) & (b > 0)) { ... }
    - while (isValid() | (count == 0)) { ... }
    - if (a == 1) & (b == 2): pass  # Python
    
    Examples of acceptable patterns:
    - if ((flags & MASK) != 0) { ... }  # Bitmask operation
    - if (a && b) { ... }  # Correct logical operator
    - if ((x & 1) == 0) { ... }  # Bitwise in comparison context
    """
    
    meta = RuleMeta(
        id="bug.boolean_bitwise_misuse",
        category="bug",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Flags bitwise operators (&/|) in boolean conditions where logical operators (&&/||) are likely intended",
        langs=["python", "javascript", "typescript", "java", "csharp", "cpp", "c"]
    )
    
    requires = Requires(syntax=True)
    
    # Control flow patterns for each language
    CONTROL_FLOW_PATTERNS = {
        "python": [
            r'(if|while|for)\s+([^:]+):',  # if condition:, while condition:, for ... in ...:
        ],
        "javascript": [
            r'(if|while|for)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
        "typescript": [
            r'(if|while|for)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
        "java": [
            r'(if|while|for)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
        "csharp": [
            r'(if|while|for|foreach)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
        "cpp": [
            r'(if|while|for)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
        "c": [
            r'(if|while|for)\s*\((.+?)\)\s*\{',  # if (condition) {, while (condition) {, for (condition) {
        ],
    }
    
    # Bitwise operator patterns to detect
    BITWISE_OPERATORS = {
        "&": r'([^&]+?)\s*&\s*([^&]+)',  # Single & not followed by another &
        "|": r'([^|]+?)\s*\|\s*([^|]+)',  # Single | not followed by another |
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit a file and check for bitwise operators in boolean conditions."""
        # Check language support
        language = getattr(ctx.adapter, 'language_id', '')
        if language not in self.meta.langs:
            return
        
        # Get control flow patterns for this language
        patterns = self.CONTROL_FLOW_PATTERNS.get(language, [])
        if not patterns:
            return
        
        # Analyze text line by line
        yield from self._analyze_text(ctx, ctx.text, language, patterns)
    
    def _analyze_text(self, ctx: RuleContext, text: str, language: str, patterns: List[str]) -> Iterable[Finding]:
        """Analyze text for control flow statements with bitwise operators."""
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            for pattern in patterns:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    control_type = match.group(1)
                    condition = match.group(2)
                    
                    # Look for bitwise operators in the condition
                    for op, op_pattern in self.BITWISE_OPERATORS.items():
                        for op_match in re.finditer(op_pattern, condition):
                            left_expr = op_match.group(1).strip()
                            right_expr = op_match.group(2).strip()
                            
                            # Check if both sides look boolean-like
                            if self._looks_boolean_like(left_expr, language) and self._looks_boolean_like(right_expr, language):
                                # Calculate byte position
                                line_start_byte = sum(len(lines[i]) + 1 for i in range(line_num))
                                condition_start = line_start_byte + match.start(2)
                                op_start = condition_start + op_match.start()
                                op_end = condition_start + op_match.end()
                                
                                # Adjust to highlight just the operator
                                op_text_start = condition_start + condition.find(op, op_match.start())
                                op_text_end = op_text_start + len(op)
                                
                                finding = self._create_finding(ctx, op, op_text_start, op_text_end, language)
                                if finding:
                                    yield finding
    
    def _looks_boolean_like(self, expr: str, language: str) -> bool:
        """Check if an expression looks like it produces a boolean value."""
        expr = expr.strip()
        
        # Skip empty expressions
        if not expr:
            return False
        
        # Boolean literals
        boolean_literals = {"true", "false", "True", "False"}
        if expr.lower() in [lit.lower() for lit in boolean_literals]:
            return True
        
        # Comparison operators
        comparison_ops = ["==", "!=", "<", ">", "<=", ">=", "===", "!==", " is ", " in ", " instanceof ", " typeof "]
        if any(op in expr for op in comparison_ops):
            return True
        
        # Already contains logical operators (nested boolean context)
        logical_ops = ["&&", "||", " and ", " or ", " not "]
        if any(op in expr for op in logical_ops):
            return True
        
        # Function calls that look like predicates
        predicate_patterns = [
            r'\bis_\w+\s*\(',  # is_valid(), is_empty()
            r'\bhas_\w+\s*\(',  # has_data(), has_permission()
            r'\bcan_\w+\s*\(',  # can_read(), can_write()
            r'\bshould_\w+\s*\(',  # should_continue(), should_retry()
            r'\bis[A-Z]\w*\s*\(',  # isValid(), isEmpty() (camelCase)
            r'\bhas[A-Z]\w*\s*\(',  # hasData(), hasPermission() (camelCase)
            r'\bcan[A-Z]\w*\s*\(',  # canRead(), canWrite() (camelCase)
            r'\bshould[A-Z]\w*\s*\(',  # shouldContinue(), shouldRetry() (camelCase)
            r'\bequals\s*\(',  # equals()
            r'\bstartswith\s*\(',  # startsWith()
            r'\bendswith\s*\(',  # endsWith()
            r'\bcontains\s*\(',  # contains()
            r'\bmatches\s*\(',  # matches()
            r'\bstartsWith\s*\(',  # startsWith() (camelCase)
            r'\bendsWith\s*\(',  # endsWith() (camelCase)
        ]
        
        for pattern in predicate_patterns:
            if re.search(pattern, expr, re.IGNORECASE):
                return True
        
        # Parenthesized expressions containing comparisons
        if expr.startswith('(') and expr.endswith(')'):
            inner = expr[1:-1].strip()
            return self._looks_boolean_like(inner, language)
        
        # Skip expressions that look like bitmask operations
        # Common patterns: MASK, 0xFF, flags, etc.
        bitmask_patterns = [
            r'^[A-Z_][A-Z0-9_]*$',  # CONSTANTS
            r'^0x[0-9a-fA-F]+$',    # Hex literals
            r'^\d+$',               # Numeric literals
            r'^[a-z_]\w*$',         # Simple identifiers (could be flags)
        ]
        
        for pattern in bitmask_patterns:
            if re.match(pattern, expr):
                # If both operands are bitmask-like, it's probably not boolean misuse
                return False
        
        return False
    
    def _create_finding(self, ctx: RuleContext, operator: str, start_byte: int, end_byte: int, language: str) -> Optional[Finding]:
        """Create a finding for bitwise misuse in boolean context."""
        # Generate language-specific suggestion
        suggestion = self._generate_suggestion(operator, language)
        
        message = f"Using bitwise '{operator}' in a boolean condition—did you mean '{'&&' if operator == '&' else '||'}' instead?"
        
        return Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning",
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "operator_detected": operator
            }
        )
    
    def _generate_suggestion(self, operator: str, language: str) -> str:
        """Generate a language-specific suggestion for fixing the issue."""
        if language == "python":
            if operator == "&":
                return "Replace '&' with 'and' for boolean logic"
            else:  # operator == "|"
                return "Replace '|' with 'or' for boolean logic"
        else:
            if operator == "&":
                return "Replace '&' with '&&' for short-circuit boolean logic"
            else:  # operator == "|"
                return "Replace '|' with '||' for short-circuit boolean logic"


# Create rule instance and register it
rule = BugBooleanBitwiseMisuseRule()
RULES = [rule]


