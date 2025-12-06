# server/tests/test_errors_swallowed_exception.py
"""Tests for the errors.swallowed_exception rule."""

import pytest
from engine.types import RuleContext, RuleMeta
from rules.errors_swallowed_exception import ErrorsSwallowedExceptionRule
from unittest.mock import Mock, MagicMock


class TestErrorsSwallowedExceptionRule:
    """Test cases for ErrorsSwallowedExceptionRule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ErrorsSwallowedExceptionRule()
        assert self.rule.meta.id == "errors.swallowed_exception"
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

    def _create_mock_catch_node(self, language: str, handler_text: str, 
                               catch_type: str = None) -> Mock:
        """Create a mock catch/except node with handler body."""
        if catch_type is None:
            catch_types = {
                "python": "except_clause",
                "java": "catch_clause", 
                "csharp": "catch_clause",
                "ruby": "rescue_clause",
                "javascript": "catch_clause",
                "typescript": "catch_clause"
            }
            catch_type = catch_types.get(language, "catch_clause")
        
        catch_node = self._create_mock_node(catch_type)
        
        # Create mock body/handler
        body_node = Mock()
        body_node.text = handler_text
        body_node.start_byte = 0
        body_node.end_byte = len(handler_text)
        
        # Attach body using common attribute names
        catch_node.body = body_node
        catch_node.children = [Mock(), body_node]  # Mock exception var + body
        
        return catch_node

    # ============================================================================
    # Python Tests
    # ============================================================================

    def test_python_empty_except_handler(self):
        """Test detection of empty Python except handler."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", "")
        
        # Mock the tree traversal to return our catch node
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Swallowed exception" in findings[0].message
        assert "empty handler" in findings[0].message

    def test_python_pass_only_handler(self):
        """Test detection of Python handler with only pass statement."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", "pass")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "trivial statements" in findings[0].message

    def test_python_proper_logging_handler(self):
        """Test that Python handler with logging is not flagged."""
        ctx = self._create_mock_context("python")
        handler_text = "logging.error('Database connection failed: %s', e)"
        catch_node = self._create_mock_catch_node("python", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_python_proper_reraise_handler(self):
        """Test that Python handler with reraise is not flagged."""
        ctx = self._create_mock_context("python")
        handler_text = "print('Error occurred'); raise"
        catch_node = self._create_mock_catch_node("python", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_python_todo_comment_handler(self):
        """Test detection of Python handler with only TODO comment."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", "# TODO: Handle this properly")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "trivial statements" in findings[0].message

    # ============================================================================
    # Java Tests
    # ============================================================================

    def test_java_empty_catch_handler(self):
        """Test detection of empty Java catch handler."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "empty handler" in findings[0].message

    def test_java_semicolon_only_handler(self):
        """Test detection of Java handler with only semicolon."""
        ctx = self._create_mock_context("java")
        catch_node = self._create_mock_catch_node("java", ";")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_java_proper_logging_handler(self):
        """Test that Java handler with logging is not flagged."""
        ctx = self._create_mock_context("java")
        handler_text = 'logger.error("Connection failed", e);'
        catch_node = self._create_mock_catch_node("java", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_java_proper_rethrow_handler(self):
        """Test that Java handler with rethrow is not flagged."""
        ctx = self._create_mock_context("java")
        handler_text = 'System.err.println("Error: " + e); throw e;'
        catch_node = self._create_mock_catch_node("java", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # C# Tests
    # ============================================================================

    def test_csharp_empty_catch_handler(self):
        """Test detection of empty C# catch handler."""
        ctx = self._create_mock_context("csharp")
        catch_node = self._create_mock_catch_node("csharp", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "empty handler" in findings[0].message

    def test_csharp_proper_logging_handler(self):
        """Test that C# handler with logging is not flagged."""
        ctx = self._create_mock_context("csharp")
        handler_text = '_logger.LogError(ex, "Operation failed");'
        catch_node = self._create_mock_catch_node("csharp", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_csharp_proper_rethrow_handler(self):
        """Test that C# handler with rethrow is not flagged."""
        ctx = self._create_mock_context("csharp")
        handler_text = 'Console.WriteLine("Error: " + ex.Message); throw;'
        catch_node = self._create_mock_catch_node("csharp", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # Ruby Tests
    # ============================================================================

    def test_ruby_empty_rescue_handler(self):
        """Test detection of empty Ruby rescue handler."""
        ctx = self._create_mock_context("ruby")
        catch_node = self._create_mock_catch_node("ruby", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "empty handler" in findings[0].message

    def test_ruby_proper_logging_handler(self):
        """Test that Ruby handler with logging is not flagged."""
        ctx = self._create_mock_context("ruby")
        handler_text = 'logger.error "Database error: #{e.message}"'
        catch_node = self._create_mock_catch_node("ruby", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_ruby_proper_reraise_handler(self):
        """Test that Ruby handler with reraise is not flagged."""
        ctx = self._create_mock_context("ruby")
        handler_text = 'puts "Error occurred: #{e}"; raise'
        catch_node = self._create_mock_catch_node("ruby", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # JavaScript Tests
    # ============================================================================

    def test_javascript_empty_catch_handler(self):
        """Test detection of empty JavaScript catch handler."""
        ctx = self._create_mock_context("javascript")
        catch_node = self._create_mock_catch_node("javascript", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "empty handler" in findings[0].message

    def test_javascript_semicolon_only_handler(self):
        """Test detection of JavaScript handler with only semicolon."""
        ctx = self._create_mock_context("javascript")
        catch_node = self._create_mock_catch_node("javascript", ";")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1

    def test_javascript_proper_console_handler(self):
        """Test that JavaScript handler with console logging is not flagged."""
        ctx = self._create_mock_context("javascript")
        handler_text = 'console.error("API call failed:", error);'
        catch_node = self._create_mock_catch_node("javascript", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_javascript_proper_rethrow_handler(self):
        """Test that JavaScript handler with rethrow is not flagged."""
        ctx = self._create_mock_context("javascript")
        handler_text = 'logger.error("Request failed", error); throw error;'
        catch_node = self._create_mock_catch_node("javascript", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # ============================================================================
    # TypeScript Tests
    # ============================================================================

    def test_typescript_empty_catch_handler(self):
        """Test detection of empty TypeScript catch handler."""
        ctx = self._create_mock_context("typescript")
        catch_node = self._create_mock_catch_node("typescript", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "empty handler" in findings[0].message

    def test_typescript_proper_console_handler(self):
        """Test that TypeScript handler with console logging is not flagged."""
        ctx = self._create_mock_context("typescript")
        handler_text = 'console.error("Service error:", error);'
        catch_node = self._create_mock_catch_node("typescript", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_typescript_proper_rethrow_handler(self):
        """Test that TypeScript handler with rethrow is not flagged."""
        ctx = self._create_mock_context("typescript")
        handler_text = 'this.logger.error("Operation failed", error); throw error;'
        catch_node = self._create_mock_catch_node("typescript", handler_text)
        
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
        ctx = self._create_mock_context("unsupported_lang")
        catch_node = self._create_mock_catch_node("unsupported_lang", "")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_no_catch_nodes_found(self):
        """Test when no catch/except nodes are found."""
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
        assert len(findings) == 1  # Should still detect as swallowed (empty)

    def test_multiple_catch_handlers_mixed(self):
        """Test file with multiple catch handlers - some good, some bad."""
        ctx = self._create_mock_context("python")
        
        # Bad handler (empty)
        bad_catch = self._create_mock_catch_node("python", "")
        
        # Good handler (with logging)
        good_catch = self._create_mock_catch_node("python", "logging.error('Failed: %s', e)")
        
        def mock_walk(tree):
            yield bad_catch
            yield good_catch
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1  # Only the bad handler should be flagged

    def test_handler_with_multiple_statements_but_no_logging(self):
        """Test handler with multiple statements but no error handling."""
        ctx = self._create_mock_context("python")
        handler_text = """
        x = 1
        y = 2
        return x + y
        """
        catch_node = self._create_mock_catch_node("python", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1  # Should be flagged as swallowed

    def test_handler_with_comment_and_real_code(self):
        """Test handler with TODO comment but also real error handling."""
        ctx = self._create_mock_context("python")
        handler_text = """
        # TODO: Improve error message
        logging.error('Database connection failed: %s', e)
        raise
        """
        catch_node = self._create_mock_catch_node("python", handler_text)
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0  # Should not be flagged due to logging + raise

    def test_byte_position_extraction(self):
        """Test that byte positions are correctly extracted for findings."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", "")
        catch_node.start_byte = 100
        catch_node.end_byte = 150
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert findings[0].start_byte == 100
        assert findings[0].end_byte == 150

    def test_finding_metadata(self):
        """Test that finding metadata is correctly populated."""
        ctx = self._create_mock_context("python")
        catch_node = self._create_mock_catch_node("python", "pass")
        
        def mock_walk(tree):
            yield catch_node
        
        self.rule._walk_nodes = mock_walk
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        finding = findings[0]
        
        assert finding.rule == "errors.swallowed_exception"
        assert finding.severity == "error"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert "language" in finding.meta
        assert "handler_type" in finding.meta
        assert finding.meta["language"] == "python"
        assert finding.meta["handler_type"] == "trivial"

    def test_suggestion_generation_all_languages(self):
        """Test that suggestions are generated for all supported languages."""
        languages = ["python", "java", "csharp", "ruby", "javascript", "typescript"]
        
        for language in languages:
            ctx = self._create_mock_context(language)
            catch_node = self._create_mock_catch_node(language, "")
            
            def mock_walk(tree):
                yield catch_node
            
            self.rule._walk_nodes = mock_walk
            
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 1
            assert "suggestion" in findings[0].meta
            suggestion = findings[0].meta["suggestion"]
            assert len(suggestion) > 50  # Should be substantial
            
            # Language-specific keywords should appear in suggestions
            if language == "python":
                assert "logging.error" in suggestion or "raise" in suggestion
            elif language == "java":
                assert "logger.error" in suggestion or "throw" in suggestion
            elif language == "csharp":
                assert "_logger.Log" in suggestion or "throw" in suggestion
            elif language == "ruby":
                assert "logger.error" in suggestion or "raise" in suggestion
            elif language in ["javascript", "typescript"]:
                assert "console.error" in suggestion or "throw" in suggestion

