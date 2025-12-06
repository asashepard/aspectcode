"""
Tests for Python Identity vs Equality Comparison Rule

Tests various scenarios where 'is'/'is not' operators are used incorrectly
for value comparisons and verifies that the rule correctly identifies
problematic patterns while avoiding false positives on legitimate identity checks.
"""

import unittest
from unittest.mock import Mock
from rules.bug_python_is_vs_eq import BugPythonIsVsEqRule
from engine.types import RuleContext


class TestBugPythonIsVsEqRule(unittest.TestCase):
    """Test cases for the Python 'is' vs '==' detection rule."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugPythonIsVsEqRule()
    
    def _create_context(self, code: str, filename: str = "test.py") -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = "python"
        context.file_path = filename
        context.syntax_tree = None  # We're using text-based analysis
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.python_is_vs_eq"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "safe"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.langs == ["python"]
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires syntax analysis."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_string_comparison(self):
        """Test 'is' used with string literal (should be flagged)."""
        code = '''
if x is "ok":
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert "Use '==' / '!=' for value comparison" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["operator"] == "is"
        assert finding.meta["replacement"] == "=="
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        assert finding.autofix[0].replacement == "=="
    
    def test_positive_case_number_comparison(self):
        """Test 'is' used with number literal (should be flagged)."""
        code = '''
if n is 0:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert "Use '==' / '!=' for value comparison" in finding.message
        assert finding.meta["operator"] == "is"
        assert finding.meta["replacement"] == "=="
    
    def test_positive_case_is_not_number(self):
        """Test 'is not' used with number literal (should be flagged)."""
        code = '''
if x is not 3.14:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert "Use '==' / '!=' for value comparison" in finding.message
        assert finding.meta["operator"] == "is not"
        assert finding.meta["replacement"] == "!="
        assert finding.autofix[0].replacement == "!="
    
    def test_positive_case_float_comparison(self):
        """Test 'is' used with float literal (should be flagged)."""
        code = '''
if temperature is 98.6:
    print("Normal")
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["operator"] == "is"
        assert finding.meta["replacement"] == "=="
    
    def test_positive_case_multiple_literals(self):
        """Test multiple different literal types (should all be flagged)."""
        code = '''
if x is "hello":
    pass
if y is 42:
    pass
if z is not 3.14:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 3
        
        # Check each finding
        operators = [f.meta["operator"] for f in findings]
        assert "is" in operators
        assert "is not" in operators
        
        replacements = [f.meta["replacement"] for f in findings]
        assert "==" in replacements
        assert "!=" in replacements
    
    def test_positive_case_parenthesized_literals(self):
        """Test 'is' with parenthesized literals (should be flagged)."""
        code = '''
if (x) is ("hello"):
    pass
if (value) is not (42):
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 2
        for finding in findings:
            assert "Use '==' / '!=' for value comparison" in finding.message
    
    def test_negative_case_none_comparison(self):
        """Test 'is' used with None (should NOT be flagged)."""
        code = '''
if x is None:
    pass
if y is not None:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since None comparisons are legitimate
        assert len(findings) == 0
    
    def test_negative_case_other_singletons(self):
        """Test 'is' used with other singletons (should NOT be flagged)."""
        code = '''
if result is NotImplemented:
    pass
if value is Ellipsis:
    pass
if flag is True:
    pass
if flag is False:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since these are singleton comparisons
        assert len(findings) == 0
    
    def test_negative_case_object_identity(self):
        """Test 'is' used for legitimate object identity (should NOT be flagged)."""
        code = '''
if a is b:
    pass
if obj is not other_obj:
    pass
if self.attr is some_var:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since these are legitimate identity checks
        assert len(findings) == 0
    
    def test_negative_case_variable_comparisons(self):
        """Test 'is' used between variables (should NOT be flagged)."""
        code = '''
if first_item is last_item:
    pass
if current_node is not previous_node:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since these are variable identity checks
        assert len(findings) == 0
    
    def test_negative_case_comments_ignored(self):
        """Test that comments with 'is' patterns are ignored."""
        code = '''
# This is a comment: if x is "bad":
# Another comment: value is not 42
def good_function():
    if x is None:  # This should not be flagged
        return True
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since problematic patterns are in comments
        assert len(findings) == 0
    
    def test_complex_expressions(self):
        """Test 'is' with more complex expressions."""
        code = '''
if result.value is "expected":
    pass
if len(items) is not 0:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should flag both since we're comparing with literals
        assert len(findings) == 2
    
    def test_different_literal_types(self):
        """Test various literal types that should be flagged."""
        code = '''
# String literals
if x is "double_quotes":
    pass
if y is 'single_quotes':
    pass

# Numeric literals
if count is 0:
    pass
if value is -42:
    pass
if pi is 3.14159:
    pass
if imaginary is 1j:
    pass

# Special numeric formats
if hex_val is 0xFF:
    pass
if binary is 0b1010:
    pass
if octal is 0o755:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should flag all literal comparisons
        assert len(findings) >= 8  # At least 8 different literal types
        
        for finding in findings:
            assert finding.meta["operator"] in ["is", "is not"]
            assert finding.meta["replacement"] in ["==", "!="]
    
    def test_autofix_functionality(self):
        """Test that autofix correctly transforms 'is' to '=='."""
        code = 'if x is "hello":\n    pass'
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        edit = finding.autofix[0]
        
        # Apply the edit to verify it works correctly
        original_bytes = code.encode('utf-8')
        fixed_bytes = (original_bytes[:edit.start_byte] + 
                      edit.replacement.encode('utf-8') + 
                      original_bytes[edit.end_byte:])
        fixed_code = fixed_bytes.decode('utf-8')
        
        assert 'if x == "hello":' in fixed_code
        assert 'is' not in fixed_code.split('\n')[0]  # 'is' should be replaced in first line
    
    def test_autofix_is_not_functionality(self):
        """Test that autofix correctly transforms 'is not' to '!='."""
        code = 'if x is not 42:\n    pass'
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        edit = finding.autofix[0]
        
        # Apply the edit to verify it works correctly
        original_bytes = code.encode('utf-8')
        fixed_bytes = (original_bytes[:edit.start_byte] + 
                      edit.replacement.encode('utf-8') + 
                      original_bytes[edit.end_byte:])
        fixed_code = fixed_bytes.decode('utf-8')
        
        assert 'if x != 42:' in fixed_code
        assert 'is not' not in fixed_code
    
    def test_idempotency(self):
        """Test that applying autofix doesn't create new findings."""
        code = 'if x is "test":\n    pass'
        ctx = self._create_context(code)
        
        # First pass
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        
        # Apply the fix
        edit = findings[0].autofix[0]
        original_bytes = code.encode('utf-8')
        fixed_bytes = (original_bytes[:edit.start_byte] + 
                      edit.replacement.encode('utf-8') + 
                      original_bytes[edit.end_byte:])
        fixed_code = fixed_bytes.decode('utf-8')
        
        # Second pass on fixed code
        ctx_fixed = self._create_context(fixed_code)
        findings_after_fix = list(self.rule.visit(ctx_fixed))
        
        # Should have no findings after fix is applied
        assert len(findings_after_fix) == 0
    
    def test_byte_position_accuracy(self):
        """Test that byte positions are calculated correctly."""
        code = 'x = 1\nif y is "test":\n    pass'
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Extract the flagged text using byte positions
        code_bytes = code.encode('utf-8')
        flagged_text = code_bytes[finding.start_byte:finding.end_byte].decode('utf-8')
        
        assert flagged_text == "is"
    
    def test_multiple_comparisons_same_line(self):
        """Test multiple 'is' comparisons on the same line."""
        code = 'if a is "x" and b is "y": pass'
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should detect both 'is' comparisons
        assert len(findings) == 2
        
        # Verify both are flagged correctly
        for finding in findings:
            assert finding.meta["operator"] == "is"
            assert finding.meta["replacement"] == "=="
    
    def test_edge_case_chained_comparisons(self):
        """Test chained comparisons with mixed patterns."""
        code = '''
if a is "x" is b:
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should detect the comparison with string literal
        assert len(findings) >= 1
    
    def test_unsupported_language_ignored(self):
        """Test that non-Python languages are ignored."""
        code = 'if (x is "hello") { }'
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = "javascript"
        context.file_path = "test.js"
        context.syntax_tree = None
        
        findings = list(self.rule.visit(context))
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_string_types_detection(self):
        """Test detection of various string literal formats."""
        code = '''
if x is "double":
    pass
if y is 'single':
    pass
if z is """triple_double""":
    pass
if w is \'\'\'triple_single\'\'\':
    pass
if a is b"bytes":
    pass
if c is r"raw":
    pass
if d is f"formatted":
    pass
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should flag all string literal comparisons
        assert len(findings) == 7
        
        for finding in findings:
            assert finding.meta["replacement"] == "=="
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = 'if x is "test":\n    pass'
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check finding properties
        assert finding.rule == "bug.python_is_vs_eq"
        assert finding.file == "test.py"
        assert finding.severity == "warning"
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        assert finding.start_byte < finding.end_byte
        assert "operator" in finding.meta
        assert "replacement" in finding.meta
        assert finding.meta["language"] == "python"


if __name__ == "__main__":
    unittest.main()

