"""
Tests for the style.inconsistent_quotes rule.
"""

import pytest
from engine.python_adapter import PythonAdapter
from engine.types import RuleContext
from rules.style_inconsistent_quotes import StyleInconsistentQuotesRule


class TestStyleInconsistentQuotesRule:
    """Test cases for the inconsistent quotes rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleInconsistentQuotesRule()
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

    def test_detects_double_quotes_when_single_expected(self):
        """Test that double quotes are detected when single quotes are expected."""
        code = 'x = "hello"'
        findings = self._run_rule(code, config={"quote_style": "single"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.inconsistent_quotes"
        assert finding.autofix[0].replacement == "'hello'"

    def test_detects_single_quotes_when_double_expected(self):
        """Test that single quotes are detected when double quotes are expected."""
        code = "x = 'hello'"
        findings = self._run_rule(code, config={"quote_style": "double"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.inconsistent_quotes"
        assert finding.autofix[0].replacement == '"hello"'

    def test_no_findings_when_style_consistent(self):
        """Test that consistent styles don't trigger findings."""
        # Single quotes with single preference
        code = "x = 'hello'"
        findings = self._run_rule(code, config={"quote_style": "single"})
        assert len(findings) == 0
        
        # Double quotes with double preference
        code = 'x = "hello"'
        findings = self._run_rule(code, config={"quote_style": "double"})
        assert len(findings) == 0

    def test_default_style_is_single(self):
        """Test that default style is single quotes when no config provided."""
        code = 'x = "hello"'
        findings = self._run_rule(code)  # No config provided
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix[0].replacement == "'hello'"

    def test_skips_strings_with_internal_quotes(self):
        """Test that strings with internal quotes are skipped."""
        code = '''x = "She said 'hello'"'''
        findings = self._run_rule(code, config={"quote_style": "single"})
        # Should be skipped due to internal single quote
        assert len(findings) == 0

    def test_handles_empty_strings(self):
        """Test that empty strings are handled correctly."""
        code = 'x = ""'
        findings = self._run_rule(code, config={"quote_style": "single"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.autofix[0].replacement == "''"

    def test_multiple_strings_in_file(self):
        """Test handling multiple strings in the same file."""
        code = '''x = "hello"
y = "world"'''
        findings = self._run_rule(code, config={"quote_style": "single"})
        
        # Should find 2 issues
        assert len(findings) == 2
        assert all(f.rule == "style.inconsistent_quotes" for f in findings)

    def test_rule_meta_information(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "style.inconsistent_quotes"
        assert self.rule.meta.tier == 0
        assert "python" in self.rule.meta.langs


