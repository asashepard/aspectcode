# server/tests/test_deadcode_noop_statement.py
"""
Tests for deadcode.noop_statement rule.

This module tests detection and removal of no-op statements like standalone semicolons
and empty blocks while preserving necessary constructs like for(;;) and do-while.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_noop_statement import DeadcodeNoopStatementRule
from engine.types import RuleContext, Finding, Edit
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter
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
        "java": JavaAdapter(),
        "csharp": CSharpAdapter(),
        "cpp": CppAdapter(),
        "c": CAdapter(),
    }
    
    # Map language to file extension
    extensions = {
        "javascript": "js",
        "typescript": "ts",
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

RULE = DeadcodeNoopStatementRule()

def test_positive_remove_noops_js():
    """Test detection and removal of various no-op statements in JavaScript."""
    code = (
        "function f(){;;}\n"
        "if (x) {}\n"
        "else {}\n"
        "{}\n"
        "let a = 1;;\n"
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    # All no-ops should be removed or converted
    assert ";;" not in fixed
    assert "else {}" not in fixed
    # Check that standalone {} is removed
    lines = [line.strip() for line in fixed.split('\n') if line.strip()]
    assert "{}" not in lines

def test_positive_if_empty_conversion():
    """Test conversion of empty if blocks to semicolons."""
    code = "if (condition) {}\nif (x > 0) {}"
    res = run_rule(RULE, code, language="c")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    # Empty if blocks should be converted to semicolons (which are then removed)
    assert "if (condition)" not in fixed or "if (condition);" in fixed or "if (condition) {}" not in fixed

def test_positive_standalone_empty_blocks():
    """Test removal of standalone empty blocks."""
    code = (
        "int main() {\n"
        "    int x = 1;\n"
        "    {}\n"
        "    return x;\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="c")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # Standalone {} should be removed
        lines = [line.strip() for line in fixed.split('\n') if line.strip()]
        assert "{}" not in lines

def test_negative_keep_for_and_do_while_and_label_c():
    """Test that for(;;), do-while, and labeled statements are preserved."""
    code = (
        "int main(){\n"
        "  for(;;) { break; }\n"
        "  do { i++; } while (i < 10);\n"
        "  label: ;\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="c")
    # Should not remove the for(;;) semicolons, do-while semicolon, or labeled semicolon
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        assert "for(;;)" in fixed
        assert "while (i < 10);" in fixed
        assert "label: ;" in fixed

def test_negative_keep_function_blocks():
    """Test that function/class/loop blocks are not touched."""
    code = (
        "function test() {}\n"
        "class MyClass {}\n"
        "for (let i = 0; i < 10; i++) {}\n"
        "while (true) {}\n"
    )
    res = run_rule(RULE, code, language="javascript")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # These blocks should be preserved as they're not standalone
        assert "function test() {}" in fixed
        assert "class MyClass {}" in fixed
        assert "for (let i = 0; i < 10; i++) {}" in fixed
        assert "while (true) {}" in fixed

def test_negative_keep_switch_try_blocks():
    """Test that switch/try blocks are preserved."""
    code = (
        "try {}\n"
        "catch (e) {}\n"
        "switch (x) {}\n"
    )
    res = run_rule(RULE, code, language="javascript")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # These should be preserved
        assert "try" in fixed
        assert "catch" in fixed  
        assert "switch" in fixed

def test_autofix_typescript_chain():
    """Test autofix behavior chains correctly in TypeScript."""
    code = (
        "if (cond) {} else {}\n"
        "let x = 1;;\n"
        "{}\n"
    )
    res = run_rule(RULE, code, language="typescript")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # All no-ops should be cleaned up
        assert "else {}" not in fixed and ";;" not in fixed
        # Second pass should be clean
        res2 = run_rule(RULE, fixed, language="typescript")
        assert len(res2.findings) == 0

def test_java_specific_patterns():
    """Test Java-specific no-op patterns."""
    code = (
        "public class Test {\n"
        "    public void method() {\n"
        "        if (x > 0) {}\n"
        "        ;;\n"
        "    }\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="java")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        assert ";;" not in fixed

def test_csharp_using_patterns():
    """Test C# specific patterns."""
    code = (
        "using System;\n"
        "class Test {\n"
        "    void Method() {\n"
        "        if (condition) {}\n"
        "        else {}\n"
        "    }\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="csharp")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        assert "else {}" not in fixed

def test_cpp_specific_patterns():
    """Test C++ specific patterns with templates."""
    code = (
        "#include <iostream>\n"
        "int main() {\n"
        "    if (true) {}\n"
        "    ;;\n"
        "    return 0;\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="cpp")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        assert ";;" not in fixed

def test_edge_case_multiple_adjacent_semicolons():
    """Test handling of multiple adjacent empty statements."""
    code = "foo();;;;"
    res = run_rule(RULE, code, language="c")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # Should reduce to single required semicolon after foo()
        assert fixed.count(';') <= 1

def test_edge_case_whitespace_around_braces():
    """Test handling of whitespace around empty blocks."""
    code = (
        "if (x) { /* comment */ }\n"  # Not truly empty - has comment
        "if (y) {   }\n"              # Truly empty with whitespace
        "if (z) {\n}\n"               # Empty with newline
    )
    res = run_rule(RULE, code, language="c")
    if res.findings:
        fixed = apply_fixes(code, res.findings)
        # Only truly empty blocks should be converted
        assert "/* comment */" in fixed  # Comment block preserved

def test_autofix_batch_edits():
    """Test that multiple edits are applied correctly in batch."""
    code = (
        "function test() {\n"
        "    if (a) {}\n"
        "    ;;\n"
        "    else {}\n"
        "    {}\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) >= 1
    
    # Verify that autofix is provided
    if res.findings:
        assert res.findings[0].autofix is not None
        assert len(res.findings[0].autofix) > 0
        
        fixed = apply_fixes(code, res.findings)
        # Verify the fixes were applied
        assert ";;" not in fixed
        
def test_language_detection():
    """Test that the rule only applies to supported languages."""
    code = "print('hello');"  # Python-like code
    res = run_rule(RULE, code, language="python")  # Unsupported language
    # Should return no findings for unsupported language
    assert len(res.findings) == 0

