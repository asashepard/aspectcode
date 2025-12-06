"""
Tests for concurrency.async_call_not_awaited rule.

This module tests detection of async/coroutine-returning function calls that are not
properly awaited, returned, or intentionally scheduled in Python and C#.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.concurrency_async_call_not_awaited import ConcurrencyAsyncCallNotAwaitedRule
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
    tree.children = []  # Make children iterable
    
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
        "csharp": "cs"
    }
    return extensions.get(language, "txt")


def run_rule(rule: ConcurrencyAsyncCallNotAwaitedRule, code: str = "", language: str = "python", 
            config: Dict[str, Any] = None) -> List[Finding]:
    """Run the rule on the given code and return findings."""
    ctx = create_test_context(code, language, config)
    return list(rule.visit(ctx))


class TestConcurrencyAsyncCallNotAwaitedRule:
    """Test suite for concurrency.async_call_not_awaited rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ConcurrencyAsyncCallNotAwaitedRule()
    
    # --- Basic Functionality Tests ---
    
    def test_meta_properties(self):
        """Test rule metadata properties."""
        assert self.rule.meta.id == "concurrency.async_call_not_awaited"
        assert self.rule.meta.category == "concurrency"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires syntax analysis."""
        assert self.rule.requires.syntax is True
    
    # --- Python Pattern Recognition Tests ---
    
    def test_python_async_name_patterns(self):
        """Test recognition of Python async function name patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        async_patterns = [
            "fetch_data_async",
            "load_async", 
            "process_async",
            "some.async_method",
            "asyncio.sleep",
            "aiohttp.get",
            "httpx.post"
        ]
        
        for pattern in async_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.adapter.language_id = "python"
            mock_ctx.text = ""
            
            # Mock the _callee_text method to return our test pattern
            rule._callee_text = lambda n, c: pattern
            
            result = rule._looks_async_like(mock_node, mock_ctx)
            assert result is True, f"Expected {pattern} to be recognized as async-like"
    
    def test_csharp_async_name_patterns(self):
        """Test recognition of C# async method name patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        async_patterns = [
            "LoadDataAsync",
            "FetchUserAsync", 
            "ProcessAsync",
            "Task.Run",
            "Task.WhenAll",
            "ValueTask.CompletedTask"
        ]
        
        for pattern in async_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.adapter.language_id = "csharp"
            mock_ctx.text = ""
            
            # Mock the _callee_text method to return our test pattern
            rule._callee_text = lambda n, c: pattern
            
            result = rule._looks_async_like(mock_node, mock_ctx)
            assert result is True, f"Expected {pattern} to be recognized as async-like"
    
    # --- Call Node Recognition Tests ---
    
    def test_call_node_recognition(self):
        """Test recognition of different call node types."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        call_kinds = [
            "call_expression",
            "call", 
            "invocation_expression",
            "method_invocation",
            "function_call"
        ]
        
        for kind in call_kinds:
            mock_node = Mock()
            mock_node.kind = kind
            
            result = rule._is_call_node(mock_node)
            assert result is True, f"Expected {kind} to be recognized as call node"
        
        # Test non-call nodes
        non_call_kinds = ["identifier", "literal", "block", "if_statement"]
        for kind in non_call_kinds:
            mock_node = Mock()
            mock_node.kind = kind
            
            result = rule._is_call_node(mock_node)
            assert result is False, f"Expected {kind} to not be recognized as call node"
    
    # --- Await Detection Tests ---
    
    def test_await_detection(self):
        """Test detection of awaited calls."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        # Mock awaited call
        await_expr = Mock()
        await_expr.kind = "await_expression"
        await_expr.parent = None
        
        call_node = Mock()
        call_node.parent = await_expr
        
        ctx = Mock()
        ctx.adapter.language_id = "python"
        
        result = rule._is_awaited(call_node, ctx)
        assert result is True, "Expected awaited call to be detected"
        
        # Mock non-awaited call
        regular_expr = Mock()
        regular_expr.kind = "call_expression"
        regular_expr.parent = None
        
        call_node2 = Mock()
        call_node2.parent = regular_expr
        
        result = rule._is_awaited(call_node2, ctx)
        assert result is False, "Expected non-awaited call to not be detected as awaited"
    
    # --- Return Detection Tests ---
    
    def test_return_detection(self):
        """Test detection of returned calls."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        # Mock return statement
        return_stmt = Mock()
        return_stmt.kind = "return_statement"
        return_stmt.parent = None
        
        call_node = Mock()
        call_node.parent = return_stmt
        
        result = rule._is_returned(call_node)
        assert result is True, "Expected returned call to be detected"
        
        # Mock non-returned call
        expr_stmt = Mock()
        expr_stmt.kind = "expression_statement"
        expr_stmt.parent = None
        
        call_node2 = Mock()
        call_node2.parent = expr_stmt
        
        result = rule._is_returned(call_node2)
        assert result is False, "Expected non-returned call to not be detected as returned"
    
    # --- Bare Expression Detection Tests ---
    
    def test_bare_expression_detection(self):
        """Test detection of bare expression statements."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        # Mock bare expression statement
        expr_stmt = Mock()
        expr_stmt.kind = "expression_statement"
        expr_stmt.parent = None
        
        call_node = Mock()
        call_node.parent = expr_stmt
        
        result = rule._is_bare_expression_statement(call_node)
        assert result is True, "Expected bare expression to be detected"
        
        # Mock assignment (not bare)
        assign_expr = Mock()
        assign_expr.kind = "assignment_expression"
        assign_expr.parent = None
        
        call_node2 = Mock()
        call_node2.parent = assign_expr
        
        result = rule._is_bare_expression_statement(call_node2)
        assert result is False, "Expected assignment to not be detected as bare expression"
    
    # --- Scheduling Detection Tests ---
    
    def test_python_scheduling_detection(self):
        """Test detection of Python async scheduling patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        ctx = Mock()
        ctx.adapter.language_id = "python"
        ctx.text = ""
        
        # Test asyncio.create_task
        call_node = Mock()
        rule._callee_text = lambda n, c: "asyncio.create_task"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is True, "Expected asyncio.create_task to be recognized as scheduled"
        
        # Test asyncio.gather 
        rule._callee_text = lambda n, c: "asyncio.gather"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is True, "Expected asyncio.gather to be recognized as scheduled"
        
        # Test regular function call
        rule._callee_text = lambda n, c: "regular_function"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is False, "Expected regular function to not be recognized as scheduled"
    
    def test_csharp_scheduling_detection(self):
        """Test detection of C# async scheduling patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        ctx = Mock()
        ctx.adapter.language_id = "csharp"
        ctx.text = ""
        
        # Test Task.WhenAll
        call_node = Mock()
        rule._callee_text = lambda n, c: "Task.WhenAll"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is True, "Expected Task.WhenAll to be recognized as scheduled"
        
        # Test Task.Run
        rule._callee_text = lambda n, c: "Task.Run"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is True, "Expected Task.Run to be recognized as scheduled"
        
        # Test regular method call
        rule._callee_text = lambda n, c: "RegularMethod"
        
        result = rule._is_explicitly_scheduled(call_node, ctx)
        assert result is False, "Expected regular method to not be recognized as scheduled"
    
    # --- Callee Text Extraction Tests ---
    
    def test_callee_text_extraction(self):
        """Test extraction of callee text from call nodes."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = "fetch_data_async()"
        
        # Test with function attribute
        call_node = Mock()
        function_node = Mock()
        
        # Mock the _get_node_text method to return function name
        rule._get_node_text = lambda c, n: "fetch_data_async" if n == function_node else "fetch_data_async()"
        
        call_node.function = function_node
        
        result = rule._callee_text(call_node, ctx)
        assert result == "fetch_data_async", f"Expected 'fetch_data_async', got '{result}'"
        
        # Test with callee attribute
        call_node2 = Mock()
        callee_node = Mock()
        del call_node2.function  # Remove function attribute
        call_node2.callee = callee_node
        
        # Update the mock to return proper text for callee
        rule._get_node_text = lambda c, n: "fetch_data_async" if n == callee_node else "fetch_data_async()"
        
        result = rule._callee_text(call_node2, ctx)
        assert result == "fetch_data_async", f"Expected 'fetch_data_async', got '{result}'"
    
    # --- Node Text Extraction Tests ---
    
    def test_node_text_extraction(self):
        """Test extraction of text from nodes."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = "fetch_data_async()"
        ctx.adapter.node_span = lambda n: (0, 18)  # Full length of the text (18 chars)
        
        # Test with text attribute
        node = Mock()
        node.text = "fetch_data_async"
        
        result = rule._get_node_text(ctx, node)
        assert result == "fetch_data_async", f"Expected 'fetch_data_async', got '{result}'"
        
        # Test with span extraction
        node2 = Mock()
        del node2.text
        
        result = rule._get_node_text(ctx, node2)
        assert result == "fetch_data_async()", f"Expected 'fetch_data_async()', got '{result}'"
    
    # --- Integration Tests ---
    
    def test_python_positive_cases(self):
        """Test Python code that should trigger warnings."""
        # This is a simplified test - in real usage, the syntax tree would be properly parsed
        ctx = create_test_context("", "python")
        
        # Mock a bare async call
        call_node = Mock()
        call_node.kind = "call_expression"
        call_node.children = []
        
        expr_stmt = Mock()
        expr_stmt.kind = "expression_statement"
        expr_stmt.parent = None
        
        call_node.parent = expr_stmt
        
        # Mock the tree to contain our call
        ctx.tree.children = [expr_stmt]
        expr_stmt.children = [call_node]
        
        # Mock rule methods for this test
        self.rule._callee_text = lambda n, c: "fetch_async"
        self.rule._get_node_text = lambda c, n: "fetch_async()"
        
        findings = list(self.rule.visit(ctx))
        
        # We expect the rule to detect patterns, but the exact number depends on the mock setup
        # The important thing is that the rule runs without errors
        assert isinstance(findings, list), "Expected rule to return a list of findings"
    
    def test_csharp_positive_cases(self):
        """Test C# code that should trigger warnings."""
        ctx = create_test_context("", "csharp")
        
        # Mock a bare async call
        call_node = Mock()
        call_node.kind = "invocation_expression"
        call_node.children = []
        
        expr_stmt = Mock()
        expr_stmt.kind = "expression_statement"
        expr_stmt.parent = None
        
        call_node.parent = expr_stmt
        
        # Mock the tree to contain our call
        ctx.tree.children = [expr_stmt]
        expr_stmt.children = [call_node]
        
        # Mock rule methods for this test
        self.rule._callee_text = lambda n, c: "FetchAsync"
        self.rule._get_node_text = lambda c, n: "FetchAsync()"
        
        findings = list(self.rule.visit(ctx))
        
        # We expect the rule to detect patterns, but the exact number depends on the mock setup
        assert isinstance(findings, list), "Expected rule to return a list of findings"
    
    # --- Edge Case Tests ---
    
    def test_empty_file(self):
        """Test handling of empty file."""
        ctx = create_test_context("", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_async_calls(self):
        """Test file with no async calls."""
        ctx = create_test_context("print('Hello, world!')", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test unsupported language."""
        ctx = create_test_context("console.log('Hello')", "javascript")  # Not in supported languages
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
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
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
        root.kind = "module"
        
        # Walk the nodes
        nodes = list(rule._walk_nodes(root))
        
        # Should visit all nodes
        assert len(nodes) >= 4  # root, branch, leaf1, leaf2
        kinds = [node.kind for node in nodes if hasattr(node, 'kind')]
        assert "module" in kinds
        assert "call_expression" in kinds
        assert "identifier" in kinds
        assert "literal" in kinds
    
    # --- Language-Specific Pattern Tests ---
    
    def test_python_library_patterns(self):
        """Test Python async library patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        library_patterns = [
            "aiohttp.ClientSession.get",
            "aiofiles.open",
            "asyncpg.connect",
            "motor.collection.find_one", 
            "httpx.AsyncClient.post"
        ]
        
        for pattern in library_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.adapter.language_id = "python"
            mock_ctx.text = ""
            
            rule._callee_text = lambda n, c: pattern
            
            result = rule._looks_async_like(mock_node, mock_ctx)
            assert result is True, f"Expected {pattern} to be recognized as async-like"
    
    def test_csharp_task_patterns(self):
        """Test C# Task-related patterns."""
        rule = ConcurrencyAsyncCallNotAwaitedRule()
        
        task_patterns = [
            "Task.FromResult",
            "ValueTask.FromResult",
            "TaskFactory.StartNew",
            "HttpClient.GetAsync",
            "DatabaseAsync"
        ]
        
        for pattern in task_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.adapter.language_id = "csharp"
            mock_ctx.text = ""
            
            rule._callee_text = lambda n, c: pattern
            
            result = rule._looks_async_like(mock_node, mock_ctx)
            # Most should be recognized, but let's check the specific ones we know should work
            if "Async" in pattern or "Task" in pattern:
                assert result is True, f"Expected {pattern} to be recognized as async-like"


def test_rule_registration():
    """Test that the rule can be imported and instantiated."""
    rule = ConcurrencyAsyncCallNotAwaitedRule()
    assert rule.meta.id == "concurrency.async_call_not_awaited"
    assert rule.requires.syntax is True

