"""
Test suite for the BugBooleanBitwiseMisuseRule.

Tests the detection of bitwise operators (&, |) used in boolean contexts
where logical operators (&&, ||) are likely intended.
"""

import unittest
from unittest.mock import Mock, MagicMock
from typing import List

try:
    from ..rules.bug_boolean_bitwise_misuse import BugBooleanBitwiseMisuseRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.bug_boolean_bitwise_misuse import BugBooleanBitwiseMisuseRule
    from engine.types import RuleContext, Finding


class TestBugBooleanBitwiseMisuseRule(unittest.TestCase):
    """Test cases for the BugBooleanBitwiseMisuseRule."""

    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugBooleanBitwiseMisuseRule()

    def _create_context(self, code: str, language: str, file_path: str = "test.py") -> RuleContext:
        """Create a mock RuleContext for testing."""
        # Create mock adapter
        adapter = Mock()
        adapter.language_id = language

        # Create mock tree structure
        tree = Mock()
        root_node = self._create_mock_node_tree(code, language)
        tree.root_node = root_node

        # Create context
        ctx = Mock(spec=RuleContext)
        ctx.file_path = file_path
        ctx.text = code
        ctx.tree = tree
        ctx.adapter = adapter
        ctx.config = {}

        return ctx

    def _create_mock_node_tree(self, code: str, language: str):
        """Create a mock syntax tree that represents the given code."""
        # This is a simplified mock that focuses on the structures we need
        # In a real implementation, this would be much more complex

        root = Mock()
        root.type = "module"
        root.start_byte = 0
        root.end_byte = len(code)
        root.children = []

        # Look for control flow patterns and create appropriate nodes
        lines = code.split('\n')
        current_byte = 0

        for line in lines:
            line_start = current_byte
            current_byte += len(line) + 1  # +1 for newline

            stripped = line.strip()
            if not stripped:
                continue

            # Create control flow nodes
            if stripped.startswith('if ') or stripped.startswith('if('):
                if_node = self._create_if_node(line, line_start, language)
                if if_node:
                    root.children.append(if_node)
            elif stripped.startswith('while ') or stripped.startswith('while('):
                while_node = self._create_while_node(line, line_start, language)
                if while_node:
                    root.children.append(while_node)
            elif stripped.startswith('for ') or stripped.startswith('for('):
                for_node = self._create_for_node(line, line_start, language)
                if for_node:
                    root.children.append(for_node)

        return root

    def _create_if_node(self, line: str, start_byte: int, language: str):
        """Create a mock if statement node."""
        node = Mock()
        node.type = "if_statement"
        node.start_byte = start_byte
        node.end_byte = start_byte + len(line)
        node.children = []

        # Extract condition
        condition_text = self._extract_condition_from_line(line)
        if condition_text and ('&' in condition_text or '|' in condition_text):
            condition_node = self._create_condition_node(condition_text, start_byte, language)
            node.condition = condition_node
            node.children.append(condition_node)

        return node

    def _create_while_node(self, line: str, start_byte: int, language: str):
        """Create a mock while statement node."""
        node = Mock()
        node.type = "while_statement"
        node.start_byte = start_byte
        node.end_byte = start_byte + len(line)
        node.children = []

        # Extract condition
        condition_text = self._extract_condition_from_line(line)
        if condition_text and ('&' in condition_text or '|' in condition_text):
            condition_node = self._create_condition_node(condition_text, start_byte, language)
            node.condition = condition_node
            node.children.append(condition_node)

        return node

    def _create_for_node(self, line: str, start_byte: int, language: str):
        """Create a mock for statement node."""
        node = Mock()
        node.type = "for_statement"
        node.start_byte = start_byte
        node.end_byte = start_byte + len(line)
        node.children = []

        # Extract condition (for C-style for loops)
        condition_text = self._extract_condition_from_line(line)
        if condition_text and ('&' in condition_text or '|' in condition_text):
            condition_node = self._create_condition_node(condition_text, start_byte, language)
            node.condition = condition_node
            node.children.append(condition_node)

        return node

    def _extract_condition_from_line(self, line: str) -> str:
        """Extract the condition part from a control flow line."""
        # Simple regex-based extraction
        import re
        
        # For if/while/for statements, extract what's in parentheses or after keyword
        patterns = [
            r'(?:if|while|for)\s*\((.*?)\)',  # if (condition)
            r'(?:if|while|for)\s+([^:{\n]+)[:{\n]',  # if condition:
        ]
        
        for pattern in patterns:
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return ""

    def _create_condition_node(self, condition_text: str, line_start: int, language: str):
        """Create a mock condition node with binary expressions."""
        condition_node = Mock()
        condition_node.type = "condition"
        
        # Find the position of the condition within the line
        condition_start = line_start + condition_text.find(condition_text.strip())
        condition_node.start_byte = condition_start
        condition_node.end_byte = condition_start + len(condition_text)
        condition_node.children = []

        # Look for binary expressions with & or |
        if '&' in condition_text or '|' in condition_text:
            binary_expr = self._create_binary_expression_node(condition_text, condition_start, language)
            if binary_expr:
                condition_node.children.append(binary_expr)

        return condition_node

    def _create_binary_expression_node(self, expr_text: str, start_byte: int, language: str):
        """Create a mock binary expression node."""
        node = Mock()
        
        # Determine node type based on language
        if language == "python":
            node.type = "binary_operator"
        else:
            node.type = "binary_expression"
        
        node.start_byte = start_byte
        node.end_byte = start_byte + len(expr_text)
        node.children = []  # Initialize as empty list
        
        # Create mock operands
        if '&' in expr_text:
            parts = expr_text.split('&', 1)
        elif '|' in expr_text:
            parts = expr_text.split('|', 1)
        else:
            parts = [expr_text, ""]
        
        if len(parts) == 2:
            left_text = parts[0].strip()
            right_text = parts[1].strip()
            
            # Create left operand
            left_node = Mock()
            left_node.type = "comparison_operator" if any(op in left_text for op in ['==', '!=', '<', '>']) else "identifier"
            left_node.start_byte = start_byte
            left_node.end_byte = start_byte + len(left_text)
            left_node.children = []  # Ensure children is always a list
            
            # Create right operand
            right_node = Mock()
            right_node.type = "comparison_operator" if any(op in right_text for op in ['==', '!=', '<', '>']) else "identifier"
            right_node.start_byte = start_byte + len(left_text) + 1  # +1 for operator
            right_node.end_byte = right_node.start_byte + len(right_text)
            right_node.children = []  # Ensure children is always a list
            
            # Create operator node
            op_node = Mock()
            op_node.type = "operator"
            op_node.start_byte = start_byte + len(left_text)
            op_node.end_byte = op_node.start_byte + 1
            op_node.children = []
            
            node.left = left_node
            node.right = right_node
            node.children = [left_node, op_node, right_node]

        return node

    def test_debug_simple_python_case(self):
        """Debug test to understand what's happening."""
        code = """
if (x == 5) & (y == 10):
    pass
"""
        ctx = self._create_context(code, "python")
        
        # Debug what we created
        print(f"Root children: {len(ctx.tree.root_node.children)}")
        for i, child in enumerate(ctx.tree.root_node.children):
            print(f"Child {i}: type={getattr(child, 'type', 'None')}")
            if hasattr(child, 'condition'):
                cond = child.condition
                print(f"  Condition: type={getattr(cond, 'type', 'None')}")
                children = getattr(cond, 'children', [])
                print(f"  Condition children: {len(children) if hasattr(children, '__len__') else 'not iterable'}")
                if hasattr(children, '__iter__'):
                    for j, cond_child in enumerate(children):
                        print(f"    Child {j}: type={getattr(cond_child, 'type', 'None')}")
        
        findings = list(self.rule.visit(ctx))
        print(f"Findings: {len(findings)}")
        
        # This test is for debugging, so no assertion
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "bug.boolean_bitwise_misuse"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 7

    def test_requires_correct_capabilities(self):
        """Test that the rule requires the correct capabilities."""
        assert self.rule.requires.syntax is True

    # Positive test cases - should detect issues

    def test_python_positive_case_bitwise_and(self):
        """Test Python bitwise AND in boolean condition."""
        code = """
def test():
    x = 5
    y = 10
    if (x == 5) & (y == 10):
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "bug.boolean_bitwise_misuse"
        assert "bitwise operator" in findings[0].message.lower()
        assert findings[0].severity == "warn"

    def test_python_positive_case_bitwise_or(self):
        """Test Python bitwise OR in boolean condition."""
        code = """
