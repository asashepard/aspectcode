"""
Rule: test.todo_comment

Detects TODO/FIXME/SKIP comments in test files without assertions and suggests 
implementing or removing them. Focuses on incomplete test code patterns that 
indicate unfinished test implementation.
"""

import re
from typing import List, Set, Dict, Iterable, Optional, Tuple

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class TestTodoCommentRule:
    """
    Rule to detect TODO/FIXME/SKIP comments in test files without assertions.
    
    Flags TODO, FIXME, or SKIP comments in test functions/methods that don't 
    contain any assertion statements, indicating incomplete test implementation.
    
    Examples of flagged patterns:
    - Python: def test_something(): # TODO: implement this test
    - TypeScript: test("thing", () => { // FIXME: add assertions })
    - Go: func TestThing(t *testing.T) { // TODO: add test logic }
    
    Examples of allowed patterns:
    - Python: def test_something(): # TODO: refactor; assert True
    - TypeScript: test("thing", () => { expect(1).toBe(1); // TODO: add more cases })
    - Skipped tests: @pytest.mark.skip("TODO: fix later") - intentionally empty
    """
    
    @property
    def meta(self) -> RuleMeta:
        return RuleMeta(
            id="test.todo_comment",
            category="test",
            tier=0,  # Text-based analysis only
            priority="P2",
            autofix_safety="suggest-only", 
            description="Detects TODO/FIXME/SKIP comments in test files without assertions",
            langs=["python", "typescript", "javascript", "go", "java", "csharp", "ruby", "rust"]
        )
    
    @property
    def requires(self) -> Requires:
        return Requires(raw_text=True, syntax=False)
    
    # TODO/FIXME comment patterns
    TODO_PATTERNS = [
        r"(?://|#|<!--)\s*(?:TODO|FIXME|SKIP|XXX|HACK|BUG|NOTE):?\s*([^\r\n]*)",
        r"/\*\s*(?:TODO|FIXME|SKIP|XXX|HACK|BUG|NOTE):?\s*([^*]*)\*/",
    ]
    
    # Language-specific test function patterns  
    TEST_FUNCTION_PATTERNS = {
        "python": [
            r"def\s+(test_\w+)\s*\([^)]*\)\s*:",
            r"class\s+(Test\w+)\s*\([^)]*\)\s*:",
        ],
        "javascript": [
            r"\b(?:test|it|describe)\s*\(\s*['\"]([^'\"]*)['\"]",
            r"function\s+(test\w+)\s*\(",
        ],
        "typescript": [
            r"\b(?:test|it|describe)\s*\(\s*['\"]([^'\"]*)['\"]",
            r"function\s+(test\w+)\s*\(",
        ],
        "go": [
            r"func\s+(Test\w+)\s*\([^)]*\*testing\.T\)",
        ],
        "java": [
            r"(?:@Test\s*(?:\([^)]*\))?\s*)?(?:public\s+|private\s+)?void\s+(\w*test\w*|Test\w+)\s*\(",
        ],
        "csharp": [
            r"\[(?:Test|Fact|Theory)\].*?(?:public\s+|private\s+)?void\s+(\w+)",
            r"(?:public\s+|private\s+)?void\s+(Test\w+)\s*\(",
        ],
        "ruby": [
            r"(?:def\s+(test_\w+)|it\s+['\"]([^'\"]*)['\"]|test\s+['\"]([^'\"]*)['\"])",
        ],
        "rust": [
            r"#\[test\]\s*fn\s+(\w+)\s*\(",
        ],
    }
    
    # Language-specific assertion patterns
    ASSERTION_PATTERNS = {
        "python": [
            r"\bassert\b",
            r"self\.assert\w+",
            r"pytest\.raises",
            r"self\.fail",
            r"unittest\.TestCase\.assert",
        ],
        "javascript": [
            r"\bexpect\s*\(",
            r"\bassert\s*[\.\(]",
            r"should\.",
            r"chai\.expect",
            r"\.to(?:Match|Be|Equal)",
        ],
        "typescript": [
            r"\bexpect\s*\(",
            r"\bassert\s*[\.\(]",
            r"should\.",
            r"chai\.expect",
            r"\.to(?:Match|Be|Equal)",
        ],
        "go": [
            r"t\.(?:Error|Fatal|Fail|Log)f?",
            r"require\.",
            r"assert\.",
        ],
        "java": [
            r"\bassert(?:That|True|False|Equals|NotNull|Null|Throws)",
            r"Assertions\.",
            r"Assert\.",
            r"assertEquals",
            r"fail\s*\(",
        ],
        "csharp": [
            r"\bAssert\.",
            r"CollectionAssert\.",
            r"StringAssert\.",
            r"Should\(\)\.",
            r"FluentAssertions",
        ],
        "ruby": [
            r"\bexpect\s*\(",
            r"\.should\b",
            r"\bassert",
            r"refute\b",
            r"must_",
            r"wont_",
        ],
        "rust": [
            r"\bassert!",
            r"assert_eq!",
            r"assert_ne!",
            r"panic!",
            r"debug_assert!",
        ],
    }
    
    # Patterns indicating intentional skip/ignore
    SKIP_PATTERNS = {
        "python": [
            r"@pytest\.mark\.skip",
            r"@unittest\.skip",
            r"pytest\.skip",
            r"@skip",
        ],
        "javascript": [
            r"\btest\.skip\s*\(",
            r"\bit\.skip\s*\(",
            r"\bxit\s*\(",
            r"\bxtest\s*\(",
        ],
        "typescript": [
            r"\btest\.skip\s*\(",
            r"\bit\.skip\s*\(",
            r"\bxit\s*\(",
            r"\bxtest\s*\(",
        ],
        "go": [
            r"t\.Skip",
            r"t\.SkipNow",
        ],
        "java": [
            r"@Ignore",
            r"@Disabled",
            r"enabled\s*=\s*false",
        ],
        "csharp": [
            r"\[Ignore\]",
            r"\[Skip\]",
            r"Skip\s*=",
        ],
        "ruby": [
            r"\bskip\b",
            r"\bpending\b",
            r"\bxit\b",
        ],
        "rust": [
            r"#\[ignore\]",
            r"panic!\s*\(\s*['\"]not implemented['\"]",
        ],
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.text:
            return
        
        # Check if this is a test file
        if not self._is_test_file(ctx.file_path):
            return
        
        # Get language from context
        language = self._get_language_from_context(ctx)
        if language not in self.meta.langs:
            return
        
        # Find TODO comments in test functions without assertions
        yield from self._analyze_todo_comments_in_tests(ctx, language)
    
    def _is_test_file(self, file_path: str) -> bool:
        """Check if the file is a test file based on naming conventions."""
        filename = file_path.lower()
        test_indicators = [
            'test_',
            '_test',
            'tests.',
            'spec.',
            '_spec',
            'test/',
            '/test',
            '__test__',
            '.test.',
            '.spec.',
        ]
        return any(indicator in filename for indicator in test_indicators)
    
    def _get_language_from_context(self, ctx: RuleContext) -> str:
        """Extract language from context."""
        if hasattr(ctx, 'adapter') and hasattr(ctx.adapter, 'language_id'):
            return ctx.adapter.language_id
        
        # Fallback: extract from file extension
        file_path = ctx.file_path
        ext = file_path.split('.')[-1].lower()
        ext_map = {
            'py': 'python',
            'ts': 'typescript', 'tsx': 'typescript',
            'js': 'javascript', 'jsx': 'javascript', 'mjs': 'javascript',
            'go': 'go',
            'java': 'java',
            'cs': 'csharp',
            'rb': 'ruby',
            'rs': 'rust',
        }
        return ext_map.get(ext, 'python')
    
    def _analyze_todo_comments_in_tests(self, ctx: RuleContext, language: str) -> Iterable[Finding]:
        """Find TODO comments in test functions that lack assertions."""
        text = ctx.text
        
        # Find all test functions
        test_functions = self._find_test_functions(text, language)
        
        for test_func in test_functions:
            # Check if this test is intentionally skipped
            if self._is_intentionally_skipped(test_func, language):
                continue
            
            # Check if test has assertions
            if self._has_assertions(test_func, language):
                continue
            
            # Look for TODO comments in this test function
            todo_comments = self._find_todo_comments_in_function(test_func, text)
            
            for comment in todo_comments:
                yield Finding(
                    rule=self.meta.id,
                    message=f"TODO comment in test without assertions: '{comment['text']}'. Either implement the test with assertions or remove/mark as skip.",
                    file=ctx.file_path,
                    start_byte=comment['start_byte'],
                    end_byte=comment['end_byte'],
                    severity="info"
                )
    
    def _find_test_functions(self, text: str, language: str) -> List[Dict]:
        """Find test functions in the code."""
        test_functions = []
        patterns = self.TEST_FUNCTION_PATTERNS.get(language, [])
        
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.IGNORECASE):
                # Find the function body
                func_start = match.start()
                func_body = self._extract_function_body(text, func_start, language)
                
                if func_body:
                    test_functions.append({
                        'name': match.group(1) if match.lastindex else 'unknown',
                        'start_byte': func_start,
                        'end_byte': func_start + len(func_body),
                        'body': func_body,
                        'full_match': match.group(0)
                    })
        
        return test_functions
    
    def _extract_function_body(self, text: str, start_pos: int, language: str) -> str:
        """Extract function body from the given start position."""
        if language == "python":
            return self._extract_python_function_body(text, start_pos)
        elif language in {"javascript", "typescript"}:
            return self._extract_brace_function_body(text, start_pos)
        elif language in {"go", "java", "csharp", "rust"}:
            return self._extract_brace_function_body(text, start_pos)
        elif language == "ruby":
            return self._extract_ruby_function_body(text, start_pos)
        else:
            return self._extract_brace_function_body(text, start_pos)
    
    def _extract_python_function_body(self, text: str, start_pos: int) -> str:
        """Extract Python function body based on indentation."""
        # Find the beginning of any decorators before the function
        lines_before_start = text[:start_pos].split('\n')
        
        # Look backwards to find decorators
        decorator_start_line = len(lines_before_start) - 1
        for i in range(len(lines_before_start) - 1, max(0, len(lines_before_start) - 10), -1):
            line = lines_before_start[i]
            if line.strip().startswith('@'):
                decorator_start_line = i
            elif line.strip() and not line.strip().startswith('@'):
                break
        
        # Recalculate start position to include decorators
        if decorator_start_line < len(lines_before_start) - 1:
            decorator_start_pos = sum(len(line) + 1 for line in lines_before_start[:decorator_start_line])
            text_from_decorators = text[decorator_start_pos:]
        else:
            text_from_decorators = text[start_pos:]
        
        lines = text_from_decorators.split('\n')
        if not lines:
            return ""
        
        # Find the function definition line in the included text
        func_line_idx = 0
        for i, line in enumerate(lines):
            if 'def ' in line:
                func_line_idx = i
                break
        
        # Get the base indentation level (function definition line)
        def_line = lines[func_line_idx]
        base_indent = len(def_line) - len(def_line.lstrip())
        
        # Include all lines from decorators to end of function
        body_lines = lines[:func_line_idx + 1]  # Include decorators and function def
        
        for i in range(func_line_idx + 1, len(lines)):
            line = lines[i]
            
            # Skip empty lines
            if not line.strip():
                body_lines.append(line)
                continue
            
            # Check indentation
            line_indent = len(line) - len(line.lstrip())
            
            # If we're back to the same level or less than the function def, we're done
            if line_indent <= base_indent:
                break
            
            body_lines.append(line)
        
        return '\n'.join(body_lines)
    
    def _extract_brace_function_body(self, text: str, start_pos: int) -> str:
        """Extract function body for brace-based languages."""
        brace_count = 0
        found_opening_brace = False
        current_pos = start_pos
        
        while current_pos < len(text):
            char = text[current_pos]
            
            if char == '{':
                brace_count += 1
                found_opening_brace = True
            elif char == '}':
                brace_count -= 1
                
            current_pos += 1
            
            if found_opening_brace and brace_count == 0:
                break
        
        return text[start_pos:current_pos]
    
    def _extract_ruby_function_body(self, text: str, start_pos: int) -> str:
        """Extract Ruby function body (until 'end' keyword)."""
        remaining_text = text[start_pos:]
        
        # For blocks with 'do...end'
        if 'do' in remaining_text[:100]:  # Look in first 100 chars
            end_match = re.search(r'\bend\b', remaining_text)
            if end_match:
                return remaining_text[:end_match.end()]
        
        # For blocks with curly braces
        return self._extract_brace_function_body(text, start_pos)
    
    def _find_todo_comments_in_function(self, test_func: Dict, full_text: str) -> List[Dict]:
        """Find TODO/FIXME comments within a specific test function."""
        func_body = test_func['body']
        func_start = test_func['start_byte']
        
        comments = []
        seen_positions = set()  # Track positions to avoid duplicates
        
        for pattern in self.TODO_PATTERNS:
            for match in re.finditer(pattern, func_body, re.MULTILINE | re.IGNORECASE):
                # Calculate absolute position in full text
                comment_start = func_start + match.start()
                comment_end = func_start + match.end()
                
                # Skip if we've already found a comment at this position
                if comment_start in seen_positions:
                    continue
                seen_positions.add(comment_start)
                
                comment_text = match.group(1).strip() if match.lastindex else match.group(0).strip()
                
                comments.append({
                    'text': comment_text,
                    'start_byte': comment_start,
                    'end_byte': comment_end,
                })
        
        return comments
    
    def _has_assertions(self, test_func: Dict, language: str) -> bool:
        """Check if test function contains assertion patterns."""
        func_body = test_func['body']
        assertion_patterns = self.ASSERTION_PATTERNS.get(language, [])
        
        for pattern in assertion_patterns:
            if re.search(pattern, func_body, re.IGNORECASE):
                return True
        
        return False
    
    def _is_intentionally_skipped(self, test_func: Dict, language: str) -> bool:
        """Check if test is intentionally skipped/ignored."""
        func_body = test_func['body']
        skip_patterns = self.SKIP_PATTERNS.get(language, [])
        
        for pattern in skip_patterns:
            if re.search(pattern, func_body, re.IGNORECASE):
                return True
        
        return False


# Create rule instance and export
_rule = TestTodoCommentRule()
RULES = [_rule]


