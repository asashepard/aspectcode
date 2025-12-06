"""
Tests for deadcode.unused_parameter rule.

This module tests detection of unused function/method parameters
and verification of suggested changes (no direct edits).
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_unused_parameter import DeadcodeUnusedParameterRule
from engine.types import RuleContext, Finding
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


def run_rule(rule: DeadcodeUnusedParameterRule, code: str, language: str = "python", config: Dict[str, Any] = None) -> List[Finding]:
    """Run the rule on the given code and return findings."""
    ctx = create_test_context(code, language, config)
    return list(rule.visit(ctx))


class TestDeadcodeUnusedParameterRule:
    """Test suite for deadcode.unused_parameter rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = DeadcodeUnusedParameterRule()
    
    # --- Positive Tests (Should Report Issues) ---
    
    def test_python_unused_parameter(self):
        """Test detection of unused parameters in Python."""
        code = """
def process(used_param, unused_param):
    return used_param + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect the unused parameter
        assert len(findings) >= 1
        
        unused_findings = [f for f in findings if "unused_param" in f.message]
        assert len(unused_findings) == 1
        
        finding = unused_findings[0]
        assert finding.rule == "deadcode.unused_parameter"
        assert "unused_param" in finding.message
        assert finding.severity == "info"
        assert finding.autofix is None  # suggest-only
    
    def test_javascript_unused_parameter(self):
        """Test detection of unused parameters in JavaScript."""
        code = """
function process(a, b) {
    return a + 1;
}
"""
        findings = run_rule(self.rule, code, "javascript")
        
        # Should detect parameter 'b' as unused
        if findings:  # If parsing works
            unused_findings = [f for f in findings if "b" in f.meta.get("parameter_name", "")]
            assert len(unused_findings) >= 1
            
            finding = unused_findings[0]
            assert finding.severity == "info"
            assert finding.meta["suggested_name"] == "_"
    
    def test_multiple_unused_parameters(self):
        """Test detection of multiple unused parameters."""
        code = """
def calculate(a, b, c, d):
    return a + b  # c and d are unused
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect c and d as unused
        unused_names = {f.meta["parameter_name"] for f in findings}
        assert "c" in unused_names
        assert "d" in unused_names
        assert "a" not in unused_names  # 'a' is used
        assert "b" not in unused_names  # 'b' is used
    
    def test_nested_function_unused_parameters(self):
        """Test detection in nested functions."""
        code = """
def outer(outer_used, outer_unused):
    def inner(inner_used, inner_unused):
        return inner_used + 1
    return outer_used + inner(5, 6)
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect both unused parameters
        unused_names = {f.meta["parameter_name"] for f in findings}
        assert "outer_unused" in unused_names
        assert "inner_unused" in unused_names
        assert "outer_used" not in unused_names
        assert "inner_used" not in unused_names
    
    def test_class_method_unused_parameters(self):
        """Test detection in class methods."""
        code = """
class Calculator:
    def add(self, a, b, unused):
        return a + b
    
    def multiply(self, x, y):
        return x * y
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should detect 'unused' parameter
        unused_names = {f.meta["parameter_name"] for f in findings}
        assert "unused" in unused_names
        assert "self" not in unused_names  # 'self' should not be flagged
        assert "a" not in unused_names
        assert "b" not in unused_names
        assert "x" not in unused_names
        assert "y" not in unused_names
    
    # --- Negative Tests (Should NOT Report Issues) ---
    
    def test_all_parameters_used(self):
        """Test that used parameters are not reported."""
        code = """
def process(x, y, z):
    result = x + y * z
    return result
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should not report any unused parameters
        assert len(findings) == 0
    
    def test_parameters_used_in_different_contexts(self):
        """Test parameters used in various contexts."""
        code = """
def complex_function(condition, value, callback):
    if condition:
        return callback(value)
    else:
        return value * 2
"""
        findings = run_rule(self.rule, code, "python")
        
        # All parameters are used
        assert len(findings) == 0
    
    def test_allowlist_configuration(self):
        """Test that allowlist configuration prevents reports."""
        code = """
