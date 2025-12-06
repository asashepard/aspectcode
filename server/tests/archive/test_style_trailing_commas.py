"""
Tests for the style.trailing_commas rule.
"""

import pytest
from engine.python_adapter import PythonAdapter
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter
from engine.types import RuleContext
from rules.style_trailing_commas import RuleStyleTrailingCommas


class TestStyleTrailingCommasRule:
    """Test cases for the trailing commas rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = RuleStyleTrailingCommas()
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
        assert meta.id == "style.trailing_commas"
        assert meta.category == "style"
        assert meta.tier == 0
        assert meta.priority == "P3"
        assert meta.autofix_safety == "suggest-only"
        assert "python" in meta.langs
        assert "javascript" in meta.langs
        assert "typescript" in meta.langs
        assert "ruby" in meta.langs

    def test_multiline_only_policy_detects_missing_comma_python(self):
        """Test multiline-only policy detects missing trailing comma in multiline Python list."""
        code = """data = [
    1,
    2,
    3
]"""
        findings = self._run_rule(code, config={"trailing_commas": "multiline-only"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_commas"
        assert "multiline-only" in finding.message
        assert finding.meta is not None
        assert finding.meta["action"] == "add"

    def test_multiline_only_policy_allows_comma_in_multiline_js(self):
        """Test multiline-only policy allows trailing comma in multiline JavaScript object."""
        code = """const obj = {
    a: 1,
    b: 2,
}"""
        findings = self._run_rule(code, language="javascript", config={"trailing_commas": "multiline-only"})
        
        assert len(findings) == 0

    def test_multiline_only_policy_forbids_comma_in_singleline_python(self):
        """Test multiline-only policy forbids trailing comma in single-line Python list."""
        code = "data = [1, 2, 3,]"
        findings = self._run_rule(code, config={"trailing_commas": "multiline-only"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_commas"
        assert "multiline-only" in finding.message
        assert finding.meta is not None
        assert finding.meta["action"] == "remove"

    def test_never_policy_forbids_all_trailing_commas_js(self):
        """Test never policy forbids trailing commas even in multiline JavaScript arrays."""
        code = """const arr = [
    1,
    2,
    3,
]"""
        findings = self._run_rule(code, language="javascript", config={"trailing_commas": "never"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_commas"
        assert "never" in finding.message
        assert finding.meta is not None
        assert finding.meta["action"] == "remove"

    def test_never_policy_allows_no_trailing_commas_python(self):
        """Test never policy allows code without trailing commas in Python."""
        code = """data = [
    1,
    2,
    3
]
config = {"a": 1, "b": 2}"""
        findings = self._run_rule(code, config={"trailing_commas": "never"})
        
        assert len(findings) == 0

    def test_always_policy_requires_trailing_commas_ts(self):
        """Test always policy requires trailing commas in TypeScript."""
        code = """const config = {
    name: "test",
    version: "1.0"
}"""
        findings = self._run_rule(code, language="typescript", config={"trailing_commas": "always"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_commas"
        assert "always" in finding.message
        assert finding.meta is not None
        assert finding.meta["action"] == "add"

    def test_always_policy_allows_existing_trailing_commas_python(self):
        """Test always policy allows existing trailing commas in Python."""
        code = """data = [1, 2, 3,]
config = {
    "a": 1,
    "b": 2,
}"""
        findings = self._run_rule(code, config={"trailing_commas": "always"})
        
        assert len(findings) == 0

    def test_empty_containers_ignored_python(self):
        """Test that empty containers are ignored in Python."""
        code = """empty_list = []
empty_dict = {}
empty_tuple = ()"""
        findings = self._run_rule(code, config={"trailing_commas": "always"})
        
        assert len(findings) == 0

    def test_function_parameters_multiline_js(self):
        """Test trailing commas in multiline function parameters in JavaScript."""
        code = """function test(
    a,
    b,
    c
) {
    return a + b + c;
}"""
        findings = self._run_rule(code, language="javascript", config={"trailing_commas": "multiline-only"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "style.trailing_commas"
        assert finding.meta is not None
        assert finding.meta["action"] == "add"

    def test_default_policy_is_multiline_only(self):
        """Test that default policy is multiline-only."""
        code = """data = [
    1,
    2,
    3
]"""
        # No config provided, should use default "multiline-only"
        findings = self._run_rule(code)
        
        assert len(findings) == 1
        finding = findings[0]
        assert "multiline-only" in finding.message

    def test_invalid_policy_defaults_to_multiline_only(self):
        """Test that invalid policy defaults to multiline-only."""
        code = """data = [
    1,
    2,
    3
]"""
        findings = self._run_rule(code, config={"trailing_commas": "invalid_policy"})
        
        assert len(findings) == 1
        finding = findings[0]
        assert "multiline-only" in finding.message

    @pytest.mark.skip(reason="suggest-only: rule provides suggestions, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped since this rule is suggest-only."""
        pass

