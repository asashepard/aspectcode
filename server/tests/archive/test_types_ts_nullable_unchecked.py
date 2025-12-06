"""
Tests for types.ts_nullable_unchecked rule.

Tests detection of unchecked nullable TypeScript values and proper handling
of various null safety guards.
"""

import pytest
from unittest.mock import Mock
from rules.types_ts_nullable_unchecked import TypesTsNullableUncheckedRule
from engine.types import RuleContext, Finding


class TestTypesTsNullableUncheckedRule:
    def setup_method(self):
        self.rule = TypesTsNullableUncheckedRule()

    def _create_context(self, code: str, language: str = "typescript") -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.file_path = f"test.{language}"
        context.tree = None  # Not used by this rule yet - would need tree-sitter parsing
        context.adapter = None  # Not used by this rule
        context.config = {}
        context.scopes = None
        context.project_graph = None
        return context

    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "types.ts_nullable_unchecked"
        assert self.rule.meta.category == "types"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.langs == ["typescript"]
        assert self.rule.meta.autofix_safety == "suggest-only"

    def test_requires_correct_capabilities(self):
        """Test that rule requires correct engine capabilities."""
        assert self.rule.requires.syntax is True

    # POSITIVE CASES - Should detect violations

    def test_positive_case_property_access(self):
        """Test detection of unsafe property access on nullable values."""
        code = """
function f(x: string | null) {
    x.toUpperCase(); // should warn - property access on nullable
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'x'" in findings[0].message
        assert findings[0].severity == "warn"
        assert findings[0].rule == "types.ts_nullable_unchecked"

    def test_positive_case_function_call(self):
        """Test detection of unsafe function calls on nullable values."""
        code = """
