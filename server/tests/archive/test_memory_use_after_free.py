"""
Tests for Memory Use After Free Rule

Tests the detection of use-after-free vulnerabilities in C and C++.
"""

import pytest
from unittest.mock import Mock

from rules.memory_use_after_free import MemoryUseAfterFreeRule


class TestMemoryUseAfterFreeRule:
    """Test suite for the memory use-after-free rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MemoryUseAfterFreeRule()
    
    # --- Meta and Requirements Tests ---
    
    def test_meta_properties(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "memory.use_after_free"
        assert self.rule.meta.category == "memory"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "use after free" in self.rule.meta.description.lower()
        
        expected_langs = {"c", "cpp"}
        assert set(self.rule.meta.langs) == expected_langs
    
    def test_requires_correct_capabilities(self):
        """Test rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
    
    # --- Function Detection Tests ---
    
    def test_free_call_detection(self):
        """Test detection of free() function calls."""
        rule = self.rule
        
        # Mock free() call
        stmt = Mock()
        stmt.kind = "call_expression"
        stmt.function = Mock()
        stmt.function.text = "free"
        
        assert rule._is_free_call(stmt) is True
        
        # Mock non-free call
        stmt.function.text = "malloc"
        assert rule._is_free_call(stmt) is False
        
        # Non-call statement
        stmt.kind = "assignment"
        assert rule._is_free_call(stmt) is False
    
    def test_delete_expression_detection(self):
        """Test detection of C++ delete expressions."""
        rule = self.rule
        
        # Mock delete expression
        stmt = Mock()
        stmt.kind = "delete_expression"
        
        assert rule._is_delete_expression(stmt) is True
        
        # Non-delete statement
        stmt.kind = "assignment"
        assert rule._is_delete_expression(stmt) is False
    
    def test_function_scope_recognition(self):
        """Test function scope recognition."""
        rule = self.rule
        
        # C function
        node = Mock()
        node.kind = "function_definition"
        assert rule._is_function_scope(node, "c") is True
        
        # C++ function
        assert rule._is_function_scope(node, "cpp") is True
        
        # Non-function node
        node.kind = "class_declaration"
        assert rule._is_function_scope(node, "c") is False
    
    # --- Identifier Extraction Tests ---
    
    def test_first_arg_identifier_extraction(self):
        """Test extraction of first argument identifier."""
        rule = self.rule
        
        # Mock call with identifier argument
        stmt = Mock()
        stmt.arguments = [Mock()]
        stmt.arguments[0].kind = "identifier"
        stmt.arguments[0].text = "ptr"
        
        result = rule._get_first_arg_identifier(stmt)
        assert result == "ptr"
        
        # No arguments
        stmt.arguments = []
        result = rule._get_first_arg_identifier(stmt)
        assert result is None
    
    def test_assigned_variable_extraction(self):
        """Test extraction of assigned variables."""
        rule = self.rule
        ctx = Mock()
        
        # Assignment expression
        stmt = Mock()
        stmt.left = Mock()
        stmt.left.kind = "identifier"
        stmt.left.text = "ptr"
        
        result = rule._get_assigned_variable(ctx, stmt)
        assert result == "ptr"
    
    def test_null_assignment_detection(self):
        """Test detection of null assignments."""
        rule = self.rule
        ctx = Mock()
        
        # Mock null assignment
        stmt = Mock()
        rule._get_node_text = lambda c, n: "ptr = NULL"
        
        assert rule._is_null_assignment(ctx, stmt) is True
        
        # Non-null assignment
        rule._get_node_text = lambda c, n: "ptr = malloc(10)"
        assert rule._is_null_assignment(ctx, stmt) is False
        
        # nullptr assignment
        rule._get_node_text = lambda c, n: "ptr = nullptr"
        assert rule._is_null_assignment(ctx, stmt) is True
    
    # --- Dereference Detection Tests ---
    
    def test_dereference_operator_detection(self):
        """Test detection of dereference operators."""
        rule = self.rule
        ctx = Mock()
        
        # Mock dereference operator
        node = Mock()
        node.operator = Mock()
        rule._get_node_text = lambda c, n: "*"
        
        assert rule._is_dereference_operator(ctx, node) is True
        
        # Non-dereference operator
        rule._get_node_text = lambda c, n: "&"
        assert rule._is_dereference_operator(ctx, node) is False
    
    def test_identifier_name_extraction(self):
        """Test extraction of identifier names."""
        rule = self.rule
        
        # Direct identifier
        node = Mock()
        node.kind = "identifier"
        node.text = "ptr"
        
        result = rule._extract_identifier_name(node)
        assert result == "ptr"
        
        # Non-identifier node
        node.kind = "literal"
        result = rule._extract_identifier_name(node)
        assert result is None
    
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
        ctx.language = "python"
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test rule handles missing syntax tree gracefully."""
        ctx = Mock()
        ctx.tree = None
        ctx.language = "c"
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
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
    
    # --- Positive Cases (Should Detect Use-After-Free) ---
    
    def test_c_use_after_free_simulation(self):
        """Test C use-after-free detection simulation."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: malloc, free, dereference
        malloc_stmt = Mock()
        malloc_stmt.kind = "assignment"
        
        free_stmt = Mock()
        free_stmt.kind = "call_expression"
        free_stmt.function = Mock()
        free_stmt.function.text = "free"
        free_stmt.arguments = [Mock()]
        free_stmt.arguments[0].kind = "identifier"
        free_stmt.arguments[0].text = "ptr"
        
        deref_stmt = Mock()
        deref_stmt.kind = "assignment"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [malloc_stmt, free_stmt, deref_stmt]
        
        def mock_is_free_call(stmt):
            return stmt == free_stmt
        
        def mock_get_first_arg_identifier(stmt):
            return "ptr" if stmt == free_stmt else None
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_get_assigned_variable(ctx, stmt):
            return "ptr" if stmt == malloc_stmt else None
        
        def mock_is_null_assignment(ctx, stmt):
            return False
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == deref_stmt:
                return [("ptr", deref_stmt)]
            return []
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_null_assignment = mock_is_null_assignment
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one use-after-free
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.use_after_free"
        assert "ptr" in finding.message
        assert "use-after-free" in finding.message.lower()
        assert finding.severity == "error"
    
    def test_cpp_delete_use_after_free_simulation(self):
        """Test C++ delete use-after-free detection simulation."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "cpp"
        ctx.file_path = "test.cpp"
        
        function_node = Mock()
        
        # Create mock statements: new, delete, dereference
        new_stmt = Mock()
        new_stmt.kind = "assignment"
        
        delete_stmt = Mock()
        delete_stmt.kind = "delete_expression"
        delete_stmt.argument = Mock()
        delete_stmt.argument.kind = "identifier"
        delete_stmt.argument.text = "obj"
        
        deref_stmt = Mock()
        deref_stmt.kind = "expression_statement"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [new_stmt, delete_stmt, deref_stmt]
        
        def mock_is_free_call(stmt):
            return False
        
        def mock_is_delete_expression(stmt):
            return stmt == delete_stmt
        
        def mock_get_deleted_identifier(ctx, stmt):
            return "obj" if stmt == delete_stmt else None
        
        def mock_get_assigned_variable(ctx, stmt):
            return "obj" if stmt == new_stmt else None
        
        def mock_is_null_assignment(ctx, stmt):
            return False
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == deref_stmt:
                return [("obj", deref_stmt)]
            return []
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_deleted_identifier = mock_get_deleted_identifier
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_null_assignment = mock_is_null_assignment
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one use-after-free
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "memory.use_after_free"
        assert "obj" in finding.message
        assert finding.severity == "error"
    
    def test_array_subscript_use_after_free_simulation(self):
        """Test array subscript use-after-free detection simulation."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: free, array access
        free_stmt = Mock()
        free_stmt.kind = "call_expression"
        
        subscript_stmt = Mock()
        subscript_stmt.kind = "assignment"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [free_stmt, subscript_stmt]
        
        def mock_is_free_call(stmt):
            return stmt == free_stmt
        
        def mock_get_first_arg_identifier(stmt):
            return "buffer" if stmt == free_stmt else None
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_get_assigned_variable(ctx, stmt):
            return None
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == subscript_stmt:
                return [("buffer", subscript_stmt)]
            return []
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect one use-after-free
        assert len(findings) == 1
        finding = findings[0]
        assert "buffer" in finding.message
    
    # --- Negative Cases (Should NOT Detect) ---
    
    def test_reinitialize_after_free_simulation(self):
        """Test no detection when pointer is reinitialized after free."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: free, reinit, use
        free_stmt = Mock()
        free_stmt.kind = "call_expression"
        
        reinit_stmt = Mock()
        reinit_stmt.kind = "assignment"
        
        use_stmt = Mock()
        use_stmt.kind = "assignment"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [free_stmt, reinit_stmt, use_stmt]
        
        def mock_is_free_call(stmt):
            return stmt == free_stmt
        
        def mock_get_first_arg_identifier(stmt):
            return "ptr" if stmt == free_stmt else None
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_get_assigned_variable(ctx, stmt):
            return "ptr" if stmt == reinit_stmt else None
        
        def mock_is_null_assignment(ctx, stmt):
            return False  # Non-null assignment
        
        def mock_is_assignment_to_freed_value(ctx, stmt):
            return False
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == use_stmt:
                return [("ptr", use_stmt)]
            return []
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_null_assignment = mock_is_null_assignment
        rule._is_assignment_to_freed_value = mock_is_assignment_to_freed_value
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should NOT detect use-after-free due to reinitialization
        assert len(findings) == 0
    
    def test_null_assignment_after_free_simulation(self):
        """Test no detection when pointer is set to NULL after free."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: free, null assignment
        free_stmt = Mock()
        free_stmt.kind = "call_expression"
        
        null_stmt = Mock()
        null_stmt.kind = "assignment"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [free_stmt, null_stmt]
        
        def mock_is_free_call(stmt):
            return stmt == free_stmt
        
        def mock_get_first_arg_identifier(stmt):
            return "ptr" if stmt == free_stmt else None
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_get_assigned_variable(ctx, stmt):
            return "ptr" if stmt == null_stmt else None
        
        def mock_is_null_assignment(ctx, stmt):
            return stmt == null_stmt  # This is null assignment
        
        def mock_find_pointer_dereferences(ctx, stmt):
            return []
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._is_null_assignment = mock_is_null_assignment
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should NOT detect use-after-free
        assert len(findings) == 0
    
    def test_no_free_no_detection_simulation(self):
        """Test no detection when there's no free/delete."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: only use, no free
        use_stmt = Mock()
        use_stmt.kind = "assignment"
        
        # Mock helper methods
        def mock_get_statements(func_node):
            return [use_stmt]
        
        def mock_is_free_call(stmt):
            return False
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_find_pointer_dereferences(ctx, stmt):
            return [("ptr", use_stmt)]
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._is_delete_expression = mock_is_delete_expression
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should NOT detect use-after-free (no free)
        assert len(findings) == 0
    
    # --- Integration Tests ---
    
    def test_multiple_pointers_tracking(self):
        """Test tracking multiple pointers simultaneously."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "c"
        ctx.file_path = "test.c"
        
        function_node = Mock()
        
        # Create mock statements: free p, free q, use p (should detect), use q (should detect)
        free_p = Mock()
        free_q = Mock()
        use_p = Mock()
        use_q = Mock()
        
        def mock_get_statements(func_node):
            return [free_p, free_q, use_p, use_q]
        
        def mock_is_free_call(stmt):
            return stmt in [free_p, free_q]
        
        def mock_get_first_arg_identifier(stmt):
            if stmt == free_p:
                return "p"
            elif stmt == free_q:
                return "q"
            return None
        
        def mock_is_delete_expression(stmt):
            return False
        
        def mock_get_assigned_variable(ctx, stmt):
            return None
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == use_p:
                return [("p", use_p)]
            elif stmt == use_q:
                return [("q", use_q)]
            return []
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect two use-after-free instances
        assert len(findings) == 2
        messages = [f.message for f in findings]
        assert any("p" in msg for msg in messages)
        assert any("q" in msg for msg in messages)
    
    def test_mixed_free_delete_scenarios(self):
        """Test mixed free() and delete scenarios."""
        rule = self.rule
        ctx = Mock()
        ctx.language = "cpp"
        ctx.file_path = "test.cpp"
        
        function_node = Mock()
        
        # Create mock statements: free(p), delete q, use p, use q
        free_stmt = Mock()
        delete_stmt = Mock()
        use_p = Mock()
        use_q = Mock()
        
        def mock_get_statements(func_node):
            return [free_stmt, delete_stmt, use_p, use_q]
        
        def mock_is_free_call(stmt):
            return stmt == free_stmt
        
        def mock_get_first_arg_identifier(stmt):
            return "p" if stmt == free_stmt else None
        
        def mock_is_delete_expression(stmt):
            return stmt == delete_stmt
        
        def mock_get_deleted_identifier(ctx, stmt):
            return "q" if stmt == delete_stmt else None
        
        def mock_get_assigned_variable(ctx, stmt):
            return None
        
        def mock_find_pointer_dereferences(ctx, stmt):
            if stmt == use_p:
                return [("p", use_p)]
            elif stmt == use_q:
                return [("q", use_q)]
            return []
        
        def mock_get_node_span(ctx, node):
            return (0, 10)
        
        # Apply mocks
        rule._get_statements = mock_get_statements
        rule._is_free_call = mock_is_free_call
        rule._get_first_arg_identifier = mock_get_first_arg_identifier
        rule._is_delete_expression = mock_is_delete_expression
        rule._get_deleted_identifier = mock_get_deleted_identifier
        rule._get_assigned_variable = mock_get_assigned_variable
        rule._find_pointer_dereferences = mock_find_pointer_dereferences
        rule._get_node_span = mock_get_node_span
        
        # Test
        findings = list(rule._check_function_scope(ctx, function_node))
        
        # Should detect both use-after-free instances
        assert len(findings) == 2


def test_rule_registration():
    """Test that the rule is properly registered."""
    from rules.memory_use_after_free import RULES
    
    assert len(RULES) == 1
    rule = RULES[0]
    assert rule.meta.id == "memory.use_after_free"
    assert isinstance(rule, MemoryUseAfterFreeRule)

