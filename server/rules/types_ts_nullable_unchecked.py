"""
Rule: types.ts_nullable_unchecked

Detects uses of nullable TypeScript values without proper null safety guards.
Under strictNullChecks, flags uses of values whose type includes null/undefined
without preceding safety checks like if-guards, optional chaining, or nullish coalescing.
"""

import re
from typing import List, Set, Dict, Iterable, Optional

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class TypesTsNullableUncheckedRule:
    """
    Rule to detect unchecked uses of nullable TypeScript values.
    
    Flags property access, method calls, element access, and arithmetic operations
    on values whose type includes null or undefined without proper safety guards.
    
    Examples of flagged patterns:
    - function f(x: string | null) { x.toUpperCase(); }  // property access
    - function g(h: (() => void) | undefined) { h(); }   // function call
    - function i(a: number[] | undefined) { a[0]; }      // element access
    
    Examples of allowed patterns:
    - if (x) { x.toUpperCase(); }          // if guard
    - x?.toUpperCase()                     // optional chaining
    - (x ?? "default").toUpperCase()       // nullish coalescing
    - x!.toUpperCase()                     // non-null assertion
    """
    
    meta = RuleMeta(
        id="types.ts_nullable_unchecked",
        category="types",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects uses of nullable TypeScript values without proper null safety guards",
        langs=["typescript"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.text:
            return
            
        # For now, use text-based analysis to detect patterns
        # This is a simplified implementation that focuses on common cases
        yield from self._analyze_nullable_usage(ctx)
    
    def _analyze_nullable_usage(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze TypeScript code for unsafe nullable value usage."""
        lines = ctx.text.split('\n')
        
        # First pass: collect nullable variable declarations
        nullable_vars = self._collect_nullable_variables(lines)
        if not nullable_vars:
            return
            
        # Second pass: look for unsafe usage of these variables
        byte_offset = 0
        for line_num, line in enumerate(lines):
            for var_name in nullable_vars:
                yield from self._check_line_for_unsafe_usage(
                    ctx, line, line_num, byte_offset, var_name, lines
                )
            byte_offset += len(line) + 1  # +1 for newline
    
    def _collect_nullable_variables(self, lines: List[str]) -> Set[str]:
        """Collect variable names that have nullable types."""
        nullable_vars = set()
        
        for line in lines:
            # Match function parameters and variable declarations with nullable types
            # This is a simplified approach that looks for | null or | undefined patterns
            
            # Look for any parameter or variable that has a union type with null/undefined
            # Pattern: identifier: SomeType | null/undefined
            union_pattern = r'(\w+)\s*:\s*[^|]*\|\s*(?:null|undefined)'
            matches = re.finditer(union_pattern, line)
            for match in matches:
                var_name = match.group(1)
                if var_name and var_name.isidentifier():
                    # Exclude keywords and common non-variable names
                    if var_name not in {'function', 'const', 'let', 'var', 'if', 'for', 'while', 'return'}:
                        nullable_vars.add(var_name)
        
        return nullable_vars
    
    def _check_line_for_unsafe_usage(self, ctx: RuleContext, line: str, line_num: int, 
                                   byte_offset: int, var_name: str, all_lines: List[str]) -> Iterable[Finding]:
        """Check a line for unsafe usage of a nullable variable."""
        # Skip content inside comments and strings (improved handling)
        cleaned_line = self._remove_comments_and_strings(line)
        
        # Look for usage patterns
        patterns = [
            (rf'\b{re.escape(var_name)}\.(\w+)', 'property access'),
            (rf'\b{re.escape(var_name)}\[', 'element access'),
            (rf'\b{re.escape(var_name)}\s*\(', 'function call'),
            (rf'\b{re.escape(var_name)}\s*[+\-*/]', 'arithmetic operation'),
        ]
        
        for pattern, usage_type in patterns:
            matches = re.finditer(pattern, cleaned_line)
            for match in matches:
                # Check if this usage is guarded
                if self._is_usage_guarded(cleaned_line, match.start(), var_name, line_num, all_lines):
                    continue
                    
                # Calculate byte position (use original line for accurate positioning)
                original_matches = list(re.finditer(pattern, line))
                if len(original_matches) > 0:
                    # Find the corresponding match in the original line
                    original_match = original_matches[0]  # Simplified - take first match
                    usage_start = byte_offset + original_match.start()
                    usage_end = byte_offset + original_match.end()
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Possible null/undefined access on '{var_name}'. Add a null check, optional chaining, or nullish coalescing.",
                        file=ctx.file_path,
                        start_byte=usage_start,
                        end_byte=usage_end,
                        severity="warning"
                    )
    
    def _remove_comments_and_strings(self, line: str) -> str:
        """Remove comments and string literals from a line."""
        # Remove single-line comments
        if '//' in line:
            line = line[:line.index('//')]
        
        # Remove string literals (simplified - handles basic cases)
        # This is a basic implementation; full string parsing would be more complex
        line = re.sub(r'"[^"]*"', '""', line)
        line = re.sub(r"'[^']*'", "''", line)
        line = re.sub(r'`[^`]*`', '``', line)
        
        return line
    
    def _is_usage_guarded(self, line: str, usage_pos: int, var_name: str, 
                         line_num: int, all_lines: List[str]) -> bool:
        """Check if a usage is properly guarded against null/undefined."""
        # Check for common guard patterns in the same line
        
        # Optional chaining: x?.prop, x?.(), x?.[0]
        if '?.' in line[:usage_pos + 10]:  # Check around usage position
            return True
            
        # Non-null assertion: x!.prop
        if '!' in line[:usage_pos]:
            return True
            
        # Nullish coalescing: x ?? default
        if '??' in line:
            return True
            
        # Logical AND: x && x.prop
        and_pattern = rf'\b{re.escape(var_name)}\s*&&'
        if re.search(and_pattern, line[:usage_pos]):
            return True
            
        # Ternary operator guard: x ? x.prop : ...
        ternary_pattern = rf'\b{re.escape(var_name)}\s*\?'
        if re.search(ternary_pattern, line[:usage_pos]):
            return True
            
        # Check for if-statement guards in previous lines or current line
        return self._check_if_guards(var_name, line_num, all_lines)
    
    def _check_if_guards(self, var_name: str, current_line: int, all_lines: List[str]) -> bool:
        """Check if the current usage is protected by an if-guard in a previous line or same line."""
        # Check current line first for inline if statements
        current_line_text = all_lines[current_line] if current_line < len(all_lines) else ""
        
        # Look for if statements in the current line or previous lines
        lines_to_check = []
        
        # Add current line 
        lines_to_check.append(current_line_text)
        
        # Add previous lines (going back up to 10 lines to find controlling if)
        for i in range(max(0, current_line - 10), current_line):
            lines_to_check.append(all_lines[i])
        
        # Join lines and look for if-guard patterns that would protect this usage
        combined_text = " ".join(lines_to_check)
        
        if_patterns = [
            rf'if\s*\(\s*{re.escape(var_name)}\s*\)',
            rf'if\s*\(\s*{re.escape(var_name)}\s*!==?\s*null\s*\)',
            rf'if\s*\(\s*{re.escape(var_name)}\s*!==?\s*undefined\s*\)',
            rf'if\s*\(\s*typeof\s+{re.escape(var_name)}\s*!==?\s*["\']undefined["\']\s*\)',
            rf'if\s*\(\s*!\s*{re.escape(var_name)}\s*\)\s*return',  # Early return pattern
        ]
        
        for pattern in if_patterns:
            if re.search(pattern, combined_text):
                # Make sure the usage comes after the if condition
                # This is a simplified check - in a real implementation we'd parse the AST
                return True
                
        return False


# Create rule instance and register it
_rule = TypesTsNullableUncheckedRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    register_rule(_rule)
except ImportError:
    # Fallback for direct imports
    from engine.registry import register_rule
    register_rule(_rule)


