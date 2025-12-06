# server/tests/test_errors_multiple_catch_order_issue.py
"""
Tests for the errors.multiple_catch_order_issue rule.

This module tests the detection of unreachable catch blocks due to improper
exception ordering in Java and C# languages.
"""

import unittest
from unittest.mock import Mock
from typing import List, Optional

from rules.errors_multiple_catch_order_issue import ErrorsMultipleCatchOrderIssueRule
from engine.types import RuleContext, Finding


class MockNode:
    """Mock tree-sitter node for testing."""
    
    def __init__(self, node_type: str, start_byte: int = 0, end_byte: int = 10, 
                 children: Optional[List['MockNode']] = None, text: str = ""):
        self.type = node_type
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.children = children or []
        self.text = text


class MockTree:
    """Mock tree-sitter tree for testing."""
    
    def __init__(self, root_node: MockNode):
        self.root_node = root_node


class MockAdapter:
    """Mock adapter for testing."""
    
    def __init__(self, language_id: str):
        self.language_id = language_id


class TestErrorsMultipleCatchOrderIssueRule(unittest.TestCase):
    """Test cases for ErrorsMultipleCatchOrderIssueRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = ErrorsMultipleCatchOrderIssueRule()

    def _create_context(self, language: str, tree: MockTree, file_text: str = "") -> RuleContext:
        """Create a mock RuleContext for testing."""
        ctx = Mock(spec=RuleContext)
        ctx.adapter = MockAdapter(language)
        ctx.tree = tree
        ctx.text = file_text
        ctx.file_path = f"test.{self._get_file_extension(language)}"
        return ctx

    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            "java": "java",
            "csharp": "cs"
        }
        return extensions.get(language, "txt")

    def _create_findings_list(self, ctx: RuleContext) -> List[Finding]:
        """Helper to convert generator to list."""
        return list(self.rule.visit(ctx))

    def _create_catch_clause(self, exception_type: str, start_byte: int, end_byte: int, language: str = "java") -> MockNode:
        """Create a mock catch clause node."""
        # Create catch parameter/header based on language
        if language == "java":
            param_text = f"({exception_type} e)"
            param_node = MockNode("catch_formal_parameter", start_byte + 5, start_byte + 5 + len(param_text), [], param_text)
        else:  # csharp
            param_text = f"({exception_type} ex)"
            param_node = MockNode("catch_declaration", start_byte + 5, start_byte + 5 + len(param_text), [], param_text)
        
        catch_clause = MockNode("catch_clause", start_byte, end_byte, [param_node])
        return catch_clause

    def _create_try_statement(self, catch_clauses: List[MockNode], language: str = "java") -> MockNode:
        """Create a mock try statement with catch clauses."""
        try_type = "try_statement"
        try_node = MockNode(try_type, 0, 100, catch_clauses)
        return try_node

    # POSITIVE TESTS - Should detect unreachable catch blocks

    def test_java_exception_before_ioexception(self):
        """Test detection when Exception is caught before IOException in Java."""
        # Create catch clauses: Exception first, then IOException
        catch1 = self._create_catch_clause("Exception", 20, 40, "java")
        catch2 = self._create_catch_clause("IOException", 50, 75, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (Exception e) {
    handle(e);
} catch (IOException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.multiple_catch_order_issue")
        self.assertIn("IOException", finding.message)
        self.assertIn("unreachable", finding.message.lower())
        self.assertEqual(finding.severity, "info")

    def test_java_throwable_before_exception(self):
        """Test detection when Throwable is caught before Exception in Java."""
        catch1 = self._create_catch_clause("Throwable", 20, 40, "java")
        catch2 = self._create_catch_clause("Exception", 50, 75, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    riskyOperation();
} catch (Throwable t) {
    handle(t);
} catch (Exception e) {
    handle(e);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("Exception", finding.message)

    def test_csharp_exception_before_ioexception(self):
        """Test detection when Exception is caught before IOException in C#."""
        catch1 = self._create_catch_clause("Exception", 20, 40, "csharp")
        catch2 = self._create_catch_clause("IOException", 50, 75, "csharp")
        
        try_stmt = self._create_try_statement([catch1, catch2], "csharp")
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try
{
    File.ReadAllText(path);
}
catch (Exception ex)
{
    Handle(ex);
}
catch (IOException ex)
{
    Handle(ex);
}"""
        
        ctx = self._create_context("csharp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("IOException", finding.message)

    def test_csharp_system_exception_before_argumentexception(self):
        """Test detection when System.Exception is caught before ArgumentException in C#."""
        catch1 = self._create_catch_clause("System.Exception", 20, 45, "csharp")
        catch2 = self._create_catch_clause("ArgumentException", 55, 85, "csharp")
        
        try_stmt = self._create_try_statement([catch1, catch2], "csharp")
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try
{
    ProcessArguments(args);
}
catch (System.Exception ex)
{
    Handle(ex);
}
catch (ArgumentException ex)
{
    Handle(ex);
}"""
        
        ctx = self._create_context("csharp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("ArgumentException", finding.message)

    def test_multiple_unreachable_catches(self):
        """Test detection of multiple unreachable catch blocks."""
        # Exception first, then IOException, then FileNotFoundException
        catch1 = self._create_catch_clause("Exception", 20, 40, "java")
        catch2 = self._create_catch_clause("IOException", 50, 75, "java")
        catch3 = self._create_catch_clause("FileNotFoundException", 85, 120, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2, catch3], "java")
        root = MockNode("compilation_unit", 0, 130, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (Exception e) {
    handle(e);
} catch (IOException ex) {
    handle(ex);
} catch (FileNotFoundException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        # Both IOException and FileNotFoundException should be flagged
        self.assertEqual(len(findings), 2)
        messages = [f.message for f in findings]
        self.assertTrue(any("IOException" in msg for msg in messages))
        self.assertTrue(any("FileNotFoundException" in msg for msg in messages))

    def test_duplicate_exception_types(self):
        """Test detection of duplicate catch blocks."""
        catch1 = self._create_catch_clause("IOException", 20, 45, "java")
        catch2 = self._create_catch_clause("IOException", 55, 80, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 90, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (IOException e1) {
    handle(e1);
} catch (IOException e2) {
    handle(e2);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("IOException", finding.message)

    # NEGATIVE TESTS - Should not detect issues with proper ordering

    def test_java_specific_before_general(self):
        """Test that IOException before Exception is not flagged in Java."""
        catch1 = self._create_catch_clause("IOException", 20, 45, "java")
        catch2 = self._create_catch_clause("Exception", 55, 80, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 90, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (IOException ex) {
    handle(ex);
} catch (Exception e) {
    handle(e);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_csharp_specific_before_general(self):
        """Test that IOException before Exception is not flagged in C#."""
        catch1 = self._create_catch_clause("IOException", 20, 45, "csharp")
        catch2 = self._create_catch_clause("Exception", 55, 80, "csharp")
        
        try_stmt = self._create_try_statement([catch1, catch2], "csharp")
        root = MockNode("compilation_unit", 0, 90, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try
{
    File.ReadAllText(path);
}
catch (IOException ex)
{
    Handle(ex);
}
catch (Exception ex)
{
    Handle(ex);
}"""
        
        ctx = self._create_context("csharp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_java_hierarchical_ordering(self):
        """Test proper hierarchical ordering in Java."""
        # FileNotFoundException -> IOException -> Exception
        catch1 = self._create_catch_clause("FileNotFoundException", 20, 55, "java")
        catch2 = self._create_catch_clause("IOException", 65, 90, "java")
        catch3 = self._create_catch_clause("Exception", 100, 125, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2, catch3], "java")
        root = MockNode("compilation_unit", 0, 135, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (FileNotFoundException ex) {
    handle(ex);
} catch (IOException ex) {
    handle(ex);
} catch (Exception e) {
    handle(e);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_single_catch_block(self):
        """Test that single catch blocks are not analyzed."""
        catch1 = self._create_catch_clause("Exception", 20, 45, "java")
        
        try_stmt = self._create_try_statement([catch1], "java")
        root = MockNode("compilation_unit", 0, 55, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    riskyOperation();
} catch (Exception e) {
    handle(e);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_no_catch_blocks(self):
        """Test that try statements without catch blocks are ignored."""
        try_stmt = MockNode("try_statement", 0, 30, [])
        root = MockNode("compilation_unit", 0, 30, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    riskyOperation();
} finally {
    cleanup();
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_unrelated_exceptions(self):
        """Test that unrelated exception types in proper order are not flagged."""
        catch1 = self._create_catch_clause("IllegalArgumentException", 20, 55, "java")
        catch2 = self._create_catch_clause("IOException", 65, 90, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    processArguments(args);
    Files.readAllLines(path);
} catch (IllegalArgumentException ex) {
    handle(ex);
} catch (IOException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    # EDGE CASES

    def test_unsupported_language(self):
        """Test that unsupported languages are ignored."""
        catch1 = self._create_catch_clause("Exception", 20, 45, "python")
        catch2 = self._create_catch_clause("IOException", 55, 80, "python")
        
        try_stmt = self._create_try_statement([catch1, catch2], "python")
        root = MockNode("module", 0, 90, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "# Python code")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_malformed_tree(self):
        """Test handling of malformed or missing tree structures."""
        ctx = self._create_context("java", None)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_empty_tree(self):
        """Test handling of empty syntax tree."""
        root = MockNode("compilation_unit", 0, 0, [])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_catch_without_header(self):
        """Test handling of catch clauses without proper headers."""
        # Create catch clause without proper parameter declaration
        catch1 = MockNode("catch_clause", 20, 40, [])
        catch2 = self._create_catch_clause("IOException", 50, 75, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 85, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "malformed catch")
        findings = self._create_findings_list(ctx)
        
        # Should handle gracefully without throwing
        self.assertIsInstance(findings, list)

    def test_java_multi_catch_with_broad_type(self):
        """Test Java multi-catch including a broad type."""
        # Create a multi-catch with Exception | IOException (Exception makes IOException unreachable)
        multi_catch_text = "(Exception | IOException e)"
        multi_catch_node = MockNode("catch_formal_parameter", 25, 25 + len(multi_catch_text), [], multi_catch_text)
        catch1 = MockNode("catch_clause", 20, 50, [multi_catch_node])
        catch2 = self._create_catch_clause("FileNotFoundException", 60, 95, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 105, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (Exception | IOException e) {
    handle(e);
} catch (FileNotFoundException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        # FileNotFoundException should be flagged as unreachable
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("FileNotFoundException", finding.message)

    def test_finding_metadata(self):
        """Test that findings contain proper metadata."""
        catch1 = self._create_catch_clause("Exception", 20, 40, "java")
        catch2 = self._create_catch_clause("IOException", 50, 75, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 85, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (Exception e) {
    handle(e);
} catch (IOException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        
        # Check metadata
        self.assertIsNotNone(finding.meta)
        self.assertEqual(finding.meta["language"], "java")
        self.assertIn("exception_types", finding.meta)
        self.assertIn("suggestion", finding.meta)
        self.assertIn("catch_span", finding.meta)
        
        # Check exception types
        self.assertIn("IOException", finding.meta["exception_types"])

    def test_suggestion_content_java(self):
        """Test that Java suggestions contain helpful refactoring advice."""
        catch1 = self._create_catch_clause("Exception", 20, 40, "java")
        catch2 = self._create_catch_clause("IOException", 50, 75, "java")
        
        try_stmt = self._create_try_statement([catch1, catch2], "java")
        root = MockNode("compilation_unit", 0, 85, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try {
    Files.readAllLines(path);
} catch (Exception e) {
    handle(e);
} catch (IOException ex) {
    handle(ex);
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain specific refactoring patterns
        self.assertIn("specific exceptions first", suggestion)
        self.assertIn("catch (IOException", suggestion)
        self.assertIn("catch (Exception", suggestion)
        self.assertIn("multi-catch", suggestion)

    def test_suggestion_content_csharp(self):
        """Test that C# suggestions contain language-appropriate advice."""
        catch1 = self._create_catch_clause("Exception", 20, 40, "csharp")
        catch2 = self._create_catch_clause("IOException", 50, 75, "csharp")
        
        try_stmt = self._create_try_statement([catch1, catch2], "csharp")
        root = MockNode("compilation_unit", 0, 85, [try_stmt])
        tree = MockTree(root)
        
        file_text = """try
{
    File.ReadAllText(path);
}
catch (Exception ex)
{
    Handle(ex);
}
catch (IOException ex)
{
    Handle(ex);
}"""
        
        ctx = self._create_context("csharp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain C#-specific patterns
        self.assertIn("specific exceptions first", suggestion)
        self.assertIn("catch (IOException", suggestion)
        self.assertIn("exception filters", suggestion)
        self.assertIn("when (", suggestion)


if __name__ == '__main__':
    unittest.main()

