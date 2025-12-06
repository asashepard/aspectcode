"""
Test suite for test.todo_comment rule.

Tests the detection of TODO/FIXME/SKIP comments in test files without assertions.
"""

import pytest
from unittest.mock import Mock
import tempfile
import os

# Import the rule
try:
    from rules.test_todo_comment import TestTodoCommentRule
    from engine.types import RuleContext, RuleMeta, Requires
except ImportError:
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from rules.test_todo_comment import TestTodoCommentRule
    from engine.types import RuleContext, RuleMeta, Requires


class TestTestTodoCommentRule:
    """Test suite for TestTodoCommentRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = TestTodoCommentRule()
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        meta = self.rule.meta
        assert meta.id == "test.todo_comment"
        assert meta.category == "test"
        assert meta.tier == 0
        assert meta.priority == "P2"
        assert meta.autofix_safety == "suggest-only"
        assert "python" in meta.langs
        assert "typescript" in meta.langs
        assert "javascript" in meta.langs
        assert "go" in meta.langs
        assert "java" in meta.langs
        
    def test_requires(self):
        """Test rule requirements."""
        requires = self.rule.requires
        assert requires.raw_text is True
        assert requires.syntax is False
    
    def test_is_test_file(self):
        """Test test file detection."""
        assert self.rule._is_test_file("/path/to/test_example.py")
        assert self.rule._is_test_file("/path/to/example_test.py") 
        assert self.rule._is_test_file("/path/to/tests.py")
        assert self.rule._is_test_file("/path/to/example.spec.js")
        assert self.rule._is_test_file("/path/to/test/example.py")
        assert not self.rule._is_test_file("/path/to/example.py")
        assert not self.rule._is_test_file("/path/to/main.js")
    
    def test_get_language_from_context(self):
        """Test language detection from context."""
        # Test with adapter
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "python"
        assert self.rule._get_language_from_context(ctx) == "python"
        
        # Test with file extension
        ctx = Mock()
        ctx.adapter = None
        ctx.file_path = "test.py"
        assert self.rule._get_language_from_context(ctx) == "python"
        
        ctx.file_path = "test.js"
        assert self.rule._get_language_from_context(ctx) == "javascript"
        
        ctx.file_path = "test.ts"
        assert self.rule._get_language_from_context(ctx) == "typescript"
    
    def test_python_todo_in_test_without_assertions(self):
        """Test Python test with TODO comment but no assertions."""
        code = '''
def test_something():
    # TODO: implement this test
    pass
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 1
        assert "TODO comment in test without assertions" in findings[0].message
        assert "implement this test" in findings[0].message
    
    def test_python_todo_with_assertions_allowed(self):
        """Test Python test with TODO comment but has assertions (should not flag)."""
        code = '''
def test_something():
    # TODO: add more test cases
    assert True
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0
    
    def test_python_skipped_test_with_todo_allowed(self):
        """Test Python skipped test with TODO (should not flag)."""
        code = '''
@pytest.mark.skip
def test_something():
    # TODO: fix this later
    pass
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0
    
    def test_javascript_todo_in_test_without_assertions(self):
        """Test JavaScript test with TODO comment but no assertions."""
        code = '''
test("something", () => {
    // TODO: implement test logic
    doSomeWork();
});
'''
        
        findings = list(self._run_rule(code, "test_example.js"))
        assert len(findings) == 1
        assert "TODO comment in test without assertions" in findings[0].message
        assert "implement test logic" in findings[0].message
    
    def test_javascript_todo_with_assertions_allowed(self):
        """Test JavaScript test with TODO but has assertions (should not flag)."""
        code = '''
test("something", () => {
    // TODO: test edge cases  
    expect(1).toBe(1);
});
'''
        
        findings = list(self._run_rule(code, "test_example.js"))
        assert len(findings) == 0
    
    def test_javascript_skipped_test_with_todo_allowed(self):
        """Test JavaScript skipped test with TODO (should not flag)."""
        code = '''
test.skip("something", () => {
    // TODO: fix this test
    doWork();
});
'''
        
        findings = list(self._run_rule(code, "test_example.js"))
        assert len(findings) == 0
    
    def test_go_todo_in_test_without_assertions(self):
        """Test Go test with TODO comment but no assertions."""
        code = '''
func TestSomething(t *testing.T) {
    // TODO: add test cases
    doWork()
}
'''
        
        findings = list(self._run_rule(code, "test_example.go"))
        assert len(findings) == 1
        assert "TODO comment in test without assertions" in findings[0].message
    
    def test_go_todo_with_assertions_allowed(self):
        """Test Go test with TODO but has assertions (should not flag)."""
        code = '''
func TestSomething(t *testing.T) {
    // TODO: refactor this
    t.Errorf("test")
}
'''
        
        findings = list(self._run_rule(code, "test_example.go"))
        assert len(findings) == 0
    
    def test_java_todo_in_test_without_assertions(self):
        """Test Java test with TODO comment but no assertions."""
        code = '''
@Test
public void testSomething() {
    // FIXME: needs implementation
    doWork();
}
'''
        
        findings = list(self._run_rule(code, "test_example.java"))
        assert len(findings) == 1
        assert "TODO comment in test without assertions" in findings[0].message
        assert "needs implementation" in findings[0].message
    
    def test_java_todo_with_assertions_allowed(self):
        """Test Java test with TODO but has assertions (should not flag)."""
        code = '''
@Test  
public void testSomething() {
    // TODO: add more assertions
    assertEquals(1, 1);
}
'''
        
        findings = list(self._run_rule(code, "test_example.java"))
        assert len(findings) == 0
    
    def test_multiple_todo_patterns(self):
        """Test detection of various TODO patterns."""
        code = '''
def test_one():
    # TODO: implement
    pass
    
def test_two():
    # FIXME: broken  
    pass
    
def test_three():
    # XXX: hack
    pass
    
def test_four():
    /* TODO: multiline comment */
    pass
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 4
        
        messages = [f.message for f in findings]
        assert any("implement" in msg for msg in messages)
        assert any("broken" in msg for msg in messages)
        assert any("hack" in msg for msg in messages)
    
    def test_non_test_file_ignored(self):
        """Test that non-test files are ignored."""
        code = '''
def regular_function():
    # TODO: implement
    pass
'''
        
        findings = list(self._run_rule(code, "regular_file.py"))
        assert len(findings) == 0
    
    def test_todo_outside_test_function_ignored(self):
        """Test that TODOs outside test functions are ignored."""
        code = '''
# TODO: global todo
import sys

def test_something():
    assert True
    
def helper_function():
    # TODO: implement helper
    pass
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0
    
    def test_python_function_body_extraction(self):
        """Test Python function body extraction."""
        code = '''
def test_something():
    # TODO: implement
    pass
    
def another_function():
    return True
'''
        
        test_functions = self.rule._find_test_functions(code, "python")
        assert len(test_functions) == 1
        assert "test_something" in test_functions[0]['name']
        assert "TODO: implement" in test_functions[0]['body']
        assert "another_function" not in test_functions[0]['body']
    
    def test_javascript_function_body_extraction(self):
        """Test JavaScript function body extraction."""
        code = '''
test("something", () => {
    // TODO: implement
    doWork();
});

function helper() {
    return true;
}
'''
        
        test_functions = self.rule._find_test_functions(code, "javascript")
        assert len(test_functions) == 1
        assert "TODO: implement" in test_functions[0]['body']
        assert "function helper" not in test_functions[0]['body']
    
    def test_nested_test_functions(self):
        """Test handling of nested test structures."""
        code = '''
describe("suite", () => {
    test("one", () => {
        // TODO: implement test one
        doWork();
    });
    
    test("two", () => {
        // TODO: implement test two
        expect(1).toBe(1);
    });
});
'''
        
        findings = list(self._run_rule(code, "test_example.js"))
        assert len(findings) == 1  # Only test one should be flagged (test two has assertion)
        assert "implement test one" in findings[0].message
    
    def test_case_insensitive_todo_detection(self):
        """Test case-insensitive TODO detection."""
        code = '''
def test_something():
    # todo: lowercase
    pass
    
def test_another():
    # TODO: uppercase
    pass
    
def test_mixed():
    # FiXmE: mixed case
    pass
'''
        
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 3
    
    def test_complex_assertion_patterns(self):
        """Test detection of various assertion patterns."""
        # Python
        python_code = '''
def test_with_assert():
    # TODO: more cases
    assert True
    
def test_with_self_assert():
    # TODO: more cases
    self.assertEqual(1, 1)
    
def test_with_pytest():
    # TODO: more cases  
    pytest.raises(ValueError)
'''
        
        findings = list(self._run_rule(python_code, "test_example.py"))
        assert len(findings) == 0
        
        # JavaScript
        js_code = '''
test("with expect", () => {
    // TODO: more cases
    expect(1).toBe(1);
});

test("with should", () => {
    // TODO: more cases
    result.should.equal(1);
});
'''
        
        findings = list(self._run_rule(js_code, "test_example.js"))
        assert len(findings) == 0
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty test function
        code = '''
def test_empty():
    pass
'''
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0  # No TODO comment, so no violation
        
        # Test with only whitespace
        code = '''
def test_whitespace():
    
    
'''
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0
        
        # Test with TODO in string literal (should NOT be detected as it's not a comment)
        code = '''
def test_todo_in_string():
    message = "TODO: this is in a string"
    pass
'''
        findings = list(self._run_rule(code, "test_example.py"))
        assert len(findings) == 0  # Should NOT be detected as our rule only looks for comments
    
    def _run_rule(self, code: str, filename: str):
        """Helper method to run rule on code."""
        # Create mock context
        ctx = Mock()
        ctx.text = code
        ctx.file_path = filename
        ctx.adapter = None
        
        return self.rule.visit(ctx)


if __name__ == "__main__":
    # Run tests directly
    test_instance = TestTestTodoCommentRule()
    
    # Test basic functionality
    test_instance.setup_method()
    test_instance.test_rule_metadata()
    test_instance.test_python_todo_in_test_without_assertions()
    test_instance.test_javascript_todo_in_test_without_assertions()
    test_instance.test_java_todo_in_test_without_assertions()
    
    print("✅ All tests passed!")

