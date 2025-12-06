"""
Rule: test.flaky_sleep

Warn when tests use fixed delays (sleep) to wait for conditions, which increases 
flakiness and runtime. Flag common sleep APIs in test bodies and suggest 
event/condition waits, retries with backoff, or fakes/mocks/timers.

Category: test
Severity: warn
Priority: P1
Languages: python,typescript,javascript,go,java,cpp,c,csharp,ruby,rust,swift
Autofix: suggest-only

Examples of flagged patterns:
- time.sleep(1) in Python test functions
- setTimeout() patterns used as sleep in JS/TS tests  
- Thread.sleep() in Java test methods
- std::this_thread::sleep_for() in C++ test functions

Examples of allowed patterns:
- Proper event/condition waits (waitFor, Eventually, etc.)
- Bounded polling loops with max timeouts
- Mock/fake timer usage (jest.useFakeTimers)
"""

from typing import Iterator

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class TestFlakySleepRule:
    """Detect sleep calls in test contexts that can cause flakiness."""
    
    meta = RuleMeta(
        id="test.flaky_sleep",
        category="test",
        tier=0,
        priority="P1", 
        autofix_safety="suggest-only",
        description="Warn when tests use fixed delays (sleep) to wait for conditions, which increases flakiness and runtime",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Sleep function signatures per language
    SLEEP_SIGS = {
        "python": {"time.sleep", "sleep"},
        "javascript": {"setTimeout"},  # heuristic: often used as sleep in tests
        "typescript": {"setTimeout"},
        "go": {"time.Sleep"},
        "java": {"Thread.sleep"},
        "csharp": {"Thread.Sleep", "Task.Delay"},  # warn if not awaited/Asserted; syntax-only → always warn
        "cpp": {"std::this_thread::sleep_for", "std::this_thread::sleep_until", "sleep", "usleep", "nanosleep"},
        "c": {"sleep", "usleep", "nanosleep"},
        "ruby": {"sleep"},
        "rust": {"std::thread::sleep"},
        "swift": {"Thread.sleep", "usleep"},
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and detect sleep calls in test contexts."""
        language = getattr(ctx.adapter, 'language_id', '')
        if language not in self.meta.langs:
            return
            
        if not ctx.tree:
            return
            
        # Walk through all nodes in the syntax tree
        for node in ctx.walk_nodes(ctx.tree):
            if not self._is_call_node(node):
                continue
            
            # Check if this is in a test context
            if not self._in_test_context(node, language):
                continue
                
            # Get the callee name
            callee = self._get_callee_name(node)
            if not callee:
                continue
            
            # Check if this is a sleep call or JS sleep pattern
            if (self._is_sleep_call(language, callee) or 
                self._looks_js_sleep_pattern(node, language)):
                
                start, end = self._get_node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message="Test uses sleep()—this makes tests slow and flaky. Use event waits or mock timers instead.",
                    file=ctx.file_path,
                    start_byte=start,
                    end_byte=end,
                    severity="warning"
                )

    def _walk_nodes(self, node):
        """Recursively walk all nodes in the syntax tree."""
        visited = set()  # Prevent infinite loops
        
        def walk_recursive(n):
            node_id = id(n)
            if node_id in visited:
                return
            visited.add(node_id)
            yield n
            
            # Walk children if they exist
            if hasattr(n, 'children') and n.children:
                for child in n.children:
                    yield from walk_recursive(child)
        
        if hasattr(node, 'root_node'):
            yield from walk_recursive(node.root_node)
        else:
            yield from walk_recursive(node)

    def _is_call_node(self, node) -> bool:
        """Check if node represents a function call."""
        if not hasattr(node, 'kind'):
            return False
        return node.kind in {
            "call_expression", "call", "invocation_expression", 
            "method_invocation", "function_call"
        }

    def _get_callee_name(self, node) -> str:
        """Extract the callee name from a call node."""
        # For mock nodes, try to get the full text first
        if hasattr(node, 'text'):
            text = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
            # Extract method/function name from the call text
            import re
            # Look for patterns like "Thread.sleep(", "std::this_thread::sleep_for(", etc.
            patterns = [
                r'([a-zA-Z_][a-zA-Z0-9_]*(?:\:\:[a-zA-Z_][a-zA-Z0-9_]*)*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\(',
                r'([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)*)\s*\(',
                r'([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        
        # Fallback: try to build name from children
        if not hasattr(node, 'children') or not node.children:
            return ""
        
        # For method calls like Thread.sleep, concatenate the parts
        parts = []
        for child in node.children:
            if hasattr(child, 'text'):
                child_text = child.text.decode('utf-8') if isinstance(child.text, bytes) else str(child.text)
                if child_text and not child_text.startswith('('):
                    parts.append(child_text)
        
        return '.'.join(parts) if parts else ""

    def _get_node_span(self, node) -> tuple:
        """Get the byte span of a node."""
        if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return node.start_byte, node.end_byte
        return 0, 0

    def _is_sleep_call(self, lang: str, callee: str) -> bool:
        """Check if the callee matches sleep patterns for the language."""
        sleep_sigs = self.SLEEP_SIGS.get(lang, set())
        return any(callee.endswith(sig) or callee == sig for sig in sleep_sigs)

    def _looks_js_sleep_pattern(self, call_node, lang: str) -> bool:
        """Check for JavaScript/TypeScript sleep patterns like 'await new Promise(r => setTimeout(r, N))'."""
        if lang not in {"javascript", "typescript"}:
            return False
        
        # Get the text representation of the call and its context
        text = ""
        if hasattr(call_node, 'text'):
            text = call_node.text.decode('utf-8') if isinstance(call_node.text, bytes) else str(call_node.text)
        
        # Look for the Promise setTimeout pattern
        text_normalized = text.replace(" ", "").replace("\n", "").replace("\t", "")
        return "newPromise" in text_normalized and "setTimeout" in text_normalized

    def _in_test_context(self, node, lang: str) -> bool:
        """Check if the node is within a test context using language-specific heuristics."""
        # Walk up the parent chain to find test context
        for parent_node in self._enclosing_chain(node):
            if self._is_test_node(parent_node, lang):
                return True
        return False

    def _enclosing_chain(self, node):
        """Generate the chain of enclosing nodes (parents) for the given node."""
        current = node
        while current:
            yield current
            current = getattr(current, 'parent', None)

    def _is_test_node(self, node, lang: str) -> bool:
        """Check if a node represents a test function/method/class."""
        if not hasattr(node, 'kind'):
            return False
        
        kind = node.kind
        
        # Get node text for analysis
        text = ""
        if hasattr(node, 'text'):
            text = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
        
        # Extract identifier/name if available
        name = self._extract_node_name(node)
        
        # Language-specific test detection
        if lang == "python":
            return (kind in {"function_definition", "async_function_definition"} and 
                    name.startswith("test_")) or \
                   (kind == "class_definition" and name.startswith("Test")) or \
                   "@pytest.mark." in text
        
        elif lang in {"javascript", "typescript"}:
            return ("it(" in text or "test(" in text or "describe(" in text) or \
                   kind == "function_declaration" and name.startswith("test")
        
        elif lang == "go":
            return kind == "function_declaration" and name.startswith("Test")
        
        elif lang == "java":
            return ("@Test" in text or "@org.junit" in text) or \
                   (kind == "method_declaration" and name.startswith("test"))
        
        elif lang == "csharp":
            return any(attr in text for attr in ["[Fact]", "[Theory]", "[Test]"]) or \
                   (kind == "method_declaration" and name.startswith("Test"))
        
        elif lang in {"c", "cpp"}:
            return "TEST(" in text or "TEST_F(" in text or "TEST_P(" in text
        
        elif lang == "ruby":
            return any(pattern in text for pattern in ["it(", "specify(", "test "]) or \
                   (kind == "method" and name.startswith("test_"))
        
        elif lang == "rust":
            return "#[test]" in text or \
                   (kind == "function_item" and name.startswith("test_"))
        
        elif lang == "swift":
            return ("XCTestCase" in text and name.startswith("test")) or \
                   (kind == "function_declaration" and name.startswith("test"))
        
        return False

    def _extract_node_name(self, node) -> str:
        """Extract the name/identifier from a node."""
        # Try common name/identifier child patterns
        if hasattr(node, 'children') and node.children:
            for child in node.children:
                if hasattr(child, 'kind') and child.kind in {"identifier", "name"}:
                    if hasattr(child, 'text'):
                        text = child.text
                        return text.decode('utf-8') if isinstance(text, bytes) else str(text)
        
        # Fallback: extract name from text using simple patterns
        if hasattr(node, 'text'):
            text = node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
            # Simple regex-like extraction for function/method names
            import re
            patterns = [
                r'def\s+(\w+)',  # Python
                r'function\s+(\w+)',  # JS/TS
                r'func\s+(\w+)',  # Go
                r'\w+\s+(\w+)\s*\(',  # Java/C#/C++
                r'fn\s+(\w+)',  # Rust
            ]
            for pattern in patterns:
                match = re.search(pattern, text)
                if match:
                    return match.group(1)
        
        return ""


# Create rule instance
_rule = TestFlakySleepRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    register_rule(_rule)
except ImportError:
    # Fallback for direct imports
    try:
        from engine.registry import register_rule
        register_rule(_rule)
    except ImportError:
        pass


