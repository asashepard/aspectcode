"""
Unit tests for lang.ts_loose_equality rule.

Tests detection and replacement of loose equality operators (== and !=) 
with strict equality operators (=== and !==) in TypeScript/JavaScript.
"""

import pytest
from engine.types import RuleContext
from rules.ts_loose_equality import TsLooseEqualityRule


class TestTsLooseEqualityRule:
    """Test suite for lang.ts_loose_equality rule."""
    
    def setup_method(self):
        """Set up test environment."""
        self.rule = TsLooseEqualityRule()
    
    def test_loose_equality_operator(self):
        """Test that loose equality == is flagged."""
        code = '''
function checkValue(x: any) {
    if (x == 0) {
        return "zero";
    }
    return "not zero";
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag loose equality operator =="
        
        finding = findings[0]
        assert finding.rule_id == "lang.ts_loose_equality"
        assert "==" in finding.message or "loose" in finding.message.lower()
    
    def test_loose_inequality_operator(self):
        """Test that loose inequality != is flagged.""" 
        code = '''
function isNotEmpty(value: string) {
    return value != "";
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag loose inequality operator !="
        
        finding = findings[0]
        assert finding.rule_id == "lang.ts_loose_equality"
    
    def test_strict_equality_allowed(self):
        """Test that strict equality === is allowed."""
        code = '''
function checkValue(x: any) {
    if (x === 0) {
        return "zero";
    }
    if (x !== null) {
        return "not null";
    }
    return "other";
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) == 0, "Should not flag strict equality operators"
    
    def test_javascript_loose_equality(self):
        """Test loose equality detection in JavaScript."""
        code = '''
function compare(a, b) {
    return a == b;
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.js",
            language="javascript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag loose equality in JavaScript"
    
    def test_type_coercion_examples(self):
        """Test common type coercion cases."""
        code = '''
function problematicComparisons() {
    if (0 == false) return "bad1";
    if ("0" == false) return "bad2";
    if ("" == 0) return "bad3";
    if (null == undefined) return "questionable";
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 4, "Should flag multiple loose equality cases"
    
    def test_assignment_vs_equality(self):
        """Test that assignment = is not flagged."""
        code = '''
function assignment() {
    let x = 5;
    x = 10;
    return x;
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) == 0, "Should not flag assignment operators"
    
    def test_autofix_suggestion(self):
        """Test that autofix suggestions are provided."""
        code = '''
if (value == null) {
    doSomething();
}
'''
        
        context = RuleContext(
            source_code=code,
            file_path="test.ts",
            language="typescript"
        )
        
        findings = list(self.rule.check(context))
        
        assert len(findings) >= 1, "Should flag loose equality"
        
        finding = findings[0]
        if hasattr(finding, 'suggested_edits') and finding.suggested_edits:
            edit = finding.suggested_edits[0]
            assert "===" in edit.new_text, "Should suggest strict equality"


if __name__ == "__main__":
    # Run basic test without pytest
    test_rule = TestTsLooseEqualityRule()
    test_rule.setup_method()
    
    try:
        test_rule.test_strict_equality_allowed()
        print("✓ Strict equality test passed")
        
        test_rule.test_assignment_vs_equality()
        print("✓ Assignment test passed")
        
        print("✓ Basic unit tests for lang.ts_loose_equality passed!")
        
    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()