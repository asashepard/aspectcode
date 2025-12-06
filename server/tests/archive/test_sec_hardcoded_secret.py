"""Test suite for sec.hardcoded_secret rule."""

import pytest
from engine.types import RuleContext
from rules.sec_hardcoded_secret import SecHardcodedSecretRule


class MockNode:
    """Mock syntax tree node for testing."""
    
    def __init__(self, kind='', text='', start_byte=0, end_byte=None, children=None, parent=None):
        self.kind = kind
        self.type = kind
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else start_byte + len(text)
        self.children = children or []
        self.parent = parent
        
        # Set up parent-child relationships
        for child in self.children:
            if child:
                child.parent = self


class MockSyntax:
    """Mock syntax tree for testing."""
    
    def __init__(self, root_node=None):
        self.root_node = root_node
        self._nodes = []
        if root_node:
            self._collect_nodes(root_node)
    
    def _collect_nodes(self, node):
        """Collect all nodes for walking."""
        self._nodes.append(node)
        for child in getattr(node, 'children', []):
            if child:
                self._collect_nodes(child)
    
    def walk(self):
        """Walk through all nodes."""
        return self._nodes
    
    def node_span(self, node):
        """Return span for node."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 10))


class TestSecHardcodedSecretRule:
    """Test hardcoded secret detection."""

    def setup_method(self):
        self.rule = SecHardcodedSecretRule()

    def test_aws_access_key_detection(self):
        """Test detection of AWS access keys."""
        code = '''
        ACCESS_KEY = "AKIAIOSFODNN7PRODUCT"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "AWS Access Key ID" in findings[0].message
        assert findings[0].severity == "error"

    def test_aws_secret_access_key_detection(self):
        """Test detection of AWS secret access keys."""
        code = '''
        SECRET = "aws_secret_access_key wJalrXUtnFEMI/K7MDENG/bPxRfiCYZZZZZZZZZ"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "AWS Secret Access Key" in findings[0].message

    def test_github_token_detection(self):
        """Test detection of GitHub personal access tokens."""
        code = '''
        GITHUB_TOKEN = "ghp_1234567890abcdef1234567890abcdef87654321"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "GitHub Personal Access Token" in findings[0].message

    def test_slack_token_detection(self):
        """Test detection of Slack tokens."""
        code = '''
        SLACK_TOKEN = "xoxb-123456789012-123456789012-abcdefghijklmnopqrstuvwx"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Slack token" in findings[0].message

    def test_google_api_key_detection(self):
        """Test detection of Google API keys."""
        code = '''
        API_KEY = "AIzaSyDaGmWKa4JsXZ-HjGw7ISLn_3namBGeabc"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Google API key" in findings[0].message

    def test_stripe_secret_detection(self):
        """Test detection of Stripe live secrets."""
        code = '''
        STRIPE_SECRET = "sk_live_abcdefghijklmnopqrstuvwxyz987654"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Stripe Live Secret" in findings[0].message

    def test_private_key_detection(self):
        """Test detection of private key material."""
        code = '''
        PRIVATE_KEY = """-----BEGIN RSA PRIVATE KEY-----
        MIIEpAIBAAKCAQEA7yn3bRHob4rRH...
        -----END RSA PRIVATE KEY-----"""
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "Private key material" in findings[0].message

    def test_jwt_token_detection(self):
        """Test detection of JWT bearer tokens."""
        code = '''
        AUTH_HEADER = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "JWT bearer token" in findings[0].message

    def test_high_entropy_with_secret_context(self):
        """Test detection of high-entropy strings in secret contexts."""
        code = '''
        api_key = "kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5"
        password = "xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 2
        for finding in findings:
            assert "High-entropy literal in secret-like context" in finding.message

    def test_allowlist_filtering(self):
        """Test that allowlisted strings are ignored."""
        code = '''
        aws_key = "AKIAIOSFODNN7EXAMPLE"  # Contains 'example' in value
        aws_secret = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"  # Contains 'example' in value
        token_with_test = "ghp_1234567890abcdefTESTabcdef12345678"  # Contains 'test' in value
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Should not find any due to allowlist filtering (all contain allowlisted substrings)
        assert len(findings) == 0

    def test_url_filtering(self):
        """Test that URLs are not flagged as secrets."""
        code = '''
        config_url = "https://api.example.com/config/kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5"
        api_endpoint = "http://localhost:8080/auth/bearer/xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # URLs should be filtered out even if they contain high-entropy parts
        assert len(findings) == 0

    def test_uuid_filtering(self):
        """Test that UUIDs are not flagged as secrets."""
        code = '''
        session_id = "550e8400-e29b-41d4-a716-446655440000"
        request_id = "6ba7b810-9dad-11d1-80b4-00c04fd430c8"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # UUIDs should not be flagged
        assert len(findings) == 0

    def test_hex_digest_filtering(self):
        """Test that hex digests are not flagged."""
        code = '''
        file_hash = "d85b1213473c2fd7c2045020a6b9c62b"
        checksum = "a1b2c3d4e5f6789012345678901234567890abcd"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Hex digests should not be flagged
        assert len(findings) == 0

    def test_short_strings_ignored(self):
        """Test that short strings are ignored."""
        code = '''
        short_secret = "abc123"
        api_key = "short"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Short strings should not be flagged
        assert len(findings) == 0

    def test_context_detection_assignment(self):
        """Test context detection in variable assignments."""
        code = '''
        const password = "kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5"
        let api_token = "xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR"
        var auth_key = "pL8mK5nR2sT6vW9yB3eF7hJ0qC4gN1xZ"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 3
        for finding in findings:
            assert "High-entropy literal in secret-like context" in finding.message

    def test_context_detection_object_property(self):
        """Test context detection in object properties."""
        code = '''
        config = {
            api_key: "kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5",
            secret: "xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR"
        }
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 2

    def test_context_detection_function_call(self):
        """Test context detection in function call arguments."""
        code = '''
        authenticate(password="kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5")
        set_api_key("xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR")
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 2

    def test_safe_high_entropy_strings(self):
        """Test that high-entropy strings without secret context are not flagged."""
        code = '''
        random_data = "kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5"
        encoded_message = "xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR"
        '''
        ctx = self._create_context(code)
        findings = list(self.rule.visit(ctx))
        
        # Without secret context, these should not be flagged
        assert len(findings) == 0

    def test_multi_language_string_literals(self):
        """Test detection across different string literal formats."""
        test_cases = [
            # Python
            'password = "kH2Lx8N9mP3qR7sT1vW4yZ6bD8fJ2nQ5"',
            "api_key = 'xY9wB3eF6hK8mN2pS5tU1vZ4cG7jL0qR'",
            'secret = """pL8mK5nR2sT6vW9yB3eF7hJ0qC4gN1xZ"""',
            # TypeScript/JavaScript
            'const token = `mN2pS5tU1vZ4cG7jL0qRxY9wB3eF6hK8`;',
            # Raw strings - use secret_key instead of just key (more specific)
            'secret_key = r"fG9jL2qRxY6wB5eF8hK1mN4pS7tU0vZ3cC"',
        ]
        
        for code in test_cases:
            ctx = self._create_context(code)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Failed to detect secret in: {code}"

    def test_rule_metadata(self):
        """Test rule metadata is correctly configured."""
        assert self.rule.meta.id == "sec.hardcoded_secret"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 12  # 11 main languages + sql

    def _create_context(self, code: str, lang: str = "python") -> RuleContext:
        """Create a mock context for testing."""
        # Create string literal nodes for each quoted string in the code
        string_nodes = []
        
        # Simple string extraction - find quoted strings (including backticks and triple quotes)
        import re
        for match in re.finditer(r'(["\']([^"\']*)["\']|`([^`]*)`|"""([^"]*)"""|\'\'\'([^\']*)\'\'\')', code):
            start, end = match.span()
            literal_text = match.group(0)
            string_node = MockNode(
                kind='string_literal',
                text=literal_text,
                start_byte=start,
                end_byte=end
            )
            string_nodes.append(string_node)
        
        # Create a root node containing the string literals
        root_node = MockNode(
            kind='source_file',
            text=code,
            start_byte=0,
            end_byte=len(code),
            children=string_nodes
        )
        
        # Create mock adapter
        class MockAdapter:
            def language_id(self):
                return lang
        
        syntax_tree = MockSyntax(root_node)
        return RuleContext(
            file_path=f"test.{lang}",
            text=code,
            tree=syntax_tree,
            adapter=MockAdapter(),
            config={},
            scopes=None,
            project_graph=None,
        )


if __name__ == "__main__":
    pytest.main([__file__])

