"""Test suite for the insecure random number generator detection rule.

Tests detection of non-cryptographic RNG usage across multiple languages
and ensures proper identification of vulnerable patterns while avoiding 
false positives for cryptographically secure alternatives.
"""

import pytest
from engine.types import RuleContext, RuleMeta, Requires
from rules.sec_insecure_random import SecInsecureRandomRule


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


class TestSecInsecureRandomRule:
    """Test cases for the insecure random number generator detection rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecInsecureRandomRule()
    
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
        # Detect assignment expressions like "var = value"
        if '=' in code and not '==' in code and not '!=' in code:
            return self._parse_assignment_expression(code)
        
        # Detect member expressions like Math.random
        elif '.' in code and not '(' in code:
            return self._parse_member_expression(code)
        
        # Detect function calls with parentheses
        elif '(' in code and ')' in code:
            return self._parse_call_expression(code)
        
        # Detect constructor calls like "new Random()"
        elif 'new ' in code:
            return self._parse_new_expression(code)
        
        # Default expression
        return MockNode(
            kind='expression_statement',
            text=code,
            children=[MockNode(kind='identifier', text=code)]
        )
    
    def _parse_assignment_expression(self, code: str) -> MockNode:
        """Parse assignment expressions like 'var = value'."""
        parts = code.split('=', 1)
        if len(parts) == 2:
            left_part = parts[0].strip()
            right_part = parts[1].strip()
            
            # Create left side (variable)
            left_node = MockNode(kind='identifier', text=left_part)
            
            # Create right side (value expression)
            right_node = self._parse_expression_for_assignment(right_part)
            
            return MockNode(
                kind='assignment_expression',
                text=code,
                children=[
                    left_node,
                    MockNode(kind='assignment_operator', text='='),
                    right_node
                ]
            )
        
        return MockNode(kind='expression_statement', text=code)
    
    def _parse_expression_for_assignment(self, expr: str) -> MockNode:
        """Parse the right-hand side of an assignment."""
        expr = expr.strip()
        
        # Function call
        if '(' in expr and ')' in expr:
            return self._parse_call_expression(expr)
        
        # Member expression
        elif '.' in expr:
            return self._parse_member_expression(expr)
        
        # Constructor
        elif expr.startswith('new '):
            return self._parse_new_expression(expr)
        
        # Simple expression
        else:
            return self._parse_expression(expr)
    
    def _parse_member_expression(self, code: str) -> MockNode:
        """Parse member expressions like Math.random."""
        if '.' in code:
            parts = code.split('.')
            if len(parts) == 2:
                obj_name, prop_name = parts
                return MockNode(
                    kind='member_expression',
                    text=code,
                    children=[
                        MockNode(kind='identifier', text=obj_name),
                        MockNode(kind='property_identifier', text=prop_name)
                    ]
                )
        
        return MockNode(kind='identifier', text=code)
    
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
    
    def _parse_new_expression(self, code: str) -> MockNode:
        """Parse constructor expressions like 'new Random()'."""
        # Remove 'new ' prefix
        constructor_part = code[4:].strip()
        
        if '(' in constructor_part:
            paren_pos = constructor_part.index('(')
            type_name = constructor_part[:paren_pos].strip()
            args_part = constructor_part[paren_pos + 1:constructor_part.rindex(')')].strip()
        else:
            type_name = constructor_part
            args_part = ""
        
        # Create type identifier
        type_node = MockNode(kind='type_identifier', text=type_name)
        
        # Create arguments
        arg_nodes = []
        if args_part:
            args = self._split_arguments(args_part)
            for arg in args:
                arg_nodes.append(self._parse_expression(arg.strip()))
        
        args_node = MockNode(
            kind='arguments',
            text=f"({args_part})",
            children=arg_nodes
        )
        
        return MockNode(
            kind='new_expression',
            text=code,
            children=[type_node, args_node]
        )

    def _parse_callee(self, callee_part: str) -> MockNode:
        """Parse callee part of function call."""
        if '.' in callee_part:
            # Member expression like random.random
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
        assert self.rule.meta.id == "sec.insecure_random"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P1"
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert "go" in self.rule.meta.langs
        assert self.rule.meta.autofix_safety == "suggest-only"
    
    # Positive test cases - should detect vulnerabilities
    
    def test_positive_python_random_random(self):
        """Test Python random.random detection."""
        code = 'random.random()'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "secrets" in findings[0].message.lower()
    
    def test_positive_python_random_randint(self):
        """Test Python random.randint detection."""
        code = 'random.randint(1, 100)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "secrets" in findings[0].message.lower()
    
    def test_positive_javascript_math_random(self):
        """Test JavaScript Math.random detection."""
        code = 'Math.random'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "crypto.getrandomvalues" in findings[0].message.lower()  # Fixed: lowercase check
    
    def test_positive_javascript_math_random_call(self):
        """Test JavaScript Math.random() call detection."""
        code = 'Math.random()'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "crypto.getrandomvalues" in findings[0].message.lower()  # Fixed: lowercase check
    
    def test_positive_java_random_constructor(self):
        """Test Java Random constructor detection."""
        code = 'new Random()'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "SecureRandom" in findings[0].message
    
    def test_positive_java_random_method(self):
        """Test Java Random method call detection."""
        code = 'random.nextInt()'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "SecureRandom" in findings[0].message
    
    def test_positive_csharp_random_constructor(self):
        """Test C# Random constructor detection."""
        code = 'new Random()'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "RandomNumberGenerator" in findings[0].message
    
    def test_positive_ruby_random_rand(self):
        """Test Ruby Random.rand detection."""
        code = 'Random.rand'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "SecureRandom" in findings[0].message
    
    def test_positive_ruby_kernel_rand(self):
        """Test Ruby Kernel.rand detection."""
        code = 'rand(16)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "SecureRandom" in findings[0].message
    
    def test_positive_go_math_rand(self):
        """Test Go math/rand detection."""
        code = 'rand.Int()'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "non-cryptographic rng" in findings[0].message.lower()
        assert "crypto/rand" in findings[0].message
    
    # Negative test cases - should NOT detect (cryptographically secure alternatives)
    
    def test_negative_python_secrets(self):
        """Test Python secrets module is not flagged."""
        code = 'secrets.token_urlsafe(32)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_python_secrets_randbelow(self):
        """Test Python secrets.randbelow is not flagged."""
        code = 'secrets.randbelow(100)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_crypto_getrandomvalues(self):
        """Test JavaScript crypto.getRandomValues is not flagged."""
        code = 'crypto.getRandomValues(new Uint8Array(16))'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_java_securerandom(self):
        """Test Java SecureRandom is not flagged."""
        code = 'new SecureRandom()'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_java_securerandom_method(self):
        """Test Java SecureRandom method call is not flagged."""
        code = 'secureRandom.nextBytes(bytes)'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_csharp_randomnumbergenerator(self):
        """Test C# RandomNumberGenerator is not flagged."""
        code = 'RandomNumberGenerator.GetBytes(16)'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_securerandom(self):
        """Test Ruby SecureRandom is not flagged."""
        code = 'SecureRandom.hex(16)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_go_crypto_rand(self):
        """Test Go crypto/rand is not flagged."""
        code = 'cryptorand.Read(bytes)'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # Comprehensive coverage tests
    
    def test_comprehensive_positive_coverage(self):
        """Test comprehensive coverage of insecure RNG patterns."""
        positive_cases = [
            # Python
            ('python', 'random.random()', True),
            ('python', 'random.randint(1, 10)', True),
            ('python', 'random.choice([1, 2, 3])', True),
            
            # JavaScript
            ('javascript', 'Math.random', True),
            ('javascript', 'Math.random()', True),
            
            # Java
            ('java', 'new Random()', True),
            ('java', 'Random.nextInt()', True),
            ('java', 'ThreadLocalRandom.current()', True),
            
            # C#
            ('csharp', 'new Random()', True),
            ('csharp', 'Random.Next()', True),
            
            # Ruby
            ('ruby', 'Random.rand', True),
            ('ruby', 'rand(16)', True),
            
            # Go
            ('go', 'rand.Int()', True),
            ('go', 'rand.Intn(100)', True),
        ]
        
        insecure_count = 0
        for lang, code, should_violate in positive_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            if should_violate:
                assert len(findings) >= 1, f"Should detect violation in {lang}: {code}"
                insecure_count += len(findings)
        
        assert insecure_count >= 14, f"Expected at least 14 insecure RNG detections, got {insecure_count}"
    
    def test_comprehensive_negative_coverage(self):
        """Test comprehensive coverage of secure alternatives."""
        negative_cases = [
            # Python - secure alternatives
            ('python', 'secrets.token_urlsafe(32)', False),
            ('python', 'secrets.randbelow(100)', False),
            ('python', 'secrets.choice([1, 2, 3])', False),
            
            # JavaScript - secure alternatives
            ('javascript', 'crypto.getRandomValues(new Uint8Array(16))', False),
            ('javascript', 'window.crypto.getRandomValues(bytes)', False),
            
            # Java - secure alternatives
            ('java', 'new SecureRandom()', False),
            ('java', 'SecureRandom.getInstanceStrong()', False),
            
            # C# - secure alternatives
            ('csharp', 'RandomNumberGenerator.GetBytes(16)', False),
            ('csharp', 'RNGCryptoServiceProvider.GetBytes(bytes)', False),
            
            # Ruby - secure alternatives
            ('ruby', 'SecureRandom.hex(16)', False),
            ('ruby', 'SecureRandom.random_bytes(16)', False),
            
            # Go - secure alternatives
            ('go', 'cryptorand.Read(bytes)', False),
            ('go', 'cryptorand.Int(max)', False),
        ]
        
        for lang, code, should_violate in negative_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT detect violation in {lang}: {code}"
    
    def test_language_specific_recommendations(self):
        """Test that language-specific recommendations are provided."""
        test_cases = [
            ('python', 'random.random()', 'secrets'),
            ('javascript', 'Math.random()', 'crypto.getRandomValues'),
            ('java', 'new Random()', 'SecureRandom'),
            ('csharp', 'new Random()', 'RandomNumberGenerator'),
            ('ruby', 'rand(16)', 'SecureRandom'),
            ('go', 'rand.Int()', 'crypto/rand'),
        ]
        
        for lang, code, expected_recommendation in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect issue in {lang}: {code}"
            assert expected_recommendation in findings[0].message, \
                f"Should recommend {expected_recommendation} for {lang}"
    
    def test_severity_and_span_reporting(self):
        """Test that severity and span are correctly reported."""
        code = 'random.random()'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        
        finding = findings[0]
        assert finding.severity == "warning"
        assert finding.rule == "sec.insecure_random"
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        assert "secrets" in finding.message
    
    def test_suggest_only_no_autofix(self):
        """Test that the rule provides suggestions without autofix edits."""
        code = 'Math.random()'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        
        # Check that no autofix is provided (suggest-only)
        finding = findings[0]
        assert not hasattr(finding, 'edit') or finding.edit is None
        assert "crypto.getrandomvalues" in finding.message.lower()  # Fixed: lowercase check
    
    def test_sensitive_context_detection(self):
        """Test detection in sensitive variable contexts."""
        test_cases = [
            ('python', 'password_salt = random.random()'),
            ('javascript', 'const token = Math.random()'),
            ('java', 'String secret = new Random().toString()'),
            ('ruby', 'api_key = rand(16)'),
        ]
        
        for lang, code in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            # Even without sensitive context detection in current implementation,
            # the rule should still flag insecure RNG usage
            assert len(findings) >= 1, f"Should detect insecure RNG in {lang}: {code}"

