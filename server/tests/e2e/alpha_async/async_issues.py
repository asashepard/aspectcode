"""
Alpha Async Test Project  

This project contains intentional async/concurrency issues that should be caught
by alpha async and concurrency rules:
- func.async_mismatch.await_in_sync
- concurrency.async_call_not_awaited
- concurrency.blocking_in_async
- concurrency.lock_not_released
- concurrency.promise_not_awaited
"""

import asyncio
import time
import threading
from typing import Any


# func.async_mismatch.await_in_sync - await in non-async function  
def bad_sync_function():
    """This should trigger func.async_mismatch.await_in_sync"""
    result = await some_async_call()  # ERROR: await in sync function
    return result


# concurrency.async_call_not_awaited - async call without await
async def main():
    """This should trigger concurrency.async_call_not_awaited"""
    # Missing await - should be flagged
    fetch_data()  # ERROR: async call not awaited
    
    # Also test multiple calls
    process_data()  # ERROR: async call not awaited
    save_results()  # ERROR: async call not awaited
    
    print("Done")


# concurrency.blocking_in_async - blocking operations in async functions
async def blocking_async_function():
    """This should trigger concurrency.blocking_in_async"""
    
    # Blocking file I/O in async function
    with open('somefile.txt', 'r') as f:  # ERROR: blocking I/O
        content = f.read()
    
    # Blocking sleep in async function  
    time.sleep(5)  # ERROR: blocking sleep
    
    # Blocking network call (conceptual)
    import urllib.request
    response = urllib.request.urlopen('http://example.com')  # ERROR: blocking network
    
    return content


# concurrency.lock_not_released - lock acquired but not released
def risky_locking():
    """This should trigger concurrency.lock_not_released"""
    lock = threading.Lock()
    
    # Acquire lock but forget to release
    lock.acquire()  # ERROR: lock not released
    
    # Do some work
    time.sleep(1)
    
    # Missing lock.release() - resource leak
    
    return "done"


def better_locking():
    """Example of proper locking (should not be flagged)"""
    lock = threading.Lock()
    
    try:
        lock.acquire()
        # Do work
        time.sleep(1) 
    finally:
        lock.release()  # Proper cleanup


# Helper async functions for testing
async def fetch_data():
    """Async function that should be awaited"""
    await asyncio.sleep(1)
    return {"data": "fetched"}


async def process_data():
    """Another async function"""
    await asyncio.sleep(0.5)
    return "processed"


async def save_results():
    """Another async function"""
    await asyncio.sleep(0.2)
    return "saved"


async def some_async_call():
    """Helper async function"""
    await asyncio.sleep(0.1)
    return "result"


# Additional examples
class AsyncProcessor:
    def __init__(self):
        self.lock = threading.Lock()
    
    def process_item(self, item):
        """concurrency.lock_not_released - class method version"""
        self.lock.acquire()  # ERROR: potential lock leak
        
        # Process item
        processed = f"processed_{item}"
        
        # Missing release in some code paths
        if item == "special":
            return processed  # ERROR: early return without release
        
        self.lock.release()
        return processed


async def mixed_async_issues():
    """Multiple async issues in one function"""
    
    # Issue 1: blocking call in async
    time.sleep(1)  # ERROR: blocking sleep
    
    # Issue 2: not awaiting async call
    fetch_data()  # ERROR: missing await
    
    # Issue 3: mixing sync and async incorrectly
    def inner():
        result = await some_async_call()  # ERROR: await in sync nested function
        return result
    
    return inner()


if __name__ == "__main__":
    # This would cause syntax errors due to await in sync functions
    # but is useful for static analysis testing
    print("Async test project loaded")