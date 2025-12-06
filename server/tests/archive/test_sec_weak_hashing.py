"""Test suite for the weak hashing detection rule.

Tests detection of weak MD5/SHA-1 hashing algorithms across multiple languages
and frameworks, ensuring proper identification of vulnerable patterns while
avoiding false positives for strong alternatives.
"""

import pytest
from engine.types import RuleContext, RuleMeta, Requires
from rules.sec_weak_hashing import SecWeakHashingRule


class MockNode:
    """Mock AST node for testing."""
    
    def __init__(self, kind: str, text: str, children=None, start_byte=0, end_byte=None):
        self.kind = kind
        self.type = kind  # Some parsers use 'type' instead of 'kind'
        self.text = text.encode() if isinstance(text, str) else text
        self.children = children or []
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else start_byte + len(text)
        self.parent = None
        
        # Set parent references for children
        for child in self.children:
            child.parent = self


class MockSyntax:
    """Mock syntax tree for testing."""
    
    def __init__(self, root_node):
        self.root = root_node
    
    def walk(self):
        """Walk the tree and yield all nodes."""
        def _walk(node):
            yield node
            for child in getattr(node, 'children', []):
                yield from _walk(child)
        
        return _walk(self.root)


class MockAdapter:
    """Mock adapter for testing."""
    
    def __init__(self, language='python'):
        self.lang = language
        
    def language_id(self):
        return self.lang


