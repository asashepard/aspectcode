"""
Unit tests for func.async_mismatch.await_in_sync rule.

Tests detection of await expressions used inside non-async functions,
which is a syntax error in Python.
"""

import pytest
from engine.types import RuleContext
from rules.async_mismatch_await_in_sync import AsyncMismatchAwaitInSyncRule


class TestAsyncMismatchAwaitInSyncRule:
    """Test suite for func.async_mismatch.await_in_sync rule."""
    
    def setup_method(self):
        """Set up test environment."""
        self.rule = AsyncMismatchAwaitInSyncRule()
    
    def test_await_in_non_async_function(self):
        """Test that await in non-async function is flagged."""
        code = '''
def regular_function():
    result = await some_async_call()
    return result
'''
        
        # Create mock context
        context = RuleContext(
            source_code=code,
            file_path="test.py",
            language="python"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag await in non-async function"
        
        finding = findings[0]
        assert finding.rule_id == "func.async_mismatch.await_in_sync"
        assert "await" in finding.message.lower()
        assert "async" in finding.message.lower()
    
    def test_await_in_async_function_allowed(self):
        """Test that await in async function is allowed."""
        code = '''
async def async_function():
    result = await some_async_call()
    return result
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.py",
            language="python"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) == 0, "Should not flag await in async function"
    
    def test_no_await_expressions(self):
        """Test that functions without await are not flagged."""
        code = '''
def regular_function():
    result = some_sync_call()
    return result

async def async_function():
    result = some_sync_call()
    return result
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.py",
            language="python"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) == 0, "Should not flag functions without await"
    
    def test_nested_await_in_non_async(self):
        """Test await in nested scope within non-async function."""
        code = '''
def outer_function():
    def inner_function():
        result = await nested_call()
        return result
    return inner_function()
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.py",
            language="python"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag await in nested non-async function"
    
    def test_multiple_await_violations(self):
        """Test multiple await violations in same function."""
        code = '''
def bad_function():
    result1 = await call1()
    result2 = await call2()
    return result1 + result2
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.py", 
            language="python"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 2, "Should flag multiple await violations"


if __name__ == "__main__":
    # Run basic test without pytest
    test_rule = TestAsyncMismatchAwaitInSyncRule()
    test_rule.setup_method()
    
    try:
        test_rule.test_await_in_async_function_allowed()
        print("✓ Async function test passed")
        
        test_rule.test_no_await_expressions()
        print("✓ No await test passed")
        
        print("✓ Basic unit tests for func.async_mismatch.await_in_sync passed!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()