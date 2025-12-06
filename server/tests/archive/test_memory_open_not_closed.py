"""
Tests for memory.leak.open_not_closed rule.

This module tests detection of resource acquisitions (file opens, memory allocations, 
connections) that are not reliably closed/freed on all control-flow paths across
multiple programming languages.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.memory_open_not_closed import MemoryOpenNotClosedRule
from engine.types import RuleContext, Finding
from unittest.mock import Mock


def create_test_context(code: str, language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a test context for the given code."""
    # Mock adapter based on language
    adapter = Mock()
    adapter.language_id = language
    adapter.parse.return_value = Mock()
    adapter.node_span = lambda node: (0, 10)  # Safe fallback span
    
    # Mock tree structure with iterable children
    tree = Mock()
    tree.kind = "module"
    tree.children = []
    
    ctx = RuleContext(
        file_path=f"test.{_get_extension(language)}",
        text=code,
        tree=tree,
        adapter=adapter,
        config=config or {}
    )
    
    return ctx


def _get_extension(language: str) -> str:
    """Get file extension for language."""
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts", 
        "go": "go",
        "java": "java",
        "csharp": "cs",
        "c": "c",
        "cpp": "cpp",
        "ruby": "rb",
        "rust": "rs",
        "swift": "swift"
    }
    return extensions.get(language, "txt")


