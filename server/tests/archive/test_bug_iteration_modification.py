"""
Tests for Iteration Modification Detection Rule

Tests various scenarios where collections are modified during iteration
and verifies that the rule correctly identifies risky patterns while
avoiding false positives on safe iteration patterns.
"""

import unittest
from unittest.mock import Mock
from rules.bug_iteration_modification import BugIterationModificationRule
from engine.types import RuleContext


class TestBugIterationModificationRule(unittest.TestCase):
    """Test cases for the iteration modification detection rule."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugIterationModificationRule()
    
    def _create_context(self, code: str, language: str, filename: str) -> RuleContext:
        """Create a mock RuleContext for testing."""
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = language
        context.file_path = filename
        context.syntax_tree = None  # We're using text-based analysis
        return context
    
    def test_rule_metadata(self):
        """Test that rule metadata is correctly configured."""
        assert self.rule.meta.id == "bug.iteration_modification"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.tier == 0
        
        expected_langs = ["python", "java", "csharp", "javascript", "typescript", "ruby"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires syntax analysis."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_python_append(self):
        """Test Python iteration with collection modification."""
        code = """
def process_items():
    for x in items:
        items.append(x * 2)
        print(x)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated during for-each iteration" in finding.message
        assert finding.severity == "warning"
        assert finding.meta["collection"] == "items"
        assert finding.meta["language"] == "python"
    
    def test_positive_case_python_remove(self):
        """Test Python iteration with remove operation."""
        code = """
for item in my_list:
    if condition:
        my_list.remove(item)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "my_list"
    
    def test_positive_case_javascript_splice(self):
        """Test JavaScript iteration with splice modification."""
        code = """
function processArray() {
    for (const item of myArray) {
        if (item > 5) {
            myArray.splice(0, 1);
        }
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "myArray"
    
    def test_positive_case_typescript_push(self):
        """Test TypeScript iteration with push operation."""
        code = """
function expand(arr: number[]) {
    for (const val of arr) {
        if (val < 10) {
            arr.push(val * 2);
        }
    }
}
"""
        ctx = self._create_context(code, "typescript", "test.ts")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "arr"
    
    def test_positive_case_java_add(self):
        """Test Java enhanced for loop with collection modification."""
        code = """
public void processData() {
    for (String item : dataList) {
        if (item.length() > 5) {
            dataList.add(item.toUpperCase());
        }
    }
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "dataList"
    
    def test_positive_case_csharp_remove(self):
        """Test C# foreach with collection modification."""
        code = """
public void CleanupList() {
    foreach (var item in itemList) {
        if (item.IsInvalid) {
            itemList.Remove(item);
        }
    }
}
"""
        ctx = self._create_context(code, "csharp", "test.cs")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "itemList"
    
    def test_positive_case_ruby_push(self):
        """Test Ruby each with collection modification."""
        code = """
def expand_array
  numbers.each do |num|
    if num < 5
      numbers.push(num * 2)
    end
  end
end
"""
        ctx = self._create_context(code, "ruby", "test.rb")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "numbers"
    
    def test_positive_case_ruby_append_operator(self):
        """Test Ruby each with << operator."""
        code = """
items.each { |item| items << item.clone }
"""
        ctx = self._create_context(code, "ruby", "test.rb")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
        assert finding.meta["collection"] == "items"
    
    def test_positive_case_element_assignment(self):
        """Test element assignment during iteration."""
        code = """
for i, item in enumerate(data):
    data[i] = item * 2
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
    
    def test_positive_case_delete_operation(self):
        """Test delete operation during iteration."""
        code = """
for (const key in obj) {
    if (obj[key] < 0) {
        delete obj[key];
    }
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert "Collection mutated" in finding.message
    
    def test_negative_case_python_snapshot(self):
        """Test Python iteration over snapshot (safe)."""
        code = """
for x in list(items):
    items.append(x * 2)
    
for y in tuple(data):
    data.remove(y)
    
for z in sorted(collection):
    collection.clear()
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since we're iterating over snapshots
        assert len(findings) == 0
    
    def test_negative_case_javascript_snapshot(self):
        """Test JavaScript iteration over snapshot (safe)."""
        code = """
for (const item of [...myArray]) {
    myArray.splice(0, 1);
}

for (const val of Array.from(collection)) {
    collection.push(val * 2);
}
"""
        ctx = self._create_context(code, "javascript", "test.js")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since we're iterating over snapshots
        assert len(findings) == 0
    
    def test_negative_case_different_collection(self):
        """Test modification of different collection (safe)."""
        code = """
for item in source_list:
    target_list.append(item)
    
for x in data:
    other_data.remove(x)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since different collections are being modified
        assert len(findings) == 0
    
    def test_negative_case_java_safe_iteration(self):
        """Test Java safe iteration patterns."""
        code = """
// Safe: iterating over a copy
for (String item : new ArrayList<>(dataList)) {
    dataList.add(item.toUpperCase());
}

// Safe: different collection
for (String item : sourceList) {
    targetList.add(item);
}
"""
        ctx = self._create_context(code, "java", "Test.java")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since these are safe patterns
        assert len(findings) == 0
    
    def test_negative_case_comment_lines_ignored(self):
        """Test that comments are ignored."""
        code = """
# This has risky pattern: for x in items: items.append(x)
// Another comment: for (const v of arr) { arr.push(v); }
/* Block comment with for (x of collection) { collection.splice(0, 1); } */

def safe_function():
    pass
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since risky patterns are in comments
        assert len(findings) == 0
    
    def test_negative_case_read_only_operations(self):
        """Test that read-only operations don't trigger the rule."""
        code = """
for item in collection:
    print(item)
    result = item.process()
    other_var = collection.count(item)  # Read-only method
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should have no findings since no mutations occur
        assert len(findings) == 0
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are ignored."""
        code = """
for (const item of collection) {
    collection.push(item * 2);
}
"""
        ctx = self._create_context(code, "kotlin", "test.kt")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "python", "empty.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = "for x in items:\n    items.append(x)"
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check finding properties
        assert finding.rule == "bug.iteration_modification"
        assert finding.file == "test.py"
        assert finding.severity == "warning"
        assert finding.autofix is None  # suggest-only
        assert "suggestion" in finding.meta
        assert "items" in finding.meta["suggestion"]
        assert finding.start_byte < finding.end_byte
    
    def test_multiple_collections_in_single_file(self):
        """Test detection of multiple iteration modifications in one file."""
        code = """
def process_data():
    for x in list1:
        list1.append(x * 2)
    
    for y in list2:
        list2.remove(y)
    
    for z in list3:
        list3.clear()
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should detect all three risky iterations
        assert len(findings) >= 3
        
        collections = {f.meta["collection"] for f in findings}
        assert collections == {"list1", "list2", "list3"}
    
    def test_nested_loops_detection(self):
        """Test detection in nested loop structures."""
        code = """
for outer in outer_list:
    for inner in inner_list:
        outer_list.append(inner)
        inner_list.remove(inner)
"""
        ctx = self._create_context(code, "python", "test.py")
        findings = list(self.rule.visit(ctx))
        
        # Should detect both mutations
        assert len(findings) >= 2
        
        collections = {f.meta["collection"] for f in findings}
        assert "outer_list" in collections
        assert "inner_list" in collections


if __name__ == "__main__":
    unittest.main()

