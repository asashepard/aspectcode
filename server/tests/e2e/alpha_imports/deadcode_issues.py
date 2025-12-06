"""
Alpha Imports and Deadcode Test Project

This project contains intentional import and dead code issues that should be caught
by alpha import and deadcode rules:
- imports.cycle
- imports.unused
- deadcode.duplicate_import 
- deadcode.redundant_condition
- deadcode.unused_variable
"""

# imports.unused - Unused imports
import os  # Not used anywhere
import sys  # Not used anywhere
import json  # Not used anywhere
from typing import Dict, List, Optional  # Dict and Optional not used

# deadcode.duplicate_import - Duplicate imports
import re
import time
import re  # Duplicate import

from datetime import datetime
from datetime import datetime  # Another duplicate

# Some actual used imports
from pathlib import Path


def analyze_data(data: List[str]) -> str:
    """Function with various deadcode issues"""
    
    # deadcode.unused_variable - Unused variables
    unused_var = "never used"
    another_unused = 42
    temp_result = "temporary"  # Not used
    
    # deadcode.redundant_condition - Redundant conditions
    if True:  # Always true
        result = "always executed"
    
    if data and len(data) > 0:  # Redundant check (data implies len > 0)
        processed = True
    
    value = 5
    if value == 5 and value == 5:  # Redundant condition
        processed = True
    
    # More redundant conditions
    if data is not None and data is not None:  # Duplicate check
        processed = True
    
    return result


def process_files():
    """More deadcode examples"""
    
    # Unused variables
    file_count = 0  # Never read
    error_messages = []  # Never read
    config_loaded = False  # Never read
    
    # Used variable (should not be flagged)
    files = Path(".").glob("*.py") 
    
    # Redundant condition
    for file_path in files:
        if file_path.exists() and file_path.is_file():  # exists() implies is_file() for files
            print(f"Processing {file_path}")
            
        # More unused vars
        start_time = time.time()  # Never used
        file_size = file_path.stat().st_size  # Never used


class DataProcessor:
    """Class with deadcode issues"""
    
    def __init__(self):
        # Unused instance variables
        self.cache = {}  # Never accessed
        self.config = None  # Never accessed
        self.stats = {"count": 0}  # Never accessed
    
    def process(self, items):
        """Process items with redundant checks"""
        
        # Redundant conditions
        if items and items is not None:  # items implies not None
            count = len(items)
            
        if count > 0 and count >= 1:  # > 0 implies >= 1
            return "processed"
            
        # Unused local variables
        backup_items = items.copy()  # Never used
        processing_start = datetime.now()  # Never used
        
        return "empty"


# Example of imports.cycle - This would create a circular import
# if cycle_module.py imported this file back
try:
    from . import cycle_module  # This creates a cycle if cycle_module imports this
except ImportError:
    pass  # Ignore for testing


def complex_conditions():
    """More complex redundant conditions"""
    x = 10
    y = 20
    
    # Various redundant patterns
    if x > 5 and x > 3:  # x > 5 implies x > 3
        print("redundant")
    
    if y == 20 and y == 20:  # Exact duplicate
        print("duplicate")
        
    if x != 0 and x:  # x implies x != 0 (for numbers)
        print("redundant non-zero check")
    
    data = [1, 2, 3]
    if data and len(data) > 0 and data is not None:  # Multiple redundant checks
        print("over-defensive")


# Unused module-level variables
MODULE_CONFIG = {"setting": "value"}  # Never accessed
DEFAULT_TIMEOUT = 30  # Never accessed
ERROR_CODES = {404: "Not Found", 500: "Server Error"}  # Never accessed


if __name__ == "__main__":
    # This variable is unused
    script_start = time.time()
    
    # Call functions to avoid them being flagged as unused
    analyze_data(["test"])
    process_files()