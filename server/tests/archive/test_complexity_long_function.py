# server/tests/test_complexity_long_function.py
"""
Tests for complexity.long_function rule.

This module tests detection of overly long or complex functions and
the suggestion generation for refactoring guidance.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.complexity_long_function import ComplexityLongFunctionRule
from engine.types import RuleContext, Finding
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter
from engine.python_adapter import PythonAdapter
from engine.java_adapter import JavaAdapter
from engine.csharp_adapter import CSharpAdapter
from engine.cpp_adapter import CppAdapter
from engine.c_adapter import CAdapter

def create_test_context(code: str, language: str = "javascript", config: Dict[str, Any] = None) -> RuleContext:
    """Create a RuleContext for testing."""
    # Choose appropriate adapter
    adapters = {
        "javascript": JavaScriptAdapter(),
        "typescript": TypeScriptAdapter(),
        "python": PythonAdapter(),
        "java": JavaAdapter(),
        "csharp": CSharpAdapter(),
        "cpp": CppAdapter(),
        "c": CAdapter(),
    }
    
    # Map language to file extension
    extensions = {
        "javascript": "js",
        "typescript": "ts",
        "python": "py",
        "java": "java",
        "csharp": "cs",
        "cpp": "cpp",
        "c": "c"
    }
    
    adapter = adapters.get(language, JavaScriptAdapter())
    ext = extensions.get(language, "js")
    file_path = f"test.{ext}"
    
    # Parse the tree
    tree = adapter.parse(code)
    
    ctx = RuleContext(
        file_path=file_path,
        text=code,
        tree=tree,
        adapter=adapter,
        config=config or {},
        scopes=None  # Tier 0 rule doesn't need scopes
    )
    
    return ctx

def run_rule(rule, code: str, language: str = "javascript", config: Dict[str, Any] = None):
    """Helper to run a rule on test code."""
    ctx = create_test_context(code, language, config)
    findings = rule.visit(ctx)
    
    # Create a simple result object
    class Result:
        def __init__(self, findings):
            self.findings = findings
    
    return Result(findings)

# Test rule instance
RULE = ComplexityLongFunctionRule()

def test_positive_flags_long_js():
    """Test that a long JavaScript function is flagged."""
    # Create a function with many lines
    statements = ["console.log('line " + str(i) + "');" for i in range(30)]
    code = f"function longFunction() {{\n  " + "\n  ".join(statements) + "\n}}\n"
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 20, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    assert "longFunction" in res.findings[0].message
    assert "extract" in res.findings[0].message.lower()
    assert res.findings[0].meta["loc"] > 20

def test_positive_flags_complex_js():
    """Test that a complex JavaScript function is flagged."""
    # Create a function with high cyclomatic complexity
    code = """
function complexFunction(x, y, z) {
    if (x > 0) {
        if (y > 0) {
            if (z > 0) {
                for (let i = 0; i < 10; i++) {
                    while (i < 5) {
                        switch (x) {
                            case 1:
                                return "one";
                            case 2:
                                return "two";
                            default:
                                break;
                        }
                        i++;
                    }
                }
            } else if (z < 0) {
                return "negative z";
            }
        } else if (y < 0) {
            return "negative y";
        }
    } else if (x < 0) {
        return "negative x";
    }
    return "default";
}
"""
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 50, "max_cyclomatic": 5})
    assert len(res.findings) == 1
    assert "complexFunction" in res.findings[0].message
    assert res.findings[0].meta["cyclomatic_complexity"] > 5

def test_negative_small_js():
    """Test that a small JavaScript function is not flagged."""
    code = """
function smallFunction(x) {
    if (x > 0) {
        return x * 2;
    }
    return 0;
}
"""
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 10, "max_cyclomatic": 5})
    assert len(res.findings) == 0

def test_negative_small_py():
    """Test that a small Python function is not flagged."""
    code = """
def small_function(x):
    if x:
        return 1
    return 0
"""
    
    res = run_rule(RULE, code, language="python", config={"max_loc": 10, "max_cyclomatic": 5})
    assert len(res.findings) == 0

def test_python_function_detection():
    """Test that Python functions are properly detected and analyzed."""
    # Create a long Python function
    statements = [f"    print('line {i}')" for i in range(25)]
    code = f"def long_python_function():\n" + "\n".join(statements) + "\n"
    
    res = run_rule(RULE, code, language="python", config={"max_loc": 20, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    assert "long_python_function" in res.findings[0].message
    assert res.findings[0].meta["loc"] > 20

def test_java_method_detection():
    """Test that Java methods are properly detected and analyzed."""
    code = """
public class TestClass {
    public void longMethod() {
        System.out.println("line 1");
        System.out.println("line 2");
        System.out.println("line 3");
        System.out.println("line 4");
        System.out.println("line 5");
        System.out.println("line 6");
        System.out.println("line 7");
        System.out.println("line 8");
        System.out.println("line 9");
        System.out.println("line 10");
        System.out.println("line 11");
        System.out.println("line 12");
        System.out.println("line 13");
        System.out.println("line 14");
        System.out.println("line 15");
    }
}
"""
    
    res = run_rule(RULE, code, language="java", config={"max_loc": 10, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    assert "longMethod" in res.findings[0].message

def test_c_function_detection():
    """Test that C functions are properly detected and analyzed."""
    code = """
