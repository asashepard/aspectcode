# server/tests/test_errors_partial_function_implementation.py
"""
Tests for the errors.partial_function_implementation rule.

This module tests the detection of functions/methods with placeholder
implementations across multiple programming languages.
"""

import unittest
from unittest.mock import Mock
from typing import List, Optional

from rules.errors_partial_function_implementation import ErrorsPartialFunctionImplementationRule
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


class TestErrorsPartialFunctionImplementationRule(unittest.TestCase):
    """Test cases for ErrorsPartialFunctionImplementationRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = ErrorsPartialFunctionImplementationRule()

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
            "typescript": "ts",
            "javascript": "js",
            "go": "go",
            "java": "java",
            "cpp": "cpp",
            "c": "c",
            "csharp": "cs",
            "ruby": "rb",
            "rust": "rs",
            "swift": "swift"
        }
        return extensions.get(language, "txt")

    def _create_findings_list(self, ctx: RuleContext) -> List[Finding]:
        """Helper to convert generator to list."""
        return list(self.rule.visit(ctx))

    def _create_function_with_placeholder(self, language: str, func_name: str = "test_func", 
                                        placeholder_text: str = "raise NotImplementedError") -> MockTree:
        """Create a mock function with a placeholder implementation."""
        # Create placeholder statement
        if language == "python":
            placeholder = MockNode("raise_statement", 30, 50, [], placeholder_text)
        elif language in ["typescript", "javascript"]:
            placeholder = MockNode("throw_statement", 30, 50, [], placeholder_text)
        elif language == "go":
            placeholder = MockNode("call_expression", 30, 50, [], placeholder_text)
        elif language == "java":
            placeholder = MockNode("throw_statement", 30, 50, [], placeholder_text)
        elif language == "csharp":
            placeholder = MockNode("throw_statement", 30, 50, [], placeholder_text)
        elif language in ["c", "cpp"]:
            placeholder = MockNode("expression_statement", 30, 50, [], placeholder_text)
        elif language == "ruby":
            placeholder = MockNode("raise_statement", 30, 50, [], placeholder_text)
        elif language == "rust":
            placeholder = MockNode("macro_invocation", 30, 50, [], placeholder_text)
        elif language == "swift":
            placeholder = MockNode("call_expression", 30, 50, [], placeholder_text)
        else:
            placeholder = MockNode("expression_statement", 30, 50, [], placeholder_text)

        # Create function body
        func_body = MockNode("block", 25, 55, [placeholder])
        
        # Create function name identifier
        func_identifier = MockNode("identifier", 10, 20, [], func_name)
        
        # Create function node
        if language == "python":
            func_node = MockNode("function_definition", 0, 60, [func_identifier, func_body])
        elif language in ["typescript", "javascript"]:
            func_node = MockNode("function_declaration", 0, 60, [func_identifier, func_body])
        elif language == "go":
            func_node = MockNode("function_declaration", 0, 60, [func_identifier, func_body])
        elif language == "java":
            func_node = MockNode("method_declaration", 0, 60, [func_identifier, func_body])
        elif language == "csharp":
            func_node = MockNode("method_declaration", 0, 60, [func_identifier, func_body])
        elif language in ["c", "cpp"]:
            func_node = MockNode("function_definition", 0, 60, [func_identifier, func_body])
        elif language == "ruby":
            func_node = MockNode("method", 0, 60, [func_identifier, func_body])
        elif language == "rust":
            func_node = MockNode("function_item", 0, 60, [func_identifier, func_body])
        elif language == "swift":
            func_node = MockNode("function_declaration", 0, 60, [func_identifier, func_body])
        else:
            func_node = MockNode("function_definition", 0, 60, [func_identifier, func_body])

        # Create root node
        root = MockNode("source_file", 0, 65, [func_node])
        return MockTree(root)

    def _create_function_with_implementation(self, language: str, func_name: str = "test_func") -> MockTree:
        """Create a mock function with actual implementation."""
        # Create multiple statements for real implementation
        stmt1 = MockNode("expression_statement", 30, 40, [], "x = 1")
        stmt2 = MockNode("return_statement", 45, 55, [], "return x")
        
        # Create function body with multiple statements
        func_body = MockNode("block", 25, 60, [stmt1, stmt2])
        
        # Create function name identifier
        func_identifier = MockNode("identifier", 10, 20, [], func_name)
        
        # Create function node
        if language == "python":
            func_node = MockNode("function_definition", 0, 65, [func_identifier, func_body])
        elif language in ["typescript", "javascript"]:
            func_node = MockNode("function_declaration", 0, 65, [func_identifier, func_body])
        elif language == "go":
            func_node = MockNode("function_declaration", 0, 65, [func_identifier, func_body])
        elif language == "java":
            func_node = MockNode("method_declaration", 0, 65, [func_identifier, func_body])
        elif language == "csharp":
            func_node = MockNode("method_declaration", 0, 65, [func_identifier, func_body])
        elif language in ["c", "cpp"]:
            func_node = MockNode("function_definition", 0, 65, [func_identifier, func_body])
        elif language == "ruby":
            func_node = MockNode("method", 0, 65, [func_identifier, func_body])
        elif language == "rust":
            func_node = MockNode("function_item", 0, 65, [func_identifier, func_body])
        elif language == "swift":
            func_node = MockNode("function_declaration", 0, 65, [func_identifier, func_body])
        else:
            func_node = MockNode("function_definition", 0, 65, [func_identifier, func_body])

        # Create root node
        root = MockNode("source_file", 0, 70, [func_node])
        return MockTree(root)

    # POSITIVE TESTS - Should detect placeholder implementations

    def test_python_not_implemented_error(self):
        """Test detection of Python NotImplementedError placeholder."""
        tree = self._create_function_with_placeholder("python", "process_data", "raise NotImplementedError")
        file_text = """def process_data(data):
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.rule, "errors.partial_function_implementation")
        self.assertIn("process_data", finding.message)
        self.assertIn("placeholder implementation", finding.message)
        self.assertEqual(finding.severity, "info")

    def test_java_unsupported_operation_exception(self):
        """Test detection of Java UnsupportedOperationException placeholder."""
        tree = self._create_function_with_placeholder("java", "processData", "throw new UnsupportedOperationException()")
        file_text = """public void processData() {
    throw new UnsupportedOperationException();
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)
        self.assertIn("placeholder implementation", finding.message)

    def test_rust_unimplemented_macro(self):
        """Test detection of Rust unimplemented!() placeholder."""
        tree = self._create_function_with_placeholder("rust", "process_data", "unimplemented!()")
        file_text = """fn process_data() {
    unimplemented!();
}"""
        
        ctx = self._create_context("rust", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("process_data", finding.message)

    def test_typescript_throw_error(self):
        """Test detection of TypeScript throw Error placeholder."""
        tree = self._create_function_with_placeholder("typescript", "processData", 'throw new Error("not implemented")')
        file_text = """function processData() {
    throw new Error("not implemented");
}"""
        
        ctx = self._create_context("typescript", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)

    def test_javascript_throw_error(self):
        """Test detection of JavaScript throw Error placeholder."""
        tree = self._create_function_with_placeholder("javascript", "processData", 'throw new Error("unimplemented")')
        file_text = """function processData() {
    throw new Error("unimplemented");
}"""
        
        ctx = self._create_context("javascript", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)

    def test_go_panic_placeholder(self):
        """Test detection of Go panic placeholder."""
        tree = self._create_function_with_placeholder("go", "processData", 'panic("not implemented")')
        file_text = """func processData() {
    panic("not implemented")
}"""
        
        ctx = self._create_context("go", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)

    def test_csharp_not_implemented_exception(self):
        """Test detection of C# NotImplementedException placeholder."""
        tree = self._create_function_with_placeholder("csharp", "ProcessData", "throw new NotImplementedException()")
        file_text = """public void ProcessData() {
    throw new NotImplementedException();
}"""
        
        ctx = self._create_context("csharp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("ProcessData", finding.message)

    def test_c_abort_placeholder(self):
        """Test detection of C abort() placeholder."""
        tree = self._create_function_with_placeholder("c", "process_data", "abort()")
        file_text = """void process_data() {
    abort();
}"""
        
        ctx = self._create_context("c", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("process_data", finding.message)

    def test_cpp_abort_placeholder(self):
        """Test detection of C++ abort() placeholder."""
        tree = self._create_function_with_placeholder("cpp", "processData", "std::abort()")
        file_text = """void processData() {
    std::abort();
}"""
        
        ctx = self._create_context("cpp", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)

    def test_ruby_not_implemented_error(self):
        """Test detection of Ruby NotImplementedError placeholder."""
        tree = self._create_function_with_placeholder("ruby", "process_data", "raise NotImplementedError")
        file_text = """def process_data
  raise NotImplementedError
end"""
        
        ctx = self._create_context("ruby", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("process_data", finding.message)

    def test_swift_fatal_error(self):
        """Test detection of Swift fatalError placeholder."""
        tree = self._create_function_with_placeholder("swift", "processData", 'fatalError("unimplemented")')
        file_text = """func processData() {
    fatalError("unimplemented")
}"""
        
        ctx = self._create_context("swift", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("processData", finding.message)

    def test_rust_todo_macro(self):
        """Test detection of Rust todo!() placeholder."""
        tree = self._create_function_with_placeholder("rust", "process_data", "todo!()")
        file_text = """fn process_data() {
    todo!();
}"""
        
        ctx = self._create_context("rust", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("process_data", finding.message)

    # NEGATIVE TESTS - Should not detect real implementations

    def test_python_real_implementation(self):
        """Test that Python functions with real implementation are not flagged."""
        tree = self._create_function_with_implementation("python", "process_data")
        file_text = """def process_data(data):
    x = 1
    return x"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_java_real_implementation(self):
        """Test that Java methods with real implementation are not flagged."""
        tree = self._create_function_with_implementation("java", "processData")
        file_text = """public int processData() {
    int x = 1;
    return x;
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_rust_real_implementation(self):
        """Test that Rust functions with real implementation are not flagged."""
        tree = self._create_function_with_implementation("rust", "process_data")
        file_text = """fn process_data() {
    let x = 1;
    x
}"""
        
        ctx = self._create_context("rust", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_multiple_statements_with_placeholder(self):
        """Test that functions with placeholder plus other statements are not flagged."""
        # Create function with multiple statements including a placeholder
        stmt1 = MockNode("expression_statement", 30, 40, [], "log.info('called')")
        stmt2 = MockNode("raise_statement", 45, 65, [], "raise NotImplementedError")
        
        func_body = MockNode("block", 25, 70, [stmt1, stmt2])
        func_identifier = MockNode("identifier", 10, 20, [], "process_data")
        func_node = MockNode("function_definition", 0, 75, [func_identifier, func_body])
        root = MockNode("source_file", 0, 80, [func_node])
        tree = MockTree(root)
        
        file_text = """def process_data(data):
    log.info('called')
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        # Should not flag because it has multiple statements
        self.assertEqual(len(findings), 0)

    def test_conditional_placeholder(self):
        """Test that conditional placeholders are not flagged."""
        # Create function with if statement containing placeholder
        placeholder = MockNode("raise_statement", 50, 70, [], "raise NotImplementedError")
        if_stmt = MockNode("if_statement", 30, 75, [placeholder])
        
        func_body = MockNode("block", 25, 80, [if_stmt])
        func_identifier = MockNode("identifier", 10, 20, [], "process_data")
        func_node = MockNode("function_definition", 0, 85, [func_identifier, func_body])
        root = MockNode("source_file", 0, 90, [func_node])
        tree = MockTree(root)
        
        file_text = """def process_data(data):
    if not feature_flag:
        raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        # Should not flag because placeholder is conditional
        self.assertEqual(len(findings), 0)

    def test_empty_function(self):
        """Test that empty functions are not flagged."""
        # Create function with empty body
        func_body = MockNode("block", 25, 30, [])
        func_identifier = MockNode("identifier", 10, 20, [], "empty_func")
        func_node = MockNode("function_definition", 0, 35, [func_identifier, func_body])
        root = MockNode("source_file", 0, 40, [func_node])
        tree = MockTree(root)
        
        file_text = """def empty_func():
    pass"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_abstract_method_declaration(self):
        """Test that abstract method declarations are not flagged."""
        # This would typically be a method without a body in an interface/abstract class
        func_identifier = MockNode("identifier", 10, 20, [], "process_data")
        func_node = MockNode("method_declaration", 0, 25, [func_identifier])  # No body
        root = MockNode("source_file", 0, 30, [func_node])
        tree = MockTree(root)
        
        file_text = """abstract void processData();"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        # Should not flag abstract declarations
        self.assertEqual(len(findings), 0)

    # EDGE CASES

    def test_unsupported_language(self):
        """Test that unsupported languages are ignored."""
        tree = self._create_function_with_placeholder("unknown", "test_func", "placeholder")
        
        ctx = self._create_context("unknown", tree, "// Unknown language")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_malformed_tree(self):
        """Test handling of malformed or missing tree structures."""
        ctx = self._create_context("python", None)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_empty_tree(self):
        """Test handling of empty syntax tree."""
        root = MockNode("source_file", 0, 0, [])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "")
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 0)

    def test_function_without_body(self):
        """Test handling of function nodes without body."""
        func_identifier = MockNode("identifier", 10, 20, [], "test_func")
        func_node = MockNode("function_definition", 0, 25, [func_identifier])  # No body
        root = MockNode("source_file", 0, 30, [func_node])
        tree = MockTree(root)
        
        ctx = self._create_context("python", tree, "def test_func(): ...")
        findings = self._create_findings_list(ctx)
        
        # Should handle gracefully without throwing
        self.assertEqual(len(findings), 0)

    def test_finding_metadata(self):
        """Test that findings contain proper metadata."""
        tree = self._create_function_with_placeholder("python", "process_data", "raise NotImplementedError")
        file_text = """def process_data(data):
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        
        # Check metadata
        self.assertIsNotNone(finding.meta)
        self.assertEqual(finding.meta["language"], "python")
        self.assertEqual(finding.meta["function_name"], "process_data")
        self.assertIn("suggestion", finding.meta)
        self.assertIn("placeholder_type", finding.meta)
        self.assertIn("placeholder_span", finding.meta)

    def test_suggestion_content_python(self):
        """Test that Python suggestions contain helpful refactoring advice."""
        tree = self._create_function_with_placeholder("python", "process_data", "raise NotImplementedError")
        file_text = """def process_data(data):
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain specific refactoring patterns
        self.assertIn("Option 1:", suggestion)
        self.assertIn("Option 2:", suggestion)
        self.assertIn("def process_data", suggestion)
        self.assertIn("abstractmethod", suggestion)

    def test_suggestion_content_java(self):
        """Test that Java suggestions contain language-appropriate advice."""
        tree = self._create_function_with_placeholder("java", "processData", "throw new UnsupportedOperationException()")
        file_text = """public void processData() {
    throw new UnsupportedOperationException();
}"""
        
        ctx = self._create_context("java", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain Java-specific patterns
        self.assertIn("public", suggestion)
        self.assertIn("abstract", suggestion)
        self.assertIn("List<String>", suggestion)
        self.assertIn("UnsupportedOperationException", suggestion)

    def test_suggestion_content_rust(self):
        """Test that Rust suggestions contain language-appropriate advice."""
        tree = self._create_function_with_placeholder("rust", "process_data", "unimplemented!()")
        file_text = """fn process_data() {
    unimplemented!();
}"""
        
        ctx = self._create_context("rust", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        finding = findings[0]
        suggestion = finding.meta["suggestion"]
        
        # Should contain Rust-specific patterns
        self.assertIn("todo!", suggestion)
        self.assertIn("trait", suggestion)
        self.assertIn("Result<", suggestion)
        self.assertIn("unimplemented!", suggestion)

    def test_function_name_extraction(self):
        """Test that function names are correctly extracted."""
        tree = self._create_function_with_placeholder("python", "my_special_function", "raise NotImplementedError")
        file_text = """def my_special_function(data):
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertIn("my_special_function", finding.message)
        self.assertEqual(finding.meta["function_name"], "my_special_function")

    def test_function_without_name(self):
        """Test handling of functions without identifiable names."""
        # Create function without proper identifier
        placeholder = MockNode("raise_statement", 30, 50, [], "raise NotImplementedError")
        func_body = MockNode("block", 25, 55, [placeholder])
        func_node = MockNode("function_definition", 0, 60, [func_body])  # No identifier
        root = MockNode("source_file", 0, 65, [func_node])
        tree = MockTree(root)
        
        file_text = """def():
    raise NotImplementedError"""
        
        ctx = self._create_context("python", tree, file_text)
        findings = self._create_findings_list(ctx)
        
        self.assertEqual(len(findings), 1)
        finding = findings[0]
        # Should handle gracefully without function name
        self.assertIn("Function has placeholder implementation", finding.message)


if __name__ == '__main__':
    unittest.main()

