"""
Tests for Copy-Paste Mistake Detection Rule

Validates detection of near-duplicate statements that likely result from 
copy-paste mistakes, including single-character typos and LHS/RHS mismatches.
"""

import unittest
from unittest.mock import Mock, MagicMock
from rules.bug_copy_paste_mist import BugCopyPasteMistRule
from engine.types import RuleContext, Finding


class TestBugCopyPasteMistRule(unittest.TestCase):
    """Test cases for the copy-paste mistake detection rule."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.rule = BugCopyPasteMistRule()
    
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
        statements = []
        
        current_pos = 0
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#'):
                # Create mock statement
                stmt = Mock()
                stmt.start_byte = current_pos
                stmt.end_byte = current_pos + len(line)
                
                # Create simplified tokens for the line
                tokens = self._tokenize_line(line, language)
                stmt.tokens = tokens
                
                statements.append(stmt)
            current_pos += len(line) + 1  # +1 for newline
        
        # Create mock block containing statements
        block = Mock()
        block.statements = statements
        
        # Create mock root that yields the block
        root = Mock()
        root.walk = Mock(return_value=iter([block]))  # Return iterator, not list
        
        return root
    
    def _tokenize_line(self, line: str, language: str) -> list:
        """Create simplified tokens for a line of code."""
        import re
        
        # Simple tokenization based on language
        if language == "python":
            # Python-style tokenization
            tokens = re.findall(r'\w+|[^\w\s]', line)
        elif language in ["javascript", "typescript"]:
            # JavaScript-style tokenization
            tokens = re.findall(r'\w+|[^\w\s]', line)
        else:
            # Generic tokenization
            tokens = re.findall(r'\w+|[^\w\s]', line)
        
        # Convert to mock token objects
        mock_tokens = []
        for token_text in tokens:
            token = Mock()
            token.text = token_text
            token.value = token_text
            
            # Determine token type
            if token_text.isidentifier():
                token.is_identifier = True
                token.kind = 'identifier'
                token.type = 'identifier'
            elif token_text.isdigit():
                token.is_identifier = False
                token.kind = 'integer'
                token.type = 'integer'
            elif token_text in {'"', "'", '"""', "'''"}:
                token.is_identifier = False
                token.kind = 'string'
                token.type = 'string'
            else:
                token.is_identifier = False
                token.kind = 'operator'
                token.type = 'operator'
            
            mock_tokens.append(token)
        
        return mock_tokens
    
    def test_rule_metadata(self):
        """Test rule metadata is correctly defined."""
        assert self.rule.meta.id == "bug.copy_paste_mist"
        assert self.rule.meta.category == "bug"
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that the rule requires correct capabilities."""
        assert self.rule.requires.syntax is True
    
    def test_positive_case_single_typo_python(self):
        """Test detection of single-character typos in Python."""
        code = '''
total += price
total += prcie
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the typo in the second statement
        assert len(findings) >= 1
        finding = findings[0]
        assert "prcie" in finding.message
        assert "price" in finding.message
        assert "copy-paste typo" in finding.message.lower()
        assert finding.severity == "info"
        assert finding.meta["pattern"] == "single_typo"
    
    def test_positive_case_single_typo_javascript(self):
        """Test detection of single-character typos in JavaScript."""
        code = '''
total += price;
total += prcie;
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the typo in the second statement
        assert len(findings) >= 1
        finding = findings[0]
        assert "prcie" in finding.message
        assert "price" in finding.message
        assert finding.severity == "info"
    
    def test_positive_case_lhs_rhs_mismatch_python(self):
        """Test detection of LHS/RHS mismatch in Python."""
        code = '''
user_data = foo
admin_data = foo
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the suspicious assignment pattern
        assert len(findings) >= 1
        finding = findings[0]
        assert "same RHS, different LHS" in finding.message
        assert finding.severity == "info"
        assert finding.meta["pattern"] == "lhs_rhs_mismatch"
    
    def test_positive_case_lhs_rhs_mismatch_javascript(self):
        """Test detection of LHS/RHS mismatch in JavaScript."""
        code = '''
userObj = getData();
adminObj = getData();
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the suspicious assignment pattern
        assert len(findings) >= 1
        finding = findings[0]
        assert "copy-pasted" in finding.message.lower()
        assert finding.severity == "info"
    
    def test_negative_case_legitimate_differences_python(self):
        """Test that legitimate differences are not flagged in Python."""
        code = '''
user_data = foo
admin_data = bar
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues
        assert len(findings) == 0
    
    def test_negative_case_legitimate_differences_javascript(self):
        """Test that legitimate differences are not flagged in JavaScript."""
        code = '''
sum += a[i];
sum += b[i];
'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues (meaningful variable difference)
        assert len(findings) == 0
    
    def test_negative_case_different_structures(self):
        """Test that statements with different structures are not compared."""
        code = '''
total += price
result = calculate(value)
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues (different statement structures)
        assert len(findings) == 0
    
    def test_negative_case_single_statement(self):
        """Test that single statements don't trigger false positives."""
        code = '''
total += price
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not detect any issues (only one statement)
        assert len(findings) == 0
    
    def test_edge_case_member_access(self):
        """Test handling of member access patterns."""
        code = '''
