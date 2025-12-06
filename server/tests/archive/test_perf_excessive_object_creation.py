"""Tests for perf.excessive_object_creation rule."""

import pytest
from unittest.mock import Mock

from rules.perf_excessive_object_creation import PerfExcessiveObjectCreationRule


class MockNode:
    """Mock tree-sitter node for testing."""
    
    def __init__(self, kind, text="", start_pos=(0, 0), end_pos=(0, 10), children=None, parent=None):
        self.kind = kind
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.children = children or []
        self.parent = parent
        
        # Set parent references for children
        for child in self.children:
            child.parent = self

    def __repr__(self):
        return f"MockNode({self.kind})"


class MockSyntaxTree:
    """Mock syntax tree for testing."""
    
    def __init__(self, nodes):
        self.nodes = nodes

    def walk(self):
        """Return all nodes for walking."""
        return self.nodes
    
    def node_span(self, node):
        """Return node span."""
        return node.start_pos, node.end_pos


def create_loop_with_allocation(loop_type="for_statement", alloc_type="new_expression", alloc_text="new Foo()"):
    """Create mock nodes with allocation inside a loop."""
    alloc_node = MockNode(alloc_type, alloc_text, start_pos=(1, 20), end_pos=(1, 30))
    loop_body = MockNode("block", children=[alloc_node])
    loop_node = MockNode(loop_type, children=[loop_body])
    
    # Set up parent relationships
    alloc_node.parent = loop_body
    loop_body.parent = loop_node
    
    return [loop_node, loop_body, alloc_node], alloc_node


def create_hoisted_allocation(alloc_type="new_expression", alloc_text="new Foo()"):
    """Create mock nodes with allocation outside loop."""
    alloc_node = MockNode(alloc_type, alloc_text, start_pos=(1, 10), end_pos=(1, 20))
    loop_body = MockNode("block", children=[])
    loop_node = MockNode("for_statement", children=[loop_body])
    
    # Set up parent relationships
    loop_body.parent = loop_node
    
    return [alloc_node, loop_node, loop_body], alloc_node


