"""
Tests for the style.redundant_semicolons rule that removes redundant semicolons.
"""

import pytest
from rules.style_redundant_semicolons import StyleRedundantSemicolonsRule


class TestStyleRedundantSemicolonsRule:
    """Test cases for the redundant semicolons rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = StyleRedundantSemicolonsRule()

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        meta = self.rule.meta
        assert meta.id == "style.redundant_semicolons"
        assert meta.category == "style" 
        assert meta.tier == 0
        assert meta.priority == "P3"
        assert meta.autofix_safety == "safe"
        
        # Check supported languages
        assert "javascript" in meta.langs
        assert "typescript" in meta.langs
        assert "java" in meta.langs
        assert "csharp" in meta.langs
        assert "cpp" in meta.langs
        assert "c" in meta.langs
        assert "swift" in meta.langs
        
        # Check unsupported languages
        assert "python" not in meta.langs

    def test_requires_syntax_only(self):
        """Test that rule only requires syntax analysis (tier 0)."""
        assert self.rule.requires.syntax is True

    def test_rule_description(self):
        """Test that rule has a meaningful description."""
        assert "redundant" in self.rule.meta.description.lower()
        assert "semicolon" in self.rule.meta.description.lower()

    def test_rule_instantiation(self):
        """Test that rule can be instantiated without errors."""
        rule = StyleRedundantSemicolonsRule()
        assert rule is not None
        assert hasattr(rule, 'visit')
        assert hasattr(rule, 'meta')
        assert hasattr(rule, 'requires')

    def test_visit_method_exists(self):
        """Test that the visit method exists and accepts a context."""
        # This tests the method signature without requiring a full context
        assert callable(self.rule.visit)
        
    def test_helper_methods_exist(self):
        """Test that helper methods exist."""
        assert hasattr(self.rule, '_find_for_header_ranges')
        assert hasattr(self.rule, '_is_in_for_header')
        assert hasattr(self.rule, '_is_redundant_semicolon')
        assert hasattr(self.rule, '_get_semicolon_context')

    def test_unsupported_language_early_return(self):
        """Test that unsupported languages return early."""
        # Create a minimal mock context for unsupported language
        class MockAdapter:
            language_id = "python"  # Unsupported language
        
        class MockContext:
            adapter = MockAdapter()
        
        # Should return immediately for unsupported language
        result = list(self.rule.visit(MockContext()))
        assert result == []


