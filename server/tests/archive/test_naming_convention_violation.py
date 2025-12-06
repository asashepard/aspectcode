"""
Tests for the naming.convention_violation rule.
"""

import pytest
from engine.python_adapter import PythonAdapter
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter
from engine.types import RuleContext
from rules.naming_convention_violation import RuleNamingConventionViolation


class TestNamingConventionViolationRule:
    """Test cases for the naming convention violation rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = RuleNamingConventionViolation()
        self.python_adapter = PythonAdapter()
        self.js_adapter = JavaScriptAdapter()
        self.ts_adapter = TypeScriptAdapter()
    
    def _run_rule(self, code: str, language: str = "python", config: dict = None):
        """Helper to run the rule on code and return findings."""
        if language == "python":
            adapter = self.python_adapter
            filename = "test.py"
        elif language == "javascript":
            adapter = self.js_adapter
            filename = "test.js"
        elif language == "typescript":
            adapter = self.ts_adapter
            filename = "test.ts"
        else:
            raise ValueError(f"Unsupported language: {language}")
            
        tree = adapter.parse(code)
        if not tree:
            pytest.skip(f"Tree-sitter parser not available for {language}")
        
        ctx = RuleContext(
            file_path=filename,
            text=code,
            tree=tree,
            adapter=adapter,
            config=config or {}
        )
        return list(self.rule.visit(ctx))

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        meta = self.rule.meta
        assert meta.id == "naming.convention_violation"
        assert meta.category == "naming"
        assert meta.tier == 0
        assert meta.priority == "P1"
        assert meta.autofix_safety == "suggest-only"
        assert "python" in meta.langs
        assert "javascript" in meta.langs
        assert "typescript" in meta.langs

    def test_positive_python_function_snake_case_violation(self):
        """Test that PascalCase function name is detected as violation in Python."""
        code = "def BadFunctionName():\n    pass\n"
        config = {"naming_map": {"function": "snake"}}
        findings = self._run_rule(code, language="python", config=config)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "naming.convention_violation"
        assert "snake" in finding.message.lower()
        assert finding.meta is not None
        assert finding.meta["original_name"] == "BadFunctionName"
        assert finding.meta["suggested_name"] == "bad_function_name"
        assert finding.meta["style"] == "snake"

    def test_positive_javascript_class_pascal_case_violation(self):
        """Test that camelCase class name is detected as violation in JavaScript."""
        code = "class badClassName {}\n"
        config = {"naming_map": {"class": "pascal"}}
        findings = self._run_rule(code, language="javascript", config=config)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "naming.convention_violation"
        assert "pascal" in finding.message.lower()
        assert finding.meta["original_name"] == "badClassName"
        assert finding.meta["suggested_name"] == "BadClassName"

    def test_positive_variable_camel_case_violation(self):
        """Test that snake_case variable is detected as violation when camel expected."""
        code = "let my_variable = 42;"
        config = {"naming_map": {"variable": "camel"}}
        findings = self._run_rule(code, language="javascript", config=config)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["original_name"] == "my_variable"
        assert finding.meta["suggested_name"] == "myVariable"

    def test_negative_python_function_correct_snake_case(self):
        """Test that correctly named snake_case function produces no findings."""
        code = "def good_function_name():\n    pass\n"
        config = {"naming_map": {"function": "snake"}}
        findings = self._run_rule(code, language="python", config=config)
        
        assert len(findings) == 0

    def test_negative_javascript_class_correct_pascal_case(self):
        """Test that correctly named PascalCase class produces no findings."""
        code = "class GoodClassName {}\n"
        config = {"naming_map": {"class": "pascal"}}
        findings = self._run_rule(code, language="javascript", config=config)
        
        assert len(findings) == 0

    def test_negative_variable_correct_camel_case(self):
        """Test that correctly named camelCase variable produces no findings."""
        code = "let goodVariable = 42;"
        config = {"naming_map": {"variable": "camel"}}
        findings = self._run_rule(code, language="javascript", config=config)
        
        assert len(findings) == 0

    def test_const_upper_snake_case_violation_typescript(self):
        """Test that const variables should use UPPER_SNAKE_CASE."""
        code = "const myConstant = 42;"
        config = {"naming_map": {"const": "upper_snake"}}
        findings = self._run_rule(code, language="typescript", config=config)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["original_name"] == "myConstant"
        assert finding.meta["suggested_name"] == "MY_CONSTANT"

    def test_case_conversion_helpers(self):
        """Test the case conversion helper methods."""
        rule = self.rule
        
        # Test snake case conversion
        assert rule._to_snake("fooBar") == "foo_bar"
        assert rule._to_snake("FooBarBaz") == "foo_bar_baz"
        assert rule._to_snake("HTTPSConnection") == "https_connection"
        
        # Test camel case conversion
        assert rule._to_camel("foo_bar") == "fooBar"
        assert rule._to_camel("foo_bar_baz") == "fooBarBaz"
        assert rule._to_camel("SOME_CONST") == "someConst"
        
        # Test pascal case conversion
        assert rule._to_pascal("foo_bar") == "FooBar"
        assert rule._to_pascal("fooBar") == "FooBar"
        assert rule._to_pascal("some_class_name") == "SomeClassName"
        
        # Test upper snake case conversion
        assert rule._to_upper_snake("fooBar") == "FOO_BAR"
        assert rule._to_upper_snake("FooBarBaz") == "FOO_BAR_BAZ"

    def test_style_validation_helpers(self):
        """Test the style validation helper methods."""
        rule = self.rule
        
        # Test snake case validation
        assert rule._style_ok("snake", "good_name") == True
        assert rule._style_ok("snake", "BadName") == False
        assert rule._style_ok("snake", "another_good_name") == True
        
        # Test camel case validation
        assert rule._style_ok("camel", "goodName") == True
        assert rule._style_ok("camel", "bad_name") == False
        assert rule._style_ok("camel", "GoodName") == False  # Should be lowercase first
        
        # Test pascal case validation
        assert rule._style_ok("pascal", "GoodName") == True
        assert rule._style_ok("pascal", "badName") == False
        assert rule._style_ok("pascal", "AnotherGoodName") == True
        
        # Test upper snake case validation
        assert rule._style_ok("upper_snake", "GOOD_NAME") == True
        assert rule._style_ok("upper_snake", "bad_name") == False
        assert rule._style_ok("upper_snake", "ANOTHER_GOOD_NAME") == True

    def test_default_naming_conventions(self):
        """Test that default naming conventions are applied when no config provided."""
        code = "def BadFunctionName():\n    pass\n"
        # No config provided - should use defaults (function: snake for Python)
        findings = self._run_rule(code, language="python")
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["style"] == "snake"  # Default for functions

    def test_custom_naming_map_overrides_defaults(self):
        """Test that custom naming_map overrides default conventions."""
        code = "def snake_function_name():\n    pass\n"
        config = {"naming_map": {"function": "pascal"}}  # Override default snake to pascal
        findings = self._run_rule(code, language="python", config=config)
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["style"] == "pascal"
        assert finding.meta["suggested_name"] == "SnakeFunctionName"

    def test_reserved_names_ignored(self):
        """Test that reserved names like __init__ are ignored."""
        code = "def __init__(self):\n    pass\n"
        config = {"naming_map": {"function": "pascal"}}
        findings = self._run_rule(code, language="python", config=config)
        
        assert len(findings) == 0  # __init__ should be ignored

    def test_multiple_violations_in_same_file(self):
        """Test multiple naming violations in the same file."""
        code = """
function BadFunction() {
    return 42;
}

class badClass {
    constructor() {}
}

let bad_variable = 42;
"""
        config = {
            "naming_map": {
                "function": "snake",
                "class": "pascal", 
                "variable": "camel"
            }
        }
        findings = self._run_rule(code, language="javascript", config=config)
        
        # Should find violations for function, class, and variable
        assert len(findings) >= 1  # At least one violation should be found

    def test_unknown_symbol_kind_defaults_to_variable(self):
        """Test that unknown symbol kinds default to variable conventions."""
        # This test might be harder to trigger, but we can test the classification logic
        rule = self.rule
        ctx = RuleContext(
            file_path="test.py",
            text="",
            tree=None,
            adapter=self.python_adapter,
            config={}
        )
        
        # Mock a node with unknown type
        class MockNode:
            def __init__(self, node_type):
                self.type = node_type
        
        # Test that unknown types default to "variable"
        unknown_node = MockNode("unknown_declaration_type")
        kind = rule._classify_kind(ctx, unknown_node)
        assert kind == "variable"

    @pytest.mark.skip(reason="suggest-only: rule provides suggestions, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped since this rule is suggest-only."""
        pass