class TestPerfExcessiveObjectCreationRule:
    """Test cases for excessive object creation rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = PerfExcessiveObjectCreationRule()
        
        self.mock_ctx = Mock()
        self.mock_ctx.language = "python"

    def test_positive_case_python_list_in_loop(self):
        """Test detection of list creation in Python loop."""
        # Create call_expression for list()
        callee = MockNode("identifier", "list", start_pos=(1, 20), end_pos=(1, 24))
        call_node = MockNode("call_expression", "list()", start_pos=(1, 20), end_pos=(1, 26), children=[callee])
        nodes, _ = create_loop_with_allocation("for_statement", "call_expression", "list()")
        nodes[2] = call_node  # Replace the allocation node
        call_node.parent = nodes[1]  # Set parent to loop body
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "python"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "scratch object" in findings[0].message

    def test_positive_case_javascript_object_literal(self):
        """Test detection of object literal in JavaScript loop."""
        nodes, alloc_node = create_loop_with_allocation("for_statement", "object_literal", "{}")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "javascript"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "preallocated object" in findings[0].message

    def test_positive_case_typescript_array_literal(self):
        """Test detection of array literal in TypeScript loop."""
        nodes, alloc_node = create_loop_with_allocation("for_of_statement", "array_literal", "[]")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "typescript"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "preallocated" in findings[0].message

    def test_positive_case_java_new_expression(self):
        """Test detection of new expression in Java loop."""
        nodes, alloc_node = create_loop_with_allocation("enhanced_for_statement", "new_expression", "new StringBuilder()")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "java"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "StringBuilder" in findings[0].message

    def test_positive_case_csharp_constructor_call(self):
        """Test detection of constructor call in C# loop."""
        nodes, alloc_node = create_loop_with_allocation("foreach_statement", "object_creation_expression", "new StringBuilder()")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "csharp"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "StringBuilder" in findings[0].message

    def test_positive_case_go_make_call(self):
        """Test detection of make() call in Go loop."""
        # Create call_expression for make()
        callee = MockNode("identifier", "make", start_pos=(1, 20), end_pos=(1, 24))
        call_node = MockNode("call_expression", "make([]int, 0)", start_pos=(1, 20), end_pos=(1, 34), children=[callee])
        nodes, _ = create_loop_with_allocation("range_for_statement", "call_expression", "make([]int, 0)")
        nodes[2] = call_node  # Replace the allocation node
        call_node.parent = nodes[1]  # Set parent to loop body
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "go"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "bytes.Buffer" in findings[0].message

    def test_positive_case_rust_string_new(self):
        """Test detection of String::new in Rust loop."""
        # Create call_expression for String::new()
        callee = MockNode("scoped_identifier", "String::new", start_pos=(1, 20), end_pos=(1, 31))
        call_node = MockNode("call_expression", "String::new()", start_pos=(1, 20), end_pos=(1, 33), children=[callee])
        nodes, _ = create_loop_with_allocation("for_statement", "call_expression", "String::new()")
        nodes[2] = call_node  # Replace the allocation node
        call_node.parent = nodes[1]  # Set parent to loop body
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "rust"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "clear()/reserve()" in findings[0].message

    def test_positive_case_swift_array_literal(self):
        """Test detection of array literal in Swift loop."""
        nodes, alloc_node = create_loop_with_allocation("for_statement", "array_literal", "[Int]()")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "swift"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "preallocate capacity" in findings[0].message

    def test_positive_case_ruby_hash_new(self):
        """Test detection of Hash.new in Ruby loop."""
        # Create call_expression for Hash.new
        callee = MockNode("member_expression", "Hash.new", start_pos=(1, 20), end_pos=(1, 28))
        call_node = MockNode("call_expression", "Hash.new", start_pos=(1, 20), end_pos=(1, 28), children=[callee])
        nodes, _ = create_loop_with_allocation("for_statement", "call_expression", "Hash.new")
        nodes[2] = call_node  # Replace the allocation node
        call_node.parent = nodes[1]  # Set parent to loop body
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "ruby"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "StringIO" in findings[0].message

    def test_positive_case_cpp_new_expression(self):
        """Test detection of new expression in C++ loop."""
        nodes, alloc_node = create_loop_with_allocation("for_statement", "new_expression", "new std::string()")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "cpp"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message
        assert "reserve() capacity" in findings[0].message

    def test_negative_case_hoisted_allocation(self):
        """Test no detection when allocation is outside loop."""
        nodes, alloc_node = create_hoisted_allocation("new_expression", "new Foo()")
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "java"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_negative_case_reuse_pattern_python(self):
        """Test no detection for reuse pattern in Python."""
        # Create a scenario where allocation is outside loop, only method calls inside
        clear_call = MockNode("call_expression", "buf.clear()", start_pos=(1, 25), end_pos=(1, 36))
        append_call = MockNode("call_expression", "buf.append(x)", start_pos=(1, 40), end_pos=(1, 53))
        loop_body = MockNode("block", children=[clear_call, append_call])
        loop_node = MockNode("for_statement", children=[loop_body])
        
        # Allocation outside loop
        alloc_node = MockNode("assignment", "buf = []", start_pos=(1, 10), end_pos=(1, 18))
        
        # Set up parent relationships
        clear_call.parent = loop_body
        append_call.parent = loop_body
        loop_body.parent = loop_node
        
        nodes = [alloc_node, loop_node, loop_body, clear_call, append_call]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "python"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_multiple_allocations_in_loop(self):
        """Test detection of multiple allocations in single loop."""
        # Create multiple allocations in one loop
        alloc1 = MockNode("object_literal", "{}", start_pos=(1, 20), end_pos=(1, 22))
        alloc2 = MockNode("array_literal", "[]", start_pos=(1, 25), end_pos=(1, 27))
        alloc3 = MockNode("new_expression", "new Date()", start_pos=(1, 30), end_pos=(1, 40))
        
        loop_body = MockNode("block", children=[alloc1, alloc2, alloc3])
        loop_node = MockNode("for_of_statement", children=[loop_body])
        
        # Set up parent relationships
        alloc1.parent = loop_body
        alloc2.parent = loop_body
        alloc3.parent = loop_body
        loop_body.parent = loop_node
        
        nodes = [loop_node, loop_body, alloc1, alloc2, alloc3]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "javascript"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 3
        for finding in findings:
            assert "Object creation inside loop" in finding.message

    def test_nested_loops(self):
        """Test detection in nested loops."""
        # Create allocation in inner loop
        alloc_node = MockNode("new_expression", "new ArrayList()", start_pos=(1, 30), end_pos=(1, 45))
        inner_body = MockNode("block", children=[alloc_node])
        inner_loop = MockNode("for_statement", children=[inner_body])
        outer_body = MockNode("block", children=[inner_loop])
        outer_loop = MockNode("for_statement", children=[outer_body])
        
        # Set up parent relationships
        alloc_node.parent = inner_body
        inner_body.parent = inner_loop
        inner_loop.parent = outer_body
        outer_body.parent = outer_loop
        
        nodes = [outer_loop, outer_body, inner_loop, inner_body, alloc_node]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "java"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Object creation inside loop" in findings[0].message

    def test_no_syntax_tree(self):
        """Test graceful handling when no syntax tree is available."""
        self.mock_ctx.syntax = None
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_rule_metadata(self):
        """Test rule metadata is correctly set."""
        assert self.rule.meta.id == "perf.excessive_object_creation"
        assert self.rule.meta.category == "perf"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert len(self.rule.meta.langs) == 11
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs

