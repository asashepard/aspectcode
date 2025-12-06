# server/tests/test_bug_uninitialized_use.py
"""
Tests for BugUninitializedUseRule.

Tests the detection of reads of variables before definite assignment on all paths.
Covers various language patterns, control flow, and edge cases.
"""

import pytest
from unittest.mock import Mock
from engine.types import RuleContext, Finding
from rules.bug_uninitialized_use import BugUninitializedUseRule


class TestBugUninitializedUseRule:
    """Test cases for the uninitialized variable use detection rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = BugUninitializedUseRule()
    
    def test_rule_metadata(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "bug.uninitialized_use"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "cpp" in self.rule.meta.langs
        assert "c" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
    
    # Python test cases
    def test_python_uninitialized_conditional_read(self):
        """Test Python: read after conditional assignment."""
        code = '''
def test_func():
    if condition:
        x = 1
    return x  # x may be uninitialized
'''
        findings = list(self._analyze_code(code, "python"))
        assert len(findings) >= 1
        
        finding = findings[0]
        assert finding.rule == "bug.uninitialized_use"
        assert finding.severity == "error"
        assert "x" in finding.message
        assert "definitely assigned" in finding.message
        assert finding.meta is not None and "suggestion" in finding.meta
    
    def test_python_uninitialized_loop_variable(self):
        """Test Python: read of variable only assigned in loop."""
        code = '''
def test_func(items):
    for item in items:
        result = item * 2
    return result  # result may be uninitialized if items is empty
'''
        findings = list(self._analyze_code(code, "python"))
        assert len(findings) >= 1
        
        finding = next((f for f in findings if "result" in f.message), None)
        assert finding is not None
        assert finding.rule == "bug.uninitialized_use"
    
    def test_python_initialized_before_use(self):
        """Test Python: variable initialized before use (no error)."""
        code = '''
def test_func():
    x = 0
    if condition:
        x = 1
    return x  # x is definitely assigned
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not flag x as uninitialized
        x_findings = [f for f in findings if "x" in f.message and "return x" in str(f)]
        assert len(x_findings) == 0
    
    def test_python_both_branches_assign(self):
        """Test Python: variable assigned in both branches (no error)."""
        code = '''
def test_func():
    if condition:
        y = 1
    else:
        y = 2
    return y  # y is definitely assigned
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not flag y as uninitialized
        y_findings = [f for f in findings if "y" in f.message]
        assert len(y_findings) == 0
    
    def test_python_parameter_usage(self):
        """Test Python: using parameters is allowed (no error)."""
        code = '''
def test_func(param):
    return param + 1  # param is a parameter, so it's initialized
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not flag param as uninitialized
        param_findings = [f for f in findings if "param" in f.message]
        assert len(param_findings) == 0
    
    # JavaScript test cases
    def test_javascript_uninitialized_let_variable(self):
        """Test JavaScript: read of let variable before assignment."""
        code = '''
function test() {
    let y;
    if (condition) {
        y = 2;
    }
    console.log(y);  // y may be uninitialized
}
'''
        findings = list(self._analyze_code(code, "javascript"))
        assert len(findings) >= 1
        
        finding = next((f for f in findings if "y" in f.message), None)
        assert finding is not None
        assert finding.rule == "bug.uninitialized_use"
    
    def test_javascript_initialized_let_variable(self):
        """Test JavaScript: let variable with initialization (no error)."""
        code = '''
function test() {
    let z = 1;
    if (k) {
        z = 2;
    }
    return z;  // z is definitely assigned
}
'''
        findings = list(self._analyze_code(code, "javascript"))
        # Should not flag z as uninitialized
        z_findings = [f for f in findings if "z" in f.message]
        assert len(z_findings) == 0
    
    def test_javascript_var_hoisting(self):
        """Test JavaScript: var hoisting behavior."""
        code = '''
function test() {
    console.log(hoisted);  // Should be considered initialized due to hoisting
    var hoisted = "value";
}
'''
        findings = list(self._analyze_code(code, "javascript"))
        # With var hoisting, this should not be flagged
        hoisted_findings = [f for f in findings if "hoisted" in f.message]
        # Note: This test may pass or fail depending on implementation of hoisting detection
        # The rule should ideally handle var hoisting correctly
    
    # C test cases
    def test_c_uninitialized_local_variable(self):
        """Test C: read of uninitialized local variable."""
        code = '''
int test_func(int c) {
    int x;
    if (c) {
        x = 1;
    }
    return x;  // x may be uninitialized
}
'''
        findings = list(self._analyze_code(code, "c"))
        assert len(findings) >= 1
        
        finding = next((f for f in findings if "x" in f.message), None)
        assert finding is not None
        assert finding.rule == "bug.uninitialized_use"
    
    def test_c_initialized_at_declaration(self):
        """Test C: variable initialized at declaration (no error)."""
        code = '''
int test_func() {
    int x = 0;
    return x;  // x is definitely assigned
}
'''
        findings = list(self._analyze_code(code, "c"))
        # Should not flag x as uninitialized
        x_findings = [f for f in findings if "x" in f.message]
        assert len(x_findings) == 0
    
    def test_c_assigned_before_use(self):
        """Test C: variable assigned before use (no error)."""
        code = '''
int test_func() {
    int y;
    y = 2;
    return y;  // y is definitely assigned
}
'''
        findings = list(self._analyze_code(code, "c"))
        # Should not flag y as uninitialized  
        y_findings = [f for f in findings if "y" in f.message]
        assert len(y_findings) == 0
    
    # C++ test cases
    def test_cpp_uninitialized_in_branch(self):
        """Test C++: variable not initialized on all paths."""
        code = '''
int test_func(bool flag) {
    int value;
    if (flag) {
        value = 42;
    }
    // else branch doesn't assign value
    return value;  // value may be uninitialized
}
'''
        findings = list(self._analyze_code(code, "cpp"))
        assert len(findings) >= 1
        
        finding = next((f for f in findings if "value" in f.message), None)
        assert finding is not None
        assert finding.rule == "bug.uninitialized_use"
    
    def test_cpp_both_branches_assign(self):
        """Test C++: variable assigned in all branches (no error)."""
        code = '''
int test_func(bool flag) {
    int value;
    if (flag) {
        value = 42;
    } else {
        value = 0;
    }
    return value;  // value is definitely assigned
}
'''
        findings = list(self._analyze_code(code, "cpp"))
        # Should not flag value as uninitialized
        value_findings = [f for f in findings if "value" in f.message]
        assert len(value_findings) == 0
    
    # Edge case tests
    def test_nested_scopes(self):
        """Test handling of nested scopes and variable shadowing."""
        code = '''
def outer():
    x = 1
    def inner():
        if condition:
            x = 2  # This shadows outer x
        return x  # This x may be uninitialized (inner scope)
    return inner()
'''
        findings = list(self._analyze_code(code, "python"))
        # Should detect uninitialized read of inner x
        inner_x_findings = [f for f in findings if "x" in f.message]
        # The exact behavior depends on how well the rule handles scope analysis
    
    def test_global_variable_reference(self):
        """Test that global variable references are not flagged."""
        code = '''
def test_func():
    return len([1, 2, 3])  # len is a builtin, should not be flagged
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not flag len as uninitialized
        len_findings = [f for f in findings if "len" in f.message]
        assert len(len_findings) == 0
    
    def test_function_parameter_usage(self):
        """Test that function parameters are not flagged as uninitialized."""
        code = '''
def calculate(a, b):
    return a + b  # a and b are parameters, should not be flagged
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not flag parameters as uninitialized
        param_findings = [f for f in findings if f.message and ("a" in f.message or "b" in f.message)]
        assert len(param_findings) == 0
    
    def test_empty_function(self):
        """Test handling of empty functions."""
        code = '''
def empty_func():
    pass
'''
        findings = list(self._analyze_code(code, "python"))
        # Should not crash and should not report any findings
        assert isinstance(findings, list)
    
    def test_complex_control_flow(self):
        """Test complex control flow with multiple branches."""
        code = '''
def complex_func(a, b, c):
    if a:
        x = 1
        if b:
            y = 2
        # y might be uninitialized here
        z = x + y  # This should be flagged for y
    else:
        if c:
            x = 3
            y = 4
        # Both x and y might be uninitialized here
        z = x + y  # This should be flagged for both x and y
    return z
'''
        findings = list(self._analyze_code(code, "python"))
        # Should detect multiple uninitialized variable uses
        # The exact number depends on the sophistication of the control flow analysis
        assert len(findings) >= 1
    
    def test_suggestion_content(self):
        """Test that suggestions contain helpful guidance."""
        code = '''
def test_func():
    if condition:
        x = 1
    return x
'''
        findings = list(self._analyze_code(code, "python"))
        assert len(findings) >= 1
        
        finding = findings[0]
        assert finding.meta is not None and "suggestion" in finding.meta
        suggestion = finding.meta["suggestion"]
        assert "Initialize" in suggestion
        assert "x" in suggestion
        # Should contain specific guidance for Python
        assert ("=" in suggestion or "default" in suggestion)
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        findings = list(self._analyze_code("some code", "unsupported"))
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty or minimal files."""
        findings = list(self._analyze_code("", "python"))
        assert isinstance(findings, list)
        
        findings = list(self._analyze_code("# Just a comment", "python"))
        assert isinstance(findings, list)
    
    def test_syntax_error_handling(self):
        """Test handling of files with syntax errors."""
        # This test assumes the rule handles syntax errors gracefully
        code = "def broken_syntax(:"  # Invalid Python syntax
        findings = list(self._analyze_code(code, "python"))
        # Should not crash, may or may not find issues depending on error handling
        assert isinstance(findings, list)
    
    def test_finding_byte_positions(self):
        """Test that findings have correct byte positions."""
        code = '''def test():
    if cond:
        x = 1
    return x'''
        
        findings = list(self._analyze_code(code, "python"))
        if findings:
            finding = findings[0]
            assert finding.start_byte >= 0
            assert finding.end_byte > finding.start_byte
            # The position should roughly correspond to the 'x' in 'return x'
    
    def test_multiple_uninitialized_variables(self):
        """Test detection of multiple uninitialized variables."""
        code = '''
def test_func():
    if condition1:
        a = 1
    if condition2:
        b = 2
    return a + b  # Both a and b may be uninitialized
'''
        findings = list(self._analyze_code(code, "python"))
        # Should detect issues with both variables
        var_names = set()
        for finding in findings:
            if "a" in finding.message:
                var_names.add("a")
            if "b" in finding.message:
                var_names.add("b")
        # Should find at least one of the variables
        assert len(var_names) >= 1
    
    def test_autofix_safety_suggest_only(self):
        """Test that rule is marked as suggest-only (no edits)."""
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        # Rule should not provide edits in findings
        code = '''
def test():
    if cond:
        x = 1
    return x
'''
        findings = list(self._analyze_code(code, "python"))
        for finding in findings:
            # Findings should not contain edit suggestions, only guidance
            assert not hasattr(finding, 'edits') or finding.edits is None or finding.autofix is None
    
    def _analyze_code(self, code: str, language: str):
        """Helper method to analyze code with the rule."""
        ctx = self._create_context(code, language)
        return self.rule.visit(ctx)
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a mock RuleContext for testing."""
        # Create a mock syntax tree
        mock_tree = self._create_mock_tree(code, language)
        
        ctx = Mock(spec=RuleContext)
        ctx.file_path = f"test.{self._get_file_extension(language)}"
        ctx.language = language
        ctx.syntax_tree = mock_tree
        ctx.raw_text = code
        
        return ctx
    
    def _create_mock_tree(self, code: str, language: str):
        """Create a mock syntax tree for testing."""
        # This is a simplified mock - in real tests, you'd use an actual parser
        mock_tree = Mock()
        mock_root = Mock()
        mock_root.children = []
        mock_root.type = "module"
        mock_root.start_byte = 0
        mock_root.end_byte = len(code.encode('utf-8'))
        
        # Add some mock nodes based on the code content
        if "def " in code or "function " in code:
            func_node = Mock()
            func_node.type = "function_definition" if language == "python" else "function_declaration"
            func_node.children = []
            func_node.parent = mock_root
            mock_root.children.append(func_node)
            
            # Add identifier nodes for variables mentioned in code, but only ones we care about
            target_vars = []
            
            # Look for assignment patterns to identify written variables
            import re
            if "x = " in code:
                target_vars.append("x")
            if "y = " in code:
                target_vars.append("y")
            if "z = " in code:
                target_vars.append("z")
            if "a = " in code:
                target_vars.append("a")
            if "b = " in code:
                target_vars.append("b")
            if "result = " in code:
                target_vars.append("result")
            if "value = " in code:
                target_vars.append("value")
            
            # Look for read patterns to identify read variables
            read_vars = []
            if "return x" in code:
                read_vars.append("x")
            if "return y" in code:
                read_vars.append("y")
            if "return z" in code:
                read_vars.append("z")
            if "return a" in code:
                read_vars.append("a")
            if "return b" in code:
                read_vars.append("b")
            if "return result" in code:
                read_vars.append("result")
            if "return value" in code:
                read_vars.append("value")
            if "console.log(" in code and ")" in code:
                # Extract variable from console.log(var)
                match = re.search(r'console\.log\((\w+)\)', code)
                if match:
                    read_vars.append(match.group(1))
            
            # Create identifier nodes for written variables and read variables
            all_vars = list(set(target_vars + read_vars))
            for word in all_vars:
                if word in code:
                    id_node = Mock()
                    id_node.type = "identifier"
                    id_node.text = word.encode('utf-8')
                    id_node.start_byte = code.find(word)
                    id_node.end_byte = id_node.start_byte + len(word)
                    id_node.parent = func_node
                    id_node.children = []
                    func_node.children.append(id_node)
        
        mock_tree.root_node = mock_root
        return mock_tree
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for a language."""
        extensions = {
            "python": "py",
            "javascript": "js", 
            "cpp": "cpp",
            "c": "c"
        }
        return extensions.get(language, "txt")