class TestSecWeakHashingRule:
    """Test cases for the weak hashing detection rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecWeakHashingRule()
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a test context with parsed structure."""
        # Parse the code based on its pattern
        root_node = self._parse_code(code, language)
        tree = MockSyntax(root_node)
        adapter = MockAdapter(language)
        
        return RuleContext(
            file_path=f"test.{self._get_file_extension(language)}",
            text=code,
            tree=tree,
            adapter=adapter,
            config={}
        )
    
    def _get_file_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            'python': 'py',
            'javascript': 'js',
            'ruby': 'rb',
            'java': 'java',
            'csharp': 'cs',
            'go': 'go'
        }
        return extensions.get(language, 'txt')
    
    def _parse_code(self, code: str, language: str) -> MockNode:
        """Parse code into mock AST based on patterns."""
        # Detect function calls with parentheses
        if '(' in code and ')' in code:
            return self._parse_call_expression(code)
        
        # Default expression
        return MockNode(
            kind='expression_statement',
            text=code,
            children=[MockNode(kind='identifier', text=code)]
        )
    
    def _parse_call_expression(self, code: str) -> MockNode:
        """Parse function call expressions."""
        paren_pos = code.index('(')
        callee_part = code[:paren_pos].strip()
        args_part = code[paren_pos + 1:code.rindex(')')].strip()
        
        # Create callee node
        callee_node = self._parse_callee(callee_part)
        
        # Create arguments
        arg_nodes = []
        if args_part:
            # Simple argument parsing
            args = self._split_arguments(args_part)
            for arg in args:
                arg_nodes.append(self._parse_expression(arg.strip()))
        
        # Create arguments list node
        args_node = MockNode(
            kind='arguments',
            text=f"({args_part})",
            children=arg_nodes
        )
        
        return MockNode(
            kind='call_expression',
            text=code,
            children=[callee_node, args_node]
        )

    def _parse_callee(self, callee_part: str) -> MockNode:
        """Parse callee part of function call."""
        if '.' in callee_part:
            # Member expression like hashlib.md5 or crypto.createHash
            parts = callee_part.split('.')
            if len(parts) == 2:
                obj_name, method_name = parts
                return MockNode(
                    kind='member_expression',
                    text=callee_part,
                    children=[
                        MockNode(kind='identifier', text=obj_name),
                        MockNode(kind='property_identifier', text=method_name)
                    ]
                )
            else:
                # Complex member expression
                return MockNode(kind='member_expression', text=callee_part)
        else:
            return MockNode(kind='identifier', text=callee_part)
    
    def _parse_expression(self, expr: str) -> MockNode:
        """Parse a simple expression."""
        expr = expr.strip()
        if expr.startswith('"') or expr.startswith("'"):
            return MockNode(kind='string_literal', text=expr)
        elif expr.isdigit():
            return MockNode(kind='integer_literal', text=expr)
        else:
            return MockNode(kind='identifier', text=expr)
    
    def _split_arguments(self, args_str: str) -> list:
        """Split function arguments, handling nested parentheses and quotes."""
        args = []
        current_arg = ""
        paren_count = 0
        quote_char = None
        
        for char in args_str:
            if quote_char:
                current_arg += char
                if char == quote_char:
                    quote_char = None
            elif char in '"\'':
                quote_char = char
                current_arg += char
            elif char == '(':
                paren_count += 1
                current_arg += char
            elif char == ')':
                paren_count -= 1
                current_arg += char
            elif char == ',' and paren_count == 0:
                if current_arg.strip():
                    args.append(current_arg.strip())
                current_arg = ""
            else:
                current_arg += char
        
        if current_arg.strip():
            args.append(current_arg.strip())
        
        return args

    def test_rule_metadata(self):
        """Test that rule metadata is correct."""
        assert self.rule.meta.id == "sec.weak_hashing"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert "python" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert "go" in self.rule.meta.langs
        assert self.rule.meta.autofix_safety == "suggest-only"
    
    # Positive test cases - should detect vulnerabilities
    
    def test_positive_python_hashlib_md5(self):
        """Test Python hashlib.md5 detection."""
        code = 'hashlib.md5(password.encode()).hexdigest()'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
        assert "md5" in findings[0].message.lower()
    
    def test_positive_python_hashlib_sha1(self):
        """Test Python hashlib.sha1 detection."""
        code = 'hashlib.sha1(token).hexdigest()'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
        assert "sha-1" in findings[0].message.lower()
    
    def test_positive_javascript_createhash_md5(self):
        """Test JavaScript crypto.createHash with MD5."""
        code = 'crypto.createHash("md5").update(secret).digest("hex")'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_javascript_subtle_digest_sha1(self):
        """Test JavaScript Web Crypto subtle.digest with SHA-1."""
        code = 'window.crypto.subtle.digest("SHA-1", data)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_ruby_digest_md5(self):
        """Test Ruby Digest::MD5 detection."""
        code = 'Digest::MD5.hexdigest(password)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_ruby_digest_sha1(self):
        """Test Ruby Digest::SHA1 detection."""
        code = 'Digest::SHA1.hexdigest(token)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_java_messagedigest_md5(self):
        """Test Java MessageDigest.getInstance with MD5."""
        code = 'MessageDigest.getInstance("MD5")'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_java_messagedigest_sha1(self):
        """Test Java MessageDigest.getInstance with SHA-1."""
        code = 'java.security.MessageDigest.getInstance("SHA-1")'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_csharp_md5_create(self):
        """Test C# MD5.Create detection."""
        code = 'MD5.Create()'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_csharp_sha1_create(self):
        """Test C# SHA1.Create detection."""
        code = 'System.Security.Cryptography.SHA1.Create()'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_go_md5_new(self):
        """Test Go md5.New detection."""
        code = 'md5.New()'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    def test_positive_go_sha1_sum(self):
        """Test Go sha1.Sum detection."""
        code = 'sha1.Sum([]byte(password))'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "weak hashing" in findings[0].message.lower()
    
    # Negative test cases - should NOT detect (strong alternatives)
    
    def test_negative_python_bcrypt(self):
        """Test Python bcrypt is not flagged."""
        code = 'bcrypt.hashpw(password, bcrypt.gensalt())'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_python_argon2(self):
        """Test Python Argon2 is not flagged."""
        code = 'argon2.hash(password)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_hmac_sha256(self):
        """Test JavaScript HMAC-SHA256 is not flagged."""
        code = 'crypto.createHmac("sha256", key).update(data).digest("hex")'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_subtle_digest_sha256(self):
        """Test JavaScript Web Crypto with SHA-256 is not flagged."""
        code = 'window.crypto.subtle.digest("SHA-256", data)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_bcrypt(self):
        """Test Ruby BCrypt is not flagged."""
        code = 'BCrypt::Password.create(password)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_java_hmac_sha256(self):
        """Test Java HMAC-SHA256 is not flagged."""
        code = 'javax.crypto.Mac.getInstance("HmacSHA256")'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_java_sha256(self):
        """Test Java SHA-256 is not flagged."""
        code = 'MessageDigest.getInstance("SHA-256")'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_csharp_hmac_sha256(self):
        """Test C# HMACSHA256 is not flagged."""
        code = 'System.Security.Cryptography.HMACSHA256(key)'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_go_hmac_sha256(self):
        """Test Go HMAC-SHA256 is not flagged."""
        code = 'hmac.New(sha256.New, key)'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # Algorithm parameter detection tests
    
    def test_algorithm_param_detection_weak(self):
        """Test detection of weak algorithms in parameters."""
        test_cases = [
            ('javascript', 'crypto.createHash("md5")'),
            ('javascript', 'window.crypto.subtle.digest("SHA-1", data)'),
            ('java', 'MessageDigest.getInstance("MD5")'),
            ('java', 'MessageDigest.getInstance("SHA-1")'),
        ]
        
        for lang, code in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect weak hashing in {lang}: {code}"
    
    def test_algorithm_param_detection_strong(self):
        """Test that strong algorithms in parameters are not flagged."""
        test_cases = [
            ('javascript', 'crypto.createHash("sha256")'),
            ('javascript', 'window.crypto.subtle.digest("SHA-256", data)'),
            ('java', 'MessageDigest.getInstance("SHA-256")'),
            ('java', 'MessageDigest.getInstance("SHA-512")'),
        ]
        
        for lang, code in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT detect strong hashing in {lang}: {code}"
    
    # Sensitive context detection tests
    
    def test_sensitive_context_detection(self):
        """Test detection of sensitive variable context."""
        test_cases = [
            ('python', 'hashlib.md5(user_password.encode()).hexdigest()'),
            ('javascript', 'crypto.createHash("md5").update(authToken).digest()'),
            ('ruby', 'Digest::MD5.hexdigest(user_secret)'),
            ('java', 'MessageDigest.getInstance("MD5").digest(apiKey.getBytes())'),
        ]
        
        for lang, code in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect sensitive context in {lang}: {code}"
    
    # Comprehensive coverage tests
    
    def test_comprehensive_positive_coverage(self):
        """Test comprehensive coverage of weak hashing patterns."""
        positive_cases = [
            # Python
            ('python', 'hashlib.md5(password.encode()).hexdigest()', True),
            ('python', 'hashlib.sha1(token).hexdigest()', True),
            
            # JavaScript
            ('javascript', 'crypto.createHash("md5").update(secret)', True),
            ('javascript', 'crypto.subtle.digest("SHA-1", data)', True),
            
            # Ruby
            ('ruby', 'Digest::MD5.hexdigest(password)', True),
            ('ruby', 'Digest::SHA1.new()', True),
            
            # Java
            ('java', 'MessageDigest.getInstance("MD5")', True),
            ('java', 'MessageDigest.getInstance("SHA-1")', True),
            
            # C#
            ('csharp', 'MD5.Create()', True),
            ('csharp', 'SHA1.Create()', True),
            
            # Go
            ('go', 'md5.New()', True),
            ('go', 'sha1.Sum([]byte(password))', True),
        ]
        
        weak_count = 0
        for lang, code, should_violate in positive_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            if should_violate:
                assert len(findings) >= 1, f"Should detect violation in {lang}: {code}"
                weak_count += len(findings)
        
        assert weak_count >= 12, f"Expected at least 12 weak hashing detections, got {weak_count}"
    
    def test_comprehensive_negative_coverage(self):
        """Test comprehensive coverage of strong alternatives."""
        negative_cases = [
            # Python - strong alternatives
            ('python', 'bcrypt.hashpw(password, bcrypt.gensalt())', False),
            ('python', 'argon2.hash(password)', False),
            ('python', 'hashlib.sha256(data).hexdigest()', False),
            
            # JavaScript - strong alternatives
            ('javascript', 'crypto.createHmac("sha256", key).digest()', False),
            ('javascript', 'crypto.subtle.digest("SHA-256", data)', False),
            
            # Ruby - strong alternatives
            ('ruby', 'BCrypt::Password.create(password)', False),
            ('ruby', 'Digest::SHA256.hexdigest(data)', False),
            
            # Java - strong alternatives
            ('java', 'MessageDigest.getInstance("SHA-256")', False),
            ('java', 'javax.crypto.Mac.getInstance("HmacSHA256")', False),
            
            # C# - strong alternatives
            ('csharp', 'System.Security.Cryptography.HMACSHA256(key)', False),
            ('csharp', 'SHA256.Create()', False),
            
            # Go - strong alternatives
            ('go', 'hmac.New(sha256.New, key)', False),
            ('go', 'sha256.New()', False),
        ]
        
        for lang, code, should_violate in negative_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT detect violation in {lang}: {code}"
    
    def test_severity_and_span_reporting(self):
        """Test that severity and span are correctly reported."""
        code = 'hashlib.md5(password.encode()).hexdigest()'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        
        finding = findings[0]
        assert finding.severity == "warning"
        assert finding.rule == "sec.weak_hashing"
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        assert "argon2" in finding.message.lower() or "bcrypt" in finding.message.lower()
        assert "hmac" in finding.message.lower()

