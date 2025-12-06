"""
Tests for concurrency.promise_not_awaited rule.

This module tests detection of Promise-returning calls that are not properly
awaited, then/catch-handled, or returned in JavaScript and TypeScript.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.concurrency_promise_not_awaited import ConcurrencyPromiseNotAwaitedRule
from engine.types import RuleContext, Finding
from unittest.mock import Mock


def create_test_context(code: str, language: str = "javascript", config: Dict[str, Any] = None) -> RuleContext:
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
        "javascript": "js",
        "typescript": "ts"
    }
    return extensions.get(language, "txt")


def run_rule(rule: ConcurrencyPromiseNotAwaitedRule, code: str = "", language: str = "javascript", 
            config: Dict[str, Any] = None) -> List[Finding]:
    """Run the rule on the given code and return findings."""
    ctx = create_test_context(code, language, config)
    return list(rule.visit(ctx))


class TestConcurrencyPromiseNotAwaitedRule:
    """Test suite for concurrency.promise_not_awaited rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ConcurrencyPromiseNotAwaitedRule()
    
    # --- Basic Functionality Tests ---
    
    def test_meta_properties(self):
        """Test that rule metadata is correctly defined."""
        assert self.rule.meta.id == "concurrency.promise_not_awaited"
        assert self.rule.meta.description == "Flags calls that likely return a Promise but are not awaited, then/catch-handled, or returned."
        assert self.rule.meta.category == "concurrency"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "javascript" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires the right analysis capabilities."""
        reqs = self.rule.requires
        assert reqs.syntax is True
    
    # --- Promise Pattern Recognition Tests ---
    
    def test_promisey_prefix_patterns(self):
        """Test recognition of Promise-returning prefixes."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Test various prefix patterns
        test_patterns = [
            "fs.promises.readFile",
            "fetch",
            "axios.get",
            "Promise.resolve",
            "db.query",
            "http.get",
            "https.get",
            "pg.connect",
            "mongo.findOne",
            "redis.get",
            "client.request",
            "api.call",
            "util.promisify"
        ]
        
        for pattern in test_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.text = ""
            
            # Mock the _get_callee_text method to return our test pattern
            rule._get_callee_text = lambda n, c: pattern
            
            result = rule._looks_promise_like(mock_node, mock_ctx)
            assert result is True, f"Expected {pattern} to be recognized as Promise-like"
    
    def test_promisey_name_hints(self):
        """Test recognition of Promise-like name hints."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Test name hint patterns
        test_patterns = [
            ("loadDataAsync", True),
            ("fetchUserAsync", True),
            ("createPromise", True),
            ("getThenable", True),
            ("normalFunction", False),
            ("syncOperation", False),
        ]
        
        for pattern, should_match in test_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.text = ""
            
            rule._get_callee_text = lambda n, c: pattern
            
            result = rule._looks_promise_like(mock_node, mock_ctx)
            assert result == should_match, f"Expected {pattern} to {'match' if should_match else 'not match'}"
    
    def test_promise_constructor_detection(self):
        """Test detection of Promise constructor calls."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        mock_node = Mock()
        mock_ctx = Mock()
        mock_ctx.text = ""
        
        # Test Promise constructor
        rule._get_callee_text = lambda n, c: "Promise"
        rule._get_node_text = lambda c, n: "new Promise((resolve, reject) => { ... })"
        
        result = rule._looks_promise_like(mock_node, mock_ctx)
        assert result is True, "Expected 'new Promise()' to be recognized as Promise-like"
        
        # Test without Promise constructor
        rule._get_node_text = lambda c, n: "regularFunction()"
        rule._get_callee_text = lambda n, c: "regularFunction"
        
        result = rule._looks_promise_like(mock_node, mock_ctx)
        assert result is False, "Expected regular function to not be recognized as Promise-like"
    
    def test_async_pattern_detection(self):
        """Test detection of common async patterns."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        async_patterns = [
            ("fetch", True),
            ("axios", True),
            ("request", True),
            ("httpGet", True),
            ("postData", True),
            ("putResource", True),
            ("deleteItem", True),
            ("regularFunction", False),
            ("calculateSync", False),
        ]
        
        for pattern, should_match in async_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.text = ""
            
            rule._get_callee_text = lambda n, c: pattern
            rule._get_node_text = lambda c, n: f"{pattern}()"
            
            result = rule._looks_promise_like(mock_node, mock_ctx)
            assert result == should_match, f"Expected {pattern} to {'match' if should_match else 'not match'}"
    
    # --- Await Detection Tests ---
    
    def test_await_detection(self):
        """Test detection of awaited calls."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock awaited call
        await_expr = Mock()
        await_expr.kind = "await_expression"
        await_expr.text = "await fetch('/api')"
        
        call_node = Mock()
        call_node.parent = await_expr
        
        result = rule._is_awaited(call_node)
        assert result is True, "Expected awaited call to be detected"
        
        # Mock non-awaited call
        regular_expr = Mock()
        regular_expr.kind = "call_expression"
        regular_expr.text = "fetch('/api')"
        
        call_node2 = Mock()
        call_node2.parent = regular_expr
        
        result = rule._is_awaited(call_node2)
        assert result is False, "Expected non-awaited call to not be detected as awaited"
    
    def test_then_chaining_detection(self):
        """Test detection of .then/.catch/.finally chaining."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = ""
        
        # Test .then chaining
        member_expr = Mock()
        member_expr.kind = "member_expression"
        
        call_node = Mock()
        call_node.parent = member_expr
        
        rule._get_node_text = lambda c, n: "fetch('/api').then(response => response.json())"
        
        result = rule._is_then_chained(call_node, ctx)
        assert result is True, "Expected .then chained call to be detected"
        
        # Test .catch chaining
        rule._get_node_text = lambda c, n: "fetch('/api').catch(error => console.error(error))"
        
        result = rule._is_then_chained(call_node, ctx)
        assert result is True, "Expected .catch chained call to be detected"
        
        # Test .finally chaining
        rule._get_node_text = lambda c, n: "fetch('/api').finally(() => setLoading(false))"
        
        result = rule._is_then_chained(call_node, ctx)
        assert result is True, "Expected .finally chained call to be detected"
        
        # Test no chaining
        rule._get_node_text = lambda c, n: "fetch('/api')"
        
        result = rule._is_then_chained(call_node, ctx)
        assert result is False, "Expected non-chained call to not be detected as chained"
    
    def test_return_detection(self):
        """Test detection of returned calls."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock return statement
        return_stmt = Mock()
        return_stmt.kind = "return_statement"
        
        call_node = Mock()
        call_node.parent = return_stmt
        
        result = rule._is_returned(call_node)
        assert result is True, "Expected returned call to be detected"
        
        # Mock arrow function
        arrow_func = Mock()
        arrow_func.kind = "arrow_function"
        arrow_func.text = "() => fetch('/api')"
        
        call_node2 = Mock()
        call_node2.parent = arrow_func
        
        result = rule._is_returned(call_node2)
        assert result is True, "Expected arrow function expression to be detected as returned"
        
        # Mock regular expression
        expr_stmt = Mock()
        expr_stmt.kind = "expression_statement"
        
        call_node3 = Mock()
        call_node3.parent = expr_stmt
        
        result = rule._is_returned(call_node3)
        assert result is False, "Expected regular expression to not be detected as returned"
    
    def test_intentional_fire_and_forget_detection(self):
        """Test detection of intentional fire-and-forget patterns."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = ""
        
        # Test void operator
        unary_expr = Mock()
        unary_expr.kind = "unary_expression"
        
        call_node = Mock()
        call_node.parent = unary_expr
        
        rule._get_node_text = lambda c, n: "void fetch('/api')"
        
        result = rule._is_intentional_fire_and_forget(call_node, ctx)
        assert result is True, "Expected void call to be detected as intentional fire-and-forget"
        
        # Test assignment to underscore
        assign_expr = Mock()
        assign_expr.kind = "assignment_expression"
        
        call_node2 = Mock()
        call_node2.parent = assign_expr
        
        rule._get_node_text = lambda c, n: "_ = fetch('/api')"
        
        result = rule._is_intentional_fire_and_forget(call_node2, ctx)
        assert result is True, "Expected assignment to underscore to be detected as intentional"
        
        # Test regular assignment
        rule._get_node_text = lambda c, n: "result = fetch('/api')"
        
        result = rule._is_intentional_fire_and_forget(call_node2, ctx)
        assert result is False, "Expected regular assignment to not be detected as intentional fire-and-forget"
    
    # --- Call Name Extraction Tests ---
    
    def test_callee_text_extraction(self):
        """Test extraction of callee text from call nodes."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = "fetch('/api/data')"
        
        # Test with function attribute
        func_node = Mock()
        func_node.text = "fetch"
        
        call_node = Mock()
        call_node.function = func_node
        
        result = rule._get_callee_text(call_node, ctx)
        assert result == "fetch"
        
        # Test with callee attribute
        callee_node = Mock()
        callee_node.text = "axios.get"
        
        call_node2 = Mock()
        if hasattr(call_node2, 'function'):
            del call_node2.function
        call_node2.callee = callee_node
        
        result = rule._get_callee_text(call_node2, ctx)
        assert result == "axios.get"
        
        # Test with parentheses (should be cleaned)
        dirty_node = Mock()
        dirty_node.text = "fs.promises.readFile(path, 'utf8')"
        
        call_node3 = Mock()
        call_node3.function = dirty_node
        
        result = rule._get_callee_text(call_node3, ctx)
        assert result == "fs.promises.readFile"
        
        # Test empty case
        empty_node = Mock()
        if hasattr(empty_node, 'function'):
            del empty_node.function
        if hasattr(empty_node, 'callee'):
            del empty_node.callee
        if hasattr(empty_node, 'name'):
            del empty_node.name
        
        result = rule._get_callee_text(empty_node, ctx)
        assert result == ""
    
    def test_node_text_extraction(self):
        """Test extraction of text from nodes."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock context
        ctx = Mock()
        ctx.text = "fetch('/api/data')"
        
        # Test node with text attribute
        node_with_text = Mock()
        node_with_text.text = "fetch"
        
        result = rule._get_node_text(ctx, node_with_text)
        assert result == "fetch"
        
        # Test node with byte positions
        node_with_bytes = Mock()
        if hasattr(node_with_bytes, 'text'):
            del node_with_bytes.text
        node_with_bytes.start_byte = 0
        node_with_bytes.end_byte = 5
        
        result = rule._get_node_text(ctx, node_with_bytes)
        assert result == "fetch"
        
        # Test node with value
        node_with_value = Mock()
        if hasattr(node_with_value, 'text'):
            del node_with_value.text
        if hasattr(node_with_value, 'start_byte'):
            del node_with_value.start_byte
        if hasattr(node_with_value, 'end_byte'):
            del node_with_value.end_byte
        node_with_value.value = "test_value"
        
        result = rule._get_node_text(ctx, node_with_value)
        assert result == "test_value"
        
        # Test None node
        result = rule._get_node_text(ctx, None)
        assert result == ""
    
    # --- Call Node Recognition Tests ---
    
    def test_call_node_recognition(self):
        """Test recognition of call nodes."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Test various call node types
        call_expr = Mock()
        call_expr.kind = "call_expression"
        assert rule._is_call_node(call_expr) is True
        
        function_call = Mock()
        function_call.kind = "function_call"
        assert rule._is_call_node(function_call) is True
        
        method_call = Mock()
        method_call.kind = "method_call"
        assert rule._is_call_node(method_call) is True
        
        new_expr = Mock()
        new_expr.kind = "new_expression"
        assert rule._is_call_node(new_expr) is True
        
        # Test non-call node
        identifier = Mock()
        identifier.kind = "identifier"
        assert rule._is_call_node(identifier) is False
        
        # Test node without kind
        no_kind = Mock()
        if hasattr(no_kind, 'kind'):
            del no_kind.kind
        assert rule._is_call_node(no_kind) is False
    
    def test_call_span_extraction(self):
        """Test extraction of spans from call nodes."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        # Mock context with adapter
        ctx = Mock()
        ctx.adapter = Mock()
        
        # Test with callee
        callee = Mock()
        
        call_node = Mock()
        call_node.callee = callee
        call_node.function = None
        
        ctx.adapter.node_span = Mock(return_value=(10, 20))
        
        result = rule._get_call_span(ctx, call_node)
        assert result == (10, 20)
        
        # Test fallback to node itself
        call_node2 = Mock()
        call_node2.callee = None
        call_node2.function = None
        
        ctx.adapter.node_span = Mock(return_value=(5, 15))
        result = rule._get_call_span(ctx, call_node2)
        assert result == (5, 15)
        
        # Test safe fallback when adapter fails
        problematic_node = Mock()
        ctx.adapter.node_span = Mock(side_effect=Exception("Error"))
        
        result = rule._get_call_span(ctx, problematic_node)
        assert result == (0, 10)  # Safe fallback
    
    # --- Edge Cases ---
    
    def test_empty_file(self):
        """Test handling of empty file."""
        ctx = create_test_context("", "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_promises(self):
        """Test file with no Promise calls."""
        ctx = create_test_context("console.log('Hello, world!');", "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_unsupported_language(self):
        """Test unsupported language."""
        ctx = create_test_context("print('Hello')", "python")  # Not in supported languages
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_no_tree(self):
        """Test handling when syntax tree is None."""
        ctx = create_test_context("code", "javascript")
        ctx.tree = None
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # --- Integration-style Tests ---
    
    def test_walk_nodes_functionality(self):
        """Test the node walking functionality."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
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
    
    # --- Language-specific Tests ---
    
    def test_javascript_patterns(self):
        """Test JavaScript-specific Promise patterns."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        js_patterns = [
            "fetch('/api')",
            "axios.get('/data')",
            "$.ajax('/endpoint')",
            "new Promise(resolve => resolve())",
            "db.findOne(query)",
        ]
        
        for pattern in js_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.text = pattern
            
            # Extract the function name from the pattern
            func_name = pattern.split('(')[0]
            rule._get_callee_text = lambda n, c: func_name
            rule._get_node_text = lambda c, n: pattern
            
            result = rule._looks_promise_like(mock_node, mock_ctx)
            assert result is True, f"Expected JavaScript pattern '{pattern}' to be recognized as Promise-like"
    
    def test_typescript_patterns(self):
        """Test TypeScript-specific Promise patterns."""
        rule = ConcurrencyPromiseNotAwaitedRule()
        
        ts_patterns = [
            "fs.promises.readFile",
            "util.promisify(fs.readFile)",
            "client.queryAsync",
            "api.fetchDataAsync",
        ]
        
        for pattern in ts_patterns:
            mock_node = Mock()
            mock_ctx = Mock()
            mock_ctx.text = f"{pattern}()"
            
            rule._get_callee_text = lambda n, c: pattern
            
            result = rule._looks_promise_like(mock_node, mock_ctx)
            assert result is True, f"Expected TypeScript pattern '{pattern}' to be recognized as Promise-like"


# Integration test to verify rule registration
def test_rule_registration():
    """Test that the rule is properly registered."""
    try:
        from rules.concurrency_promise_not_awaited import RULES
        assert len(RULES) == 1
        assert RULES[0].meta.id == "concurrency.promise_not_awaited"
    except ImportError:
        # Skip if rules module not available in test environment
        pytest.skip("Rules module not available for registration test")


if __name__ == "__main__":
    # Run a quick smoke test
    rule = ConcurrencyPromiseNotAwaitedRule()
    
    print("Testing concurrency.promise_not_awaited rule...")
    
    # Test basic metadata
    print(f"Rule ID: {rule.meta.id}")
    print(f"Supported languages: {rule.meta.langs}")
    print(f"Priority: {rule.meta.priority}")
    print(f"Category: {rule.meta.category}")
    
    # Test pattern recognition
    print("\nTesting pattern recognition:")
    print(f"Promise prefixes: {len(rule.PROMISEY_PREFIXES)} patterns")
    print(f"Promise name hints: {len(rule.PROMISEY_NAME_HINTS)} patterns")
    
    # Test some specific patterns
    test_patterns = ["fetch", "axios.get", "fs.promises.readFile", "new Promise"]
    for pattern in test_patterns:
        mock_node = Mock()
        mock_ctx = Mock()
        mock_ctx.text = f"{pattern}()"
        
        rule._get_callee_text = lambda n, c: pattern
        rule._get_node_text = lambda c, n: f"{pattern}()"
        
        is_promise_like = rule._looks_promise_like(mock_node, mock_ctx)
        print(f"  {pattern} recognized as Promise-like: {is_promise_like}")
    
    print("Test completed successfully!")

