# server/tests/test_complexity_high_cyclomatic.py
"""Tests for complexity.high_cyclomatic rule."""

import pytest
from unittest.mock import Mock
from rules.complexity_high_cyclomatic import ComplexityHighCyclomaticRule
from engine.types import RuleContext


class TestComplexityHighCyclomaticRule:
    """Test cases for high cyclomatic complexity detection rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ComplexityHighCyclomaticRule()

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
        ctx.text = code
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
        
        # Analyze code to determine complexity
        complexity_indicators = code.count("if") + code.count("for") + code.count("while") + code.count("case") + code.count("&&") + code.count("||")
        
        if complexity_indicators >= 10:
            # High complexity case
            tree.root_node = self._create_high_complexity_structure(language, complexity_indicators)
        elif complexity_indicators >= 5:
            # Medium complexity case  
            tree.root_node = self._create_medium_complexity_structure(language, complexity_indicators)
        else:
            # Low complexity case
            tree.root_node = self._create_simple_function_structure(language)
            
        return tree

    def _create_high_complexity_structure(self, language: str, complexity: int):
        """Create mock node structure for high complexity function."""
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 500
        
        # Function node
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 500
        
        # Function name
        name_node = Mock()
        name_node.text = b"complexFunction"
        func_node.name = name_node
        
        # Function body with many decision points
        body_node = Mock()
        body_node.type = "block" if language != "python" else "suite"
        body_node.start_byte = 50
        body_node.end_byte = 450
        func_node.body = body_node
        
        # Create multiple decision nodes
        decision_nodes = []
        for i in range(min(complexity, 12)):  # Cap at 12 decisions
            decision_node = Mock()
            if i % 4 == 0:
                decision_node.type = "if_statement"
            elif i % 4 == 1:
                decision_node.type = "for_statement"
            elif i % 4 == 2:
                decision_node.type = "while_statement"
            else:
                decision_node.type = "switch_case" if language != "python" else "case_clause"
            
            decision_node.start_byte = 60 + i * 30
            decision_node.end_byte = 80 + i * 30
            decision_node.children = []
            decision_nodes.append(decision_node)
        
        func_node.children = [body_node] + decision_nodes
        body_node.children = decision_nodes
        root.children = [func_node]
        return root

    def _create_medium_complexity_structure(self, language: str, complexity: int):
        """Create mock node structure for medium complexity function."""
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 200
        
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 200
        
        name_node = Mock()
        name_node.text = b"mediumFunction"
        func_node.name = name_node
        
        body_node = Mock()
        body_node.type = "block" if language != "python" else "suite"
        body_node.start_byte = 30
        body_node.end_byte = 180
        func_node.body = body_node
        
        # Create some decision nodes
        decision_nodes = []
        for i in range(min(complexity, 6)):
            decision_node = Mock()
            decision_node.type = "if_statement" if i % 2 == 0 else "for_statement"
            decision_node.start_byte = 40 + i * 20
            decision_node.end_byte = 55 + i * 20
            decision_node.children = []
            decision_nodes.append(decision_node)
        
        func_node.children = [body_node] + decision_nodes
        body_node.children = decision_nodes
        root.children = [func_node]
        return root

    def _create_simple_function_structure(self, language: str):
        """Create mock node structure for simple function."""
        root = Mock()
        root.type = "module" if language == "python" else "program"
        root.start_byte = 0
        root.end_byte = 100
        
        func_node = Mock()
        func_node.type = "function_definition" if language == "python" else "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 100
        
        name_node = Mock()
        name_node.text = b"simpleFunction"
        func_node.name = name_node
        
        body_node = Mock()
        body_node.type = "block" if language != "python" else "suite"
        body_node.start_byte = 20
        body_node.end_byte = 80
        func_node.body = body_node
        func_node.children = [body_node]
        body_node.children = []
        
        root.children = [func_node]
        return root

    def test_positive_flags_high_complexity_javascript(self):
        """Test that high complexity JavaScript function is flagged."""
        code = """
        function complexFunction(x) {
            if (x === 1) { return 'one'; }
            else if (x === 2) { return 'two'; }
            else if (x === 3) { return 'three'; }
            for (let i = 0; i < 10; i++) {
                if (i % 2 === 0) { continue; }
                if (i > 5 && i < 8) { break; }
                for (let j = 0; j < 5; j++) {
                    if (j === 2 || j === 4) { return j; }
                    while (j < 3) { j++; }
                }
            }
            return 'default';
        }
        """
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 5})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "cyclomatic complexity" in findings[0].message.lower()
        assert "complexfunction" in findings[0].message.lower()
        assert findings[0].meta["complexity"] > 5
        assert "suggestion" in findings[0].meta

    def test_positive_flags_high_complexity_python(self):
        """Test that high complexity Python function is flagged."""
        code = """
        def complex_function(data):
            if not data:
                return None
            for item in data:
                if item.get('active'):
                    if item.get('type') == 'A':
                        for sub in item.get('children', []):
                            if sub.get('valid'):
                                if sub.get('score') > 10:
                                    try:
                                        result = process(sub)
                                        if result and result.success:
                                            return result
                                    except Exception as e:
                                        if str(e) == 'critical':
                                            raise
                                        continue
            return 'default'
        """
        ctx = self._create_mock_context(code, "python", {"max_cyclomatic": 6})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "complexity" in findings[0].message.lower()
        assert findings[0].severity == "warn"

    def test_negative_simple_function_python(self):
        """Test that simple function is not flagged."""
        code = """
        def simple_function(x):
            if x > 0:
                return x * 2
            return 0
        """
        ctx = self._create_mock_context(code, "python", {"max_cyclomatic": 10})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_no_body_function(self):
        """Test that functions without bodies are not flagged."""
        code = """
        def abstract_function():
            pass
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

    def test_configurable_max_cyclomatic(self):
        """Test that max_cyclomatic is configurable."""
        code = """
        function testFunction(x) {
            if (x === 1) return 'one';
            if (x === 2) return 'two';
            if (x === 3) return 'three';
            if (x === 4) return 'four';
            if (x === 5) return 'five';
            if (x === 6) return 'six';
            return 'other';
        }
        """
        
        # Test with higher threshold - should not flag
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 15})
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
        
        # Test with lower threshold - should flag
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 3})
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_default_max_cyclomatic(self):
        """Test that default max_cyclomatic is 10."""
        code = """
        function testFunction(x) {
            if (x === 1) return 'one';
            if (x === 2) return 'two';
            if (x === 3) return 'three';
            if (x === 4) return 'four';
            if (x === 5) return 'five';
            if (x === 6) return 'six';
            if (x === 7) return 'seven';
            if (x === 8) return 'eight';
            if (x === 9) return 'nine';
            if (x === 10) return 'ten';
            if (x === 11) return 'eleven';
            return 'other';
        }
        """
        
        ctx = self._create_mock_context(code, "javascript")  # No config
        findings = list(self.rule.visit(ctx))
        
        # Should flag with default threshold of 10
        assert len(findings) == 1

    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "complexity.high_cyclomatic"
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
        code = """
        function complexFunction(x) {
            if (x === 1) return 'one';
            if (x === 2) return 'two';
            if (x === 3) return 'three';
            if (x === 4) return 'four';
            if (x === 5) return 'five';
            if (x === 6) return 'six';
            if (x === 7) return 'seven';
            return 'other';
        }
        """
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 4})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        # Should contain refactoring suggestions
        assert any(keyword in suggestion.lower() for keyword in ["guard", "extract", "strategy", "helper", "refactor"])
        assert "//" in suggestion  # JavaScript comment style

    def test_suggestion_comment_style_by_language(self):
        """Test that suggestion comments use appropriate style for each language."""
        code = """
        function complexFunction(x) {
            if (x === 1) return 'one';
            if (x === 2) return 'two';
            if (x === 3) return 'three';
            if (x === 4) return 'four';
            if (x === 5) return 'five';
            if (x === 6) return 'six';
            return 'other';
        }
        """
        
        # Test JavaScript (// comments)
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 4})
        findings = list(self.rule.visit(ctx))
        assert "//" in findings[0].meta["suggestion"]
        
        # Test Python (# comments) - adapt code for Python
        python_code = """
        def complex_function(x):
            if x == 1: return 'one'
            if x == 2: return 'two'
            if x == 3: return 'three'
            if x == 4: return 'four'
            if x == 5: return 'five'
            if x == 6: return 'six'
            return 'other'
        """
        ctx = self._create_mock_context(python_code, "python", {"max_cyclomatic": 4})
        findings = list(self.rule.visit(ctx))
        assert "#" in findings[0].meta["suggestion"]

    def test_complexity_calculation_includes_boolean_operators(self):
        """Test that boolean operators contribute to complexity."""
        code = """
        function testFunction(a, b, c, d) {
            if (a && b || c && d) {
                return true;
            }
            return false;
        }
        """
        ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 2})
        findings = list(self.rule.visit(ctx))
        
        # Should flag due to boolean operators increasing complexity
        assert len(findings) == 1
        assert findings[0].meta["token_complexity"] > 0

    def test_very_high_complexity_suggestions(self):
        """Test that very high complexity functions get appropriate suggestions."""
        # Create a function with very high complexity
        high_complexity_code = """
        function megaComplexFunction(x) {
            """ + "\n".join([f"            if (x === {i}) return '{i}';" for i in range(25)]) + """
            return 'default';
        }
        """
        
        ctx = self._create_mock_context(high_complexity_code, "javascript", {"max_cyclomatic": 5})
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        # Should suggest breaking into multiple functions for very high complexity
        assert "break" in suggestion.lower() and "multiple" in suggestion.lower()

    @pytest.mark.skip(reason="suggest-only: rule provides guidance, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped for suggest-only rule."""
        pass

    def test_function_name_extraction(self):
        """Test that function names are correctly extracted."""
        code = """
        function namedFunction() {
            if (true) return 1;
            if (false) return 2;
            if (maybe) return 3;
            if (perhaps) return 4;
            if (definitely) return 5;
            return 0;
        }
        """
        
        # Create a specific mock for this test
        adapter = Mock()
        adapter.language_id = "javascript"
        
        # Create mock tree with correct function name
        tree = Mock()
        root = Mock()
        root.type = "program"
        
        func_node = Mock()
        func_node.type = "function_declaration"
        func_node.start_byte = 0
        func_node.end_byte = 200
        
        # Mock the function name correctly
        name_node = Mock()
        name_node.text = b"namedFunction"
        func_node.name = name_node
        
        body_node = Mock()
        body_node.type = "block"
        body_node.start_byte = 30
        body_node.end_byte = 180
        func_node.body = body_node
        
        # Add decision nodes to exceed threshold
        decision_nodes = []
        for i in range(6):  # More than threshold of 3
            decision_node = Mock()
            decision_node.type = "if_statement"
            decision_node.start_byte = 40 + i * 20
            decision_node.end_byte = 55 + i * 20
            decision_node.children = []
            decision_nodes.append(decision_node)
        
        func_node.children = [body_node] + decision_nodes
        body_node.children = decision_nodes
        root.children = [func_node]
        tree.root_node = root
        adapter.parse_tree.return_value = tree
        
        ctx = Mock(spec=RuleContext)
        ctx.adapter = adapter
        ctx.file_path = "test.js"
        ctx.config = {"max_cyclomatic": 3}
        ctx.text = code
        ctx.tree = tree
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "namedFunction" in findings[0].message

    def test_no_false_positives_for_simple_functions(self):
        """Test that simple functions don't trigger false positives."""
        simple_functions = [
            "function simple() { return 1; }",
            "function withOneIf(x) { if (x) return 1; return 0; }",
            "function withLoop(arr) { for (let i of arr) { console.log(i); } }",
        ]
        
        for code in simple_functions:
            ctx = self._create_mock_context(code, "javascript", {"max_cyclomatic": 10})
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"False positive for: {code}"


if __name__ == "__main__":
    pytest.main([__file__])

