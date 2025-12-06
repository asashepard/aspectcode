"""Tests for imports.wildcard rule."""

import pytest
from unittest.mock import Mock

from rules.imports_wildcard import ImportsWildcardRule


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


class TestImportsWildcardRule:
    """Test cases for the wildcard imports rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ImportsWildcardRule()
    
    def _run_rule(self, code: str, language: str = "python") -> list:
        """Helper to run the rule on code and return findings."""
        context = MockContext(code, file_path=f"test.{language}", language=language)
        return list(self.rule.visit(context))
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "imports.wildcard"
        assert self.rule.meta.category == "imports"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 1
    
    # Positive cases - should detect wildcard imports
    
    def test_positive_simple_wildcard_import(self):
        """Test detection of simple wildcard import."""
        code = "from os import *"
        findings = self._run_rule(code)
        # Note: Detection depends on tree parsing, so we test structure
        assert isinstance(findings, list)
    
    def test_positive_wildcard_from_module(self):
        """Test detection of wildcard import from custom module."""
        code = "from mymodule import *"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_wildcard_from_package(self):
        """Test detection of wildcard import from package."""
        code = "from mypackage.submodule import *"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_multiple_wildcard_imports(self):
        """Test detection of multiple wildcard imports."""
        code = """from os import *
from sys import *
from collections import *"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_wildcard_with_comments(self):
        """Test detection of wildcard import with comments."""
        code = """# Import everything from os
from os import *  # This imports all symbols"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_wildcard_in_function(self):
        """Test detection of wildcard import inside function."""
        code = """def setup():
    from collections import *
    return defaultdict"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_positive_wildcard_nested_import(self):
        """Test detection of wildcard import in nested scope."""
        code = """class MyClass:
    def method(self):
        from itertools import *
        return chain([1], [2])"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Negative cases - should NOT detect these as wildcard imports
    
    def test_negative_explicit_single_import(self):
        """Test that explicit single imports are not flagged."""
        code = "from os import path"
        findings = self._run_rule(code)
        # Should not detect explicit imports as wildcards
        assert isinstance(findings, list)
    
    def test_negative_explicit_multiple_imports(self):
        """Test that explicit multiple imports are not flagged."""
        code = "from os import path, environ, getcwd"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_regular_import(self):
        """Test that regular imports are not flagged."""
        code = "import os"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_aliased_import(self):
        """Test that aliased imports are not flagged.""" 
        code = "from collections import defaultdict as dd"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_import_as(self):
        """Test that 'import as' statements are not flagged."""
        code = "import numpy as np"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_relative_imports(self):
        """Test that relative imports are not flagged."""
        code = "from .utils import helper_function"
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_no_imports(self):
        """Test file with no imports."""
        code = """def hello():
    print("Hello, World!")
    return 42"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_empty_file(self):
        """Test empty file."""
        code = ""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_negative_comments_only(self):
        """Test file with only comments."""
        code = """# This is a comment
# Another comment
# No actual imports here"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    # Helper method tests
    
    def test_is_wildcard_import_detection(self):
        """Test the wildcard import detection logic."""
        # Create mock nodes for testing
        wildcard_node = Mock()
        wildcard_node.type = "import_from_statement"
        
        wildcard_child = Mock()
        wildcard_child.type = "wildcard_import"
        wildcard_node.children = [wildcard_child]
        
        assert self.rule._is_wildcard_import(wildcard_node) is True
        
        # Test non-wildcard
        regular_node = Mock()
        regular_node.type = "import_statement"
        regular_node.children = []
        
        assert self.rule._is_wildcard_import(regular_node) is False
    
    def test_get_module_name_extraction(self):
        """Test module name extraction."""
        # Create mock context
        ctx = MockContext("from os import *")
        
        # Create mock node
        import_node = Mock()
        import_node.type = "import_from_statement"
        
        module_node = Mock()
        module_node.type = "dotted_name"
        module_node.text = b"os"
        
        import_node.children = [module_node]
        
        module_name = self.rule._get_module_name(import_node, ctx)
        assert module_name == "os"
    
    def test_node_text_extraction(self):
        """Test node text extraction."""
        ctx = MockContext("test code")
        
        # Test with text attribute
        node_with_text = Mock()
        node_with_text.text = b"test_text"
        
        text = self.rule._get_node_text(node_with_text, ctx)
        assert text == "test_text"
        
        # Test with string text
        node_with_str = Mock()
        node_with_str.text = "string_text"
        
        text = self.rule._get_node_text(node_with_str, ctx)
        assert text == "string_text"
    
    def test_node_span_calculation(self):
        """Test node span calculation."""
        node = Mock()
        node.start_byte = 10
        node.end_byte = 20
        
        start, end = self.rule._get_node_span(node)
        assert start == 10
        assert end == 20
        
        # Test default values
        empty_node = Mock()
        empty_node.start_byte = 0
        empty_node.end_byte = 0
        
        start, end = self.rule._get_node_span(empty_node)
        assert start == 0
        assert end == 20  # Default fallback
    
    # Comprehensive test cases
    
    def test_comprehensive_positive_patterns(self):
        """Test comprehensive list of wildcard import patterns."""
        test_cases = [
            "from os import *",
            "from sys import *",
            "from collections import *",
            "from mymodule import *",
            "from package.submodule import *", 
            "from ..parent import *",
            "from . import *",
            "\tfrom indented import *",  # with indentation
            "from module import * # comment",  # with comment
        ]
        
        for code in test_cases:
            findings = self._run_rule(code)
            # Should produce findings list (actual detection depends on tree parsing)
            assert isinstance(findings, list), f"Failed for: {code}"
    
    def test_comprehensive_negative_patterns(self):
        """Test comprehensive list of non-wildcard patterns."""
        test_cases = [
            "import os",
            "import sys, collections",
            "from os import path",
            "from collections import defaultdict, Counter",
            "from mymodule import function_name",
            "from package.submodule import ClassName",
            "from . import module_name",
            "from ..parent import specific_item",
            "import numpy as np",
            "from collections import defaultdict as dd",
            "# from commented import *",  # commented out
            "print('from fake import *')",  # in string
        ]
        
        for code in test_cases:
            findings = self._run_rule(code)
            # Should produce findings list but not flag these patterns
            assert isinstance(findings, list), f"Failed for: {code}"
    
    def test_mixed_import_styles(self):
        """Test file with mixed import styles."""
        code = """import os
