"""
Rule to detect Promise-returning calls that are not properly awaited or handled.

This rule flags calls that likely return a Promise but whose result is neither awaited,
then/catch-handled, nor returned, which can lead to lost errors and race conditions.
"""

from typing import Iterator, Dict, Any, Set, List, Optional
import re

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class ConcurrencyPromiseNotAwaitedRule(Rule):
    """Rule to detect Promise calls that are not properly awaited or handled."""
    
    meta = RuleMeta(
        id="concurrency.promise_not_awaited",
        description="Flags calls that likely return a Promise but are not awaited, then/catch-handled, or returned.",
        category="concurrency",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        langs=["javascript", "typescript"],
    )

    requires = Requires(syntax=True)

    # Known Promise-returning patterns
    PROMISEY_PREFIXES = (
        "fs.promises.", "fetch", "axios.", "Promise.", "db.", "http.", "https.", 
        "pg.", "mongo.", "redis.", "client.", "api.", "request.", "http.get", 
        "https.get", "util.promisify"
    )
    
    PROMISEY_NAME_HINTS = ("Async", "Thenable", "Promise")

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and analyze Promise-returning calls."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        if not ctx.tree:
            return

        # Walk through all nodes in the syntax tree
        for node in ctx.walk_nodes(ctx.tree):
            if not self._is_call_node(node):
                continue
            
            # Skip if already properly handled
            if (self._is_awaited(node) or self._is_then_chained(node, ctx) or 
                self._is_returned(node) or self._is_intentional_fire_and_forget(node, ctx)):
                continue
            
            # Check if this looks like a Promise-returning call
            if self._looks_promise_like(node, ctx):
                span = self._get_call_span(ctx, node)
                yield Finding(
                    file=ctx.file_path,
                    message="Promise not awaited/handled; use 'await', chain '.then/.catch', or return it.",
                    severity="warning",
                    span=span,
                    meta={
                        "rule_id": self.meta.id,
                        "issue_type": "promise_not_awaited",
                        "call_name": self._get_callee_text(node, ctx)
                    }
                )

    def _walk_nodes(self, tree):
        """Walk through all nodes in the syntax tree."""
        if not tree:
            return
        
        visited = set()  # Track visited nodes to prevent infinite loops
        
        def walk_recursive(node):
            # Prevent infinite loops by tracking visited nodes
            node_id = id(node)
            if node_id in visited:
                return
            visited.add(node_id)
            
            yield node
            if hasattr(node, 'children'):
                for child in node.children:
                    if child:
                        yield from walk_recursive(child)
        
        yield from walk_recursive(tree)

    def _is_call_node(self, node) -> bool:
        """Check if a node represents a function call."""
        if not hasattr(node, 'kind'):
            return False
        
        # Common call node types in JavaScript/TypeScript
        call_kinds = {
            "call_expression", "function_call", "method_call", 
            "member_call_expression", "new_expression", "call"
        }
        return node.type in call_kinds

    def _get_callee_text(self, call_node, ctx: RuleContext) -> str:
        """Extract the full callee name (e.g., 'fs.promises.readFile', 'fetch')."""
        if not call_node:
            return ""
        
        # Try to get the function/method being called
        callee = None
        if hasattr(call_node, 'function'):
            callee = call_node.function
        elif hasattr(call_node, 'callee'):
            callee = call_node.callee
        elif hasattr(call_node, 'name'):
            callee = call_node.name
        
        if not callee:
            return ""
        
        # Extract text from the callee
        call_text = self._get_node_text(ctx, callee)
        
        # Clean up the call name (remove parentheses and arguments)
        if call_text:
            call_text = call_text.split('(')[0].strip()
            return call_text
        
        return ""

    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
        
        try:
            if hasattr(node, 'text'):
                text = node.text
                # Handle bytes vs string issue
                if isinstance(text, bytes):
                    return text.decode('utf-8', errors='ignore')
                elif isinstance(text, str):
                    return text
                else:
                    return str(text)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return ctx.text[node.start_byte:node.end_byte]
            elif hasattr(node, 'value'):
                return str(node.value)
            else:
                return ""
        except:
            return ""

    def _looks_promise_like(self, call_node, ctx: RuleContext) -> bool:
        """Check if this call looks like it returns a Promise."""
        name = self._get_callee_text(call_node, ctx)
        if not name:
            return False
        
        # Check known Promise-returning prefixes
        if any(name.startswith(prefix) for prefix in self.PROMISEY_PREFIXES):
            return True
        
        # Check name hints (functions ending with Async, Promise, etc.)
        if any(name.endswith(hint) for hint in self.PROMISEY_NAME_HINTS):
            return True
        
        # Check for explicit Promise constructor
        node_text = self._get_node_text(ctx, call_node)
        if node_text and isinstance(node_text, str) and "new Promise(" in node_text:
            return True
        
        # Check for common async patterns
        async_patterns = ["fetch", "axios", "request", "get", "post", "put", "delete", "ajax"]
        if any(pattern in name.lower() for pattern in async_patterns):
            return True
        
        return False

    def _is_awaited(self, call_node) -> bool:
        """Check if this call is preceded by await."""
        # Walk up to find if there's an await expression
        current = call_node
        visited = set()  # Prevent infinite loops
        max_depth = 20  # Safety limit for parent chain walking
        depth = 0
        
        while hasattr(current, 'parent') and current.parent and depth < max_depth:
            parent = current.parent
            parent_id = id(parent)
            
            # Check for infinite loops
            if parent_id in visited:
                break
            visited.add(parent_id)
            depth += 1
            
            if hasattr(parent, 'type'):
                if parent.type == "await_expression":
                    return True
                # Check for await keyword in text (only if kind is await_expression)
                # Don't match random text that happens to start with "await"
            current = parent
        return False

    def _is_then_chained(self, call_node, ctx: RuleContext) -> bool:
        """Check if this call is chained with .then/.catch/.finally."""
        # Look at the parent to see if this is part of a method chain
        if not hasattr(call_node, 'parent'):
            return False
        
        parent = call_node.parent
        
        # Check if parent is a member expression (for chaining)
        if hasattr(parent, 'type') and parent.type == "member_expression":
            # Look for .then, .catch, .finally in the chain
            parent_text = self._get_node_text(ctx, parent)
            if any(method in parent_text for method in ['.then', '.catch', '.finally']):
                return True
        
        # Check if the call node is followed by method calls
        node_text = self._get_node_text(ctx, call_node)
        if any(method in node_text for method in ['.then(', '.catch(', '.finally(']):
            return True
        
        return False

    def _is_returned(self, call_node) -> bool:
        """Check if this call is being returned."""
        # Walk up to find if we're in a return statement
        current = call_node
        visited = set()  # Prevent infinite loops
        max_depth = 20  # Safety limit for parent chain walking
        depth = 0
        
        while hasattr(current, 'parent') and current.parent and depth < max_depth:
            parent = current.parent
            parent_id = id(parent)
            
            # Check for infinite loops
            if parent_id in visited:
                break
            visited.add(parent_id)
            depth += 1
            
            if hasattr(parent, 'type'):
                if parent.type in {"return_statement", "arrow_function", "arrow_expression"}:
                    return True
                # Check for arrow function body
                if parent.type == "arrow_function":
                    # Check if this is a direct expression body (not in braces)
                    parent_text = getattr(parent, 'text', '')
                    if '=>' in parent_text and '{' not in parent_text.split('=>')[1].strip()[:10]:
                        return True
            current = parent
        return False

    def _is_intentional_fire_and_forget(self, call_node, ctx: RuleContext) -> bool:
        """Check if this is intentionally ignored (void operator, assignment to _, etc.)."""
        # Check for void operator
        if hasattr(call_node, 'parent') and call_node.parent:
            parent = call_node.parent
            if hasattr(parent, 'type') and parent.type == "unary_expression":
                parent_text = self._get_node_text(ctx, parent)
                if parent_text.strip().startswith('void'):
                    return True
        
        # Check for assignment to underscore or similar ignore patterns
        current = call_node
        visited = set()  # Prevent infinite loops
        max_depth = 20  # Safety limit for parent chain walking
        depth = 0
        
        while hasattr(current, 'parent') and current.parent and depth < max_depth:
            parent = current.parent
            parent_id = id(parent)
            
            # Check for infinite loops
            if parent_id in visited:
                break
            visited.add(parent_id)
            depth += 1
            
            if hasattr(parent, 'type') and parent.type in ["assignment_expression", "assignment"]:
                parent_text = self._get_node_text(ctx, parent)
                # Look for patterns like _ = promise() or unused = promise()
                if any(pattern in parent_text for pattern in ['_ =', 'unused =', 'ignore =']):
                    return True
            current = parent
        
        return False

    def _get_call_span(self, ctx: RuleContext, node):
        """Get the span of a call node for reporting."""
        try:
            # Try to get the callee span specifically
            callee = None
            if hasattr(node, 'function'):
                callee = node.function
            elif hasattr(node, 'callee'):
                callee = node.callee
            
            if callee and hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(callee)
            elif hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(node)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return (node.start_byte, node.end_byte)
            else:
                return (0, 10)  # Safe fallback
        except:
            return (0, 10)  # Safe fallback


# Register the rule
rule = ConcurrencyPromiseNotAwaitedRule()
RULES = [rule]


