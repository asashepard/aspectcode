# server/tests/test_errors_broad_catch.py
"""
Tests for the errors.broad_catch rule.

This tests that the rule correctly:
- Flags broad exception catches across multiple languages  
- Ignores specific, narrow exception catches
- Provides appropriate language-specific suggestions
- Handles edge cases like multi-catch, qualified names, etc.
"""

import pytest
from unittest.mock import Mock
from rules.errors_broad_catch import ErrorsBroadCatchRule
from engine.types import RuleContext


class TestErrorsBroadCatchRule:
    """Test suite for the errors.broad_catch rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ErrorsBroadCatchRule()

    def _create_mock_context(self, code: str, language: str = "python") -> RuleContext:
        """Create a mock rule context for testing."""
        adapter = Mock()
        adapter.language_id = language
        
        tree = Mock()
        root = Mock()
        root.type = "program"
        tree.root_node = root
        
        ctx = Mock(spec=RuleContext)
        ctx.adapter = adapter
        ctx.file_path = f"test.{self._get_extension(language)}"
        ctx.config = {}
        ctx.text = code
        ctx.tree = tree
        
        return ctx

    def _get_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "python": "py",
            "java": "java",
            "csharp": "cs",
            "ruby": "rb",
            "javascript": "js",
            "typescript": "ts"
        }
        return extensions.get(language, "txt")

    def test_positive_python_bare_except(self):
        """Test that Python bare except: is flagged."""
        code = """
try:
    risky_operation()
except:
    handle_error()
"""
        ctx = self._create_mock_context(code, "python")
        
        # Mock except clause node
        except_node = Mock()
        except_node.type = "except_clause"
        except_node.start_byte = 25
        except_node.end_byte = 32
        except_node.text = b"except:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "bare 'except:'" in findings[0].message.lower()
        assert findings[0].severity == "warn"
        assert findings[0].rule == "errors.broad_catch"

    def test_positive_python_except_exception(self):
        """Test that Python except Exception is flagged."""
        code = """
try:
    risky_operation()
except Exception as e:
    handle_error(e)
"""
        ctx = self._create_mock_context(code, "python")
        
        except_node = Mock()
        except_node.type = "except_clause"
        except_node.start_byte = 25
        except_node.end_byte = 50
        except_node.text = b"except Exception as e:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "broad catch" in findings[0].message.lower()
        assert "Exception" in findings[0].message

    def test_positive_python_except_base_exception(self):
        """Test that Python except BaseException is flagged."""
        code = """
try:
    risky_operation()
except BaseException as e:
    handle_error(e)
"""
        ctx = self._create_mock_context(code, "python")
        
        except_node = Mock()
        except_node.type = "except_clause"
        except_node.start_byte = 25
        except_node.end_byte = 54
        except_node.text = b"except BaseException as e:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "BaseException" in findings[0].message

    def test_positive_java_catch_exception(self):
        """Test that Java catch (Exception e) is flagged."""
        code = """
try {
    riskyOperation();
} catch (Exception e) {
    handleError(e);
}
"""
        ctx = self._create_mock_context(code, "java")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 35
        catch_node.end_byte = 60
        catch_node.text = b"catch (Exception e)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "broad catch" in findings[0].message.lower()
        assert "Exception" in findings[0].message

    def test_positive_java_catch_throwable(self):
        """Test that Java catch (Throwable t) is flagged."""
        code = """
try {
    riskyOperation();
} catch (Throwable t) {
    handleError(t);
}
"""
        ctx = self._create_mock_context(code, "java")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 35
        catch_node.end_byte = 62
        catch_node.text = b"catch (Throwable t)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Throwable" in findings[0].message

    def test_positive_java_multicatch_with_exception(self):
        """Test that Java multi-catch with Exception is flagged."""
        code = """
