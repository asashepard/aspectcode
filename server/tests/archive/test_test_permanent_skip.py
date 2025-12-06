import os
import sys
import pytest
import tempfile
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rules.test_permanent_skip import TestPermanentSkipRule
from engine.types import RuleContext


class MockAdapter:
    """Simple mock adapter for text-based rules."""
    def __init__(self, text: str, language: str = "python"):
        self.text = text
        self.language_id = language


class MockRuleContext:
    """Mock context for testing."""
    def __init__(self, text: str, file_path: str = "test.py", language: str = "python"):
        self.text = text
        self.file_path = file_path
        self.adapter = MockAdapter(text, language)


class TestTestPermanentSkipRule:
    """Test suite for test.permanent_skip rule."""
    
    @pytest.fixture
    def rule(self):
        return TestPermanentSkipRule()
    
    # Python Tests - Positive Cases (should be flagged)
    def test_python_skip_without_justification_flagged(self, rule):
        """Python test with skip but no justification should be flagged."""
        code = '''
import pytest

@pytest.mark.skip(reason="flaky")
def test_something():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_python_xfail_without_justification_flagged(self, rule):
        """Python test with xfail but no justification should be flagged."""
        code = '''
import pytest

@pytest.mark.xfail(reason="broken")
def test_broken():
    assert False
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_python_unittest_skip_without_justification_flagged(self, rule):
        """Python unittest skip without justification should be flagged."""
        code = '''
import unittest

@unittest.skip("temporarily disabled")
def test_temp():
    self.assertTrue(True)
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    # Python Tests - Negative Cases (should NOT be flagged)
    def test_python_skip_with_ticket_not_flagged(self, rule):
        """Python test with ticket reference should not be flagged."""
        code = '''
import pytest

@pytest.mark.skip(reason="TICKET-123 flaky test")
def test_something():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_skip_with_expiry_not_flagged(self, rule):
        """Python test with expiry date should not be flagged."""
        code = '''
import pytest

@pytest.mark.skip(reason="broken expires=2025-12-31")
def test_broken():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_skip_with_bug_reference_not_flagged(self, rule):
        """Python test with BUG reference should not be flagged."""
        code = '''
import pytest

@pytest.mark.skip(reason="BUG:456 race condition")
def test_race():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_skip_with_url_not_flagged(self, rule):
        """Python test with URL reference should not be flagged."""
        code = '''
import pytest

@pytest.mark.skip(reason="https://github.com/org/repo/issues/123")
def test_github_issue():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # JavaScript/TypeScript Tests
    def test_js_test_skip_without_justification_flagged(self, rule):
        """JavaScript test.skip without justification should be flagged."""
        code = '''
test.skip("temporarily disabled", () => {
    expect(1).toBe(1);
});
'''
        ctx = MockRuleContext(code, "test.spec.js", "javascript")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_js_it_skip_without_justification_flagged(self, rule):
        """JavaScript it.skip without justification should be flagged."""
        code = '''
it.skip("broken test", () => {
    expect(doWork()).toBe(42);
});
'''
        ctx = MockRuleContext(code, "test.spec.js", "javascript")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_js_xit_without_justification_flagged(self, rule):
        """JavaScript xit without justification should be flagged."""
        code = '''
xit("not working", () => {
    expect(true).toBe(false);
});
'''
        ctx = MockRuleContext(code, "test.spec.js", "javascript")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_ts_test_skip_with_ticket_not_flagged(self, rule):
        """TypeScript test.skip with ticket should not be flagged."""
        code = '''
test.skip("TICKET-789 blocked by API", () => {
    expect(apiCall()).toBe("success");
});
'''
        ctx = MockRuleContext(code, "test.spec.ts", "typescript")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_js_skip_with_expiry_not_flagged(self, rule):
        """JavaScript skip with expiry should not be flagged."""
        code = '''
