"""Tests for test_brittle_time_dependent rule."""

import pytest
from typing import List

try:
    from ..rules.test_brittle_time_dependent import TestBrittleTimeDependentRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.test_brittle_time_dependent import TestBrittleTimeDependentRule
    from engine.types import RuleContext, Finding


class MockAdapter:
    """Mock adapter for testing syntax-based rules."""
    def __init__(self, language_id: str):
        self.language_id = language_id


class MockNode:
    """Mock tree-sitter node for testing."""
    def __init__(self, node_type: str = "", text: str = "", start_byte: int = 0, end_byte: int = 0, children=None, parent=None, **kwargs):
        self.type = node_type
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte > start_byte else start_byte + len(text)
        self.children = children or []
        self.parent = parent
        
        # Set additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Set parent references for children
        for child in self.children:
            child.parent = self


class MockTree:
    """Mock syntax tree."""
    def __init__(self, root_node):
        self.root_node = root_node
        
    def node_span(self, node):
        """Return node span."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 10))


class MockRuleContext:
    """Mock context for testing."""
    def __init__(self, code: str, file_path: str, language: str):
        self.text = code
        self.file_path = file_path
        self.language = language
        self.adapter = MockAdapter(language)
        self.syntax = MockTree(self._create_mock_tree(code, language))
    
    def _create_mock_tree(self, code: str, language: str):
        """Create a mock syntax tree based on the code and language."""
        # Create appropriate nodes based on the code content and language
        
        if language == "python" and "def test_" in code:
            if "datetime.datetime.now" in code:
                now_pos = code.find("datetime.datetime.now")
                now_end = now_pos + len("datetime.datetime.now")
                
                call_node = MockNode(
                    "call_expression", 
                    "datetime.datetime.now()",
                    now_pos, now_end,
                    callee=MockNode("attribute", "datetime.datetime.now", now_pos, now_end)
                )
                
                func_node = MockNode(
                    "function_definition", 
                    code, 0, len(code),
                    children=[call_node],
                    name=MockNode("identifier", "test_something")
                )
                call_node.parent = func_node
                return func_node
        
        elif language == "javascript" and ("test(" in code or "it(" in code):
            if "Date.now" in code:
                now_pos = code.find("Date.now")
                now_end = now_pos + len("Date.now")
                
                call_node = MockNode(
                    "call_expression",
                    "Date.now()",
                    now_pos, now_end,
                    callee=MockNode("member_expression", "Date.now", now_pos, now_end)
                )
                
                test_node = MockNode(
                    "call_expression",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
            elif "new Date(" in code:
                date_pos = code.find("new Date(")
                date_end = code.find(")", date_pos) + 1
                
                # Check if there are arguments
                args_text = code[code.find("(", date_pos) + 1:code.find(")", date_pos)]
                has_args = bool(args_text.strip())
                
                arguments = []
                if has_args:
                    # Create a mock argument
                    arguments = [MockNode("string_literal", args_text.strip())]
                
                call_node = MockNode(
                    "new_expression",
                    code[date_pos:date_end],
                    date_pos, date_end,
                    callee=MockNode("identifier", "Date", date_pos + 4, date_pos + 8),
                    arguments=arguments
                )
                
                test_node = MockNode(
                    "call_expression",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
        
        elif language == "typescript" and ("test(" in code or "it(" in code):
            if "Date.now" in code:
                now_pos = code.find("Date.now")
                now_end = now_pos + len("Date.now")
                
                call_node = MockNode(
                    "call_expression",
                    "Date.now()",
                    now_pos, now_end,
                    callee=MockNode("member_expression", "Date.now", now_pos, now_end)
                )
                
                test_node = MockNode(
                    "call_expression",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
            elif "new Date(" in code:
                date_pos = code.find("new Date(")
                date_end = code.find(")", date_pos) + 1
                
                # Check if there are arguments
                args_text = code[code.find("(", date_pos) + 1:code.find(")", date_pos)]
                has_args = bool(args_text.strip())
                
                arguments = []
                if has_args:
                    # Create a mock argument
                    arguments = [MockNode("string_literal", args_text.strip())]
                
                call_node = MockNode(
                    "new_expression",
                    code[date_pos:date_end],
                    date_pos, date_end,
                    callee=MockNode("identifier", "Date", date_pos + 4, date_pos + 8),
                    arguments=arguments
                )
                
                test_node = MockNode(
                    "call_expression",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
        
        elif language == "go" and "func Test" in code:
            if "time.Now" in code:
                now_pos = code.find("time.Now")
                now_end = now_pos + len("time.Now")
                
                call_node = MockNode(
                    "call_expression",
                    "time.Now()",
                    now_pos, now_end,
                    callee=MockNode("selector_expression", "time.Now", now_pos, now_end)
                )
                
                func_node = MockNode(
                    "function_declaration",
                    code, 0, len(code),
                    children=[call_node],
                    name=MockNode("identifier", "TestSomething")
                )
                call_node.parent = func_node
                return func_node
        
        elif language == "java":
            if "@Test" in code and "System.currentTimeMillis" in code:
                millis_pos = code.find("System.currentTimeMillis")
                millis_end = millis_pos + len("System.currentTimeMillis")
                
                call_node = MockNode(
                    "method_invocation",
                    "System.currentTimeMillis()",
                    millis_pos, millis_end,
                    callee=MockNode("member_expression", "System.currentTimeMillis", millis_pos, millis_end)
                )
                
                func_node = MockNode(
                    "method_declaration",
                    code, 0, len(code),
                    children=[call_node],
                    name=MockNode("identifier", "testSomething"),
                    annotations=[MockNode("annotation", "@Test")]
                )
                call_node.parent = func_node
                return func_node
        
        elif language == "cpp":
            if "TEST(" in code and "std::chrono::system_clock::now" in code:
                now_pos = code.find("std::chrono::system_clock::now")
                now_end = now_pos + len("std::chrono::system_clock::now")
                
                call_node = MockNode(
                    "call_expression",
                    "std::chrono::system_clock::now()",
                    now_pos, now_end,
                    callee=MockNode("qualified_identifier", "std::chrono::system_clock::now", now_pos, now_end)
                )
                
                test_node = MockNode(
                    "function_definition",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
        
        elif language == "csharp":
            if "[Fact]" in code and "DateTime.Now" in code:
                now_pos = code.find("DateTime.Now")
                now_end = now_pos + len("DateTime.Now")
                
                # C# DateTime.Now is a property access, not a method call
                access_node = MockNode(
                    "member_access_expression",
                    "DateTime.Now",
                    now_pos, now_end,
                    callee=MockNode("member_expression", "DateTime.Now", now_pos, now_end)
                )
                
                func_node = MockNode(
                    "method_declaration",
                    code, 0, len(code),
                    children=[access_node],
                    name=MockNode("identifier", "TestMethod"),
                    attributes=[MockNode("attribute", "[Fact]")]
                )
                access_node.parent = func_node
                return func_node
        
        elif language == "ruby":
            if 'it "' in code and "Time.now" in code:
                now_pos = code.find("Time.now")
                now_end = now_pos + len("Time.now")
                
                call_node = MockNode(
                    "call",
                    "Time.now",
                    now_pos, now_end,
                    callee=MockNode("constant", "Time.now", now_pos, now_end)
                )
                
                test_node = MockNode(
                    "call",
                    code, 0, len(code),
                    children=[call_node]
                )
                call_node.parent = test_node
                return test_node
        
        elif language == "rust":
            if "#[test]" in code and "SystemTime::now" in code:
                now_pos = code.find("SystemTime::now")
                now_end = now_pos + len("SystemTime::now")
                
                call_node = MockNode(
                    "call_expression",
                    "std::time::SystemTime::now()",
                    now_pos, now_end,
                    callee=MockNode("scoped_identifier", "std::time::SystemTime::now", now_pos, now_end)
                )
                
                func_node = MockNode(
                    "function_item",
                    code, 0, len(code),
                    children=[call_node],
                    name=MockNode("identifier", "test_bad")
                )
                call_node.parent = func_node
                return func_node
        
        elif language == "swift":
            if "func test" in code and "Date(" in code:
                date_pos = code.find("Date(")
                date_end = code.find(")", date_pos) + 1
                
                # Check if there are arguments
                args_text = code[code.find("(", date_pos) + 1:code.find(")", date_pos)]
                has_args = bool(args_text.strip())
                
                arguments = []
                if has_args:
                    # Create a mock argument
                    arguments = [MockNode("string_literal", args_text.strip())]
                
                call_node = MockNode(
                    "call_expression",
                    code[date_pos:date_end],
                    date_pos, date_end,
                    callee=MockNode("type_identifier", "Date", date_pos, date_pos + 4),
                    arguments=arguments
                )
                
                func_node = MockNode(
                    "function_declaration",
                    code, 0, len(code),
                    children=[call_node],
                    name=MockNode("identifier", "testBad")
                )
                call_node.parent = func_node
                return func_node
        
        # Default: empty node
        return MockNode("source_file", code, 0, len(code))


class TestTestBrittleTimeDependentRule:
    """Test cases for TestBrittleTimeDependentRule."""
    
    def setup_method(self):
        """Set up test rule instance."""
        self.rule = TestBrittleTimeDependentRule()

    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "test.brittle_time_dependent"
        assert self.rule.meta.category == "test"
        assert "info" in str(self.rule.meta.tier) or self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert len(self.rule.meta.langs) == 11

    def test_python_datetime_now_in_test(self):
        """Test detection of datetime.now() in Python test."""
        code = """
