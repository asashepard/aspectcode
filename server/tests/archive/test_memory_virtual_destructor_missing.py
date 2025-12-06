"""
Tests for Memory Virtual Destructor Missing Rule

Tests the detection of C++ classes with virtual functions but missing virtual destructors.
"""

import pytest
from unittest.mock import Mock

from rules.memory_virtual_destructor_missing import MemoryVirtualDestructorMissingRule
from engine.types import Finding


class TestMemoryVirtualDestructorMissingRule:
    """Test cases for MemoryVirtualDestructorMissingRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MemoryVirtualDestructorMissingRule()
    
    # --- Metadata Tests ---
    
    def test_meta_properties(self):
        """Test rule metadata properties."""
        assert self.rule.meta.id == "memory.virtual_destructor_missing"
        assert self.rule.meta.category == "memory"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "cpp" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 1
    
    def test_requires_correct_capabilities(self):
        """Test rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
    
    # --- Class Detection Tests ---
    
    def test_class_or_struct_detection(self):
        """Test detection of class and struct specifiers."""
        rule = self.rule
        
        # Class specifier
        node = Mock()
        node.type = "class_specifier"
        assert rule._is_class_or_struct(node) is True
        
        # Struct specifier
        node.type = "struct_specifier"
        assert rule._is_class_or_struct(node) is True
        
        # Non-class node
        node.type = "function_definition"
        assert rule._is_class_or_struct(node) is False
    
    def test_final_class_detection(self):
        """Test detection of final classes."""
        rule = self.rule
        ctx = Mock()
        
        # Final class
        node = Mock()
        rule._get_node_text = lambda c, n: "class MyClass final { ... }"
        assert rule._is_final_class(ctx, node) is True
        
        # Non-final class
        rule._get_node_text = lambda c, n: "class MyClass { ... }"
        assert rule._is_final_class(ctx, node) is False
    
    # --- Virtual Function Detection Tests ---
    
    def test_virtual_function_detection(self):
        """Test detection of virtual functions."""
        rule = self.rule
        ctx = Mock()
        
        # Virtual function
        member = Mock()
        member.type = "function_definition"
        rule._get_node_text = lambda c, n: "virtual void foo();"
        assert rule._is_virtual_function(ctx, member) is True
        
        # Virtual pure function
        rule._get_node_text = lambda c, n: "virtual void bar() = 0;"
        assert rule._is_virtual_function(ctx, member) is True
        
        # Non-virtual function
        rule._get_node_text = lambda c, n: "void baz();"
        assert rule._is_virtual_function(ctx, member) is False
        
        # Non-function member
        member.type = "field_declaration"
        rule._get_node_text = lambda c, n: "int x;"
        assert rule._is_virtual_function(ctx, member) is False
    
    # --- Destructor Analysis Tests ---
    
    def test_destructor_analysis_virtual(self):
        """Test analysis of virtual destructor."""
        rule = self.rule
        ctx = Mock()
        
        class_node = Mock()
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        rule._get_class_name = lambda c, n: "MyClass"
        rule._get_class_members = lambda n: [destructor_member]
        rule._get_node_text = lambda c, n: "virtual ~MyClass();"
        
        result = rule._analyze_destructor(ctx, class_node)
        assert result["exists"] is True
        assert result["is_virtual"] is True
        assert result["node"] == destructor_member
    
    def test_destructor_analysis_non_virtual(self):
        """Test analysis of non-virtual destructor."""
        rule = self.rule
        ctx = Mock()
        
        class_node = Mock()
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        rule._get_class_name = lambda c, n: "MyClass"
        rule._get_class_members = lambda n: [destructor_member]
        rule._get_node_text = lambda c, n: "~MyClass();"
        
        result = rule._analyze_destructor(ctx, class_node)
        assert result["exists"] is True
        assert result["is_virtual"] is False
        assert result["node"] == destructor_member
    
    def test_destructor_analysis_missing(self):
        """Test analysis when destructor is missing."""
        rule = self.rule
        ctx = Mock()
        
        class_node = Mock()
        other_member = Mock()
        other_member.type = "function_definition"
        
        rule._get_class_name = lambda c, n: "MyClass"
        rule._get_class_members = lambda n: [other_member]
        rule._get_node_text = lambda c, n: "void foo();"
        
        result = rule._analyze_destructor(ctx, class_node)
        assert result["exists"] is False
        assert result["is_virtual"] is False
        assert result["node"] is None
    
    # --- Class Name Extraction Tests ---
    
    def test_class_name_extraction(self):
        """Test extraction of class names."""
        rule = self.rule
        ctx = Mock()
        
        class_node = Mock()
        name_node = Mock()
        name_node.type = "type_identifier"
        class_node.children = [name_node]
        
        rule._get_node_text = lambda c, n: "MyClass"
        
        result = rule._get_class_name(ctx, class_node)
        assert result == "MyClass"
    
    def test_class_name_span_extraction(self):
        """Test extraction of class name spans."""
        rule = self.rule
        ctx = Mock()
        
        class_node = Mock()
        name_node = Mock()
        name_node.type = "type_identifier"
        class_node.children = [name_node]
        
        rule._get_node_span = lambda c, n: (10, 20) if n == name_node else (0, 50)
        
        result = rule._get_class_name_span(ctx, class_node)
        assert result == (10, 20)
    
    # --- Edge Case Tests ---
    
    def test_empty_file(self):
        """Test rule on empty file."""
        rule = self.rule
        ctx = Mock()
        ctx.tree = None
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test rule on unsupported language."""
        rule = self.rule
        ctx = Mock()
        ctx.tree = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "python"
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test rule when syntax tree is None."""
        rule = self.rule
        ctx = Mock()
        ctx.tree = None
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    # --- Node Text Extraction Tests ---
    
    def test_node_text_extraction(self):
        """Test node text extraction methods."""
        rule = self.rule
        ctx = Mock()
        ctx.text = "class MyClass { };"
        ctx.adapter = Mock()
        ctx.adapter.node_span = lambda n: (6, 13)  # "MyClass"
        
        node = Mock()
        result = rule._get_node_text(ctx, node)
        assert result == "MyClass"
    
    # --- Integration Simulation Tests ---
    
    def test_positive_case_non_virtual_destructor(self):
        """Test positive case: class with virtual function but non-virtual destructor."""
        rule = self.rule
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        ctx.file_path = "test.cpp"
        
        class_node = Mock()
        virtual_member = Mock()
        virtual_member.type = "function_definition"
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        name_node = Mock()
        name_node.type = "type_identifier"
        class_node.children = [name_node]
        
        # Mock helper methods
        def mock_walk_nodes(ctx):
            return [class_node]
        
        def mock_is_class_or_struct(node):
            return node == class_node
        
        def mock_get_class_name(ctx, node):
            return "Base"
        
        def mock_is_final_class(ctx, node):
            return False
        
        def mock_get_class_members(node):
            return [virtual_member, destructor_member]
        
        def mock_is_virtual_function(ctx, member):
            return member == virtual_member
        
        def mock_analyze_destructor(ctx, node):
            return {"exists": True, "is_virtual": False, "node": destructor_member}
        
        def mock_get_class_name_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._walk_nodes = mock_walk_nodes
        rule._is_class_or_struct = mock_is_class_or_struct
        rule._get_class_name = mock_get_class_name
        rule._is_final_class = mock_is_final_class
        rule._get_class_members = mock_get_class_members
        rule._is_virtual_function = mock_is_virtual_function
        rule._analyze_destructor = mock_analyze_destructor
        rule._get_class_name_span = mock_get_class_name_span
        
        # Test
        findings = list(rule.visit(ctx))
        
        # Should detect one issue
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.virtual_destructor_missing"
        assert "Base" in finding.message
        assert "non-virtual destructor" in finding.message
        assert finding.severity == "error"
    
    def test_positive_case_missing_destructor(self):
        """Test positive case: class with virtual function but no destructor."""
        rule = self.rule
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        ctx.file_path = "test.cpp"
        
        class_node = Mock()
        virtual_member = Mock()
        virtual_member.type = "function_definition"
        
        name_node = Mock()
        name_node.type = "type_identifier"
        class_node.children = [name_node]
        
        # Mock helper methods
        def mock_walk_nodes(ctx):
            return [class_node]
        
        def mock_is_class_or_struct(node):
            return node == class_node
        
        def mock_get_class_name(ctx, node):
            return "Base2"
        
        def mock_is_final_class(ctx, node):
            return False
        
        def mock_get_class_members(node):
            return [virtual_member]
        
        def mock_is_virtual_function(ctx, member):
            return member == virtual_member
        
        def mock_analyze_destructor(ctx, node):
            return {"exists": False, "is_virtual": False, "node": None}
        
        def mock_get_class_name_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._walk_nodes = mock_walk_nodes
        rule._is_class_or_struct = mock_is_class_or_struct
        rule._get_class_name = mock_get_class_name
        rule._is_final_class = mock_is_final_class
        rule._get_class_members = mock_get_class_members
        rule._is_virtual_function = mock_is_virtual_function
        rule._analyze_destructor = mock_analyze_destructor
        rule._get_class_name_span = mock_get_class_name_span
        
        # Test
        findings = list(rule.visit(ctx))
        
        # Should detect one issue
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.virtual_destructor_missing"
        assert "Base2" in finding.message
        assert "no virtual destructor" in finding.message
        assert finding.severity == "error"
    
    def test_negative_case_virtual_destructor(self):
        """Test negative case: class with virtual destructor."""
        rule = self.rule
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        ctx.file_path = "test.cpp"
        
        class_node = Mock()
        virtual_member = Mock()
        virtual_member.type = "function_definition"
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        # Mock helper methods
        def mock_walk_nodes(ctx):
            return [class_node]
        
        def mock_is_class_or_struct(node):
            return node == class_node
        
        def mock_get_class_name(ctx, node):
            return "Good"
        
        def mock_is_final_class(ctx, node):
            return False
        
        def mock_get_class_members(node):
            return [virtual_member, destructor_member]
        
        def mock_is_virtual_function(ctx, member):
            return member == virtual_member
        
        def mock_analyze_destructor(ctx, node):
            return {"exists": True, "is_virtual": True, "node": destructor_member}
        
        # Apply mocks
        rule._walk_nodes = mock_walk_nodes
        rule._is_class_or_struct = mock_is_class_or_struct
        rule._get_class_name = mock_get_class_name
        rule._is_final_class = mock_is_final_class
        rule._get_class_members = mock_get_class_members
        rule._is_virtual_function = mock_is_virtual_function
        rule._analyze_destructor = mock_analyze_destructor
        
        # Test
        findings = list(rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_no_virtual_functions(self):
        """Test negative case: class with no virtual functions."""
        rule = self.rule
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        ctx.file_path = "test.cpp"
        
        class_node = Mock()
        regular_member = Mock()
        regular_member.type = "function_definition"
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        # Mock helper methods
        def mock_walk_nodes(ctx):
            return [class_node]
        
        def mock_is_class_or_struct(node):
            return node == class_node
        
        def mock_get_class_name(ctx, node):
            return "Plain"
        
        def mock_is_final_class(ctx, node):
            return False
        
        def mock_get_class_members(node):
            return [regular_member, destructor_member]
        
        def mock_is_virtual_function(ctx, member):
            return False  # No virtual functions
        
        def mock_analyze_destructor(ctx, node):
            return {"exists": True, "is_virtual": False, "node": destructor_member}
        
        # Apply mocks
        rule._walk_nodes = mock_walk_nodes
        rule._is_class_or_struct = mock_is_class_or_struct
        rule._get_class_name = mock_get_class_name
        rule._is_final_class = mock_is_final_class
        rule._get_class_members = mock_get_class_members
        rule._is_virtual_function = mock_is_virtual_function
        rule._analyze_destructor = mock_analyze_destructor
        
        # Test
        findings = list(rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_final_class(self):
        """Test negative case: final class with virtual functions."""
        rule = self.rule
        ctx = Mock()
        ctx.adapter = Mock()
        ctx.adapter.language_id = "cpp"
        ctx.file_path = "test.cpp"
        
        class_node = Mock()
        virtual_member = Mock()
        virtual_member.type = "function_definition"
        destructor_member = Mock()
        destructor_member.type = "function_definition"
        
        # Mock helper methods
        def mock_walk_nodes(ctx):
            return [class_node]
        
        def mock_is_class_or_struct(node):
            return node == class_node
        
        def mock_get_class_name(ctx, node):
            return "Final"
        
        def mock_is_final_class(ctx, node):
            return True  # Class is final
        
        # Apply mocks
        rule._walk_nodes = mock_walk_nodes
        rule._is_class_or_struct = mock_is_class_or_struct
        rule._get_class_name = mock_get_class_name
        rule._is_final_class = mock_is_final_class
        
        # Test
        findings = list(rule.visit(ctx))
        
        # Should not detect any issues (final classes are exempt)
        assert len(findings) == 0


def test_rule_registration():
    """Test that the rule is properly registered."""
    from rules.memory_virtual_destructor_missing import RULES
    
    assert len(RULES) == 1
    rule = RULES[0]
    assert rule.meta.id == "memory.virtual_destructor_missing"
    assert isinstance(rule, MemoryVirtualDestructorMissingRule)

