import os
import sys
import pytest
import tempfile
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from rules.test_no_assertions import TestNoAssertionsRule
from engine.types import RuleContext


class MockRuleContext:
    """Mock context for testing."""
    def __init__(self, text: str, file_path: str = "test.py"):
        self.text = text
        self.file_path = file_path


class TestTestNoAssertionsRule:
    """Test suite for test.no_assertions rule."""
    
    @pytest.fixture
    def rule(self):
        return TestNoAssertionsRule()
    
    # Python Tests
    def test_python_test_without_assertions_flagged(self, rule):
        """Python test function without assertions should be flagged."""
        code = '''
def test_something():
    result = do_work()
    process_result(result)
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_python_test_with_assert_not_flagged(self, rule):
        """Python test with assert statement should not be flagged."""
        code = '''
def test_something():
    result = do_work()
    assert result == expected
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_test_with_pytest_raises_not_flagged(self, rule):
        """Python test with pytest.raises should not be flagged."""
        code = '''
def test_exception():
    with pytest.raises(ValueError):
        do_invalid_work()
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_skipped_test_not_flagged(self, rule):
        """Python skipped test should not be flagged."""
        code = '''
@pytest.mark.skip
def test_something():
    pass
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_python_non_test_function_ignored(self, rule):
        """Non-test Python function should be ignored."""
        code = '''
def helper_function():
    do_work()
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # JavaScript/TypeScript Tests
    def test_js_test_without_assertions_flagged(self, rule):
        """JavaScript test without assertions should be flagged."""
        code = '''
test("should do something", () => {
    const result = doWork();
    processResult(result);
});
'''
        ctx = MockRuleContext(code, "test.spec.js")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_js_test_with_expect_not_flagged(self, rule):
        """JavaScript test with expect should not be flagged."""
        code = '''
test("should do something", () => {
    const result = doWork();
    expect(result).toBe(42);
});
'''
        ctx = MockRuleContext(code, "test.spec.js")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_js_skipped_test_not_flagged(self, rule):
        """JavaScript skipped test should not be flagged."""
        code = '''
test.skip("not implemented yet", () => {
    // TODO: implement
});
'''
        ctx = MockRuleContext(code, "test.spec.js")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_ts_test_with_assertions_not_flagged(self, rule):
        """TypeScript test with assertions should not be flagged."""
        code = '''
it("should handle types correctly", () => {
    const value: string = getValue();
    expect(value).toEqual("expected");
});
'''
        ctx = MockRuleContext(code, "test.spec.ts")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Go Tests
    def test_go_test_without_assertions_flagged(self, rule):
        """Go test without assertions should be flagged."""
        code = '''
func TestSomething(t *testing.T) {
    result := doWork()
    processResult(result)
}
'''
        ctx = MockRuleContext(code, "test_file_test.go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_go_test_with_assertions_not_flagged(self, rule):
        """Go test with assertions should not be flagged."""
        code = '''
func TestSomething(t *testing.T) {
    result := doWork()
    if result != expected {
        t.Errorf("Expected %v, got %v", expected, result)
    }
}
'''
        ctx = MockRuleContext(code, "test_file_test.go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_go_test_with_skip_not_flagged(self, rule):
        """Go test that skips should not be flagged."""
        code = '''
func TestSomething(t *testing.T) {
    t.Skip("Not implemented yet")
}
'''
        ctx = MockRuleContext(code, "test_file_test.go")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Java Tests
    def test_java_test_without_assertions_flagged(self, rule):
        """Java test without assertions should be flagged."""
        code = '''
@Test
public void testSomething() {
    Object result = doWork();
    processResult(result);
}
'''
        ctx = MockRuleContext(code, "TestFile.java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_java_test_with_assertions_not_flagged(self, rule):
        """Java test with assertions should not be flagged."""
        code = '''
@Test
public void testSomething() {
    Object result = doWork();
    assertEquals(expected, result);
}
'''
        ctx = MockRuleContext(code, "TestFile.java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_java_ignored_test_not_flagged(self, rule):
        """Java ignored test should not be flagged."""
        code = '''
@Ignore
@Test
public void testSomething() {
    // Not implemented
}
'''
        ctx = MockRuleContext(code, "TestFile.java")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # C# Tests
    def test_csharp_test_without_assertions_flagged(self, rule):
        """C# test without assertions should be flagged."""
        code = '''
[Test]
public void TestSomething()
{
    var result = DoWork();
    ProcessResult(result);
}
'''
        ctx = MockRuleContext(code, "TestFile.cs")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_csharp_test_with_assertions_not_flagged(self, rule):
        """C# test with assertions should not be flagged."""
        code = '''
[Fact]
public void TestSomething()
{
    var result = DoWork();
    Assert.Equal(expected, result);
}
'''
        ctx = MockRuleContext(code, "TestFile.cs")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # C++ Tests
    def test_cpp_test_without_assertions_flagged(self, rule):
        """C++ test without assertions should be flagged."""
        code = '''
