# server/tests/test_errors_finally_control_flow.py
"""
Tests for the errors.finally_control_flow rule.

This module tests the detection of control flow statements (return, break, continue)
in finally blocks across Python, Java, and C# languages.
"""

import unittest
from unittest.mock import Mock
from typing import List, Optional

from rules.errors_finally_control_flow import ErrorsFinallyControlFlowRule
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


class TestErrorsFinallyControlFlowRule(unittest.TestCase):
    """Test cases for ErrorsFinallyControlFlowRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = ErrorsFinallyControlFlowRule()

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
            "python": "py",
            "java": "java", 
            "csharp": "cs"
        }
        return extensions.get(language, "txt")

    def _create_findings_list(self, ctx: RuleContext) -> List[Finding]:
        """Helper to convert generator to list."""
        return list(self.rule.visit(ctx))

    # POSITIVE TESTS - Should detect control flow in finally blocks

    def test_python_return_in_finally(self):
        """Test detection of return statement in Python finally block."""
        # Create AST: try-finally with return in finally
        return_stmt = MockNode("return_statement", 50, 65)
        finally_block = MockNode("finally_clause", 40, 70, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 70, [finally_block])
        root = MockNode("module", 0, 70, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    return 'done'")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.finally_control_flow")
        self.assertIn("return", finding.message)
        self.assertEqual(finding.severity, "warn")
        self.assertEqual(finding.start_byte, 50)
        self.assertEqual(finding.end_byte, 65)

    def test_python_break_in_finally(self):
        """Test detection of break statement in Python finally block."""
        break_stmt = MockNode("break_statement", 75, 85)
        finally_block = MockNode("finally_clause", 60, 90, [break_stmt])
        for_loop = MockNode("for_statement", 0, 90, [finally_block])
        root = MockNode("module", 0, 90, [for_loop])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "for i in range(10):\n    try:\n        pass\n    finally:\n        break")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.finally_control_flow")
        self.assertIn("break", finding.message)
        self.assertEqual(finding.severity, "warn")

    def test_python_continue_in_finally(self):
        """Test detection of continue statement in Python finally block."""
        continue_stmt = MockNode("continue_statement", 75, 88)
        finally_block = MockNode("finally_clause", 60, 95, [continue_stmt])
        for_loop = MockNode("for_statement", 0, 95, [finally_block])
        root = MockNode("module", 0, 95, [for_loop])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "for i in range(10):\n    try:\n        pass\n    finally:\n        continue")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.finally_control_flow")
        self.assertIn("continue", finding.message)

    def test_java_return_in_finally(self):
        """Test detection of return statement in Java finally block."""
        return_stmt = MockNode("return_statement", 80, 95)
        finally_block = MockNode("finally_clause", 70, 100, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 100, [finally_block])
        method = MockNode("method_declaration", 0, 100, [try_stmt])
        root = MockNode("program", 0, 100, [method])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "public String test() {\n    try {\n        return \"try\";\n    } finally {\n        return \"finally\";\n    }\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.finally_control_flow")
        self.assertIn("return", finding.message)

    def test_java_break_in_finally(self):
        """Test detection of break statement in Java finally block."""
        break_stmt = MockNode("break_statement", 90, 100)
        finally_block = MockNode("finally_clause", 80, 105, [break_stmt])
        try_stmt = MockNode("try_statement", 50, 105, [finally_block])
        for_loop = MockNode("for_statement", 0, 105, [try_stmt])
        root = MockNode("program", 0, 105, [for_loop])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "for (int i = 0; i < 10; i++) {\n    try {\n        // code\n    } finally {\n        break;\n    }\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("break", finding.message)

    def test_csharp_return_in_finally(self):
        """Test detection of return statement in C# finally block."""
        return_stmt = MockNode("return_statement", 70, 85)
        finally_block = MockNode("finally_clause", 60, 90, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 90, [finally_block])
        method = MockNode("method_declaration", 0, 90, [try_stmt])
        root = MockNode("compilation_unit", 0, 90, [method])
        tree = MockTree(root)
        
        ctx = self._create_context("csharp", tree, "public string Test() {\n    try {\n        return \"try\";\n    } finally {\n        return \"finally\";\n    }\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("return", finding.message)

    def test_csharp_continue_in_finally(self):
        """Test detection of continue statement in C# finally block."""
        continue_stmt = MockNode("continue_statement", 95, 108)
        finally_block = MockNode("finally_clause", 85, 115, [continue_stmt])
        try_stmt = MockNode("try_statement", 55, 115, [finally_block])
        foreach_loop = MockNode("foreach_statement", 0, 115, [try_stmt])
        root = MockNode("compilation_unit", 0, 115, [foreach_loop])
        tree = MockTree(root)
        
        ctx = self._create_context("csharp", tree, "foreach (var item in items) {\n    try {\n        // code\n    } finally {\n        continue;\n    }\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("continue", finding.message)

    def test_multiple_control_flow_in_finally(self):
        """Test detection of multiple control flow statements in same finally block."""
        return_stmt = MockNode("return_statement", 50, 65)
        break_stmt = MockNode("break_statement", 70, 80)
        finally_block = MockNode("finally_clause", 40, 85, [return_stmt, break_stmt])
        try_stmt = MockNode("try_statement", 0, 85, [finally_block])
        root = MockNode("module", 0, 85, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    return 'done'\n    break")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 2)
        self.assertTrue(any("return" in f.message for f in findings))
        self.assertTrue(any("break" in f.message for f in findings))

    def test_nested_finally_blocks(self):
        """Test detection in nested try-finally blocks."""
        # Inner return in inner finally
        inner_return = MockNode("return_statement", 80, 95)
        inner_finally = MockNode("finally_clause", 70, 100, [inner_return])
        inner_try = MockNode("try_statement", 50, 100, [inner_finally])
        
        # Outer break in outer finally  
        outer_break = MockNode("break_statement", 110, 120)
        outer_finally = MockNode("finally_clause", 40, 125, [inner_try, outer_break])
        outer_try = MockNode("try_statement", 0, 125, [outer_finally])
        root = MockNode("module", 0, 125, [outer_try])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    try:\n        pass\n    finally:\n        return 'inner'\nfinally:\n    break")
        findings = self._create_findings_list(ctx)
        
        # Should find both control flow statements: inner return and outer break
        self.assertGreaterEqual(len(findings), 2)
        rule_ids = [f.rule for f in findings]
        self.assertTrue(all(rule_id == "errors.finally_control_flow" for rule_id in rule_ids))
        messages = [f.message for f in findings]
        self.assertTrue(any("return" in msg for msg in messages))
        self.assertTrue(any("break" in msg for msg in messages))

    # NEGATIVE TESTS - Should not detect control flow outside finally or safe operations

    def test_return_in_try_block(self):
        """Test that return in try block is not flagged."""
        return_stmt = MockNode("return_statement", 20, 35)
        try_block = MockNode("block", 15, 40, [return_stmt])
        finally_block = MockNode("finally_clause", 45, 60, [])
        try_stmt = MockNode("try_statement", 0, 60, [try_block, finally_block])
        root = MockNode("module", 0, 60, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    return 'safe'\nfinally:\n    cleanup()")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_return_in_except_block(self):
        """Test that return in except block is not flagged."""
        return_stmt = MockNode("return_statement", 35, 50)
        except_block = MockNode("except_clause", 25, 55, [return_stmt])
        finally_block = MockNode("finally_clause", 60, 75, [])
        try_stmt = MockNode("try_statement", 0, 75, [except_block, finally_block])
        root = MockNode("module", 0, 75, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    risky()\nexcept:\n    return 'error'\nfinally:\n    cleanup()")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_function_call_in_finally(self):
        """Test that function calls in finally are not flagged."""
        call_stmt = MockNode("expression_statement", 50, 70, [
            MockNode("call", 50, 70)
        ])
        finally_block = MockNode("finally_clause", 40, 75, [call_stmt])
        try_stmt = MockNode("try_statement", 0, 75, [finally_block])
        root = MockNode("module", 0, 75, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    cleanup()")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_assignment_in_finally(self):
        """Test that assignments in finally are not flagged."""
        assignment = MockNode("assignment", 50, 70)
        finally_block = MockNode("finally_clause", 40, 75, [assignment])
        try_stmt = MockNode("try_statement", 0, 75, [finally_block])
        root = MockNode("module", 0, 75, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    result = None")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_java_method_call_in_finally(self):
        """Test that Java method calls in finally are not flagged."""
        method_call = MockNode("method_invocation", 80, 100)
        expr_stmt = MockNode("expression_statement", 75, 105, [method_call])
        finally_block = MockNode("finally_clause", 70, 110, [expr_stmt])
        try_stmt = MockNode("try_statement", 0, 110, [finally_block])
        root = MockNode("program", 0, 110, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "try {\n    // code\n} finally {\n    cleanup();\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_csharp_using_statement_in_finally(self):
        """Test that C# using statements in finally are not flagged."""
        using_stmt = MockNode("using_statement", 70, 95)
        finally_block = MockNode("finally_clause", 60, 100, [using_stmt])
        try_stmt = MockNode("try_statement", 0, 100, [finally_block])
        root = MockNode("compilation_unit", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("csharp", tree, "try {\n    // code\n} finally {\n    using (var stream = new FileStream()) { }\n}")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_empty_finally_block(self):
        """Test that empty finally blocks are not flagged."""
        finally_block = MockNode("finally_clause", 40, 50, [])
        try_stmt = MockNode("try_statement", 0, 50, [finally_block])
        root = MockNode("module", 0, 50, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    pass")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_control_flow_outside_finally(self):
        """Test that control flow outside finally blocks is not flagged."""
        return_stmt = MockNode("return_statement", 80, 95)
        finally_block = MockNode("finally_clause", 40, 60, [])
        try_stmt = MockNode("try_statement", 0, 60, [finally_block])
        function_body = MockNode("block", 0, 100, [try_stmt, return_stmt])
        root = MockNode("module", 0, 100, [function_body])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "def test():\n    try:\n        pass\n    finally:\n        cleanup()\n    return 'done'")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    # EDGE CASES

    def test_unsupported_language(self):
        """Test that unsupported languages are ignored."""
        return_stmt = MockNode("return_statement", 50, 65)
        finally_block = MockNode("finally_clause", 40, 70, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 70, [finally_block])
        root = MockNode("source_file", 0, 70, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("go", tree, "// Go code with try-finally (hypothetical)")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_malformed_tree(self):
        """Test handling of malformed or missing tree structures."""
        ctx = self._create_context("python", None)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_empty_tree(self):
        """Test handling of empty syntax tree."""
        root = MockNode("module", 0, 0, [])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_node_without_type(self):
        """Test handling of nodes without type attribute."""
        # Create a node-like object without 'type' attribute
        class NodeWithoutType:
            def __init__(self):
                self.start_byte = 0
                self.end_byte = 10
                self.children = []
        
        node_without_type = NodeWithoutType()
        root = MockNode("module", 0, 10, [node_without_type])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "some code")
        findings = self._create_findings_list(ctx)
        
        # Should handle gracefully without throwing
        self.assertEqual(len(findings), 0)

    def test_finding_metadata(self):
        """Test that findings contain proper metadata."""
        return_stmt = MockNode("return_statement", 50, 65)
        finally_block = MockNode("finally_clause", 40, 70, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 70, [finally_block])
        root = MockNode("module", 0, 70, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    return 'done'")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        
        # Check metadata
        self.assertIsNotNone(finding.meta)
        self.assertEqual(finding.meta["language"], "python")
        self.assertEqual(finding.meta["control_flow_type"], "return")
        self.assertIn("suggestion", finding.meta)
        self.assertIn("finally_span", finding.meta)
        
        # Check finally span
        finally_span = finding.meta["finally_span"]
        self.assertEqual(finally_span["start"], 40)
        self.assertEqual(finally_span["end"], 70)

    def test_suggestion_content_python(self):
        """Test that Python suggestions contain helpful refactoring advice."""
        return_stmt = MockNode("return_statement", 50, 65)
        finally_block = MockNode("finally_clause", 40, 70, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 70, [finally_block])
        root = MockNode("module", 0, 70, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "try:\n    pass\nfinally:\n    return 'done'")
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain specific refactoring patterns
        self.assertIn("Solution 1:", suggestion)
        self.assertIn("Solution 2:", suggestion)
        self.assertIn("try:", suggestion)
        self.assertIn("finally:", suggestion)
        self.assertIn("cleanup()", suggestion)

    def test_suggestion_content_java(self):
        """Test that Java suggestions contain language-appropriate advice."""
        return_stmt = MockNode("return_statement", 80, 95)
        finally_block = MockNode("finally_clause", 70, 100, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 100, [finally_block])
        root = MockNode("program", 0, 100, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("java", tree, "try { } finally { return \"done\"; }")
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain Java-specific patterns
        self.assertIn("public", suggestion)
        self.assertIn("Exception", suggestion)
        self.assertIn("throw new RuntimeException", suggestion)
        self.assertIn("logger", suggestion)

    def test_suggestion_content_csharp(self):
        """Test that C# suggestions contain language-appropriate advice."""
        return_stmt = MockNode("return_statement", 70, 85)
        finally_block = MockNode("finally_clause", 60, 90, [return_stmt])
        try_stmt = MockNode("try_statement", 0, 90, [finally_block])
        root = MockNode("compilation_unit", 0, 90, [try_stmt])
        tree = MockTree(root)
        
        ctx = self._create_context("csharp", tree, "try { } finally { return \"done\"; }")
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain C#-specific patterns
        self.assertIn("using", suggestion)
        self.assertIn("_logger", suggestion)
        self.assertIn("LogError", suggestion)
        self.assertIn("AcquireResource", suggestion)


if __name__ == '__main__':
    unittest.main()

