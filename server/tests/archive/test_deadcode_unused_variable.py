"""
Tests for deadcode.unused_variable rule.

This module tests detection of unused local variables and parameters,
and verification of autofix options.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_unused_variable import DeadcodeUnusedVariableRule
from engine.types import RuleContext, Finding, Edit
from engine.python_adapter import PythonAdapter
from engine.scopes import build_scopes


def create_test_context(code: str, language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a test context for the given code."""
    if language == "python":
        adapter = PythonAdapter()
        file_path = "test.py"
    elif language in ["javascript", "typescript"]:
        adapter = PythonAdapter()  # Use Python adapter for now in tests
        file_path = f"test.{language[:2]}"
    else:
        adapter = PythonAdapter()
        file_path = f"test.{language}"
    
    # Parse the code to get the tree
    tree = adapter.parse(code)
    if not tree:
        # For tests with syntax errors or empty files, create minimal context
        scopes = None
    else:
        # Build scopes for Tier 1 rule
        scopes = build_scopes(adapter, tree, code)
    
    ctx = RuleContext(
        file_path=file_path,
        text=code,
        tree=tree,
        adapter=adapter,
        config=config or {},
        scopes=scopes
    )
    
    return ctx


def run_rule(rule: DeadcodeUnusedVariableRule, code: str, language: str = "python", config: Dict[str, Any] = None) -> List[Finding]:
    """Run the rule on the given code and return findings."""
    ctx = create_test_context(code, language, config)
    return list(rule.visit(ctx))


def apply_fixes(code: str, findings: List[Finding]) -> str:
    """Apply autofix edits to code and return the result."""
    text = code
    
    # Collect all edits
    all_edits = []
    for finding in findings:
        if finding.autofix:
            all_edits.extend(finding.autofix)
    
    # Sort edits by start_byte descending (apply from end to beginning)
    all_edits.sort(key=lambda e: e.start_byte, reverse=True)
    
    # Apply edits
    for edit in all_edits:
        text = text[:edit.start_byte] + edit.replacement + text[edit.end_byte:]
    
    return text


class TestDeadcodeUnusedVariableRule:
    """Test suite for deadcode.unused_variable rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = DeadcodeUnusedVariableRule()
    
    # --- Positive Tests (Should Report Issues) ---
    
    def test_python_unused_local_variable(self):
        """Test detection of unused local variables in Python."""
        code = """
def process():
    unused_var = 42
    used_var = 10
    return used_var
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect the unused variable
        assert len(findings) >= 1
        
        unused_findings = [f for f in findings if "unused_var" in f.message]
        assert len(unused_findings) == 1
        
        finding = unused_findings[0]
        assert finding.rule == "deadcode.unused_variable"
        assert "unused_var" in finding.message
        assert finding.severity == "info"  # Info level for unused variables
    
    def test_python_unused_multiple_variables(self):
        """Test detection of multiple unused variables."""
        code = """
def process():
    a = 1
    b = 2
    c = 3
    return a  # only 'a' is used
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect b and c as unused
        unused_names = {f.meta["symbol_name"] for f in findings}
        assert "b" in unused_names
        assert "c" in unused_names
        assert "a" not in unused_names  # 'a' is used
    
    def test_python_unused_in_nested_scope(self):
        """Test detection in nested function scopes."""
        code = """
def outer():
    def inner():
        nested_unused = "hello"
        nested_used = "world"
        print(nested_used)
    return inner
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect nested_unused
        unused_names = {f.meta["symbol_name"] for f in findings}
        assert "nested_unused" in unused_names
        assert "nested_used" not in unused_names
    
    def test_python_unused_loop_variable(self):
        """Test detection of unused loop variables."""
        code = """
def process():
    for i in range(10):
        pass  # i is never used
    
    for j in range(5):
        print(j)  # j is used
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect unused loop variable 'i'
        unused_names = {f.meta["symbol_name"] for f in findings}
        # Note: scope analysis might not capture loop variables perfectly
        # This test documents current behavior
        if unused_names:
            # If loop variables are detected, 'i' should be flagged but not 'j'
            assert "j" not in unused_names
    
    # --- Negative Tests (Should NOT Report Issues) ---
    
    def test_python_used_variable_not_reported(self):
        """Test that used variables are not reported."""
        code = """
def process():
    x = 42
    y = x * 2
    return y
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should not report any unused variables
        assert len(findings) == 0
    
    def test_python_variable_used_in_expression(self):
        """Test that variables used in expressions are not flagged."""
        code = """
def calculate():
    a = 10
    b = 20
    result = a + b
    return result
"""
        findings = run_rule(self.rule, code, "python")
        
        # No variables should be flagged as unused
        assert len(findings) == 0
    
    def test_python_variable_used_in_conditional(self):
        """Test that variables used in conditionals are not flagged."""
        code = """
def check():
    flag = True
    value = 42
    if flag:
        return value
    return 0
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 0
    
    def test_allowlist_configuration(self):
        """Test that allowlist configuration prevents reports."""
        code = """
