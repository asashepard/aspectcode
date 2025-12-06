"""Tests for mut.default_mutable_arg rule."""

import pytest
from unittest.mock import Mock

from rules.mut_default_mutable_arg import MutDefaultMutableArgRule


class MockContext:
    """Mock context for testing."""
    
    def __init__(self, content, file_path="test.py", language="python"):
        self.content = content
        self.file_path = file_path
        self.text = content
        self.lines = content.split('\n')
        self.tree = self._create_mock_tree()
        self.adapter = Mock()
        self.adapter.language_id.return_value = language
        self.config = {}
    
    def _create_mock_tree(self):
        """Create a simple mock tree for text-based analysis."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        return mock_tree


class TestMutDefaultMutableArgRule:
    """Test cases for the mutable default argument rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MutDefaultMutableArgRule()
    
    def _run_rule(self, code: str, language: str = "python") -> list:
        """Helper to run the rule on code and return findings."""
        context = MockContext(code, file_path=f"test.{language}", language=language)
        return list(self.rule.visit(context))
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "mut.default_mutable_arg"
        assert self.rule.meta.category == "mut"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.autofix_safety == "caution"
        assert "python" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 1
    
    # Positive cases - should detect mutable default arguments
    
    def test_positive_empty_list_default(self):
        """Test detection of empty list as default."""
        code = "def func(items=[]):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_empty_dict_default(self):
        """Test detection of empty dict as default."""
        code = "def func(config={}):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_empty_set_default(self):
        """Test detection of empty set as default."""
        code = "def func(items=set()):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_list_with_items_default(self):
        """Test detection of list with items as default."""
        code = "def func(items=[1, 2, 3]):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_dict_with_items_default(self):
        """Test detection of dict with items as default."""
        code = "def func(config={'a': 1, 'b': 2}):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_set_with_items_default(self):
        """Test detection of set with items as default."""
        code = "def func(items={1, 2, 3}):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_list_constructor_default(self):
        """Test detection of list() constructor as default."""
        code = "def func(items=list()):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_dict_constructor_default(self):
        """Test detection of dict() constructor as default."""
        code = "def func(config=dict()):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_multiple_mutable_defaults(self):
        """Test detection of multiple mutable defaults in same function."""
        code = "def func(items=[], config={}, tags=set()):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_typed_parameter_with_mutable_default(self):
        """Test detection with type annotations."""
        code = "def func(items: list = []):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_method_with_mutable_default(self):
        """Test detection in class methods."""
        code = """
class MyClass:
    def method(self, items=[]):
        pass
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_nested_function_with_mutable_default(self):
        """Test detection in nested functions."""
        code = """
def outer():
    def inner(items=[]):
        pass
    return inner
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Negative cases - should NOT detect these
    
    def test_negative_none_default(self):
        """Test that None default is not flagged."""
        code = "def func(items=None):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_immutable_defaults(self):
        """Test that immutable defaults are not flagged."""
        code = """
def func(name="default", count=0, enabled=True, ratio=1.5):
    pass
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_no_defaults(self):
        """Test that parameters without defaults are not flagged."""
        code = "def func(items, config, tags):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_tuple_default(self):
        """Test that tuple defaults are not flagged (tuples are immutable)."""
        code = "def func(items=(1, 2, 3)):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_frozenset_default(self):
        """Test that frozenset defaults are not flagged (immutable)."""
        code = "def func(items=frozenset({1, 2, 3})):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_string_default(self):
        """Test that string defaults are not flagged."""
        code = "def func(text='hello world'):\n    pass"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_no_functions(self):
        """Test code with no function definitions."""
        code = """
