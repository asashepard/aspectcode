"""Tests for sec.over_permissive_perms rule

Tests over-permissive permission detection across Python, Bash, and JavaScript, covering:
- Numeric permission modes (777, 666, etc.)
- Symbolic permission modes (a+rwx, o+w, etc.)
- Option objects in JavaScript
- Various API functions that set permissions
"""

import pytest
from unittest.mock import Mock

from engine.types import RuleContext, Finding
from rules.sec_over_permissive_perms import SecOverPermissivePermsRule


class TestSecOverPermissivePermsRule:
    """Test suite for SecOverPermissivePermsRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecOverPermissivePermsRule()
    
    def _create_mock_context(self, code: str, language: str, file_path: str = "test.py"):
        """Create a mock context for testing."""
        # Create a simple mock tree
        mock_tree = Mock()
        mock_tree.children = []
        
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = language
        context.file_path = file_path
        context.tree = mock_tree
        
        return context
    
    def _run_rule(self, code: str, language: str) -> list:
        """Helper to run rule on code and return findings."""
        context = self._create_mock_context(code, language)
        findings = list(self.rule.visit(context))
        return findings
    
    def test_rule_metadata(self):
        """Test that rule has correct metadata."""
        assert self.rule.meta.id == "sec.over_permissive_perms"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.requires.syntax is True
        assert "python" in self.rule.meta.langs
        assert "bash" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 3
    
    # Positive test cases (should detect over-permissive permissions)
    
    def test_positive_python_mkdir_777(self):
        """Test detection of Python mkdir with 777 permissions."""
        code = "import os\nos.mkdir('dir', 0o777)"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
        assert any("over-permissive" in f.message.lower() for f in findings)
    
    def test_positive_python_chmod_666(self):
        """Test detection of Python chmod with 666 permissions."""
        code = "import os\nos.chmod('file', 0o666)"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
        assert any("0o666" in f.message for f in findings)
    
    def test_positive_python_makedirs_775(self):
        """Test detection of Python makedirs with group-writable permissions."""
        code = "import os\nos.makedirs('path', 0o775)"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
    
    def test_positive_python_open_666(self):
        """Test detection of Python open with world-writable permissions."""
        code = "os.open('file', os.O_CREAT, 0o666)"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
    
    def test_positive_javascript_mkdir_777(self):
        """Test detection of JavaScript mkdir with 777 permissions."""
        code = "const fs = require('fs');\nfs.mkdirSync('dir', {mode: 0o777});"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
        assert any("over-permissive" in f.message.lower() for f in findings)
    
    def test_positive_javascript_chmod_666(self):
        """Test detection of JavaScript chmod with 666 permissions."""
        code = "fs.chmodSync('file', 0o666);"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
    
    def test_positive_javascript_mkdir_numeric_string(self):
        """Test detection of JavaScript mkdir with string mode."""
        code = "fs.mkdirSync('dir', 0777);"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
    
    def test_positive_bash_mkdir_777(self):
        """Test detection of bash mkdir with 777 permissions."""
        code = "mkdir -m 777 newdir"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
        assert any("over-permissive" in f.message.lower() for f in findings)
    
    def test_positive_bash_chmod_777(self):
        """Test detection of bash chmod with 777 permissions."""
        code = "chmod 777 file"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
    
    def test_positive_bash_chmod_symbolic_all_write(self):
        """Test detection of bash chmod with a+rwx symbolic mode."""
        code = "chmod a+rwx file"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
    
    def test_positive_bash_chmod_others_write(self):
        """Test detection of bash chmod with o+w (others write)."""
        code = "chmod o+w file"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
    
    def test_positive_bash_install_mode_666(self):
        """Test detection of bash install with 666 permissions."""
        code = "install -m 666 source dest"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
    
    # Negative test cases (should NOT detect - safe permissions)
    
    def test_negative_python_mkdir_750(self):
        """Test that safe Python mkdir permissions are not flagged."""
        code = "import os\nos.mkdir('dir', 0o750)"
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_python_chmod_640(self):
        """Test that safe Python chmod permissions are not flagged."""
        code = "import os\nos.chmod('file', 0o640)"
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_python_makedirs_755(self):
        """Test that Python makedirs with 755 permissions are not flagged."""
        code = "import os\nos.makedirs('path', 0o755)"
        findings = self._run_rule(code, "python")
        # 755 is commonly used for directories and should not be flagged
        assert len(findings) == 0
    
    def test_negative_python_open_644(self):
        """Test that safe Python open permissions are not flagged."""
        code = "os.open('file', os.O_CREAT, 0o644)"
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_javascript_mkdir_750(self):
        """Test that safe JavaScript mkdir permissions are not flagged."""
        code = "fs.mkdirSync('dir', {mode: 0o750});"
        findings = self._run_rule(code, "javascript")
        assert len(findings) == 0
    
    def test_negative_javascript_chmod_640(self):
        """Test that safe JavaScript chmod permissions are not flagged."""
        code = "fs.chmodSync('file', 0o640);"
        findings = self._run_rule(code, "javascript")
        assert len(findings) == 0
    
    def test_negative_bash_mkdir_750(self):
        """Test that safe bash mkdir permissions are not flagged."""
        code = "mkdir -m 750 newdir"
        findings = self._run_rule(code, "bash")
        assert len(findings) == 0
    
    def test_negative_bash_chmod_640(self):
        """Test that safe bash chmod permissions are not flagged."""
        code = "chmod 640 file"
        findings = self._run_rule(code, "bash")
        assert len(findings) == 0
    
    def test_negative_bash_chmod_user_only(self):
        """Test that user-only bash chmod permissions are not flagged."""
        code = "chmod u+rwx file"
        findings = self._run_rule(code, "bash")
        assert len(findings) == 0
    
    def test_negative_bash_install_mode_644(self):
        """Test that safe bash install permissions are not flagged."""
        code = "install -m 644 source dest"
        findings = self._run_rule(code, "bash")
        assert len(findings) == 0
    
    # Edge cases and special scenarios
    
    def test_positive_python_different_octal_formats(self):
        """Test detection across different octal formats."""
        test_cases = [
            "os.mkdir('d', 0o777)",  # 0o prefix
            "os.mkdir('d', 0777)",   # 0 prefix (deprecated but valid)
            "os.chmod('f', 777)"     # decimal (might be interpreted as octal)
        ]
        
        for code in test_cases:
            findings = self._run_rule(code, "python")
            # At least one should be detected
            if len(findings) > 0:
                break
        else:
            pytest.fail("No octal format was detected")
    
    def test_positive_javascript_option_object_mode(self):
        """Test detection of mode in JavaScript option objects."""
        code = "fs.mkdirSync('dir', {mode: 0o777, recursive: true});"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
    
    def test_positive_bash_multiple_symbolic_modes(self):
        """Test detection of multiple symbolic modes."""
        test_cases = [
            "chmod go+w file",      # group and others write
            "chmod ugo+rwx file",   # all permissions for all
            "chmod a+w file"        # all write
        ]
        
        for code in test_cases:
            findings = self._run_rule(code, "bash")
            assert len(findings) > 0, f"Failed to detect: {code}"
    
    def test_negative_python_no_mode_specified(self):
        """Test that functions without explicit mode are not flagged."""
        code = "os.mkdir('dir')"  # Uses default umask
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_bash_chmod_remove_permissions(self):
        """Test that removing permissions is not flagged."""
        code = "chmod go-rwx file"  # Remove group/others permissions
        findings = self._run_rule(code, "bash")
        assert len(findings) == 0
    
    def test_suggest_only_no_autofix(self):
        """Test that findings have no autofix (suggest-only)."""
        code = "chmod 777 file"
        findings = self._run_rule(code, "bash")
        assert len(findings) > 0
        for finding in findings:
            # Findings should not have edit suggestions (suggest-only rule)
            assert not hasattr(finding, 'edit') or finding.edit is None
    
    def test_comprehensive_positive_coverage(self):
        """Test that all major positive patterns are detected."""
        test_cases = {
            "python": [
                "os.mkdir('d', 0o777)",
                "os.chmod('f', 0o666)",
                "os.makedirs('p', 0o775)"
            ],
            "javascript": [
                "fs.mkdirSync('d', 0o777)",
                "fs.chmodSync('f', 0o666)",
                "fs.mkdirSync('d', {mode: 0o777})"
            ],
            "bash": [
                "mkdir -m 777 d",
                "chmod 666 f", 
                "chmod a+rwx f"
            ]
        }
        
        for language, codes in test_cases.items():
            for code in codes:
                findings = self._run_rule(code, language)
                assert len(findings) > 0, f"Failed to detect: {code} in {language}"
    
    def test_comprehensive_negative_coverage(self):
        """Test that all major negative patterns are not flagged."""
        test_cases = {
            "python": [
                "os.mkdir('d', 0o750)",
                "os.chmod('f', 0o640)",
                "os.makedirs('p')"  # No explicit mode
            ],
            "javascript": [
                "fs.mkdirSync('d', 0o750)",
                "fs.chmodSync('f', 0o640)",
                "fs.mkdirSync('d')"  # No mode specified
            ],
            "bash": [
                "mkdir -m 750 d",
                "chmod 640 f",
                "chmod u+rwx f"  # User only
            ]
        }
        
        for language, codes in test_cases.items():
            for code in codes:
                findings = self._run_rule(code, language)
                assert len(findings) == 0, f"False positive on: {code} in {language}"
    
    def test_language_specific_recommendations(self):
        """Test that language-specific recommendations are provided."""
        test_cases = {
            "python": "os.mkdir('d', 0o777)",
            "javascript": "fs.mkdirSync('d', 0o777)",
            "bash": "chmod 777 file"
        }
        
        for language, code in test_cases.items():
            findings = self._run_rule(code, language)
            assert len(findings) > 0
            
            # Check that language-specific recommendations are included
            message = findings[0].message.lower()
            if language == "python":
                assert "umask" in message or "0o750" in message
            elif language == "javascript":
                assert "process umask" in message or "0o750" in message
            elif language == "bash":
                assert "750" in message or "640" in message
    
    def test_severity_and_span_reporting(self):
        """Test that findings have correct severity and span info."""
        code = "chmod 777 file"
        findings = self._run_rule(code, "bash")
        
        assert len(findings) > 0
        finding = findings[0]
        
        # Check severity and rule
        assert finding.severity == "warning"
        assert finding.rule == "sec.over_permissive_perms"
        
        # Check span information
        assert hasattr(finding, 'start_byte')
        assert hasattr(finding, 'end_byte')
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
    
    def test_mode_parsing_edge_cases(self):
        """Test edge cases in mode parsing."""
        # Test the internal parsing function
        parse_func = self.rule._parse_mode_literal
        
        # Test various formats
        assert parse_func("777") == 0o777
        assert parse_func("0o777") == 0o777
        assert parse_func("0x1ff") == 0o777  # hex equivalent
        assert parse_func(0o777) == 0o777
        assert parse_func("invalid") is None
        assert parse_func(None) is None
    
    def test_over_permissive_detection_logic(self):
        """Test the core over-permissive detection logic."""
        # Test the internal detection function
        is_over_permissive = self.rule._is_over_permissive
        
        # Test known dangerous permissions
        assert is_over_permissive(0o777) is True   # World writable + executable
        assert is_over_permissive(0o666) is True   # World writable
        assert is_over_permissive(0o775) is True   # Group writable
        assert is_over_permissive(0o766) is True   # Group writable
        
        # Test safe permissions
        assert is_over_permissive(0o750) is False  # Owner only write, group read/exec
        assert is_over_permissive(0o640) is False  # Owner write, group read
        assert is_over_permissive(0o644) is False  # Owner write, group/others read
        assert is_over_permissive(0o600) is False  # Owner only read/write
        assert is_over_permissive(0o755) is False  # Common dir/exec permissions (may be acceptable)

