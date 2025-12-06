"""
Tests for Recursion Without Base Case Detection Rule

Tests various scenarios where functions call themselves recursively
without proper base cases and verifies that the rule correctly identifies
risky patterns while avoiding false positives on safe recursive patterns.
"""

import unittest
from unittest.mock import Mock
from rules.bug_recursion_no_base_case import BugRecursionNoBaseCaseRule
from engine.types import RuleContext


class TestBugRecursionNoBaseCaseRule(unittest.TestCase):
    """Test cases for the recursion without base case detection rule."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugRecursionNoBaseCaseRule()
    
    def _create_context(self, code: str, language: str, filename: str) -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = language
        context.file_path = filename
        context.syntax_tree = None  # We're using text-based analysis
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.recursion_no_base_case"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.tier == 0
        
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires syntax analysis."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_python_simple(self):
        """Test Python function with simple recursion, no base case."""
        code = """
def factorial(n):
    return factorial(n - 1)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["function_name"] == "factorial"
        assert finding.meta["language"] == "python"
    
    def test_positive_case_python_multiple_recursion(self):
        """Test Python function with multiple recursive calls, no base case."""
        code = """
def fibonacci(n):
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "fibonacci"
        assert finding.meta["recursive_calls"] == 2
    
    def test_positive_case_javascript_simple(self):
        """Test JavaScript function with recursion, no base case."""
        code = """
