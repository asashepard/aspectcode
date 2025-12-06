# server/tests/test_deadcode_commented_out_code.py
"""
Tests for deadcode.commented_out_code rule.

This module tests detection of commented-out code blocks and
verification of suggest-only behavior.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.deadcode_commented_out_code import DeadcodeCommentedOutCodeRule
from engine.types import RuleContext, Finding, Edit
from engine.python_adapter import PythonAdapter
from engine.javascript_adapter import JavaScriptAdapter
from engine.typescript_adapter import TypeScriptAdapter

def create_test_context(code: str, language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a RuleContext for testing."""
    # Choose appropriate adapter
    adapters = {
        "python": PythonAdapter(),
        "javascript": JavaScriptAdapter(), 
        "typescript": TypeScriptAdapter(),
        "java": JavaScriptAdapter(),  # Fallback for now
        "cpp": JavaScriptAdapter(),   # Fallback for now
        "c": JavaScriptAdapter(),     # Fallback for now
    }
    
    # Map language to file extension
    extensions = {
        "python": "py",
        "javascript": "js",
        "typescript": "ts",
        "java": "java",
        "cpp": "cpp",
        "c": "c"
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

RULE = DeadcodeCommentedOutCodeRule()

def test_positive_block_js():
    """Test detection of JavaScript commented-out code block."""
    code = (
        "function f(){return 1;}\n"
        "/*\n"
        "if (x) {\n"
        "  doWork();\n"
        "} else {\n"
        "  console.log(x);\n"
        "}\n"
        "*/\n"
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 1
    assert "commented-out code" in res.findings[0].message.lower()
    assert res.findings[0].meta is not None
    assert "diff" in res.findings[0].meta

def test_positive_python_multiple_lines():
    """Test detection of Python commented-out code with # comments."""
    code = (
        "def active_function():\n"
        "    return True\n"
        "\n"
        "# if condition:\n"
        "#     result = process_data()\n"
        "#     return result\n"
        "# else:\n"
        "#     raise ValueError('Invalid')\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    finding = res.findings[0]
    assert "commented-out code" in finding.message.lower()
    # For suggest-only rules, suggestions are in meta, not as fix
    assert finding.meta is not None
    assert "diff" in finding.meta

def test_positive_cpp_with_keywords():
    """Test detection of C++ commented-out code with strong keyword signals."""
    code = (
        "#include <iostream>\n"
        "int main() {\n"
        "  return 0;\n"
        "}\n"
        "/*\n"
        "class MyClass {\n"
        "  public:\n"
        "    void method() {\n"
        "      if (condition) {\n"
        "        doSomething();\n"
        "      }\n"
        "    }\n"
        "};\n"
        "*/\n"
    )
    res = run_rule(RULE, code, language="cpp")
    assert len(res.findings) == 1
    finding = res.findings[0]
    assert "commented-out code" in finding.message.lower()

def test_negative_docblock_java():
    """Test that JavaDoc blocks are not flagged as commented-out code."""
    code = (
        "/**\n"
        " * Copyright ACME Corp\n"
        " * This class provides utility methods for data processing.\n"
        " * Licensed under MIT License.\n"
        " */\n"
        "public class DataProcessor {}\n"
    )
    res = run_rule(RULE, code, language="java")
    assert len(res.findings) == 0

def test_negative_todo_comments():
    """Test that TODO/FIXME style comments are not flagged."""
    code = (
        "function processData() {\n"
        "  // TODO: optimize this algorithm\n"
        "  // FIXME: handle edge case when data is null\n"
        "  // NOTE: this is a temporary workaround\n"
        "  return data.process();\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 0

def test_negative_license_header():
    """Test that license headers are not flagged as commented-out code."""
    code = (
        "/*\n"
        " * Licensed under the Apache License, Version 2.0\n"
        " * Generated by code generator tool\n"
        " * Copyright 2023 Example Corp\n"
        " */\n"
        "package com.example;\n"
    )
    res = run_rule(RULE, code, language="java")
    assert len(res.findings) == 0

def test_negative_single_line_comment():
    """Test that single-line comments don't trigger (need minimum 2 lines)."""
    code = (
        "def main():\n"
        "    # return calculate_result()\n"
        "    pass\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 0

def test_negative_low_code_score():
    """Test that comments with insufficient code signals are ignored."""
    code = (
        "// This is just a regular comment\n"
        "// explaining what the next function does\n"
        "// in plain English without code\n"
        "function example() { return 1; }\n"
    )
    res = run_rule(RULE, code, language="javascript")
    assert len(res.findings) == 0

def test_consecutive_comment_grouping():
    """Test that consecutive comments are grouped into blocks properly."""
    code = (
        "function active() { return true; }\n"
        "\n"
        "// if (debug) {\n"
        "//   console.log('debug mode');\n"
        "// }\n"
        "\n"
        "// Another separate block\n"
        "// for (let i = 0; i < 10; i++) {\n"
        "//   process(i);\n"
        "// }\n"
    )
    res = run_rule(RULE, code, language="javascript")
    # Should detect 2 separate blocks of commented-out code
    assert len(res.findings) == 2

def test_mixed_comment_styles():
    """Test handling of mixed comment styles within same block."""
    code = (
        "int main() {\n"
        "  /* if (condition) {\n"
        "   *   doWork();\n"
        "   */ \n"
        "  // } else {\n"
        "  //   cleanup();\n"
        "  // }\n"
        "  return 0;\n"
        "}\n"
    )
    res = run_rule(RULE, code, language="c")
    # Should find at least one block (the first /* */ block)
    assert len(res.findings) >= 1

def test_suggest_only_behavior():
    """Test that the rule provides suggestions but doesn't edit directly."""
    code = (
        "def working_function():\n"
        "    return 42\n"
        "\n"
        "# def unused_function():\n"
        "#     result = complex_calculation()\n"
        "#     if result > 0:\n"
        "#         return result\n"
        "#     else:\n"
        "#         raise ValueError('Invalid result')\n"
    )
    res = run_rule(RULE, code, language="python")
    assert len(res.findings) == 1
    finding = res.findings[0]
    
    # For suggest-only rules, autofix should be None
    assert finding.autofix is None
    
    # Suggestions should be in meta
    assert finding.meta is not None
    assert "diff" in finding.meta
    assert "rationale" in finding.meta

@pytest.mark.skip(reason="suggest-only: rule provides suggestions, not edits")
def test_suggest_only():
    """Placeholder test - rule is suggest-only so no direct edits to test."""
    pass

