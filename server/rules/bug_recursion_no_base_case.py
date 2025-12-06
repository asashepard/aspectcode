"""
Recursion Without Base Case Detection Rule

This rule detects functions/methods that call themselves recursively without 
an explicit base case or guard condition. Such functions will likely cause 
stack overflow errors or infinite recursion.

Common problematic patterns:
- Recursive calls without terminating conditions
- Guards that appear after the first recursive call
- Functions with only recursive paths

Examples:
- RISKY: def f(n): return f(n-1)
- SAFE:  def f(n): if n <= 0: return 1; return f(n-1)

- RISKY: function fact(n) { return fact(n-1); }
- SAFE:  function fact(n) { if (n === 0) return 1; return fact(n-1); }

- RISKY: int f(int n) { return f(n-1); }
- SAFE:  int f(int n) { if (n == 0) return 0; return f(n-1); }
"""

import re
from typing import Iterable, Set, Optional, List, Dict, Any

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugRecursionNoBaseCaseRule:
    """
    Rule to detect recursive functions without explicit base cases.
    
    Analyzes function definitions to find:
    1. Functions that call themselves recursively
    2. No apparent base case guard before the first recursive call
    3. Missing terminating conditions
    
    Examples of flagged patterns:
    - def f(n): return f(n-1)
    - function fact(n) { return fact(n-1); }
    - int fibonacci(int n) { return fibonacci(n-1) + fibonacci(n-2); }
    
    Examples of safe patterns:
    - def f(n): if n <= 0: return 1; return f(n-1)
    - function fact(n) { if (n === 0) return 1; return n * fact(n-1); }
    """
    
    meta = RuleMeta(
        id="bug.recursion_no_base_case",
        category="bug",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects functions/methods that call themselves recursively without an explicit base-case/guard; prompts adding a terminating condition or converting to iteration",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Function definition patterns for each language
    FUNCTION_PATTERNS = {
        "python": [
            r'^\s*def\s+(\w+)\s*\([^)]*\)\s*:',  # def function_name():
        ],
        "typescript": [
            r'^\s*function\s+(\w+)\s*\([^)]*\)\s*:\s*\w+\s*{',  # function name(...): type {
            r'^\s*function\s+(\w+)\s*\([^)]*\)\s*{',  # function name() {
            r'^\s*(\w+)\s*\([^)]*\)\s*:\s*\w+\s*{',  # method_name(): type {
            r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*\([^)]*\)\s*:\s*\w+\s*=>\s*{',  # arrow functions with type
            r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*\([^)]*\)\s*=>\s*{',  # arrow functions
        ],
        "javascript": [
            r'^\s*function\s+(\w+)\s*\([^)]*\)\s*{',  # function name() {
            r'^\s*(\w+)\s*\([^)]*\)\s*{',  # method_name() {
            r'^\s*(?:const|let|var)\s+(\w+)\s*=\s*\([^)]*\)\s*=>\s*{',  # arrow functions
        ],
        "go": [
            r'^\s*func\s+(\w+)\s*\([^)]*\)\s*[^{]*{',  # func name() {
        ],
        "java": [
            r'^\s*(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*{',  # method declarations
        ],
        "cpp": [
            r'^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*{',  # function definitions
        ],
        "c": [
            r'^\s*(?:\w+\s+)*(\w+)\s*\([^)]*\)\s*{',  # function definitions
        ],
        "csharp": [
            r'^\s*(?:public|private|protected|internal)?\s*(?:static)?\s*\w+\s+(\w+)\s*\([^)]*\)\s*{',  # method declarations
        ],
        "ruby": [
            r'^\s*def\s+(\w+)(?:\s*\([^)]*\))?\s*$',  # def method_name
        ],
        "rust": [
            r'^\s*fn\s+(\w+)\s*\([^)]*\)\s*(?:->\s*\w+)?\s*{',  # fn function_name() {
        ],
        "swift": [
            r'^\s*func\s+(\w+)\s*\([^)]*\)\s*(?:->\s*\w+)?\s*{',  # func function_name() {
        ],
    }
    
    # Base case guard patterns that indicate terminating conditions
    BASE_CASE_PATTERNS = [
        r'if\s*\([^)]*<=\s*0[^)]*\)',  # if (n <= 0)
        r'if\s*\([^)]*==\s*0[^)]*\)',  # if (n == 0)
        r'if\s*\([^)]*<\s*1[^)]*\)',   # if (n < 1)
        r'if\s*\([^)]*<=\s*1[^)]*\)',  # if (n <= 1)
        r'if\s*\([^)]*is\s+None[^)]*\)',  # if (x is None)
        r'if\s*\([^)]*===\s*null[^)]*\)',  # if (x === null)
        r'if\s*\([^)]*==\s*null[^)]*\)',   # if (x == null)
        r'if\s*\([^)]*\.length\s*==\s*0[^)]*\)',  # if (arr.length == 0)
        r'if\s*\([^)]*\.isEmpty\(\)[^)]*\)',  # if (list.isEmpty())
        r'if\s*\([^)]*\.empty\(\)[^)]*\)',    # if (container.empty())
        r'if\s+[^:\s]+\s*<=\s*0\s*:',  # Python: if n <= 0:
        r'if\s+[^:\s]+\s*==\s*0\s*:',  # Python: if n == 0:
        r'if\s+[^:\s]+\s*<\s*1\s*:',   # Python: if n < 1:
        r'if\s+[^:\s]+\s*<=\s*1\s*:',  # Python: if n <= 1:
        r'if\s+[^:\s]+\s+is\s+None\s*:',  # Python: if x is None:
        r'if\s+len\([^)]+\)\s*==\s*0\s*:',  # Python: if len(arr) == 0:
        r'return\s+[^;]+\s+if\s+[^;]*<=\s*0',  # Ternary/guard returns
        r'return\s+[^;]+\s+if\s+[^;]*==\s*0',
        r'return\s+[^;]+\s+if\s+[^;]*<=\s*1',
        r'guard\s+[^{]*>\s*0',  # Swift guard statements
        r'guard\s+[^{]*!=\s*nil',
    ]
    
    # Return/exit statements that would stop recursion
    RETURN_PATTERNS = [
        r'return\s+[^;]+;?\s*$',  # return statement
        r'return\s*;?\s*$',       # bare return
        r'break\s*;?\s*$',        # break statement
        r'continue\s*;?\s*$',     # continue statement
        r'throw\s+[^;]+;?\s*$',   # throw statement
        r'raise\s+[^;]+;?\s*$',   # Python raise statement
    ]
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze text for recursive functions without base cases."""
        if ctx.language not in self.meta.langs:
            return
        
        # Use text-based analysis since that's what the existing codebase uses
        yield from self._analyze_text(ctx, ctx.text, ctx.language)
    
    def _analyze_text(self, ctx: RuleContext, text: str, language: str) -> Iterable[Finding]:
        """Analyze text for recursive functions without proper base cases."""
        lines = text.split('\n')
        
        # Find all function definitions
        functions = self._find_functions(lines, language)
        
        for func_info in functions:
            func_name = func_info['name']
            start_line = func_info['start_line']
            end_line = func_info['end_line']
            # Get only the function body, excluding the definition line
            func_lines = lines[start_line + 1:end_line + 1]
            
            # Check if function calls itself recursively
            recursive_calls = self._find_recursive_calls(func_lines, func_name, language)
            if not recursive_calls:
                continue
            
            # Check if there's a base case guard before the first recursive call
            first_call_line = min(call['line'] for call in recursive_calls)
            has_base_case = self._has_base_case_guard(func_lines[:first_call_line], language)
            
            if not has_base_case:
                # Calculate byte positions for the function header
                func_header_line = lines[start_line]
                
                # Find start of function name in the line
                patterns = self.FUNCTION_PATTERNS.get(language, [])
                name_start = name_end = 0
                
                for pattern in patterns:
                    match = re.search(pattern, func_header_line)
                    if match and match.group(1) == func_name:
                        name_start = match.start(1)
                        name_end = match.end(1)
                        break
                
                # Calculate byte position
                lines_before = lines[:start_line]
                start_byte = sum(len(line) + 1 for line in lines_before) + name_start  # +1 for newlines
                end_byte = sum(len(line) + 1 for line in lines_before) + name_end
                
                yield Finding(
                    rule=self.meta.id,
                    message="Recursive function without a visible base case—add a condition to stop recursion.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error",
                    autofix=None,
                    meta={
                        "function_name": func_name,
                        "recursive_calls": len(recursive_calls),
                        "language": language,
                        "suggestion": f"Add a base case like 'if {self._suggest_base_case(language)}' before the recursive call, or consider using iteration instead."
                    }
                )
    
    def _find_functions(self, lines: List[str], language: str) -> List[Dict[str, Any]]:
        """Find all function definitions in the text."""
        functions = []
        patterns = self.FUNCTION_PATTERNS.get(language, [])
        
        for line_num, line in enumerate(lines):
            for pattern in patterns:
                match = re.search(pattern, line)
                if match:
                    func_name = match.group(1)
                    
                    # Find the end of this function
                    end_line = self._find_function_end(lines, line_num, language)
                    
                    functions.append({
                        'name': func_name,
                        'start_line': line_num,
                        'end_line': end_line,
                        'header_line': line
                    })
                    break
        
        return functions
    
    def _find_function_end(self, lines: List[str], start_line: int, language: str) -> int:
        """Find the end line of a function definition."""
        if language == "python":
            # Python uses indentation
            base_indent = len(lines[start_line]) - len(lines[start_line].lstrip())
            
            for i in range(start_line + 1, len(lines)):
                line = lines[i]
                if line.strip() == "":
                    continue
                    
                current_indent = len(line) - len(line.lstrip())
                if current_indent <= base_indent and line.strip():
                    return i - 1
            
            return len(lines) - 1
            
        elif language == "ruby":
            # Ruby uses 'end' keyword
            for i in range(start_line + 1, len(lines)):
                line = lines[i].strip()
                if line == "end" or line.startswith("end "):
                    return i
            
            return len(lines) - 1
            
        else:
            # Most languages use braces
            brace_count = 0
            found_opening = False
            
            # Count braces starting from the function definition line
            for i in range(start_line, len(lines)):
                line = lines[i]
                
                for char in line:
                    if char == '{':
                        brace_count += 1
                        found_opening = True
                    elif char == '}':
                        brace_count -= 1
                        
                        if found_opening and brace_count == 0:
                            return i
            
            return len(lines) - 1
    
    def _find_recursive_calls(self, func_lines: List[str], func_name: str, language: str) -> List[Dict[str, Any]]:
        """Find all recursive calls within a function."""
        calls = []
        
        for line_num, line in enumerate(func_lines):
            # Skip comments to avoid false positives
            if self._is_comment_line(line, language):
                continue
            
            # Look for function calls that match the function name
            # Use word boundaries to avoid false matches in substrings
            call_pattern = rf'\b{re.escape(func_name)}\s*\('
            
            matches = re.finditer(call_pattern, line)
            for match in matches:
                calls.append({
                    'line': line_num,
                    'position': match.start(),
                    'text': match.group()
                })
        
        return calls
    
    def _has_base_case_guard(self, lines_before_recursion: List[str], language: str) -> bool:
        """Check if there's a base case guard before the recursive call."""
        text_before = '\n'.join(lines_before_recursion)
        
        # Look for typical base case patterns
        for pattern in self.BASE_CASE_PATTERNS:
            if re.search(pattern, text_before, re.IGNORECASE):
                # Verify this guard has a return/exit statement
                if self._guard_has_return(text_before, pattern):
                    return True
        
        # Check for immediate return statements at the start
        for line in lines_before_recursion:
            line = line.strip()
            if not line or self._is_comment_line(line, language):
                continue
                
            for return_pattern in self.RETURN_PATTERNS:
                if re.match(return_pattern, line):
                    return True
            
            # If we hit any non-return/non-guard statement, stop looking
            if not any(re.search(pattern, line, re.IGNORECASE) for pattern in self.BASE_CASE_PATTERNS):
                break
        
        return False
    
    def _guard_has_return(self, text: str, guard_pattern: str) -> bool:
        """Check if a guard condition is followed by a return/exit statement."""
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            if re.search(guard_pattern, line, re.IGNORECASE):
                # Look at the next few lines for return statements
                for j in range(i, min(i + 5, len(lines))):
                    check_line = lines[j]
                    for return_pattern in self.RETURN_PATTERNS:
                        if re.search(return_pattern, check_line):
                            return True
                break
        
        return False
    
    def _is_comment_line(self, line: str, language: str) -> bool:
        """Check if a line is primarily a comment."""
        line = line.strip()
        
        if language == "python":
            return line.startswith('#')
        elif language in ["javascript", "typescript", "java", "cpp", "c", "csharp", "go", "rust", "swift"]:
            return line.startswith('//') or line.startswith('/*') or line.startswith('*')
        elif language == "ruby":
            return line.startswith('#')
        
        return False
    
    def _suggest_base_case(self, language: str) -> str:
        """Suggest an appropriate base case condition for the language."""
        if language == "python":
            return "n <= 0: return 1"
        elif language in ["javascript", "typescript"]:
            return "(n === 0) return 1;"
        elif language in ["java", "cpp", "c", "csharp"]:
            return "(n == 0) return 1;"
        elif language == "go":
            return "n <= 0 { return 1 }"
        elif language == "ruby":
            return "n <= 0; return 1; end"
        elif language == "rust":
            return "n <= 0 { return 1; }"
        elif language == "swift":
            return "n <= 0 { return 1 }"
        else:
            return "n <= 0: return base_value"