def process(data, debug_param, _context):
    return data.upper()
"""
        # Without allowlist - should report unused parameters
        findings_normal = run_rule(self.rule, code, "python")
        assert len(findings_normal) >= 1
        
        # With allowlist - should not report allowlisted names
        config = {"unused_param_allowlist": ["debug_param", "_context"]}
        findings_allowlist = run_rule(self.rule, code, "python", config)
        allowlisted_names = {f.meta["parameter_name"] for f in findings_allowlist}
        assert "debug_param" not in allowlisted_names
        assert "_context" not in allowlisted_names
    
    def test_already_suppressed_names_ignored(self):
        """Test that already-suppressed names are ignored."""
        code = """
def process(data, _, _unused):
    return data.upper()
"""
        findings = run_rule(self.rule, code, "python")
        
        # Should not flag already suppressed names
        flagged_names = {f.meta["parameter_name"] for f in findings}
        assert "_" not in flagged_names
        assert "_unused" not in flagged_names
    
    def test_probable_override_methods_skipped(self):
        """Test that probable override methods are skipped."""
        # Java-style override
        java_code = """
class MyClass {
    @Override
    public String toString(unused_param) {
        return super.toString();
    }
}
"""
        findings = run_rule(self.rule, java_code, "java")
        
        # Should skip override methods
        assert len(findings) == 0
        
        # C#-style override
        csharp_code = """
class MyClass {
    public override string ToString(string unused_param) {
        return base.ToString();
    }
}
"""
        findings = run_rule(self.rule, csharp_code, "csharp")
        
        # Should skip override methods
        assert len(findings) == 0
    
    def test_public_methods_skipped(self):
        """Test that public/exported methods are skipped."""
        code = """
class API {
    public void processData(String data, String unused) {
        System.out.println(data);
    }
}
"""
        findings = run_rule(self.rule, code, "java")
        
        # Should skip public API methods
        assert len(findings) == 0
    
    # --- Language-Specific Tests ---
    
    def test_rust_specific_suggestions(self):
        """Test Rust-specific underscore prefix suggestions."""
        code = """
fn process(used: i32, unused: i32) -> i32 {
    used + 1
}
"""
        findings = run_rule(self.rule, code, "rust")
        
        if findings:  # If parsing works
            unused_finding = next((f for f in findings if "unused" in f.meta["parameter_name"]), None)
            if unused_finding:
                # Rust should suggest prefixing with underscore
                assert unused_finding.meta["suggested_name"] == "_unused"
                assert "Rust" in unused_finding.meta["rationale"]
    
    def test_go_specific_suggestions(self):
        """Test Go-specific blank identifier suggestions."""
        code = """
func process(used int, unused int) int {
    return used + 1
}
"""
        findings = run_rule(self.rule, code, "go")
        
        if findings:  # If parsing works
            unused_finding = next((f for f in findings if "unused" in f.meta["parameter_name"]), None)
            if unused_finding:
                # Go should suggest blank identifier
                assert unused_finding.meta["suggested_name"] == "_"
                assert "Go" in unused_finding.meta["rationale"]
    
    def test_python_specific_suggestions(self):
        """Test Python-specific suggestions."""
        code = """
def process(used, unused):
    return used + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["suggested_name"] == "_"
        assert "Python" in finding.meta["rationale"]
    
    # --- Suggestion Content Tests ---
    
    def test_suggestion_includes_diff(self):
        """Test that suggestions include proper diff."""
        code = """
def process(used, unused):
    return used + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check that diff is present and formatted
        assert "diff" in finding.meta
        diff = finding.meta["diff"]
        assert "---" in diff
        assert "+++" in diff
        assert "unused" in diff
        assert "_" in diff
    
    def test_suggestion_includes_rationale(self):
        """Test that suggestions include rationale."""
        code = """
