# server/tests/test_deadcode_duplicate_import.py
"""
Tests for deadcode.duplicate_import rule.

This module tests detection of duplicate import statements and
verification of safe autofix options.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_duplicate_import import DeadcodeDuplicateImportRule
from engine.types import RuleContext, Finding, Edit
from engine.python_adapter import PythonAdapter
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter
from engine.java_adapter import JavaAdapter
from engine.csharp_adapter import CSharpAdapter

def create_test_context(code: str, language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a RuleContext for testing."""
    # Choose appropriate adapter
    adapters = {
        "python": PythonAdapter(),
        "javascript": JavaScriptAdapter(), 
        "typescript": TypeScriptAdapter(),
        "java": JavaAdapter(),  # Now using proper Java adapter
        "csharp": CSharpAdapter(),   # Now using proper C# adapter
    }
    
    # Map language to file extension
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "csharp": "cs"
    }
    
    adapter = adapters.get(language, PythonAdapter())
    ext = extensions.get(language, "py")
    file_path = f"test.{ext}"
    
    # Parse the tree
    tree = adapter.parse(code)
    
    ctx = RuleContext(
        file_path=file_path,
        text=code,
        tree=tree,
        adapter=adapter,
        config=config or {},
        scopes=None  # Tier 0 rule doesn't need scopes
    )
    
    return ctx

def run_rule(rule, code: str, language: str = "python", config: Dict[str, Any] = None):
    """Helper to run a rule on test code."""
    ctx = create_test_context(code, language, config)
    findings = rule.visit(ctx)
    
    # Create a simple result object
    class Result:
        def __init__(self, findings):
            self.findings = findings
    
    return Result(findings)

def apply_fixes(code: str, findings: List[Finding]) -> str:
    """Apply autofix edits from findings to the code."""
    if not findings:
        return code
    
    # Collect all edits from all findings
    all_edits = []
    for finding in findings:
        if finding.autofix:
            all_edits.extend(finding.autofix)
    
    if not all_edits:
        return code
    
    # Sort edits by start_byte in reverse order to apply from end to start
    all_edits.sort(key=lambda e: e.start_byte, reverse=True)
    
    # Apply edits
    result = code
    for edit in all_edits:
        result = result[:edit.start_byte] + edit.replacement + result[edit.end_byte:]
    
    return result

RULE = DeadcodeDuplicateImportRule()

