"""
Tests for Operator Precedence Risk Detection Rule

Tests various scenarios where operator precedence might cause confusion
and verifies that the rule correctly identifies risky patterns while
avoiding false positives on safely parenthesized expressions.
"""

import unittest
from unittest.mock import Mock
from rules.bug_operator_precedence_risky import BugOperatorPrecedenceRiskyRule
from engine.types import RuleContext


class TestBugOperatorPrecedenceRiskyRule(unittest.TestCase):
    """Test cases for the operator precedence risk detection rule."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugOperatorPrecedenceRiskyRule()
    
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
        assert self.rule.meta.id == "bug.operator_precedence_risky"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.tier == 0
        
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires syntax analysis."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_logical_mix_javascript(self):
        """Test JavaScript mixed logical operators without parentheses."""
        code = """
function test() {
    if (condition && flag || other) {
        return true;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Mixed && and || operators" in finding.message
        assert finding.severity == "info"
        assert finding.meta["pattern_type"] == "logical_mix"
        assert finding.meta["language"] == "javascript"
    
    def test_positive_case_nullish_mix_typescript(self):
        """Test TypeScript nullish coalescing mixed with logical operators."""
        code = """
const value = a ?? b || c;
"""
        ctx = self._create_context(code, "typescript", "test.ts")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Nullish coalescing" in finding.message
        assert finding.meta["pattern_type"] == "nullish_mix"
    
    def test_positive_case_bitwise_compare_c(self):
        """Test C bitwise operation with comparison without parentheses."""
        code = """
int main() {
    if (x & MASK == 0) {
        return 1;
    }
}
"""
        ctx = self._create_context(code, "c", "test.c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Bitwise operation combined with comparison" in finding.message
        assert finding.meta["pattern_type"] == "bitwise_compare"
    
    def test_positive_case_shift_arithmetic_cpp(self):
        """Test C++ shift operation mixed with arithmetic."""
        code = """
int calculate() {
    auto result = x << y + z;
    return result;
}
"""
        ctx = self._create_context(code, "cpp", "test.cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Shift operation mixed with arithmetic" in finding.message
        assert finding.meta["pattern_type"] == "shift_arithmetic"
    
    def test_positive_case_chained_compare_java(self):
        """Test Java chained comparison operators."""
        code = """
public class Test {
    public boolean check() {
        return a < b < c;
    }
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Chained comparison operators" in finding.message
        assert finding.meta["pattern_type"] == "chained_compare"
    
    def test_positive_case_python_not_membership(self):
        """Test Python 'not x in y' pattern."""
        code = """
def check_item():
    if not item in collection:
        return False
    return True
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "not in" in finding.message or "is not" in finding.message
        assert finding.meta["pattern_type"] == "python_not_membership"
    
    def test_positive_case_ruby_mixed_logical(self):
        """Test Ruby mixing 'and/or' with '&&/||'."""
        code = """
def check_conditions
  result = condition and flag || other
  return result
end
"""
        ctx = self._create_context(code, "ruby", "test.rb")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Mixed 'and/or' with '&&/||'" in finding.message
        assert finding.meta["pattern_type"] == "ruby_mixed_logical"
    
    def test_negative_case_safely_parenthesized_javascript(self):
        """Test JavaScript with safely parenthesized expressions."""
        code = """
function test() {
    if ((condition && flag) || other) {
        return true;
    }
    
    const value = (a ?? b) || c;
    
    if ((x & MASK) == 0) {
        return false;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since expressions are properly parenthesized
        assert len(findings) == 0
    
    def test_negative_case_python_correct_membership(self):
        """Test Python with correct membership operators."""
        code = """
def check_item():
    if item not in collection:
        return False
    
    if item is not None:
        return True
        
    return False
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since operators are used correctly
        assert len(findings) == 0
    
    def test_negative_case_comment_lines_ignored(self):
        """Test that comments are ignored."""
        code = """
// This has risky operators: a && b || c
/* Another comment with x & MASK == 0 */
function safe() {
    return true;
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since risky patterns are in comments
        assert len(findings) == 0
    
    def test_negative_case_chaining_languages(self):
        """Test that chained comparisons are allowed in Python."""
        code = """
def check_range(x):
    return 0 < x < 10
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Python supports chained comparisons, so no finding expected
        chained_findings = [f for f in findings if f.meta.get("pattern_type") == "chained_compare"]
        assert len(chained_findings) == 0
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = """
// This would be risky in supported languages
if (a && b || c) { return true; }
"""
        ctx = self._create_context(code, "fortran", "test.f90")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "javascript", "empty.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = "if (a && b || c) { return true; }"
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check finding properties
        assert finding.rule == "bug.operator_precedence_risky"
        assert finding.file == "test.js"
        assert finding.severity == "info"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert finding.meta["suggestion"] == "Add explicit parentheses to clarify operator grouping"
        assert finding.start_byte < finding.end_byte
    
    def test_multiple_patterns_in_single_file(self):
        """Test detection of multiple different patterns in one file."""
        code = """
function multipleIssues() {
    // Mixed logical operators
    if (a && b || c) {
        console.log("logical mix");
    }
    
    // Nullish with logical
    const value = x ?? y || z;
    
    // Bitwise with comparison
    if (flags & MASK == 0) {
        console.log("bitwise");
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should detect multiple different pattern types
        assert len(findings) >= 3
        
        pattern_types = {f.meta["pattern_type"] for f in findings}
        assert "logical_mix" in pattern_types
        assert "nullish_mix" in pattern_types
        assert "bitwise_compare" in pattern_types


if __name__ == "__main__":
    unittest.main()