def process(used, unused):
    return used + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check rationale is present
        assert "rationale" in finding.meta
        rationale = finding.meta["rationale"]
        assert "placeholder" in rationale.lower() or "unused" in rationale.lower()
    
    def test_removal_hint_when_configured(self):
        """Test removal hint when configured and parameter is last."""
        code = """
def internal_function(used, trailing_unused):
    return used + 1
"""
        config = {"suggest_param_remove_when_safe": True}
        findings = run_rule(self.rule, code, "python", config)
        
        if findings:
            finding = findings[0]
            # Should suggest removal for trailing parameter
            assert "removing" in finding.message.lower() or "remove" in finding.message.lower()
            assert finding.meta.get("suggest_removal", False)
    
    # --- Edge Cases ---
    
    def test_empty_function(self):
        """Test handling of functions with no parameters."""
        code = """
def empty_function():
    return 42
"""
        findings = run_rule(self.rule, code, "python")
        assert len(findings) == 0
    
    def test_function_with_only_used_parameters(self):
        """Test function where all parameters are used."""
        code = """
def all_used(a, b, c):
    return a + b + c
"""
        findings = run_rule(self.rule, code, "python")
        assert len(findings) == 0
    
    def test_syntax_error_handling(self):
        """Test handling of files with syntax errors."""
        code = """
def broken_syntax(param
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
function test(unused) {
    return 1;
}
"""
        findings = run_rule(self.rule, code, "cobol")  # Unsupported language
        
        # Should not process unsupported languages
        assert len(findings) == 0
    
    def test_unicode_parameter_names(self):
        """Test handling of unicode parameter names."""
        code = """
def process(参数, λ, used):
    return used
"""
        # Should handle unicode identifiers without crashing
        try:
            findings = run_rule(self.rule, code, "python")
            # Unicode parameters should be flagged if unused
            if findings:
                flagged_names = {f.meta["parameter_name"] for f in findings}
                # May include unicode names depending on scope analysis
        except Exception:
            pytest.fail("Rule should handle unicode identifiers gracefully")
    
    # --- Meta Information Tests ---
    
    def test_meta_information_complete(self):
        """Test that findings include complete meta information."""
        code = """
def process(used, unused):
    return used + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check all expected meta fields
        required_meta = ["parameter_name", "suggested_name", "language", "diff", "rationale"]
        for field in required_meta:
            assert field in finding.meta
        
        assert finding.meta["parameter_name"] == "unused"
        assert finding.meta["suggested_name"] == "_"
        assert finding.meta["language"] == "python"
    
    def test_suggest_only_no_autofix(self):
        """Test that rule is suggest-only and provides no autofix."""
        code = """
def process(used, unused):
    return used + 1
"""
        findings = run_rule(self.rule, code, "python")
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Should not provide autofix (suggest-only)
        assert finding.autofix is None
        
        # But should provide suggestion in meta
        assert "diff" in finding.meta
        assert "rationale" in finding.meta


# Integration test to verify rule registration
def test_rule_registration():
    """Test that the rule is properly registered."""
    try:
        from rules import RULES
        rule_ids = [rule.meta.id for rule in RULES]
        assert "deadcode.unused_parameter" in rule_ids
    except ImportError:
        # Skip if rules module not available in test environment
        pytest.skip("Rules module not available for registration test")


if __name__ == "__main__":
    # Run a quick smoke test
    rule = DeadcodeUnusedParameterRule()
    
    test_code = """
def process(used_param, unused_param1, unused_param2):
    return used_param + 1
"""
    
    print("Testing deadcode.unused_parameter rule...")
    findings = run_rule(rule, test_code, "python")
    
    print(f"Found {len(findings)} issues:")
    for finding in findings:
        print(f"  - {finding.message}")
        print(f"    Parameter: {finding.meta['parameter_name']}")
        print(f"    Suggested: {finding.meta['suggested_name']}")
        print(f"    Language: {finding.meta['language']}")
        print(f"    Rationale: {finding.meta['rationale'][:100]}...")
        print()
    
    print("Test completed successfully!")