def test_positive_python_duplicates_removed():
    """Test detection and removal of duplicate Python imports."""
    code = (
        "import os\n"
        "import sys\n"
        "import os\n"          # duplicate
        "from math import pi\n"
        "from math import pi\n" # duplicate
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1
    assert fixed.count("from math import pi") == 1
    # Ensure both unique imports are still present
    assert "import sys" in fixed

def test_positive_javascript_duplicates():
    """Test detection of duplicate JavaScript imports."""
    code = (
        "import fs from 'fs';\n"
        "import path from 'path';\n"
        "import fs from 'fs';\n"  # duplicate
        "import { readFile } from 'fs';\n"
        "import { readFile } from 'fs';\n"  # duplicate
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import fs from 'fs';") == 1
    assert fixed.count("import { readFile } from 'fs';") == 1
    assert "import path from 'path';" in fixed

def test_positive_typescript_duplicates():
    """Test detection of duplicate TypeScript imports."""
    code = (
        "import * as fs from 'fs';\n"
        "import { Component } from 'react';\n"
        "import * as fs from 'fs';\n"  # duplicate
    )
    res = run_rule(RULE, code, language="typescript")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import * as fs from 'fs';") == 1
    assert "import { Component } from 'react';" in fixed

def test_positive_csharp_duplicates():
    """Test detection of duplicate C# using statements."""
    code = (
        "using System;\n"
        "using System.Collections.Generic;\n"
        "using System;\n"  # duplicate
        "class Test {}\n"
    )
    res = run_rule(RULE, code, language="csharp")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("using System;") == 1
    assert "using System.Collections.Generic;" in fixed
    assert "class Test {}" in fixed

def test_positive_java_duplicates():
    """Test detection of duplicate Java imports."""
    code = (
        "import java.util.List;\n"
        "import java.util.Map;\n"
        "import java.util.List;\n"  # duplicate
        "class Test {}\n"
    )
    res = run_rule(RULE, code, language="java")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import java.util.List;") == 1
    assert "import java.util.Map;" in fixed
    assert "class Test {}" in fixed

def test_positive_multiple_duplicates():
    """Test handling of multiple sets of duplicates."""
    code = (
        "import os\n"
        "import sys\n"
        "import os\n"    # duplicate 1
        "import json\n"
        "import sys\n"   # duplicate 2
        "import os\n"    # duplicate 3
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1
    assert fixed.count("import sys") == 1
    assert fixed.count("import json") == 1

def test_negative_js_similar_but_not_identical():
    """Test that similar but not identical imports are not considered duplicates."""
    code = (
        "import { a } from 'm';\n"
        "import { a as aa } from 'm';\n"   # not identical → keep
        "import * as m from 'm';\n"        # not identical → keep
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 0

def test_negative_python_different_imports():
    """Test that different Python imports are not flagged."""
    code = (
        "import os\n"
        "import os.path\n"     # different
        "from os import path\n" # different
        "import sys\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 0

def test_negative_whitespace_differences():
    """Test that whitespace differences prevent matching (byte-identical only)."""
    code = (
        "import os\n"
        "import  os\n"    # extra space - not identical
        "import\tos\n"    # tab instead of space - not identical
    )
    res = run_rule(RULE, code, language="python")
    # Should not match because they're not byte-identical
    assert len(res.findings) == 0

def test_negative_different_aliases():
    """Test that different aliases are not considered duplicates."""
    code = (
        "import numpy as np\n"
        "import numpy as numpy\n"  # different alias
        "import pandas as pd\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 0

def test_autofix_java_using_duplicates():
    """Test autofix behavior with Java imports."""
    code = (
        "import java.util.List;\n"
        "import java.util.List;\n"
        "class A {}\n"
    )
    res = run_rule(RULE, code, language="java")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import java.util.List;") == 1
    assert "class A {}" in fixed
    
    # Re-run to ensure it's clean
    res2 = run_rule(RULE, fixed, language="java")
    assert len(res2.findings) == 0

def test_autofix_preserves_order():
    """Test that autofix preserves the order of remaining imports."""
    code = (
        "import first\n"
        "import second\n"
        "import first\n"    # duplicate
        "import third\n"
        "import second\n"   # duplicate
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    lines = [line.strip() for line in fixed.split('\n') if line.strip()]
    assert lines == ["import first", "import second", "import third"]

def test_edge_case_with_comments():
    """Test handling of imports with comments between them."""
    code = (
        "import os\n"
        "# This is a comment\n"
        "import sys\n"
        "import os\n"    # duplicate
        "# Another comment\n"
        "import json\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1
    assert "# This is a comment" in fixed
    assert "# Another comment" in fixed

def test_edge_case_trailing_newlines():
    """Test that trailing newlines are properly handled."""
    code = "import os\nimport sys\nimport os\n"
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1
    # Should not have extra blank lines
    assert "\n\n" not in fixed

def test_edge_case_no_trailing_newline():
    """Test handling when the file doesn't end with a newline."""
    code = "import os\nimport sys\nimport os"  # No trailing newline
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1

def test_three_or_more_duplicates():
    """Test handling of three or more identical imports."""
    code = (
        "import os\n"
        "import os\n"    # duplicate 1
        "import os\n"    # duplicate 2
        "import os\n"    # duplicate 3
        "import sys\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    
    fixed = apply_fixes(code, res.findings)
    assert fixed.count("import os") == 1
    assert "import sys" in fixed