it.skip("expires=2026-01-01 waiting for fix", () => {
    expect(buggyFunction()).toBe(true);
});
'''
        ctx = MockRuleContext(code, "test.spec.js", "javascript")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Java Tests
    def test_java_ignore_without_justification_flagged(self, rule):
        """Java @Ignore without justification should be flagged."""
        code = '''
@org.junit.Ignore
public void testSomething() {
    assertEquals(1, 1);
}
'''
        ctx = MockRuleContext(code, "TestFile.java", "java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_java_disabled_without_justification_flagged(self, rule):
        """Java @Disabled without justification should be flagged."""
        code = '''
@org.junit.jupiter.api.Disabled
void testBroken() {
    assertTrue(false);
}
'''
        ctx = MockRuleContext(code, "TestFile.java", "java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_java_disabled_with_url_not_flagged(self, rule):
        """Java @Disabled with URL should not be flagged."""
        code = '''
@org.junit.jupiter.api.Disabled("https://tracker/issue/123")
void testBlocked() {
    assertTrue(true);
}
'''
        ctx = MockRuleContext(code, "TestFile.java", "java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_java_ignore_with_jira_not_flagged(self, rule):
        """Java @Ignore with JIRA reference should not be flagged."""
        code = '''
@org.junit.Ignore("JIRA-456 waiting for upstream fix")
public void testUpstream() {
    assertEquals(42, getAnswer());
}
'''
        ctx = MockRuleContext(code, "TestFile.java", "java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Go Tests
    def test_go_skip_without_justification_flagged(self, rule):
        """Go t.Skip without justification should be flagged."""
        code = '''
func TestSomething(t *testing.T) {
    t.Skip("temporary")
}
'''
        ctx = MockRuleContext(code, "test_file_test.go", "go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_go_skip_with_issue_not_flagged(self, rule):
        """Go t.Skip with ISSUE reference should not be flagged."""
        code = '''
func TestBlocked(t *testing.T) {
    t.Skip("ISSUE:789 blocked by external dependency")
}
'''
        ctx = MockRuleContext(code, "test_file_test.go", "go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_go_skip_with_until_date_not_flagged(self, rule):
        """Go t.Skip with until date should not be flagged."""
        code = '''
func TestTemporary(t *testing.T) {
    t.SkipNow("until=2025-11-15 waiting for server update")
}
'''
        ctx = MockRuleContext(code, "test_file_test.go", "go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # C# Tests
    def test_csharp_ignore_without_justification_flagged(self, rule):
        """C# [Ignore] without justification should be flagged."""
        code = '''
[Ignore]
public void TestSomething() {
    Assert.AreEqual(1, 1);
}
'''
        ctx = MockRuleContext(code, "TestFile.cs", "csharp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_csharp_fact_skip_with_ticket_not_flagged(self, rule):
        """C# [Fact(Skip=...)] with ticket should not be flagged."""
        code = '''
[Fact(Skip="TICKET-9 until=2025-10-10")]
public void TestBlocked() {
    Assert.True(true);
}
'''
        ctx = MockRuleContext(code, "TestFile.cs", "csharp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # C/C++ Tests
    def test_cpp_disabled_test_without_justification_flagged(self, rule):
        """C++ DISABLED_ test without justification should be flagged."""
        code = '''
TEST(DISABLED_MySuite, MyCase) {
    EXPECT_EQ(1, 1);
}
'''
        ctx = MockRuleContext(code, "test_file.cpp", "cpp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_cpp_gtest_skip_with_ticket_not_flagged(self, rule):
        """C++ GTEST_SKIP with ticket should not be flagged."""
        code = '''
TEST(MySuite, MyCase) {
    GTEST_SKIP() << "TICKET-5 broken on Windows";
}
'''
        ctx = MockRuleContext(code, "test_file.cpp", "cpp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Rust Tests
    def test_rust_ignore_without_justification_flagged(self, rule):
        """Rust #[ignore] without justification should be flagged."""
        code = '''
