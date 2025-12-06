"""
Alpha Test Quality Issues Project

This project contains intentional test quality issues that should be caught
by alpha test rules:
- test.brittle_time_dependent
- test.flaky_sleep  
- test.no_assertions
"""

import time
import random
import datetime
from unittest import TestCase


# test.brittle_time_dependent - Tests dependent on timing
class BrittleTimeTests(TestCase):
    """Tests with time dependencies that could be flaky"""
    
    def test_processing_speed(self):
        """ERROR: test.brittle_time_dependent - depends on execution speed"""
        start = time.time()
        
        # Some processing
        for i in range(1000):
            x = i * 2
        
        end = time.time()
        duration = end - start
        
        # Brittle assertion - depends on machine speed
        self.assertLess(duration, 0.1)  # Could fail on slow machines
    
    def test_timestamp_generation(self):
        """ERROR: test.brittle_time_dependent - depends on current time"""
        timestamp1 = datetime.datetime.now()
        time.sleep(0.001)  # Tiny sleep
        timestamp2 = datetime.datetime.now()
        
        # Brittle - could fail if system clock changes
        self.assertTrue(timestamp2 > timestamp1)
    
    def test_timeout_behavior(self):
        """ERROR: test.brittle_time_dependent - depends on timing"""
        start_time = time.time()
        
        # Simulate timeout
        while time.time() - start_time < 0.5:
            pass
        
        elapsed = time.time() - start_time
        # Brittle timing assertion
        self.assertAlmostEqual(elapsed, 0.5, delta=0.01)


# test.flaky_sleep - Tests using sleep for synchronization
class FlakySleepTests(TestCase):
    """Tests that use sleep to wait for conditions"""
    
    def test_async_operation_simulation(self):
        """ERROR: test.flaky_sleep - using sleep instead of proper waiting"""
        # Start some "async" operation (simulated)
        operation_started = True
        
        # Bad: using sleep to wait
        time.sleep(1)  # ERROR: flaky sleep
        
        # Assume operation is done
        self.assertTrue(operation_started)
    
    def test_retry_logic(self):
        """ERROR: test.flaky_sleep - multiple sleep calls"""
        attempts = 0
        success = False
        
        while attempts < 3:
            attempts += 1
            
            # Simulate unreliable operation
            success = random.random() > 0.5
            
            if not success:
                time.sleep(0.5)  # ERROR: flaky sleep for retry
            else:
                break
        
        self.assertTrue(success)
    
    def test_server_startup_wait(self):
        """ERROR: test.flaky_sleep - waiting for server with sleep"""
        # Simulate server startup
        server_starting = True
        
        # Bad: fixed sleep instead of polling
        time.sleep(2)  # ERROR: flaky sleep
        
        # Assume server is ready
        server_ready = True
        self.assertTrue(server_ready)
    
    def test_multiple_sleep_calls(self):
        """ERROR: test.flaky_sleep - multiple problematic sleeps"""
        step1_done = True
        time.sleep(0.1)  # ERROR: sleep 1
        
        step2_done = True  
        time.sleep(0.2)  # ERROR: sleep 2
        
        step3_done = True
        time.sleep(0.3)  # ERROR: sleep 3
        
        self.assertTrue(step1_done and step2_done and step3_done)


# test.no_assertions - Tests without any assertions
class NoAssertionTests(TestCase):
    """Tests that don't verify anything"""
    
    def test_data_processing_no_check(self):
        """ERROR: test.no_assertions - no assertions in test"""
        data = [1, 2, 3, 4, 5]
        
        # Process data but don't verify results
        processed = [x * 2 for x in data]
        
        # No assertions - test doesn't verify anything
        print(f"Processed: {processed}")
    
    def test_file_operation_no_verification(self):
        """ERROR: test.no_assertions - no verification of file operations"""
        filename = "test_file.txt"
        
        # Simulate file operations
        with open(filename, 'w') as f:
            f.write("test content")
        
        # Read it back
        with open(filename, 'r') as f:
            content = f.read()
        
        # No assertions to verify content
        print(f"File content: {content}")
        
        # Cleanup
        import os
        os.unlink(filename)
    
    def test_calculation_no_verification(self):
        """ERROR: test.no_assertions - calculation without verification"""
        x = 10
        y = 20
        
        # Perform calculation
        result = x + y
        
        # Just print, no verification
        print(f"Result: {result}")
        
        # Maybe some side effects but no assertions
        global_var = result
    
    def test_empty_test(self):
        """ERROR: test.no_assertions - completely empty test"""
        pass
    
    def test_only_setup_no_verification(self):
        """ERROR: test.no_assertions - only setup code, no verification"""
        # Setup some state
        items = []
        for i in range(10):
            items.append(i * 2)
        
        # Process items
        total = sum(items)
        average = total / len(items)
        
        # Store results but don't verify
        self.results = {
            'total': total,
            'average': average,
            'count': len(items)
        }


# Combined issues - tests with multiple problems
class CombinedIssuesTests(TestCase):
    """Tests with multiple quality issues"""
    
    def test_all_issues_combined(self):
        """Combines time dependence, sleep, and no assertions"""
        # Time dependent
        start = time.time()
        
        # Flaky sleep
        time.sleep(0.5)  # ERROR: flaky sleep
        
        # Some processing
        for i in range(100):
            x = i * 2
        
        end = time.time()
        duration = end - start
        
        # Time dependent assertion
        # (Also note: this might be the only assertion, making it brittle)
        print(f"Duration: {duration}")  # ERROR: no real assertions
    
    def test_timing_with_sleeps(self):
        """Multiple timing and sleep issues"""
        timestamps = []
        
        for i in range(3):
            timestamps.append(time.time())
            time.sleep(0.1)  # ERROR: flaky sleep
        
        # Brittle timing checks
        for i in range(len(timestamps) - 1):
            diff = timestamps[i + 1] - timestamps[i]
            # This could be brittle and has no assertions
            print(f"Time diff {i}: {diff}")


def utility_function():
    """This is not a test function, so it should not be flagged for no assertions"""
    return "helper"


if __name__ == "__main__":
    import unittest
    unittest.main()