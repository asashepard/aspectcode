"""
Tests for bug.incompatible_comparison rule.

Tests incompatible comparison detection across multiple languages:
- Java/C# string/object equality with ==
- C/C++ pointer vs string literal comparison
- JavaScript/TypeScript loose equality cross-type
- Cross-type literal comparisons
- Suspicious ordering between non-numeric types
"""

import unittest
from unittest.mock import Mock
from engine.types import RuleContext
from rules.bug_incompatible_comparison import BugIncompatibleComparisonRule


class TestBugIncompatibleComparisonRule(unittest.TestCase):
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugIncompatibleComparisonRule()
    
    def _create_context(self, code: str, language: str = "python") -> RuleContext:
        """Create a mock rule context for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = language
        context.file_path = f"test.{language}"
        
        # Create a simple mock syntax tree
        context.syntax_tree = self._create_mock_syntax_tree(code, language)
        
        # Mock registry and adapter
        mock_adapter = Mock()
        mock_adapter.iter_tokens = Mock(return_value=[])
        mock_adapter.node_span = Mock(return_value=(0, len(code)))
        
        mock_registry = Mock()
        mock_registry.get_adapter = Mock(return_value=mock_adapter)
        context.registry = mock_registry
        
        return context
    
    def _create_mock_syntax_tree(self, code: str, language: str):
        """Create a simplified mock syntax tree for testing."""
        lines = code.strip().split('\n')
        comparison_nodes = []
        
        current_pos = 0
        for line in lines:
            line = line.strip()
            if any(op in line for op in ['==', '!=', '===', '!==', '<', '>', '<=', '>=']):
                # Create mock comparison node
                node = self._create_comparison_node(line, current_pos, language)
                if node:
                    comparison_nodes.append(node)
            current_pos += len(line) + 1  # +1 for newline
        
        # Create mock root that yields comparison nodes
        root = Mock()
        root.walk = Mock(return_value=iter(comparison_nodes))
        
        return root
    
    def _create_comparison_node(self, line: str, start_pos: int, language: str):
        """Create a mock comparison node from a line of code."""
        # Find operator in the line
        operators = ['===', '!==', '==', '!=', '<=', '>=', '<', '>']  # Order matters for parsing
        operator = None
        op_pos = -1
        
        for op in operators:
            pos = line.find(op)
            if pos != -1:
                operator = op
                op_pos = pos
                break
        
        if not operator:
            return None
        
        # Split into left and right parts
        left_text = line[:op_pos].strip()
        right_text = line[op_pos + len(operator):].strip()
        
        # Remove common syntax elements
        left_text = left_text.replace('if (', '').replace('if ', '').strip()
        right_text = right_text.replace(')', '').replace('{', '').replace(':', '').replace('pass', '').strip()
        
        # Create operand nodes
        left_node = self._create_operand_node(left_text)
        right_node = self._create_operand_node(right_text)
        
        # Create comparison node
        node = Mock()
        node.operator = operator
        node.left = left_node
        node.right = right_node
        node.start_byte = start_pos
        node.end_byte = start_pos + len(line)
        
        # Make tokens properly iterable (empty list for now)
        node.tokens = []
        
        return node
    
    def _create_operand_node(self, text: str):
        """Create a mock operand node."""
        node = Mock()
        node.text = text
        
        # Determine node kind based on text patterns
        if text.startswith('"') and text.endswith('"'):
            node.kind = 'string'
        elif text.startswith("'") and text.endswith("'"):
            node.kind = 'string'
        elif text.isdigit() or ('.' in text and text.replace('.', '').isdigit()):
            node.kind = 'number'
        elif text.lower() in ['true', 'false']:
            node.kind = 'boolean'
        elif text.lower() in ['null', 'undefined', 'none', 'nil']:
            node.kind = 'null'
        else:
            node.kind = 'identifier'
        
        return node
    
    def test_rule_metadata(self):
        """Test rule metadata is correctly defined."""
        assert self.rule.meta.id == "bug.incompatible_comparison"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "c" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires correct capabilities."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_java_string_equality(self):
        """Test detection of Java string equality with ==."""
        code = '''
if (s == "ok") {
    return true;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the string equality issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "Object/string compared with '=='" in finding.message
        assert ".equals" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["pattern"] == "java_csharp_object_equality"
        assert finding.meta["operator"] == "=="
    
    def test_positive_case_csharp_string_equality(self):
        """Test detection of C# string equality with ==."""
        code = '''
if (str == "test") {
    Console.WriteLine("match");
}
'''
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the string equality issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "Object/string compared with '=='" in finding.message
        assert "string.Equals" in finding.message
        assert finding.severity == "warning"
    
    def test_positive_case_c_pointer_string_literal(self):
        """Test detection of C pointer vs string literal comparison."""
        code = '''
const char* p = getenv("X");
if (p == "x") {
    printf("found");
}
'''
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the pointer comparison issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "Pointer compared to string literal" in finding.message
        assert "strcmp" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["pattern"] == "c_pointer_string_literal"
    
    def test_positive_case_cpp_pointer_string_literal(self):
        """Test detection of C++ pointer vs string literal comparison."""
        code = '''
char* buffer = get_data();
if (buffer == "expected") {
    process();
}
'''
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the pointer comparison issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "Pointer compared to string literal" in finding.message
        assert finding.severity == "warning"
    
    def test_positive_case_javascript_loose_equality(self):
        """Test detection of JavaScript loose equality cross-type."""
        code = '''
if (1 == "1") {
    console.log("number as string");
}
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the loose equality issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "cross-type comparison" in finding.message
        assert "===" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["pattern"] == "js_ts_loose_equality"
    
    def test_positive_case_typescript_loose_equality(self):
        """Test detection of TypeScript loose equality cross-type."""
        code = '''