def test():
    if (x > 0) | (y < 10):
        pass
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "bitwise operator" in findings[0].message.lower()

    def test_javascript_positive_case_strict_equality(self):
        """Test JavaScript bitwise in strict equality condition."""
        code = """
function test() {
    if ((a === 1) & (b !== 0)) {
        return true;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "bug.boolean_bitwise_misuse"

    def test_typescript_positive_case_while_loop(self):
        """Test TypeScript bitwise in while loop condition."""
        code = """
function process(): void {
    while ((isReady()) | (count === 0)) {
        // process
    }
}
"""
        ctx = self._create_context(code, "typescript", "test.ts")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_java_positive_case_predicate_calls(self):
        """Test Java bitwise with predicate method calls."""
        code = """
public boolean validate() {
    if (isValid() & hasPermission()) {
        return true;
    }
    return false;
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_csharp_positive_case_boolean_literals(self):
        """Test C# bitwise with boolean literals."""
        code = """
public bool Check() {
    if (true & (x > 5)) {
        return true;
    }
    return false;
}
"""
        ctx = self._create_context(code, "csharp", "Test.cs")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_cpp_positive_case_comparison_operators(self):
        """Test C++ bitwise with comparison operators."""
        code = """
bool check() {
    if ((x <= 10) & (y >= 5)) {
        return true;
    }
    return false;
}
"""
        ctx = self._create_context(code, "cpp", "test.cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    def test_c_positive_case_for_loop(self):
        """Test C bitwise in for loop condition."""
        code = """
int process() {
    for (int i = 0; (i < 10) & (flag == 1); i++) {
        // process
    }
    return 0;
}
"""
        ctx = self._create_context(code, "c", "test.c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1

    # Negative test cases - should NOT detect issues

    def test_python_negative_case_logical_operators(self):
        """Test Python with correct logical operators (should not flag)."""
        code = """
def test():
    if (x == 5) and (y == 10):
        return True
    if a or b:
        return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_javascript_negative_case_logical_operators(self):
        """Test JavaScript with correct logical operators (should not flag)."""
        code = """
function test() {
    if ((a === 1) && (b !== 0)) {
        return true;
    }
    if (x || y) {
        return false;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_bitwise_in_bitmask_context(self):
        """Test bitwise operators used for actual bitmasks (should not flag)."""
        code = """
function checkFlags() {
    if ((flags & MASK) !== 0) {
        return true;
    }
    if ((value & 0xFF) === expected) {
        return false;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag because these are legitimate bitwise operations
        assert len(findings) == 0

    def test_cpp_negative_case_bitmask_comparison(self):
        """Test C++ bitwise in bitmask comparison context (should not flag)."""
        code = """
bool checkBits() {
    if ((x & 1) == 0) {
        return true;
    }
    return false;
}
"""
        ctx = self._create_context(code, "cpp", "test.cpp")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag because this is legitimate bitwise operation
        assert len(findings) == 0

    def test_java_negative_case_integer_bitwise(self):
        """Test Java with integer bitwise operations (should not flag)."""
        code = """
public boolean check() {
    if ((num & mask) != 0) {
        return true;
    }
    return false;
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag because operands don't look boolean-like
        assert len(findings) == 0

    def test_no_control_flow_statements(self):
        """Test code without control flow statements (should not flag)."""
        code = """
def simple_function():
    x = a & b  # Variable assignment, not condition
    return x | y  # Return expression, not condition
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = """
if x & y then
    return true
end
"""
        ctx = self._create_context(code, "ruby")  # Unsupported language
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_empty_file_handling(self):
        """Test handling of empty files."""
        code = ""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = """
def test():
    if (a == 1) & (b == 2):
        pass
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        
        assert finding.rule == "bug.boolean_bitwise_misuse"
        assert finding.severity == "warning"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert finding.file == "test.py"
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte

    def test_suggestion_content_python(self):
        """Test suggestion content for Python."""
        code = """
if (a == 1) & (b == 2):
    pass
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta.get("suggestion", "")
        assert "and" in suggestion and "or" in suggestion

    def test_suggestion_content_other_languages(self):
        """Test suggestion content for non-Python languages."""
        code = """
function test() {
    if ((a === 1) & (b === 2)) {
        return true;
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        suggestion = findings[0].meta.get("suggestion", "")
        assert "&&" in suggestion  # Only expect the relevant operator replacement


if __name__ == "__main__":
    unittest.main()

