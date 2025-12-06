"""
Unit tests for TypesTsAnyOveruseRule

Tests the detection of TypeScript escape hatch overuse including any types and non-null assertions.
"""

import unittest
from unittest.mock import Mock, MagicMock

try:
    from ..rules.types_ts_any_overuse import TypesTsAnyOveruseRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.types_ts_any_overuse import TypesTsAnyOveruseRule
    from engine.types import RuleContext, Finding


class TestTypesTsAnyOveruseRule(unittest.TestCase):
    """Test cases for the TypesTsAnyOveruseRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = TypesTsAnyOveruseRule()

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        meta = self.rule.meta
        self.assertEqual(meta.id, "types.ts_any_overuse")
        self.assertEqual(meta.category, "types")
        self.assertEqual(meta.tier, 0)
        self.assertEqual(meta.priority, "P1")
        self.assertEqual(meta.autofix_safety, "suggest-only")
        self.assertIn("typescript", meta.langs)

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        requires = self.rule.requires
        self.assertTrue(requires.syntax)
        self.assertFalse(requires.scopes)
        self.assertFalse(requires.raw_text)

    def test_message_constants(self):
        """Test that message constants are properly defined."""
        self.assertEqual(self.rule.ANY_MSG, "Avoid 'any'; prefer precise types or 'unknown' with narrowing.")
        self.assertEqual(self.rule.NN_MSG, "Avoid non-null assertion '!'; add a null check, use optional chaining, or refine the type.")

    def test_visit_unsupported_language(self):
        """Test that rule does nothing for unsupported languages."""
        ctx = Mock()
        ctx.tree = Mock()
        ctx.adapter.language_id = "javascript"
        
        findings = list(self.rule.visit(ctx))
        self.assertEqual(len(findings), 0)

    def test_visit_no_tree(self):
        """Test that rule does nothing when no syntax tree is available."""
        ctx = Mock()
        ctx.tree = None
        ctx.adapter.language_id = "typescript"
        
        findings = list(self.rule.visit(ctx))
        self.assertEqual(len(findings), 0)

    def test_get_node_text_with_bytes(self):
        """Test node text extraction when text is bytes."""
        ctx = Mock()
        node = Mock()
        node.text = b"any"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "any")

    def test_get_node_text_with_string(self):
        """Test node text extraction when text is string."""
        ctx = Mock()
        node = Mock()
        node.text = "any"
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "any")

    def test_get_node_text_from_raw_text(self):
        """Test node text extraction from raw text using byte positions."""
        ctx = Mock()
        ctx.raw_text = "let x: any = 5;"
        
        node = Mock()
        node.start_byte = 7
        node.end_byte = 10  # "any"
        delattr(node, 'text')  # Remove text attribute to force fallback
        
        result = self.rule._get_node_text(ctx, node)
        self.assertEqual(result, "any")

    def test_type_contains_any_positive(self):
        """Test detection of 'any' in type annotations."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="any")
        
        result = self.rule._type_contains_any(ctx, node)
        self.assertTrue(result)

    def test_type_contains_any_in_union(self):
        """Test detection of 'any' in union types."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="string | any | number")
        
        result = self.rule._type_contains_any(ctx, node)
        self.assertTrue(result)

    def test_type_contains_any_negative(self):
        """Test that types without 'any' are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="string | number")
        
        result = self.rule._type_contains_any(ctx, node)
        self.assertFalse(result)

    def test_type_contains_any_similar_word(self):
        """Test that similar words to 'any' are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="company | many")
        
        result = self.rule._type_contains_any(ctx, node)
        self.assertFalse(result)

    def test_is_as_any_positive(self):
        """Test detection of 'as any' expressions."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="value as any")
        
        result = self.rule._is_as_any(ctx, node)
        self.assertTrue(result)

    def test_is_as_any_negative(self):
        """Test that 'as' expressions without 'any' are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="value as string")
        
        result = self.rule._is_as_any(ctx, node)
        self.assertFalse(result)

    def test_is_as_any_no_as_keyword(self):
        """Test that expressions without 'as' are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="any + 1")
        
        result = self.rule._is_as_any(ctx, node)
        self.assertFalse(result)

    def test_has_definite_assignment_assertion_positive(self):
        """Test detection of definite assignment assertions."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="field!: string")
        
        result = self.rule._has_definite_assignment_assertion(ctx, node)
        self.assertTrue(result)

    def test_has_definite_assignment_assertion_with_access_modifier(self):
        """Test detection with access modifiers."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="private field!: string")
        
        result = self.rule._has_definite_assignment_assertion(ctx, node)
        self.assertTrue(result)

    def test_has_definite_assignment_assertion_negative(self):
        """Test that normal field declarations are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="field: string")
        
        result = self.rule._has_definite_assignment_assertion(ctx, node)
        self.assertFalse(result)

    def test_has_definite_assignment_assertion_no_type(self):
        """Test that fields without type annotations are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="field = 'value'")
        
        result = self.rule._has_definite_assignment_assertion(ctx, node)
        self.assertFalse(result)

    def test_has_definite_assignment_assertion_exclamation_after_colon(self):
        """Test that exclamation marks after colon are not flagged."""
        ctx = Mock()
        node = Mock()
        
        self.rule._get_node_text = Mock(return_value="field: string = 'test!'")
        
        result = self.rule._has_definite_assignment_assertion(ctx, node)
        self.assertFalse(result)

    def test_walk_nodes_simple(self):
        """Test basic node walking functionality."""
        # Create a simple tree structure
        child1 = Mock()
        child1.children = []
        child2 = Mock()
        child2.children = []
        
        root = Mock()
        root.children = [child1, child2]
        
        nodes = list(self.rule._walk_nodes(root))
        
        self.assertEqual(len(nodes), 3)  # root + 2 children
        self.assertIn(root, nodes)
        self.assertIn(child1, nodes)
        self.assertIn(child2, nodes)

    def test_walk_nodes_nested(self):
        """Test node walking with nested structure."""
        # Create a nested tree structure
        grandchild = Mock()
        grandchild.children = []
        
        child = Mock()
        child.children = [grandchild]
        
        root = Mock()
        root.children = [child]
        
        nodes = list(self.rule._walk_nodes(root))
        
        self.assertEqual(len(nodes), 3)  # root + child + grandchild
        self.assertIn(root, nodes)
        self.assertIn(child, nodes)
        self.assertIn(grandchild, nodes)

    def test_integration_any_type_annotation(self):
        """Test integration with mock tree for any type annotation."""
        ctx = Mock()
        ctx.adapter.language_id = "typescript"
        ctx.raw_text = "let x: any = 5;"
        ctx.file_path = "test.ts"
        
        # Mock type annotation node
        type_node = Mock()
        type_node.type = "type_annotation"
        type_node.start_byte = 7
        type_node.end_byte = 10
        type_node.children = []
        
        root = Mock()
        root.children = [type_node]
        
        ctx.tree = Mock()
        ctx.tree.root_node = root
        
        self.rule._get_node_text = Mock(return_value="any")
        
        findings = list(self.rule.visit(ctx))
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].message, self.rule.ANY_MSG)
        self.assertEqual(findings[0].start_byte, 7)
        self.assertEqual(findings[0].end_byte, 10)

    def test_integration_as_any_expression(self):
        """Test integration with mock tree for as any expression."""
        ctx = Mock()
        ctx.adapter.language_id = "typescript"
        ctx.raw_text = "const x = value as any;"
        ctx.file_path = "test.ts"
        
        # Mock as expression node
        as_node = Mock()
        as_node.type = "as_expression"
        as_node.start_byte = 10
        as_node.end_byte = 22
        as_node.children = []
        
        root = Mock()
        root.children = [as_node]
        
        ctx.tree = Mock()
        ctx.tree.root_node = root
        
        self.rule._get_node_text = Mock(return_value="value as any")
        
        findings = list(self.rule.visit(ctx))
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].message, self.rule.ANY_MSG + " (found 'as any')")
        self.assertEqual(findings[0].start_byte, 10)
        self.assertEqual(findings[0].end_byte, 22)

    def test_integration_non_null_expression(self):
        """Test integration with mock tree for non-null assertion."""
        ctx = Mock()
        ctx.adapter.language_id = "typescript"
        ctx.raw_text = "const x = value!.prop;"
        ctx.file_path = "test.ts"
        
        # Mock non-null expression node
        nn_node = Mock()
        nn_node.type = "non_null_expression"
        nn_node.start_byte = 10
        nn_node.end_byte = 16
        nn_node.children = []
        
        root = Mock()
        root.children = [nn_node]
        
        ctx.tree = Mock()
        ctx.tree.root_node = root
        
        findings = list(self.rule.visit(ctx))
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].message, self.rule.NN_MSG)
        self.assertEqual(findings[0].start_byte, 10)
        self.assertEqual(findings[0].end_byte, 16)

    def test_integration_definite_assignment(self):
        """Test integration with mock tree for definite assignment assertion."""
        ctx = Mock()
        ctx.adapter.language_id = "typescript"
        ctx.raw_text = "class C { field!: string }"
        ctx.file_path = "test.ts"
        
        # Mock class field declaration node
        field_node = Mock()
        field_node.type = "public_field_definition"
        field_node.start_byte = 10
        field_node.end_byte = 24
        field_node.children = []
        
        root = Mock()
        root.children = [field_node]
        
        ctx.tree = Mock()
        ctx.tree.root_node = root
        
        self.rule._get_node_text = Mock(return_value="field!: string")
        
        findings = list(self.rule.visit(ctx))
        
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].message, self.rule.NN_MSG + " (definite assignment '!')")
        self.assertEqual(findings[0].start_byte, 10)
        self.assertEqual(findings[0].end_byte, 24)


if __name__ == '__main__':
    unittest.main()

