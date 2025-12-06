"""
Bug Detection Rule: Float Equality

Detects direct equality checks (`==`, `===`) on floating-point values and recommends
epsilon/approximate comparison instead. Supports 9 languages with language-specific
float detection heuristics.

This rule helps prevent floating-point precision issues by encouraging the use of
tolerance-based comparisons.
"""

import re
from typing import List, Set, Dict, Iterable, Optional

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugFloatEqualityRule:
    """
    Rule to detect direct equality checks on floating-point values.
    
    Flags `==` and `===` operations on expressions that appear to involve
    floating-point values, recommending epsilon-based comparisons instead.
    
    Examples of flagged patterns:
    - if (x == 1.0) { ... }
    - if (parseFloat(s) === 0.1) { ... }
    - if y == 0.1f: ...
    
    Examples of recommended alternatives:
    - if (Math.abs(x - 1.0) < 1e-9) { ... }
    - if math.isclose(x, 1.0): ...
    - if (Mathf.Approximately(x, 1.0f)) { ... }
    """
    
    meta = RuleMeta(
        id="bug.float_equality",
        category="bug",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects direct equality checks on floating-point values; recommends epsilon/approximate comparison",
        langs=["python", "java", "csharp", "cpp", "c", "javascript", "typescript", "go", "rust"]
    )
    
    requires = Requires(syntax=True)
    
    # Patterns to detect equality expressions in different languages
    # Use greedy matching for RHS to capture the immediate operand (up to space, comment, or terminator)
    EQUALITY_PATTERNS = {
        "python": [r'(\S+)\s*(==)\s*(\d+\.\d+|\d+\.|\.\d+|\d+[eE][+-]?\d+|float\([^)]*\))'],
        "java": [r'(\S+)\s*(==)\s*(\d+\.\d+[fFdD]?|\d+\.[fFdD]?|\.\d+[fFdD]?|\d+[fFdD]|\d+[eE][+-]?\d+[fFdD]?)'],
        "csharp": [r'(\S+)\s*(==)\s*(\d+\.\d+[fFdDmM]?|\d+\.[fFdDmM]?|\.\d+[fFdDmM]?|\d+[fFdDmM]|\d+[eE][+-]?\d+[fFdDmM]?)'],
        "cpp": [r'(\S+)\s*(==)\s*(\d+\.\d+[fFlL]?|\d+\.[fFlL]?|\.\d+[fFlL]?|\d+[fFlL]|\d+[eE][+-]?\d+[fFlL]?)'],
        "c": [r'(\S+)\s*(==)\s*(\d+\.\d+[fFlL]?|\d+\.[fFlL]?|\.\d+[fFlL]?|\d+[fFlL]|\d+[eE][+-]?\d+[fFlL]?)'],
        "javascript": [r'(\S+)\s*(===?)\s*(\d+\.\d+|\d+\.|\.\d+|\d+[eE][+-]?\d+|parseFloat\([^)]*\)|Number\([^)]*\))'],
        "typescript": [r'(\S+)\s*(===?)\s*(\d+\.\d+|\d+\.|\.\d+|\d+[eE][+-]?\d+|parseFloat\([^)]*\)|Number\([^)]*\))'],
        "go": [r'(\S+)\s*(==)\s*(\d+\.\d+|\d+\.|\.\d+|\d+[eE][+-]?\d+)'],
        "rust": [r'(\S+)\s*(==)\s*(\d+\.\d+(?:_f32|_f64|f32|f64)?|\d+\.(?:_f32|_f64|f32|f64)?|\.\d+(?:_f32|_f64|f32|f64)?|\d+(?:_f32|_f64|f32|f64))']
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.raw_text:
            return
            
        language = ctx.language
        if language not in self.meta.langs:
            return
            
        # Use text-based analysis to find equality expressions
        yield from self._analyze_equality_expressions(ctx, ctx.raw_text, language)
    
    def _analyze_equality_expressions(self, ctx: RuleContext, text: str, language: str) -> Iterable[Finding]:
        """Analyze equality expressions for floating-point comparisons."""
        patterns = self.EQUALITY_PATTERNS.get(language, [])
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            for pattern in patterns:
                for match in re.finditer(pattern, line):
                    lhs = match.group(1).strip()
                    operator = match.group(2).strip()
                    rhs = match.group(3).strip()
                    
                    # Check if either side looks like a floating-point value
                    if self._looks_floaty(lhs, language) or self._looks_floaty(rhs, language):
                        # Calculate byte position of the operator
                        line_start_byte = sum(len(lines[i]) + 1 for i in range(line_num))
                        operator_pos = line_start_byte + match.start(2)
                        operator_end = line_start_byte + match.end(2)
                        
                        message = self._generate_message(operator, language)
                        suggestion = self._generate_suggestion(lhs, rhs, language)
                        
                        yield Finding(
                            rule=self.meta.id,
                            message=message,
                            file=ctx.file_path,
                            start_byte=operator_pos,
                            end_byte=operator_end,
                            severity="info",
                            meta={
                                "suggestion": suggestion,
                                "autofix_safety": "suggest-only"
                            }
                        )
    
    def _looks_floaty(self, expr: str, language: str) -> bool:
        """
        Syntax-only heuristics to guess floating-point values.
        
        Detects:
        - Decimal/scientific literals (1.0, .5, 1e-9, 2.0f, 3D, etc.)
        - Float-producing function calls (parseFloat, atof, float(), etc.)
        - Explicit casts and type suffixes
        """
        expr = expr.strip()
        
        # Skip obviously non-float expressions
        if not expr or expr in ['true', 'false', 'null', 'None', 'nil']:
            return False
        
        # Skip quoted strings (both single and double quotes)
        if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
            return False
        
        # Skip backtick strings (template literals in JS/TS)
        if expr.startswith('`') and expr.endswith('`'):
            return False
        
        # Check for decimal points or scientific notation
        if ('.' in expr or 'e' in expr.lower()) and any(c.isdigit() for c in expr):
            return True
        
        # Language-specific float suffixes
        float_suffixes = {
            "c": ['f', 'F', 'l', 'L'],
            "cpp": ['f', 'F', 'l', 'L'],
            "java": ['f', 'F', 'd', 'D'],
            "csharp": ['f', 'F', 'd', 'D', 'm', 'M'],  # m/M for decimal
            "rust": ['f32', 'f64'],
            "go": [],  # Go doesn't use suffixes
            "python": [],
            "javascript": [],
            "typescript": []
        }
        
        suffixes = float_suffixes.get(language, [])
        for suffix in suffixes:
            if expr.endswith(suffix):
                # Make sure it's not part of an identifier
                if len(expr) > len(suffix) and expr[-len(suffix)-1].isdigit():
                    return True
        
        # Check for Rust f32/f64 suffixes with underscore
        if language == "rust":
            if expr.endswith('_f32') or expr.endswith('_f64'):
                return True
        
        # Float-producing function calls and casts
        float_indicators = {
            "python": ['float(', 'math.', 'numpy.', 'np.'],
            "java": ['Float.', 'Double.', '(float)', '(double)', 'parseDouble(', 'parseFloat('],
            "csharp": ['float.', 'double.', '(float)', '(double)', 'Convert.ToSingle(', 'Convert.ToDouble(', ' as float', ' as double'],
            "cpp": ['(float)', '(double)', 'static_cast<float>', 'static_cast<double>', 'float(', 'double(', 'atof(', 'strtod('],
            "c": ['(float)', '(double)', 'atof(', 'strtod(', 'strtof('],
            "javascript": ['parseFloat(', 'Number(', 'Math.'],
            "typescript": ['parseFloat(', 'Number(', 'Math.', ' as number'],
            "go": ['float32(', 'float64(', 'strconv.ParseFloat(', 'math.'],
            "rust": ['f32::', 'f64::', '.parse::<f32>', '.parse::<f64>', ' as f32', ' as f64']
        }
        
        indicators = float_indicators.get(language, [])
        for indicator in indicators:
            if indicator in expr:
                return True
        
        return False
    
    def _generate_message(self, operator: str, language: str) -> str:
        """Generate appropriate error message for the float equality check."""
        if operator == "===":
            return "Comparing floating-point numbers with '===' is unreliable—use an epsilon comparison instead."
        else:
            return "Comparing floating-point numbers with '==' is unreliable—use an epsilon comparison instead."
    
    def _generate_suggestion(self, lhs: str, rhs: str, language: str) -> str:
        """Generate language-specific suggestion for fixing the float equality issue."""
        suggestions = {
            "python": f"Use math.isclose({lhs}, {rhs}) or abs({lhs} - {rhs}) < 1e-9",
            "java": f"Use Math.abs({lhs} - {rhs}) < 1e-9 or Objects.equals() for boxed types",
            "csharp": f"Use Math.Abs({lhs} - {rhs}) < 1e-9 or Mathf.Approximately() in Unity",
            "cpp": f"Use std::abs({lhs} - {rhs}) < std::numeric_limits<double>::epsilon() or custom epsilon",
            "c": f"Use fabs({lhs} - {rhs}) < DBL_EPSILON or custom epsilon (include <float.h>)",
            "javascript": f"Use Math.abs({lhs} - {rhs}) < Number.EPSILON or custom tolerance",
            "typescript": f"Use Math.abs({lhs} - {rhs}) < Number.EPSILON or custom tolerance",
            "go": f"Use math.Abs({lhs} - {rhs}) < 1e-9 or custom epsilon",
            "rust": f"Use ({lhs} - {rhs}).abs() < f64::EPSILON or custom tolerance"
        }
        
        return suggestions.get(language, f"Use epsilon-based comparison instead of direct equality")


# Register the rule
_rule = BugFloatEqualityRule()
RULES = [_rule]