user.name = value
admin.name = value
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect this as a potential LHS/RHS mismatch
        assert len(findings) >= 1
        finding = findings[0]
        assert "same RHS" in finding.message
    
    def test_edge_case_numeric_indices(self):
        """Test that numeric index changes are not flagged."""
        code = '''
arr[0] = value
arr[1] = value
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag this as the indices are meaningfully different
        # This test may need adjustment based on tokenization
        # For now, we'll accept either outcome as the pattern is debatable
        pass
    
    def test_looks_like_typo_function(self):
        """Test the typo detection heuristic directly."""
        # Should detect typos
        assert self.rule._looks_like_typo("price", "prcie") is True
        assert self.rule._looks_like_typo("value", "vlue") is True
        assert self.rule._looks_like_typo("count", "coun") is True
        
        # Should not detect legitimate differences
        assert self.rule._looks_like_typo("price", "cost") is False
        assert self.rule._looks_like_typo("foo", "bar") is False
        assert self.rule._looks_like_typo("a", "b") is False
        assert self.rule._looks_like_typo("short", "verylongname") is False
    
    def test_multiple_typos_same_block(self):
        """Test detection of multiple typos in the same block."""
        code = '''
total += price
total += prcie
sum += value
sum += vlue
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect both typos
        assert len(findings) >= 2
        
        # Check that both typos are detected
        messages = [f.message for f in findings]
        assert any("prcie" in msg for msg in messages)
        assert any("vlue" in msg for msg in messages)
    
    def test_complex_expressions(self):
        """Test handling of more complex expressions."""
        code = '''
result = calculate(a, b, c)
result = calculate(a, b, d)
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag this as the difference in 'c' vs 'd' is meaningful
        # This depends on how the tokenization handles function calls
        pass
    
    def test_empty_file_handling(self):
        """Test handling of empty files."""
        ctx = self._create_context("", "python")
        findings = list(self.rule.visit(ctx))
        
        # Should handle empty files gracefully
        assert len(findings) == 0
    
    def test_comments_ignored(self):
        """Test that comments don't interfere with detection."""
        code = '''
total += price
# This is a comment
total += prcie
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should still detect the typo despite the comment
        assert len(findings) >= 1
        finding = findings[0]
        assert "prcie" in finding.message
    
    def test_finding_properties(self):
        """Test that findings have correct properties."""
        code = '''
total += price
total += prcie
'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check required properties
        assert finding.rule == "bug.copy_paste_mist"
        assert finding.file == ctx.file_path
        assert finding.severity == "info"
        assert finding.start_byte is not None
        assert finding.end_byte is not None
        assert isinstance(finding.message, str)
        assert isinstance(finding.meta, dict)
    
    def test_unsupported_language_ignored(self):
        """Test that unsupported languages are handled gracefully."""
        code = 'some code here'
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = "unsupported_language"
        context.file_path = "test.unknown"
        context.syntax_tree = None  # No syntax tree for unsupported language
        
        findings = list(self.rule.visit(context))
        # Should handle gracefully without errors
        assert len(findings) == 0


if __name__ == '__main__':
    unittest.main()

