"""Test suite for sec.xss_unescaped_html rule.

Tests XSS unescaped HTML injection detection across multiple languages including
JavaScript/TypeScript DOM manipulation, React JSX, Ruby Rails helpers, and Python Django.
"""

import pytest
from engine.types import RuleContext
from rules.sec_xss_unescaped_html import SecXssUnescapedHtmlRule


class MockNode:
    """Mock syntax tree node for testing."""
    
    def __init__(self, kind='', text='', start_byte=0, end_byte=None, children=None, **kwargs):
        self.kind = kind
        self.type = kind
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else start_byte + len(str(text))
        self.children = children or []
        
        # Add any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)


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


class MockAdapter:
    """Mock adapter for testing."""
    
    def __init__(self, language='javascript'):
        self.lang = language
        
    def language_id(self):
        return self.lang


class TestSecXssUnescapedHtmlRule:
    """Test cases for the XSS unescaped HTML rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecXssUnescapedHtmlRule()
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a test context with parsed structure."""
        # Parse the code based on its pattern
        root_node = self._parse_code(code, language)
        tree = MockSyntax(root_node)
        adapter = MockAdapter(language)
        
        return RuleContext(
            file_path="test.js" if language in ['javascript', 'typescript'] else f"test.{language[0:2]}",
            text=code,
            tree=tree,
            adapter=adapter,
            config={}
        )
    
    def _parse_code(self, code: str, language: str) -> MockNode:
        """Parse code into mock AST based on patterns."""
        # JavaScript/TypeScript assignment: el.innerHTML = expr
        if '=' in code and any(prop in code for prop in ['innerHTML', 'outerHTML']):
            return self._parse_assignment(code)
        
        # Method calls with parentheses: document.write(), insertAdjacentHTML(), mark_safe(), etc.
        elif '(' in code and ')' in code:
            return self._parse_call_expression(code)
        
        # Ruby method calls without parentheses: params[:bio].html_safe
        elif language == 'ruby' and '.html_safe' in code and '(' not in code:
            return self._parse_ruby_method_call(code)
            
        # JSX dangerouslySetInnerHTML
        elif 'dangerouslySetInnerHTML' in code:
            return self._parse_jsx_attribute(code)
        
        # Default expression
        else:
            return MockNode(
                kind='expression_statement',
                text=code,
                children=[MockNode(kind='identifier', text=code)]
            )
    
    def _parse_ruby_method_call(self, code: str) -> MockNode:
        """Parse Ruby method calls without parentheses like params[:bio].html_safe."""
        if '.html_safe' in code:
            parts = code.split('.html_safe', 1)
            receiver_part = parts[0].strip()
            
            # Parse the receiver (params[:bio])
            receiver_node = self._parse_complex_expression(receiver_part)
            
            # Create method call node
            return MockNode(
                kind='call_expression',
                text=code,
                children=[
                    MockNode(
                        kind='member_expression',
                        text=code,
                        children=[
                            receiver_node,
                            MockNode(kind='property_identifier', text='html_safe')
                        ]
                    ),
                    MockNode(kind='arguments', text='', children=[])  # No args for parameterless call
                ]
            )
        
        return MockNode(kind='expression_statement', text=code)
    
    def _parse_assignment(self, code: str) -> MockNode:
        """Parse assignment expressions like el.innerHTML = expr."""
        parts = code.split('=')
        if len(parts) >= 2:
            left_part = parts[0].strip()
            right_part = '='.join(parts[1:]).strip()
            
            # Create member expression for left side (el.innerHTML)
            if '.' in left_part:
                obj_name, prop_name = left_part.split('.', 1)
                left_node = MockNode(
                    kind='member_expression',
                    text=left_part,
                    children=[
                        MockNode(kind='identifier', text=obj_name),
                        MockNode(kind='property_identifier', text=prop_name)
                    ]
                )
            else:
                left_node = MockNode(kind='identifier', text=left_part)
            
            # Create right side expression
            right_node = self._parse_expression(right_part)
            
            return MockNode(
                kind='assignment_expression',
                text=code,
                children=[left_node, MockNode(kind='assignment_operator', text='='), right_node]
            )
        
        return MockNode(kind='expression_statement', text=code)
    
    def _parse_call_expression(self, code: str) -> MockNode:
        """Parse function/method call expressions."""
        paren_pos = code.index('(')
        callee_part = code[:paren_pos].strip()
        args_part = code[paren_pos + 1:code.rindex(')')].strip()
        
        # Create callee node - handle method chains like params[:bio].html_safe() 
        callee_node = self._parse_callee(callee_part)
        
        # Create arguments
        arg_nodes = []
        if args_part:
            # Simple argument parsing
            args = []
            current_arg = ""
            paren_count = 0
            quote_char = None
            
            for char in args_part:
                if quote_char:
                    current_arg += char
                    if char == quote_char:
                        quote_char = None
                elif char in '"\'`':
                    quote_char = char
                    current_arg += char
                elif char == '(':
                    paren_count += 1
                    current_arg += char
                elif char == ')':
                    paren_count -= 1
                    current_arg += char
                elif char == ',' and paren_count == 0:
                    args.append(current_arg.strip())
                    current_arg = ""
                else:
                    current_arg += char
            
            if current_arg.strip():
                args.append(current_arg.strip())
            
            for arg in args:
                arg_nodes.append(self._parse_expression(arg))
        
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
        """Parse callee part of method/function call."""
        # Handle simple function calls like mark_safe
        if '.' not in callee_part and '[' not in callee_part:
            return MockNode(kind='identifier', text=callee_part)
        
        # Handle member expressions with array access like params[:bio].html_safe
        if '[' in callee_part and ']' in callee_part:
            # Split on the last dot to handle chaining
            if '.' in callee_part:
                parts = callee_part.rsplit('.', 1)
                base_part = parts[0]  # params[:bio] 
                method_part = parts[1]  # html_safe
                
                # Create member expression
                base_node = self._parse_complex_expression(base_part)
                return MockNode(
                    kind='member_expression',
                    text=callee_part,
                    children=[
                        base_node,
                        MockNode(kind='property_identifier', text=method_part)
                    ]
                )
            else:
                return self._parse_complex_expression(callee_part)
        
        # Handle simple member expressions like obj.method
        elif '.' in callee_part:
            obj_name, method_name = callee_part.split('.', 1)
            return MockNode(
                kind='member_expression',
                text=callee_part,
                children=[
                    MockNode(kind='identifier', text=obj_name),
                    MockNode(kind='property_identifier', text=method_name)
                ]
            )
        
        return MockNode(kind='identifier', text=callee_part)
        
    def _parse_complex_expression(self, expr: str) -> MockNode:
        """Parse complex expressions with array access."""
        if '[' in expr and ']' in expr:
            bracket_pos = expr.index('[')
            obj_part = expr[:bracket_pos]
            bracket_part = expr[bracket_pos:]
            
            return MockNode(
                kind='subscript_expression',
                text=expr,
                children=[
                    MockNode(kind='identifier', text=obj_part),
                    MockNode(kind='string_literal', text=bracket_part)
                ]
            )
        
        return MockNode(kind='identifier', text=expr)
        
        arguments_node = MockNode(
            kind='arguments',
            text=f"({args_part})",
            children=arg_nodes
        )
        
        return MockNode(
            kind='call_expression',
            text=code,
            children=[callee_node, arguments_node]
        )
    
    def _parse_jsx_attribute(self, code: str) -> MockNode:
        """Parse JSX attribute like dangerouslySetInnerHTML={{ __html: expr }}."""
        # Extract attribute name and value
        if '=' in code:
            attr_name = 'dangerouslySetInnerHTML'
            value_part = code.split('=', 1)[1].strip()
            
            # Parse JSX expression {{ __html: expr }}
            if value_part.startswith('{') and value_part.endswith('}'):
                inner_expr = value_part[1:-1].strip()
                if inner_expr.startswith('{') and inner_expr.endswith('}'):
                    # Object expression
                    obj_content = inner_expr[1:-1].strip()
                    
                    # Parse __html: expr
                    if '__html:' in obj_content:
                        html_expr_part = obj_content.split('__html:', 1)[1].strip()
                        html_expr = self._parse_expression(html_expr_part)
                        
                        # Create object property
                        html_property = MockNode(
                            kind='property',
                            text=f'__html: {html_expr_part}',
                            children=[
                                MockNode(kind='property_identifier', text='__html'),
                                html_expr
                            ]
                        )
                        
                        # Create object expression
                        obj_expr = MockNode(
                            kind='object_expression',
                            text=inner_expr,
                            children=[html_property]
                        )
                        
                        # Create JSX expression
                        jsx_expr = MockNode(
                            kind='jsx_expression',
                            text=value_part,
                            children=[obj_expr]
                        )
                        
                        return MockNode(
                            kind='jsx_attribute',
                            text=code,
                            children=[
                                MockNode(kind='property_identifier', text=attr_name),
                                jsx_expr
                            ]
                        )
        
        return MockNode(kind='jsx_attribute', text=code)
    
    def _parse_expression(self, expr: str) -> MockNode:
        """Parse various expression types."""
        expr = expr.strip()
        
        # String literals
        if expr.startswith('"') and expr.endswith('"'):
            return MockNode(kind='string_literal', text=expr)
        elif expr.startswith("'") and expr.endswith("'"):
            return MockNode(kind='string_literal', text=expr)
        elif expr.startswith('`') and expr.endswith('`'):
            # Template literal
            if '${' in expr:
                return MockNode(kind='template_literal', text=expr)
            else:
                return MockNode(kind='string_literal', text=expr)
        
        # Binary expressions (concatenation)
        elif '+' in expr and not expr.startswith('"') and not expr.startswith("'"):
            parts = expr.split('+', 1)
            left = self._parse_expression(parts[0].strip())
            right = self._parse_expression(parts[1].strip())
            return MockNode(
                kind='binary_expression',
                text=expr,
                children=[left, MockNode(kind='operator', text='+'), right]
            )
        
        # Function calls
        elif '(' in expr and ')' in expr:
            return self._parse_call_expression(expr)
        
        # Member expressions
        elif '.' in expr:
            return MockNode(kind='member_expression', text=expr)
        
        # Identifiers
        else:
            return MockNode(kind='identifier', text=expr)
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        meta = self.rule.meta
        assert meta.id == "sec.xss_unescaped_html"
        assert meta.category == "sec"
        assert meta.tier == 0
        assert meta.priority == "P0"
        assert "javascript" in meta.langs
        assert "typescript" in meta.langs
        assert "ruby" in meta.langs
        assert "python" in meta.langs
        assert meta.autofix_safety == "suggest-only"
    
    def test_positive_js_ts_innerHTML(self):
        """Test JavaScript/TypeScript innerHTML assignment detection."""
        code = 'el.innerHTML = "<b>" + userInput;'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "innerhtml" in findings[0].message.lower()  # Fixed: use lowercase
    
    def test_positive_js_ts_outerHTML(self):
        """Test JavaScript/TypeScript outerHTML assignment detection."""
        code = 'el.outerHTML = `${prefix}${html}`;'
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "outerhtml" in findings[0].message.lower()  # Fixed: use lowercase
    
    def test_positive_js_document_write(self):
        """Test document.write() detection."""
        code = 'document.write(userHtml);'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "HTML-writing API" in findings[0].message
    
    def test_positive_js_insertAdjacentHTML(self):
        """Test insertAdjacentHTML() detection."""
        code = 'el.insertAdjacentHTML("beforeend", htmlBlob);'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "HTML-writing API" in findings[0].message
    
    def test_positive_react_dangerouslySetInnerHTML(self):
        """Test React dangerouslySetInnerHTML detection."""
        code = 'dangerouslySetInnerHTML={{ __html: userInput }}'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dangerouslySetInnerHTML" in findings[0].message
    
    def test_positive_ruby_raw(self):
        """Test Ruby Rails raw() detection."""
        code = 'raw(params[:content])'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "raw" in findings[0].message.lower()
    
    def test_positive_ruby_html_safe(self):
        """Test Ruby html_safe detection."""
        code = 'params[:bio].html_safe'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "html_safe" in findings[0].message.lower()
    
    def test_positive_python_mark_safe(self):
        """Test Python Django mark_safe() detection."""
        code = 'mark_safe(user_supplied)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "mark_safe" in findings[0].message
    
    def test_negative_js_textContent(self):
        """Test that textContent assignment is safe."""
        code = 'el.textContent = userInput;'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_js_sanitized_innerHTML(self):
        """Test that sanitized innerHTML is safe."""
        code = 'el.innerHTML = DOMPurify.sanitize(userHtml);'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        # Should not trigger because it's sanitized
        # Note: This is a simplified test - real implementation might be more sophisticated
        assert len(findings) == 0
    
    def test_negative_react_escaped_jsx(self):
        """Test that regular JSX escapes content."""
        code = '<div>{userInput}</div>'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_literal_raw(self):
        """Test that raw() with literal content is safe."""
        code = 'raw("<p>static</p>")'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_python_literal_mark_safe(self):
        """Test that mark_safe() with literal content is safe."""
        code = 'mark_safe("<em>static</em>")'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_comprehensive_positive_coverage(self):
        """Test comprehensive coverage of positive cases across languages."""
        positive_cases = [
            # JavaScript/TypeScript
            ('javascript', 'el.innerHTML = "<b>" + userInput;', True),
            ('typescript', 'el.outerHTML = `${prefix}${html}`;', True),
            ('javascript', 'document.write(userHtml);', True),
            ('javascript', 'el.insertAdjacentHTML("beforeend", htmlBlob);', True),
            ('javascript', 'dangerouslySetInnerHTML={{ __html: userInput }}', True),
            
            # Ruby
            ('ruby', 'raw(params[:content])', True),
            ('ruby', 'user_bio.html_safe', True),
            
            # Python
            ('python', 'mark_safe(user_supplied)', True),
        ]
        
        total_violations = 0
        for lang, code, should_violate in positive_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            if should_violate:
                total_violations += len(findings)
                assert len(findings) > 0, f"Should detect violation in {lang}: {code}"
        
        # Should have detected violations in most positive cases
        assert total_violations >= 6, f"Expected at least 6 violations, got {total_violations}"
    
    def test_comprehensive_negative_coverage(self):
        """Test comprehensive coverage of safe cases across languages."""
        negative_cases = [
            # JavaScript/TypeScript - safe alternatives
            ('javascript', 'el.textContent = userInput;', False),
            ('javascript', 'el.innerHTML = DOMPurify.sanitize(userHtml);', False),
            ('javascript', 'el.innerHTML = "<p>static</p>";', False),
            ('javascript', '<div>{userInput}</div>', False),
            
            # Ruby - literal content
            ('ruby', 'raw("<p>static</p>")', False),
            ('ruby', '"<em>literal</em>".html_safe', False),
            
            # Python - literal content
            ('python', 'mark_safe("<em>static</em>")', False),
        ]
        
        for lang, code, should_violate in negative_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT detect violation in {lang}: {code}"
    
    def test_user_controlled_variable_names(self):
        """Test detection of user-controlled variable names."""
        user_controlled_vars = ['userInput', 'htmlContent', 'requestData', 'userHtml', 'params', 'bodyContent']
        
        for var in user_controlled_vars:
            code = f'el.innerHTML = {var};'
            ctx = self._create_context(code, "javascript")
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect {var} as user-controlled"
    
    def test_template_literal_interpolation(self):
        """Test detection of template literal interpolation."""
        code = 'el.innerHTML = `<div>${userContent}</div>`;'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "innerhtml" in findings[0].message.lower()  # Fixed: use lowercase
    
    def test_string_concatenation_detection(self):
        """Test detection of string concatenation patterns."""
        concat_patterns = [
            'el.innerHTML = "<p>" + userText + "</p>";',
            'el.outerHTML = prefix + dynamicHtml + suffix;',
            'document.write("<html>" + content);'
        ]
        
        for pattern in concat_patterns:
            ctx = self._create_context(pattern, "javascript")
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect concatenation in: {pattern}"
    
    def test_severity_and_span_reporting(self):
        """Test that findings have correct severity and span information."""
        code = 'el.innerHTML = userInput;'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.severity == "error"
        assert finding.rule == "sec.xss_unescaped_html"
        assert hasattr(finding, 'start_byte')
        assert hasattr(finding, 'end_byte')
        assert finding.start_byte < finding.end_byte

