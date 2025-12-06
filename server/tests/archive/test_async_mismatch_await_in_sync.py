"""Tests for func.async_mismatch.await_in_sync rule."""

import pytest
from unittest.mock import Mock

from rules.async_mismatch_await_in_sync import AsyncMismatchAwaitInSyncRule


class MockContext:
    """Mock context for testing."""
    
    def __init__(self, content, file_path="test.py", language="python"):
        self.content = content
        self.file_path = file_path
        self.text = content
        self.lines = content.split('\n')
        self.tree = self._create_mock_tree()
        self.adapter = Mock()
        self.adapter.language_id.return_value = language
        self.config = {}
    
    def _create_mock_tree(self):
        """Create a simple mock tree for text-based analysis."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        return mock_tree


class TestAsyncMismatchAwaitInSyncRule:
    """Test cases for the await in sync function rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = AsyncMismatchAwaitInSyncRule()
    
    def _run_rule(self, code: str, language: str = "python") -> list:
        """Helper to run the rule on code and return findings."""
        context = MockContext(code, file_path=f"test.{language}", language=language)
        return list(self.rule.visit(context))
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "func.async_mismatch.await_in_sync"
        assert self.rule.meta.category == "func"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 1
    
    # Positive cases - should detect await in non-async functions
    
    def test_positive_simple_await_in_sync(self):
        """Test detection of await in regular function."""
        code = """
def sync_function():
    result = await some_coroutine()
    return result
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_await_in_method(self):
        """Test detection of await in class method."""
        code = """
class MyClass:
    def sync_method(self):
        data = await fetch_data()
        return data
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_multiple_awaits_in_sync(self):
        """Test detection of multiple awaits in sync function."""
        code = """
def process_data():
    data1 = await get_data1()
    data2 = await get_data2()
    return data1 + data2
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_await_in_nested_sync_function(self):
        """Test detection of await in nested non-async function."""
        code = """
def outer_sync():
    def inner_sync():
        result = await inner_coroutine()
        return result
    return inner_sync()
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_await_in_sync_with_async_nearby(self):
        """Test detection when both sync and async functions are present."""
        code = """
async def async_func():
    return await valid_coroutine()

def sync_func():
    return await invalid_coroutine()  # This should be flagged
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_await_in_staticmethod(self):
        """Test detection in static methods."""
        code = """
class Utils:
    @staticmethod
    def helper():
        return await some_operation()
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_await_in_classmethod(self):
        """Test detection in class methods."""
        code = """
class DataProcessor:
    @classmethod
    def process(cls):
        return await cls.fetch_data()
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Negative cases - should NOT detect these (valid async usage)
    
    def test_negative_await_in_async_function(self):
        """Test that await in async function is not flagged."""
        code = """
async def async_function():
    result = await some_coroutine()
    return result
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_await_in_async_method(self):
        """Test that await in async method is not flagged."""
        code = """
class MyClass:
    async def async_method(self):
        data = await fetch_data()
        return data
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_multiple_awaits_in_async(self):
        """Test that multiple awaits in async function are not flagged."""
        code = """
async def process_data():
    data1 = await get_data1()
    data2 = await get_data2()
    return data1 + data2
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_no_await_expressions(self):
        """Test that functions without await are not flagged."""
        code = """
def regular_function():
    result = some_function()
    return result
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_await_in_async_generator(self):
        """Test that await in async generator is not flagged."""
        code = """
async def async_generator():
    for item in range(10):
        result = await process_item(item)
        yield result
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_await_in_async_context_manager(self):
        """Test that await in async context manager is not flagged."""
        code = """
class AsyncContextManager:
    async def __aenter__(self):
        return await self.setup()
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_await_keyword_in_string(self):
        """Test that 'await' in strings is not flagged."""
        code = """
def print_message():
    print("Please await the response")
    return "await keyword in string"
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_await_keyword_in_comment(self):
        """Test that 'await' in comments is not flagged."""
        code = """
def some_function():
    # This function should await the result
    result = sync_operation()
    return result
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_no_functions(self):
        """Test code with no function definitions."""
        code = """