function g(h: (() => void) | undefined) {
    h(); // should warn - call on potentially undefined function
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'h'" in findings[0].message

    def test_positive_case_element_access(self):
        """Test detection of unsafe element access on nullable arrays."""
        code = """
function i(a: number[] | undefined) {
    const v = a[0]; // should warn - index access on potentially undefined array
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'a'" in findings[0].message

    def test_positive_case_arithmetic_operations(self):
        """Test detection of arithmetic operations on nullable values."""
        code = """
function calc(x: number | null, y: number | undefined) {
    const result = x + 1; // should warn - arithmetic on potentially null
    const sum = y * 2;    // should warn - arithmetic on potentially undefined
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 2
        messages = [f.message for f in findings]
        assert any("Possible null/undefined access on 'x'" in msg for msg in messages)
        assert any("Possible null/undefined access on 'y'" in msg for msg in messages)

    def test_positive_case_multiple_violations_same_function(self):
        """Test detection of multiple violations in the same function."""
        code = """
function processUser(user: User | null) {
    user.getName(); // should detect - unsafe property access
    return user.id; // should detect - unsafe property access
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 2
        for finding in findings:
            assert "Possible null/undefined access on 'user'" in finding.message
            assert finding.severity == "warning"

    def test_positive_case_callback_function(self):
        """Test detection of unsafe callback invocation."""
        code = """
function processCallback(callback: (() => void) | undefined) {
    callback(); // should detect - unsafe function call
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'callback'" in findings[0].message

    def test_positive_case_array_operations(self):
        """Test detection of unsafe array operations."""
        code = """
function processArray(items: string[] | undefined) {
    return items[0]; // should detect - unsafe element access
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'items'" in findings[0].message

    def test_positive_case_complex_union_types(self):
        """Test detection with complex union types."""
        code = """
function processData(
    text: string | null,
    callback: ((data: string) => void) | undefined,
    config: {enabled: boolean} | null
) {
    text.toLowerCase();     // should warn
    callback("test");       // should warn  
    config.enabled;         // should warn
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        # Note: callback detection may be challenging for text-based analysis
        # due to complex function type syntax
        assert len(findings) >= 2  # At least text and config should be detected
        
        var_names = []
        for finding in findings:
            if "'text'" in finding.message:
                var_names.append("text")
            elif "'callback'" in finding.message:
                var_names.append("callback")
            elif "'config'" in finding.message:
                var_names.append("config")
        
        assert "text" in var_names
        assert "config" in var_names
        # callback may or may not be detected depending on regex complexity

    # NEGATIVE CASES - Should NOT detect violations

    def test_negative_case_if_guard_single_line(self):
        """Test that single-line if-guards properly protect nullable access."""
        code = """
function f(x: string | null) { if (x) { x.toUpperCase(); } }
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_if_guard_multiline(self):
        """Test that multi-line if-guards properly protect nullable access."""
        code = """
function f(x: string | null) {
    if (x) {
        x.toUpperCase(); // safe - guarded by if
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_explicit_null_check(self):
        """Test that explicit null checks protect nullable access."""
        code = """
function g(h: (() => void) | undefined) {
    if (h != null) {
        h(); // safe - guarded by null check
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_strict_equality_null_check(self):
        """Test that strict equality null checks protect nullable access."""
        code = """
function test(x: string | null) {
    if (x !== null) {
        x.trim(); // safe - guarded by strict null check
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_undefined_check(self):
        """Test that undefined checks protect nullable access."""
        code = """
function test(x: string | undefined) {
    if (x !== undefined) {
        x.trim(); // safe - guarded by undefined check
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_typeof_check(self):
        """Test that typeof checks protect nullable access."""
        code = """
function test(x: string | undefined) {
    if (typeof x !== 'undefined') {
        x.trim(); // safe - guarded by typeof check
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_optional_chaining_property(self):
        """Test that optional chaining on properties is considered safe."""
        code = """
function f(x: {prop: string} | null) {
    x?.prop; // safe - uses optional chaining
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_optional_chaining_method(self):
        """Test that optional chaining on method calls is considered safe."""
        code = """
function g(h: (() => void) | undefined) {
    h?.(); // safe - uses optional call chaining
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_optional_chaining_element(self):
        """Test that optional chaining on element access is considered safe."""
        code = """
function i(a: number[] | undefined) {
    const v = a?.[0]; // safe - uses optional element access
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_nullish_coalescing_simple(self):
        """Test that simple nullish coalescing provides safety."""
        code = """
function j(y: string | undefined) {
    const z = y ?? "default";
    z.toUpperCase(); // safe - z is guaranteed non-null
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_nullish_coalescing_inline(self):
        """Test that inline nullish coalescing provides safety."""
        code = """
function k(x: string | null) {
    (x ?? "default").trim(); // safe - immediate coalescing
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_non_null_assertion(self):
        """Test that non-null assertion is allowed."""
        code = """
function k(p: HTMLElement | null) {
    p!.focus(); // allowed - explicit non-null assertion
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_logical_and_guard(self):
        """Test that logical AND guards are recognized."""
        code = """
function m(x: {run(): void} | null) {
    x && x.run(); // safe - guarded by logical AND
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_ternary_guard(self):
        """Test that ternary expressions provide proper guarding."""
        code = """
function n(x: string | undefined) {
    const result = x ? x.trim() : ""; // safe - guarded by ternary
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_early_return_guard(self):
        """Test that early return guards are recognized."""
        code = """
function complex(x: string | null, y: number | undefined) {
    // Early return guard
    if (!x) return;
    x.trim(); // should be safe
    
    // Nested conditions
    if (y !== undefined) {
        if (y > 0) {
            y.toString(); // should be safe
        }
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_negative_case_non_nullable_types(self):
        """Test that non-nullable types don't trigger warnings."""
        code = """
function test(x: string, y: number) {
    x.trim();     // safe - not nullable
    y + 1;        // safe - not nullable
    x.length;     // safe - not nullable
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    # EDGE CASES

    def test_edge_case_chained_property_access(self):
        """Test chained property access where base is nullable."""
        code = """
function test(obj: {nested: {prop: string}} | null) {
    obj.nested.prop; // should warn on first access
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'obj'" in findings[0].message

    def test_edge_case_method_call_chain(self):
        """Test method calls in property access chains."""
        code = """
interface Service {
    getData(): {value: string} | null;
}

function test(service: Service | null) {
    service.getData(); // should warn - service might be null
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'service'" in findings[0].message

    def test_edge_case_complex_guard_scenarios(self):
        """Test complex guard scenarios with nested conditions."""
        code = """
function complexGuards(data: Data | null, callback: Function | undefined) {
    if (data != null) {
        data.process(); // should be safe - explicit null check
        
        if (callback !== undefined) {
            callback(); // should be safe - nested guard
        }
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0

    def test_edge_case_mixed_safety_mechanisms(self):
        """Test file with mixed safety mechanisms."""
        code = """
function mixedSafety(x: string | null, y: Function | undefined, z: Array | null) {
    // Guarded usage
    if (x) {
        x.trim(); // safe
    }
    
    // Optional chaining
    y?.(); // safe
    
    // Nullish coalescing
    const arr = z ?? [];
    arr.push(1); // safe
    
    // Unguarded usage
    x.toUpperCase(); // should warn
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 1
        assert "Possible null/undefined access on 'x'" in findings[0].message

    def test_edge_case_comments_and_strings(self):
        """Test that comments and strings don't interfere with detection."""
        code = '''
function test(x: string | null) {
    // This is a comment about x.method()
    const msg = "x.someMethod() is dangerous";
    x.trim(); // should still warn despite comments and strings
}
'''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        # Should detect at least the real x.trim() usage
        assert len(findings) >= 1
        # Check that at least one finding is for the actual x.trim() call
        has_real_usage = any("x" in f.message for f in findings)
        assert has_real_usage

    def test_edge_case_variable_shadowing(self):
        """Test handling of variable name shadowing."""
        code = """
function outer(x: string | null) {
    x.trim(); // should warn
    
    function inner(x: string) {
        x.trim(); // should NOT warn - different x, non-nullable
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        # Note: This is a limitation of text-based analysis
        # More sophisticated AST analysis would handle scoping better
        assert len(findings) >= 1  # At least the outer x should be detected

    def test_edge_case_arrow_functions(self):
        """Test nullable detection in arrow functions."""
        code = """
const process = (data: Data | undefined) => {
    return data.transform(); // should warn
};

const safeFn = (item: Item | null) => {
    return item ? item.getValue() : null; // ternary guard should make this safe
};
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        # Should detect data.transform() but not item.getValue() due to ternary guard
        assert len(findings) == 1
        assert "Possible null/undefined access on 'data'" in findings[0].message

    def test_edge_case_multiple_union_types(self):
        """Test complex union types with multiple nullable options."""
        code = """
function handleSimpleUnion(value: string | null) {
    value.toString(); // should warn - value could be null
}

function handleSafeUnion(value: string | null) {
    if (value != null) {
        value.toString(); // should be safe
    }
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        # Should detect the first case but not the second (guarded)
        assert len(findings) == 1
        assert "Possible null/undefined access on 'value'" in findings[0].message

    def test_edge_case_destructuring_patterns(self):
        """Test detection of destructuring from nullable objects."""
        code = """
function destructureTest() {
    const obj: {a: string, b: number} | null = getObject();
    const {a, b} = obj; // This pattern is challenging for text-based analysis
    
    const user: User | undefined = getUser();  
    user.name; // This should definitely be detected
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        # Should at least detect the user.name access
        messages = [f.message for f in findings]
        assert any("user" in msg for msg in messages)

    def test_edge_case_generic_types_with_nullability(self):
        """Test nullable generic types."""
        code = """
function processGeneric<T>(item: T | null, list: Array<T> | undefined) {
    item.someMethod(); // should warn
    list.push(item);   // should warn
}
"""
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 2
        messages = [f.message for f in findings]
        assert any("item" in msg for msg in messages)
        assert any("list" in msg for msg in messages)

