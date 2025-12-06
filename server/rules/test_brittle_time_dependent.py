"""Detect tests using current time/timezone calls instead of controllable clocks."""

from typing import Iterator

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class TestBrittleTimeDependentRule:
    """Warn when tests read the current time/timezone directly."""
    
    meta = RuleMeta(
        id="test.brittle_time_dependent",
        category="test",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Warn when tests read the current time/timezone directly instead of using a controllable clock",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    requires = Requires(syntax=True)

    NOW_SIGS = {
        "python": {
            "datetime.datetime.now", "datetime.datetime.utcnow", "datetime.date.today", 
            "time.time", "time.monotonic", "datetime.now", "datetime.utcnow", "date.today"
        },
        "javascript": {"Date.now", "new Date", "Intl.DateTimeFormat", "performance.now"},
        "typescript": {"Date.now", "new Date", "Intl.DateTimeFormat", "performance.now"},
        "go": {"time.Now", "time.Since", "time.Until"},
        "java": {
            "java.time.Instant.now", "java.time.LocalDate.now", "java.time.LocalDateTime.now", 
            "java.util.Date.<init>", "System.currentTimeMillis", "System.nanoTime", "Clock.system"
        },
        "csharp": {
            "System.DateTime.Now", "System.DateTime.UtcNow", "System.DateTimeOffset.Now", 
            "System.DateTimeOffset.UtcNow", "System.Environment.TickCount64",
            "DateTime.Now", "DateTime.UtcNow", "DateTimeOffset.Now", "DateTimeOffset.UtcNow"
        },
        "cpp": {"std::chrono::system_clock::now", "std::chrono::steady_clock::now", "time", "gettimeofday"},
        "c": {"time", "gettimeofday", "clock_gettime"},
        "ruby": {"Time.now", "Time.new", "Date.today"},
        "rust": {"std::time::SystemTime::now", "std::time::Instant::now", "chrono::Utc::now", "chrono::Local::now"},
        "swift": {"Date.init", "Date()", "Date.now", "CFAbsoluteTimeGetCurrent", "Date"},
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for time-dependent calls in test contexts."""
        if not ctx.syntax:
            return
            
        lang = ctx.language
        if lang not in self.NOW_SIGS:
            return
            
        # Walk the syntax tree looking for calls and constructors
        for node in ctx.walk_nodes():
            if not self._is_call_or_constructor(node):
                continue
                
            if not self._in_test_context(node, lang):
                continue
                
            callee = self._get_callee_name(node)
            if self._is_now_like_call(lang, callee) or self._is_new_date_ctor(lang, node, callee):
                # Get the span of the callee part
                callee_node = getattr(node, "callee", node)
                start_pos, end_pos = ctx.node_span(callee_node)
                
                yield Finding(
                    rule=self.meta.id,
                    message="Time-dependent call in test; inject/mock a clock or use fixed timestamps (freeze time).",
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="info",
                )

    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        def walk(node):
            yield node
            children = getattr(node, "children", [])
            if children:
                for child in children:
                    yield from walk(child)
        
        root = getattr(tree, "root_node", tree)
        yield from walk(root)

    def _is_call_or_constructor(self, node) -> bool:
        """Check if node is a call or constructor."""
        node_type = getattr(node, "type", "")
        return node_type in {
            "call_expression", "method_invocation", "constructor_invocation",
            "function_call", "new_expression", "call", "invoke_expression",
            "member_access_expression"  # For C# property access like DateTime.Now
        }

    def _get_callee_name(self, node) -> str:
        """Extract the callee name from a call node."""
        # Try various attributes for callee
        callee_node = (
            getattr(node, "callee", None) or
            getattr(node, "function", None) or
            getattr(node, "name", None)
        )
        
        if not callee_node:
            return ""
            
        # Get text representation
        text = getattr(callee_node, "text", "")
        if text:
            return text.decode() if isinstance(text, bytes) else str(text)
            
        # Try to build qualified name from node structure
        return self._extract_qualified_name(callee_node)

    def _extract_qualified_name(self, node) -> str:
        """Extract qualified name like 'std::chrono::system_clock::now'."""
        if not node:
            return ""
            
        node_type = getattr(node, "type", "")
        
        # Handle member access patterns
        if node_type in {"member_expression", "field_expression", "attribute"}:
            obj = getattr(node, "object", None) or getattr(node, "left", None)
            prop = getattr(node, "property", None) or getattr(node, "right", None) or getattr(node, "field", None)
            
            obj_name = self._extract_qualified_name(obj) if obj else ""
            prop_name = self._extract_qualified_name(prop) if prop else ""
            
            if obj_name and prop_name:
                return f"{obj_name}.{prop_name}"
            return prop_name or obj_name
            
        # Handle scope resolution (C++)
        if node_type == "qualified_identifier":
            scope = getattr(node, "scope", None)
            name = getattr(node, "name", None)
            
            scope_name = self._extract_qualified_name(scope) if scope else ""
            name_text = self._extract_qualified_name(name) if name else ""
            
            if scope_name and name_text:
                return f"{scope_name}::{name_text}"
            return name_text or scope_name
            
        # Handle identifiers
        if node_type in {"identifier", "type_identifier"}:
            text = getattr(node, "text", "")
            if text:
                return text.decode() if isinstance(text, bytes) else str(text)
                
        return ""

    def _is_now_like_call(self, lang: str, callee: str) -> bool:
        """Check if the callee matches a time-reading signature."""
        if not callee:
            return False
            
        signatures = self.NOW_SIGS.get(lang, set())
        
        # Direct match or suffix match
        for sig in signatures:
            if callee == sig or callee.endswith(sig):
                return True
                
        return False

    def _is_new_date_ctor(self, lang: str, node, callee: str) -> bool:
        """Check for zero-argument Date constructors."""
        if lang not in {"javascript", "typescript", "swift", "java"}:
            return False
            
        if "Date" not in callee:
            return False
            
        # Check for zero arguments (current time)
        args = getattr(node, "arguments", None)
        if args is not None:
            # Count actual argument nodes that have content
            actual_args = []
            for arg in args:
                arg_type = getattr(arg, 'type', '')
                arg_text = getattr(arg, 'text', b'')
                if isinstance(arg_text, bytes):
                    arg_text = arg_text.decode()
                # Skip empty or whitespace-only arguments
                if arg_type and arg_text.strip():
                    actual_args.append(arg)
            return len(actual_args) == 0
            
        return False

    def _in_test_context(self, node, lang: str) -> bool:
        """Check if the node is within a test context."""
        for ancestor in self._ancestors(node):
            if self._is_test_node(ancestor, lang):
                return True
        return False

    def _is_test_node(self, node, lang: str) -> bool:
        """Check if a node represents a test function/method/case."""
        node_type = getattr(node, "type", "")
        text = getattr(node, "text", "")
        if isinstance(text, bytes):
            text = text.decode()
        text = str(text)
        
        # Get node name/identifier
        name_node = (
            getattr(node, "name", None) or 
            getattr(node, "identifier", None) or
            getattr(node, "declarator", None)
        )
        name = ""
        if name_node:
            name_text = getattr(name_node, "text", "")
            if isinstance(name_text, bytes):
                name_text = name_text.decode()
            name = str(name_text).lower()
        
        # Check decorators/annotations/attributes
        decorators = []
        for attr_name in ["decorators", "annotations", "attributes"]:
            attr_list = getattr(node, attr_name, [])
            if attr_list:
                for decorator in attr_list:
                    dec_text = getattr(decorator, "text", "")
                    if isinstance(dec_text, bytes):
                        dec_text = dec_text.decode()
                    decorators.append(str(dec_text))
        decorator_text = " ".join(decorators)
        
        # Language-specific test detection
        if lang == "python":
            return (name.startswith("test_") or 
                   "@pytest.mark." in decorator_text or
                   "@test" in decorator_text.lower())
                   
        elif lang in {"javascript", "typescript"}:
            return any(pattern in text for pattern in ["it(", "test(", "describe("])
            
        elif lang == "go":
            return name.startswith("test") and node_type in {"function_declaration", "method_declaration"}
            
        elif lang == "java":
            return ("@Test" in decorator_text or 
                   "@org.junit.jupiter.api.Test" in decorator_text or
                   "@org.junit.Test" in decorator_text)
                   
        elif lang == "csharp":
            return any(attr in decorator_text for attr in ["[Fact]", "[Theory]", "[Test]"])
            
        elif lang in {"c", "cpp"}:
            return any(pattern in text for pattern in ["TEST(", "TEST_F(", "TEST_P("])
            
        elif lang == "ruby":
            return any(pattern in text for pattern in ["it ", "specify(", "test "])
            
        elif lang == "rust":
            return "#[test]" in text
            
        elif lang == "swift":
            return ("XCTestCase" in text or "func test" in text) and name.startswith("test")
            
        return False

    def _ancestors(self, node):
        """Iterate through all ancestor nodes."""
        current = node
        while current:
            yield current
            current = getattr(current, "parent", None)


# Register the rule
_rule = TestBrittleTimeDependentRule()
RULES = [_rule]


