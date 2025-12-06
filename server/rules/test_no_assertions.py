"""
Rule: test.no_assertions

Detects test cases with no assertions/expectations (likely incomplete or false positives).
Handles common frameworks: PyTest/unittest, Jest/Mocha/Vitest, Go testing, Java JUnit/TestNG,
C# xUnit/NUnit/MSTest, C/C++ GoogleTest, Ruby RSpec/Minitest, Rust #[test], Swift XCTest.
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


class TestNoAssertionsRule(Rule):
    """
    Rule to detect test cases with no assertions/expectations.
    
    Flags test functions/methods that don't contain any assertion statements,
    which likely indicates incomplete tests or false positives.
    
    Examples of flagged patterns:
    - Python: def test_something(): pass
    - TypeScript: test("thing", () => { doWork(); })
    - Go: func TestThing(t *testing.T) { doWork() }
    
    Examples of allowed patterns:
    - Python: def test_something(): assert True
    - TypeScript: test("thing", () => { expect(1).toBe(1); })
    - Skipped tests: test.skip("thing", () => {}) - treated as intentional
    """
    
    meta = RuleMeta(
        id="test.no_assertions",
        category="test",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects test cases with no assertions/expectations (likely incomplete or false positives)",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Language-specific assertion patterns to look for
    ASSERT_TOKENS = {
        "python": {"assert ", "self.assert", "pytest.raises", "pytest.approx", "self.fail", "unittest.TestCase.assert"},
        "javascript": {"expect(", "assert.", "assert(", "should.", "chai.expect(", "toMatch", "toBe", "toEqual"},
        "typescript": {"expect(", "assert.", "assert(", "should.", "chai.expect(", "toMatch", "toBe", "toEqual"},
        "go": {"t.Errorf", "t.Error", "t.Fail", "t.Fatal", "require.", "assert.", "t.Log"},
        "java": {"assertThat(", "Assertions.", "Assert.", "assertEquals(", "assertTrue(", "assertThrows(", "@Test(expected", "fail("},
        "csharp": {"Assert.", "CollectionAssert.", "StringAssert.", "Should().", "FluentAssertions", "Xunit.Assert"},
        "cpp": {"EXPECT_", "ASSERT_", "GTEST_", "FAIL()", "ADD_FAILURE(", "TEST_", "REQUIRE("},
        "c": {"EXPECT_", "ASSERT_", "GTEST_", "CU_ASSERT", "REQUIRE(", "CHECK("},
        "ruby": {"expect(", ".should", " assert ", "refute", "must_", "wont_"},
        "rust": {"assert!(", "assert_eq!(", "assert_ne!(", "panic!(", "debug_assert!"},
        "swift": {"XCTAssert", "XCTFail(", "XCTExpectFailure"}
    }
    
    # Patterns that indicate intentionally skipped/ignored tests
    SKIP_PATTERNS = {
        "python": {"@pytest.mark.skip", "@unittest.skip", "pytest.mark.skip", "@skip"},
        "javascript": {"test.skip", "it.skip", "xtest", "xit", "describe.skip", ".skip("},
        "typescript": {"test.skip", "it.skip", "xtest", "xit", "describe.skip", ".skip("},
        "go": {"t.Skip", "t.SkipNow"},
        "java": {"@Ignore", "@Disabled", "assumeTrue(false)", "org.junit.Ignore"},
        "csharp": {"[Ignore]", "[Skip]", "Assert.Ignore", "Inconclusive"},
        "cpp": {"GTEST_SKIP", "DISABLED_"},
        "c": {"GTEST_SKIP", "DISABLED_"},
        "ruby": {"skip", "pending", "xit"},
        "rust": {"#[ignore]", "panic!(\"not implemented\")"},
        "swift": {"XCTSkip", "XCTExpectFailure"}
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.text:
            return
        
        # Get language from context
        language = self._get_language_from_context(ctx)
        if language not in self.meta.langs:
            return
        
        # Find test functions/methods in the file
        yield from self._analyze_test_functions(ctx, language)
    
    def _get_language_from_context(self, ctx: RuleContext) -> str:
        """Extract language from file context."""
        if hasattr(ctx, 'adapter') and hasattr(ctx.adapter, 'language_id'):
            return ctx.adapter.language_id
        
        # Fallback: extract from file extension
        file_path = ctx.file_path
        ext = file_path.split('.')[-1].lower()
        ext_map = {
            'py': 'python',
            'ts': 'typescript', 'tsx': 'typescript',
            'js': 'javascript', 'jsx': 'javascript',
            'go': 'go',
            'java': 'java',
            'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp',
            'c': 'c', 'h': 'c',
            'cs': 'csharp',
            'rb': 'ruby',
            'rs': 'rust',
            'swift': 'swift'
        }
        return ext_map.get(ext, 'python')
    
    def _analyze_test_functions(self, ctx: RuleContext, language: str) -> Iterable[Finding]:
        """Analyze file for test functions without assertions."""
        lines = ctx.text.split('\n')
        
        # Find test functions using language-specific patterns
        test_functions = self._find_test_functions(lines, language)
        
        for test_func in test_functions:
            if not self._has_assertions(test_func, language):
                if not self._is_intentionally_skipped(test_func, language):
                    # Calculate byte position for the finding
                    start_byte, end_byte = self._get_test_span(test_func, ctx.text)
                    
                    yield Finding(
                        rule=self.meta.id,
                        message="Test has no assertions—add expect(), assert, or similar to verify behavior.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="warning"
                    )
    
    def _find_test_functions(self, lines: List[str], language: str) -> List[Dict]:
        """Find test functions using language-specific patterns."""
        test_functions = []
        
        if language == "python":
            test_functions.extend(self._find_python_tests(lines))
        elif language in {"javascript", "typescript"}:
            test_functions.extend(self._find_js_ts_tests(lines))
        elif language == "go":
            test_functions.extend(self._find_go_tests(lines))
        elif language == "java":
            test_functions.extend(self._find_java_tests(lines))
        elif language == "csharp":
            test_functions.extend(self._find_csharp_tests(lines))
        elif language in {"c", "cpp"}:
            test_functions.extend(self._find_c_cpp_tests(lines))
        elif language == "ruby":
            test_functions.extend(self._find_ruby_tests(lines))
        elif language == "rust":
            test_functions.extend(self._find_rust_tests(lines))
        elif language == "swift":
            test_functions.extend(self._find_swift_tests(lines))
        
        return test_functions
    
    def _find_python_tests(self, lines: List[str]) -> List[Dict]:
        """Find Python test functions."""
        tests = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Track function definitions that look like tests
            if stripped.startswith('def '):
                # Extract function name
                match = re.search(r'def\s+(\w+)', stripped)
                if match:
                    func_name = match.group(1)
                    # Check if it's a test function (starts with test_ or has test decorators)
                    is_test = func_name.startswith('test_')
                    
                    # Also check for pytest decorators in previous lines
                    decorator_start = i
                    if not is_test:
                        for j in range(max(0, i-5), i):
                            if '@pytest.mark' in lines[j] or '@test' in lines[j]:
                                is_test = True
                                decorator_start = j
                                break
                    
                    if is_test:
                        # Extract function body, including any decorators
                        # Find decorator start line
                        decorator_start = i
                        for j in range(max(0, i-5), i):
                            if lines[j].strip().startswith('@'):
                                decorator_start = j
                                break
                        
                        function_body = self._extract_python_function_body(lines, decorator_start, i)
                        tests.append({
                            'name': func_name,
                            'start_line': decorator_start,
                            'lines': function_body,
                            'type': 'python_test'
                        })
        
        return tests
    
    def _find_js_ts_tests(self, lines: List[str]) -> List[Dict]:
        """Find JavaScript/TypeScript test functions."""
        tests = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Look for test calls: test("...", ...), it("...", ...), describe("...", ...)
            # IMPORTANT: Use word boundaries to avoid matching onSubmit, withIt, etc.
            # Also require the call to be at the start of a statement (after optional whitespace)
            test_patterns = [
                r'^\s*\b(test|it|describe)\s*\(',
                r'^\s*\b(test|it|describe)\.[a-zA-Z]+\s*\(',  # test.skip, it.only, etc.
            ]
            
            for pattern in test_patterns:
                match = re.search(pattern, line)
                if match:
                    # Extract the test body (simplified - look for the callback function)
                    test_body = self._extract_js_callback_body(lines, i)
                    if test_body:
                        tests.append({
                            'name': match.group(1),
                            'start_line': i,
                            'lines': test_body,
                            'type': 'js_test'
                        })
        
        return tests
    
    def _find_go_tests(self, lines: List[str]) -> List[Dict]:
        """Find Go test functions."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for func TestXxx(t *testing.T)
            match = re.search(r'func\s+(Test\w+)\s*\([^)]*\*testing\.T\)', line)
            if match:
                func_name = match.group(1)
                # Extract function body
                body_lines = self._extract_go_function_body(lines, i)
                tests.append({
                    'name': func_name,
                    'start_line': i,
                    'lines': body_lines,
                    'type': 'go_test'
                })
        
        return tests
    
    def _find_java_tests(self, lines: List[str]) -> List[Dict]:
        """Find Java test methods."""
        tests = []
        i = 0
        
        while i < len(lines):
            # Look for @Test annotation or other test annotations
            if '@Test' in lines[i] or '@Ignore' in lines[i] or '@Disabled' in lines[i]:
                # Find the start of annotations (look backwards for additional annotations)
                annotation_start = i
                while annotation_start > 0 and lines[annotation_start - 1].strip().startswith('@'):
                    annotation_start -= 1
                
                # Look for method definition in next few lines after @Test
                test_line = None
                for j in range(i, min(i + 5, len(lines))):
                    if '@Test' in lines[j]:
                        test_line = j
                        break
                
                if test_line is not None:
                    # Look for method definition after @Test
                    for method_line in range(test_line + 1, min(test_line + 5, len(lines))):
                        if 'void' in lines[method_line]:
                            match = re.search(r'void\s+(\w+)', lines[method_line])
                            if match:
                                method_name = match.group(1)
                                body_lines = self._extract_java_method_body(lines, method_line)
                                # Include all annotation lines in the body for skip detection
                                full_body = lines[annotation_start:method_line+1] + body_lines
                                tests.append({
                                    'name': method_name,
                                    'start_line': annotation_start,
                                    'lines': full_body,
                                    'type': 'java_test'
                                })
                                i = method_line + len(body_lines)  # Skip past this test
                                break
                    else:
                        i += 1
                else:
                    i += 1
            # Look for methods with test prefix (without @Test) - but only if we didn't just process a @Test
            elif re.search(r'(public|private|protected)?\s*void\s+test\w+', lines[i]):
                match = re.search(r'void\s+(test\w+)', lines[i])
                if match:
                    method_name = match.group(1)
                    body_lines = self._extract_java_method_body(lines, i)
                    tests.append({
                        'name': method_name,
                        'start_line': i,
                        'lines': [lines[i]] + body_lines,
                        'type': 'java_test'
                    })
                    i += len(body_lines)  # Skip past this test
            else:
                i += 1
        
        return tests
    
    def _find_csharp_tests(self, lines: List[str]) -> List[Dict]:
        """Find C# test methods."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for [Test], [Fact], [Theory] attributes
            if any(attr in line for attr in ['[Test]', '[Fact]', '[Theory]']):
                # Look for method definition in next few lines
                method_line = i + 1
                while method_line < len(lines) and 'void' not in lines[method_line]:
                    method_line += 1
                
                if method_line < len(lines):
                    match = re.search(r'void\s+(\w+)', lines[method_line])
                    if match:
                        method_name = match.group(1)
                        body_lines = self._extract_csharp_method_body(lines, method_line)
                        tests.append({
                            'name': method_name,
                            'start_line': i,
                            'lines': body_lines,
                            'type': 'csharp_test'
                        })
        
        return tests
    
    def _find_c_cpp_tests(self, lines: List[str]) -> List[Dict]:
        """Find C/C++ test functions (GoogleTest)."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for TEST(, TEST_F(, TEST_P( macros
            match = re.search(r'(TEST|TEST_F|TEST_P)\s*\([^)]+\)', line)
            if match:
                test_name = match.group(1)
                # Extract test body
                body_lines = self._extract_c_cpp_test_body(lines, i)
                tests.append({
                    'name': test_name,
                    'start_line': i,
                    'lines': body_lines,
                    'type': 'cpp_test'
                })
        
        return tests
    
    def _find_ruby_tests(self, lines: List[str]) -> List[Dict]:
        """Find Ruby test methods."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for it "...", test "...", specify "..."
            match = re.search(r'\b(it|test|specify)\s+["\']([^"\']*)["\']', line)
            if match:
                test_name = match.group(1)
                body_lines = self._extract_ruby_block_body(lines, i)
                tests.append({
                    'name': test_name,
                    'start_line': i,
                    'lines': body_lines,
                    'type': 'ruby_test'
                })
        
        return tests
    
    def _find_rust_tests(self, lines: List[str]) -> List[Dict]:
        """Find Rust test functions."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for #[test] attribute
            if '#[test]' in line:
                # Look for function definition in next line
                if i + 1 < len(lines):
                    next_line = lines[i + 1]
                    match = re.search(r'fn\s+(\w+)', next_line)
                    if match:
                        func_name = match.group(1)
                        body_lines = self._extract_rust_function_body(lines, i + 1)
                        tests.append({
                            'name': func_name,
                            'start_line': i,
                            'lines': body_lines,
                            'type': 'rust_test'
                        })
        
        return tests
    
    def _find_swift_tests(self, lines: List[str]) -> List[Dict]:
        """Find Swift test methods."""
        tests = []
        
        for i, line in enumerate(lines):
            # Look for func testXxx() methods
            match = re.search(r'func\s+(test\w+)', line)
            if match:
                func_name = match.group(1)
                body_lines = self._extract_swift_function_body(lines, i)
                tests.append({
                    'name': func_name,
                    'start_line': i,
                    'lines': body_lines,
                    'type': 'swift_test'
                })
        
        return tests
    
    # Helper methods for extracting function/method bodies
    def _extract_python_function_body(self, lines: List[str], decorator_start: int, func_start: int) -> List[str]:
        """Extract Python function body based on indentation, including decorators."""
        body = []
        if func_start >= len(lines):
            return body
        
        # Include decorators if any
        for i in range(decorator_start, func_start):
            body.append(lines[i])
            
        # Get the base indentation level (the function definition line)
        def_line = lines[func_start]
        base_indent = len(def_line) - len(def_line.lstrip())
        
        # Add the function definition line
        body.append(def_line)
        
        # For multi-line function definitions, we need to find where the signature ends
        # (i.e., find the line ending with ':')
        signature_end = func_start
        for i in range(func_start, min(func_start + 20, len(lines))):
            line = lines[i]
            body_line = line.rstrip()
            if i > func_start:
                body.append(line)
            # Check if this line ends with ':' (end of function signature)
            # Also handle ') -> Type:' and similar patterns
            if body_line.endswith(':'):
                signature_end = i
                break
        
        # Now extract the actual function body after the signature
        for i in range(signature_end + 1, len(lines)):
            line = lines[i]
            
            # Skip empty lines
            if not line.strip():
                body.append(line)
                continue
            
            # Check indentation
            line_indent = len(line) - len(line.lstrip())
            
            # If we're back to the same level or less than the function def, we're done
            if line_indent <= base_indent:
                break
                
            body.append(line)
        
        return body
    
    def _extract_js_callback_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract JavaScript callback body (simplified)."""
        body = []
        brace_count = 0
        found_start = False
        
        for i in range(start_line, min(start_line + 20, len(lines))):
            line = lines[i]
            if '{' in line:
                found_start = True
            if found_start:
                body.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and found_start:
                    break
        
        return body
    
    def _extract_go_function_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract Go function body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_java_method_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract Java method body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_csharp_method_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract C# method body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_c_cpp_test_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract C/C++ test body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_ruby_block_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract Ruby block body (do...end or {...})."""
        body = []
        in_block = False
        
        for i in range(start_line, min(start_line + 20, len(lines))):
            line = lines[i]
            if 'do' in line or '{' in line:
                in_block = True
            if in_block:
                body.append(line)
                if 'end' in line or '}' in line:
                    break
        
        return body
    
    def _extract_rust_function_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract Rust function body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_swift_function_body(self, lines: List[str], start_line: int) -> List[str]:
        """Extract Swift function body."""
        return self._extract_brace_body(lines, start_line)
    
    def _extract_brace_body(self, lines: List[str], start_line: int) -> List[str]:
        """Generic brace-based body extraction."""
        body = []
        brace_count = 0
        found_start = False
        
        for i in range(start_line, min(start_line + 50, len(lines))):
            line = lines[i]
            if '{' in line:
                found_start = True
            if found_start:
                body.append(line)
                brace_count += line.count('{') - line.count('}')
                if brace_count <= 0 and found_start and i > start_line:
                    break
        
        return body
    
    def _has_assertions(self, test_func: Dict, language: str) -> bool:
        """Check if test function contains assertion patterns."""
        # Check each line of the test function for assertions, ignoring comments
        assert_patterns = self.ASSERT_TOKENS.get(language, set())
        
        for line in test_func['lines']:
            # Skip comment lines for more accurate detection
            stripped_line = line.strip()
            if language == "python" and (stripped_line.startswith('#') or not stripped_line):
                continue
            elif language in {"javascript", "typescript"} and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language == "java" and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language == "csharp" and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language in {"c", "cpp"} and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language == "go" and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language == "ruby" and (stripped_line.startswith('#') or not stripped_line):
                continue
            elif language == "rust" and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
            elif language == "swift" and (stripped_line.startswith('//') or stripped_line.startswith('/*') or not stripped_line):
                continue
                
            # Check for assertion patterns in non-comment lines
            for pattern in assert_patterns:
                if pattern.lower() in line.lower():
                    return True
        
        return False
    
    def _is_intentionally_skipped(self, test_func: Dict, language: str) -> bool:
        """Check if test is intentionally skipped/ignored."""
        # Combine all lines of the test function
        test_text = "\n".join(test_func['lines'])
        
        # Check for skip patterns specific to the language
        skip_patterns = self.SKIP_PATTERNS.get(language, set())
        for pattern in skip_patterns:
            # Use case-insensitive matching for patterns
            if pattern.lower() in test_text.lower():
                return True
        
        return False
    
    def _get_test_span(self, test_func: Dict, full_text: str) -> tuple[int, int]:
        """Get byte span for the test function."""
        lines = full_text.split('\n')
        start_line = test_func['start_line']
        
        # Calculate byte offset to start of the line
        start_byte = sum(len(line) + 1 for line in lines[:start_line])  # +1 for newline
        
        # Find end of test name for a reasonable span
        if start_line < len(lines):
            line = lines[start_line]
            # Find the test name in the line for a focused span
            test_name_match = re.search(r'(test\w*|Test\w*|it|describe)', line)
            if test_name_match:
                name_start = test_name_match.start()
                name_end = test_name_match.end()
                return start_byte + name_start, start_byte + name_end
        
        # Fallback: highlight the entire first line
        end_byte = start_byte + len(lines[start_line])
        return start_byte, end_byte


# Create rule instance and register it
_rule = TestNoAssertionsRule()

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


