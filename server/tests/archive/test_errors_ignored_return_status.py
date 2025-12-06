# server/tests/test_errors_ignored_return_status.py
"""Tests for the errors.ignored_return_status rule."""

import pytest
from engine.types import RuleContext, RuleMeta
from rules.errors_ignored_return_status import ErrorsIgnoredReturnStatusRule
from unittest.mock import Mock, MagicMock


class TestErrorsIgnoredReturnStatusRule:
    """Test cases for ErrorsIgnoredReturnStatusRule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ErrorsIgnoredReturnStatusRule()
        assert self.rule.meta.id == "errors.ignored_return_status"
        assert self.rule.meta.category == "errors"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"

    def _create_mock_context(self, language: str, file_content: str = "") -> RuleContext:
        """Create a mock RuleContext for testing."""
        ctx = Mock(spec=RuleContext)
        ctx.adapter = Mock()
        ctx.adapter.language_id = language
        ctx.file_path = f"test.{language}"
        ctx.text = file_content
        
        # Create a mock tree with root_node
        ctx.tree = Mock()
        ctx.tree.root_node = Mock()
        
        return ctx

    def _create_mock_node(self, node_type: str, text: str = "", 
                         start_byte: int = 0, end_byte: int = None) -> Mock:
        """Create a mock AST node."""
        node = Mock()
        node.type = node_type
        node.text = text
        node.start_byte = start_byte
        node.end_byte = end_byte if end_byte is not None else len(text)
        node.children = []
        return node

    def _create_mock_expr_stmt_with_call(self, language: str, call_text: str, 
                                        stmt_type: str = None, call_type: str = None) -> Mock:
        """Create a mock expression statement containing a function call."""
        if stmt_type is None:
            stmt_types = {
                "c": "expression_statement",
                "cpp": "expression_statement",
                "go": "expression_statement", 
                "rust": "expression_statement",
                "csharp": "expression_statement",
                "java": "expression_statement"
            }
            stmt_type = stmt_types.get(language, "expression_statement")
        
        if call_type is None:
            call_types = {
                "c": "call_expression",
                "cpp": "call_expression",
                "go": "call_expression",
                "rust": "call_expression",
                "csharp": "invocation_expression", 
                "java": "method_invocation"
            }
            call_type = call_types.get(language, "call_expression")
        
        # Create expression statement
        stmt_node = self._create_mock_node(stmt_type)
        
        # Create call expression
        call_node = Mock()
        call_node.type = call_type
        call_node.text = call_text
        call_node.start_byte = 0
        call_node.end_byte = len(call_text)
        
        # Create callee node for span targeting
        callee_node = Mock()
        callee_node.type = "identifier"
        func_name = call_text.split('(')[0] if '(' in call_text else call_text
        callee_node.text = func_name
        callee_node.start_byte = 0
        callee_node.end_byte = len(func_name)
        
        call_node.children = [callee_node]
        stmt_node.children = [call_node]
        
        return stmt_node

    # ============================================================================
    # C Positive Cases (Should Flag)
    # ============================================================================

    def test_c_ignored_function_call(self):
        """Test detection of ignored C function call."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "strerror(0)")
        
        # Mock the tree traversal to return our statement node
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Ignored return value" in findings[0].message
        assert findings[0].severity == "warn"
        assert findings[0].rule == "errors.ignored_return_status"

    def test_c_ignored_malloc_call(self):
        """Test detection of ignored malloc call."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "malloc(100)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # C Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_c_void_cast_not_flagged(self):
        """Test that C void cast is not flagged."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "(void)close(fd)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_c_printf_not_flagged(self):
        """Test that C printf (side effect function) is not flagged."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", 'printf("Hello world")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_c_assignment_not_flagged(self):
        """Test that C assignment is not flagged (not a bare call)."""
        ctx = self._create_mock_context("c")
        
        # Create assignment statement instead of bare call
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        # Assignment expression (not a direct call)
        assign_node = Mock()
        assign_node.type = "assignment_expression"
        assign_node.text = "result = function_call()"
        
        stmt_node.children = [assign_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # C++ Positive Cases (Should Flag)
    # ============================================================================

    def test_cpp_ignored_method_call(self):
        """Test detection of ignored C++ method call."""
        ctx = self._create_mock_context("cpp")
        stmt_node = self._create_mock_expr_stmt_with_call("cpp", "s.size()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_cpp_ignored_function_call(self):
        """Test detection of ignored C++ function call."""
        ctx = self._create_mock_context("cpp")
        stmt_node = self._create_mock_expr_stmt_with_call("cpp", "std::stoi(input)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # C++ Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_cpp_cout_not_flagged(self):
        """Test that C++ cout (side effect) is not flagged."""
        ctx = self._create_mock_context("cpp")
        
        # Create expression statement with binary expression (not call expression)
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        # Binary expression for cout << "Hello"
        binary_node = Mock()
        binary_node.type = "binary_expression"  # Not a call_expression
        binary_node.text = 'cout << "Hello"'
        
        stmt_node.children = [binary_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_cpp_assignment_not_flagged(self):
        """Test that C++ assignment is not flagged."""
        ctx = self._create_mock_context("cpp")
        
        # Create assignment statement
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        assign_node = Mock()
        assign_node.type = "assignment_expression"
        assign_node.text = "auto n = s.size()"
        
        stmt_node.children = [assign_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Go Positive Cases (Should Flag)
    # ============================================================================

    def test_go_ignored_function_call(self):
        """Test detection of ignored Go function call."""
        ctx = self._create_mock_context("go")
        stmt_node = self._create_mock_expr_stmt_with_call("go", "f()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_go_ignored_method_call(self):
        """Test detection of ignored Go method call."""
        ctx = self._create_mock_context("go")
        stmt_node = self._create_mock_expr_stmt_with_call("go", "file.Read(buffer)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # Go Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_go_println_not_flagged(self):
        """Test that Go println (side effect) is not flagged."""
        ctx = self._create_mock_context("go")
        stmt_node = self._create_mock_expr_stmt_with_call("go", 'println("Hello")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_go_assignment_not_flagged(self):
        """Test that Go assignment is not flagged."""
        ctx = self._create_mock_context("go")
        
        # Create assignment statement
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        assign_node = Mock()
        assign_node.type = "assignment_expression"
        assign_node.text = "result, err := f()"
        
        stmt_node.children = [assign_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Rust Positive Cases (Should Flag)
    # ============================================================================

    def test_rust_ignored_function_call(self):
        """Test detection of ignored Rust function call."""
        ctx = self._create_mock_context("rust")
        stmt_node = self._create_mock_expr_stmt_with_call("rust", "f()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_rust_ignored_method_call(self):
        """Test detection of ignored Rust method call."""
        ctx = self._create_mock_context("rust")
        stmt_node = self._create_mock_expr_stmt_with_call("rust", "vec.len()", call_type="method_call_expression")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # Rust Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_rust_expect_not_flagged(self):
        """Test that Rust expect call is not flagged."""
        ctx = self._create_mock_context("rust")
        stmt_node = self._create_mock_expr_stmt_with_call("rust", 'f().expect("should work")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_rust_println_not_flagged(self):
        """Test that Rust println! macro is not flagged."""
        ctx = self._create_mock_context("rust")
        stmt_node = self._create_mock_expr_stmt_with_call("rust", 'println!("Hello")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_rust_let_underscore_not_flagged(self):
        """Test that Rust let _ assignment is not flagged."""
        ctx = self._create_mock_context("rust")
        
        # Create let statement instead of bare call
        stmt_node = Mock()
        stmt_node.type = "let_declaration"
        stmt_node.text = "let _ = f();"
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # C# Positive Cases (Should Flag)
    # ============================================================================

    def test_csharp_ignored_method_call(self):
        """Test detection of ignored C# method call."""
        ctx = self._create_mock_context("csharp")
        stmt_node = self._create_mock_expr_stmt_with_call("csharp", "int.Parse(input)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_csharp_ignored_static_method(self):
        """Test detection of ignored C# static method call."""
        ctx = self._create_mock_context("csharp")
        stmt_node = self._create_mock_expr_stmt_with_call("csharp", "DateTime.Now.ToString()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # C# Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_csharp_console_writeline_not_flagged(self):
        """Test that C# Console.WriteLine is not flagged."""
        ctx = self._create_mock_context("csharp")
        stmt_node = self._create_mock_expr_stmt_with_call("csharp", 'Console.WriteLine("Hello")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_csharp_assignment_not_flagged(self):
        """Test that C# assignment is not flagged."""
        ctx = self._create_mock_context("csharp")
        
        # Create assignment statement
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        assign_node = Mock()
        assign_node.type = "assignment_expression"
        assign_node.text = "var result = int.Parse(input)"
        
        stmt_node.children = [assign_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Java Positive Cases (Should Flag)
    # ============================================================================

    def test_java_ignored_method_call(self):
        """Test detection of ignored Java method call."""
        ctx = self._create_mock_context("java")
        stmt_node = self._create_mock_expr_stmt_with_call("java", "Integer.parseInt(input)")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_java_ignored_instance_method(self):
        """Test detection of ignored Java instance method call."""
        ctx = self._create_mock_context("java")
        stmt_node = self._create_mock_expr_stmt_with_call("java", "list.size()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # Java Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_java_system_out_println_not_flagged(self):
        """Test that Java System.out.println is not flagged."""
        ctx = self._create_mock_context("java")
        stmt_node = self._create_mock_expr_stmt_with_call("java", 'System.out.println("Hello")')
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_java_assignment_not_flagged(self):
        """Test that Java assignment is not flagged."""
        ctx = self._create_mock_context("java")
        
        # Create assignment statement
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        assign_node = Mock()
        assign_node.type = "assignment_expression"
        assign_node.text = "int result = Integer.parseInt(input)"
        
        stmt_node.children = [assign_node]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Edge Cases and Error Conditions
    # ============================================================================

    def test_unsupported_language(self):
        """Test that unsupported languages are skipped."""
        ctx = self._create_mock_context("python")  # Not supported for this rule
        stmt_node = self._create_mock_expr_stmt_with_call("python", "function()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_non_expression_statement(self):
        """Test that non-expression statements are ignored."""
        ctx = self._create_mock_context("c")
        
        # Create a different type of statement
        stmt_node = Mock()
        stmt_node.type = "if_statement"
        stmt_node.children = []
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_expression_statement_with_multiple_children(self):
        """Test expression statement with multiple children (should not flag)."""
        ctx = self._create_mock_context("c")
        
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        # Multiple meaningful children
        child1 = Mock()
        child1.type = "call_expression"
        child2 = Mock()
        child2.type = "identifier"
        
        stmt_node.children = [child1, child2]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_expression_statement_with_non_call_child(self):
        """Test expression statement with non-call child."""
        ctx = self._create_mock_context("c")
        
        stmt_node = Mock()
        stmt_node.type = "expression_statement"
        
        # Non-call child
        child = Mock()
        child.type = "identifier"
        
        stmt_node.children = [child]
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_node_without_type_attribute(self):
        """Test handling of nodes without type attribute."""
        ctx = self._create_mock_context("c")
        
        def mock_walk(tree):
            # Return a node without type attribute
            node = Mock()
            # Don't set node.type
            yield node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_text_extraction_failure(self):
        """Test handling when text extraction fails."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "function()")
        
        # Remove text attributes to simulate extraction failure
        call_node = stmt_node.children[0]
        del call_node.text
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1  # Should still flag with default behavior

    def test_finding_metadata(self):
        """Test that finding metadata is correctly populated."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "malloc(100)")
        stmt_node.start_byte = 50
        stmt_node.children[0].start_byte = 50
        stmt_node.children[0].end_byte = 60
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        finding = findings[0]
        
        assert finding.rule == "errors.ignored_return_status"
        assert finding.severity == "warning"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert "language" in finding.meta
        assert "call_type" in finding.meta
        assert finding.meta["language"] == "c"

    def test_call_head_span_extraction(self):
        """Test that call head spans are correctly extracted."""
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "function()")
        
        # Set up byte positions
        call_node = stmt_node.children[0]
        call_node.start_byte = 100
        call_node.end_byte = 110
        
        callee_node = call_node.children[0]
        callee_node.start_byte = 100
        callee_node.end_byte = 108  # "function"
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert findings[0].start_byte == 100
        assert findings[0].end_byte == 108  # Should target callee

    def test_suggestion_generation_all_languages(self):
        """Test that suggestions are generated for all supported languages."""
        languages = ["c", "cpp", "go", "rust", "csharp", "java"]
        
        for language in languages:
            ctx = self._create_mock_context(language)
            stmt_node = self._create_mock_expr_stmt_with_call(language, "function()")
            
            def mock_walk(tree):
                yield stmt_node
            
            self.rule._walk_nodes = mock_walk
            
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 1
            assert "suggestion" in findings[0].meta
            suggestion = findings[0].meta["suggestion"]
            assert len(suggestion) > 100  # Should be substantial
            
            # Language-specific patterns should appear in suggestions
            if language in ["c", "cpp"]:
                assert "result =" in suggestion or "(void)" in suggestion
            elif language == "go":
                assert "err :=" in suggestion or "_ =" in suggestion
            elif language == "rust":
                assert "let _" in suggestion or ".expect(" in suggestion
            elif language in ["csharp", "java"]:
                assert "var " in suggestion or "try" in suggestion

    def test_call_type_identification(self):
        """Test correct identification of different call types."""
        # Function call
        ctx = self._create_mock_context("c")
        stmt_node = self._create_mock_expr_stmt_with_call("c", "function()")
        
        def mock_walk(tree):
            yield stmt_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert findings[0].meta["call_type"] == "function_call"
        
        # Method call
        stmt_node2 = self._create_mock_expr_stmt_with_call("c", "obj.method()")
        
        def mock_walk2(tree):
            yield stmt_node2
        
        self.rule._walk_nodes = mock_walk2
        
        findings2 = list(self.rule.visit(ctx))
        assert len(findings2) == 1
        assert findings2[0].meta["call_type"] == "method_call"

    def test_multiple_calls_in_file(self):
        """Test file with multiple ignored calls."""
        ctx = self._create_mock_context("c")
        
        stmt1 = self._create_mock_expr_stmt_with_call("c", "function1()")
        stmt2 = self._create_mock_expr_stmt_with_call("c", "function2()")
        
        def mock_walk(tree):
            yield stmt1
            yield stmt2
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 2  # Both should be flagged