TEST(TestSuite, TestCase) {
    auto result = doWork();
    processResult(result);
}
'''
        ctx = MockRuleContext(code, "test_file.cpp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_cpp_test_with_assertions_not_flagged(self, rule):
        """C++ test with assertions should not be flagged."""
        code = '''
TEST(TestSuite, TestCase) {
    auto result = doWork();
    EXPECT_EQ(expected, result);
}
'''
        ctx = MockRuleContext(code, "test_file.cpp")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Ruby Tests
    def test_ruby_test_without_assertions_flagged(self, rule):
        """Ruby test without assertions should be flagged."""
        code = '''
it "should do something" do
    result = do_work
    process_result(result)
end
'''
        ctx = MockRuleContext(code, "test_file_spec.rb")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_ruby_test_with_assertions_not_flagged(self, rule):
        """Ruby test with assertions should not be flagged."""
        code = '''
it "should do something" do
    result = do_work
    expect(result).to eq(expected)
end
'''
        ctx = MockRuleContext(code, "test_file_spec.rb")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Rust Tests
    def test_rust_test_without_assertions_flagged(self, rule):
        """Rust test without assertions should be flagged."""
        code = '''
#[test]
fn test_something() {
    let result = do_work();
    process_result(result);
}
'''
        ctx = MockRuleContext(code, "lib.rs")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_rust_test_with_assertions_not_flagged(self, rule):
        """Rust test with assertions should not be flagged."""
        code = '''
#[test]
fn test_something() {
    let result = do_work();
    assert_eq!(result, expected);
}
'''
        ctx = MockRuleContext(code, "lib.rs")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_rust_ignored_test_not_flagged(self, rule):
        """Rust ignored test should not be flagged."""
        code = '''
#[test]
#[ignore]
fn test_something() {
    // Not implemented
}
'''
        ctx = MockRuleContext(code, "lib.rs")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Swift Tests
    def test_swift_test_without_assertions_flagged(self, rule):
        """Swift test without assertions should be flagged."""
        code = '''
func testSomething() {
    let result = doWork()
    processResult(result)
}
'''
        ctx = MockRuleContext(code, "TestFile.swift")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_swift_test_with_assertions_not_flagged(self, rule):
        """Swift test with assertions should not be flagged."""
        code = '''
func testSomething() {
    let result = doWork()
    XCTAssertEqual(result, expected)
}
'''
        ctx = MockRuleContext(code, "TestFile.swift")
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # Edge Cases
    def test_multiple_test_functions_mixed(self, rule):
        """File with multiple test functions, some with and some without assertions."""
        code = '''
def test_with_assertion():
    result = do_work()
    assert result == expected

def test_without_assertion():
    result = do_work()
    process_result(result)

def test_with_different_assertion():
    with pytest.raises(ValueError):
        do_invalid_work()
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        # Only the middle function should be flagged
        assert len(findings) == 1
    
    def test_empty_test_function_flagged(self, rule):
        """Empty test function should be flagged."""
        code = '''
def test_empty():
    pass
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_test_with_only_comments_flagged(self, rule):
        """Test with only comments should be flagged."""
        code = '''
def test_commented():
    # TODO: implement this test
    # result = do_work()
    # assert result == expected
'''
        ctx = MockRuleContext(code, "test_file.py")
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "no assertions" in findings[0].message
    
    def test_nested_test_functions_js(self, rule):
        """Nested test functions in JavaScript should be handled."""
        code = '''
describe("Feature", () => {
    test("should work", () => {
        const result = doWork();
        expect(result).toBe(true);
    });
    
    test("should handle edge case", () => {
        const result = doEdgeCase();
        // Missing assertion
    });
});
'''
        ctx = MockRuleContext(code, "test.spec.js")
        findings = list(rule.visit(ctx))
        # Should find the test without assertion
        assert len(findings) >= 1
        assert "no assertions" in findings[0].message
    
    def test_language_detection_from_extension(self, rule):
        """Rule should correctly detect language from file extension."""
        python_code = 'def test_something(): pass'
        js_code = 'test("something", () => {});'
        
        python_ctx = MockRuleContext(python_code, "test.py")
        js_ctx = MockRuleContext(js_code, "test.js")
        
        python_findings = list(rule.visit(python_ctx))
        js_findings = list(rule.visit(js_ctx))
        
        # Both should find issues but handle them appropriately for their language
        assert len(python_findings) == 1
        assert len(js_findings) == 1
    
    # Metadata Tests
    def test_rule_metadata(self, rule):
        """Test rule metadata is correct."""
        assert rule.meta.id == "test.no_assertions"
        assert rule.meta.category == "test"
        assert rule.meta.tier == 0
        assert rule.meta.priority == "P1"
        assert len(rule.meta.langs) == 11  # 11 supported languages
        assert "python" in rule.meta.langs
        assert "typescript" in rule.meta.langs
        assert "go" in rule.meta.langs
    
    def test_requires_syntax(self, rule):
        """Test rule requires syntax analysis."""
        assert rule.requires.syntax is True

