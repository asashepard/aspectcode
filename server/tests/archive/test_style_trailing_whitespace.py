"""
Tests for style.trailing_whitespace rule.
"""

import pytest
import sys
import os

# Add server to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.types import RuleContext, Edit
from engine.python_adapter import PythonAdapter
from rules.style_trailing_whitespace import StyleTrailingWhitespaceRule


class TestStyleTrailingWhitespaceRule:
    """Test cases for the trailing whitespace rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleTrailingWhitespaceRule()
        self.adapter = PythonAdapter()
    
    def _run_rule(self, code: str):
        """Helper to run the rule on code and return findings."""
        tree = self.adapter.parse(code)
        if not tree:
            pytest.skip("Tree-sitter parser not available")
        
        ctx = RuleContext(
            file_path="test.py",
            text=code,
            tree=tree,
            adapter=self.adapter,
            config={}
        )
        
        return list(self.rule.visit(ctx))
    
    def test_trailing_spaces_triggers(self):
        """Test that trailing spaces trigger a finding."""
        code = """def f():
    print(1)    
    print(2)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert "Trailing whitespace found" in finding.message
        assert finding.severity == "info"
        assert finding.meta["affected_lines"] == 1
    
    def test_trailing_tabs_triggers(self):
        """Test that trailing tabs trigger a finding."""
        code = """def f():
    print(1)\t\t
    print(2)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 1
    
    def test_mixed_trailing_whitespace_triggers(self):
        """Test that mixed trailing spaces and tabs trigger a finding."""
        code = """def f():
    print(1) \t 
    print(2)\t  
    print(3)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 2
    
    def test_no_trailing_whitespace_no_findings(self):
        """Test that code without trailing whitespace doesn't trigger findings."""
        code = """def f():
    print(1)
    print(2)
    if True:
        print(3)
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_empty_lines_no_findings(self):
        """Test that empty lines without trailing whitespace don't trigger."""
        code = """def f():
    print(1)

    print(2)
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_trailing_whitespace_on_blank_lines(self):
        """Test that trailing whitespace on blank lines is detected."""
        code = """def f():
    print(1)
   
    print(2)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 1
    
    def test_multiple_lines_with_trailing_whitespace(self):
        """Test multiple lines with trailing whitespace."""
        code = """def f():  
    print(1)    
    print(2)\t
    print(3) \t 
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 4  # All 4 lines have trailing whitespace
    
    def test_autofix_removes_trailing_spaces(self):
        """Test autofix removes trailing spaces."""
        code = "def f():    \n    print(1)\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        edit = finding.autofix[0]
        assert isinstance(edit, Edit)
        assert edit.replacement == ""
        # Verify it's removing the trailing spaces after the colon
        assert code[edit.start_byte:edit.end_byte] == "    "
    
    def test_autofix_removes_trailing_tabs(self):
        """Test autofix removes trailing tabs."""
        code = "def f():\t\t\n    print(1)\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        edit = finding.autofix[0]
        assert edit.replacement == ""
        assert code[edit.start_byte:edit.end_byte] == "\t\t"
    
    def test_autofix_preserves_line_endings(self):
        """Test that autofix preserves different line endings."""
        # Test with \r\n line endings
        code = "def f():    \r\n    print(1)\r\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Apply autofix manually to verify
        text = code
        for edit in finding.autofix:
            text = text[:edit.start_byte] + edit.replacement + text[edit.end_byte:]
        
        # Should preserve \r\n line endings
        assert "\r\n" in text
        assert text == "def f():\r\n    print(1)\r\n"
    
    def test_different_line_endings(self):
        """Test handling of different line ending styles."""
        # Mix of \n and \r\n
        code = "def f():    \n    print(1)  \r\n    print(2)\t\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["affected_lines"] == 3
        assert finding.autofix is not None
        assert len(finding.autofix) == 3
    
    def test_trailing_whitespace_at_eof(self):
        """Test trailing whitespace at end of file without newline."""
        code = "def f():\n    print(1)   "  # No newline at end
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 1
    
    def test_autofix_sorting_multiple_edits(self):
        """Test that multiple autofix edits are sorted correctly."""
        code = """def f():    
    print(1)  
    print(2)\t
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) >= 2
        
        # Edits should be sorted by start_byte in descending order
        edits = finding.autofix
        for i in range(len(edits) - 1):
            assert edits[i].start_byte >= edits[i + 1].start_byte
    
    def test_apply_autofix_simulation(self):
        """Test simulating the application of autofix edits."""
        original = """def f():    
    print(1)  
    print(2)
"""
        findings = self._run_rule(original)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Simulate applying edits
        text = original
        for edit in finding.autofix:
            text = text[:edit.start_byte] + edit.replacement + text[edit.end_byte:]
        
        expected = """def f():
    print(1)
    print(2)
"""
        assert text == expected
        
        # Re-run rule on fixed text - should have no findings
        fixed_findings = self._run_rule(text)
        assert len(fixed_findings) == 0
    
    def test_edge_case_only_whitespace_line(self):
        """Test edge case with line containing only whitespace."""
        code = "def f():\n    \t  \n    print(1)\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["affected_lines"] == 1
        
        # Apply fix
        text = code
        for edit in finding.autofix:
            text = text[:edit.start_byte] + edit.replacement + text[edit.end_byte:]
        
        # Should result in an empty line but preserve the newline
        assert text == "def f():\n\n    print(1)\n"
    
    def test_file_level_finding_range(self):
        """Test that the finding covers the entire file."""
        code = "def f():    \n    print(1)\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.start_byte == 0
        assert finding.end_byte == len(code)
    
    def test_no_false_positives_with_indentation(self):
        """Test that leading indentation is not considered trailing whitespace."""
        code = """def f():
    if True:
        print(1)
        print(2)
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_language_filtering(self):
        """Test that rule only runs on supported languages."""
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_meta_bytes_trimmed_calculation(self):
        """Test that meta information correctly calculates bytes trimmed."""
        code = "def f():    \n    print(1)  \n"  # 4 spaces + 2 spaces = 6 bytes
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["total_bytes_trimmed"] == 6
    
    def test_unicode_content_handling(self):
        """Test that rule handles unicode content correctly."""
        code = "def f():\n    print('こんにちは')    \n    print('世界')\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_whitespace"
        assert finding.meta["affected_lines"] == 1


if __name__ == "__main__":
    pytest.main([__file__])

