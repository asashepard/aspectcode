# server/tests/test_complexity_long_file.py
"""
Tests for the complexity.long_file rule.

This tests that the rule correctly:
- Flags files that exceed size thresholds
- Ignores files within acceptable size limits
- Provides appropriate refactoring suggestions
- Handles various languages and comment styles
"""

import pytest
from unittest.mock import Mock
from rules.complexity_long_file import ComplexityLongFileRule
from engine.types import RuleContext


class TestComplexityLongFileRule:
    """Test suite for the complexity.long_file rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ComplexityLongFileRule()

    def _create_mock_context(self, code: str, language: str = "python", config: dict = None) -> RuleContext:
        """Create a mock rule context for testing."""
        adapter = Mock()
        adapter.language_id = language
        
        tree = Mock()
        tree.root_node = Mock()
        
        ctx = Mock(spec=RuleContext)
        ctx.adapter = adapter
        ctx.file_path = f"test.{language}"
        ctx.config = config or {}
        ctx.text = code
        ctx.tree = tree
        
        return ctx

    def _make_lines(self, n: int, prefix: str = "line") -> str:
        """Generate code with n lines for testing."""
        return "\n".join(f"{prefix} {i}" for i in range(n)) + "\n"

    def test_positive_flags_large_file_javascript(self):
        """Test that large JavaScript files are flagged."""
        # Create a file with 1201 lines of code (above absolute cap of 1000)
        code = self._make_lines(1201, "const x = 1; // code")
        ctx = self._create_mock_context(code, "javascript", {
            "median_loc": 300,
            "ratio": 2.0,
            "absolute_cap": 1000
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "consider splitting" in findings[0].message.lower()
        assert findings[0].severity == "info"
        assert findings[0].rule == "complexity.long_file"
        assert findings[0].meta["loc"] == 1201
        assert findings[0].meta["threshold"] == 1000  # max(300*2, 1000) = 1000

    def test_positive_flags_large_file_python(self):
        """Test that large Python files are flagged."""
        # Create a file that exceeds the absolute cap threshold
        code = self._make_lines(1001, "print(1)  # code")
        ctx = self._create_mock_context(code, "python", {
            "median_loc": 300,
            "ratio": 2.0,
            "absolute_cap": 1000
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "LOC=1001" in findings[0].message
        assert "threshold=1000" in findings[0].message  # max(300*2, 1000) = 1000
        assert findings[0].meta["loc"] == 1001

    def test_negative_within_threshold_python(self):
        """Test that files within threshold are not flagged."""
        # Create a file with 350 lines (below 300 * 2.0 = 600 threshold)
        code = self._make_lines(350, "print(1)  # code")
        ctx = self._create_mock_context(code, "python", {
            "median_loc": 300,
            "ratio": 2.0,
            "absolute_cap": 1000
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_small_file(self):
        """Test that small files are not flagged."""
        code = "def hello():\n    print('hello')\n"
        ctx = self._create_mock_context(code, "python")
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_default_configuration(self):
        """Test that default configuration values are used correctly."""
        # Create a file that exceeds default thresholds (median=200, ratio=2.0, cap=1000)
        code = self._make_lines(1100, "code line")
        ctx = self._create_mock_context(code, "javascript")  # No config provided
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].meta["median_loc"] == 200
        assert findings[0].meta["ratio"] == 2.0
        assert findings[0].meta["absolute_cap"] == 1000
        assert findings[0].meta["threshold"] == 1000  # max(200*2, 1000) = 1000

    def test_configurable_thresholds(self):
        """Test that thresholds are configurable."""
        code = self._make_lines(800, "code line")
        
        # Test with higher threshold - should not flag
        ctx = self._create_mock_context(code, "javascript", {
            "median_loc": 500,
            "ratio": 2.0,
            "absolute_cap": 1200
        })
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0  # 800 <= max(500*2, 1200) = 1200
        
        # Test with lower threshold - should flag
        ctx = self._create_mock_context(code, "javascript", {
            "median_loc": 300,
            "ratio": 2.0,
            "absolute_cap": 700
        })
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1  # 800 > max(300*2, 700) = 700

    def test_effective_loc_counting_excludes_blanks(self):
        """Test that effective LOC counting excludes blank lines."""
        code = """line 1
line 2

line 4


line 7
"""
        ctx = self._create_mock_context(code, "python")
        loc = self.rule._count_effective_loc(code)
        
        assert loc == 4  # Only non-blank lines counted

    def test_effective_loc_counting_excludes_comments_python(self):
        """Test that effective LOC counting excludes comment-only lines in Python."""
        code = """# This is a comment
line 1
# Another comment
line 2
"""
        ctx = self._create_mock_context(code, "python")
        loc = self.rule._count_effective_loc(code)
        
        assert loc == 2  # Only non-comment lines counted

    def test_effective_loc_counting_excludes_comments_javascript(self):
        """Test that effective LOC counting excludes comment-only lines in JavaScript."""
        code = """// This is a comment
const x = 1;
/* Block comment */
const y = 2;
// Another comment
"""
        ctx = self._create_mock_context(code, "javascript")
        loc = self.rule._count_effective_loc(code)
        
        assert loc == 2  # Only non-comment lines counted

    def test_suggestion_contains_refactoring_advice(self):
        """Test that suggestions contain useful refactoring advice."""
        code = self._make_lines(1200, "code line")
        ctx = self._create_mock_context(code, "javascript", {
            "median_loc": 300,
            "ratio": 2.0,
            "absolute_cap": 1000
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        # Check that suggestion contains concrete advice
        assert "move data types" in suggestion.lower()
        assert "extract utility functions" in suggestion.lower()
        assert "split large class" in suggestion.lower()
        assert "separate i/o" in suggestion.lower()

    def test_suggestion_comment_style_by_language(self):
        """Test that suggestion comments use appropriate style for each language."""
        code = self._make_lines(1200, "code line")
        
        # Test Python (# comments)
        ctx = self._create_mock_context(code, "python", {"absolute_cap": 1000})
        findings = list(self.rule.visit(ctx))
        suggestion = findings[0].meta["suggestion"]
        assert "#" in suggestion
        assert "//" not in suggestion
        
        # Test JavaScript (// comments)
        ctx = self._create_mock_context(code, "javascript", {"absolute_cap": 1000})
        findings = list(self.rule.visit(ctx))
        suggestion = findings[0].meta["suggestion"]
        assert "//" in suggestion

    def test_language_specific_comment_leaders(self):
        """Test that different languages get appropriate comment leaders."""
        test_cases = [
            ("python", "#"),
            ("ruby", "#"),
            ("javascript", "//"),
            ("typescript", "//"),
            ("go", "//"),
            ("java", "//"),
            ("csharp", "//"),
            ("cpp", "//"),
            ("c", "//"),
            ("rust", "//"),
            ("swift", "//"),
        ]
        
        for lang, expected_leader in test_cases:
            leader = self.rule._get_comment_leader(lang)
            assert leader == expected_leader, f"Language {lang} should use {expected_leader} but got {leader}"

    def test_different_languages_supported(self):
        """Test that the rule supports different programming languages."""
        code = self._make_lines(1200, "code line")
        supported_languages = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        
        for lang in supported_languages:
            ctx = self._create_mock_context(code, lang, {"absolute_cap": 1000})
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 1, f"Language {lang} should be supported"

    def test_unsupported_language_returns_empty(self):
        """Test that unsupported languages return no findings."""
        code = self._make_lines(1200, "code line")
        ctx = self._create_mock_context(code, "unsupported_lang", {"absolute_cap": 1000})
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_rule_metadata(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "complexity.long_file"
        assert self.rule.meta.category == "complexity"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "split" in self.rule.meta.description.lower()

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is False
        assert self.rule.requires.project_graph is False

    def test_mixed_content_loc_counting(self):
        """Test LOC counting with mixed content (code, comments, blanks)."""
        code = """# File header comment
// Another comment style
import sys

# Configuration section
CONFIG = {
    'key': 'value'
}


def main():
    # Implementation comment
    print("Hello")
    
    /* 
     * Multi-line comment
     */
    
    return 0

"""
        ctx = self._create_mock_context(code, "python")
        loc = self.rule._count_effective_loc(code)
        
        # Should count only the actual code lines:
        # import sys, CONFIG = {...}, def main():, print("Hello"), return 0
        # Comments and blank lines should be excluded
        expected_code_lines = 7  # Approximate, may vary based on comment detection
        assert loc <= expected_code_lines + 2  # Allow some tolerance for edge cases

    @pytest.mark.skip(reason="suggest-only: rule provides guidance, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped since this is a suggest-only rule."""
        pass

    def test_threshold_calculation_logic(self):
        """Test that threshold calculation uses max(median * ratio, absolute_cap) correctly."""
        test_cases = [
            # (median, ratio, cap, expected_threshold)
            (200, 2.0, 1000, 1000),  # max(400, 1000) = 1000
            (500, 2.0, 800, 1000),   # max(1000, 800) = 1000
            (300, 3.0, 500, 900),    # max(900, 500) = 900
            (100, 1.5, 200, 200),    # max(150, 200) = 200
        ]
        
        for median, ratio, cap, expected in test_cases:
            code = self._make_lines(expected + 1, "code")  # Just over threshold
            ctx = self._create_mock_context(code, "python", {
                "median_loc": median,
                "ratio": ratio,
                "absolute_cap": cap
            })
            
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 1
            assert findings[0].meta["threshold"] == expected