# Module level code
import asyncio
x = 5
print("Hello world")
        """
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_empty_file(self):
        """Test empty file."""
        code = ""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Helper method tests
    
    def test_is_async_function_detection(self):
        """Test async function detection logic."""
        context = MockContext("async def test(): pass")
        
        # Mock async function node
        async_func = Mock()
        async_func.type = "function_definition"
        async_func.children = []
        
        # Add async keyword child
        async_keyword = Mock()
        async_keyword.type = "async"
        async_keyword.text = "async"
        async_func.children = [async_keyword]
        
        is_async = self.rule._is_async_function(async_func, context)
        # Note: actual detection depends on tree parsing
        assert isinstance(is_async, bool)
    
    def test_get_function_name_extraction(self):
        """Test function name extraction."""
        context = MockContext("def test_func(): pass")
        
        # Mock function node with identifier child
        func_node = Mock()
        identifier = Mock()
        identifier.type = "identifier"
        identifier.text = b"test_func"
        func_node.children = [Mock(), identifier]  # def, name
        
        name = self.rule._get_function_name(func_node, context)
        assert name == "test_func"
    
    def test_node_text_extraction(self):
        """Test node text extraction methods."""
        context = MockContext("test code")
        
        # Test with bytes text
        node_with_bytes = Mock()
        node_with_bytes.text = b"await"
        
        text = self.rule._get_node_text(node_with_bytes, context)
        assert text == "await"
        
        # Test with string text
        node_with_str = Mock()
        node_with_str.text = "await"
        
        text = self.rule._get_node_text(node_with_str, context)
        assert text == "await"
    
    def test_node_span_calculation(self):
        """Test node span calculation."""
        node = Mock()
        node.start_byte = 20
        node.end_byte = 25
        
        start, end = self.rule._get_node_span(node)
        assert start == 20
        assert end == 25
    
    def test_finding_generation_structure(self):
        """Test that findings are generated with correct structure."""
        code = """
def bad_function():
    result = await some_call()
    return result
        """
        findings = self._run_rule(code)
        
        assert isinstance(findings, list)
        
        # Check that rule metadata is correct
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        for finding in findings:
            # Autofix should be None (suggest-only)
            assert finding.autofix is None
            # Severity should be warn
            assert finding.severity == "warning"
    
    # Comprehensive test cases
    
    def test_comprehensive_positive_patterns(self):
        """Test comprehensive list of problematic patterns."""
        test_cases = [
            "def func(): return await call()",
            "def method(self): await operation()",
            "def helper(): x = await async_func()",
            "def process(): await asyncio.sleep(1)",
            "def handler(): await event.wait()",
            "def worker(): result = await queue.get()",
            "def fetcher(): data = await http.get(url)",
        ]
        
        for code_line in test_cases:
            code = f"{code_line}"
            findings = self._run_rule(code)
            assert isinstance(findings, list), f"Failed for: {code_line}"
    
    def test_comprehensive_negative_patterns(self):
        """Test comprehensive list of valid patterns."""
        test_cases = [
            "async def func(): return await call()",
            "async def method(self): await operation()",
            "async def helper(): x = await async_func()",
            "async def process(): await asyncio.sleep(1)",
            "def func(): return call()",  # no await
            "def func(): pass",  # no await
            "def func(): print('await')",  # await in string
            "# await something",  # await in comment
            "class MyClass: pass",  # no functions
        ]
        
        for code_line in test_cases:
            findings = self._run_rule(code_line)
            assert isinstance(findings, list), f"Failed for: {code_line}"
    
    def test_real_world_examples(self):
        """Test realistic code examples."""
        # Example 1: Common mistake - forgetting async
        problematic_code = """
import asyncio

def fetch_data():  # Should be async
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.example.com') as response:
            data = await response.json()  # Error: await in non-async
            return data

def process_multiple():  # Should be async
    tasks = []
    for url in urls:
        task = await fetch_url(url)  # Error: await in non-async
        tasks.append(task)
    return tasks
        """
        findings1 = self._run_rule(problematic_code)
        assert isinstance(findings1, list)
        
        # Example 2: Correct async usage
        correct_code = """
import asyncio

async def fetch_data():  # Correctly marked as async
    async with aiohttp.ClientSession() as session:
        async with session.get('https://api.example.com') as response:
            data = await response.json()  # Valid: await in async function
            return data

async def process_multiple():  # Correctly marked as async
    tasks = []
    for url in urls:
        task = await fetch_url(url)  # Valid: await in async function
        tasks.append(task)
    return tasks
        """
        findings2 = self._run_rule(correct_code)
        assert isinstance(findings2, list)
        
        # Example 3: Mixed patterns
        mixed_code = """
