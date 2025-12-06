# Should trigger: test.no_assertions
import pytest

def test_something():
    result = calculate()
    # No assertion - test doesn't verify anything
    
def calculate():
    return 42