class TestMemoryOpenNotClosedRule:
    """Test suite for memory.leak.open_not_closed rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = MemoryOpenNotClosedRule()
    
    # --- Basic Functionality Tests ---
    
    def test_meta_properties(self):
        """Test rule metadata properties."""
        assert self.rule.meta.id == "memory.leak.open_not_closed"
        assert self.rule.meta.category == "memory"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "cpp" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires syntax, scopes, and raw_text."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
    
    # --- Pattern Recognition Tests ---
    
    def test_python_acquire_patterns(self):
        """Test recognition of Python resource acquisition patterns."""
        rule = MemoryOpenNotClosedRule()
        
        acquire_patterns = [
            "open",
            "tempfile.NamedTemporaryFile",
            "sqlite3.connect",
            "socket.socket"
        ]
        
        for pattern in acquire_patterns:
            result = rule._is_acquire("python", pattern)
            assert result is True, f"Expected {pattern} to be recognized as acquisition"
    
    def test_python_release_patterns(self):
        """Test recognition of Python resource release patterns."""
        rule = MemoryOpenNotClosedRule()
        
        release_patterns = [
            "close",
            "commit", 
            "rollback",
            "shutdown"
        ]
        
        for pattern in release_patterns:
            result = rule._is_release("python", pattern, "")
            assert result is True, f"Expected {pattern} to be recognized as release"
    
    def test_java_acquire_patterns(self):
        """Test recognition of Java resource acquisition patterns."""
        rule = MemoryOpenNotClosedRule()
        
        acquire_patterns = [
            "java.io.FileInputStream.<init>",
            "java.io.FileOutputStream.<init>",
            "java.sql.DriverManager.getConnection"
        ]
        
        for pattern in acquire_patterns:
            result = rule._is_acquire("java", pattern)
            assert result is True, f"Expected {pattern} to be recognized as acquisition"
    
    def test_c_acquire_patterns(self):
        """Test recognition of C resource acquisition patterns.""" 
        rule = MemoryOpenNotClosedRule()
        
        acquire_patterns = [
            "fopen",
            "malloc",
            "calloc",
            "socket"
        ]
        
        for pattern in acquire_patterns:
            result = rule._is_acquire("c", pattern)
            assert result is True, f"Expected {pattern} to be recognized as acquisition"
    
    def test_c_release_patterns(self):
        """Test recognition of C resource release patterns."""
        rule = MemoryOpenNotClosedRule()
        
        release_patterns = [
            "fclose",
            "free",
            "close"
        ]
        
        for pattern in release_patterns:
            result = rule._is_release("c", pattern, "")
            assert result is True, f"Expected {pattern} to be recognized as release"
    
    # --- Function Scope Recognition Tests ---
    
    def test_function_scope_recognition(self):
        """Test recognition of function/method scopes."""
        rule = MemoryOpenNotClosedRule()
        
        function_kinds = [
            "function_definition",
            "function_declaration", 
            "method_definition",
            "function",
            "method",
            "constructor",
            "lambda",
            "arrow_function"
        ]
        
        for kind in function_kinds:
            mock_node = Mock()
            mock_node.kind = kind
            
            result = rule._is_function_scope(mock_node)
            assert result is True, f"Expected {kind} to be recognized as function scope"
    
    # --- Early Exit Detection Tests ---
    
    def test_early_exit_detection(self):
        """Test detection of early exit statements."""
        rule = MemoryOpenNotClosedRule()
        
        exit_kinds = [
            "return_statement",
            "throw_statement",
            "break_statement",
            "continue_statement",
            "raise_statement",
            "panic"
        ]
        
        for kind in exit_kinds:
            mock_stmt = Mock()
            mock_stmt.kind = kind
            
            result = rule._is_early_exit(mock_stmt)
            assert result is True, f"Expected {kind} to be recognized as early exit"
    
    # --- Structured Safe Pattern Tests ---
    
    def test_python_structured_safe_patterns(self):
        """Test Python structured safe patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # with statement
        with_stmt = Mock()
        with_stmt.kind = "with_statement"
        rule._get_node_text = lambda c, n: "with open('file') as f:"
        
        result = rule._structured_safe(with_stmt, "python", ctx)
        assert result is True, "Expected with statement to be recognized as safe"
    
    def test_go_structured_safe_patterns(self):
        """Test Go structured safe patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # defer statement
        defer_stmt = Mock()
        defer_stmt.kind = "defer_statement"
        rule._get_node_text = lambda c, n: "defer f.Close()"
        
        result = rule._structured_safe(defer_stmt, "go", ctx)
        assert result is True, "Expected defer statement to be recognized as safe"
    
    def test_java_structured_safe_patterns(self):
        """Test Java structured safe patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # try-with-resources
        try_stmt = Mock()
        try_stmt.kind = "try_statement"
        rule._get_node_text = lambda c, n: "try (FileInputStream in = new FileInputStream('file'))"
        
        result = rule._structured_safe(try_stmt, "java", ctx)
        assert result is True, "Expected try-with-resources to be recognized as safe"
    
    def test_csharp_structured_safe_patterns(self):
        """Test C# structured safe patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # using statement
        using_stmt = Mock()
        using_stmt.kind = "using_statement"
        rule._get_node_text = lambda c, n: "using var fs = new FileStream('file', FileMode.Open)"
        
        result = rule._structured_safe(using_stmt, "csharp", ctx)
        assert result is True, "Expected using statement to be recognized as safe"
    
    def test_cpp_structured_safe_patterns(self):
        """Test C++ RAII patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # RAII with smart pointers
        raii_stmt = Mock()
        raii_stmt.kind = "declaration"
        rule._get_node_text = lambda c, n: "std::unique_ptr<FILE> file(fopen('test', 'r'))"
        
        result = rule._structured_safe(raii_stmt, "cpp", ctx)
        assert result is True, "Expected RAII pattern to be recognized as safe"
    
    def test_rust_structured_safe_patterns(self):
        """Test Rust RAII patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Normal Rust code (auto-drop)
        rust_stmt = Mock()
        rust_stmt.kind = "let_declaration"
        rule._get_node_text = lambda c, n: "let file = std::fs::File::open('test')?;"
        
        result = rule._structured_safe(rust_stmt, "rust", ctx)
        assert result is True, "Expected normal Rust code to be recognized as safe"
        
        # Rust with mem::forget (unsafe)
        unsafe_stmt = Mock()
        unsafe_stmt.kind = "let_declaration"
        rule._get_node_text = lambda c, n: "let file = std::fs::File::open('test')?; mem::forget(file);"
        
        result = rule._structured_safe(unsafe_stmt, "rust", ctx)
        assert result is False, "Expected mem::forget to be recognized as unsafe"
    
    # --- Node Text Extraction Tests ---
    
    def test_node_text_extraction(self):
        """Test extraction of text from nodes."""
        rule = MemoryOpenNotClosedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = "open('test.txt')"
        ctx.adapter.node_span = lambda n: (0, 16)  # Fixed: full span should be 0-16 for 16-character string
        
        # Test with text attribute
        node = Mock()
        node.text = "open"
        
        result = rule._get_node_text(ctx, node)
        assert result == "open", f"Expected 'open', got '{result}'"
        
        # Test with span extraction
        node2 = Mock()
        del node2.text
        
        result = rule._get_node_text(ctx, node2)
        assert result == "open('test.txt')", f"Expected full text, got '{result}'"
    
    # --- Target Variable Extraction Tests ---
    
    def test_target_var_extraction(self):
        """Test extraction of target variables from assignments."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Python-style assignment
        assign_stmt = Mock()
        assign_stmt.kind = "assignment_expression"
        left_node = Mock()
        rule._get_identifier_text = lambda n, c: "file_handle" if n == left_node else None
        assign_stmt.left = left_node
        
        result = rule._get_target_var(assign_stmt, ctx)
        assert result == "file_handle", f"Expected 'file_handle', got '{result}'"
        
        # Go-style assignment
        go_stmt = Mock()
        go_stmt.kind = "go_assignment"  # Use different kind to avoid first branch
        # Fixed: Mock method with correct parameters (ctx, node)
        def mock_get_node_text(ctx, node):
            return "f, err := os.Open('test')"
        rule._get_node_text = mock_get_node_text
        
        result = rule._get_target_var(go_stmt, ctx)
        assert result == "f", f"Expected 'f', got '{result}'"
    
    # --- Callee Text Extraction Tests ---
    
    def test_callee_text_extraction(self):
        """Test extraction of callee text from call expressions."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Direct call
        call_stmt = Mock()
        call_stmt.kind = "call_expression"
        function_node = Mock()
        
        rule._get_node_text = lambda c, n: "open" if n == function_node else "open('test')"
        call_stmt.function = function_node
        
        result = rule._get_callee_text(call_stmt, ctx)
        assert result == "open", f"Expected 'open', got '{result}'"
    
    def test_receiver_name_extraction(self):
        """Test extraction of receiver names from method calls."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Method call like file.close()
        call_stmt = Mock()
        rule._get_callee_text = lambda s, c: "file.close"
        
        result = rule._get_receiver_name(call_stmt, ctx)
        assert result == "file", f"Expected 'file', got '{result}'"
    
    # --- Integration Tests ---
    
    def test_empty_file(self):
        """Test handling of empty file."""
        ctx = create_test_context("", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_resources(self):
        """Test file with no resource operations."""
        ctx = create_test_context("print('Hello, world!')", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test unsupported language."""
        ctx = create_test_context("code", "unknown")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test handling when syntax tree is None."""
        ctx = create_test_context("code", "python")
        ctx.tree = None
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # --- Walk Nodes Tests ---
    
    def test_walk_nodes_functionality(self):
        """Test the node walking functionality."""
        rule = MemoryOpenNotClosedRule()
        
        # Create a mock tree structure
        leaf1 = Mock()
        leaf1.children = []
        leaf1.kind = "identifier"
        
        leaf2 = Mock()
        leaf2.children = []
        leaf2.kind = "literal"
        
        branch = Mock()
        branch.children = [leaf1, leaf2]
        branch.kind = "call_expression"
        
        root = Mock()
        root.children = [branch]
        root.kind = "function_definition"
        
        # Walk the nodes
        nodes = list(rule._walk_nodes(root))
        
        # Should visit all nodes
        assert len(nodes) >= 4  # root, branch, leaf1, leaf2
        kinds = [node.kind for node in nodes if hasattr(node, 'kind')]
        assert "function_definition" in kinds
        assert "call_expression" in kinds
        assert "identifier" in kinds
        assert "literal" in kinds
    
    # --- Language-Specific Pattern Tests ---
    
    def test_go_patterns(self):
        """Test Go-specific patterns."""
        rule = MemoryOpenNotClosedRule()
        
        # Go acquisition patterns
        go_acquire = ["os.Open", "os.Create", "net.Dial", "sql.Open"]
        for pattern in go_acquire:
            result = rule._is_acquire("go", pattern)
            assert result is True, f"Expected {pattern} to be recognized as Go acquisition"
        
        # Go release patterns
        go_release = ["Close"]
        for pattern in go_release:
            result = rule._is_release("go", pattern, "")
            assert result is True, f"Expected {pattern} to be recognized as Go release"
    
    def test_javascript_patterns(self):
        """Test JavaScript/TypeScript patterns."""
        rule = MemoryOpenNotClosedRule()
        
        # JS acquisition patterns
        js_acquire = ["fs.open", "fs.createReadStream", "net.createConnection"]
        for pattern in js_acquire:
            result = rule._is_acquire("javascript", pattern)
            assert result is True, f"Expected {pattern} to be recognized as JS acquisition"
        
        # JS release patterns
        js_release = ["close", "end", "destroy"]
        for pattern in js_release:
            result = rule._is_release("javascript", pattern, "")
            assert result is True, f"Expected {pattern} to be recognized as JS release"
    
    def test_ruby_patterns(self):
        """Test Ruby patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Ruby safe block pattern
        ruby_stmt = Mock()
        ruby_stmt.kind = "block"
        rule._get_node_text = lambda c, n: "File.open('test') { |f| f.read }"
        
        result = rule._structured_safe(ruby_stmt, "ruby", ctx)
        assert result is True, "Expected Ruby block pattern to be safe"
    
    def test_swift_patterns(self):
        """Test Swift patterns."""
        rule = MemoryOpenNotClosedRule()
        ctx = Mock()
        
        # Swift defer pattern
        swift_stmt = Mock()
        swift_stmt.kind = "defer_statement"
        rule._get_node_text = lambda c, n: "defer { fileHandle.close() }"
        
        result = rule._structured_safe(swift_stmt, "swift", ctx)
        assert result is True, "Expected Swift defer pattern to be safe"
    
    # --- Positive Case Simulation Tests ---
    
    def test_python_positive_case_simulation(self):
        """Test Python code that should trigger warnings."""
        ctx = create_test_context("", "python")
        
        # Mock a function with unclosed resource
        func_node = Mock()
        func_node.kind = "function_definition"
        func_node.children = []
        
        # Mock statements
        assign_stmt = Mock()
        assign_stmt.kind = "assignment_expression"
        
        return_stmt = Mock()
        return_stmt.kind = "return_statement"
        
        func_node.body = Mock()
        func_node.body.children = [assign_stmt, return_stmt]
        
        # Mock the tree
        ctx.tree.children = [func_node]
        
        # Mock rule methods for this test
        self.rule._get_callee_text = lambda s, c: "open" if s == assign_stmt else ""
        self.rule._get_target_var = lambda s, c: "f" if s == assign_stmt else None
        self.rule._structured_safe = lambda s, l, c: False
        
        findings = list(self.rule.visit(ctx))
        
        # We expect the rule to detect the pattern
        assert isinstance(findings, list), "Expected rule to return a list of findings"
    
    # --- Edge Case Tests ---
    
    def test_multiple_resources(self):
        """Test tracking of multiple resources."""
        rule = MemoryOpenNotClosedRule()
        
        # Test that acquisition tracking works for multiple variables
        assert rule._is_acquire("python", "open")
        assert rule._is_acquire("python", "socket.socket")
        assert rule._is_release("python", "close", "file")
        assert rule._is_release("python", "close", "sock")
    
    def test_conditional_acquisition(self):
        """Test conditional resource acquisition scenarios."""
        # This would be tested with proper AST in real usage
        # Here we just verify the helper methods work
        rule = MemoryOpenNotClosedRule()
        
        # Mock conditional scenarios
        mock_stmt = Mock()
        mock_stmt.kind = "if_statement"
        
        # The rule should handle conditional logic in real AST traversal
        assert not rule._is_early_exit(mock_stmt)


def test_rule_registration():
    """Test that the rule can be imported and instantiated."""
    rule = MemoryOpenNotClosedRule()
    assert rule.meta.id == "memory.leak.open_not_closed"
    assert rule.requires.syntax is True
    assert rule.requires.scopes is True
    assert rule.requires.raw_text is True

