"""
Tests for memory.malloc_new_mismatch rule.
"""

import pytest
from unittest.mock import Mock, MagicMock
from rules.memory_malloc_new_mismatch import MemoryMallocNewMismatchRule
from engine.types import RuleContext, Finding


class TestMemoryMallocNewMismatchRule:
    """Test cases for MemoryMallocNewMismatchRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MemoryMallocNewMismatchRule()
    
    def test_meta_properties(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "memory.malloc_new_mismatch"
        assert self.rule.meta.category == "memory"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "cpp" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test rule requires only syntax analysis."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.raw_text is False
        assert self.rule.requires.scopes is False
        assert self.rule.requires.project_graph is False
    
    def test_valid_pairs_constants(self):
        """Test valid allocation/deallocation pairs are defined correctly."""
        expected_pairs = {("new", "delete"), ("new_array", "delete_array"), ("malloc", "free")}
        assert self.rule.VALID_PAIRS == expected_pairs
    
    def test_malloc_family_constants(self):
        """Test malloc family functions are defined correctly."""
        expected_malloc = {"malloc", "calloc", "realloc", "strdup", "strndup", "aligned_alloc", "posix_memalign"}
        assert self.rule.MALLOC_FAMILY == expected_malloc
    
    def test_allocation_type_detection(self):
        """Test allocation type detection methods."""
        ctx = Mock()
        ctx.text = "new int"
        
        # Test new expression
        mock_new = Mock()
        mock_new.type = "new_expression"
        mock_new.children = []  # No new_declarator = regular new
        assert self.rule._get_allocation_type(ctx, mock_new) == "new"
        
        # Test new[] expression
        mock_new_array = Mock()
        mock_new_array.type = "new_expression"
        mock_new_declarator = Mock()
        mock_new_declarator.type = "new_declarator"
        mock_new_array.children = [mock_new_declarator]
        assert self.rule._get_allocation_type(ctx, mock_new_array) == "new_array"
        
        # Test malloc call
        mock_malloc = Mock()
        mock_malloc.type = "call_expression"
        mock_malloc_func = Mock()
        mock_malloc_func.type = "identifier"
        mock_malloc_func.text = b"malloc"
        mock_malloc.children = [mock_malloc_func]
        assert self.rule._get_allocation_type(ctx, mock_malloc) == "malloc"
    
    def test_valid_pair_checking(self):
        """Test valid pair checking logic."""
        assert self.rule._is_valid_pair("new", "delete") is True
        assert self.rule._is_valid_pair("new_array", "delete_array") is True
        assert self.rule._is_valid_pair("malloc", "free") is True
        
        assert self.rule._is_valid_pair("new", "free") is False
        assert self.rule._is_valid_pair("malloc", "delete") is False
        assert self.rule._is_valid_pair("new_array", "delete") is False
    
    def test_empty_file(self):
        """Test rule handles empty files gracefully."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        
        ctx = RuleContext(
            file_path="empty.cpp",
            text="",
            tree=mock_tree,
            adapter=Mock(language_id="cpp"),
            config={}
        )
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test rule skips unsupported languages."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        
        ctx = RuleContext(
            file_path="test.py",
            text="# Python code",
            tree=mock_tree,
            adapter=Mock(language_id="python"),
            config={}
        )
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test rule handles missing tree gracefully."""
        ctx = RuleContext(
            file_path="test.cpp",
            text="void f() {}",
            tree=None,
            adapter=Mock(language_id="cpp"),
            config={}
        )
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_function_detection_utilities(self):
        """Test utility methods for extracting information from nodes."""
        ctx = Mock()
        
        # Test _get_declared_variable_name
        mock_decl = Mock()
        mock_init_declarator = Mock()
        mock_init_declarator.type = "init_declarator"
        mock_identifier = Mock()
        mock_identifier.type = "identifier"
        mock_identifier.text = b"variable_name"
        mock_init_declarator.children = [mock_identifier]
        mock_decl.children = [mock_init_declarator]
        
        result = self.rule._get_declared_variable_name(mock_decl)
        assert result == "variable_name"
        
        # Test _get_function_name
        mock_call = Mock()
        mock_func_id = Mock()
        mock_func_id.type = "identifier"
        mock_func_id.text = b"function_name"
        mock_call.children = [mock_func_id]
        
        result = self.rule._get_function_name(ctx, mock_call)
        assert result == "function_name"
        
        # Test _get_node_text
        ctx.text = "some code here"
        mock_node = Mock()
        mock_node.start_byte = 0
        mock_node.end_byte = 4
        
        result = self.rule._get_node_text(ctx, mock_node)
        assert result == "some"
    
    def test_get_node_text_error_handling(self):
        """Test _get_node_text handles errors gracefully."""
        ctx = Mock()
        ctx.text = "short"
        
        mock_node = Mock()
        mock_node.start_byte = 100  # Beyond text length
        mock_node.end_byte = 200
        
        result = self.rule._get_node_text(ctx, mock_node)
        assert result == ""
    
    def test_rule_registration(self):
        """Test that rule can be discovered by the engine."""
        # This test verifies the rule is properly structured for registration
        from engine.registry import Registry
        from rules import memory_malloc_new_mismatch
        
        registry = Registry()
        registry._extract_rules_from_module(memory_malloc_new_mismatch, "memory_malloc_new_mismatch")
        
        # Check rule was registered
        rules = registry.get_all_rules()
        rule_ids = [rule.meta.id for rule in rules]
        assert "memory.malloc_new_mismatch" in rule_ids

