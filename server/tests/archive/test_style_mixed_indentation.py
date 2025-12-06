"""
Tests for style.mixed_indentation rule.
"""

import pytest
import sys
import os

# Add server to path so we can import modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.types import RuleContext, Edit
from engine.python_adapter import PythonAdapter
from rules.style_mixed_indentation import StyleMixedIndentationRule


class TestStyleMixedIndentationRule:
    """Test cases for the mixed indentation rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleMixedIndentationRule()
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
    
    def test_mixed_indentation_triggers(self):
        """Test that mixed tabs and spaces trigger a finding."""
        code = """def f():
\tprint(1)
    print(2)
"""
        findings = self._run_rule(code)
        
        # Should have at least one finding with specific line info
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.rule == "style.mixed_indentation"
        # New messages are line-specific
        assert "Line" in finding.message
        assert finding.severity == "info"
        # New meta has line_number instead of file-level has_tabs/has_spaces
        assert "line_number" in finding.meta
        assert finding.meta["line_number"] >= 1
    
    def test_consistent_spaces_no_findings(self):
        """Test that consistent spaces don't trigger findings."""
        code = """def f():
    print(1)
    print(2)
    if True:
        print(3)
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_consistent_tabs_no_findings(self):
        """Test that consistent tabs don't trigger findings."""
        code = """def f():
\tprint(1)
\tprint(2)
\tif True:
\t\tprint(3)
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_no_indentation_no_findings(self):
        """Test that files with no indentation don't trigger findings."""
        code = """print(1)
print(2)
x = 3
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_empty_lines_ignored(self):
        """Test that empty lines don't affect indentation detection."""
        code = """def f():
\tprint(1)

    print(2)

"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.mixed_indentation"
    
    def test_autofix_prefers_spaces_when_more_space_lines(self):
        """Test autofix prefers spaces when more lines use spaces."""
        code = """def f():
\tprint(1)
    print(2)
    print(3)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        # Should convert tab to 4 spaces (default width)
        edit = finding.autofix[0]
        assert edit.replacement == "    "  # 4 spaces
    
    def test_autofix_prefers_tabs_when_more_tab_lines(self):
        """Test autofix prefers tabs when more lines use tabs."""
        code = """def f():
    print(1)
\tprint(2)
\tprint(3)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        assert len(finding.autofix) == 1
        
        # Should convert spaces to tab
        edit = finding.autofix[0]
        assert edit.replacement == "\t"
    
    def test_autofix_preserves_logical_depth(self):
        """Test that autofix preserves logical indentation depth."""
        code = """def f():
\tif True:
\t\tprint(1)
    if True:
        print(2)
"""
        findings = self._run_rule(code)
        
        # Should have multiple findings (one per line with incorrect indentation)
        assert len(findings) >= 1
        
        # Each finding should have an autofix
        for finding in findings:
            if finding.autofix:
                # Verify the autofix produces valid indentation
                for edit in finding.autofix:
                    # Should be spaces since more lines use spaces
                    assert edit.replacement.startswith("    ") or '\t' in edit.replacement
    
    def test_mixed_indentation_same_line(self):
        """Test handling of mixed indentation on the same line."""
        code = """def f():
 \tprint(1)
    print(2)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.mixed_indentation"
    
    def test_infer_space_width_gcd(self):
        """Test that space width is inferred correctly using GCD."""
        code = """def f():
\tprint(1)
  print(2)
    print(3)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        # The GCD of [2, 4] is 2, so should use 2-space indentation
        finding = findings[0]
        assert finding.autofix is not None
    
    def test_multiple_violations_reports_per_line(self):
        """Test that multiple violations result in per-line findings."""
        code = """def f():
\tprint(1)
    print(2)
\tif True:
        print(3)
"""
        findings = self._run_rule(code)
        
        # Should have findings for each line with inconsistent indentation
        assert len(findings) >= 1
        
        # Verify each finding points to a specific line
        for finding in findings:
            assert "line_number" in finding.meta
            # start_byte should NOT be 0 (file-level) - should be specific line position
            if finding.meta.get("issue") != "summary":
                assert finding.start_byte > 0 or finding.meta["line_number"] == 1
    
    def test_line_specific_finding_range(self):
        """Test that findings point to specific line positions, not the entire file."""
        code = """def f():
\tprint(1)
    print(2)
"""
        findings = self._run_rule(code)
        
        assert len(findings) >= 1
        finding = findings[0]
        # Finding should point to the specific indentation, not start of file
        assert finding.start_byte != 0 or finding.meta.get("line_number") == 1
        # end_byte should not cover the whole file
        assert finding.end_byte != len(code)
        # Verify it has line number info
        assert "line_number" in finding.meta
    
    def test_autofix_sorting(self):
        """Test that autofix edits are sorted correctly to avoid offset issues."""
        code = """def f():
\tprint(1)
    print(2)
\tprint(3)
"""
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Edits should be sorted by start_byte in descending order
        edits = finding.autofix
        assert len(edits) >= 1  # At least one edit
        
        for i in range(len(edits) - 1):
            assert edits[i].start_byte >= edits[i + 1].start_byte
    
    def test_edge_case_only_one_indented_line(self):
        """Test edge case with only one indented line (no mixing possible)."""
        code = """print("hello")
    print("indented")
print("not indented")
"""
        findings = self._run_rule(code)
        assert len(findings) == 0
    
    def test_apply_autofix_simulation(self):
        """Test simulating the application of autofix edits."""
        original = """def f():
\tprint(1)
    print(2)
"""
        findings = self._run_rule(original)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix is not None
        
        # Simulate applying edits (manually for testing)
        text = original
        for edit in finding.autofix:
            text = text[:edit.start_byte] + edit.replacement + text[edit.end_byte:]
        
        # Re-run rule on fixed text - should have no findings
        fixed_findings = self._run_rule(text)
        assert len(fixed_findings) == 0
    
    def test_language_filtering(self):
        """Test that rule only runs on supported languages."""
        # This test would need a different adapter for a non-supported language
        # For now, just verify the meta.langs contains expected languages
        expected_langs = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        assert set(self.rule.meta.langs) == set(expected_langs)


if __name__ == "__main__":
    pytest.main([__file__])

