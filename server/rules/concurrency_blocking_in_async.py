"""
Rule to detect blocking/synchronous I/O inside async contexts.

This rule flags use of blocking calls in async functions that could stall the event loop,
and recommends async equivalents to maintain non-blocking behavior.
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


class ConcurrencyBlockingInAsyncRule(Rule):
    """Rule to detect blocking calls inside async contexts."""
    
    meta = RuleMeta(
        id="concurrency.blocking_in_async",
        description="Flags use of blocking/synchronous I/O inside async contexts to prevent event-loop stalls; recommend async equivalents.",
        category="concurrency",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        langs=["javascript", "typescript", "python"],
    )

    requires = Requires(syntax=True)

    # Heuristic blocklists for different languages
    JS_SYNC = {
        "fs.readFileSync", "fs.writeFileSync", "fs.appendFileSync", "fs.readdirSync", "fs.existsSync",
        "fs.mkdirSync", "fs.rmSync", "fs.rmdirSync", "fs.statSync", "fs.lstatSync", "fs.copyFileSync",
        "child_process.execSync", "child_process.spawnSync", "child_process.execFileSync",
        "crypto.randomBytes"  # when used without callback (sync variant)
    }
    
    PY_BLOCKING = {
        "time.sleep", "sleep",  # common imported alias
        "subprocess.run", "subprocess.call", "subprocess.check_call", "subprocess.check_output",
        "requests.get", "requests.post", "requests.put", "requests.delete", "requests.request",
        "urllib.request.urlopen", "open"  # plain open().read() in async fn is suspicious
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and analyze blocking calls in async contexts."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        if not ctx.tree:
            return

        lang = ctx.adapter.language_id
        
        # Walk through all nodes in the syntax tree
        for node in ctx.walk_nodes(ctx.tree.root_node):
            if not self._is_call_node(node):
                continue
            
            if lang in {"javascript", "typescript"}:
                if self._inside_async_js(node) and self._is_js_sync_call(node, ctx):
                    start, end = self._get_call_span(ctx, node)
                    yield Finding(
                        rule=self.meta.id,
                        file=ctx.file_path,
                        message="Calling a synchronous function inside an async function—this blocks the event loop.",
                        severity="warning",
                        start_byte=start,
                        end_byte=end,
                        meta={
                            "rule_id": self.meta.id,
                            "issue_type": "js_sync_in_async",
                            "call_name": self._get_call_name(node, ctx)
                        }
                    )
            elif lang == "python":
                if self._inside_async_py(node) and self._is_py_blocking_call(node, ctx):
                    start, end = self._get_call_span(ctx, node)
                    yield Finding(
                        rule=self.meta.id,
                        file=ctx.file_path,
                        message="Blocking call inside async function—use an async alternative or run in an executor.",
                        severity="warning",
                        start_byte=start,
                        end_byte=end,
                        meta={
                            "rule_id": self.meta.id,
                            "issue_type": "py_blocking_in_async",
                            "call_name": self._get_call_name(node, ctx)
                        }
                    )

    def _walk_nodes(self, tree):
        """Walk through all nodes in the syntax tree."""
        if not tree:
            return
        
        # Use a simple recursive approach to walk nodes
        def walk_recursive(node):
            yield node
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from walk_recursive(child)
        
        yield from walk_recursive(tree)

    def _is_call_node(self, node) -> bool:
        """Check if a node represents a function call."""
        # Common call node types across languages
        call_kinds = {
            "call_expression", "function_call", "method_call", 
            "member_call_expression", "call", "invoke"
        }
        node_type = self._get_node_type(node)
        return node_type is not None and node_type in call_kinds

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

    def _inside_async_js(self, node) -> bool:
        """Check if a node is inside an async JavaScript/TypeScript function."""
        # Walk up the tree to find the containing function
        current = node
        while hasattr(current, 'parent') and current.parent:
            current = current.parent
            current_type = self._get_node_type(current)
            if current_type:
                # Look for async function declarations
                if current_type in {"function_declaration", "arrow_function", "method_definition"}:
                    # Check if it has async modifier
                    if hasattr(current, 'text'):
                        text = current.text
                        # Handle bytes from tree-sitter
                        if isinstance(text, bytes):
                            text = text.decode('utf-8', errors='ignore')
                        if text and 'async' in text and text.strip().startswith('async'):
                            return True
                    # Check for async keyword in children
                    if hasattr(current, 'children'):
                        for child in current.children:
                            child_type = self._get_node_type(child)
                            child_text = getattr(child, 'text', None)
                            if isinstance(child_text, bytes):
                                child_text = child_text.decode('utf-8', errors='ignore')
                            if child_type == "async" or child_text == "async":
                                return True
                    return False
        return False

    def _inside_async_py(self, node) -> bool:
        """Check if a node is inside an async Python function."""
        # Walk up the tree to find the containing function
        current = node
        while hasattr(current, 'parent') and current.parent:
            current = current.parent
            current_type = self._get_node_type(current)
            if current_type:
                # Look for async function definitions
                if current_type in {"function_definition", "async_function_definition"}:
                    if current_type == "async_function_definition":
                        return True
                    # Check if it's an async def
                    if hasattr(current, 'text'):
                        text = current.text
                        # Handle bytes from tree-sitter
                        if isinstance(text, bytes):
                            text = text.decode('utf-8', errors='ignore')
                        if text and text.strip().startswith('async def'):
                            return True
                    return False
        return False

    def _is_js_sync_call(self, node, ctx: RuleContext) -> bool:
        """Check if this is a blocking JavaScript/TypeScript call."""
        call_name = self._get_call_name(node, ctx)
        if not call_name:
            return False
        
        # Check against known sync patterns
        return any(call_name.endswith(sync_call) for sync_call in self.JS_SYNC)

    def _is_py_blocking_call(self, node, ctx: RuleContext) -> bool:
        """Check if this is a blocking Python call."""
        call_name = self._get_call_name(node, ctx)
        if not call_name:
            return False
        
        # Exclude async-friendly functions/libraries
        # These are async frameworks that provide non-blocking alternatives
        if (call_name.startswith('asyncio.') or 
            call_name.startswith('aiofiles.') or
            call_name.startswith('aiohttp.') or
            call_name.startswith('trio.') or       # trio.sleep is async
            call_name.startswith('anyio.') or      # anyio.sleep is async
            call_name.startswith('curio.') or      # curio.sleep is async
            'async' in call_name.lower()):
            return False
        
        # Check against known blocking patterns
        return any(call_name.endswith(blocking_call) for blocking_call in self.PY_BLOCKING)

    def _get_call_name(self, node, ctx: RuleContext) -> str:
        """Extract the full call name (e.g., 'fs.readFileSync', 'time.sleep')."""
        if not node:
            return ""
        
        # Try to get the function/method being called
        callee = None
        if hasattr(node, 'function'):
            callee = node.function
        elif hasattr(node, 'callee'):
            callee = node.callee
        elif hasattr(node, 'name'):
            callee = node.name
        elif hasattr(node, 'children') and len(node.children) > 0:
            # For tree-sitter Python: call node has [function, arguments] as children
            callee = node.children[0]
        
        if not callee:
            return ""
        
        # Extract text from the callee
        call_text = self._get_node_text(ctx, callee)
        
        # Clean up the call name
        if call_text:
            # Remove parentheses and arguments
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
                # Handle bytes from tree-sitter
                if isinstance(text, bytes):
                    return text.decode('utf-8', errors='ignore')
                return text
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return ctx.text[node.start_byte:node.end_byte]
            elif hasattr(node, 'value'):
                return str(node.value)
            else:
                return ""
        except:
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
rule = ConcurrencyBlockingInAsyncRule()
RULES = [rule]


