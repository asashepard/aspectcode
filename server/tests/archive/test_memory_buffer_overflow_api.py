"""
Unit tests for MemoryBufferOverflowApiRule

Tests the detection of unsafe C/C++ APIs that can cause buffer overflows.
"""

import unittest
from unittest.mock import Mock, MagicMock

try:
    from ..rules.memory_buffer_overflow_api import MemoryBufferOverflowApiRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.memory_buffer_overflow_api import MemoryBufferOverflowApiRule
    from engine.types import RuleContext, Finding


class TestMemoryBufferOverflowApiRule(unittest.TestCase):
    """Test cases for the MemoryBufferOverflowApiRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = MemoryBufferOverflowApiRule()

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        meta = self.rule.meta
        self.assertEqual(meta.id, "memory.buffer_overflow_api")
        self.assertEqual(meta.category, "memory")
        self.assertEqual(meta.tier, 0)
        self.assertEqual(meta.priority, "P0")
        self.assertEqual(meta.autofix_safety, "suggest-only")
        self.assertIn("c", meta.langs)
        self.assertIn("cpp", meta.langs)

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        requires = self.rule.requires
        self.assertTrue(requires.syntax)
        self.assertFalse(requires.scopes)
        self.assertFalse(requires.raw_text)

    def test_bad_callees_constants(self):
        """Test that unsafe function names are properly defined."""
        expected_functions = {
            "gets", "strcpy", "wcscpy", "strcat", "wcscat",
            "sprintf", "vsprintf", "swprintf", "vswprintf",
            "getwd", "streadd", "strecpy", "strtrns"
        }
        self.assertEqual(self.rule.BAD_CALLEES, expected_functions)

    def test_scanf_family_constants(self):
        """Test that scanf family functions are properly defined."""
        expected_functions = {
            "scanf", "sscanf", "fscanf", "vscanf", "vsscanf", 
            "vfscanf", "swscanf", "wscanf"
        }
        self.assertEqual(self.rule.SCANF_FAMILY, expected_functions)

    def test_visit_unsupported_language(self):
        """Test that rule does nothing for unsupported languages."""
        ctx = Mock()
        ctx.tree = Mock()
        ctx.adapter.language_id = "python"
        
        findings = list(self.rule.visit(ctx))
        self.assertEqual(len(findings), 0)

    def test_visit_no_tree(self):
        """Test that rule does nothing when no syntax tree is available."""
        ctx = Mock()
        ctx.tree = None
        ctx.adapter.language_id = "c"
        
        findings = list(self.rule.visit(ctx))
        self.assertEqual(len(findings), 0)

    def test_get_node_text_with_bytes(self):
        """Test node text extraction when text is bytes."""
        ctx = Mock()
        node = Mock()
        node.text = b"strcpy"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "strcpy")

    def test_get_node_text_with_string(self):
        """Test node text extraction when text is string."""
        ctx = Mock()
        node = Mock()
        node.text = "strcpy"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "strcpy")

    def test_get_node_text_from_raw_text(self):
        """Test node text extraction from raw text using byte positions."""
        ctx = Mock()
        ctx.raw_text = "strcpy(dest, src);"
        
        node = Mock()
        node.start_byte = 0
        node.end_byte = 6  # "strcpy"
        delattr(node, 'text')  # Remove text attribute to force fallback
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "strcpy")

    def test_get_callee_name_simple(self):
        """Test getting callee name from simple function call."""
        ctx = Mock()
        
        func_node = Mock()
        func_node.text = "strcpy"
        
        call_node = Mock()
        call_node.children = [func_node]
        
        self.rule._get_node_text = Mock(return_value="strcpy")
        
        result = self.rule._get_callee_name(ctx, call_node)
        self.assertEqual(result, "strcpy")

    def test_get_callee_name_no_children(self):
        """Test getting callee name when call node has no children."""
        ctx = Mock()
        call_node = Mock()
        call_node.children = []
        
        result = self.rule._get_callee_name(ctx, call_node)
        self.assertIsNone(result)

    def test_get_callee_node(self):
        """Test getting callee node from call expression."""
        func_node = Mock()
        call_node = Mock()
        call_node.children = [func_node, Mock()]  # function and args
        
        result = self.rule._get_callee_node(call_node)
        self.assertEqual(result, func_node)

    def test_get_callee_node_no_children(self):
        """Test getting callee node when no children exist."""
        call_node = Mock()
        call_node.children = []
        
        result = self.rule._get_callee_node(call_node)
        self.assertIsNone(result)

    def test_get_call_arguments_simple(self):
        """Test extracting arguments from call expression."""
        arg1 = Mock()
        arg1.type = "string_literal"
        arg2 = Mock()
        arg2.type = "identifier"
        comma = Mock()
        comma.type = ","
        lparen = Mock()
        lparen.type = "("
        rparen = Mock()
        rparen.type = ")"
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [lparen, arg1, comma, arg2, rparen]
        
        func_node = Mock()
        call_node = Mock()
        call_node.children = [func_node, arg_list]
        
        result = self.rule._get_call_arguments(call_node)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0], arg1)
        self.assertEqual(result[1], arg2)

    def test_get_call_arguments_no_args(self):
        """Test extracting arguments when call has no arguments."""
        call_node = Mock()
        call_node.children = [Mock()]  # Only function node
        
        result = self.rule._get_call_arguments(call_node)
        self.assertEqual(len(result), 0)

    def test_is_scanf_unbounded_with_unbounded_string(self):
        """Test detection of unbounded %s in scanf format."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = '"%s"'
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]  # parens and format
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='"%s"')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertTrue(result)

    def test_is_scanf_unbounded_with_bounded_string(self):
        """Test that bounded %s is not flagged."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = '"%10s"'
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='"%10s"')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertFalse(result)

    def test_is_scanf_unbounded_with_unbounded_char(self):
        """Test detection of unbounded %c in scanf format."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = '"%c"'
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='"%c"')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertTrue(result)

    def test_is_scanf_unbounded_with_bracket_format(self):
        """Test detection of unbounded %[ in scanf format."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = '"%[a-z]"'
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='"%[a-z]"')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertTrue(result)

    def test_is_scanf_unbounded_with_safe_format(self):
        """Test that safe formats are not flagged."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = '"%d %f"'
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='"%d %f"')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertFalse(result)

    def test_is_scanf_unbounded_no_arguments(self):
        """Test scanf check when no arguments are present."""
        ctx = Mock()
        call_node = Mock()
        call_node.children = [Mock()]  # Only function node
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertFalse(result)

    def test_is_scanf_unbounded_non_string_literal(self):
        """Test that non-string-literal formats are not checked."""
        ctx = Mock()
        
        format_node = Mock()
        format_node.text = 'format_var'  # Not a string literal
        
        arg_list = Mock()
        arg_list.type = "argument_list"
        arg_list.children = [Mock(), format_node, Mock()]
        
        call_node = Mock()
        call_node.children = [Mock(), arg_list]
        
        self.rule._get_node_text = Mock(return_value='format_var')
        
        result = self.rule._is_scanf_unbounded(ctx, call_node)
        self.assertFalse(result)

    def test_find_function_calls_mock(self):
        """Test finding function calls in a mocked tree."""
        ctx = Mock()
        
        # Create mock call nodes
        call1 = Mock()
        call1.type = "call_expression"
        call1.children = []
        
        call2 = Mock()
        call2.type = "call_expression" 
        call2.children = []
        
        other_node = Mock()
        other_node.type = "declaration"
        other_node.children = [call1]
        
        root = Mock()
        root.children = [other_node, call2]
        
        ctx.tree.root_node = root
        
        # Mock the recursive walk
        calls = []
        def mock_walk(node):
            if node.type == "call_expression":
                calls.append(node)
            for child in getattr(node, 'children', []):
                mock_walk(child)
        
        # Replace the method temporarily
        original_find = self.rule._find_function_calls
        self.rule._find_function_calls = lambda ctx: (mock_walk(ctx.tree.root_node), calls)[1]
        
        try:
            result = self.rule._find_function_calls(ctx)
            self.assertEqual(len(result), 2)
            self.assertIn(call1, result)
            self.assertIn(call2, result)
        finally:
            self.rule._find_function_calls = original_find


if __name__ == '__main__':
    unittest.main()