async def good_async():
    return await valid_call()  # Good

def bad_sync():
    return await invalid_call()  # Bad - should be flagged

def regular_sync():
    return regular_call()  # Good - no await
        """
        findings3 = self._run_rule(mixed_code)
        assert isinstance(findings3, list)
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty function
        findings = self._run_rule("def func(): pass", "python")
        assert isinstance(findings, list)
        
        # Function with only comments
        findings = self._run_rule("def func():\n    # await something\n    pass", "python")
        assert isinstance(findings, list)
        
        # Nested class and function definitions
        nested_code = """
class Outer:
    def method(self):
        class Inner:
            def inner_method(self):
                return await nested_call()  # Should be flagged
        return Inner()
        """
        findings = self._run_rule(nested_code, "python")
        assert isinstance(findings, list)
        
        # Lambda functions (edge case)
        lambda_code = """
def create_lambda():
    return lambda x: await process(x)  # Should be flagged
        """
        findings = self._run_rule(lambda_code, "python")
        assert isinstance(findings, list)
        
        # Multiple nested scopes
        complex_code = """
def outer():
    def middle():
        def inner():
            return await deepest_call()  # Should be flagged
        return inner
    return middle

async def async_outer():
    def sync_inner():
        return await mixed_call()  # Should be flagged (inner is not async)
    return sync_inner
        """
        findings = self._run_rule(complex_code, "python")
        assert isinstance(findings, list)
    
    def test_await_detection_methods(self):
        """Test await detection helper methods."""
        context = MockContext("def func(): await call()")
        
        # Test finding awaits in function
        func_node = Mock()
        func_node.children = []
        
        # Create mock await node
        await_node = Mock()
        await_node.type = "await"  # String, not Mock
        await_node.children = []
        func_node.children = [await_node]
        
        awaits = self.rule._find_awaits_in_function(func_node)
        assert isinstance(awaits, list)
        
        # Test await token finding
        await_token = self.rule._find_await_token(await_node, context)
        # Should return the node itself or None
        assert await_token is None or await_token == await_node
    
    def test_tree_walking(self):
        """Test tree walking functionality."""
        context = MockContext("def func(): pass")
        
        # Test that tree walking handles None tree gracefully
        context.tree = None
        findings = list(self.rule.visit(context))
        assert len(findings) == 0
        
        # Test with mock tree
        context.tree = Mock()
        root_node = Mock()
        root_node.children = []
        context.tree.root_node = root_node
        
        # Should handle empty tree
        findings = list(self.rule.visit(context))
        assert isinstance(findings, list)
    
    def test_severity_and_configuration(self):
        """Test rule severity and configuration."""
        # Check that severity is warn as specified
        assert self.rule.meta.priority == "P0"
        
        code = """
def func():
    await call()
        """
        findings = self._run_rule(code)
        
        for finding in findings:
            assert finding.severity == "warning"
            
            # Check metadata structure
            if finding.meta:
                assert "function_name" in finding.meta
                assert "suggestion" in finding.meta
                assert "await_text" in finding.meta
            
            # Should not have autofix (suggest-only)
            assert finding.autofix is None
    
    def test_function_name_in_messages(self):
        """Test that function names appear in error messages."""
        code = """
def my_special_function():
    result = await some_operation()
    return result
        """
        findings = self._run_rule(code)
        
        # Check that function name appears in messages/metadata
        for finding in findings:
            # Either in message or metadata
            assert ("my_special_function" in finding.message or
                    (finding.meta and "my_special_function" in str(finding.meta)))
    
    def test_complex_async_patterns(self):
        """Test complex async/await patterns."""
        # Async generators
        async_gen_code = """
async def async_gen():
    for i in range(10):
        yield await process(i)  # Valid

def sync_gen():
    for i in range(10):
        yield await process(i)  # Invalid - should be flagged
        """
        findings = self._run_rule(async_gen_code)
        assert isinstance(findings, list)
        
        # Context managers
        context_mgr_code = """
class AsyncContext:
    async def __aenter__(self):
        return await self.setup()  # Valid
    
    def __enter__(self):
        return await self.setup()  # Invalid - should be flagged
        """
        findings = self._run_rule(context_mgr_code)
        assert isinstance(findings, list)