function factorial(n) {
    return factorial(n - 1);
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
        assert finding.meta["language"] == "javascript"
    
    def test_positive_case_typescript_arrow_function(self):
        """Test TypeScript arrow function with recursion, no base case."""
        code = """
const factorial = (n: number): number => {
    return factorial(n - 1);
};
"""
        ctx = self._create_context(code, "typescript", "test.ts")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
    
    def test_positive_case_java_method(self):
        """Test Java method with recursion, no base case."""
        code = """
public class Test {
    public int factorial(int n) {
        return factorial(n - 1);
    }
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
        assert finding.meta["language"] == "java"
    
    def test_positive_case_csharp_method(self):
        """Test C# method with recursion, no base case."""
        code = """
public class Calculator {
    public int Factorial(int n) {
        return Factorial(n - 1);
    }
}
"""
        ctx = self._create_context(code, "csharp", "Calculator.cs")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "Factorial"
    
    def test_positive_case_ruby_method(self):
        """Test Ruby method with recursion, no base case."""
        code = """
def factorial(n)
  factorial(n - 1)
end
"""
        ctx = self._create_context(code, "ruby", "test.rb")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
    
    def test_positive_case_go_function(self):
        """Test Go function with recursion, no base case."""
        code = """
func factorial(n int) int {
    return factorial(n - 1)
}
"""
        ctx = self._create_context(code, "go", "test.go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
    
    def test_positive_case_rust_function(self):
        """Test Rust function with recursion, no base case."""
        code = """
fn factorial(n: i32) -> i32 {
    factorial(n - 1)
}
"""
        ctx = self._create_context(code, "rust", "test.rs")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
    
    def test_positive_case_swift_function(self):
        """Test Swift function with recursion, no base case."""
        code = """
func factorial(n: Int) -> Int {
    return factorial(n - 1)
}
"""
        ctx = self._create_context(code, "swift", "test.swift")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
        assert finding.meta["function_name"] == "factorial"
    
    def test_negative_case_python_with_base_case(self):
        """Test Python function with proper base case (safe)."""
        code = """
def factorial(n):
    if n <= 0:
        return 1
    return n * factorial(n - 1)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_javascript_with_base_case(self):
        """Test JavaScript function with proper base case (safe)."""
        code = """
function factorial(n) {
    if (n === 0) {
        return 1;
    }
    return n * factorial(n - 1);
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_typescript_with_base_case(self):
        """Test TypeScript function with proper base case (safe)."""
        code = """
function sum(n: number): number {
    if (n === 0) {
        return 0;
    }
    return n + sum(n - 1);
}
"""
        ctx = self._create_context(code, "typescript", "test.ts")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_java_with_base_case(self):
        """Test Java method with proper base case (safe)."""
        code = """
public class Test {
    public int fibonacci(int n) {
        if (n <= 1) {
            return n;
        }
        return fibonacci(n - 1) + fibonacci(n - 2);
    }
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_csharp_with_base_case(self):
        """Test C# method with proper base case (safe)."""
        code = """
public class Calculator {
    public int Factorial(int n) {
        if (n == 0) return 1;
        return n * Factorial(n - 1);
    }
}
"""
        ctx = self._create_context(code, "csharp", "Calculator.cs")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_ruby_with_base_case(self):
        """Test Ruby method with proper base case (safe)."""
        code = """
def factorial(n)
  return 1 if n <= 0
  n * factorial(n - 1)
end
"""
        ctx = self._create_context(code, "ruby", "test.rb")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's a proper base case
        assert len(findings) == 0
    
    def test_negative_case_immediate_return(self):
        """Test function with immediate return (edge case)."""
        code = """
def simple_case(n):
    return 0  # Immediate return, no recursion risk
    return simple_case(n - 1)  # This would never be reached
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's an immediate return
        assert len(findings) == 0
    
    def test_negative_case_non_recursive_function(self):
        """Test function that doesn't call itself (safe)."""
        code = """
def calculate(n):
    result = n * 2
    helper_function(result)
    return result
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since there's no recursion
        assert len(findings) == 0
    
    def test_negative_case_different_function_call(self):
        """Test function that calls a different function with similar name (safe)."""
        code = """
def factorial(n):
    return factorial_helper(n)

def factorial_helper(n):
    if n <= 0:
        return 1
    return n * factorial_helper(n - 1)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since factorial calls factorial_helper, not itself
        assert len(findings) == 0
    
    def test_positive_case_guard_after_recursion(self):
        """Test function where guard appears after first recursive call (should warn)."""
        code = """
def bad_factorial(n):
    result = bad_factorial(n - 1)  # Recursion happens first
    if n <= 0:  # Guard is too late
        return 1
    return n * result
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have findings since the guard comes after recursion
        assert len(findings) >= 1
        finding = findings[0]
        assert "Recursive call without an explicit base-case/guard" in finding.message
    
    def test_positive_case_multiple_functions(self):
        """Test multiple functions in same file, some with issues."""
        code = """
def good_factorial(n):
    if n <= 0:
        return 1
    return n * good_factorial(n - 1)

def bad_factorial(n):
    return bad_factorial(n - 1)

def fibonacci(n):
    return fibonacci(n - 1) + fibonacci(n - 2)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should find issues with bad_factorial and fibonacci
        assert len(findings) >= 2
        
        function_names = {f.meta["function_name"] for f in findings}
        assert "bad_factorial" in function_names
        assert "fibonacci" in function_names
        assert "good_factorial" not in function_names
    
    def test_negative_case_comments_ignored(self):
        """Test that comments with recursive patterns are ignored."""
        code = """
# This is a bad example: def bad(n): return bad(n-1)
// Another comment: function bad(n) { return bad(n-1); }
/* Block comment with recursive pattern */

def good_function(n):
    if n <= 0:
        return 1
    return n * good_function(n - 1)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since the bad patterns are in comments
        assert len(findings) == 0
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = """
fun factorial(n: Int): Int {
    return factorial(n - 1)
}
"""
        ctx = self._create_context(code, "kotlin", "test.kt")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "python", "empty.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = "def bad(n):\n    return bad(n-1)"
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check finding properties
        assert finding.rule == "bug.recursion_no_base_case"
        assert finding.file == "test.py"
        assert finding.severity == "warning"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert "bad" in finding.meta["function_name"]
        assert finding.start_byte < finding.end_byte
    
    def test_nested_functions(self):
        """Test detection in nested function structures."""
        code = """
def outer():
    def inner(n):
        return inner(n - 1)  # Should be detected
    
    if True:
        return 0
    return outer()  # This has a guard, should not be detected
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the inner function issue but not outer
        assert len(findings) >= 1
        
        function_names = {f.meta["function_name"] for f in findings}
        assert "inner" in function_names
    
    def test_complex_base_case_patterns(self):
        """Test recognition of various base case patterns."""
        test_cases = [
            # Python patterns
            ("python", "def f(n):\n    if n <= 0: return 1\n    return f(n-1)"),
            ("python", "def f(arr):\n    if len(arr) == 0: return []\n    return f(arr[1:])"),
            ("python", "def f(x):\n    if x is None: return 0\n    return f(x.next)"),
            
            # JavaScript patterns  
            ("javascript", "function f(n) {\n    if (n === 0) return 1;\n    return f(n-1);\n}"),
            ("javascript", "function f(arr) {\n    if (arr.length == 0) return [];\n    return f(arr.slice(1));\n}"),
            ("javascript", "function f(x) {\n    if (x === null) return 0;\n    return f(x.next);\n}"),
            
            # Java patterns
            ("java", "int f(int n) {\n    if (n == 0) return 1;\n    return f(n-1);\n}"),
            ("java", "List f(List list) {\n    if (list.isEmpty()) return new ArrayList();\n    return f(list.subList(1, list.size()));\n}"),
        ]
        
        for language, code in test_cases:
            with self.subTest(language=language):
                ctx = self._create_context(code, language, f"test.{language}")
                findings = list(self.rule.visit(ctx))
                
                # All of these should have proper base cases
                assert len(findings) == 0, f"Expected no findings for {language} code with base case"


if __name__ == "__main__":
    unittest.main()

