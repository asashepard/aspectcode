"""
Tests for the excessive blank lines rule.
"""

import pytest
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from engine.types import RuleContext
    from engine.python_adapter import PythonAdapter
    from rules.style_blank_lines_excessive import StyleBlankLinesExcessiveRule
except ImportError:
    # Fallback import strategy
    import sys
    sys.path.append('..')
    from engine.types import RuleContext
    from engine.python_adapter import PythonAdapter
    from rules.style_blank_lines_excessive import StyleBlankLinesExcessiveRule


class TestStyleBlankLinesExcessiveRule:
    """Test cases for the excessive blank lines rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleBlankLinesExcessiveRule()
        self.adapter = PythonAdapter()
    
    def _run_rule(self, code: str, config: dict = None):
        """Helper to run the rule on code and return findings."""
        tree = self.adapter.parse(code)
        if not tree:
            pytest.skip("Tree-sitter parser not available")
        
        ctx = RuleContext(
            file_path="test.py",
            text=code,
            tree=tree,
            adapter=self.adapter,
            config=config or {}
        )
        
        return list(self.rule.visit(ctx))
    
    def _apply_autofix(self, code: str, findings):
        """Apply autofix edits to code and return the result."""
        if not findings or not findings[0].autofix:
            return code
        
        # Apply edits in reverse order (should already be sorted that way)
        result = code
        for edit in findings[0].autofix:
            result_bytes = result.encode('utf-8')
            new_bytes = (result_bytes[:edit.start_byte] + 
                        edit.replacement.encode('utf-8') + 
                        result_bytes[edit.end_byte:])
            result = new_bytes.decode('utf-8')
        
        return result
    
    def test_detects_multiple_blank_lines(self):
        """Test that multiple consecutive blank lines are detected."""
        code = "def func1():\n    pass\n\n\n\ndef func2():\n    pass\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.blank_lines.excessive"
        assert "Excessive blank lines" in finding.message
        assert finding.autofix is not None
        assert len(finding.autofix) > 0
    
    def test_no_detection_single_blank_lines(self):
        """Test that single blank lines are not flagged."""
        code = "def func1():\n    pass\n\ndef func2():\n    pass\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 0
    
    def test_no_detection_no_blank_lines(self):
        """Test that code with no blank lines is not flagged."""
        code = "def func1():\n    pass\ndef func2():\n    pass\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 0
    
    def test_autofix_collapses_to_single_blank_line(self):
        """Test that autofix collapses multiple blank lines to one."""
        code = "line1\n\n\n\nline2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\n\nline2\n"
        assert fixed_code == expected
        
        # Verify no more issues after fix
        findings_after = self._run_rule(fixed_code)
        assert len(findings_after) == 0
    
    def test_preserves_crlf_line_endings(self):
        """Test that CRLF line endings are preserved."""
        code = "line1\r\n\r\n\r\n\r\nline2\r\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\r\n\r\nline2\r\n"
        assert fixed_code == expected
    
    def test_handles_blank_lines_with_spaces(self):
        """Test that lines with only spaces are treated as blank."""
        code = "line1\n\n   \n\t\n\nline2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\n\nline2\n"
        assert fixed_code == expected
    
    def test_handles_blank_lines_with_tabs(self):
        """Test that lines with only tabs are treated as blank."""
        code = "line1\n\n\t\t\n\nline2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\n\nline2\n"
        assert fixed_code == expected
    
    def test_multiple_runs_of_blank_lines(self):
        """Test handling multiple separate runs of blank lines."""
        code = "func1\n\n\n\nfunc2\n\n\n\n\nfunc3\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "func1\n\nfunc2\n\nfunc3\n"
        assert fixed_code == expected
    
    def test_blank_lines_at_file_start(self):
        """Test handling blank lines at the start of the file."""
        code = "\n\n\nfunc1\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "\nfunc1\n"
        assert fixed_code == expected
    
    def test_blank_lines_at_file_end(self):
        """Test handling blank lines at the end of the file."""
        code = "func1\n\n\n\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "func1\n\n"
        assert fixed_code == expected
    
    def test_mixed_line_endings_preserved(self):
        """Test that mixed line endings are preserved correctly."""
        code = "line1\n\n\r\n\nline2\r\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        # Should preserve the original line ending style for each line
        expected = "line1\n\nline2\r\n"
        assert fixed_code == expected
    
    def test_empty_file_no_findings(self):
        """Test that empty files don't trigger findings."""
        code = ""
        findings = self._run_rule(code)
        
        assert len(findings) == 0
    
    def test_only_blank_lines_file(self):
        """Test a file with only blank lines."""
        code = "\n\n\n\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "\n"
        assert fixed_code == expected
    
    def test_meta_information(self):
        """Test that finding metadata is properly set."""
        code = "line1\n\n\n\nline2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.severity == "info"
        assert "runs_collapsed" in finding.meta
        assert finding.meta["runs_collapsed"] > 0
        assert "description" in finding.meta
    
    def test_large_number_of_blank_lines(self):
        """Test handling a large number of consecutive blank lines."""
        code = "line1\n" + "\n" * 10 + "line2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\n\nline2\n"
        assert fixed_code == expected
    
    def test_language_filtering(self):
        """Test that the rule works across different supported languages."""
        # Since we're using PythonAdapter, this tests the concept
        # In practice, different adapters would be used for different languages
        code = "function test() {\n}\n\n\n\nfunction test2() {\n}\n"
        findings = self._run_rule(code)
        
        # Should still work even with non-Python syntax
        assert len(findings) == 1
    
    def test_edge_case_cr_only_line_endings(self):
        """Test handling of CR-only line endings (rare but possible)."""
        code = "line1\r\r\r\rline2\r"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\r\rline2\r"
        assert fixed_code == expected
    
    def test_whitespace_only_lines_various_types(self):
        """Test various types of whitespace-only lines."""
        code = "line1\n\n \n\t\n \t \n\nline2\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        expected = "line1\n\nline2\n"
        assert fixed_code == expected
    
    def test_real_world_python_code(self):
        """Test with realistic Python code structure."""
        code = '''import os
import sys


class TestClass:
    """A test class."""
    
    def __init__(self):
        self.value = 42


    def method1(self):
        """First method."""
        return self.value




    def method2(self):
        """Second method."""
        return self.value * 2


if __name__ == "__main__":
    test = TestClass()
    print(test.method1())
'''
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        fixed_code = self._apply_autofix(code, findings)
        
        # Verify the structure is preserved but excessive blanks are removed
        assert "import os" in fixed_code
        assert "class TestClass:" in fixed_code
        assert fixed_code.count("\n\n\n") == 0  # No triple newlines should remain
        
        # Should still have some double newlines for proper separation
        assert "\n\n" in fixed_code

