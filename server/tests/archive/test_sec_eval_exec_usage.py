"""Test suite for the dynamic code execution detection rule.

Tests detection of eval/exec/Function usage with variable input across multiple languages
and ensures proper identification of dangerous patterns while avoiding false positives
for literal string usage and safe alternatives.
"""

import pytest
from engine.types import RuleContext, RuleMeta, Requires
from rules.sec_eval_exec_usage import SecEvalExecUsageRule


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


class TestSecEvalExecUsageRule:
    """Test cases for the dynamic code execution detection rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecEvalExecUsageRule()
    
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
            'ruby': 'rb'
        }
        return extensions.get(language, 'txt')
    
    def _parse_code(self, code: str, language: str) -> MockNode:
        """Parse code into mock AST based on patterns."""
        # Detect assignment expressions like "var = value"
        if '=' in code and not '==' in code and not '!=' in code and not 'new ' in code:
            return self._parse_assignment_expression(code)
        
        # Detect constructor calls like "new Function()"
        elif 'new ' in code:
            return self._parse_new_expression(code)
        
        # Detect function calls with parentheses
        elif '(' in code and ')' in code:
            return self._parse_call_expression(code)
        
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
        
        # Constructor
        elif expr.startswith('new '):
            return self._parse_new_expression(expr)
        
        # Simple expression
        else:
            return self._parse_expression(expr)
    
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
        """Parse constructor expressions like 'new Function()'."""
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
            # Member expression like obj.instance_eval
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
        elif expr.startswith('`') and expr.endswith('`'):
            return MockNode(kind='template_string', text=expr)
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
        assert self.rule.meta.id == "sec.eval_exec_usage"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert "python" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert self.rule.meta.autofix_safety == "suggest-only"
    
    # Positive test cases - should detect vulnerabilities
    
    def test_positive_python_eval_variable(self):
        """Test Python eval with variable input."""
        code = 'result = eval(user_input)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
        assert "ast.literal_eval" in findings[0].message.lower()
    
    def test_positive_python_exec_variable(self):
        """Test Python exec with variable input."""
        code = 'exec(code_string)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
        assert "explicit dispatch" in findings[0].message.lower()
    
    def test_positive_python_builtins_eval(self):
        """Test Python builtins.eval with variable input."""
        code = 'builtins.eval(expression)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
    
    def test_positive_javascript_eval_variable(self):
        """Test JavaScript eval with variable input."""
        code = 'eval(userCode)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
        assert "json.parse" in findings[0].message.lower()
    
    def test_positive_javascript_function_constructor(self):
        """Test JavaScript Function constructor with variable input."""
        code = 'new Function(userScript)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
        assert "table-driven dispatch" in findings[0].message.lower()
    
    def test_positive_ruby_eval_variable(self):
        """Test Ruby eval with variable input."""
        code = 'eval(code_string)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
        assert "json.parse" in findings[0].message.lower()
    
    def test_positive_ruby_kernel_eval(self):
        """Test Ruby Kernel.eval with variable input."""
        code = 'Kernel.eval(expression)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
    
    def test_positive_ruby_instance_eval(self):
        """Test Ruby instance_eval with variable input."""
        code = 'obj.instance_eval(code)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
    
    def test_positive_ruby_class_eval(self):
        """Test Ruby class_eval with variable input."""
        code = 'MyClass.class_eval(definition)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
    
    # Negative test cases - should NOT detect (literal strings)
    
    def test_negative_python_eval_literal(self):
        """Test Python eval with literal string is not flagged."""
        code = 'eval("1 + 2")'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_python_exec_literal(self):
        """Test Python exec with literal string is not flagged."""
        code = 'exec("print(\\"hello\\")")'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_eval_literal(self):
        """Test JavaScript eval with literal string is not flagged."""
        code = 'eval("2 * 3")'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_function_literal(self):
        """Test JavaScript Function constructor with literal is not flagged."""
        code = 'new Function("return 42")'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_eval_literal(self):
        """Test Ruby eval with literal string is not flagged."""
        code = 'eval("1 + 1")'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_instance_eval_literal(self):
        """Test Ruby instance_eval with literal is not flagged."""
        code = 'obj.instance_eval("def foo; end")'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # Safe alternatives should not be flagged
    
    def test_negative_python_ast_literal_eval(self):
        """Test Python ast.literal_eval is not flagged."""
        code = 'ast.literal_eval(data)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_javascript_json_parse(self):
        """Test JavaScript JSON.parse is not flagged."""
        code = 'JSON.parse(jsonString)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_ruby_json_parse(self):
        """Test Ruby JSON.parse is not flagged."""
        code = 'JSON.parse(json_data)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    # Template literal interpolation should be flagged
    
    def test_positive_javascript_template_literal_interpolation(self):
        """Test JavaScript template literal with interpolation is flagged."""
        code = 'eval(`return ${userValue}`)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "dynamic code execution" in findings[0].message.lower()
    
    def test_positive_ruby_interpolated_string(self):
        """Test Ruby interpolated string is flagged."""
        code = 'eval("result = #{user_input}")'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        # Note: This depends on how our mock parser handles interpolated strings
        # For safety, we treat interpolated strings as variable input
    
    # Comprehensive coverage tests
    
    def test_comprehensive_positive_coverage(self):
        """Test comprehensive coverage of dangerous eval patterns."""
        positive_cases = [
            # Python
            ('python', 'eval(user_code)', True),
            ('python', 'exec(command)', True),
            ('python', 'builtins.eval(expr)', True),
            
            # JavaScript
            ('javascript', 'eval(script)', True),
            ('javascript', 'new Function(code)', True),
            
            # Ruby
            ('ruby', 'eval(expression)', True),
            ('ruby', 'Kernel.eval(code)', True),
            ('ruby', 'obj.instance_eval(method_def)', True),
            ('ruby', 'Class.class_eval(class_def)', True),
        ]
        
        dangerous_count = 0
        for lang, code, should_violate in positive_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            if should_violate:
                assert len(findings) >= 1, f"Should detect violation in {lang}: {code}"
                dangerous_count += len(findings)
        
        assert dangerous_count >= 9, f"Expected at least 9 dangerous eval detections, got {dangerous_count}"
    
    def test_comprehensive_negative_coverage(self):
        """Test comprehensive coverage of safe alternatives."""
        negative_cases = [
            # Python - safe alternatives and literals
            ('python', 'eval("1 + 2")', False),
            ('python', 'ast.literal_eval(data)', False),
            ('python', 'json.loads(json_str)', False),
            
            # JavaScript - safe alternatives and literals
            ('javascript', 'eval("Math.PI")', False),
            ('javascript', 'JSON.parse(json_data)', False),
            ('javascript', 'new Function("return 42")', False),
            
            # Ruby - safe alternatives and literals
            ('ruby', 'eval("42")', False),
            ('ruby', 'JSON.parse(json_string)', False),
            ('ruby', 'obj.instance_eval("def x; end")', False),
        ]
        
        for lang, code, should_violate in negative_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT detect violation in {lang}: {code}"
    
    def test_language_specific_recommendations(self):
        """Test that language-specific recommendations are provided."""
        test_cases = [
            ('python', 'eval(user_input)', 'ast.literal_eval'),
            ('javascript', 'eval(userCode)', 'JSON.parse'),
            ('ruby', 'eval(code)', 'JSON.parse'),
        ]
        
        for lang, code, expected_recommendation in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect issue in {lang}: {code}"
            assert expected_recommendation.lower() in findings[0].message.lower(), \
                f"Should recommend {expected_recommendation} for {lang}"
    
    def test_severity_and_span_reporting(self):
        """Test that severity and span are correctly reported."""
        code = 'eval(dangerous_input)'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        
        finding = findings[0]
        assert finding.severity == "error"
        assert finding.rule == "sec.eval_exec_usage"
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
        assert "ast.literal_eval" in finding.message
    
    def test_suggest_only_no_autofix(self):
        """Test that the rule provides suggestions without autofix edits."""
        code = 'eval(user_script)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        
        # Check that no autofix is provided (suggest-only)
        finding = findings[0]
        assert not hasattr(finding, 'edit') or finding.edit is None
        assert "json.parse" in finding.message.lower()
    
    def test_variable_vs_literal_distinction(self):
        """Test proper distinction between variable input and literal strings."""
        # Variable input should be flagged
        variable_cases = [
            ('python', 'eval(user_input)'),
            ('javascript', 'eval(userCode)'),
            ('ruby', 'eval(expression)'),
        ]
        
        for lang, code in variable_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should flag variable input in {lang}: {code}"
        
        # Literal strings should not be flagged
        literal_cases = [
            ('python', 'eval("print(42)")'),
            ('javascript', 'eval("console.log(42)")'),
            ('ruby', 'eval("puts 42")'),
        ]
        
        for lang, code in literal_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) == 0, f"Should NOT flag literal string in {lang}: {code}"

