# server/tests/test_errors_rethrow_without_context.py
"""Tests for the errors.rethrow_without_context rule."""

import pytest
from engine.types import RuleContext, RuleMeta
from rules.errors_rethrow_without_context import ErrorsRethrowWithoutContextRule
from unittest.mock import Mock, MagicMock


class TestErrorsRethrowWithoutContextRule:
    """Test cases for ErrorsRethrowWithoutContextRule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ErrorsRethrowWithoutContextRule()
        assert self.rule.meta.id == "errors.rethrow_without_context"
        assert self.rule.meta.category == "errors"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P2"
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

    def _create_mock_catch_node(self, language: str, handler_statements: list, 
                               catch_type: str = None) -> Mock:
        """Create a mock catch/except node with handler body containing given statements."""
        if catch_type is None:
            catch_types = {
                "python": "except_clause",
                "java": "catch_clause", 
                "csharp": "catch_clause"
            }
            catch_type = catch_types.get(language, "catch_clause")
        
        catch_node = self._create_mock_node(catch_type)
        
        # Create mock body with statements
        body_node = Mock()
        body_node.type = "suite"  # Set proper type for body detection
        body_node.children = []
        
        # Add statement nodes
        for stmt_text, stmt_type in handler_statements:
            stmt_node = Mock()
            stmt_node.type = stmt_type
            stmt_node.text = stmt_text
            stmt_node.start_byte = 0
            stmt_node.end_byte = len(stmt_text)
            body_node.children.append(stmt_node)
        
        # Attach body using common attribute names
        catch_node.body = body_node
        catch_node.children = [Mock(), body_node]  # Mock exception var + body
        
        return catch_node

    # ============================================================================
    # Python Positive Cases (Should Flag)
    # ============================================================================

    def test_python_bare_raise(self):
        """Test detection of Python bare raise statement."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise", "raise_statement")])
        
        # Mock the tree traversal to return our catch node
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Rethrow without added context" in findings[0].message
        assert findings[0].severity == "info"
        assert findings[0].rule == "errors.rethrow_without_context"

    def test_python_raise_variable(self):
        """Test detection of Python raise with variable."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise e", "raise_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Rethrow without added context" in findings[0].message

    def test_python_raise_exception_variable(self):
        """Test detection of Python raise with exception variable."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise exception", "raise_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # Python Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_python_raise_with_context(self):
        """Test that Python raise with context is not flagged."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [
            ('raise RuntimeError("failed: %s" % e)', "raise_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_python_logging_before_raise(self):
        """Test that Python handler with logging before raise is not flagged."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [
            ('logger.error("Error occurred: %s", e)', "expression_statement"),
            ("raise", "raise_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_python_raise_from_chaining(self):
        """Test that Python exception chaining is not flagged."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [
            ('raise ValueError("Custom error") from e', "raise_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Java Positive Cases (Should Flag)
    # ============================================================================

    def test_java_throw_variable(self):
        """Test detection of Java throw with variable."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [("throw e;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Rethrow without added context" in findings[0].message

    def test_java_throw_exception_variable(self):
        """Test detection of Java throw with exception variable."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [("throw exception;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_java_throw_field_access(self):
        """Test detection of Java throw with field access."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [("throw this.e;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # Java Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_java_throw_with_context(self):
        """Test that Java throw with context is not flagged."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [
            ('throw new RuntimeException("failed: " + e.getMessage(), e);', "throw_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_java_logging_before_throw(self):
        """Test that Java handler with logging before throw is not flagged."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [
            ('logger.error("Error occurred: {}", e.getMessage(), e);', "expression_statement"),
            ("throw e;", "throw_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_java_multiple_statements(self):
        """Test that Java handler with multiple statements is not flagged."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", [
            ('System.err.println("Error: " + e);', "expression_statement"),
            ("throw e;", "throw_statement"),
            ('cleanup();', "expression_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # C# Positive Cases (Should Flag)
    # ============================================================================

    def test_csharp_bare_throw(self):
        """Test detection of C# bare throw statement."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [("throw;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Rethrow without added context" in findings[0].message

    def test_csharp_throw_variable(self):
        """Test detection of C# throw with variable."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [("throw e;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_csharp_throw_exception_variable(self):
        """Test detection of C# throw with exception variable."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [("throw ex;", "throw_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    # ============================================================================
    # C# Negative Cases (Should NOT Flag)
    # ============================================================================

    def test_csharp_throw_with_context(self):
        """Test that C# throw with context is not flagged."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [
            ('throw new InvalidOperationException("x", e);', "throw_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_csharp_logging_before_throw(self):
        """Test that C# handler with logging before throw is not flagged."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [
            ('_logger.LogError(ex, "Operation failed: {Message}", ex.Message);', "expression_statement"),
            ("throw;", "throw_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_csharp_wrapped_exception(self):
        """Test that C# wrapped exception is not flagged."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", [
            ('throw new ApplicationException("Failed to process", ex);', "throw_statement")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Edge Cases and Error Conditions
    # ============================================================================

    def test_unsupported_language(self):
        """Test that unsupported languages are skipped."""
        ctx = self._create_mock_context("ruby")  # Not supported for this rule
        catch_node = self._create_mock_catch_node("ruby", [("raise", "raise_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_empty_handler_body(self):
        """Test handler with empty body."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_handler_with_only_comments(self):
        """Test handler with only comments (should not flag)."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [
            ("# TODO: Handle this properly", "comment")
        ])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_non_catch_nodes(self):
        """Test that non-catch nodes are ignored."""
        ctx = self._create_mock_context("python")
        
        def mock_walk(tree):
            # Return a non-catch node
            node = self._create_mock_node("function_definition")
            yield node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_node_without_type_attribute(self):
        """Test handling of nodes without type attribute."""
        ctx = self._create_mock_context("python")
        
        def mock_walk(tree):
            # Return a node without type attribute
            node = Mock()
            # Don't set node.type
            yield node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_handler_body_extraction_failure(self):
        """Test handling when body extraction fails."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_node("except_clause")
        # Don't set body or children
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_mixed_handlers_in_file(self):
        """Test file with mixed catch handlers - some redundant, some meaningful."""
        ctx = self._create_mock_context("python")
        
        # Redundant handler
        bad_catch = self._create_mock_catch_node("python", [("raise", "raise_statement")])
        
        # Good handler with logging
        good_catch = self._create_mock_catch_node("python", [
            ('logging.error("Error: %s", e)', "expression_statement"),
            ("raise", "raise_statement")
        ])
        
        def mock_walk(tree):
            yield bad_catch
            yield good_catch
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1  # Only the redundant handler should be flagged

    def test_statement_text_extraction_failure(self):
        """Test handling when statement text extraction fails."""
        ctx = self._create_mock_context("python")
        
        # Create catch node with statement that has no text
        catch_node = Mock()
        catch_node.type = "except_clause"
        
        body_node = Mock()
        stmt_node = Mock()
        stmt_node.type = "raise_statement"
        # Don't set text attribute
        body_node.children = [stmt_node]
        catch_node.body = body_node
        catch_node.children = [Mock(), body_node]
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0  # Should not flag due to text extraction failure

    def test_finding_metadata(self):
        """Test that finding metadata is correctly populated."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise", "raise_statement")])
        catch_node.start_byte = 100
        catch_node.end_byte = 150
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        finding = findings[0]
        
        assert finding.rule == "errors.rethrow_without_context"
        assert finding.severity == "info"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert "language" in finding.meta
        assert "rethrow_type" in finding.meta
        assert finding.meta["language"] == "python"
        assert finding.meta["rethrow_type"] == "bare_raise"

    def test_header_span_extraction(self):
        """Test that header spans are correctly extracted."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise", "raise_statement")])
        catch_node.start_byte = 50
        catch_node.end_byte = 100  # Set end_byte for fallback case
        
        # Mock body with start_byte for header span calculation
        catch_node.body.start_byte = 70
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert findings[0].start_byte == 50
        assert findings[0].end_byte == 70  # Should end at body start

    def test_suggestion_generation_all_languages(self):
        """Test that suggestions are generated for all supported languages."""
        languages = ["python", "java", "csharp"]
        
        for language in languages:
            ctx = self._create_mock_context(language)
            
            if language == "python":
                statements = [("raise", "raise_statement")]
            elif language == "java":
                statements = [("throw e;", "throw_statement")]
            else:  # csharp
                statements = [("throw;", "throw_statement")]
            
            catch_node = self._create_mock_catch_node(language, statements)
            
            def mock_walk(tree):
                yield catch_node
            
            self.rule._walk_nodes = mock_walk
            
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 1
            assert "suggestion" in findings[0].meta
            suggestion = findings[0].meta["suggestion"]
            assert len(suggestion) > 100  # Should be substantial
            
            # Language-specific keywords should appear in suggestions
            if language == "python":
                assert "logger.error" in suggestion or "logging" in suggestion
                assert "raise" in suggestion
            elif language == "java":
                assert "logger.error" in suggestion or "Logger" in suggestion
                assert "throw" in suggestion
            elif language == "csharp":
                assert "_logger.Log" in suggestion or "Logger" in suggestion
                assert "throw" in suggestion

    def test_rethrow_type_identification(self):
        """Test correct identification of different rethrow types."""
        # Python bare raise
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", [("raise", "raise_statement")])
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert findings[0].meta["rethrow_type"] == "bare_raise"
        
        # Python raise variable
        catch_node2 = self._create_mock_catch_node("python", [("raise e", "raise_statement")])
        
        def mock_walk2(tree):
            yield catch_node2
        
        self.rule._walk_nodes = mock_walk2
        
        findings2 = list(self.rule.visit(ctx))
        assert len(findings2) == 1
        assert findings2[0].meta["rethrow_type"] == "raise_variable"
        
        # C# bare throw
        ctx_cs = self._create_mock_context("csharp")
        catch_node3 = self._create_mock_catch_node("csharp", [("throw;", "throw_statement")])
        
        def mock_walk3(tree):
            yield catch_node3
        
        self.rule._walk_nodes = mock_walk3
        
        findings3 = list(self.rule.visit(ctx_cs))
        assert len(findings3) == 1
        assert findings3[0].meta["rethrow_type"] == "bare_throw"