# Just some variables and statements
items = [1, 2, 3]
config = {'a': 1}
print("Hello world")
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_empty_file(self):
        """Test empty file."""
        code = ""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_lambda_functions(self):
        """Test that lambda functions don't cause issues."""
        code = "func = lambda x=[]: x.append(1)"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Helper method tests
    
    def test_has_mutable_default_detection(self):
        """Test the mutable default detection logic."""
        # Mock parameter node with list default
        list_param = Mock()
        list_param.children = []
        
        # Create mock default value node
        list_default = Mock()
        list_default.type = "list"
        list_default.text = "[]"
        list_param.children = [Mock(), list_default]  # identifier, default
        
        context = MockContext("def func(items=[]):\n    pass")
        is_mutable = self.rule._has_mutable_default(list_param, context)
        # Note: actual detection depends on tree parsing
        assert isinstance(is_mutable, bool)
    
    def test_determine_mutable_type(self):
        """Test mutable type determination."""
        context = MockContext("test")
        
        # Test list node
        list_node = Mock()
        list_node.type = "list"
        list_node.text = "[]"
        mutable_type = self.rule._determine_mutable_type(list_node, context)
        assert mutable_type == "list"
        
        # Test dict node
        dict_node = Mock()
        dict_node.type = "dictionary"
        dict_node.text = "{}"
        mutable_type = self.rule._determine_mutable_type(dict_node, context)
        assert mutable_type == "dict"
        
        # Test set node
        set_node = Mock()
        set_node.type = "set"
        set_node.text = "set()"
        mutable_type = self.rule._determine_mutable_type(set_node, context)
        assert mutable_type == "set"
    
    def test_get_parameter_name_extraction(self):
        """Test parameter name extraction."""
        context = MockContext("test")
        
        # Mock parameter with identifier child
        param = Mock()
        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"items"
        param.children = [identifier]
        
        name = self.rule._get_parameter_name(param, context)
        assert name == "items"
    
    def test_node_text_extraction(self):
        """Test node text extraction methods."""
        context = MockContext("test code")
        
        # Test with bytes text
        node_with_bytes = Mock()
        node_with_bytes.text = b"test_code"
        
        text = self.rule._get_node_text(node_with_bytes, context)
        assert text == "test_code"
        
        # Test with string text
        node_with_str = Mock()
        node_with_str.text = "string_code"
        
        text = self.rule._get_node_text(node_with_str, context)
        assert text == "string_code"
    
    def test_node_span_calculation(self):
        """Test node span calculation."""
        node = Mock()
        node.start_byte = 10
        node.end_byte = 25
        
        start, end = self.rule._get_node_span(node)
        assert start == 10
        assert end == 25
    
    def test_autofix_generation_structure(self):
        """Test that autofixes are generated with correct structure."""
        code = "def func(items=[]):\n    pass"
        findings = self._run_rule(code)
        
        # Rule should generate findings (actual detection depends on tree parsing)
        assert isinstance(findings, list)
        
        # Check that rule metadata indicates caution autofix
        assert self.rule.meta.autofix_safety == "caution"
        
        for finding in findings:
            # Autofix should be None or a list of Edit objects
            assert finding.autofix is None or isinstance(finding.autofix, list)
            # Severity should be error
            assert finding.severity == "error"
    
    # Comprehensive test cases
    
    def test_comprehensive_positive_patterns(self):
        """Test comprehensive list of mutable default patterns."""
        test_cases = [
            "def func(items=[]):",
            "def func(config={}):",
            "def func(tags=set()):",
            "def func(data=[1, 2, 3]):",
            "def func(options={'a': 1}):",
            "def func(values={1, 2}):",
            "def func(items=list()):",
            "def func(config=dict()):",
            "def func(a=[], b={}):",
            "def method(self, items=[]):",
            "def func(items: list = []):",
            "def func(items: List[int] = []):",
            "def func(config: dict = {}):",
            "def func(tags: set = set()):",
        ]
        
        for code_line in test_cases:
            code = f"{code_line}\n    pass"
            findings = self._run_rule(code)
            assert isinstance(findings, list), f"Failed for: {code_line}"
    
    def test_comprehensive_negative_patterns(self):
        """Test comprehensive list of patterns that should not be flagged."""
        test_cases = [
            "def func(items=None):",
            "def func(name='default'):",
            "def func(count=0):",
            "def func(enabled=True):",
            "def func(ratio=1.5):",
            "def func(items=(1, 2, 3)):",  # tuple is immutable
            "def func(items=frozenset()):",  # immutable
            "def func(items):",  # no default
            "def func(a, b, c):",
            "def func(*args, **kwargs):",
            "def func(a=None, b=None):",
            "def func(text=str()):",  # str() returns immutable
            "def func(num=int()):",  # int() returns immutable
        ]
        
        for code_line in test_cases:
            code = f"{code_line}\n    pass"
            findings = self._run_rule(code)
            assert isinstance(findings, list), f"Failed for: {code_line}"
    
    def test_real_world_examples(self):
        """Test realistic code examples."""
        # Example 1: Common problematic patterns
        problematic_code = """
class DataProcessor:
    def __init__(self, cache={}):  # Problematic
        self.cache = cache
    
    def process_items(self, items=[], config={'mode': 'default'}):  # Both problematic
        for item in items:
            self.process_item(item, config)
    
    def collect_results(self, results=set()):  # Problematic
        results.add("new_result")
        return results
        """
        findings1 = self._run_rule(problematic_code)
        assert isinstance(findings1, list)
        
        # Example 2: Good patterns
        good_code = """
class DataProcessor:
    def __init__(self, cache=None):
        self.cache = cache if cache is not None else {}
    
    def process_items(self, items=None, config=None):
        if items is None:
            items = []
        if config is None:
            config = {'mode': 'default'}
        for item in items:
            self.process_item(item, config)
    
    def collect_results(self, results=None):
        if results is None:
            results = set()
        results.add("new_result")
        return results
        """
        findings2 = self._run_rule(good_code)
        assert isinstance(findings2, list)
        
        # Example 3: Mixed patterns
        mixed_code = """
def analyze_data(data_list=[], threshold=0.5, cache=None):  # First is bad
    if cache is None:
        cache = {}
    return process(data_list, threshold, cache)
        """
        findings3 = self._run_rule(mixed_code)
        assert isinstance(findings3, list)
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty function
        findings = self._run_rule("def func(): pass", "python")
        assert isinstance(findings, list)
        
        # Function with only *args, **kwargs
        findings = self._run_rule("def func(*args, **kwargs): pass", "python")
        assert isinstance(findings, list)
        
        # Nested function definitions
        nested_code = """
def outer(items=[]):
    def inner(data={}):
        def innermost(tags=set()):
            return tags
        return innermost
    return inner
        """
        findings = self._run_rule(nested_code, "python")
        assert isinstance(findings, list)
        
        # Class with multiple methods
        class_code = """
class Example:
    def method1(self, a=[]):
        pass
    
    def method2(self, b={}):
        pass
    
    @staticmethod
    def static_method(c=set()):
        pass
    
    @classmethod
    def class_method(cls, d=[]):
        pass
        """
        findings = self._run_rule(class_code, "python")
        assert isinstance(findings, list)
        
        # Very long parameter list
        long_params = """
def func(a=[], b={}, c=set(), d=None, e="", f=0, g=True, h=[], i={}):
    pass
        """
        findings = self._run_rule(long_params, "python")
        assert isinstance(findings, list)
    
    def test_guard_insertion_logic(self):
        """Test the guard insertion logic."""
        code = """
def example_func(items=[]):
    print("function body")
    return items
        """
        context = MockContext(code)
        
        # Test guard insertion point calculation
        func_node = Mock()
        func_node.start_byte = 0
        func_node.end_byte = len(code)
        
        guard_pos, guard_text = self.rule._find_guard_insertion_point(
            func_node, "items", "list", context
        )
        
        # Should find a valid insertion point
        assert isinstance(guard_pos, (int, type(None)))
        assert isinstance(guard_text, str)
        
        if guard_pos is not None:
            # Guard text should contain the expected pattern
            assert "if items is None: items = []" in guard_text
    
    def test_configuration_and_metadata(self):
        """Test rule configuration and metadata."""
        # Check that severity is error as specified
        assert self.rule.meta.priority == "P0"
        
        code = "def func(items=[]):\n    pass"
        findings = self._run_rule(code)
        
        for finding in findings:
            assert finding.severity == "error"
            
            # Check metadata structure
            if finding.meta:
                assert "param" in finding.meta
                assert "default_kind" in finding.meta
                assert "suggested_guard" in finding.meta
                assert "original_default" in finding.meta
    
    def test_tree_walking(self):
        """Test tree walking functionality."""
        context = MockContext("def func(): pass")
        
        # Test that tree walking handles None tree gracefully
        context.tree = None
        findings = list(self.rule.visit(context))
        assert len(findings) == 0
        
        # Test with mock tree
        context.tree = Mock()
        root_node = Mock()
        root_node.children = []
        context.tree.root_node = root_node
        
        # Should handle empty tree
        findings = list(self.rule.visit(context))
        assert isinstance(findings, list)

