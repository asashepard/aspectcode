"""
Tests for Memory Double Free/Close Rule

Tests the detection of double releases across C, C++, Python, Java, and C#.
"""

import pytest
from unittest.mock import Mock

from rules.memory_double_free_or_close import MemoryDoubleFreeOrCloseRule


class TestMemoryDoubleFreeOrCloseRule:
    """Test suite for the memory double free/close rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MemoryDoubleFreeOrCloseRule()
    
    # --- Meta and Requirements Tests ---
    
    def test_meta_properties(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "memory.double_free_or_close"
        assert self.rule.meta.category == "memory"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "double releases" in self.rule.meta.description.lower()
        
        expected_langs = {"c", "cpp", "python", "java", "csharp"}
        assert set(self.rule.meta.langs) == expected_langs
    
    def test_requires_correct_capabilities(self):
        """Test rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
    
    # --- Release Signature Tests ---
    
    def test_c_release_signatures(self):
        """Test C release function signatures."""
        c_sigs = self.rule.RELEASE_SIGS["c"]
        assert "free" in c_sigs
        assert "fclose" in c_sigs
        assert "close" in c_sigs
    
    def test_cpp_release_signatures(self):
        """Test C++ release function signatures."""
        cpp_sigs = self.rule.RELEASE_SIGS["cpp"]
        assert "delete" in cpp_sigs
        assert "delete[]" in cpp_sigs
        assert "free" in cpp_sigs
        assert "fclose" in cpp_sigs
        assert "close" in cpp_sigs
    
    def test_python_release_signatures(self):
        """Test Python release method signatures."""
        py_sigs = self.rule.RELEASE_SIGS["python"]
        assert "close" in py_sigs
    
    def test_java_release_signatures(self):
        """Test Java release method signatures."""
        java_sigs = self.rule.RELEASE_SIGS["java"]
        assert "close" in java_sigs
    
    def test_csharp_release_signatures(self):
        """Test C# release method signatures."""
        cs_sigs = self.rule.RELEASE_SIGS["csharp"]
        assert "Close" in cs_sigs
        assert "Dispose" in cs_sigs
    
    # --- Function Scope Recognition Tests ---
    
    def test_function_scope_recognition_c(self):
        """Test C function scope recognition."""
        # Mock node with C function definition
        node = Mock()
        node.kind = "function_definition"
        
        assert self.rule._is_function_scope(node, "c") is True
        
        # Non-function node
        node.kind = "expression_statement"
        assert self.rule._is_function_scope(node, "c") is False
    
    def test_function_scope_recognition_java(self):
        """Test Java method scope recognition."""
        # Method declaration
        node = Mock()
        node.kind = "method_declaration"
        assert self.rule._is_function_scope(node, "java") is True
        
        # Constructor declaration
        node.kind = "constructor_declaration"
        assert self.rule._is_function_scope(node, "java") is True
        
        # Non-method node
        node.kind = "class_declaration"
        assert self.rule._is_function_scope(node, "java") is False
    
    # --- Assignment and Nulling Detection Tests ---
    
    def test_assignment_nulling_detection(self):
        """Test detection of assignment and nulling operations."""
        rule = self.rule
        ctx = Mock()
        
        # Mock assignment statement with nulling
        stmt = Mock()
        stmt.kind = "assignment"
        
        # Mock _get_node_text to return nulling pattern
        rule._get_node_text = lambda c, n: "p = NULL"
        
        assert rule._is_assignment_or_nulling(ctx, stmt) is True
        
        # Non-nulling assignment
        rule._get_node_text = lambda c, n: "p = malloc(10)"
        assert rule._is_assignment_or_nulling(ctx, stmt) is False
    
    # --- Release Information Extraction Tests ---
    
    def test_method_call_detection(self):
        """Test detection of method calls."""
        stmt = Mock()
        stmt.kind = "call_expression"
        
        # With receiver (method call)
        stmt.function = Mock()
        stmt.function.object = Mock()
        
        assert self.rule._is_method_call(stmt) is True
        
        # Test _has_receiver directly with proper mock setup
        stmt_no_receiver = Mock()
        stmt_no_receiver.function = Mock(spec=[])  # spec=[] means no attributes
        
        assert self.rule._has_receiver(stmt_no_receiver) is False
    
    def test_function_call_detection(self):
        """Test detection of function calls."""
        stmt = Mock()
        stmt.kind = "call_expression"
        
        # Without receiver (function call)
        stmt.function = Mock()
        
        # Mock _has_receiver to return False
        self.rule._has_receiver = lambda s: False
        
        assert self.rule._is_function_call(stmt) is True
    
    # --- Text Extraction Tests ---
    
    def test_node_text_extraction(self):
        """Test extraction of text from nodes."""
        rule = self.rule
        
        # Mock context
        ctx = Mock()
        ctx.text = "free(ptr)"
        ctx.adapter.node_span = lambda n: (0, 9)
        
        # Test with text attribute
        node = Mock()
        node.text = "free"
        
        result = rule._get_node_text(ctx, node)
        assert result == "free"
        
        # Test with span extraction
        node2 = Mock()
        del node2.text
        
        result = rule._get_node_text(ctx, node2)
        assert result == "free(ptr)"
    
    def test_identifier_text_extraction(self):
        """Test extraction of identifier text."""
        rule = self.rule
        ctx = Mock()
        
        # Test with direct text
        node = Mock()
        node.text = "ptr"
        
        result = rule._get_identifier_text(ctx, node)
        assert result == "ptr"
    
    # --- Edge Case Tests ---
    
    def test_empty_file(self):
        """Test rule handles empty files gracefully."""
        ctx = Mock()
        ctx.tree = None
        ctx.language = "c"
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test rule handles unsupported languages gracefully."""
        ctx = Mock()
        ctx.tree = Mock()
        ctx.language = "unsupported"
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test rule handles missing syntax tree gracefully."""
        ctx = Mock()
        ctx.tree = None
        ctx.language = "c"
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # --- Language-Specific Pattern Tests ---
    
    def test_c_patterns(self):
        """Test C-specific double free patterns."""
        rule = self.rule
        
        # Test C acquire hints
        c_hints = rule.ACQUIRE_HINTS["c"]
        assert "malloc" in c_hints
        assert "fopen" in c_hints
        assert "calloc" in c_hints
    
    def test_cpp_patterns(self):
        """Test C++ specific patterns."""
        rule = self.rule
        
        # Test C++ acquire hints
        cpp_hints = rule.ACQUIRE_HINTS["cpp"]
        assert "new" in cpp_hints
        assert "new[]" in cpp_hints
        assert "malloc" in cpp_hints  # C++ also supports C functions
    
    def test_python_patterns(self):
        """Test Python-specific patterns."""
        rule = self.rule
        
        # Test Python acquire hints
        py_hints = rule.ACQUIRE_HINTS["python"]
        assert "open" in py_hints
    
    def test_java_patterns(self):
        """Test Java-specific patterns."""
        rule = self.rule
        
        # Test Java acquire hints
        java_hints = rule.ACQUIRE_HINTS["java"]
        assert "new " in java_hints
    
    def test_csharp_patterns(self):
        """Test C#-specific patterns."""
        rule = self.rule
        
        # Test C# acquire hints
        cs_hints = rule.ACQUIRE_HINTS["csharp"]
        assert "new " in cs_hints
    
    # --- Positive Cases (Should Detect Double Release) ---
    
    def test_c_positive_case_simulation(self):
        """Test C double free detection simulation."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        ctx.text = """
        void test() {
            char* p = malloc(10);
            free(p);
            free(p);  // double free
        }
        """
        
        # Mock function that has statements with double free
        function_node = Mock()
        
        # Create mock statements
        malloc_stmt = Mock()
        malloc_stmt.kind = "assignment"
        rule._get_node_text = lambda c, n: "char* p = malloc(10)" if n == malloc_stmt else ""
        
        first_free = Mock()
        first_free.kind = "call_expression"
        first_free.function = Mock()
        first_free.function.text = "free"
        first_free.arguments = [Mock()]
        first_free.arguments[0].text = "p"
        
        second_free = Mock()
        second_free.kind = "call_expression"
        second_free.function = Mock()
        second_free.function.text = "free"
        second_free.arguments = [Mock()]
        second_free.arguments[0].text = "p"
        
        # Mock helper methods for this test
        def mock_get_statements(func_node):
            return [malloc_stmt, first_free, second_free]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt == malloc_stmt
        
        def mock_get_assigned_variable(ctx, stmt):
            return "p" if stmt == malloc_stmt else None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt == malloc_stmt
        
        def mock_get_target_variable(ctx, stmt):
            return "p" if stmt == malloc_stmt else None
        
        def mock_get_release_info(ctx, stmt):
            if stmt in [first_free, second_free]:
                return ("p", stmt)
            return None
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        rule._get_node_span = mock_get_node_span
        
        # Test the function scope checking
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one double free
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.double_free_or_close"
        assert "p" in finding.message
        assert "more than once" in finding.message
        assert finding.severity == "error"
    
    def test_python_positive_case_simulation(self):
        """Test Python double close detection simulation."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "python"
        ctx.file_path = "test.py"
        
        # Mock function with double close
        function_node = Mock()
        
        # Create mock statements
        open_stmt = Mock()
        open_stmt.kind = "assignment"
        
        first_close = Mock()
        first_close.kind = "call_expression"
        
        second_close = Mock()
        second_close.kind = "call_expression"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [open_stmt, first_close, second_close]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt == open_stmt
        
        def mock_get_assigned_variable(ctx, stmt):
            return "f" if stmt == open_stmt else None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt == open_stmt
        
        def mock_get_target_variable(ctx, stmt):
            return "f" if stmt == open_stmt else None
        
        def mock_get_release_info(ctx, stmt):
            if stmt in [first_close, second_close]:
                return ("f", stmt)
            return None
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one double close
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.double_free_or_close"
        assert "f" in finding.message
        assert finding.severity == "error"
    
    # --- Negative Cases (Should NOT Detect) ---
    
    def test_c_negative_case_nulling_simulation(self):
        """Test C case with nulling between releases (should not detect)."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: malloc, free, null, free
        malloc_stmt = Mock()
        malloc_stmt.kind = "assignment"
        
        first_free = Mock()
        first_free.kind = "call_expression"
        
        null_stmt = Mock()
        null_stmt.kind = "assignment"
        
        second_free = Mock()
        second_free.kind = "call_expression"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [malloc_stmt, first_free, null_stmt, second_free]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt in [malloc_stmt, null_stmt]
        
        def mock_get_assigned_variable(ctx, stmt):
            if stmt in [malloc_stmt, null_stmt]:
                return "p"
            return None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt == malloc_stmt
        
        def mock_get_target_variable(ctx, stmt):
            return "p" if stmt == malloc_stmt else None
        
        def mock_get_release_info(ctx, stmt):
            if stmt in [first_free, second_free]:
                return ("p", stmt)
            return None
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should NOT detect double free due to nulling reset
        assert len(findings) == 0
    
    def test_python_negative_case_reassignment_simulation(self):
        """Test Python case with reassignment between closes (should not detect)."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "python"
        ctx.file_path = "test.py"
        
        function_node = Mock()
        
        # Create mock statements: open, close, reassign, close
        first_open = Mock()
        first_open.kind = "assignment"
        
        first_close = Mock()
        first_close.kind = "call_expression"
        
        second_open = Mock()
        second_open.kind = "assignment"
        
        second_close = Mock()
        second_close.kind = "call_expression"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [first_open, first_close, second_open, second_close]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt in [first_open, second_open]
        
        def mock_get_assigned_variable(ctx, stmt):
            if stmt in [first_open, second_open]:
                return "f"
            return None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt in [first_open, second_open]
        
        def mock_get_target_variable(ctx, stmt):
            if stmt in [first_open, second_open]:
                return "f"
            return None
        
        def mock_get_release_info(ctx, stmt):
            if stmt in [first_close, second_close]:
                return ("f", stmt)
            return None
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should NOT detect double close due to reassignment reset
        assert len(findings) == 0
    
    # --- Integration Tests ---
    
    def test_multiple_variables_tracking(self):
        """Test tracking multiple resource variables simultaneously."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements for two variables: p and q
        p_malloc = Mock()
        q_malloc = Mock()
        p_free1 = Mock()
        q_free1 = Mock()
        p_free2 = Mock()  # This should be detected
        
        def mock_get_statements(func_node):
            return [p_malloc, q_malloc, p_free1, q_free1, p_free2]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt in [p_malloc, q_malloc]
        
        def mock_get_assigned_variable(ctx, stmt):
            if stmt == p_malloc:
                return "p"
            elif stmt == q_malloc:
                return "q"
            return None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt in [p_malloc, q_malloc]
        
        def mock_get_target_variable(ctx, stmt):
            if stmt == p_malloc:
                return "p"
            elif stmt == q_malloc:
                return "q"
            return None
        
        def mock_get_release_info(ctx, stmt):
            if stmt == p_free1 or stmt == p_free2:
                return ("p", stmt)
            elif stmt == q_free1:
                return ("q", stmt)
            return None
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one double free for variable 'p'
        assert len(findings) == 1
        finding = findings[0]
        assert "p" in finding.message
    
    def test_conditional_flows_simulation(self):
        """Test detection with conditional flows."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Simulate: malloc, if-branch-free, else-branch-free, unconditional-free
        malloc_stmt = Mock()
        if_free = Mock()
        else_free = Mock()
        final_free = Mock()  # This should be detected
        
        def mock_get_statements(func_node):
            return [malloc_stmt, if_free, else_free, final_free]
        
        def mock_is_assignment_or_nulling(ctx, stmt):
            return stmt == malloc_stmt
        
        def mock_get_assigned_variable(ctx, stmt):
            return "p" if stmt == malloc_stmt else None
        
        def mock_is_resource_acquisition(ctx, stmt):
            return stmt == malloc_stmt
        
        def mock_get_target_variable(ctx, stmt):
            return "p" if stmt == malloc_stmt else None
        
        def mock_get_release_info(ctx, stmt):
            if stmt in [if_free, else_free, final_free]:
                return ("p", stmt)
            return None
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_assignment_or_nulling = mock_is_assignment_or_nulling
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_resource_acquisition = mock_is_resource_acquisition
        rule._get_target_variable = mock_get_target_variable
        rule._get_release_info = mock_get_release_info
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect multiple double frees (this is a limitation of syntax-only analysis)
        # but at least one should be detected
        assert len(findings) >= 1


def test_rule_registration():
    """Test that the rule is properly registered."""
    from rules.memory_double_free_or_close import RULES
    
    assert len(RULES) == 1
    rule = RULES[0]
    assert rule.meta.id == "memory.double_free_or_close"
    assert isinstance(rule, MemoryDoubleFreeOrCloseRule)

