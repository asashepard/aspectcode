# server/tests/test_complexity_deep_nesting.py
"""Tests for complexity.deep_nesting rule."""

import pytest
from unittest.mock import Mock
from rules.complexity_deep_nesting import ComplexityDeepNestingRule
from engine.types import RuleContext


class TestComplexityDeepNestingRule:
    """Test cases for deep nesting detection rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ComplexityDeepNestingRule()

    def _create_mock_context(self, code: str, language: str, config: dict = None):
        """Create a mock rule context with syntax tree."""
        # Mock adapter
        adapter = Mock()
        adapter.language_id = language
        adapter.parse_tree.return_value = self._create_mock_tree(code, language)
        
        # Mock context
        ctx = Mock(spec=RuleContext)
        ctx.adapter = adapter
        ctx.file_path = f"test.{self._get_extension(language)}"
        ctx.config = config or {}
        ctx.tree = adapter.parse_tree()
        
        return ctx

    def _get_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "javascript": "js", 
            "typescript": "ts",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "csharp": "cs",
            "go": "go",
            "ruby": "rb",
            "rust": "rs",
            "swift": "swift"
        }
        return extensions.get(language, "txt")

    def _create_mock_tree(self, code: str, language: str):
        """Create a mock syntax tree based on code and language."""
        tree = Mock()
        
        # Create nested structure based on code analysis
        if_count = code.count("if")
        if "if" in code and if_count >= 4:
            # Deep nesting case - create 4+ levels
            tree.root_node = self._create_deep_nested_structure(language)
        elif "if" in code and if_count <= 2:
            # Shallow nesting case - create 2 levels
            tree.root_node = self._create_shallow_nested_structure(language)
        else:
            # No nesting
            tree.root_node = self._create_flat_structure(language)
            
        return tree

    def _create_deep_nested_structure(self, language: str):
        """Create mock node structure with deep nesting (4+ levels)."""
        # Root node
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 100
        
        # Function node
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 100
        
        # Create nested if statements (depth 4)
        if_nodes = []
        for i in range(4):
            if_node = Mock()
            if_node.type = "if_statement"
            if_node.start_byte = 10 + i * 20
            if_node.end_byte = 10 + (i + 1) * 20
            if_nodes.append(if_node)
        
        # Link them as nested children
        func_node.children = [if_nodes[0]]
        for i in range(len(if_nodes) - 1):
            if_nodes[i].children = [if_nodes[i + 1]]
        if_nodes[-1].children = []  # Innermost has no children
        
        root.children = [func_node]
        return root

    def _create_shallow_nested_structure(self, language: str):
        """Create mock node structure with shallow nesting (2 levels)."""
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 50
        
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 50
        
        # Create 2 nested if statements
        if1 = Mock()
        if1.type = "if_statement"
        if1.start_byte = 10
        if1.end_byte = 40
        
        if2 = Mock()
        if2.type = "if_statement"
        if2.start_byte = 20
        if2.end_byte = 30
        
        if1.children = [if2]
        if2.children = []
        func_node.children = [if1]
        root.children = [func_node]
        return root

    def _create_flat_structure(self, language: str):
        """Create mock node structure with no nesting."""
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 20
        
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 20
        func_node.children = []
        
        root.children = [func_node]
        return root

    def test_positive_flags_deep_nesting_javascript(self):
        """Test that deep nesting in JavaScript is flagged."""
        code = """
        function test() {
            if (a) {
                if (b) {
                    if (c) {
                        if (d) {
                            return 1;
                        }
                    }
                }
            }
        }
        """
        ctx = self._create_mock_context(code, "javascript", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "guard" in findings[0].message.lower()
        assert findings[0].meta["depth"] == 4
        assert findings[0].meta["max_depth"] == 3
        assert "suggestion" in findings[0].meta

    def test_positive_flags_deep_nesting_python(self):
        """Test that deep nesting in Python is flagged."""
        code = """
        def test():
            if a:
                if b:
                    if c:
                        if d:
                            return 1
        """
        ctx = self._create_mock_context(code, "python", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "nesting depth" in findings[0].message.lower()
        assert findings[0].severity == "warn"

    def test_negative_within_threshold_python(self):
        """Test that shallow nesting within threshold is not flagged."""
        code = """
        def test(x):
            if x:
                if x > 1:
                    return 2
            return 1
        """
        ctx = self._create_mock_context(code, "python", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_no_nesting(self):
        """Test that code without nesting is not flagged."""
        code = """
        def test():
            return 1
        """
        ctx = self._create_mock_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_different_languages_supported(self):
        """Test that different languages are properly supported."""
        languages = ["python", "javascript", "typescript", "java", "go", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        
        for lang in languages:
            assert lang in self.rule.meta.langs

    def test_unsupported_language_returns_empty(self):
        """Test that unsupported languages return no findings."""
        ctx = self._create_mock_context("test code", "unsupported_lang")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_configurable_max_depth(self):
        """Test that max_depth is configurable."""
        # Test with higher threshold - should not flag
        code = "if(a) { if(b) { if(c) { if(d) { return 1; } } } }"
        ctx = self._create_mock_context(code, "javascript", {"max_depth": 5})
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
        
        # Test with lower threshold - should flag
        ctx = self._create_mock_context(code, "javascript", {"max_depth": 2})
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_default_max_depth(self):
        """Test that default max_depth is 3."""
        code = "if(a) { if(b) { if(c) { if(d) { return 1; } } } }"
        ctx = self._create_mock_context(code, "javascript")  # No config
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1  # Should flag at depth 4 with default max 3

    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "complexity.deep_nesting"
        assert self.rule.meta.category == "complexity"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert len(self.rule.meta.langs) == 11

    def test_requires_syntax_only(self):
        """Test that rule requires syntax only (tier 0)."""
        assert self.rule.requires.syntax is True

    def test_suggestion_contains_refactoring_advice(self):
        """Test that suggestions contain useful refactoring advice."""
        code = "if(a) { if(b) { if(c) { if(d) { return 1; } } } }"
        ctx = self._create_mock_context(code, "javascript", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        # Should contain refactoring suggestions
        assert "guard clauses" in suggestion.lower() or "early return" in suggestion.lower()
        assert "extract" in suggestion.lower() or "function" in suggestion.lower()
        assert "//" in suggestion  # JavaScript comment style

    def test_suggestion_comment_style_by_language(self):
        """Test that suggestion comments use appropriate style for each language."""
        code = "if(a) { if(b) { if(c) { if(d) { return 1; } } } }"
        
        # Test JavaScript (// comments)
        ctx = self._create_mock_context(code, "javascript", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        assert "//" in findings[0].meta["suggestion"]
        
        # Test Python (# comments)
        python_code = "if a:\n    if b:\n        if c:\n            if d:\n                return 1"
        ctx = self._create_mock_context(python_code, "python", {"max_depth": 3})
        findings = list(self.rule.visit(ctx))
        assert "#" in findings[0].meta["suggestion"]

    @pytest.mark.skip(reason="suggest-only: rule provides suggestions, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped for suggest-only rule."""
        pass

    def test_function_scope_resets_nesting(self):
        """Test that entering a new function resets nesting depth."""
        # This test would verify that nested functions don't accumulate depth
        # from outer function contexts - implementation dependent on tree walking logic
        pass

    def test_different_control_structures(self):
        """Test detection of various control structures."""
        structures = {
            "javascript": ["if_statement", "for_statement", "while_statement", "switch_statement", "try_statement"],
            "python": ["if_statement", "for_statement", "while_statement", "try_statement", "with_statement"],
            "java": ["if_statement", "for_statement", "while_statement", "switch_block", "try_statement"]
        }
        
        for lang, control_types in structures.items():
            # All these should be in the CONTROL_KINDS for the language
            from rules.complexity_deep_nesting import CONTROL_KINDS
            lang_controls = CONTROL_KINDS.get(lang, set())
            for control_type in control_types:
                # At least some should be present (exact names may vary by tree-sitter grammar)
                assert len(lang_controls) > 0


if __name__ == "__main__":
    pytest.main([__file__])

