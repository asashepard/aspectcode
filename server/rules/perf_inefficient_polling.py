"""
perf.inefficient_polling rule: Detect tight polling loops with fixed sleeps.

Detects polling loops that repeatedly check conditions with fixed sleep/delay calls,
which can waste CPU or be inefficient. Suggests event-driven alternatives or 
exponential backoff with bounded retries.

Examples of problematic patterns:
- while not ready(): time.sleep(0.1)
- for(;;) { if (ready()) break; await new Promise(r => setTimeout(r, 100)); }
- while(!ready()) { Thread.sleep(100); }

Suggests alternatives:
- Event-driven waits (condition variables, signals, promises)
- Bounded retries with exponential backoff and timeouts
- Async/await patterns with proper wait utilities
"""

from typing import Iterator
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext


class PerfInefficientPollingRule:
    """Detects inefficient polling loops with fixed sleep delays."""
    
    meta = RuleMeta(
        id="perf.inefficient_polling",
        category="perf",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detect tight polling loops with fixed sleeps",
        langs=["python", "javascript", "java", "csharp", "go"],
    )
    
    requires = Requires(syntax=True)
    
    # Sleep/delay function signatures by language
    SLEEP_SIGS = {
        "python": {"time.sleep", "sleep"},
        "javascript": {"setTimeout"},  # used in ad-hoc polling with loops/recursion
        "java": {"Thread.sleep"},
        "csharp": {"System.Threading.Thread.Sleep", "Thread.Sleep", "Task.Delay"},
        "go": {"time.Sleep"},
    }
    
    def visit(self, ctx) -> Iterator[Finding]:
        """Visit file and detect inefficient polling loops."""
        if not hasattr(ctx, 'syntax') or not ctx.syntax:
            return
        
        lang = ctx.language
        for loop in self._walk_nodes(ctx.syntax):
            # Only check loop constructs
            if not self._is_loop(loop):
                continue
            
            sleep_call = self._sleep_call_in(loop, lang, ctx)
            if not sleep_call:
                continue
            
            # Skip if it looks like an event-driven pattern
            if self._looks_event_driven(loop, lang, ctx):
                continue
            
            # Report the sleep call as inefficient polling
            start_pos, end_pos = ctx.node_span(sleep_call)
            yield Finding(
                rule=self.meta.id,
                message="Polling loop with fixed sleep detected; prefer event/condition waits or retries with exponential backoff and a max timeout.",
                file=ctx.file_path,
                start_byte=start_pos,
                end_byte=end_pos,
                severity="info",
            )
    
    def _is_loop(self, node) -> bool:
        """Check if node is a loop construct."""
        kind = getattr(node, 'kind', '')
        return kind in {
            'while_statement', 'for_statement', 'for_in_statement', 
            'for_of_statement', 'for_loop', 'while_loop'
        }
    
    def _sleep_call_in(self, loop, lang, ctx):
        """Find sleep/delay calls within the loop body."""
        if lang not in self.SLEEP_SIGS:
            return None
        
        sleep_signatures = self.SLEEP_SIGS[lang]
        
        # Walk all nodes in the loop to find function calls
        for node in self._walk_nodes_in_subtree(loop):
            if not self._is_function_call(node):
                continue
            
            callee_text = self._get_callee_text(node, ctx)
            if not callee_text:
                continue
            
            # Check if this call matches any sleep signature
            if any(self._matches_sleep_signature(callee_text, sig) for sig in sleep_signatures):
                # Check if it has a fixed duration argument
                if self._has_fixed_duration(node, ctx):
                    return node
        
        return None
    
    def _is_function_call(self, node) -> bool:
        """Check if node is a function call."""
        kind = getattr(node, 'kind', '')
        return kind in {
            'call_expression', 'method_call', 'function_call', 
            'call', 'invocation_expression'
        }
    
    def _get_callee_text(self, node, ctx) -> str:
        """Extract the function name/callee from a call node."""
        # Try different ways to get the callee
        callee = getattr(node, 'callee', None)
        if callee:
            return self._node_text(callee, ctx)
        
        function = getattr(node, 'function', None)
        if function:
            return self._node_text(function, ctx)
        
        name = getattr(node, 'name', None)
        if name:
            return self._node_text(name, ctx)
        
        return ""
    
    def _node_text(self, node, ctx) -> str:
        """Get text representation of a node."""
        try:
            # Try to get tokens and reconstruct text
            tokens = list(ctx.syntax.iter_tokens(node))
            if tokens:
                return ''.join(ctx.syntax.token_text(t) for t in tokens)
        except:
            pass
        
        # Fallback to node text if available
        text = getattr(node, 'text', '')
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='ignore')
        return str(text)
    
    def _matches_sleep_signature(self, callee_text: str, signature: str) -> bool:
        """Check if callee text matches a sleep function signature."""
        # Remove whitespace for comparison
        callee_clean = callee_text.replace(' ', '').replace('\n', '')
        
        # Exact match
        if callee_clean == signature:
            return True
        
        # Ends with the signature (for qualified names)
        if callee_clean.endswith('.' + signature) or callee_clean.endswith('::' + signature):
            return True
        
        # For partial matches like just "sleep" when signature is "time.sleep"
        if '.' in signature:
            short_name = signature.split('.')[-1]
            if callee_clean == short_name:
                return True
        
        return False
    
    def _has_fixed_duration(self, call_node, ctx) -> bool:
        """Check if the call has a fixed (non-dynamic) duration argument."""
        # Get arguments from the call
        args = getattr(call_node, 'arguments', None)
        if not args:
            return True  # No args means default behavior, still consider it fixed
        
        # Get the first argument (usually the duration)
        if hasattr(args, 'children') and args.children:
            first_arg = args.children[0]
        elif hasattr(args, '__iter__'):
            try:
                first_arg = next(iter(args))
            except StopIteration:
                return True
        else:
            return True
        
        # Get the argument text
        arg_text = self._node_text(first_arg, ctx)
        if not arg_text:
            return True
        
        # Clean up the text
        arg_clean = arg_text.replace(' ', '').replace('\n', '')
        
        # Consider it fixed if it contains digits and no dynamic elements
        has_digits = any(ch.isdigit() for ch in arg_clean)
        
        # Dynamic patterns that indicate backoff/jitter
        dynamic_patterns = [
            'random', 'rand', 'nextint', 'math.random', 'retries', 'attempt',
            'backoff', 'jitter', '<<', 'math.pow'
        ]
        has_dynamic = any(pattern in arg_clean.lower() for pattern in dynamic_patterns)
        
        # Special case: Go time multiplication patterns like "100*time.Millisecond" are still fixed
        if '*time.' in arg_clean or '*time:' in arg_clean:
            has_dynamic = False
        
        # If it has digits and no dynamic elements, consider it fixed
        return has_digits and not has_dynamic
    
    def _looks_event_driven(self, loop, lang, ctx) -> bool:
        """Check if the loop uses event-driven patterns that should be allowed."""
        # Get the text content of the loop
        loop_text = self._node_text(loop, ctx).replace(' ', '').replace('\n', '').lower()
        
        # Patterns that indicate acceptable event-driven behavior
        allow_hints = [
            'condition.wait', 'awaitwaitfor', 'awaitscreen.findby', 'awaitility', 
            'semaphore', 'monitor.wait', 'autoresetevent', 'manualresetevent',
            'waithandle.wait', 'task.whenany', 'context.done()', 'select{',
            'await', 'promise', 'observable', 'eventhandler', 'callback'
        ]
        
        # Check if any event-driven patterns are present
        return any(hint in loop_text for hint in allow_hints)
    
    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        def walk(node):
            if node is not None:
                yield node
                children = getattr(node, 'children', [])
                for child in children:
                    yield from walk(child)
        
        root = getattr(tree, 'root_node', tree)
        yield from walk(root)
    
    def _walk_nodes_in_subtree(self, subtree_root):
        """Walk all nodes within a specific subtree."""
        def walk(node):
            if node is not None:
                yield node
                children = getattr(node, 'children', [])
                for child in children:
                    yield from walk(child)
        
        yield from walk(subtree_root)


# Export the rule for registration
RULES = [PerfInefficientPollingRule()]


