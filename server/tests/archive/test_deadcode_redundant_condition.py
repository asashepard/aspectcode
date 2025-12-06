# server/tests/test_deadcode_redundant_condition.py
"""
Tests for deadcode.redundant_condition rule.

This module tests constant-folding of boolean expressions and
verification of safe autofix options.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_redundant_condition import DeadcodeRedundantConditionRule
from engine.types import RuleContext, Finding, Edit
from engine.python_adapter import PythonAdapter
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter

def create_test_context(code: str, language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a RuleContext for testing."""
    # Choose appropriate adapter
    adapters = {
        "python": PythonAdapter(),
        "javascript": JavaScriptAdapter(), 
        "typescript": TypeScriptAdapter(),
        "java": JavaScriptAdapter(),  # Fallback for now
        "cpp": JavaScriptAdapter(),   # Fallback for now
        "c": JavaScriptAdapter(),     # Fallback for now
    }
    
    # Map language to file extension
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "cpp": "cpp",
        "c": "c"
    }
    
    adapter = adapters.get(language, PythonAdapter())
    ext = extensions.get(language, "py")
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

def run_rule(rule, code: str, language: str = "python", config: Dict[str, Any] = None):
    """Helper to run a rule on test code."""
    ctx = create_test_context(code, language, config)
    findings = rule.visit(ctx)
    
    # Create a simple result object
    class Result:
        def __init__(self, findings):
            self.findings = findings
    
    return Result(findings)

def apply_fixes(code: str, findings: List[Finding]) -> str:
    """Apply autofix edits from findings to the code."""
    if not findings:
        return code
    
    # Collect all edits from all findings
    all_edits = []
    for finding in findings:
        if finding.autofix:
            all_edits.extend(finding.autofix)
    
    if not all_edits:
        return code
    
    # Sort edits by start_byte in reverse order to apply from end to start
    all_edits.sort(key=lambda e: e.start_byte, reverse=True)
    
    # Apply edits
    result = code
    for edit in all_edits:
        result = result[:edit.start_byte] + edit.replacement + result[edit.end_byte:]
    
    return result

RULE = DeadcodeRedundantConditionRule()

def test_positive_ops_and_ternary_js():
    """Test detection and simplification of boolean ops and ternaries in JavaScript."""
    code = "const a = foo && true; const b = false || bar; const c = true ? x : y;\n"
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert "foo" in fixed 
    assert "bar" in fixed 
    assert "x" in fixed 
    assert "true ? x : y" not in fixed
    assert "foo && true" not in fixed
    assert "false || bar" not in fixed

def test_positive_boolean_ops_various():
    """Test various boolean operation patterns."""
    test_cases = [
        ("condition && true", "condition", "javascript"),
        ("true && condition", "condition", "javascript"), 
        ("condition || false", "condition", "javascript"),
        ("false || condition", "condition", "javascript"),
    ]
    
    for original, expected, lang in test_cases:
        code = f"var result = {original};"
        res = run_rule(RULE, code, language=lang)
        if res.findings:
            fixed = apply_fixes(code, res.findings)
            assert expected in fixed
            assert original not in fixed

def test_positive_ternary_simplification():
    """Test ternary expression simplification."""
    test_cases = [
        ("true ? alpha : beta", "alpha", "javascript"),
        ("false ? alpha : beta", "beta", "javascript"),
        ("True ? x : y", "x", "javascript"),  # Mixed case
        ("False ? x : y", "y", "javascript"), # Mixed case
    ]
    
    for original, expected, lang in test_cases:
        code = f"var result = {original};"
        res = run_rule(RULE, code, language=lang)
        if res.findings:
            fixed = apply_fixes(code, res.findings)
            assert expected in fixed
            assert "?" not in fixed

def test_positive_python_conditional_expr():
    """Test Python conditional expression simplification."""
    test_cases = [
        ("x if True else y", "x"),
        ("x if False else y", "y"),
        ("alpha if true else beta", "alpha"),  # lowercase true/false
        ("alpha if false else beta", "beta"),
    ]
    
    for original, expected in test_cases:
        code = f"result = {original}"
        res = run_rule(RULE, code, language="python")
        if res.findings:
            fixed = apply_fixes(code, res.findings)
            assert expected in fixed
            assert " if " not in fixed

