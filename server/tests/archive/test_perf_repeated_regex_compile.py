"""
Tests for perf.repeated_regex_compile rule.

Tests regex compilation detection inside loops across multiple languages.
"""

import pytest
from rules.perf_repeated_regex_compile import PerfRepeatedRegexCompileRule


class MockNode:
    """Mock syntax tree node for testing."""
    
    def __init__(self, kind='', children=None, parent=None, text='', start_byte=0, end_byte=None, **kwargs):
        self.kind = kind
        self.type = kind  # tree-sitter uses 'type'
        self.children = children or []
        self.parent = parent
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else start_byte + len(str(text))
        
        # Common attributes for function calls
        self.callee = None
        self.function = None
        self.name = None
        self.arguments = None
        
        # Set additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Set up parent-child relationships
        for child in self.children:
            if child:
                child.parent = self


class MockSyntax:
    """Mock syntax tree for testing."""
    
    def __init__(self, root_node=None):
        self.root_node = root_node
    
    def node_span(self, node):
        """Return mock span for node."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 10))
    
    def token_text(self, token):
        """Return text for token."""
        if hasattr(token, 'text'):
            text = token.text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return str(text)
        return str(token)
    
    def iter_tokens(self, node):
        """Iterate tokens in node."""
        if hasattr(node, 'text'):
            return [node]
        return []


class MockRuleContext:
    """Mock rule context for testing."""
    
    def __init__(self, language='python', root_node=None):
        self.language = language
        self.file_path = f'test.{language}'
        self.syntax = MockSyntax(root_node)


def create_regex_compile_loop(language='python', compile_call='re.compile', pattern='"ab+c"', loop_kind='for_statement'):
    """Create a mock loop with regex compilation for testing."""
    
    # Create regex compile call
    callee_node = MockNode(kind='identifier', text=compile_call, start_byte=20, end_byte=20 + len(compile_call))
    arg_node = MockNode(kind='string_literal', text=pattern, start_byte=30, end_byte=30 + len(pattern))
    args_node = MockNode(kind='arguments', children=[arg_node], start_byte=29, end_byte=32)
    
    call_node = MockNode(
        kind='call_expression',
        callee=callee_node,
        arguments=args_node,
        text=f'{compile_call}({pattern})',
        start_byte=20,
        end_byte=35
    )
    callee_node.parent = call_node
    args_node.parent = call_node
    
    # Create loop body with the call
    loop_body = MockNode(kind='block', children=[call_node], start_byte=15, end_byte=40)
    call_node.parent = loop_body
    
    # Create the loop
    loop_text = f"for item in items: {compile_call}({pattern})"
    loop_node = MockNode(
        kind=loop_kind,
        children=[loop_body],
        text=loop_text,
        start_byte=0,
        end_byte=len(loop_text)
    )
    loop_body.parent = loop_node
    
    return loop_node


def create_regex_literal_loop(language='javascript', literal_pattern='/ab+c/i', loop_kind='for_of_statement'):
    """Create a mock loop with regex literal for testing."""
    
    # Create regex literal
    regex_node = MockNode(
        kind='regex_literal',
        text=literal_pattern,
        start_byte=20,
        end_byte=20 + len(literal_pattern)
    )
    
    # Create loop body with the literal
    loop_body = MockNode(kind='block', children=[regex_node], start_byte=15, end_byte=40)
    regex_node.parent = loop_body
    
    # Create the loop
    loop_text = f"for (item of items) {{ {literal_pattern}.test(item) }}"
    loop_node = MockNode(
        kind=loop_kind,
        children=[loop_body],
        text=loop_text,
        start_byte=0,
        end_byte=len(loop_text)
    )
    loop_body.parent = loop_node
    
    return loop_node


def create_hoisted_regex_pattern(language='python', compile_call='re.compile', pattern='"ab+c"'):
    """Create a pattern where regex is compiled outside the loop."""
    
    # Create regex compile call outside loop
    callee_node = MockNode(kind='identifier', text=compile_call)
    call_node = MockNode(kind='call_expression', callee=callee_node, text=f'{compile_call}({pattern})')
    
    # Create loop that uses the pre-compiled regex
    loop_body = MockNode(kind='block', text='compiled_regex.search(item)')
    loop_node = MockNode(kind='for_statement', children=[loop_body])
    loop_body.parent = loop_node
    
    # Create root with compile outside and loop
    root_node = MockNode(kind='source_file', children=[call_node, loop_node])
    call_node.parent = root_node
    loop_node.parent = root_node
    
    return root_node


class TestPerfRepeatedRegexCompile:
    """Test cases for repeated regex compilation detection."""
    
    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        rule = PerfRepeatedRegexCompileRule()
        
        assert rule.meta.id == "perf.repeated_regex_compile"
        assert rule.meta.category == "perf"
        assert rule.meta.tier == 0
        assert rule.meta.priority == "P2"
        assert rule.meta.autofix_safety == "suggest-only"
        assert rule.requires.syntax == True
        
        expected_languages = {"python", "javascript", "java", "csharp", "ruby", "go"}
        assert set(rule.meta.langs) == expected_languages
    
    def test_compile_signatures(self):
        """Test regex compilation signature detection."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Test signature matching for different languages
        assert rule._matches_compile_signature("re.compile", "re.compile", "python") == True
        assert rule._matches_compile_signature("RegExp", "RegExp", "javascript") == True
        assert rule._matches_compile_signature("new RegExp", "RegExp", "javascript") == True
        assert rule._matches_compile_signature("Pattern.compile", "Pattern.compile", "java") == True
        assert rule._matches_compile_signature("new Regex", "Regex", "csharp") == True
        assert rule._matches_compile_signature("Regexp.new", "Regexp.new", "ruby") == True
        assert rule._matches_compile_signature("regexp.MustCompile", "regexp.MustCompile", "go") == True
        
        # Test non-matches
        assert rule._matches_compile_signature("unrelated.call", "re.compile", "python") == False
    
    def test_loop_detection(self):
        """Test _in_loop helper correctly identifies nodes inside loops."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create nested structure
        loop_node = create_regex_compile_loop('python')
        call_node = loop_node.children[0].children[0]  # The call inside the loop
        
        assert rule._in_loop(call_node) == True
        assert rule._in_loop(loop_node) == False  # The loop itself is not "in" a loop
    
    def test_positive_case_python(self):
        """Test positive case for Python regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create Python loop with re.compile
        loop_node = create_regex_compile_loop('python', 're.compile', 'r"ab+c"')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
        assert "hoist/precompile outside the loop" in findings[0].message
        assert findings[0].severity == "info"
        assert findings[0].rule == "perf.repeated_regex_compile"
    
    def test_positive_case_javascript(self):
        """Test positive case for JavaScript regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create JavaScript loop with new RegExp
        loop_node = create_regex_compile_loop('javascript', 'RegExp', '"ab+c"', 'for_of_statement')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('javascript', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
    
    def test_positive_case_java(self):
        """Test positive case for Java regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create Java loop with Pattern.compile
        loop_node = create_regex_compile_loop('java', 'Pattern.compile', '"ab+c"', 'enhanced_for_statement')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('java', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
    
    def test_positive_case_csharp(self):
        """Test positive case for C# regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create C# loop with new Regex
        loop_node = create_regex_compile_loop('csharp', 'new Regex', '"ab+c"', 'foreach_statement')
        # Update the call node to be a constructor call
        call_node = loop_node.children[0].children[0]
        call_node.kind = 'object_creation_expression'
        
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('csharp', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
    
    def test_positive_case_ruby(self):
        """Test positive case for Ruby regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create Ruby loop with Regexp.new
        loop_node = create_regex_compile_loop('ruby', 'Regexp.new', '"ab+c"')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('ruby', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
    
    def test_positive_case_go(self):
        """Test positive case for Go regex compilation."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create Go loop with regexp.MustCompile
        loop_node = create_regex_compile_loop('go', 'regexp.MustCompile', '`ab+c`', 'range_for_statement')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('go', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex compiled inside loop" in findings[0].message
    
    def test_positive_case_javascript_literal(self):
        """Test positive case for JavaScript regex literal."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create JavaScript loop with regex literal
        loop_node = create_regex_literal_loop('javascript', '/ab+c/i')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('javascript', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex literal created per-iteration" in findings[0].message
        assert "hoisting it outside the loop" in findings[0].message
    
    def test_positive_case_ruby_literal(self):
        """Test positive case for Ruby regex literal."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create Ruby loop with regex literal
        loop_node = create_regex_literal_loop('ruby', '/ab+c/i')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('ruby', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Regex literal created per-iteration" in findings[0].message
    
    def test_negative_case_hoisted_python(self):
        """Test negative case for Python with hoisted regex."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create pattern with regex compiled outside loop
        root_node = create_hoisted_regex_pattern('python', 're.compile', 'r"ab+c"')
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_hoisted_javascript(self):
        """Test negative case for JavaScript with hoisted regex."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create pattern with regex literal outside loop
        root_node = create_hoisted_regex_pattern('javascript', 'RegExp', '/ab+c/i')
        ctx = MockRuleContext('javascript', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_non_loop_compile(self):
        """Test that regex compilation outside loops is not flagged."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create regex compile call outside a loop
        callee_node = MockNode(kind='identifier', text='re.compile')
        call_node = MockNode(kind='call_expression', callee=callee_node)
        
        root_node = MockNode(kind='source_file', children=[call_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_multiple_languages_comprehensive(self):
        """Test detection across multiple languages in comprehensive scenarios."""
        rule = PerfRepeatedRegexCompileRule()
        
        test_cases = [
            ('python', 're.compile', 'r"ab+c"'),
            ('javascript', 'RegExp', '"ab+c"'),
            ('java', 'Pattern.compile', '"ab+c"'),
            ('csharp', 'new Regex', '"ab+c"'),
            ('ruby', 'Regexp.new', '"ab+c"'),
            ('go', 'regexp.MustCompile', '`ab+c`'),
        ]
        
        total_findings = 0
        for lang, compile_func, pattern in test_cases:
            loop_node = create_regex_compile_loop(lang, compile_func, pattern)
            if lang == 'csharp':
                # Update C# call to be constructor
                call_node = loop_node.children[0].children[0]
                call_node.kind = 'object_creation_expression'
            
            root_node = MockNode(kind='source_file', children=[loop_node])
            ctx = MockRuleContext(lang, root_node)
            
            findings = list(rule.visit(ctx))
            assert len(findings) == 1, f"Expected 1 finding for {lang}, got {len(findings)}"
            total_findings += len(findings)
        
        assert total_findings == 6
    
    def test_edge_case_nested_loops(self):
        """Test regex compilation in nested loops."""
        rule = PerfRepeatedRegexCompileRule()
        
        # Create inner loop with regex compilation
        inner_loop = create_regex_compile_loop('python', 're.compile', 'r"ab+c"')
        
        # Create outer loop containing the inner loop
        outer_loop = MockNode(
            kind='for_statement', 
            children=[inner_loop],
            text='for i in range(10): for item in items: re.compile(r"ab+c")',
            start_byte=0,
            end_byte=50
        )
        inner_loop.parent = outer_loop
        
        root_node = MockNode(kind='source_file', children=[outer_loop])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) >= 1  # Should find at least one regex compilation
    
    def test_function_call_detection(self):
        """Test function call detection helper methods."""
        rule = PerfRepeatedRegexCompileRule()
        ctx = MockRuleContext()
        
        # Test function call detection
        call_node = MockNode(kind='call_expression')
        assert rule._is_function_call(call_node) == True
        
        constructor_node = MockNode(kind='new_expression')
        assert rule._is_function_call(constructor_node) == True
        
        non_call_node = MockNode(kind='identifier')
        assert rule._is_function_call(non_call_node) == False
        
        # Test callee text extraction
        callee = MockNode(kind='identifier', text='re.compile')
        call_with_callee = MockNode(kind='call_expression', callee=callee)
        callee_text = rule._get_callee_text(call_with_callee, ctx)
        assert 'compile' in callee_text
    
    def test_regex_literal_detection(self):
        """Test regex literal detection for JavaScript and Ruby."""
        rule = PerfRepeatedRegexCompileRule()
        ctx_js = MockRuleContext('javascript')
        ctx_ruby = MockRuleContext('ruby')
        ctx_python = MockRuleContext('python')
        
        # Test JavaScript regex literal
        js_regex = MockNode(kind='regex_literal', text='/ab+c/i')
        assert rule._regex_literal_in_loop(js_regex, 'javascript', ctx_js) == True
        
        # Test Ruby regex literal
        ruby_regex = MockNode(kind='regex_literal', text='/ab+c/i')
        assert rule._regex_literal_in_loop(ruby_regex, 'ruby', ctx_ruby) == True
        
        # Test Python (no regex literals)
        python_string = MockNode(kind='string_literal', text='"ab+c"')
        assert rule._regex_literal_in_loop(python_string, 'python', ctx_python) == False
        
        # Test non-regex node
        identifier = MockNode(kind='identifier', text='variable')
        assert rule._regex_literal_in_loop(identifier, 'javascript', ctx_js) == False