def test_something():
    import datetime
    x = datetime.datetime.now()
    assert x is not None
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Time-dependent call in test" in findings[0].message
        assert findings[0].rule == "test.brittle_time_dependent"

    def test_javascript_date_now_in_test(self):
        """Test detection of Date.now() in JavaScript test."""
        code = """
test("should work", () => {
    const t = Date.now();
    expect(t).toBeGreaterThan(0);
});
"""
        ctx = MockRuleContext(code, "test.js", "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_typescript_new_date_constructor(self):
        """Test detection of new Date() in TypeScript test."""
        code = """
test("should work", () => {
    const t = new Date();
    expect(t).toBeInstanceOf(Date);
});
"""
        ctx = MockRuleContext(code, "test.ts", "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_go_time_now_in_test(self):
        """Test detection of time.Now() in Go test."""
        code = """
func TestSomething(t *testing.T) {
    n := time.Now()
    if n.IsZero() {
        t.Fatal()
    }
}
"""
        ctx = MockRuleContext(code, "test.go", "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_java_system_currenttimemillis_in_test(self):
        """Test detection of System.currentTimeMillis() in Java test."""
        code = """
@Test
void testSomething() {
    long t = System.currentTimeMillis();
    assertTrue(t > 0);
}
"""
        ctx = MockRuleContext(code, "Test.java", "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_cpp_chrono_now_in_test(self):
        """Test detection of std::chrono::system_clock::now() in C++."""
        code = """
TEST(Suite, Bad) {
    auto now = std::chrono::system_clock::now();
    EXPECT_GT(now.time_since_epoch().count(), 0);
}
"""
        ctx = MockRuleContext(code, "test.cpp", "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_csharp_datetime_now_in_test(self):
        """Test detection of DateTime.Now in C# test."""
        code = """
[Fact]
void TestMethod() {
    var n = DateTime.Now;
    Assert.True(n.Year > 2000);
}
"""
        ctx = MockRuleContext(code, "Test.cs", "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_ruby_time_now_in_test(self):
        """Test detection of Time.now in Ruby test."""
        code = """
it "should work" do
    t = Time.now
    expect(t).to be_a(Time)
end
"""
        ctx = MockRuleContext(code, "test.rb", "ruby")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_rust_systemtime_now_in_test(self):
        """Test detection of SystemTime::now() in Rust test."""
        code = """
#[test]
fn test_bad() {
    let _ = std::time::SystemTime::now();
}
"""
        ctx = MockRuleContext(code, "test.rs", "rust")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_swift_date_init_in_test(self):
        """Test detection of Date() in Swift test."""
        code = """
func testBad() {
    let d = Date()
    XCTAssertNotNil(d)
}
"""
        ctx = MockRuleContext(code, "Test.swift", "swift")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_negative_case_fixed_timestamps(self):
        """Test that fixed timestamps are not flagged."""
        code = """
def test_ok():
    fixed = datetime.datetime(2020, 1, 1)
    assert fixed.year == 2020
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_case_date_with_args(self):
        """Test that Date constructor with arguments is not flagged."""
        code = """
test("ok", () => {
    const t = new Date("2020-01-01");
    expect(t.getFullYear()).toBe(2020);
});
"""
        ctx = MockRuleContext(code, "test.js", "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_case_non_test_context(self):
        """Test that time calls outside test context are not flagged."""
        code = """
def regular_function():
    return datetime.datetime.now()
"""
        ctx = MockRuleContext(code, "utils.py", "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_unsupported_language(self):
        """Test that unsupported languages are ignored."""
        code = """
sub test_something {
    my $now = time();
}
"""
        ctx = MockRuleContext(code, "test.pl", "perl")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_no_syntax_tree(self):
        """Test handling when syntax tree is None."""
        ctx = MockRuleContext("", "test.py", "python")
        ctx.syntax = None
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

