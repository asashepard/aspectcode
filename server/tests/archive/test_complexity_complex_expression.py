# server/tests/test_complexity_complex_expression.py
"""
Tests for the complexity.complex_expression rule.

This tests that the rule correctly:
- Flags expressions that exceed complexity thresholds
- Ignores simple expressions within acceptable limits
- Provides appropriate refactoring suggestions
- Handles various languages and expression types
"""

import pytest
from unittest.mock import Mock
from rules.complexity_complex_expression import ComplexityComplexExpressionRule
from engine.types import RuleContext


class TestComplexityComplexExpressionRule:
    """Test suite for the complexity.complex_expression rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ComplexityComplexExpressionRule()

    def _create_mock_context(self, code: str, language: str = "javascript", config: dict = None) -> RuleContext:
        """Create a mock rule context for testing."""
        adapter = Mock()
        adapter.language_id = language
        
        tree = Mock()
        root = Mock()
        root.type = "program"
        tree.root_node = root
        
        ctx = Mock(spec=RuleContext)
        ctx.adapter = adapter
        ctx.file_path = f"test.{language}"
        ctx.config = config or {}
        ctx.text = code
        ctx.tree = tree
        
        return ctx

    def test_positive_flags_chained_calls_javascript(self):
        """Test that deeply chained method calls are flagged."""
        code = "const result = obj.method1().method2().method3().method4().method5();"
        ctx = self._create_mock_context(code, "javascript", {
            "max_chain": 3,
            "max_bool_ops": 4,
            "max_ternary_nesting": 1,
            "max_op_chain": 6,
            "max_score": 10
        })
        
        # Mock a complex expression node
        expr_node = Mock()
        expr_node.type = "call_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 75
        expr_node.children = []
        
        # Override the expression finding to return our mock
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        
        # Override complexity measurement to return high chain count
        self.rule._measure_complexity = Mock(return_value={
            "chain": 5,  # Exceeds max_chain=3
            "bool_ops": 0,
            "ternary_depth": 0,
            "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "complex expression" in findings[0].message.lower()
        assert "chain=5" in findings[0].message
        assert findings[0].severity == "info"
        assert findings[0].rule == "complexity.complex_expression"

    def test_positive_flags_boolean_chain_python(self):
        """Test that long boolean chains are flagged."""
        code = "if condition1 and condition2 and condition3 and condition4 and condition5:"
        ctx = self._create_mock_context(code, "python", {
            "max_chain": 4,
            "max_bool_ops": 3,  # Set low to trigger
            "max_ternary_nesting": 1,
            "max_op_chain": 6,
            "max_score": 10
        })
        
        expr_node = Mock()
        expr_node.type = "binary_expression"
        expr_node.start_byte = 3
        expr_node.end_byte = 65
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 0,
            "bool_ops": 5,  # Exceeds max_bool_ops=3
            "ternary_depth": 0,
            "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "bool_ops=5" in findings[0].message

    def test_positive_flags_nested_ternary_javascript(self):
        """Test that nested ternary expressions are flagged."""
        code = "const result = condition1 ? (condition2 ? value1 : value2) : (condition3 ? value3 : value4);"
        ctx = self._create_mock_context(code, "javascript", {
            "max_chain": 4,
            "max_bool_ops": 4,
            "max_ternary_nesting": 1,  # Set low to trigger
            "max_op_chain": 6,
            "max_score": 10
        })
        
        expr_node = Mock()
        expr_node.type = "conditional_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 85
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 0,
            "bool_ops": 0,
            "ternary_depth": 2,  # Exceeds max_ternary_nesting=1
            "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "ternary_depth=2" in findings[0].message

    def test_positive_flags_arithmetic_chain(self):
        """Test that long arithmetic chains are flagged."""
        code = "const result = a + b * c - d / e % f | g & h ^ i;"
        ctx = self._create_mock_context(code, "javascript", {
            "max_chain": 4,
            "max_bool_ops": 4,
            "max_ternary_nesting": 1,
            "max_op_chain": 5,  # Set low to trigger
            "max_score": 10
        })
        
        expr_node = Mock()
        expr_node.type = "binary_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 45
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 0,
            "bool_ops": 0,
            "ternary_depth": 0,
            "op_chain": 8  # Exceeds max_op_chain=5
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "ops=8" in findings[0].message

    def test_positive_flags_high_score(self):
        """Test that expressions with high combined score are flagged."""
        code = "const result = obj.a().b().c() && cond1 && cond2 ? val1 : val2;"
        ctx = self._create_mock_context(code, "javascript", {
            "max_chain": 10,  # Set high individually
            "max_bool_ops": 10,
            "max_ternary_nesting": 10,
            "max_op_chain": 10,
            "max_score": 8  # But low combined score
        })
        
        expr_node = Mock()
        expr_node.type = "conditional_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 65
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 3,        # 3 * 2 = 6
            "bool_ops": 2,     # 2 * 1 = 2
            "ternary_depth": 1, # 1 * 3 = 3
            "op_chain": 0      # 0 * 1 = 0
        })                     # Total score = 11 > max_score=8
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "score=11" in findings[0].message

    def test_negative_simple_expression_javascript(self):
        """Test that simple expressions are not flagged."""
        code = "const result = a + b;"
        ctx = self._create_mock_context(code, "javascript")
        
        expr_node = Mock()
        expr_node.type = "binary_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 20
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 0,
            "bool_ops": 0,
            "ternary_depth": 0,
            "op_chain": 1
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_simple_expression_python(self):
        """Test that simple Python expressions are not flagged."""
        code = "result = (x + 1) * 2"
        ctx = self._create_mock_context(code, "python")
        
        expr_node = Mock()
        expr_node.type = "binary_expression"
        expr_node.start_byte = 9
        expr_node.end_byte = 20
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 0,
            "bool_ops": 0,
            "ternary_depth": 0,
            "op_chain": 2
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_suggestion_contains_refactoring_advice(self):
        """Test that suggestions contain useful refactoring advice."""
        code = "const complex = obj.a().b().c().d() && cond1 && cond2 && cond3;"
        ctx = self._create_mock_context(code, "javascript", {"max_chain": 2})
        
        expr_node = Mock()
        expr_node.type = "binary_expression"
        expr_node.start_byte = 16
        expr_node.end_byte = 65
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 4,  # Exceeds threshold
            "bool_ops": 3,
            "ternary_depth": 0,
            "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        # Check that suggestion contains concrete advice
        assert "intermediate variables" in suggestion.lower()
        assert "boolean chains" in suggestion.lower()
        assert "ternaries" in suggestion.lower()
        assert "strategy helpers" in suggestion.lower()

    def test_suggestion_comment_style_by_language(self):
        """Test that suggestion comments use appropriate style for each language."""
        code = "result = obj.a().b().c().d().e()"
        
        # Test Python (# comments)
        ctx = self._create_mock_context(code, "python", {"max_chain": 2})
        expr_node = Mock()
        expr_node.type = "call_expression"
        expr_node.start_byte = 9
        expr_node.end_byte = 35
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 5, "bool_ops": 0, "ternary_depth": 0, "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        suggestion = findings[0].meta["suggestion"]
        assert "#" in suggestion
        assert "//" not in suggestion
        
        # Test JavaScript (// comments) 
        ctx = self._create_mock_context(code, "javascript", {"max_chain": 2})
        findings = list(self.rule.visit(ctx))
        suggestion = findings[0].meta["suggestion"]
        assert "//" in suggestion

    def test_different_languages_supported(self):
        """Test that the rule supports different programming languages."""
        code = "result = obj.method1().method2().method3().method4()"
        supported_languages = ["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
        
        for lang in supported_languages:
            ctx = self._create_mock_context(code, lang, {"max_chain": 2})
            # The rule should process the language without errors
            assert self.rule._matches_language(ctx, self.rule.meta.langs)

    def test_unsupported_language_returns_empty(self):
        """Test that unsupported languages return no findings."""
        code = "result = obj.method1().method2().method3().method4()"
        ctx = self._create_mock_context(code, "unsupported_lang", {"max_chain": 2})
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_rule_metadata(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "complexity.complex_expression"
        assert self.rule.meta.category == "complexity"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "complex expressions" in self.rule.meta.description.lower()

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is False
        assert self.rule.requires.project_graph is False

    def test_configurable_thresholds(self):
        """Test that all thresholds are configurable."""
        code = "const result = a.b().c() && d && e ? f : g;"
        
        # Test with strict thresholds - should flag
        ctx = self._create_mock_context(code, "javascript", {
            "max_chain": 1,
            "max_bool_ops": 1,
            "max_ternary_nesting": 0,
            "max_op_chain": 1,
            "max_score": 1
        })
        
        expr_node = Mock()
        expr_node.type = "conditional_expression"
        expr_node.start_byte = 15
        expr_node.end_byte = 40
        expr_node.children = []
        
        self.rule._find_expression_nodes = Mock(return_value=[expr_node])
        self.rule._measure_complexity = Mock(return_value={
            "chain": 2, "bool_ops": 2, "ternary_depth": 1, "op_chain": 0
        })
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        
        # Test with lenient thresholds - should not flag
        ctx.config = {
            "max_chain": 10,
            "max_bool_ops": 10,
            "max_ternary_nesting": 10,
            "max_op_chain": 10,
            "max_score": 50
        }
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_score_calculation(self):
        """Test that complexity score is calculated correctly."""
        metrics = {
            "chain": 3,
            "bool_ops": 2,
            "ternary_depth": 1,
            "op_chain": 4
        }
        
        # Expected: 3*2 + 2*1 + 1*3 + 4*1 = 6 + 2 + 3 + 4 = 15
        score = self.rule._calculate_score(metrics)
        assert score == 15

    def test_comment_leaders(self):
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

    @pytest.mark.skip(reason="suggest-only: rule provides guidance, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped since this is a suggest-only rule."""
        pass

    def test_boolean_token_detection(self):
        """Test that boolean operators are correctly detected."""
        # Test various boolean operators
        test_cases = [
            ("condition1 && condition2", 1),
            ("a || b || c", 2),
            ("x and y and z", 2),
            ("p or q", 1),
            ("a && b || c", 2),
        ]
        
        for text, expected_count in test_cases:
            count = self.rule._count_boolean_operators(text)
            assert count == expected_count, f"Expected {expected_count} boolean ops in '{text}', got {count}"

    def test_arithmetic_token_detection(self):
        """Test that arithmetic operators are correctly detected."""
        test_cases = [
            ("a + b - c", 2),
            ("x * y / z % w", 3),
            ("p | q & r ^ s", 3),
            ("a << b >> c", 2),
            ("x ** y", 3),  # ** counts as both * (2x) and ** (1x) = 3
        ]
        
        for text, expected_count in test_cases:
            count = self.rule._count_arithmetic_operators(text)
            assert count == expected_count, f"Expected {expected_count} arithmetic ops in '{text}', got {count}"

