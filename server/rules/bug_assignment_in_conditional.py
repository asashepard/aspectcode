"""
Bug Detection Rule: Assignment in Conditional

Detects assignment (`=`) used directly in `if`/`while`/`for` conditions where
comparison (`==`) was likely intended. Provides safe autofix to replace `=` with `==`.

Supports C, C++, Java, C#, JavaScript, and TypeScript.
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


class BugAssignmentInConditionalRule:
    """
    Rule to detect assignment operators in conditional statements.
    
    Flags single `=` used in if/while/for conditions where `==` was likely intended.
    Excludes legitimate patterns like assignment-in-comparison idioms.
    
    Examples of flagged patterns:
    - if (x = y) { ... }
    - while (a = next()) { ... }
    
    Examples of allowed patterns:
    - if (x == y) { ... }
    - while ((ch = getchar()) != EOF) { ... }
    - for (; (n = iter()) !== null; ) { ... }
    """
    
    meta = RuleMeta(
        id="bug.assignment_in_conditional",
        category="bug",
        tier=0,
        priority="P0",
        autofix_safety="safe",
        description="Detects assignment (`=`) used in conditional statements where comparison (`==`) was likely intended",
        langs=["c", "cpp", "java", "csharp", "javascript", "typescript"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.text:
            return
            
        # For now, use text-based analysis since this rule supports multiple languages
        # and we need a simple pattern-based approach
        yield from self._analyze_conditionals(ctx)
    
    def _analyze_conditionals(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze conditional statements for assignment operators."""
        text = ctx.text
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            # Find if/while/for statements
            for keyword in ['if', 'while', 'for']:
                if f'{keyword} ' in line or f'{keyword}(' in line:
                    # Find the condition part more carefully
                    condition_start = line.find(keyword)
                    if condition_start == -1:
                        continue
                    
                    # Find opening parenthesis
                    paren_start = line.find('(', condition_start)
                    if paren_start == -1:
                        continue
                    
                    # Find matching closing parenthesis (handle nested parens)
                    paren_count = 0
                    condition_end = -1
                    for i in range(paren_start, len(line)):
                        if line[i] == '(':
                            paren_count += 1
                        elif line[i] == ')':
                            paren_count -= 1
                            if paren_count == 0:
                                condition_end = i
                                break
                    
                    if condition_end == -1:
                        continue
                    
                    # Extract the condition (inside parentheses)
                    condition = line[paren_start+1:condition_end].strip()
                    
                    # For for-loops, extract only the middle part (condition)
                    if keyword == 'for':
                        parts = condition.split(';')
                        if len(parts) >= 2:
                            condition = parts[1].strip()  # Middle part is the condition
                        else:
                            continue  # Invalid for loop syntax
                    
                    # Check if this condition contains a problematic assignment
                    assignment_pos = self._find_lone_assignment_equals(condition)
                    if assignment_pos is not None:
                        # Calculate absolute byte position
                        line_start_byte = sum(len(lines[i]) + 1 for i in range(line_num))
                        condition_start_byte = line_start_byte + paren_start + 1
                        
                        if keyword == 'for':
                            # Adjust for for-loop condition offset
                            first_semicolon = line[paren_start:condition_end].find(';')
                            if first_semicolon != -1:
                                condition_start_byte += first_semicolon + 1
                        
                        abs_pos = condition_start_byte + assignment_pos
                        
                        # Create autofix edit
                        autofix_edits = [Edit(
                            start_byte=abs_pos,
                            end_byte=abs_pos + 1,  # Single '=' character
                            replacement="=="
                        )]
                        
                        yield Finding(
                            rule=self.meta.id,
                            message="Assignment used in conditional; did you mean '=='?",
                            file=ctx.file_path,
                            start_byte=abs_pos,
                            end_byte=abs_pos + 1,  # Single '=' character
                            severity="error",
                            autofix=autofix_edits,
                            meta={
                                "autofix_safety": "safe",
                                "suggestion": "Replace '=' with '==' for comparison"
                            }
                        )
    
    def _find_lone_assignment_equals(self, condition: str) -> Optional[int]:
        """
        Find the position of a lone assignment '=' in the condition.
        
        Excludes:
        - '==', '===', '!=', '<=', '>='
        - '=>' (arrow functions)
        - assignments that are part of comparison idioms
        
        Returns the character position of '=' or None if not found.
        """
        condition = condition.strip()
        
        # Find all '=' characters that are not part of compound operators
        lone_equals_positions = []
        i = 0
        while i < len(condition):
            if condition[i] == '=':
                # Check if it's part of a compound operator
                prev_char = condition[i-1] if i > 0 else ''
                next_char = condition[i+1] if i+1 < len(condition) else ''
                
                # Skip compound operators
                if prev_char in ['<', '>', '!', '='] or next_char in ['=', '>']:
                    i += 1
                    continue
                
                # Found a lone '=' - record its position
                lone_equals_positions.append(i)
            
            i += 1
        
        # If no lone equals found, return None
        if not lone_equals_positions:
            return None
        
        # For each lone equals, check if it's part of an assignment-in-comparison idiom
        for pos in lone_equals_positions:
            # Check if this specific assignment is part of a comparison
            # Look for comparison operators after this assignment
            rest_of_condition = condition[pos+1:]
            
            # Common patterns that indicate assignment-in-comparison:
            # - Assignment followed by comparison: (x = f()) != value
            # - Assignment with EOF: (ch = getchar()) != EOF
            if any(op in rest_of_condition for op in ['!=', '==', '<=', '>=', '<', '>', '===', '!==']):
                # Check if this is a direct assignment-comparison pattern
                # by looking at the structure around this equals
                before_assignment = condition[:pos].strip()
                if before_assignment.count('(') > before_assignment.count(')'):
                    # This assignment is inside parentheses, likely assignment-in-comparison
                    # But we need to check if it's the whole condition or just part
                    
                    # If there are logical operators (&&, ||) then this might be legitimate
                    if any(op in condition for op in ['&&', '||']):
                        # This is a complex expression, flag the assignment
                        return pos
                    else:
                        # Simple assignment-in-comparison, skip it
                        continue
                else:
                    # Assignment not in parentheses, flag it
                    return pos
            else:
                # No comparison operators after this assignment, flag it
                return pos
        
        return None


# Create rule instance and register it
_rule = BugAssignmentInConditionalRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    register_rule(_rule)
except ImportError:
    from engine.registry import register_rule
    register_rule(_rule)


