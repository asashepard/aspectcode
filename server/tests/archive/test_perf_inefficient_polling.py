"""
Tests for perf.inefficient_polling rule.

Tests inefficient polling loop detection across multiple languages.
"""

import pytest
from rules.perf_inefficient_polling import PerfInefficientPollingRule


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


def create_polling_loop(language='python', sleep_call='time.sleep', sleep_arg='0.1', loop_kind='while_statement', condition='not ready()', extra_text=''):
    """Create a mock polling loop structure for testing."""
    
    # Create sleep call arguments
    arg_node = MockNode(kind='literal', text=sleep_arg, start_byte=30, end_byte=30 + len(sleep_arg))
    args_node = MockNode(kind='arguments', children=[arg_node], start_byte=29, end_byte=32)
    
    # Create sleep function call
    callee_node = MockNode(kind='identifier', text=sleep_call, start_byte=20, end_byte=20 + len(sleep_call))
    call_node = MockNode(
        kind='call_expression',
        callee=callee_node,
        arguments=args_node,
        text=f'{sleep_call}({sleep_arg})',
        start_byte=20,
        end_byte=35
    )
    callee_node.parent = call_node
    args_node.parent = call_node
    
    # Create condition node
    condition_node = MockNode(kind='expression', text=condition, start_byte=10, end_byte=10 + len(condition))
    
    # Create loop body with the call
    loop_body = MockNode(kind='block', children=[call_node], start_byte=15, end_byte=40)
    call_node.parent = loop_body
    
    # Create the loop
    loop_text = f"while {condition}: {sleep_call}({sleep_arg}){extra_text}"
    loop_node = MockNode(
        kind=loop_kind,
        children=[condition_node, loop_body],
        text=loop_text,
        start_byte=0,
        end_byte=len(loop_text)
    )
    condition_node.parent = loop_node
    loop_body.parent = loop_node
    
    return loop_node


def create_event_driven_loop(language='python', pattern='await'):
    """Create a mock event-driven loop that should not trigger warnings."""
    
    if pattern == 'await':
        loop_text = "while not ready(): await condition.wait(timeout=1.0)"
    elif pattern == 'select':
        loop_text = "for { select { case <-ch: return; default: }; time.Sleep(50*time.Millisecond) }"
    elif pattern == 'waitfor':
        loop_text = "while (!ready) { await waitFor(() => screen.getByText('ready')); }"
    else:
        loop_text = f"while condition: {pattern}"
    
    loop_node = MockNode(
        kind='while_statement',
        text=loop_text,
        start_byte=0,
        end_byte=len(loop_text)
    )
    
    return loop_node