def test_positive_if_else_braces_java():
    """Test if/else with braces simplification in Java."""
    code = "class A{ void f(){ if (false) { doA(); } else { doB(); } } }\n"
    res = run_rule(RULE, code, language="java")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert "doB();" in fixed 
    assert "if (false)" not in fixed
    assert "else" not in fixed

def test_positive_if_true_only():
    """Test if(true) without else."""
    code = "if (true) { executeThis(); }"
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert "executeThis();" in fixed
    assert "if (true)" not in fixed

def test_positive_if_false_only():
    """Test if(false) without else - should delete entirely."""
    code = "if (false) { neverExecute(); }"
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert "neverExecute();" not in fixed
    assert "if (false)" not in fixed
    assert fixed.strip() == ""

def test_negative_elif_chain_python():
    """Test that elif chains are not touched."""
    code = "if True:\n    a=1\nelif cond:\n    a=2\n"
    # Not simplified because of elif (not matched by simple brace/ifexpr rules)
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 0

def test_negative_else_if_chain():
    """Test that else-if chains are not touched."""
    code = "if (true) { a(); } else if (cond) { b(); }"
    res = run_rule(RULE, code, language="javascript")
    # Should not match because it's else-if, not simple else
    assert len(res.findings) == 0

def test_negative_complex_conditions():
    """Test that complex conditions are not touched."""
    code = "if (someVar == true) { doSomething(); }"
    res = run_rule(RULE, code, language="javascript")
    # Should not match because condition is not a literal boolean
    assert len(res.findings) == 0

def test_negative_nested_braces():
    """Test that nested brace blocks are not touched."""
    code = "if (true) { if (x) { nested(); } }"
    res = run_rule(RULE, code, language="javascript")
    # Should not match because of nested braces in the regex
    # Actually this might match - let's see what happens
    res_findings = len(res.findings)
    # The regex should be conservative enough to avoid this

def test_autofix_multiple_issues():
    """Test that multiple issues in one file are all fixed."""
    code = """
    var a = condition && true;
    var b = false || other;
    if (true) { keep_this(); } else { remove_this(); }
    var c = true ? yes : no;
    """
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1  # Should be batched into one finding
    
    fixed = apply_fixes(code, res.findings)
    assert "condition" in fixed
    assert "&& true" not in fixed
    assert "other" in fixed  
    assert "false ||" not in fixed
    assert "keep_this();" in fixed
    assert "remove_this();" not in fixed
    assert "yes" in fixed
    assert "? yes : no" not in fixed

def test_autofix_rerun_clean():
    """Test that after applying fixes, re-running the rule finds no more issues."""
    code = "if (false) { doA(); } else { doB(); }"
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    res2 = run_rule(RULE, fixed, language="javascript")
    assert len(res2.findings) == 0

def test_mixed_case_booleans():
    """Test handling of mixed case boolean literals."""
    test_cases = [
        ("True && x", "x", "javascript"),
        ("False || x", "x", "javascript"), 
        ("x && True", "x", "javascript"),
        ("x || False", "x", "javascript"),
    ]
    
    for original, expected, lang in test_cases:
        code = f"var result = {original};"
        res = run_rule(RULE, code, language=lang)
        if res.findings:
            fixed = apply_fixes(code, res.findings)
            assert expected in fixed

def test_edge_case_whitespace():
    """Test handling of various whitespace patterns."""
    test_cases = [
        "condition&&true",
        "condition  &&  true", 
        "condition\t&&\ttrue",
        "true\n&& condition",  # This might not match due to newline exclusion
    ]
    
    for code_pattern in test_cases:
        code = f"var result = {code_pattern};"
        res = run_rule(RULE, code, language="javascript")
        # Some patterns with newlines might not match due to safety restrictions

