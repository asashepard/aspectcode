"""
Tests for bug_assignment_in_conditional rule.

Tests the detection of assignment operators in conditional statements across
multiple languages including positive cases (should detect) and negative cases (should not detect).
"""

import pytest
from unittest.mock import Mock
from rules.bug_assignment_in_conditional import BugAssignmentInConditionalRule
from engine.types import RuleContext, Finding


class TestBugAssignmentInConditionalRule:
    """Test suite for the BugAssignmentInConditionalRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = BugAssignmentInConditionalRule()
    
    def _create_context(self, code: str, language: str = "c") -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.file_path = f"test.{language}"
        context.tree = None  # Not used by this rule
        context.adapter = None  # Not used by this rule
        context.config = {}
        context.scopes = None
        context.project_graph = None
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.assignment_in_conditional"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.autofix_safety == "safe"
        assert set(self.rule.meta.langs) == {"c", "cpp", "java", "csharp", "javascript", "typescript"}
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
    
    # POSITIVE CASES - Should detect assignment in conditionals
    
    def test_c_positive_case_if_statement(self):
        """Test C code with assignment in if statement."""
        code = """int main() {
    int x, y = 5;
    if (x = y) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Assignment used in conditional" in finding.message
        assert finding.severity == "error"
        # Check that the finding points to the '=' character
        assert code[finding.start_byte:finding.end_byte] == "="
    
    def test_cpp_positive_case_while_statement(self):
        """Test C++ code with assignment in while statement."""
        code = """void test() {
    int a, next = 1;
    while (a = next) {
        break;
    }
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Assignment used in conditional" in finding.message
    
    def test_java_positive_case_for_statement(self):
        """Test Java code with assignment in for statement condition."""
        code = """public class Test {
    public void method() {
        int i, n = 5;
        for (int j = 0; i = n; j++) {
            System.out.println(i);
        }
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Assignment used in conditional" in finding.message
    
    def test_javascript_positive_case(self):
        """Test JavaScript code with assignment in while statement."""
        code = """function test() {
    let a, next = 1;
    while (a = next) {
        break;
    }
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Assignment used in conditional" in finding.message
    
    def test_typescript_positive_case(self):
        """Test TypeScript code with assignment in if statement."""
        code = """function test(): number {
    let x: number, y: number = 5;
    if (x = y) {
        return x;
    }
    return 0;
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Assignment used in conditional" in finding.message
    
    # NEGATIVE CASES - Should NOT detect (legitimate patterns)
    
    def test_c_negative_case_equality_comparison(self):
        """Test C code with proper equality comparison."""
        code = """int main() {
    int x = 5, y = 5;
    if (x == y) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_c_negative_case_assignment_in_comparison_idiom(self):
        """Test C code with assignment-in-comparison idiom (should not flag)."""
        code = """int main() {
    int ch;
    while ((ch = getchar()) != EOF) {
        putchar(ch);
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag this common C idiom
        assert len(findings) == 0
    
    def test_cpp_negative_case_compound_operators(self):
        """Test C++ code with compound assignment operators."""
        code = """void test() {
    int x = 10, y = 5;
    if (x <= y) return;
    if (x >= y) return;
    if (x != y) return;
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_javascript_negative_case_strict_equality(self):
        """Test JavaScript code with strict equality."""
        code = """function test() {
    let a = 5, b = 5;
    if (a === b) {
        console.log("strictly equal");
    }
    if (a !== b) {
        console.log("not strictly equal");
    }
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_typescript_negative_case_assignment_with_comparison(self):
        """Test TypeScript code with assignment inside comparison (should not flag)."""
        code = """function test() {
    let n: number;
    for (; (n = iter()) !== null; ) {
        console.log(n);
    }
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag because there's a comparison operator
        assert len(findings) == 0
    
    def test_arrow_function_not_flagged(self):
        """Test that arrow functions are not flagged."""
        code = """const fn = (x) => x * 2;
if (fn(5) == 10) {
    console.log("correct");
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    # AUTOFIX TESTS
    
    def test_autofix_functionality(self):
        """Test that autofix data is generated correctly."""
        code = """if (x = y) {
    console.log("test");
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        assert finding.autofix[0].replacement == "=="
    
    def test_autofix_application(self):
        """Test applying autofix to replace = with ==."""
        code = "if (x = y) { do_something(); }"
        expected = "if (x == y) { do_something(); }"
        
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Apply the autofix
        edit = finding.autofix[0]
        fixed_code = code[:edit.start_byte] + edit.replacement + code[edit.end_byte:]
        assert fixed_code == expected
    
    def test_autofix_idempotency(self):
        """Test that applying autofix twice doesn't change the result."""
        code = "if (x = y) { return; }"
        
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Apply autofix once
        edit = finding.autofix[0]
        fixed_once = code[:edit.start_byte] + edit.replacement + code[edit.end_byte:]
        
        # Check that no more issues are found in fixed code
        ctx_fixed = self._create_context(fixed_once, "c")
        findings_after_fix = list(self.rule.visit(ctx_fixed))
        
        assert len(findings_after_fix) == 0  # No more issues should be found
    
    # EDGE CASES
    
    def test_multiple_assignments_in_condition(self):
        """Test condition with multiple assignment operators."""
        code = """if (x = y = z) {
    return 1;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should detect at least one problematic assignment
        assert len(findings) >= 1
    
    def test_nested_conditionals(self):
        """Test nested conditional statements."""
        code = """if (x == y) {
    if (a = b) {
        return 1;
    }
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the inner assignment but not the outer comparison
        assert len(findings) == 1
    
    def test_complex_expression_with_assignment(self):
        """Test complex expressions containing assignment."""
        code = """if ((x = getValue()) && (y == 10)) {
    process(x, y);
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the assignment in the complex expression
        assert len(findings) >= 1
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_positions(self):
        """Test that findings have correct byte positions."""
        code = "if (x = y) { return; }"
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        
        # The finding should point to the '=' character
        problem_char = code[finding.start_byte:finding.end_byte]
        assert problem_char == "="
    
    def test_whitespace_handling(self):
        """Test handling of various whitespace patterns."""
        code = """if(x=y){
    return 1;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert code[finding.start_byte:finding.end_byte] == "="

