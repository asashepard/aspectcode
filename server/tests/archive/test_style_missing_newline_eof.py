"""
Tests for style.missing_newline_eof rule.
"""

import pytest
import sys
import os

# Add server to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.types import RuleContext, Edit
from engine.python_adapter import PythonAdapter
from rules.style_missing_newline_eof import StyleMissingNewlineEofRule


class TestStyleMissingNewlineEofRule:
    """Test cases for the missing newline at EOF rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleMissingNewlineEofRule()
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
    
    def test_missing_newline_triggers(self):
        """Test that files without final newline trigger a finding."""
        code = "def f():\n    print(1)"  # No newline at end
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.missing_newline_eof"
        assert "Missing newline at end of file" in finding.message
        assert finding.severity == "info"
        assert finding.start_byte == len(code)
        assert finding.end_byte == len(code)
    
    def test_file_with_newline_no_findings(self):
        """Test that files with proper newline don't trigger findings."""
        code = "def f():\n    print(1)\n"
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_file_with_crlf_no_findings(self):
        """Test that files ending with CRLF don't trigger findings."""
        code = "def f():\r\n    print(1)\r\n"
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_file_with_cr_no_findings(self):
        """Test that files ending with lone CR don't trigger findings."""
        code = "def f():\r    print(1)\r"
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_empty_file_triggers(self):
        """Test that empty files trigger a finding."""
        code = ""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.missing_newline_eof"
        assert finding.start_byte == 0
        assert finding.end_byte == 0
    
    def test_autofix_appends_lf_by_default(self):
        """Test autofix appends LF by default."""
        code = "def f():\n    print(1)"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        edit = finding.autofix[0]
        assert isinstance(edit, Edit)
        assert edit.replacement == "\n"
        assert edit.start_byte == len(code)
        assert edit.end_byte == len(code)
    
    def test_autofix_respects_crlf_style(self):
        """Test autofix uses CRLF when file contains CRLF."""
        code = "def f():\r\n    print(1)"  # Contains CRLF but missing at end
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        edit = finding.autofix[0]
        assert edit.replacement == "\r\n"
        assert edit.start_byte == len(code)
        assert edit.end_byte == len(code)
    
    def test_autofix_respects_cr_style(self):
        """Test autofix uses CR when file contains lone CR."""
        code = "def f():\r    print(1)"  # Contains CR but missing at end
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        edit = finding.autofix[0]
        assert edit.replacement == "\r"
    
    def test_mixed_line_endings_prefers_crlf(self):
        """Test that CRLF is preferred when both CRLF and LF are present."""
        code = "line1\r\nline2\nline3"  # Mixed line endings, no final newline
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        edit = finding.autofix[0]
        assert edit.replacement == "\r\n"  # Should prefer CRLF
    
    def test_empty_file_autofix(self):
        """Test autofix for empty files."""
        code = ""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        edit = finding.autofix[0]
        assert edit.replacement == "\n"  # Default to LF for empty files
        assert edit.start_byte == 0
        assert edit.end_byte == 0
    
    def test_apply_autofix_simulation(self):
        """Test simulating the application of autofix edits."""
        original = "def f():\n    print(1)"
        findings = self._run_rule(original)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Simulate applying edit
        edit = finding.autofix[0]
        fixed = original[:edit.start_byte] + edit.replacement + original[edit.end_byte:]
        
        expected = "def f():\n    print(1)\n"
        assert fixed == expected
        
        # Re-run rule on fixed text - should have no findings
        fixed_findings = self._run_rule(fixed)
        assert len(fixed_findings) == 0
    
    def test_apply_autofix_crlf_simulation(self):
        """Test autofix simulation with CRLF style."""
        original = "line1\r\nline2"
        findings = self._run_rule(original)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Apply fix
        edit = finding.autofix[0]
        fixed = original[:edit.start_byte] + edit.replacement + original[edit.end_byte:]
        
        expected = "line1\r\nline2\r\n"
        assert fixed == expected
        
        # Verify no more findings
        fixed_findings = self._run_rule(fixed)
        assert len(fixed_findings) == 0
    
    def test_file_level_finding_at_eof(self):
        """Test that finding points to EOF position."""
        code = "def f():\n    print(1)"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.start_byte == len(code)
        assert finding.end_byte == len(code)
    
    def test_meta_information(self):
        """Test that meta information is correctly populated."""
        code = "def f():\r\n    print(1)"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["file_length"] == len(code)
        assert finding.meta["newline_style"] == "\\r\\n"
    
    def test_only_one_finding_per_file(self):
        """Test that only one finding is generated per file."""
        code = "line1\nline2\nline3"  # Multiple lines but missing final newline
        findings = self._run_rule(code)
        
        # Should be exactly one finding regardless of number of lines
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.missing_newline_eof"
    
    def test_single_character_file(self):
        """Test single character files without newline."""
        code = "x"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        edit = finding.autofix[0]
        assert edit.replacement == "\n"
        assert edit.start_byte == 1
        assert edit.end_byte == 1
    
    def test_whitespace_only_file(self):
        """Test files containing only whitespace without newline."""
        code = "   \t  "  # Spaces and tabs but no newline
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        edit = finding.autofix[0]
        assert edit.replacement == "\n"
    
    def test_language_filtering(self):
        """Test that rule only runs on supported languages."""
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_multiple_consecutive_newlines_at_end(self):
        """Test that files ending with newlines don't trigger."""
        # This tests the edge case where files already end with newlines
        code = "def f():\n    print(1)\n\n"  # Multiple newlines at end
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_unicode_content_handling(self):
        """Test that rule handles unicode content correctly."""
        code = "print('こんにちは世界')"  # Unicode without newline
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.missing_newline_eof"
        
        # Apply fix and verify
        edit = finding.autofix[0]
        fixed = code + edit.replacement
        fixed_findings = self._run_rule(fixed)
        assert len(fixed_findings) == 0
    
    def test_very_long_lines(self):
        """Test rule works with very long lines."""
        code = "x = '" + "a" * 10000 + "'"  # Very long line without newline
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.start_byte == len(code)
        assert finding.autofix is not None


if __name__ == "__main__":
    pytest.main([__file__])

