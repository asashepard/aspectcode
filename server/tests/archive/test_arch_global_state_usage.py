"""Tests for arch_global_state_usage rule."""

import pytest
from typing import List

try:
    from ..rules.arch_global_state_usage import ArchGlobalStateUsageRule
    from ..engine.types import RuleContext, Finding
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from rules.arch_global_state_usage import ArchGlobalStateUsageRule
    from engine.types import RuleContext, Finding


class MockAdapter:
    """Mock adapter for testing syntax-based rules."""
    def __init__(self, language_id: str):
        self.language_id = language_id


class MockNode:
    """Mock tree-sitter node for testing."""
    def __init__(self, node_type: str = "", text: str = "", start_byte: int = 0, end_byte: int = 0, children=None, parent=None, **kwargs):
        self.type = node_type
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte > start_byte else start_byte + len(text)
        self.children = children or []
        self.parent = parent
        
        # Set additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Set parent references for children
        for child in self.children:
            child.parent = self


class MockTree:
    """Mock syntax tree."""
    def __init__(self, root_node):
        self.root_node = root_node
        
    def node_span(self, node):
        """Return node span."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 10))


class MockRuleContext:
    """Mock context for testing."""
    def __init__(self, code: str, file_path: str, language: str):
        self.text = code
        self.file_path = file_path
        self.language = language
        self.adapter = MockAdapter(language)
        self.syntax = MockTree(self._create_mock_tree(code, language))
        self.scopes = None  # Mock scopes if needed
        self.raw_text = code
    
    def _create_mock_tree(self, code: str, language: str):
        """Create a mock syntax tree based on the code and language."""
        
        # Python global state mutation
        if language == "python" and "STATE[" in code and "def " in code:
            # Find the assignment
            state_pos = code.find("STATE[")
            state_end = code.find("]", state_pos) + 1
            
            # Create assignment node
            assignment_node = MockNode(
                "assignment_expression",
                "STATE[\"x\"] = 1",
                state_pos, state_end + 4,
                left=MockNode("identifier", "STATE", state_pos, state_pos + 5)
            )
            
            # Create function node
            func_node = MockNode(
                "function_definition",
                code, 0, len(code),
                children=[assignment_node],
                name=MockNode("identifier", "f")
            )
            assignment_node.parent = func_node
            return func_node
            
        # Java singleton access
        elif language == "java" and "getInstance" in code:
            # Find getInstance call
            get_pos = code.find("getInstance")
            get_end = get_pos + len("getInstance")
            
            call_node = MockNode(
                "method_invocation",
                "MySingleton.getInstance()",
                get_pos - 12, get_end + 2,
                callee=MockNode("member_expression", "MySingleton.getInstance", get_pos - 12, get_end)
            )
            
            # Create class/method context
            method_node = MockNode(
                "method_declaration",
                code, 0, len(code),
                children=[call_node],
                name=MockNode("identifier", "f")
            )
            call_node.parent = method_node
            return method_node
            
        # JavaScript/TypeScript global object access
        elif language in ["javascript", "typescript"] and ("window." in code or "globalThis." in code):
            # Create assignment expressions for both window and globalThis
            assignments = []
            
            if "window." in code:
                window_pos = code.find("window.")
                window_end = code.find(";", window_pos) if ";" in code[window_pos:] else len(code)
                assignments.append(MockNode(
                    "assignment_expression",
                    code[window_pos:window_end].strip(),
                    window_pos, window_end,
                    left=MockNode("member_expression", "window.appState", window_pos, window_pos + 15)
                ))
            
            if "globalThis." in code:
                global_pos = code.find("globalThis.")
                global_end = code.find(";", global_pos) if ";" in code[global_pos:] else len(code)
                assignments.append(MockNode(
                    "assignment_expression", 
                    code[global_pos:global_end].strip(),
                    global_pos, global_end,
                    left=MockNode("member_expression", "globalThis.cache", global_pos, global_pos + 16)
                ))
            
            func_node = MockNode(
                "function_declaration",
                code, 0, len(code),
                children=assignments,
                name=MockNode("identifier", "f")
            )
            for assignment in assignments:
                assignment.parent = func_node
            return func_node
            
        # Swift singleton access
        elif language == "swift" and ".standard" in code:
            standard_pos = code.find(".standard")
            standard_end = standard_pos + 9
            
            access_node = MockNode(
                "member_expression",
                "UserDefaults.standard",
                standard_pos - 12, standard_end,
                property=MockNode("identifier", "standard", standard_pos + 1, standard_end)
            )
            
            func_node = MockNode(
                "function_declaration",
                code, 0, len(code),
                children=[access_node],
                name=MockNode("identifier", "f")
            )
            access_node.parent = func_node
            return func_node
            
        # C++ singleton access
        elif language == "cpp" and "Instance()" in code:
            instance_pos = code.find("Instance()")
            instance_end = instance_pos + 10
            
            call_node = MockNode(
                "call_expression",
                "Logger::Instance()",
                instance_pos - 8, instance_end,
                callee=MockNode("qualified_identifier", "Logger::Instance", instance_pos - 8, instance_pos + 8)
            )
            
            func_node = MockNode(
                "function_definition",
                code, 0, len(code),
                children=[call_node],
                name=MockNode("identifier", "f")
            )
            call_node.parent = func_node
            return func_node
            
        # Go global access
        elif language == "go" and "Global[" in code:
            global_pos = code.find("Global[")
            global_end = code.find("]", global_pos) + 1
            assignment_end = code.find("1", global_end) + 1
            
            assignment_node = MockNode(
                "assignment_expression",
                code[global_pos:assignment_end],
                global_pos, assignment_end,
                left=MockNode("identifier", "Global", global_pos, global_pos + 6)
            )
            
            func_node = MockNode(
                "function_declaration",
                code, 0, len(code),
                children=[assignment_node],
                name=MockNode("identifier", "F")
            )
            assignment_node.parent = func_node
            return func_node
            
        # Rust static mut access
        elif language == "rust" and "STATE = " in code:
            state_pos = code.find("STATE = ")
            state_end = state_pos + 9  # "STATE = 1"
            
            assignment_node = MockNode(
                "assignment_expression",
                "STATE = 1",
                state_pos, state_end,
                left=MockNode("identifier", "STATE", state_pos, state_pos + 5)
            )
            
            func_node = MockNode(
                "function_item",
                code, 0, len(code),
                children=[assignment_node],
                name=MockNode("identifier", "f")
            )
            assignment_node.parent = func_node
            return func_node
            
        # Default: empty node for negative cases
        return MockNode("source_file", code, 0, len(code))


class TestArchGlobalStateUsageRule:
    """Test cases for ArchGlobalStateUsageRule."""
    
    def setup_method(self):
        """Set up test rule instance."""
        self.rule = ArchGlobalStateUsageRule()

    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "arch.global_state_usage"
        assert self.rule.meta.category == "arch"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.priority == "P3"  # Lowered - architectural suggestion
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert len(self.rule.meta.langs) == 11

    def test_python_global_state_mutation(self):
        """Test detection of global state mutation in Python."""
        code = """
