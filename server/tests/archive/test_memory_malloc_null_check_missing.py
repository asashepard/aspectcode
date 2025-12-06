"""
Unit tests for MemoryMallocNullCheckMissingRule

Tests the detection of malloc family allocations used without null checks.
"""

import unittest
from unittest.mock import Mock, MagicMock

try:
    from ..rules.memory_malloc_null_check_missing import MemoryMallocNullCheckMissingRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.memory_malloc_null_check_missing import MemoryMallocNullCheckMissingRule
    from engine.types import RuleContext, Finding


class TestMemoryMallocNullCheckMissingRule(unittest.TestCase):
    """Test cases for the MemoryMallocNullCheckMissingRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = MemoryMallocNullCheckMissingRule()

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        meta = self.rule.meta
        self.assertEqual(meta.id, "memory.malloc_null_check_missing")
        self.assertEqual(meta.category, "memory")
        self.assertEqual(meta.tier, 0)
        self.assertEqual(meta.priority, "P1")
        self.assertEqual(meta.autofix_safety, "suggest-only")
        self.assertIn("c", meta.langs)
        self.assertIn("cpp", meta.langs)

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        requires = self.rule.requires
        self.assertTrue(requires.syntax)
        self.assertFalse(requires.scopes)
        self.assertFalse(requires.raw_text)

    def test_malloc_family_constants(self):
        """Test that malloc family functions are properly defined."""
        expected_functions = {
            "malloc", "calloc", "realloc", "strdup", "strndup", 
            "aligned_alloc", "posix_memalign"
        }
        self.assertEqual(self.rule.MALLOC_FAMILY, expected_functions)

    def test_deref_consumers_constants(self):
        """Test that dereference consumer functions are properly defined."""
        expected_consumers = {
            "memcpy", "memmove", "memset", "strcpy", "strncpy", 
            "strlen", "fwrite", "fread", "printf", "sprintf",
            "snprintf", "fprintf"
        }
        self.assertEqual(self.rule.DEREF_CONSUMERS, expected_consumers)

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

    def test_extract_variable_name_identifier(self):
        """Test variable name extraction from identifier nodes."""
        node = Mock()
        node.type = "identifier"
        node.text = "ptr"
        
        result = self.rule._extract_variable_name(node)
        self.assertEqual(result, "ptr")

    def test_extract_variable_name_bytes(self):
        """Test variable name extraction when text is bytes."""
        node = Mock()
        node.type = "identifier"
        node.text = b"ptr"
        
        result = self.rule._extract_variable_name(node)
        self.assertEqual(result, "ptr")

    def test_extract_variable_name_pointer_declarator(self):
        """Test variable name extraction from pointer declarators."""
        inner_node = Mock()
        inner_node.type = "identifier"
        inner_node.text = "ptr"
        
        node = Mock()
        node.type = "pointer_declarator"
        node.children = [inner_node]
        
        # Mock the _get_child_by_field to return the inner node
        self.rule._get_child_by_field = Mock(return_value=inner_node)
        
        result = self.rule._extract_variable_name(node)
        self.assertEqual(result, "ptr")

    def test_is_malloc_call_direct(self):
        """Test detection of direct malloc calls."""
        ctx = Mock()
        
        func_node = Mock()
        func_node.text = "malloc"
        
        node = Mock()
        node.type = "call_expression"
        
        self.rule._get_child_by_field = Mock(return_value=func_node)
        self.rule._get_node_text = Mock(return_value="malloc")
        
        result = self.rule._is_malloc_call(ctx, node)
        self.assertTrue(result)

    def test_is_malloc_call_cast_expression(self):
        """Test detection of malloc calls in cast expressions."""
        ctx = Mock()
        
        # Inner malloc call
        func_node = Mock()
        func_node.text = "malloc"
        
        inner_call = Mock()
        inner_call.type = "call_expression"
        
        # Cast expression containing malloc
        node = Mock()
        node.type = "cast_expression"
        
        def mock_get_child_by_field(node, field):
            if field == "value":
                return inner_call
            elif field == "function":
                return func_node
            return None
        
        def mock_get_node_text(ctx, node):
            if node == func_node:
                return "malloc"
            return ""
        
        self.rule._get_child_by_field = mock_get_child_by_field
        self.rule._get_node_text = mock_get_node_text
        
        result = self.rule._is_malloc_call(ctx, node)
        self.assertTrue(result)

    def test_is_malloc_call_non_malloc(self):
        """Test that non-malloc calls are not detected."""
        ctx = Mock()
        
        func_node = Mock()
        func_node.text = "printf"
        
        node = Mock()
        node.type = "call_expression"
        
        self.rule._get_child_by_field = Mock(return_value=func_node)
        self.rule._get_node_text = Mock(return_value="printf")
        
        result = self.rule._is_malloc_call(ctx, node)
        self.assertFalse(result)

    def test_statement_checks_variable_basic_null_check(self):
        """Test detection of basic null checks."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="if (!ptr) return;")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertTrue(result)

    def test_statement_checks_variable_comparison_null(self):
        """Test detection of null comparison checks."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="if (ptr == NULL) { return; }")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertTrue(result)

    def test_statement_checks_variable_comparison_nullptr(self):
        """Test detection of nullptr comparison checks."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="if (ptr != nullptr) { use_ptr(); }")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertTrue(result)

    def test_statement_checks_variable_assert(self):
        """Test detection of assert checks."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="assert(ptr);")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertTrue(result)

    def test_statement_checks_variable_inline_allocation_check(self):
        """Test detection of inline allocation and check."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="if (!(ptr = malloc(10))) return;")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertTrue(result)

    def test_statement_checks_variable_no_check(self):
        """Test that non-check statements are not detected."""
        ctx = Mock()
        stmt = Mock()
        
        self.rule._get_node_text = Mock(return_value="ptr[0] = 42;")
        
        result = self.rule._statement_checks_variable(ctx, stmt, "ptr")
        self.assertFalse(result)

    def test_get_node_text_with_bytes(self):
        """Test node text extraction when text is bytes."""
        ctx = Mock()
        node = Mock()
        node.text = b"malloc"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "malloc")

    def test_get_node_text_with_string(self):
        """Test node text extraction when text is string."""
        ctx = Mock()
        node = Mock()
        node.text = "malloc"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "malloc")

    def test_get_node_text_from_raw_text(self):
        """Test node text extraction from raw text using byte positions."""
        ctx = Mock()
        ctx.raw_text = "char *ptr = malloc(10);"
        
        node = Mock()
        node.start_byte = 12
        node.end_byte = 18  # "malloc"
        delattr(node, 'text')  # Remove text attribute to force fallback
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "malloc")

    def test_get_child_by_field_assignment_left(self):
        """Test getting left child of assignment expression."""
        left_child = Mock()
        op_child = Mock()
        right_child = Mock()
        
        node = Mock()
        node.type = "assignment_expression"
        node.children = [left_child, op_child, right_child]
        node.child_by_field_name = Mock(return_value=left_child)
        
        result = self.rule._get_child_by_field(node, "left")
        self.assertEqual(result, left_child)
        node.child_by_field_name.assert_called_once_with("left")

    def test_get_child_by_field_assignment_right(self):
        """Test getting right child of assignment expression."""
        left_child = Mock()
        op_child = Mock()
        right_child = Mock()
        
        node = Mock()
        node.type = "assignment_expression"
        node.children = [left_child, op_child, right_child]
        node.child_by_field_name = Mock(return_value=right_child)
        
        result = self.rule._get_child_by_field(node, "right")
        self.assertEqual(result, right_child)
        node.child_by_field_name.assert_called_once_with("right")

    def test_get_child_by_field_call_function(self):
        """Test getting function child of call expression."""
        func_child = Mock()
        args_child = Mock()
        
        node = Mock()
        node.type = "call_expression"
        node.children = [func_child, args_child]
        node.child_by_field_name = Mock(return_value=func_child)
        
        result = self.rule._get_child_by_field(node, "function")
        self.assertEqual(result, func_child)
        node.child_by_field_name.assert_called_once_with("function")

    def test_get_child_by_field_call_arguments(self):
        """Test getting arguments child of call expression."""
        func_child = Mock()
        args_child = Mock()
        
        node = Mock()
        node.type = "call_expression"
        node.children = [func_child, args_child]
        node.child_by_field_name = Mock(return_value=args_child)
        
        result = self.rule._get_child_by_field(node, "arguments")
        self.assertEqual(result, args_child)
        node.child_by_field_name.assert_called_once_with("arguments")


if __name__ == '__main__':
    unittest.main()