class TestPerfInefficientPolling:
    """Test cases for inefficient polling detection."""
    
    def test_rule_metadata(self):
        """Test rule has correct metadata."""
        rule = PerfInefficientPollingRule()
        
        assert rule.meta.id == "perf.inefficient_polling"
        assert rule.meta.category == "perf"
        assert rule.meta.tier == 0
        assert rule.meta.priority == "P2"
        assert rule.meta.autofix_safety == "suggest-only"
        assert rule.requires.syntax == True
        
        expected_languages = {"python", "javascript", "java", "csharp", "go"}
        assert set(rule.meta.langs) == expected_languages
    
    def test_sleep_signatures(self):
        """Test sleep function signature detection."""
        rule = PerfInefficientPollingRule()
        
        # Test signature matching
        assert rule._matches_sleep_signature("time.sleep", "time.sleep") == True
        assert rule._matches_sleep_signature("sleep", "time.sleep") == True
        assert rule._matches_sleep_signature("obj.time.sleep", "time.sleep") == True
        assert rule._matches_sleep_signature("Thread.sleep", "Thread.sleep") == True
        assert rule._matches_sleep_signature("System.Threading.Thread.Sleep", "Thread.Sleep") == True
        assert rule._matches_sleep_signature("unrelated", "time.sleep") == False
    
    def test_fixed_duration_detection(self):
        """Test detection of fixed vs dynamic durations."""
        rule = PerfInefficientPollingRule()
        ctx = MockRuleContext()
        
        # Test with fixed numeric argument
        fixed_arg = MockNode(kind='literal', text='0.1')
        call_with_fixed = MockNode(kind='call_expression', arguments=MockNode(children=[fixed_arg]))
        assert rule._has_fixed_duration(call_with_fixed, ctx) == True
        
        # Test with dynamic argument
        dynamic_arg = MockNode(kind='expression', text='random.random()')
        call_with_dynamic = MockNode(kind='call_expression', arguments=MockNode(children=[dynamic_arg]))
        assert rule._has_fixed_duration(call_with_dynamic, ctx) == False
        
        # Test Go time constant (should be considered fixed)
        go_time_arg = MockNode(kind='expression', text='100*time.Millisecond')
        call_with_go_time = MockNode(kind='call_expression', arguments=MockNode(children=[go_time_arg]))
        assert rule._has_fixed_duration(call_with_go_time, ctx) == True
    
    def test_event_driven_detection(self):
        """Test detection of event-driven patterns."""
        rule = PerfInefficientPollingRule()
        ctx = MockRuleContext()
        
        # Test event-driven pattern
        event_loop = create_event_driven_loop('python', 'await')
        assert rule._looks_event_driven(event_loop, 'python', ctx) == True
        
        # Test regular polling loop
        polling_loop = create_polling_loop('python')
        assert rule._looks_event_driven(polling_loop, 'python', ctx) == False
    
    def test_positive_case_python(self):
        """Test positive case for Python polling."""
        rule = PerfInefficientPollingRule()
        
        # Create Python polling loop
        loop_node = create_polling_loop('python', 'time.sleep', '0.1')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Polling loop with fixed sleep detected" in findings[0].message
        assert "exponential backoff" in findings[0].message
        assert findings[0].severity == "info"
        assert findings[0].rule == "perf.inefficient_polling"
    
    def test_positive_case_java(self):
        """Test positive case for Java polling."""
        rule = PerfInefficientPollingRule()
        
        # Create Java polling loop
        loop_node = create_polling_loop('java', 'Thread.sleep', '100')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('java', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Polling loop with fixed sleep detected" in findings[0].message
    
    def test_positive_case_csharp(self):
        """Test positive case for C# polling."""
        rule = PerfInefficientPollingRule()
        
        # Create C# polling loop
        loop_node = create_polling_loop('csharp', 'Thread.Sleep', '50')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('csharp', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Polling loop with fixed sleep detected" in findings[0].message
    
    def test_positive_case_go(self):
        """Test positive case for Go polling."""
        rule = PerfInefficientPollingRule()
        
        # Create Go polling loop
        loop_node = create_polling_loop('go', 'time.Sleep', '100*time.Millisecond', 'for_statement')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('go', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Polling loop with fixed sleep detected" in findings[0].message
    
    def test_positive_case_javascript(self):
        """Test positive case for JavaScript polling."""
        rule = PerfInefficientPollingRule()
        
        # Create JavaScript polling loop with setTimeout
        loop_node = create_polling_loop('javascript', 'setTimeout', '100', 'for_statement')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('javascript', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 1
        assert "Polling loop with fixed sleep detected" in findings[0].message
    
    def test_negative_case_event_driven_python(self):
        """Test negative case for Python event-driven code."""
        rule = PerfInefficientPollingRule()
        
        # Create event-driven loop that should not trigger warnings
        loop_node = create_event_driven_loop('python', 'await')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_event_driven_go(self):
        """Test negative case for Go select statement."""
        rule = PerfInefficientPollingRule()
        
        # Create Go loop with select that should not trigger warnings
        loop_node = create_event_driven_loop('go', 'select')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('go', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_event_driven_javascript(self):
        """Test negative case for JavaScript waitFor pattern."""
        rule = PerfInefficientPollingRule()
        
        # Create JavaScript waitFor pattern that should not trigger warnings
        loop_node = create_event_driven_loop('javascript', 'waitfor')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('javascript', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_dynamic_sleep(self):
        """Test negative case for dynamic sleep durations."""
        rule = PerfInefficientPollingRule()
        
        # Create loop with dynamic sleep duration (exponential backoff)
        loop_node = create_polling_loop('python', 'time.sleep', 'random.random()', extra_text=' # backoff')
        root_node = MockNode(kind='source_file', children=[loop_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_negative_case_non_loop_sleep(self):
        """Test that sleep outside loops is not flagged."""
        rule = PerfInefficientPollingRule()
        
        # Create sleep call outside a loop
        arg_node = MockNode(kind='literal', text='1.0')
        args_node = MockNode(kind='arguments', children=[arg_node])
        callee_node = MockNode(kind='identifier', text='time.sleep')
        call_node = MockNode(kind='call_expression', callee=callee_node, arguments=args_node)
        
        root_node = MockNode(kind='source_file', children=[call_node])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        assert len(findings) == 0
    
    def test_multiple_languages_comprehensive(self):
        """Test detection across multiple languages in comprehensive scenarios."""
        rule = PerfInefficientPollingRule()
        
        test_cases = [
            ('python', 'time.sleep', '0.1'),
            ('java', 'Thread.sleep', '100'),
            ('csharp', 'System.Threading.Thread.Sleep', '50'),
            ('go', 'time.Sleep', '100*time.Millisecond'),
            ('javascript', 'setTimeout', '100'),
        ]
        
        total_findings = 0
        for lang, sleep_func, duration in test_cases:
            loop_node = create_polling_loop(lang, sleep_func, duration)
            root_node = MockNode(kind='source_file', children=[loop_node])
            ctx = MockRuleContext(lang, root_node)
            
            findings = list(rule.visit(ctx))
            assert len(findings) == 1, f"Expected 1 finding for {lang}, got {len(findings)}"
            total_findings += len(findings)
        
        assert total_findings == 5
    
    def test_edge_case_nested_loops(self):
        """Test polling detection in nested loops."""
        rule = PerfInefficientPollingRule()
        
        # Create inner polling loop
        inner_loop = create_polling_loop('python', 'time.sleep', '0.1')
        
        # Create outer loop containing the inner loop
        outer_loop = MockNode(
            kind='for_statement', 
            children=[inner_loop],
            text='for i in range(10): while not ready(): time.sleep(0.1)',
            start_byte=0,
            end_byte=50
        )
        inner_loop.parent = outer_loop
        
        root_node = MockNode(kind='source_file', children=[outer_loop])
        ctx = MockRuleContext('python', root_node)
        
        findings = list(rule.visit(ctx))
        # The rule walks through both the outer and inner loop, but should only
        # report the sleep call once per loop that contains it
        assert len(findings) >= 1  # Should find at least one polling pattern
    
    def test_function_call_detection(self):
        """Test function call detection helper methods."""
        rule = PerfInefficientPollingRule()
        ctx = MockRuleContext()
        
        # Test function call detection
        call_node = MockNode(kind='call_expression')
        assert rule._is_function_call(call_node) == True
        
        non_call_node = MockNode(kind='identifier')
        assert rule._is_function_call(non_call_node) == False
        
        # Test callee text extraction
        callee = MockNode(kind='identifier', text='time.sleep')
        call_with_callee = MockNode(kind='call_expression', callee=callee)
        callee_text = rule._get_callee_text(call_with_callee, ctx)
        assert 'sleep' in callee_text