try {
    riskyOperation();
} catch (IOException | Exception e) {
    handleError(e);
}
"""
        ctx = self._create_mock_context(code, "java")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 35
        catch_node.end_byte = 75
        catch_node.text = b"catch (IOException | Exception e)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "broad catch" in findings[0].message.lower()

    def test_positive_csharp_untyped_catch(self):
        """Test that C# untyped catch is flagged."""
        code = """
try
{
    RiskyOperation();
}
catch
{
    HandleError();
}
"""
        ctx = self._create_mock_context(code, "csharp")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 45
        catch_node.end_byte = 50
        catch_node.text = b"catch"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "untyped 'catch'" in findings[0].message.lower()

    def test_positive_csharp_catch_exception(self):
        """Test that C# catch (Exception ex) is flagged."""
        code = """
try
{
    RiskyOperation();
}
catch (Exception ex)
{
    HandleError(ex);
}
"""
        ctx = self._create_mock_context(code, "csharp")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 45
        catch_node.end_byte = 70
        catch_node.text = b"catch (Exception ex)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Exception" in findings[0].message

    def test_positive_ruby_generic_rescue(self):
        """Test that Ruby generic rescue is flagged."""
        code = """
begin
  risky_operation
rescue
  handle_error
end
"""
        ctx = self._create_mock_context(code, "ruby")
        
        rescue_node = Mock()
        rescue_node.type = "rescue"
        rescue_node.start_byte = 25
        rescue_node.end_byte = 31
        rescue_node.text = b"rescue"
        
        self.rule._walk_nodes = Mock(return_value=[rescue_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "generic 'rescue'" in findings[0].message.lower()

    def test_positive_ruby_rescue_exception(self):
        """Test that Ruby rescue Exception is flagged."""
        code = """
begin
  risky_operation
rescue Exception => e
  handle_error(e)
end
"""
        ctx = self._create_mock_context(code, "ruby")
        
        rescue_node = Mock()
        rescue_node.type = "rescue"
        rescue_node.start_byte = 25
        rescue_node.end_byte = 48
        rescue_node.text = b"rescue Exception => e"
        
        self.rule._walk_nodes = Mock(return_value=[rescue_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Exception" in findings[0].message

    def test_positive_javascript_catch(self):
        """Test that JavaScript catch is flagged as broad."""
        code = """
try {
    riskyOperation();
} catch (error) {
    handleError(error);
}
"""
        ctx = self._create_mock_context(code, "javascript")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 35
        catch_node.end_byte = 55
        catch_node.text = b"catch (error)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "inherently broad" in findings[0].message.lower()

    def test_positive_typescript_catch(self):
        """Test that TypeScript catch is flagged as broad."""
        code = """
try {
    riskyOperation();
} catch (error: unknown) {
    handleError(error);
}
"""
        ctx = self._create_mock_context(code, "typescript")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.start_byte = 35
        catch_node.end_byte = 60
        catch_node.text = b"catch (error: unknown)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "inherently broad" in findings[0].message.lower()

    def test_negative_python_specific_exception(self):
        """Test that Python specific exceptions are not flagged."""
        code = """
try:
    risky_operation()
except ValueError as e:
    handle_value_error(e)
except IOError as e:
    handle_io_error(e)
"""
        ctx = self._create_mock_context(code, "python")
        
        except_node1 = Mock()
        except_node1.type = "except_clause"
        except_node1.text = b"except ValueError as e:"
        
        except_node2 = Mock()
        except_node2.type = "except_clause"
        except_node2.text = b"except IOError as e:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node1, except_node2])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_java_specific_exception(self):
        """Test that Java specific exceptions are not flagged."""
        code = """
try {
    riskyOperation();
} catch (IOException e) {
    handleIOError(e);
} catch (IllegalArgumentException e) {
    handleArgumentError(e);
}
"""
        ctx = self._create_mock_context(code, "java")
        
        catch_node1 = Mock()
        catch_node1.type = "catch_clause"
        catch_node1.text = b"catch (IOException e)"
        
        catch_node2 = Mock()
        catch_node2.type = "catch_clause"
        catch_node2.text = b"catch (IllegalArgumentException e)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node1, catch_node2])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_csharp_specific_exception(self):
        """Test that C# specific exceptions are not flagged."""
        code = """
try
{
    RiskyOperation();
}
catch (ArgumentException ex)
{
    HandleArgumentError(ex);
}
catch (IOException ex)
{
    HandleIOError(ex);
}
"""
        ctx = self._create_mock_context(code, "csharp")
        
        catch_node1 = Mock()
        catch_node1.type = "catch_clause"
        catch_node1.text = b"catch (ArgumentException ex)"
        
        catch_node2 = Mock()
        catch_node2.type = "catch_clause"
        catch_node2.text = b"catch (IOException ex)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node1, catch_node2])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_ruby_specific_error(self):
        """Test that Ruby specific errors are not flagged."""
        code = """
begin
  risky_operation
rescue ArgumentError => e
  handle_argument_error(e)
rescue IOError => e
  handle_io_error(e)
end
"""
        ctx = self._create_mock_context(code, "ruby")
        
        rescue_node1 = Mock()
        rescue_node1.type = "rescue"
        rescue_node1.text = b"rescue ArgumentError => e"
        
        rescue_node2 = Mock()
        rescue_node2.type = "rescue"
        rescue_node2.text = b"rescue IOError => e"
        
        self.rule._walk_nodes = Mock(return_value=[rescue_node1, rescue_node2])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_negative_javascript_with_rethrow(self):
        """Test that JavaScript catch with immediate rethrow is not flagged."""
        code = """
try {
    riskyOperation();
} catch (error) {
    console.error('Operation failed:', error);
    throw new CustomError('Wrapped error', error);
}
"""
        ctx = self._create_mock_context(code, "javascript")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.text = b"catch (error) {\n    console.error('Operation failed:', error);\n    throw new CustomError('Wrapped error', error);\n}"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0  # Should not flag due to rethrow pattern

    def test_edge_case_qualified_exception_names(self):
        """Test handling of qualified exception names."""
        code = """
try {
    riskyOperation();
} catch (java.lang.Exception e) {
    handleError(e);
}
"""
        ctx = self._create_mock_context(code, "java")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.text = b"catch (java.lang.Exception e)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "java.lang.Exception" in findings[0].message

    def test_edge_case_system_exception_csharp(self):
        """Test handling of System.Exception in C#."""
        code = """
try
{
    RiskyOperation();
}
catch (System.Exception ex)
{
    HandleError(ex);
}
"""
        ctx = self._create_mock_context(code, "csharp")
        
        catch_node = Mock()
        catch_node.type = "catch_clause"
        catch_node.text = b"catch (System.Exception ex)"
        
        self.rule._walk_nodes = Mock(return_value=[catch_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "System.Exception" in findings[0].message

    def test_suggestion_contains_appropriate_guidance(self):
        """Test that suggestions contain appropriate refactoring guidance."""
        code = """
try:
    risky_operation()
except:
    handle_error()
"""
        ctx = self._create_mock_context(code, "python")
        
        except_node = Mock()
        except_node.type = "except_clause"
        except_node.text = b"except:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta["suggestion"]
        
        assert "specific exception types" in suggestion.lower()
        assert "valueerror" in suggestion.lower()
        assert "ioerror" in suggestion.lower()
        assert "try:" in suggestion
        assert "except" in suggestion

    def test_meta_information_correct(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "errors.broad_catch"
        assert self.rule.meta.category == "errors"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs

    def test_requires_syntax_only(self):
        """Test that rule requires only syntax analysis."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is False
        assert self.rule.requires.project_graph is False

    def test_unsupported_language_returns_empty(self):
        """Test that unsupported languages return no findings."""
        code = "some code here"
        ctx = self._create_mock_context(code, "unsupported_lang")
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_broad_type_identification(self):
        """Test that broad exception types are correctly identified."""
        # Test Python
        assert "Exception" in self.rule.BROAD_EXCEPTION_TYPES["python"]
        assert "BaseException" in self.rule.BROAD_EXCEPTION_TYPES["python"]
        
        # Test Java
        assert "Exception" in self.rule.BROAD_EXCEPTION_TYPES["java"]
        assert "Throwable" in self.rule.BROAD_EXCEPTION_TYPES["java"]
        assert "java.lang.Exception" in self.rule.BROAD_EXCEPTION_TYPES["java"]
        
        # Test C#
        assert "Exception" in self.rule.BROAD_EXCEPTION_TYPES["csharp"]
        assert "System.Exception" in self.rule.BROAD_EXCEPTION_TYPES["csharp"]
        
        # Test Ruby
        assert "Exception" in self.rule.BROAD_EXCEPTION_TYPES["ruby"]

    def test_catch_node_types_mapping(self):
        """Test that catch node types are correctly mapped for each language."""
        assert "except_clause" in self.rule.CATCH_NODE_TYPES["python"]
        assert "catch_clause" in self.rule.CATCH_NODE_TYPES["java"]
        assert "catch_clause" in self.rule.CATCH_NODE_TYPES["csharp"]
        assert "general_catch_clause" in self.rule.CATCH_NODE_TYPES["csharp"]
        assert "rescue" in self.rule.CATCH_NODE_TYPES["ruby"]
        assert "catch_clause" in self.rule.CATCH_NODE_TYPES["javascript"]
        assert "catch_clause" in self.rule.CATCH_NODE_TYPES["typescript"]

    def test_language_specific_suggestions(self):
        """Test that each language gets appropriate suggestion format."""
        # Test Python suggestion
        python_suggestion = self.rule._create_python_suggestion("Exception")
        assert "try:" in python_suggestion
        assert "except ValueError" in python_suggestion
        assert "except IOError" in python_suggestion
        
        # Test Java suggestion
        java_suggestion = self.rule._create_java_suggestion("Exception")
        assert "try {" in java_suggestion
        assert "} catch (IOException" in java_suggestion
        assert "IllegalArgumentException" in java_suggestion
        
        # Test C# suggestion
        cs_suggestion = self.rule._create_csharp_suggestion("Exception")
        assert "try" in cs_suggestion
        assert "ArgumentException" in cs_suggestion
        assert "IOException" in cs_suggestion
        
        # Test Ruby suggestion
        ruby_suggestion = self.rule._create_ruby_suggestion("Exception")
        assert "begin" in ruby_suggestion
        assert "rescue ArgumentError" in ruby_suggestion
        assert "rescue IOError" in ruby_suggestion
        
        # Test JavaScript suggestion
        js_suggestion = self.rule._create_js_suggestion()
        assert "instanceof" in js_suggestion
        assert "TypeError" in js_suggestion
        assert "throw error" in js_suggestion

    @pytest.mark.skip(reason="suggest-only: rule provides guidance, not edits")
    def test_autofix_skipped(self):
        """Test that autofix is skipped since this is a suggest-only rule."""
        pass

    def test_multiple_broad_catches_detected(self):
        """Test that multiple broad catches in the same file are all detected."""
        code = """
try:
    operation1()
except:
    handle1()

try:
    operation2()
except Exception:
    handle2()
"""
        ctx = self._create_mock_context(code, "python")
        
        except_node1 = Mock()
        except_node1.type = "except_clause"
        except_node1.text = b"except:"
        
        except_node2 = Mock()
        except_node2.type = "except_clause"
        except_node2.text = b"except Exception as e:"
        
        self.rule._walk_nodes = Mock(return_value=[except_node1, except_node2])
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 2
        assert any("Bare 'except:'" in f.message for f in findings)
        assert any("Exception" in f.message for f in findings)

