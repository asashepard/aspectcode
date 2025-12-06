"""
Rule: func.async_mismatch.await_in_sync (Python)

Flags await expressions used inside non-async functions, which is
a syntax error in Python.
"""

from typing import Iterator
try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit


class AsyncMismatchAwaitInSyncRule:
    """Flag await expressions in non-async functions."""
    
    meta = RuleMeta(
        id="func.async_mismatch.await_in_sync",
        category="func",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="await used inside non-async function",
        langs=["python"]
    )
    
    requires = Requires(
        raw_text=False,
        syntax=True,
        scopes=False,
        project_graph=False
    )
    
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find await expressions in non-async functions."""
        if not ctx.tree:
            return
            
        # Walk the tree to find function definitions and await expressions
        for node in self._walk_tree(ctx.tree.root_node):
            if node.type == "function_definition":
                yield from self._check_function_for_awaits(node, ctx)
    
    def _walk_tree(self, node):
        """Recursively walk the syntax tree."""
        yield node
        for child in getattr(node, 'children', []):
            yield from self._walk_tree(child)
    
    def _check_function_for_awaits(self, func_node, ctx: RuleContext):
        """Check a function definition for await expressions in non-async functions."""
        # Check if the function is async
        is_async = self._is_async_function(func_node, ctx)
        
        if is_async:
            return  # Await is valid in async functions
        
        # Get function name for better error messages
        func_name = self._get_function_name(func_node, ctx)
        
        # Find all await expressions within this function
        for await_node in self._find_awaits_in_function(func_node):
            yield self._create_finding_for_await(await_node, func_name, ctx)
    
    def _is_async_function(self, func_node, ctx: RuleContext) -> bool:
        """Check if a function is declared as async."""
        # Look for 'async' keyword before 'def'
        for child in getattr(func_node, 'children', []):
            if child.type == "async" or (hasattr(child, 'text') and 
                                       self._get_node_text(child, ctx).strip() == "async"):
                return True
        
        # Also check if the function node itself indicates async
        if hasattr(func_node, 'type') and 'async' in func_node.type:
            return True
            
        # Check preceding siblings for async keyword
        parent = getattr(func_node, 'parent', None)
        if parent:
            func_index = -1
            siblings = getattr(parent, 'children', [])
            for i, sibling in enumerate(siblings):
                if sibling == func_node:
                    func_index = i
                    break
            
            # Look for async keyword before the function
            if func_index > 0:
                prev_node = siblings[func_index - 1]
                if (hasattr(prev_node, 'text') and 
                    self._get_node_text(prev_node, ctx).strip() == "async"):
                    return True
        
        return False
    
    def _get_function_name(self, func_node, ctx: RuleContext) -> str:
        """Extract function name from function definition."""
        for child in getattr(func_node, 'children', []):
            if child.type == "identifier":
                return self._get_node_text(child, ctx)
        return "anonymous"
    
    def _find_awaits_in_function(self, func_node):
        """Find all await expressions within a function."""
        awaits = []
        
        def collect_awaits(node):
            if hasattr(node, 'type') and node.type == "await":
                awaits.append(node)
            # Also check for await as part of expressions
            elif hasattr(node, 'type') and isinstance(node.type, str) and "await" in node.type:
                awaits.append(node)
            
            for child in getattr(node, 'children', []):
                collect_awaits(child)
        
        collect_awaits(func_node)
        return awaits
    
    def _create_finding_for_await(self, await_node, func_name: str, ctx: RuleContext) -> Finding:
        """Create a finding for an await in a non-async function."""
        start_byte, end_byte = self._get_node_span(await_node)
        
        # Check if this looks like an await expression by examining text
        await_text = self._get_node_text(await_node, ctx)
        if not await_text.strip().startswith('await'):
            # Try to find the actual await token
            await_token = self._find_await_token(await_node, ctx)
            if await_token:
                start_byte, end_byte = self._get_node_span(await_token)
                await_text = self._get_node_text(await_token, ctx)
        
        finding = Finding(
            rule=self.meta.id,
            message=f"await used inside non-async function '{func_name}'",
            severity="warning",
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            autofix=None,  # suggest-only as specified
            meta={
                "function_name": func_name,
                "suggestion": f"Add 'async' keyword to function '{func_name}' or remove await",
                "await_text": await_text.strip()
            }
        )
        
        return finding
    
    def _find_await_token(self, node, ctx: RuleContext):
        """Find the actual await token within a node."""
        # Check if this node is the await token
        node_text = self._get_node_text(node, ctx)
        if node_text.strip() == "await":
            return node
        
        # Look in children
        for child in getattr(node, 'children', []):
            child_text = self._get_node_text(child, ctx)
            if child_text.strip() == "await":
                return child
            # Recursively search
            result = self._find_await_token(child, ctx)
            if result:
                return result
        
        return None
    
    def _get_node_text(self, node, ctx: RuleContext = None) -> str:
        """Extract text from a node."""
        if not node:
            return ""
        
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='replace')
            return str(text)
        
        # Fallback: use span and context
        if ctx and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.text[node.start_byte:node.end_byte]
        
        return ""
    
    def _get_node_span(self, node) -> tuple[int, int]:
        """Get the byte span of a node."""
        if not node:
            return 0, 0
            
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        # If no span info, try to estimate
        if start_byte == end_byte == 0:
            # Use a default span for await keyword
            end_byte = start_byte + 5  # "await" is 5 characters
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [AsyncMismatchAwaitInSyncRule()]


