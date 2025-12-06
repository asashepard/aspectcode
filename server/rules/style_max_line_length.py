"""
Rule: style.max_line_length

Flags lines exceeding a configurable maximum line length and provides
suggested wraps/refactors without making direct edits.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    try:
        from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
    except ImportError:
        # For test execution
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit

from typing import List, Dict, Any, Optional

DEFAULT_MAX = 120


class StyleMaxLineLengthRule:
    """Flag lines exceeding maximum length and suggest wrapping strategies."""
    
    meta = RuleMeta(
        id="style.max_line_length",
        category="style",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description=f"Lines should not exceed {DEFAULT_MAX} characters (suggest wrap/refactor)",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=False,
        project_graph=False
    )
    
    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Check for lines exceeding maximum length."""
        findings = []
        
        # Check if this is a supported language
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return findings
        
        # Get configuration for max length (default to DEFAULT_MAX)
        max_length = ctx.config.get('style.max_line_length.limit', DEFAULT_MAX)
        
        # Analyze each line for length violations
        violations = self._find_long_lines(ctx.text, max_length)
        
        for violation in violations:
            finding = Finding(
                rule=self.meta.id,
                message=f"Line {violation['line_no']} exceeds max length ({violation['length']}>{max_length}). Consider wrapping or refactoring.",
                severity="info",
                file=ctx.file_path,
                start_byte=violation['start_byte'],
                end_byte=violation['end_byte'],
                autofix=None,  # suggest-only, no direct edits
                meta={
                    "line_number": violation['line_no'],
                    "actual_length": violation['length'],
                    "max_length": max_length,
                    "suggestion": violation['suggestion']
                }
            )
            findings.append(finding)
        
        return findings
    
    def _find_long_lines(self, text: str, max_length: int) -> List[Dict[str, Any]]:
        """
        Find all lines exceeding the maximum length.
        
        Returns list of violation dictionaries with line info and suggestions.
        """
        violations = []
        lines = text.splitlines(keepends=True)
        byte_offset = 0
        
        for line_no, line in enumerate(lines, 1):
            # Calculate line length excluding line terminators
            line_content = line.rstrip('\r\n')
            line_length = len(line_content)
            
            if line_length > max_length:
                suggestion = self._suggest_wrap(line_content, max_length)
                
                violations.append({
                    'line_no': line_no,
                    'length': line_length,
                    'start_byte': byte_offset,
                    'end_byte': byte_offset + len(line_content),
                    'content': line_content,
                    'suggestion': suggestion
                })
            
            byte_offset += len(line)
        
        return violations
    
    def _suggest_wrap(self, line: str, limit: int) -> Dict[str, str]:
        """
        Generate a heuristic suggestion for wrapping a long line.
        
        Returns a dictionary with 'diff' and 'rationale' for the suggestion.
        """
        if len(line) <= limit:
            return {"diff": "", "rationale": "Within limit; no change needed."}
        
        # Try to find a good break point using common delimiters
        break_point = self._find_break_point(line, limit)
        
        if break_point <= 0:
            # Fallback to hard wrap at limit
            break_point = limit
            strategy = "hard wrap at character limit"
        else:
            strategy = "wrap at natural delimiter"
        
        # Create the wrapped version
        before_part = line[:break_point].rstrip()
        after_part = line[break_point:].lstrip()
        
        # Choose wrapping strategy based on language context
        if self._looks_like_string_literal(line):
            wrapped = self._suggest_string_wrap(before_part, after_part)
            rationale = f"Break long string literal using concatenation ({strategy})"
        elif self._looks_like_import_statement(line):
            wrapped = self._suggest_import_wrap(before_part, after_part)
            rationale = f"Break import statement across lines ({strategy})"
        elif self._looks_like_method_chain(line):
            wrapped = self._suggest_method_chain_wrap(before_part, after_part)
            rationale = f"Break method chain with proper indentation ({strategy})"
        else:
            # Generic line continuation
            wrapped = f"{before_part} \\\n    {after_part}"
            rationale = f"Wrap long line with continuation and indent ({strategy})"
        
        # Create unified diff
        diff = self._create_diff(line, wrapped)
        
        return {"diff": diff, "rationale": rationale}
    
    def _find_break_point(self, line: str, limit: int) -> int:
        """Find the best break point within the limit using common delimiters."""
        # Try delimiters in order of preference
        delimiters = [',', ' ', ')', ']', '}', ';', '+', '-', '*', '/', '&', '|']
        
        best_break = -1
        for delimiter in delimiters:
            pos = line.rfind(delimiter, 0, limit + 1)
            if pos > best_break:
                best_break = pos + 1  # Break after the delimiter
        
        return best_break
    
    def _looks_like_string_literal(self, line: str) -> bool:
        """Check if line appears to contain a long string literal."""
        stripped = line.strip()
        return (
            (stripped.count('"') >= 2 and '"' in stripped) or
            (stripped.count("'") >= 2 and "'" in stripped) or
            '"""' in stripped or
            "'''" in stripped
        )
    
    def _looks_like_import_statement(self, line: str) -> bool:
        """Check if line appears to be an import statement."""
        stripped = line.strip()
        return (
            stripped.startswith('import ') or
            stripped.startswith('from ') or
            'import' in stripped
        )
    
    def _looks_like_method_chain(self, line: str) -> bool:
        """Check if line appears to be a method chain."""
        return line.count('.') >= 2 and '(' in line
    
    def _suggest_string_wrap(self, before: str, after: str) -> str:
        """Suggest string literal wrapping."""
        # Simple string concatenation suggestion
        if before.rstrip().endswith('"'):
            return f'{before.rstrip()[:-1]}" +\n    "{after}'
        elif before.rstrip().endswith("'"):
            return f"{before.rstrip()[:-1]}' +\n    '{after}"
        else:
            return f"{before} \\\n    {after}"
    
    def _suggest_import_wrap(self, before: str, after: str) -> str:
        """Suggest import statement wrapping."""
        # If it's a from...import, suggest parentheses
        if 'from' in before and 'import' in before:
            if '(' not in before:
                import_pos = before.find('import')
                if import_pos > 0:
                    return f"{before[:import_pos]}import (\n    {before[import_pos+6:].strip()},{after}\n)"
        
        # Fallback to line continuation
        return f"{before} \\\n    {after}"
    
    def _suggest_method_chain_wrap(self, before: str, after: str) -> str:
        """Suggest method chain wrapping."""
        # Find the last dot before the break point
        last_dot = before.rfind('.')
        if last_dot > 0 and last_dot < len(before) - 1:
            # Break before the method call
            return f"{before[:last_dot]}\n    .{before[last_dot+1:]}{after}"
        else:
            return f"{before} \\\n    {after}"
    
    def _create_diff(self, original: str, wrapped: str) -> str:
        """Create a unified diff showing the suggested change."""
        return f"""--- a/current_line
+++ b/current_line
-{original}
+{wrapped}"""


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
except ImportError:
    try:
        from engine.registry import register_rule
    except ImportError:
        # For test execution - registry may not be available
        def register_rule(rule):
            pass

register_rule(StyleMaxLineLengthRule())


