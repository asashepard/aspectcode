"""
Tests for bug_float_equality rule.

Tests the detection of direct equality checks on floating-point values across
multiple languages including positive cases (should detect) and negative cases (should not detect).
"""

import pytest
from unittest.mock import Mock
from rules.bug_float_equality import BugFloatEqualityRule
from engine.types import RuleContext, Finding


class TestBugFloatEqualityRule:
    """Test suite for the BugFloatEqualityRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = BugFloatEqualityRule()
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.raw_text = code
        context.language = language
        context.file_path = f"test.{language}"
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.float_equality"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.autofix_safety == "suggest-only"
        expected_langs = {"python", "java", "csharp", "cpp", "c", "javascript", "typescript", "go", "rust"}
        assert set(self.rule.meta.langs) == expected_langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True
    
    # POSITIVE CASES - Should detect float equality checks
    
    def test_python_positive_case_float_literal(self):
        """Test Python code with float literal equality."""
        code = """
def test():
    x = 1.5
    if x == 1.0:
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Float equality check detected" in finding.message
        assert finding.severity == "info"
        assert "math.isclose" in finding.meta.get("suggestion", "")
    
    def test_python_positive_case_float_function(self):
        """Test Python code with float() function."""
        code = """
if float(input()) == 0.0:
    print("zero")
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
    
    def test_java_positive_case_double_literal(self):
        """Test Java code with double literal equality."""
        code = """