STATE = {}
def f():
    STATE["x"] = 1  # global mutation
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Global state access detected" in f.message for f in findings)

    def test_java_singleton_access(self):
        """Test detection of singleton access in Java."""
        code = """
class A {
    void f() {
        var log = LogManager.getLogManager();
        var i = MySingleton.getInstance();
    }
}
"""
        ctx = MockRuleContext(code, "Test.java", "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Singleton/service-locator usage" in f.message for f in findings)

    def test_typescript_global_object_access(self):
        """Test detection of global object access in TypeScript."""
        code = """
function f() {
    window.appState = {};
    globalThis.cache = new Map();
}
"""
        ctx = MockRuleContext(code, "test.ts", "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Global state access detected" in f.message or 
                 "Singleton/service-locator usage" in f.message for f in findings)

    def test_swift_singleton_access(self):
        """Test detection of singleton access in Swift."""
        code = """
func f() {
    let d = UserDefaults.standard
    d.set(true, forKey:"x")
}
"""
        ctx = MockRuleContext(code, "test.swift", "swift")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Singleton/service-locator usage" in f.message for f in findings)

    def test_positive_case_multiple_languages(self):
        """Test positive cases across multiple languages."""
        test_cases = [
            ("python", "STATE = {}\ndef f():\n    STATE['x'] = 1"),
            ("java", "class A { void f(){ var i = MySingleton.getInstance(); } }"),
            ("typescript", "function f(){ window.appState = {}; }"),
            ("swift", "func f(){ let d = UserDefaults.standard; }"),
        ]
        
        total_findings = 0
        for lang, code in test_cases:
            ctx = MockRuleContext(code, f"test.{lang}", lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Expected at least 1 finding for {lang}, got {len(findings)}"
            total_findings += len(findings)
        
        assert total_findings >= 4

    def test_negative_case_dependency_injection(self):
        """Test that dependency injection patterns are not flagged."""
        # Python DI
        code = """
def f(state):
    state["x"] = 1
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_constructor_injection(self):
        """Test that constructor injection is not flagged."""
        # Java constructor injection
        code = """
final class Svc {
    private final Logger log;
    Svc(Logger log) {
        this.log = log;
    }
}
"""
        ctx = MockRuleContext(code, "Test.java", "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_factory_pattern(self):
        """Test that factory patterns are not flagged."""
        # TypeScript factory
        code = """
export function makeSvc(cfg: Cfg) {
    return new Svc(cfg);
}
"""
        ctx = MockRuleContext(code, "test.ts", "typescript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_csharp_di(self):
        """Test that C# dependency injection is not flagged."""
        code = """
public sealed class S {
    private readonly IClock _c;
    public S(IClock c) {
        _c = c;
    }
}
"""
        ctx = MockRuleContext(code, "Test.cs", "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_more_languages_positive_cpp(self):
        """Test C++ singleton detection."""
        code = """
Logger& Logger::Instance();
void f() {
    auto& g = Logger::Instance();
}
"""
        ctx = MockRuleContext(code, "test.cpp", "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Singleton/service-locator usage" in f.message for f in findings)

    def test_more_languages_positive_go(self):
        """Test Go global variable detection."""
        code = """
var Global = map[string]int{}
func F() {
    Global["a"] = 1
}
"""
        ctx = MockRuleContext(code, "test.go", "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Global state access detected" in f.message for f in findings)

    def test_more_languages_positive_rust(self):
        """Test Rust static mut detection."""
        code = """
static mut STATE: i32 = 0;
fn f() {
    unsafe {
        STATE = 1;
    }
}
"""
        ctx = MockRuleContext(code, "test.rs", "rust")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert any("Global state access detected" in f.message for f in findings)

    def test_constants_not_flagged(self):
        """Test that constants are not flagged."""
        # Python constants
        code = """
MAX_SIZE = 100
def f():
    size = MAX_SIZE  # Should not be flagged - constant
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        # Should have fewer findings since MAX_SIZE is a constant
        assert len(findings) == 0 or all("MAX_SIZE" not in f.message for f in findings)

    def test_module_level_access_not_flagged(self):
        """Test that module-level access is not flagged."""
        code = """
STATE = {}
CONFIG = STATE  # Module level - should not be flagged
"""
        ctx = MockRuleContext(code, "test.py", "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_unsupported_language(self):
        """Test that unsupported languages are ignored."""
        code = """
my $global = 42;
sub test {
    $global = 24;
}
"""
        ctx = MockRuleContext(code, "test.pl", "perl")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_no_syntax_tree(self):
        """Test handling when syntax tree is None."""
        ctx = MockRuleContext("", "test.py", "python")
        ctx.syntax = None
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

