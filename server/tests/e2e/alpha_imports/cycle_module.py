"""
Cycle module to create circular import for testing imports.cycle rule.

This module imports deadcode_issues, creating a circular dependency.
"""

# This creates a circular import if deadcode_issues.py imports this module
from . import deadcode_issues

def helper_function():
    """Helper function that uses the other module"""
    return deadcode_issues.analyze_data(["cycle", "test"])