"""
Tests for style.max_line_length rule.
"""

import pytest
import sys
import os

# Add server to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.types import RuleContext, Edit
from engine.python_adapter import PythonAdapter
from rules.style_max_line_length import StyleMaxLineLengthRule, DEFAULT_MAX


class TestStyleMaxLineLengthRule:
    """Test cases for the max line length rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleMaxLineLengthRule()
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
    
    def _make_long_line(self, n: int) -> str:
        """Generate a line of exactly n characters."""
        # "x = '" is 5 chars, "'" is 1 char, so we need n-6 content chars
        content_chars = max(0, n - 6)
        return "x = '" + "a" * content_chars + "'"
    
    def test_long_line_triggers(self):
        """Test that lines exceeding default limit trigger findings."""
        long_line = self._make_long_line(140)  # 140 > 120
        code = f"{long_line}\nprint('short line')\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.max_line_length"
        assert "exceeds max length" in finding.message
        assert "140>120" in finding.message
        assert finding.severity == "info"
        assert finding.meta["actual_length"] == 140
        assert finding.meta["max_length"] == DEFAULT_MAX
        assert finding.meta["line_number"] == 1
    
    def test_short_lines_no_findings(self):
        """Test that lines within limit don't trigger findings."""
        code = """def short_function():
    print("This is a short line")
    return True
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_exactly_at_limit_no_findings(self):
        """Test that lines exactly at the limit don't trigger."""
        line_at_limit = self._make_long_line(DEFAULT_MAX)  # Exactly 120 chars
        code = f"{line_at_limit}\n"
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_multiple_long_lines(self):
        """Test multiple long lines trigger multiple findings."""
        long_line1 = self._make_long_line(130)
        long_line2 = self._make_long_line(140)
        code = f"{long_line1}\nprint('short')\n{long_line2}\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 2
        assert findings[0].meta["line_number"] == 1
        assert findings[1].meta["line_number"] == 3
        assert findings[0].meta["actual_length"] == 130
        assert findings[1].meta["actual_length"] == 140
    
    def test_custom_max_length_config(self):
        """Test custom max length configuration."""
        code = self._make_long_line(100) + "\n"  # 100 chars
        
        # With default limit (120), should not trigger
        findings_default = self._run_rule(code)
        assert len(findings_default) == 0
        
        # With custom limit (80), should trigger
        findings_custom = self._run_rule(code, config={'style.max_line_length.limit': 80})
        assert len(findings_custom) == 1
        assert findings_custom[0].meta["max_length"] == 80
        assert "100>80" in findings_custom[0].message
    
    def test_suggestion_metadata_present(self):
        """Test that suggestions are included in metadata."""
        long_line = self._make_long_line(140)
        code = f"{long_line}\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert "suggestion" in finding.meta
        assert "diff" in finding.meta["suggestion"]
        assert "rationale" in finding.meta["suggestion"]
        assert finding.meta["suggestion"]["diff"]  # Should not be empty
        assert finding.meta["suggestion"]["rationale"]  # Should not be empty
    
    def test_string_literal_suggestion(self):
        """Test suggestion for long string literals."""
        code = 'message = "This is a very long string literal that exceeds the maximum line length and should be wrapped appropriately for testing purposes"\n'
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        assert "string" in suggestion["rationale"].lower()
        assert "concatenation" in suggestion["rationale"].lower() or "wrap" in suggestion["rationale"].lower()
    
    def test_import_statement_suggestion(self):
        """Test suggestion for long import statements."""
        code = 'from very.long.module.name.that.exceeds.the.maximum.line.length.limit import function1, function2, function3, function4, function5\n'
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        assert "import" in suggestion["rationale"].lower()
    
    def test_method_chain_suggestion(self):
        """Test suggestion for long method chains."""
        code = 'result = obj.method1().method2().method3().method4().method5().method6().method7().method8().method9().method10().final_method()\n'
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        assert "method" in suggestion["rationale"].lower() or "chain" in suggestion["rationale"].lower()
    
    def test_diff_format(self):
        """Test that diff is properly formatted."""
        long_line = self._make_long_line(140)
        code = f"{long_line}\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        diff = findings[0].meta["suggestion"]["diff"]
        
        # Check diff format
        assert "--- a/current_line" in diff
        assert "+++ b/current_line" in diff
        assert f"-{long_line}" in diff
        assert diff.count('\n') >= 3  # Should have multiple lines
    
    def test_no_autofix_edits(self):
        """Test that rule doesn't provide direct autofix edits (suggest-only)."""
        long_line = self._make_long_line(140)
        code = f"{long_line}\n"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is None  # Should not provide direct edits
    
    def test_line_with_mixed_content(self):
        """Test line with mixed content (code + comment)."""
        code = 'def function_with_very_long_name(param1, param2, param3, param4):  # This is a very long comment that makes the line exceed the limit\n'
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["line_number"] == 1
        assert finding.meta["actual_length"] > DEFAULT_MAX
    
    def test_empty_lines_ignored(self):
        """Test that empty lines don't trigger false positives."""
        code = f"""
{self._make_long_line(140)}



{self._make_long_line(130)}
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 2  # Only the two long lines
        assert findings[0].meta["line_number"] == 2
        assert findings[1].meta["line_number"] == 6
    
    def test_unicode_content_handling(self):
        """Test that unicode content is handled correctly."""
        # Unicode characters might have different byte vs character lengths
        code = "message = 'これは非常に長い日本語のメッセージで、最大行長制限を超える可能性があります。追加のテキストを含めて確実に制限を超えるようにします。'\n"
        findings = self._run_rule(code)
        
        # Should trigger if the visual length exceeds limit
        if len(code.strip()) > DEFAULT_MAX:
            assert len(findings) == 1
            finding = findings[0]
            assert finding.rule == "style.max_line_length"
    
    def test_tabs_vs_spaces_length_calculation(self):
        """Test that tabs are counted correctly in length calculation."""
        # Line with tabs that might affect length calculation
        code = f"\t\t\t{self._make_long_line(130)}\n"  # Tabs + long content
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        # Length should include the tabs
        assert finding.meta["actual_length"] > 130
    
    def test_different_line_endings(self):
        """Test handling of different line ending styles."""
        long_line = self._make_long_line(140)
        
        # Test with \n
        code_lf = f"{long_line}\nshort\n"
        findings_lf = self._run_rule(code_lf)
        
        # Test with \r\n
        code_crlf = f"{long_line}\r\nshort\r\n"
        findings_crlf = self._run_rule(code_crlf)
        
        # Both should detect the same long line
        assert len(findings_lf) == 1
        assert len(findings_crlf) == 1
        assert findings_lf[0].meta["actual_length"] == findings_crlf[0].meta["actual_length"]
    
    def test_finding_byte_positions(self):
        """Test that finding byte positions are correct."""
        short_line = "short\n"
        long_line = self._make_long_line(140)
        code = f"{short_line}{long_line}\n"
        
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        
        # Check that start_byte points to beginning of long line
        assert finding.start_byte == len(short_line)
        # Check that end_byte points to end of long line content (excluding newline)
        assert finding.end_byte == len(short_line) + len(long_line)
    
    def test_language_filtering(self):
        """Test that rule only runs on supported languages."""
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_break_point_detection(self):
        """Test break point detection with various delimiters."""
        rule = self.rule
        
        # Test comma break point
        line_comma = "function(param1, param2, very_long_parameter_name_that_exceeds_limit)"
        break_point = rule._find_break_point(line_comma, 50)
        assert break_point > 0
        assert line_comma[break_point-1] == ','
        
        # Test space break point
        line_space = "this is a very long line with many words that should be broken at spaces"
        break_point = rule._find_break_point(line_space, 30)
        assert break_point > 0
    
    def test_suggestion_rationale_variety(self):
        """Test that different types of lines get appropriate rationales."""
        test_cases = [
            ('x = "very long string literal that exceeds the maximum line length limit"', "string"),
            ('from very.long.module import func1, func2, func3', "import"),
            ('obj.method1().method2().method3().method4()', "method"),
            ('regular_long_line_with_no_special_content_just_text', "wrap"),
        ]
        
        for code, expected_keyword in test_cases:
            if len(code) <= DEFAULT_MAX:
                code += "x" * (DEFAULT_MAX - len(code) + 10)  # Make it long enough
            
            findings = self._run_rule(code + "\n")
            if findings:  # Only check if it actually triggered
                rationale = findings[0].meta["suggestion"]["rationale"].lower()
                assert expected_keyword in rationale, f"Expected '{expected_keyword}' in rationale for: {code[:50]}..."


if __name__ == "__main__":
    pytest.main([__file__])