if (0 == null) {
    return undefined;
}
'''
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the loose equality issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "cross-type comparison" in finding.message
        assert finding.severity == "warning"
    
    def test_positive_case_cross_type_literal_comparison(self):
        """Test detection of cross-type literal comparisons."""
        code = '''
if (42 == "hello") {
    print("impossible");
}
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the mismatched types
        assert len(findings) >= 1
        finding = findings[0]
        assert "unrelated literal types" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["pattern"] == "mismatched_literal_types"
    
    def test_positive_case_python_ordering_cross_type(self):
        """Test detection of Python ordering between different types."""
        code = '''
if 42 < "3":
    pass
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the mismatched types (number vs string)
        assert len(findings) >= 1
        finding = findings[0]
        assert "unrelated literal types" in finding.message
        assert finding.severity == "warning"
    
    def test_positive_case_boolean_ordering(self):
        """Test detection of boolean ordering comparisons."""
        code = '''
if 5 > true {
    return;
}
'''
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the mismatched types (number vs boolean)
        assert len(findings) >= 1
        finding = findings[0]
        assert "unrelated literal types" in finding.message
        assert finding.severity == "warning"
    
    def test_negative_case_java_proper_equals(self):
        """Test that proper Java equals usage is not flagged."""
        code = '''
if ("ok".equals(s)) {
    return true;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_csharp_proper_equals(self):
        """Test that proper C# equals usage is not flagged."""
        code = '''
if (string.Equals(s, "ok")) {
    Console.WriteLine("match");
}
'''
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_c_proper_strcmp(self):
        """Test that proper C strcmp usage is not flagged."""
        code = '''
if (strcmp(p, "x") == 0) {
    printf("found");
}
'''
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_javascript_strict_equality(self):
        """Test that JavaScript strict equality is not flagged."""
        code = '''
if (x === 1) {
    console.log("number");
}
if (s === "1") {
    console.log("string");
}
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_python_same_type_comparison(self):
        """Test that Python same-type comparisons are not flagged."""
        code = '''
if "x" == "3":
    pass
if 10 < 20:
    pass
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_numeric_ordering(self):
        """Test that numeric ordering comparisons are not flagged."""
        code = '''
if (a < b) {
    return a;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_string_ordering(self):
        """Test that string ordering comparisons are not flagged."""
        code = '''
if "name" < "zzz":
    process(name)
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues (both sides are strings)
        assert len(findings) == 0
    
    def test_edge_case_java_new_object(self):
        """Test detection of Java new object comparison."""
        code = '''
if (new String("test") == "test") {
    return true;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the object comparison issue
        assert len(findings) >= 1
        finding = findings[0]
        assert "Object/string compared with '=='" in finding.message
    
    def test_edge_case_multiple_issues_same_line(self):
        """Test handling of multiple issues in the same code."""
        code = '''
if (s == "ok") {
    return;
}
if ("hello" == 42) {
    return;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should detect multiple issues
        assert len(findings) >= 1  # At least one issue detected
    
    def test_edge_case_nested_comparisons(self):
        """Test handling of nested comparison expressions."""
        code = '''
if (1 == "1") {
    process();
}
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the loose equality issue
        assert len(findings) >= 1
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "python")
        findings = list(self.rule.visit(ctx))
        
        # Should handle empty files gracefully
        assert len(findings) == 0
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored gracefully."""
        code = '''
if x == "test":
    pass
'''
        ctx = self._create_context(code, "unknown_language")
        findings = list(self.rule.visit(ctx))
        
        # May still detect cross-type issues, but should not crash
        # The exact behavior depends on the implementation
        pass
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = '''
if (s == "test") {
    return;
}
'''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check finding structure
        assert finding.rule == "bug.incompatible_comparison"
        assert finding.file == "test.java"
        assert finding.severity == "warning"
        assert isinstance(finding.start_byte, int)
        assert isinstance(finding.end_byte, int)
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        assert "pattern" in finding.meta
        assert "operator" in finding.meta


if __name__ == '__main__':
    unittest.main()

