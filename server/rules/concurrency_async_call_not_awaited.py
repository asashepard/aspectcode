"""
Rule: concurrency.async_call_not_awaited

Detects calls to async/coroutine-returning functions whose results are not awaited,
returned, or intentionally handled (fire-and-forget). Suggests using 'await', 
returning the task/coroutine, or using a scheduling API.

Category: concurrency
Severity: warn
Priority: P0
Languages: python, csharp
Autofix: suggest-only
"""

from typing import Iterator
from engine.types import RuleContext, Finding
from engine.types import Rule, RuleMeta, Requires


class ConcurrencyAsyncCallNotAwaitedRule(Rule):
    """Detect async calls that are not awaited, returned, or intentionally scheduled."""
    
    meta = RuleMeta(
        id="concurrency.async_call_not_awaited",
        category="concurrency", 
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects calls to async/coroutine-returning functions whose results are not awaited, returned, or intentionally handled.",
        langs=["python", "csharp"]
    )
    
    requires = Requires(syntax=True)
    
    # Heuristic async indicators
    PY_ASYNC_SCHEDULERS = {
        "asyncio.create_task", "asyncio.ensure_future", "asyncio.gather", 
        "asyncio.run", "asyncio.wait", "asyncio.wait_for"
    }
    CS_TASK_AGGREGATORS = {"Task.WhenAll", "Task.WhenAny", "Task.Run"}
    NAME_HINTS = ("Async",)  # Functions ending with Async
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and analyze async calls."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            
        if not ctx.tree:
            return
            
        # Walk through all nodes in the syntax tree
        for node in ctx.walk_nodes(ctx.tree.root_node):
            if not self._is_call_node(node):
                continue
                
            # Skip if properly handled (awaited, returned, or scheduled)
            if (self._is_awaited(node, ctx) or 
                self._is_returned(node) or 
                self._is_explicitly_scheduled(node, ctx)):
                continue
                
            # Check if this looks like an async call in a bare expression
            if (self._looks_async_like(node, ctx) and 
                self._is_bare_expression_statement(node)):
                start, end = self._get_call_span(ctx, node)
                yield Finding(
                    rule=self.meta.id,
                    file=ctx.file_path,
                    message="Async call result not awaited/handled; use 'await', return the task/coroutine, or schedule intentionally.",
                    severity="warning",
                    start_byte=start,
                    end_byte=end,
                    meta={
                        "rule_id": self.meta.id,
                        "issue_type": "async_not_awaited",
                        "call_name": self._callee_text(node, ctx)
                    }
                )

    def _build_parent_map(self, ctx: RuleContext) -> dict:
        """Build a mapping from child nodes to parent nodes."""
        parent_map = {}
        
        def build_map(node, parent=None):
            if node:
                parent_map[id(node)] = parent
                children = getattr(node, 'children', [])
                # Handle mock objects that have children as Mock instead of list
                if hasattr(children, '__iter__') and not isinstance(children, str):
                    try:
                        for child in children:
                            build_map(child, node)
                    except (TypeError, AttributeError):
                        # Skip if children is not iterable (e.g., Mock object)
                        pass
        
        root = getattr(ctx.tree, 'root_node', ctx.tree)
        build_map(root)
        return parent_map

    def _get_parent(self, node):
        """Get parent of a node using either parent map or .parent attribute (for mock tests)."""
        # If we have a parent map from visit(), use it
        if hasattr(self, 'parent_map'):
            return self.parent_map.get(id(node))
        # Fall back to .parent attribute for mock tests
        elif hasattr(node, 'parent'):
            return node.parent
        else:
            return None
    
    def _get_ancestors(self, node, max_depth=5):
        """Get ancestors of a node up to max_depth."""
        ancestors = []
        current = node
        depth = 0
        
        while depth < max_depth:
            parent = self._get_parent(current)
            if not parent:
                break
            ancestors.append(parent)
            current = parent
            depth += 1
            
        return ancestors
    
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
        
        yield from walk_recursive(node)
    
    def _is_call_node(self, node) -> bool:
        """Check if node represents a function call."""
        call_node_types = {
            "call_expression", "call", "invocation_expression", 
            "method_invocation", "function_call"
        }
        
        node_type = self._get_node_type(node)
        return node_type is not None and node_type in call_node_types

    def _get_node_type(self, node):
        """Helper to get node type, handling both .type (tree-sitter) and .kind (mock tests)."""
        # For Mock objects, check if attributes were explicitly set
        if hasattr(node, '_mock_name'):  # This is a Mock object
            # Check if .kind was explicitly set (not auto-created)
            if 'kind' in node.__dict__:
                return node.kind
            # Check if .type was explicitly set (not auto-created)  
            elif 'type' in node.__dict__:
                return node.type
            else:
                return None
        else:
            # Real tree-sitter node - check .type first (standard)
            if hasattr(node, 'type'):
                return node.type
            elif hasattr(node, 'kind'):
                return node.kind
            else:
                return None
    
    def _is_bare_expression_statement(self, call_node) -> bool:
        """Check if the call is a bare expression statement (not part of assignment, etc)."""
        current = call_node
        max_depth = 5
        depth = 0
        
        while hasattr(current, 'parent') and current.parent and depth < max_depth:
            parent = current.parent
            parent_type = self._get_node_type(parent)
            
            if parent_type:
                # Found expression statement - this is a bare call
                if parent_type in {"expression_statement", "expression_stmt"}:
                    return True
                # If we hit assignment, return, await, etc. - not bare
                if parent_type in {
                    "assignment_expression", "assignment", "return_statement",
                    "await_expression", "variable_declaration", "local_declaration"
                }:
                    return False
            current = parent
            depth += 1
        return False
    
    def _is_awaited(self, call_node, ctx: RuleContext) -> bool:
        """Check if this call is awaited."""
        max_depth = 5
        
        for parent in self._get_ancestors(call_node, max_depth):
            parent_type = self._get_node_type(parent)
            if parent_type:
                if parent_type in {"await_expression", "await"}:
                    return True
                # Only check text for await in Python, and only if not already a call_expression
                if (ctx.adapter.language_id == "python" and 
                    parent_type != "call_expression"):
                    parent_text = self._get_node_text(ctx, parent)
                    if (parent_text and isinstance(parent_text, str) and 
                        parent_text.strip().startswith('await ')):
                        return True
        return False
    
    def _is_returned(self, call_node) -> bool:
        """Check if this call is being returned."""
        max_depth = 5
        
        for parent in self._get_ancestors(call_node, max_depth):
            parent_type = self._get_node_type(parent)
            if parent_type and parent_type in {"return_statement", "return"}:
                return True
        return False
    
    def _callee_text(self, call_node, ctx: RuleContext) -> str:
        """Get the callee text/name from a call node."""
        # Try to get function/callee from call node
        callee = None
        if hasattr(call_node, 'function'):
            callee = call_node.function
        elif hasattr(call_node, 'callee'):
            callee = call_node.callee
        elif hasattr(call_node, 'expression'):
            callee = call_node.expression
            
        if callee:
            return self._get_node_text(ctx, callee)
        
        # Fallback to call node text
        call_text = self._get_node_text(ctx, call_node)
        if '(' in call_text:
            return call_text.split('(')[0].strip()
        return call_text
    
    def _is_explicitly_scheduled(self, call_node, ctx: RuleContext) -> bool:
        """Check if this call is explicitly scheduled/managed."""
        callee_name = self._callee_text(call_node, ctx)
        
        if ctx.adapter.language_id == "python":
            # Check if it's a known async scheduler
            for scheduler in self.PY_ASYNC_SCHEDULERS:
                if callee_name.endswith(scheduler.split('.')[-1]) or scheduler in callee_name:
                    return True
                    
            # Check if parent is asyncio.gather or similar
            max_depth = 3
            
            for parent in self._get_ancestors(call_node, max_depth):
                parent_type = self._get_node_type(parent)
                if parent_type and parent_type in {"call_expression", "call"}:
                    parent_callee = self._callee_text(parent, ctx)
                    if any(scheduler in parent_callee for scheduler in self.PY_ASYNC_SCHEDULERS):
                        return True
                
        elif ctx.adapter.language_id == "csharp":
            # Check for Task aggregators
            for aggregator in self.CS_TASK_AGGREGATORS:
                if aggregator in callee_name:
                    return True
            
            # Check for explicit discard assignment: _ = FooAsync();
            max_depth = 3
            
            for parent in self._get_ancestors(call_node, max_depth):
                parent_type = self._get_node_type(parent)
                if parent_type and parent_type in {"assignment_expression", "assignment"}:
                    # Check if left side is discard
                    if hasattr(parent, 'left'):
                        left_text = self._get_node_text(ctx, parent.left)
                        if left_text.strip() in {"_", "_discard"}:
                            return True
                
        return False
    
    def _looks_async_like(self, call_node, ctx: RuleContext) -> bool:
        """Check if this call looks like it returns an async/awaitable result."""
        callee_name = self._callee_text(call_node, ctx)
        
        if ctx.adapter.language_id == "python":
            # Common async patterns in Python
            name_lower = callee_name.lower()
            
            # Function names with async hints
            if (name_lower.endswith('_async') or 
                '.async_' in name_lower or 
                'asyncio.' in name_lower or
                name_lower.endswith('async')):
                return True
                
            # Common async library patterns
            async_patterns = [
                'aiohttp.', 'aiofiles.', 'asyncpg.', 'motor.',
                'aiomysql.', 'aioredis.', 'httpx.'
            ]
            if any(pattern in name_lower for pattern in async_patterns):
                return True
                
        elif ctx.adapter.language_id == "csharp":
            # C# async method conventions
            if any(callee_name.endswith(hint) for hint in self.NAME_HINTS):
                return True
                
            # Known async types/namespaces
            if (callee_name.startswith("Task.") or 
                callee_name.startswith("ValueTask.") or
                "TaskFactory" in callee_name):
                return True
                
        return False
    
    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
            
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, str):
                return text
            elif hasattr(text, 'decode'):
                return text.decode('utf-8', errors='ignore')
            # Handle Mock objects that return other Mocks
            elif hasattr(text, '__class__') and 'Mock' in str(text.__class__):
                return ""
                
        # Try to get span and extract from source
        try:
            if hasattr(ctx.adapter, 'node_span') and ctx.text:
                start, end = ctx.adapter.node_span(node)
                if start is not None and end is not None and start >= 0 and end <= len(ctx.text):
                    return ctx.text[start:end]
        except:
            pass
            
        return ""
    
    def _get_call_span(self, ctx: RuleContext, node):
        """Get the span of a call node for reporting."""
        try:
            # Try to get the callee span specifically
            callee = None
            if hasattr(node, 'function'):
                callee = node.function
            elif hasattr(node, 'callee'):
                callee = node.callee
            elif hasattr(node, 'expression'):
                callee = node.expression
            
            if callee and hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(callee)
            elif hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(node)
        except:
            pass
            
        # Fallback span
        return (0, 10)


# Register the rule
rule = ConcurrencyAsyncCallNotAwaitedRule()
RULES = [rule]