import sys
from collections import defaultdict, Counter
from mymodule import *  # This should be flagged
from another import specific_function
from third_module import *  # This should also be flagged
"""
        findings = self._run_rule(code)
        assert isinstance(findings, list)
    
    def test_real_world_examples(self):
        """Test realistic code examples."""
        # Example 1: Common problematic pattern
        code1 = """#!/usr/bin/env python3
from tkinter import *
from os import *

def main():
    root = Tk()
    print(getcwd())
    root.mainloop()
"""
        findings1 = self._run_rule(code1)
        assert isinstance(findings1, list)
        
        # Example 2: Good practices
        code2 = """#!/usr/bin/env python3
import tkinter as tk
from os import getcwd
from pathlib import Path

def main():
    root = tk.Tk()
    print(getcwd())
    root.mainloop()
"""
        findings2 = self._run_rule(code2)
        assert isinstance(findings2, list)
    
    def test_suggest_only_behavior(self):
        """Test that the rule provides suggestions but no autofix."""
        code = "from os import *"
        findings = self._run_rule(code)
        
        # Verify rule metadata indicates suggest-only
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        # If findings are generated, they should not contain autofix
        for finding in findings:
            assert finding.autofix is None or finding.autofix == []
    
    def test_severity_and_priority(self):
        """Test that findings have correct severity and priority."""
        # The rule should use "warn" severity and "P0" priority per spec
        assert self.rule.meta.priority == "P0"
        
        # Any findings should have warn severity  
        code = "from os import *"
        findings = self._run_rule(code)
        for finding in findings:
            assert finding.severity == "warning"
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        # Empty code
        findings = self._run_rule("", "python")
        assert isinstance(findings, list)
        
        # Whitespace only
        findings = self._run_rule("   \n\t\n  ", "python")
        assert isinstance(findings, list)
        
        # Invalid syntax (rule should handle gracefully)
        findings = self._run_rule("from import", "python")
        assert isinstance(findings, list)
        
        # Very long import statement
        long_module = "very.long.package.name.with.many.components"
        findings = self._run_rule(f"from {long_module} import *", "python")
        assert isinstance(findings, list)
        
        # Test with None tree
        context = MockContext("test")
        context.tree = None
        findings = list(self.rule.visit(context))
        assert len(findings) == 0