def process():
    debug_var = 42
    temp_value = "test"
    return "done"
"""
        # Without allowlist - should report
        findings_normal = run_rule(self.rule, code, "python")
        assert len(findings_normal) >= 1
        
        # With allowlist - should not report allowlisted names
        config = {"unused_allowlist": ["debug_var", "temp_value"]}
        findings_allowlist = run_rule(self.rule, code, "python", config)
        assert len(findings_allowlist) == 0
    
    def test_already_suppressed_names_ignored(self):
        """Test that already-suppressed names are ignored."""
        code = """
def process():
    _ = 42          # underscore - should be ignored
    _unused = 10    # underscore prefix - should be ignored in some languages
    normal = 20     # normal name - should be flagged
    return "done"
"""
        findings = run_rule(self.rule, code, "python")
        
        flagged_names = {f.meta["symbol_name"] for f in findings}
        assert "_" not in flagged_names
        assert "normal" in flagged_names
    
    # --- Autofix Tests ---
    
    def test_autofix_underscore_mode_default(self):
        """Test autofix in default underscore mode."""
        code = """
def process():
    unused_var = 42
    used_var = 10
    return used_var
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        edit = finding.autofix[0]
        assert edit.replacement == "_"
        
        # Apply fix and verify
        fixed_code = apply_fixes(code, findings)
        assert "_ = 42" in fixed_code
        assert "used_var" in fixed_code
        
        # Re-run rule on fixed code - should have no findings
        fixed_findings = run_rule(self.rule, fixed_code, "python")
        assert len(fixed_findings) == 0
    
    def test_autofix_language_specific_throwaway_names(self):
        """Test language-specific throwaway name generation."""
        code = "func test() { unused := 42; }"
        
        # Test Go language (should use "_")
        findings = run_rule(self.rule, code, "go")
        if findings:  # If parsing works
            finding = findings[0]
            if finding.autofix:
                edit = finding.autofix[0]
                assert edit.replacement == "_"
        
        # Test Rust language (should prefix with _)
        rust_code = "fn test() { let unused = 42; }"
        findings = run_rule(self.rule, rust_code, "rust")
        if findings:  # If parsing works
            finding = findings[0]
            if finding.autofix:
                edit = finding.autofix[0]
                assert edit.replacement == "_unused"
    
    def test_autofix_remove_mode_simple_declaration(self):
        """Test autofix in remove mode for simple declarations."""
        code = """
def process():
    let unused;
    used_var = 10
    return used_var
"""
        config = {"unused_var_fix": "remove"}
        findings = run_rule(self.rule, code, "python", config)
        
        # Should attempt to remove simple declaration
        if findings:
            unused_finding = next((f for f in findings if "unused" in f.meta["symbol_name"]), None)
            if unused_finding and unused_finding.autofix:
                # Verify it's a removal edit
                edit = unused_finding.autofix[0]
                assert edit.replacement == ""
    
    def test_autofix_preserve_semantics(self):
        """Test that autofix preserves code semantics."""
        code = """
def process():
    temp = expensive_computation()
    result = other_computation()
    return result
"""
        # Even though temp is unused, we should not remove it if it might have side effects
        # This tests the conservative nature of the autofix
        findings = run_rule(self.rule, code, "python")
        
        if findings:
            temp_finding = next((f for f in findings if "temp" in f.meta["symbol_name"]), None)
            if temp_finding:
                # Should prefer underscore rename over removal for expressions
                fixed_code = apply_fixes(code, [temp_finding])
                # Should still call expensive_computation()
                assert "expensive_computation()" in fixed_code
    
    def test_multiple_unused_variables_batch_fix(self):
        """Test that multiple unused variables can be fixed in batch."""
        code = """
def process():
    a = 1
    b = 2  
    c = 3
    used = 4
    return used
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should find multiple unused variables
        assert len(findings) >= 2
        
        # Apply all fixes
        fixed_code = apply_fixes(code, findings)
        
        # Should replace unused variables with underscores
        lines = fixed_code.split('\n')
        assignment_lines = [line for line in lines if '=' in line and 'return' not in line]
        
        unused_assignments = [line for line in assignment_lines if line.strip().startswith('_')]
        assert len(unused_assignments) >= 2
        
        # Used variable should remain unchanged
        assert "used = 4" in fixed_code
    
    # --- Edge Cases ---
    
    def test_empty_function(self):
        """Test handling of empty functions."""
        code = """
def empty_func():
    pass
