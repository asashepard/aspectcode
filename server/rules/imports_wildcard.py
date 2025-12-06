"""Rule: imports.wildcard

Detects wildcard imports (from X import *) in Python code.

Wildcard imports can pollute the namespace and make code harder to understand 
and maintain. They hide which specific symbols are being used and can lead
to naming conflicts and debugging difficulties.

Examples:
- from os import *           # BAD: pollutes namespace
- from collections import * # BAD: unclear which symbols used
- from mymodule import foo   # GOOD: explicit import
"""

from typing import Iterator

from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class ImportsWildcardRule:
    """Flag wildcard imports in Python code."""
    
    meta = RuleMeta(
        id="imports.wildcard",
        category="imports", 
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Wildcard import; use explicit names",
        langs=["python"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find wildcard imports in the file."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Walk the tree to find import_from_statement nodes with wildcards
        for node in self._iter_nodes(ctx.tree):
            if self._is_wildcard_import(node):
                module_name = self._get_module_name(node, ctx)
                start_byte, end_byte = self._get_node_span(node)
                
                yield Finding(
                    rule=self.meta.id,
                    message=f"Wildcard import from '{module_name}' pollutes namespace. Use explicit imports instead.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="warning",  # Following the spec
                    autofix=None  # suggest-only
                )
    
    def _iter_nodes(self, tree):
        """Iterate through all nodes in the tree."""
        def visit_node(node):
            if node is None:
                return
                
            yield node
            
            # Visit children recursively
            for child in getattr(node, 'children', []):
                yield from visit_node(child)
        
        # Start from root node
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        yield from visit_node(root_node)
    
    def _is_wildcard_import(self, node) -> bool:
        """Check if this node represents a wildcard import."""
        node_type = getattr(node, 'type', '') or getattr(node, 'kind', '')
        
        if node_type != 'import_from_statement':
            return False
        
        # Look for wildcard_import child node or '*' in the import
        for child in getattr(node, 'children', []):
            child_type = getattr(child, 'type', '') or getattr(child, 'kind', '')
            
            # Direct wildcard_import node
            if child_type == 'wildcard_import':
                return True
            
            # Check for '*' text in children (fallback)
            child_text = self._get_node_text(child)
            if child_text == '*':
                return True
            
            # Check import_list for '*' 
            if child_type == 'import_list':
                for grandchild in getattr(child, 'children', []):
                    grandchild_text = self._get_node_text(grandchild)
                    if grandchild_text == '*':
                        return True
        
        return False
    
    def _get_module_name(self, node, ctx: RuleContext) -> str:
        """Extract the module name from an import_from_statement."""
        for child in getattr(node, 'children', []):
            child_type = getattr(child, 'type', '') or getattr(child, 'kind', '')
            
            if child_type in ['dotted_name', 'identifier']:
                module_text = self._get_node_text(child, ctx)
                if module_text and not module_text.startswith('import'):
                    return module_text
        
        return "unknown"
    
    def _get_node_text(self, node, ctx: RuleContext = None) -> str:
        """Extract text from a node."""
        if not node:
            return ""
        
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Fallback: use span to extract from source
        if ctx and hasattr(ctx, 'text'):
            start_byte, end_byte = self._get_node_span(node)
            try:
                return ctx.text[start_byte:end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""
    
    def _get_node_span(self, node) -> tuple:
        """Get the start and end byte positions of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        # If no span info, try to estimate
        if start_byte == end_byte == 0:
            # Use a default span
            end_byte = start_byte + 20
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [ImportsWildcardRule()]