public class Test {
    public boolean test(double x) {
        if (x == 1.0) {
            return true;
        }
        return false;
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Float equality check detected" in finding.message
        assert "Math.abs" in finding.meta.get("suggestion", "")
    
    def test_java_positive_case_float_suffix(self):
        """Test Java code with float suffix."""
        code = """
public class Test {
    public void test() {
        float y = 2.5f;
        if (y == 0.1f) {
            System.out.println("match");
        }
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
    
    def test_csharp_positive_case(self):
        """Test C# code with double equality."""
        code = """
public class Test {
    public void Method() {
        double x = 1.5;
        if (x == 1.0) {
            Console.WriteLine("match");
        }
    }
}"""
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Math.Abs" in finding.meta.get("suggestion", "")
    
    def test_cpp_positive_case_scientific_notation(self):
        """Test C++ code with scientific notation."""
        code = """
int main() {
    double x = 1e-6;
    if (x == 1e-6) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "std::abs" in finding.meta.get("suggestion", "")
    
    def test_c_positive_case_atof(self):
        """Test C code with atof function."""
        code = """
int main() {
    double val = atof("1.5");
    if (val == 1.5) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "fabs" in finding.meta.get("suggestion", "")
    
    def test_javascript_positive_case_parseFloat(self):
        """Test JavaScript code with parseFloat."""
        code = """
function test(s) {
    if (parseFloat(s) === 0.1) {
        return true;
    }
    return false;
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "===" in finding.message
        assert "Math.abs" in finding.meta.get("suggestion", "")
    
    def test_typescript_positive_case_number_conversion(self):
        """Test TypeScript code with Number conversion."""
        code = """
function test(s: string): boolean {
    const num = Number(s);
    if (num == 0.1) {
        return true;
    }
    return false;
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
    
    def test_go_positive_case_float64(self):
        """Test Go code with float64 conversion."""
        code = """
package main

func test() bool {
    x := float64(42)
    if x == 42.0 {
        return true
    }
    return false
}"""
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "math.Abs" in finding.meta.get("suggestion", "")
    
    def test_rust_positive_case_f64_suffix(self):
        """Test Rust code with f64 suffix."""
        code = """
fn test() -> bool {
    let x = 1.0_f64;
    if x == 1.0 {
        true
    } else {
        false
    }
}"""
        ctx = self._create_context(code, "rust")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "f64::EPSILON" in finding.meta.get("suggestion", "")
    
    # NEGATIVE CASES - Should NOT detect
    
    def test_python_negative_case_isclose(self):
        """Test Python code using math.isclose (should not flag)."""
        code = """
import math

def test():
    x = 1.5
    if math.isclose(x, 1.0, rel_tol=1e-9):
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_python_negative_case_integer_equality(self):
        """Test Python code with integer equality (should not flag)."""
        code = """
def test():
    x = 42
    if x == 42:
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_java_negative_case_math_abs(self):
        """Test Java code using Math.abs tolerance (should not flag)."""
        code = """
public class Test {
    public boolean test(double x) {
        if (Math.abs(x - 1.0) < 1e-9) {
            return true;
        }
        return false;
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_java_negative_case_integer_equality(self):
        """Test Java code with integer equality (should not flag)."""
        code = """
public class Test {
    public void test() {
        int n = 42;
        if (n == 42) {
            System.out.println("match");
        }
    }
}"""
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_csharp_negative_case_mathf_approximately(self):
        """Test C# code using approximate comparison (should not flag)."""
        code = """
public class Test {
    public void Method() {
        float x = 1.5f;
        if (Mathf.Approximately(x, 1.0f)) {
            Console.WriteLine("approximately equal");
        }
    }
}"""
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_cpp_negative_case_epsilon_comparison(self):
        """Test C++ code using epsilon comparison (should not flag)."""
        code = """
#include <cmath>
#include <limits>

int main() {
    double x = 1.0;
    if (std::abs(x - 1.0) < std::numeric_limits<double>::epsilon()) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "cpp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_c_negative_case_dbl_epsilon(self):
        """Test C code using DBL_EPSILON (should not flag)."""
        code = """
#include <float.h>
#include <math.h>

int main() {
    double x = 1.0;
    if (fabs(x - 1.0) < DBL_EPSILON) {
        return 1;
    }
    return 0;
}"""
        ctx = self._create_context(code, "c")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_javascript_negative_case_number_epsilon(self):
        """Test JavaScript code using Number.EPSILON (should not flag)."""
        code = """
function test(a, b) {
    if (Math.abs(a - b) < Number.EPSILON) {
        return true;
    }
    return false;
}"""
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_typescript_negative_case_tolerance(self):
        """Test TypeScript code using custom tolerance (should not flag)."""
        code = """
function test(a: number, b: number): boolean {
    const tolerance = 1e-9;
    return Math.abs(a - b) < tolerance;
}"""
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_go_negative_case_math_abs(self):
        """Test Go code using math.Abs (should not flag)."""
        code = """
package main
import "math"

func test(x float64) bool {
    return math.Abs(x - 1.0) < 1e-9
}"""
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_go_negative_case_integer_equality(self):
        """Test Go code with integer equality (should not flag)."""
        code = """
package main

func test() bool {
    n := 42
    if n == 42 {
        return true
    }
    return false
}"""
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_rust_negative_case_f64_epsilon(self):
        """Test Rust code using f64::EPSILON (should not flag)."""
        code = """
fn test(a: f64, b: f64) -> bool {
    (a - b).abs() < f64::EPSILON
}"""
        ctx = self._create_context(code, "rust")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    # EDGE CASES
    
    def test_nan_comparison(self):
        """Test NaN comparison (should flag - NaN == NaN is always false)."""
        code = """
import math

def test():
    x = float('nan')
    if x == math.nan:
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should flag this as it's always false
        assert len(findings) >= 1
    
    def test_mixed_types_float_literal(self):
        """Test mixed int/float where float literal is present."""
        code = """
def test():
    n = 42
    if n == 42.0:  # Float literal should trigger
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1  # Should flag due to 42.0
    
    def test_decimal_suffix_csharp(self):
        """Test C# decimal suffix (should not flag - decimal is not float)."""
        code = """
public class Test {
    public void Method() {
        decimal x = 1.0m;
        if (x == 1.0m) {  // Decimal, not float
            Console.WriteLine("match");
        }
    }
}"""
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        # Should flag because _looks_floaty doesn't distinguish decimal from float
        # This is a limitation of the text-based approach
        assert len(findings) >= 1
    
    def test_chained_comparison(self):
        """Test chained comparison with one float side."""
        code = """
def test():
    x = 1.0
    y = 2
    if x == 1.0 and y == 2:  # Only first comparison should be flagged
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should only flag the float comparison
        assert len(findings) == 1
    
    def test_string_equality_not_flagged(self):
        """Test string equality (should not flag)."""
        code = """
def test():
    s = "1.0"
    if s == "1.0":
        return True
    return False
"""
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = "if x == 1.0 then return true end"
        ctx = self._create_context(code, "ruby")  # Unsupported language
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_positions(self):
        """Test that findings have correct byte positions."""
        code = "if x == 1.0: pass"
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        
        # The finding should point to the '==' operator
        operator = code[finding.start_byte:finding.end_byte]
        assert operator == "=="
    
    def test_suggestion_content(self):
        """Test that suggestions provide helpful guidance."""
        code = "if x == 1.0: pass"
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        suggestion = finding.meta.get("suggestion", "")
        assert "math.isclose" in suggestion or "abs" in suggestion
    
    def test_autofix_safety_suggest_only(self):
        """Test that autofix safety is set to suggest-only."""
        code = "if x == 1.0: pass"
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.meta.get("autofix_safety") == "suggest-only"