int long_c_function(int x) {
    printf("line 1");
    printf("line 2");
    printf("line 3");
    printf("line 4");
    printf("line 5");
    printf("line 6");
    printf("line 7");
    printf("line 8");
    printf("line 9");
    printf("line 10");
    printf("line 11");
    printf("line 12");
    printf("line 13");
    printf("line 14");
    printf("line 15");
    return x;
}
"""
    
    res = run_rule(RULE, code, language="c", config={"max_loc": 10, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    assert "long_c_function" in res.findings[0].message

def test_suggestion_content():
    """Test that the suggestion contains useful refactoring guidance."""
    code = """
function needsRefactoring() {
    let result = 0;
    for (let i = 0; i < 100; i++) {
        if (i % 2 === 0) {
            if (i % 4 === 0) {
                result += i * 2;
            } else {
                result += i;
            }
        } else {
            if (i % 3 === 0) {
                result -= i;
            } else {
                result += i / 2;
            }
        }
    }
    return result;
}
"""
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 5, "max_cyclomatic": 3})
    assert len(res.findings) == 1
    
    finding = res.findings[0]
    suggestion = finding.meta["suggestion"]
    assert "TODO" in suggestion
    assert "needsRefactoring" in suggestion
    assert "Extract helper method" in suggestion
    assert "//" in suggestion  # JavaScript comment style

def test_configuration_respected():
    """Test that custom configuration values are respected."""
    code = """
function testFunction() {
    console.log("line 1");
    console.log("line 2");
    console.log("line 3");
    console.log("line 4");
    console.log("line 5");
}
"""
    
    # Should not flag with high limits
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 10, "max_cyclomatic": 10})
    assert len(res.findings) == 0
    
    # Should flag with low limits
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 3, "max_cyclomatic": 10})
    assert len(res.findings) == 1

def test_language_detection():
    """Test that the rule only applies to supported languages."""
    code = "function test() { console.log('hello'); }"
    
    # Create a mock adapter with unsupported language_id
    class MockAdapter:
        def __init__(self):
            self.language_id = "unsupported"
        
        def parse(self, code):
            # Return a minimal mock tree
            class MockTree:
                def __init__(self):
                    self.root_node = MockNode()
            return MockTree()
    
    class MockNode:
        def __init__(self):
            self.children = []
    
    # Test with unsupported language
    ctx = RuleContext(
        file_path="test.unknown",
        text=code,
        tree=MockAdapter().parse(code),
        adapter=MockAdapter(),
        config={},
        scopes=None
    )
    
    findings = RULE.visit(ctx)
    assert len(findings) == 0

def test_empty_function_ignored():
    """Test that empty or signature-only functions are ignored."""
    # Interface method with no body
    code = """
interface TestInterface {
    void emptyMethod();
}
"""
    
    res = run_rule(RULE, code, language="java", config={"max_loc": 1, "max_cyclomatic": 1})
    assert len(res.findings) == 0

def test_comment_style_per_language():
    """Test that comment style is appropriate for each language."""
    # Python should use # comments
    code = """
def long_python_function():
    print("line 1")
    print("line 2")
    print("line 3")
    print("line 4")
    print("line 5")
"""
    
    res = run_rule(RULE, code, language="python", config={"max_loc": 3, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    
    suggestion = res.findings[0].meta["suggestion"]
    assert "#" in suggestion  # Python comment style
    assert "//" not in suggestion

def test_loc_calculation():
    """Test that LOC calculation correctly ignores empty lines and comments."""
    code = """
function testLOC() {
    // This is a comment
    console.log("line 1");
    
    /* Multi-line
       comment */
    console.log("line 2");
    
    console.log("line 3");
    {}
    console.log("line 4");
}
"""
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 3, "max_cyclomatic": 10})
    assert len(res.findings) == 1
    
    # Should count only the 4 console.log statements
    finding = res.findings[0]
    assert finding.meta["loc"] == 4

def test_cyclomatic_calculation():
    """Test that cyclomatic complexity is calculated correctly."""
    code = """
function testCC(x, y) {
    if (x > 0) {        // +1
        if (y > 0) {    // +1
            return 1;
        } else {        // +1
            return 2;
        }
    } else if (x < 0) { // +1
        return 3;
    }
    return 0;
}
"""
    
    res = run_rule(RULE, code, language="javascript", config={"max_loc": 50, "max_cyclomatic": 3})
    assert len(res.findings) == 1
    
    # Base complexity (1) + 4 decision points = 5
    finding = res.findings[0]
    assert finding.meta["cyclomatic_complexity"] >= 4  # Should be around 5

@pytest.mark.skip(reason="suggest-only: rule provides guidance, not edits")
def test_autofix_skipped():
    """Test that autofix is not provided (suggest-only rule)."""
    pass