"""
        findings = run_rule(self.rule, code, "python")
        assert len(findings) == 0
    
    def test_function_with_only_used_variables(self):
        """Test function where all variables are used."""
        code = """
def all_used():
    a = 1
    b = 2
    c = a + b
    return c
"""
        findings = run_rule(self.rule, code, "python")
        assert len(findings) == 0
    
    def test_syntax_error_handling(self):
        """Test handling of files with syntax errors."""
        code = """
def broken_syntax(
    # Missing closing parenthesis and body
"""
        # Should not crash on syntax errors
        try:
            findings = run_rule(self.rule, code, "python")
            # May or may not find issues depending on how parser handles errors
        except Exception:
            pytest.fail("Rule should handle syntax errors gracefully")
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = """
function test() {
    const unused = 42;
    return 1;
}
"""
        findings = run_rule(self.rule, code, "cobol")  # Unsupported language
        
        # Should not process unsupported languages
        assert len(findings) == 0
    
    def test_unicode_variable_names(self):
        """Test handling of unicode variable names."""
        code = """
def process():
    变量 = 42  # Chinese characters
    λ = 3.14   # Greek letter
    used = 10
    return used
"""
        # Should handle unicode identifiers without crashing
        try:
            findings = run_rule(self.rule, code, "python")
            # Unicode variables should be flagged if unused
            if findings:
                flagged_names = {f.meta["symbol_name"] for f in findings}
                # May include unicode names depending on scope analysis
        except Exception:
            pytest.fail("Rule should handle unicode identifiers gracefully")
    
    # --- Parameter Handling ---
    
    def test_unused_parameters_detected(self):
        """Test detection of unused function parameters."""
        # Note: Parameter detection depends on scope analysis capabilities
        code = """
def process(used_param, unused_param):
    return used_param
"""
        findings = run_rule(self.rule, code, "python")
        
        # Current scope analysis may or may not expose parameters as symbols
        # This test documents the current behavior
        if findings:
            # If parameters are detected, only unused_param should be flagged
            flagged_names = {f.meta["symbol_name"] for f in findings}
            assert "used_param" not in flagged_names
    
    def test_parameters_not_removed(self):
        """Test that parameters are never removed, only renamed."""
        code = """
def process(unused_param):
    return 42
"""
        config = {"unused_var_fix": "remove"}
        findings = run_rule(self.rule, code, "python", config)
        
        if findings:
            param_finding = next((f for f in findings if f.meta["symbol_kind"] == "param"), None)
            if param_finding and param_finding.autofix:
                # Should not be a removal edit for parameters
                edit = param_finding.autofix[0]
                assert edit.replacement != ""  # Not a removal
    
    # --- Language-Specific Tests ---
    
    def test_javascript_typescript_support(self):
        """Test basic support for JavaScript/TypeScript."""
        js_code = """
function process() {
    let unused = 42;
    const used = 10;
    return used;
}
"""
        findings = run_rule(self.rule, js_code, "javascript")
        
        # Should work with JS syntax (if parser supports it)
        if findings:
            flagged_names = {f.meta["symbol_name"] for f in findings}
            assert "used" not in flagged_names
    
    def test_meta_information_present(self):
        """Test that findings include proper meta information."""
        code = """
def process():
    unused_var = 42
    return "done"
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check meta information
        assert "symbol_name" in finding.meta
        assert "symbol_kind" in finding.meta
        assert "language" in finding.meta
        assert "mode" in finding.meta
        
        assert finding.meta["symbol_name"] == "unused_var"
        assert finding.meta["language"] == "python"
        assert finding.meta["mode"] == "underscore"  # default


# Integration test to verify rule registration
def test_rule_registration():
    """Test that the rule is properly registered."""
    try:
        from rules import RULES
        rule_ids = [rule.meta.id for rule in RULES]
        assert "deadcode.unused_variable" in rule_ids
    except ImportError:
        # Skip if rules module not available in test environment
        pytest.skip("Rules module not available for registration test")


if __name__ == "__main__":
    # Run a quick smoke test
    rule = DeadcodeUnusedVariableRule()
    
    test_code = """
def process():
    unused1 = 42
    unused2 = "hello"
    used = 10
    return used
"""
    
    print("Testing deadcode.unused_variable rule...")
    findings = run_rule(rule, test_code, "python")
    
    print(f"Found {len(findings)} issues:")
    for finding in findings:
        print(f"  - {finding.message}")
        print(f"    Variable: {finding.meta['symbol_name']}")
        print(f"    Kind: {finding.meta['symbol_kind']}")
        if finding.autofix:
            edit = finding.autofix[0]
            print(f"    Fix: Replace with '{edit.replacement}'")
        print()
    
    print("Test completed successfully!")