#[ignore]
fn test_broken() {
    assert_eq!(1, 1);
}
'''
        ctx = MockRuleContext(code, "lib.rs", "rust")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_rust_ignore_with_expiry_not_flagged(self, rule):
        """Rust #[ignore] with expiry should not be flagged."""
        code = '''
#[ignore] // expires=2025-12-01 waiting for feature
fn test_future_feature() {
    assert!(false);
}
'''
        ctx = MockRuleContext(code, "lib.rs", "rust")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Edge Cases
    def test_multiple_skipped_tests_mixed(self, rule):
        """File with multiple skipped tests, some justified and some not."""
        code = '''
import pytest

@pytest.mark.skip(reason="TICKET-123 flaky")
def test_justified():
    assert True

@pytest.mark.skip(reason="broken")
def test_unjustified():
    assert True

@pytest.mark.skip(reason="expires=2025-12-31")
def test_with_expiry():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        # Only the middle test should be flagged
        assert len(findings) == 1
        assert "ticket or expiry" in findings[0].message
    
    def test_non_test_function_ignored(self, rule):
        """Non-test functions with decorators should be ignored."""
        code = '''
import pytest

@pytest.mark.skip(reason="not a test")
def helper_function():
    return 42
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        # Should not flag non-test functions
        assert len(findings) == 0
    
    def test_date_patterns_recognized(self, rule):
        """Various date patterns should be recognized as valid expiry."""
        code = '''
import pytest

@pytest.mark.skip(reason="broken until 2025-01-15")
def test_date1():
    assert True

@pytest.mark.skip(reason="expires 2026-12-31")
def test_date2():
    assert True

@pytest.mark.skip(reason="expiry=2025-06-01")
def test_date3():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        # All should be recognized as justified
        assert len(findings) == 0
    
    def test_various_ticket_patterns_recognized(self, rule):
        """Various ticket reference patterns should be recognized."""
        code = '''
import pytest

@pytest.mark.skip(reason="TICKET-123")
def test_ticket():
    assert True

@pytest.mark.skip(reason="BUG:456")
def test_bug():
    assert True

@pytest.mark.skip(reason="ISSUE:789")
def test_issue():
    assert True

@pytest.mark.skip(reason="see JIRA ABC-123")
def test_jira():
    assert True
'''
        ctx = MockRuleContext(code, "test_file.py", "python")
        findings = list(rule.visit(ctx))
        # All should be recognized as justified
        assert len(findings) == 0
    
    def test_language_detection_from_extension(self, rule):
        """Rule should correctly detect language from file extension."""
        python_code = '@pytest.mark.skip(reason="flaky")\ndef test_something(): pass'
        js_code = 'test.skip("broken", () => {});'
        
        python_ctx = MockRuleContext(python_code, "test.py", "python")
        js_ctx = MockRuleContext(js_code, "test.js", "javascript")
        
        python_findings = list(rule.visit(python_ctx))
        js_findings = list(rule.visit(js_ctx))
        
        # Both should find issues since they lack justification
        assert len(python_findings) == 1
        assert len(js_findings) == 1
    
    # Metadata Tests
    def test_rule_metadata(self, rule):
        """Test rule metadata is correct."""
        assert rule.meta.id == "test.permanent_skip"
        assert rule.meta.category == "test"
        assert rule.meta.tier == 0  # Text-based analysis
        assert rule.meta.priority == "P2"
        assert rule.meta.autofix_safety == "suggest-only"
        assert len(rule.meta.langs) == 11  # 11 supported languages
        assert "python" in rule.meta.langs
        assert "typescript" in rule.meta.langs
        assert "go" in rule.meta.langs
        assert "java" in rule.meta.langs
    
    def test_requires_syntax(self, rule):
        """Test that rule doesn't require syntax analysis."""
        assert rule.requires.syntax is False

