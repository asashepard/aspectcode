# Should trigger: test.flaky_sleep
import time
import pytest

def test_with_sleep():
    start_process()
    time.sleep(5)  # flaky sleep in test
    assert check_result()
    
def start_process():
    pass
    
def check_result():
    return True
