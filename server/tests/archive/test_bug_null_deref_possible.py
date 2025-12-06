"""
Tests for bug_null_deref_possible rule.

Tests the detection of possible null/None dereferences across multiple languages
including positive cases (should detect) and negative cases (should not detect).
"""

import pytest
from unittest.mock import Mock
from rules.bug_null_deref_possible import BugNullDerefPossibleRule
from engine.types import RuleContext, Finding


class TestBugNullDerefPossibleRule:
    """Test suite for the BugNullDerefPossibleRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = BugNullDerefPossibleRule()
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.raw_text = code
        context.language = language
        context.file_path = f"test.{language}"
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.null_deref_possible"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert set(self.rule.meta.langs) == {"java", "csharp", "cpp", "c", "python", "typescript"}
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
    
    # POSITIVE CASES - Should detect null dereferences
    
    def test_java_positive_case(self):
        """Test Java code with null dereference."""
        code = """
public class Test {
    public int test() {
        String s = map.get("key");
        return s.length();
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "null dereference" in finding.message
        assert "s" in finding.message
        assert finding.severity == "error"
    
    def test_csharp_positive_case(self):
        """Test C# code with null dereference."""
        code = """
public class Test {
    public int TestMethod() {
        var item = collection.FirstOrDefault();
        return item.Length;
    }
}"""
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "null dereference" in finding.message
        assert "item" in finding.message
    
    def test_cpp_positive_case(self):
        """Test C++ code with null dereference."""
        code = """
int test() {
    char* p = getenv("HOME");
    return *p;
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "null dereference" in finding.message
        assert "p" in finding.message
    
    def test_c_positive_case(self):
        """Test C code with null dereference."""
        code = """
int test() {
    char* p = getenv("HOME");
    return p[0];
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "NULL dereference" in finding.message
        assert "p" in finding.message
    
    def test_python_positive_case(self):
        """Test Python code with None dereference."""
        code = """
def test():
    x = os.getenv("HOME")
    return x.strip()
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "None dereference" in finding.message
        assert "x" in finding.message
    
    def test_typescript_positive_case(self):
        """Test TypeScript code with null dereference."""
        code = """
function test() {
    const n = map.get("key");
    return n.toString();
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "null/undefined dereference" in finding.message
        assert "n" in finding.message
    
    # NEGATIVE CASES - Should NOT detect (properly guarded)
    
    def test_java_negative_case_null_check(self):
        """Test Java code with proper null check."""
        code = """
public class Test {
    public int test() {
        String s = map.get("key");
        if (s != null) {
            return s.length();
        }
        return 0;
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect issues when properly guarded
        assert len(findings) == 0
    
    def test_csharp_negative_case_null_check(self):
        """Test C# code with proper null check."""
        code = """
public class Test {
    public int TestMethod() {
        var item = collection.FirstOrDefault();
        if (item != null) {
            return item.Length;
        }
        return 0;
    }
}"""
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_cpp_negative_case_null_check(self):
        """Test C++ code with proper null check."""
        code = """
int test() {
    char* p = getenv("HOME");
    if (p != nullptr) {
        return *p;
    }
    return 0;
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_c_negative_case_null_check(self):
        """Test C code with proper null check."""
        code = """
int test() {
    char* p = getenv("HOME");
    if (p != NULL) {
        return p[0];
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_python_negative_case_none_check(self):
        """Test Python code with proper None check."""
        code = """
def test():
    x = os.getenv("HOME")
    if x is not None:
        return x.strip()
    return ""
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_typescript_negative_case_optional_chaining(self):
        """Test TypeScript code with optional chaining."""
        code = """
function test() {
    const n = map.get("key");
    return n?.toString();
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_typescript_negative_case_null_check(self):
        """Test TypeScript code with proper null check."""
        code = """
function test() {
    const n = map.get("key");
    if (n != null) {
        return n.toString();
    }
    return "";
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    # EDGE CASES
    
    def test_direct_null_assignment(self):
        """Test direct null assignment followed by dereference."""
        code = """
String s = null;
return s.length();
"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert "s" in findings[0].message
    
    def test_reassignment_clears_null(self):
        """Test that reassignment to non-null clears the warning."""
        code = """
String s = map.get("key");
s = "hello";
return s.length();
"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should not warn because s is reassigned to non-null
        assert len(findings) == 0
    
    def test_multiple_variables(self):
        """Test tracking multiple potentially null variables."""
        code = """
def test():
    x = os.getenv("X")
    y = os.getenv("Y")
    return x.strip() + y.upper()
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect both x.strip() and y.upper()
        assert len(findings) >= 2
        variables = {f.message for f in findings}
        assert any("x" in msg for msg in variables)
        assert any("y" in msg for msg in variables)
    
    def test_same_line_guard(self):
        """Test that same-line null guards protect dereferences."""
        code = """
return (s != null) ? s.length() : 0;
"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # Should not warn due to same-line guard
        assert len(findings) == 0
    
    def test_assertion_guards(self):
        """Test that assertions are recognized as guards."""
        code = """
def test():
    x = os.getenv("HOME")
    assert x is not None
    return x.strip()
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_pointer_member_access(self):
        """Test C/C++ pointer member access."""
        code = """
struct Point {
    int x, y;
};

int test() {
    struct Point* p = malloc(sizeof(struct Point));
    return p->x;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert "p" in findings[0].message
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = "let x = null; return x.foo();"
        ctx = self._create_context(code, "rust")  # Unsupported language
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_positions(self):
        """Test that findings have correct byte positions."""
        code = """String s = map.get("key");
return s.length();"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        
        # The finding should point to the dereference
        deref_text = code[finding.start_byte:finding.end_byte]
        assert "s." in deref_text or "s.length" in deref_text
    
    def test_suggestion_content(self):
        """Test that suggestions provide helpful guidance."""
        code = """
def test():
    x = os.getenv("HOME")
    return x.strip()
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "meta" in finding.__dict__ or hasattr(finding, "meta")
        if hasattr(finding, "meta") and finding.meta:
            suggestion = finding.meta.get("suggestion", "")
            assert "is not None" in suggestion or "null check" in suggestion
    
    def test_autofix_safety_suggest_only(self):
        """Test that autofix safety is set to suggest-only."""
        code = "String s = null; return s.length();"
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        if hasattr(finding, "meta") and finding.meta:
            assert finding.meta.get("autofix_safety") == "suggest-only"

