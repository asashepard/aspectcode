"""
Static analysis rule to remove redundant semicolons that form empty statements.

This rule detects and removes standalone semicolons that create empty statements,
but preserves semicolons that are required (e.g., in for loop headers).
"""

import re
from typing import Iterator
from engine.types import RuleContext, Finding, Edit, RuleMeta, Requires


class StyleRedundantSemicolonsRule:
    """Rule to remove redundant semicolons (empty statements)."""
    
    meta = RuleMeta(
        id="style.redundant_semicolons",
        category="style", 
        tier=0,
        priority="P3",
        autofix_safety="safe",
        description="Remove redundant standalone semicolons that form empty statements (not in for-headers).",
        langs=["javascript", "typescript", "java", "csharp", "cpp", "c", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect redundant semicolons."""
        # Check if this language is supported
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        # Find semicolon nodes in the syntax tree
        def find_semicolon_nodes(node):
            """Recursively find semicolon nodes."""
            if node.type == ";" or (hasattr(node, 'text') and node.text == b';'):
                yield node
            
            for child in node.children:
                yield from find_semicolon_nodes(child)
        
        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return
        
        # Track context to avoid removing semicolons in for loop headers
        for_header_ranges = self._find_for_header_ranges(ctx.tree.root_node)
        
        # Find all semicolon nodes and check if they're redundant
        for semicolon_node in find_semicolon_nodes(ctx.tree.root_node):
            # Skip semicolons inside for loop headers
            if self._is_in_for_header(semicolon_node, for_header_ranges):
                continue
            
            # Check if this semicolon is redundant (forms an empty statement)
            if self._is_redundant_semicolon(semicolon_node, ctx):
                yield Finding(
                    rule=self.meta.id,
                    message="Redundant semicolon; remove empty statement.",
                    file=ctx.file_path,
                    start_byte=semicolon_node.start_byte,
                    end_byte=semicolon_node.end_byte,
                    severity="info",
                    autofix=[Edit(
                        start_byte=semicolon_node.start_byte,
                        end_byte=semicolon_node.end_byte,
                        replacement=""
                    )],
                    meta={
                        "semicolon_type": "redundant_empty_statement",
                        "context": self._get_semicolon_context(semicolon_node, ctx)
                    }
                )
    
    def _find_for_header_ranges(self, root_node):
        """Find byte ranges of for loop headers to preserve their semicolons."""
        ranges = []
        
        def find_for_statements(node):
            """Recursively find for statement nodes."""
            if node.type == "for_statement":
                # Look for the parentheses part of the for loop
                for child in node.children:
                    if child.type == "(" or (hasattr(child, 'text') and child.text == b'('):
                        # Find the matching closing parenthesis
                        paren_depth = 0
                        start_byte = child.start_byte
                        end_byte = child.end_byte
                        
                        # Simple heuristic: find the range from opening to closing paren
                        for sibling in node.children:
                            if sibling.start_byte >= child.start_byte:
                                if sibling.type == "(" or (hasattr(sibling, 'text') and sibling.text == b'('):
                                    paren_depth += 1
                                elif sibling.type == ")" or (hasattr(sibling, 'text') and sibling.text == b')'):
                                    paren_depth -= 1
                                    if paren_depth == 0:
                                        end_byte = sibling.end_byte
                                        break
                        
                        ranges.append((start_byte, end_byte))
                        break
            
            for child in node.children:
                find_for_statements(child)
        
        find_for_statements(root_node)
        return ranges
    
    def _is_in_for_header(self, semicolon_node, for_header_ranges):
        """Check if a semicolon is inside a for loop header."""
        semicolon_byte = semicolon_node.start_byte
        
        for start_byte, end_byte in for_header_ranges:
            if start_byte <= semicolon_byte <= end_byte:
                return True
        
        return False
    
    def _is_redundant_semicolon(self, semicolon_node, ctx):
        """
        Check if a semicolon is redundant (forms an empty statement).
        
        A semicolon is considered redundant if:
        1. It creates an empty statement (not terminating a real statement)
        2. It's a duplicate semicolon (like ;; or ;;; )
        3. It appears standalone on a line or after a block/statement
        """
        # Get the parent node to understand context
        parent = semicolon_node.parent
        
        # If the semicolon is the only child of an empty statement, it's redundant
        if parent and parent.type in ("empty_statement", "expression_statement"):
            # Check if this expression statement only contains the semicolon
            significant_children = [child for child in parent.children 
                                   if child.type not in ("comment", "whitespace")]
            if len(significant_children) == 1 and significant_children[0] == semicolon_node:
                return True
        
        # Check for duplicate semicolons by looking at surrounding text
        source_text = ctx.text
        # Ensure source_text is a string
        if isinstance(source_text, bytes):
            source_text = source_text.decode('utf-8', errors='ignore')
        
        if semicolon_node.start_byte > 0:
            # Look for preceding semicolon
            before_text = source_text[max(0, semicolon_node.start_byte - 10):semicolon_node.start_byte]
            # Remove whitespace and check if there's a semicolon
            before_clean = re.sub(r'\s', '', before_text)
            if before_clean.endswith(';'):
                return True  # Duplicate semicolon
        
        # Check if it's a standalone semicolon (on its own line or after a block)
        line_start = source_text.rfind('\n', 0, semicolon_node.start_byte) + 1
        line_end = source_text.find('\n', semicolon_node.end_byte)
        if line_end == -1:
            line_end = len(source_text)
        
        line_text = source_text[line_start:line_end]
        line_before_semicolon = line_text[:semicolon_node.start_byte - line_start]
        line_after_semicolon = line_text[semicolon_node.end_byte - line_start:]
        
        # If the line only contains whitespace before and after the semicolon, it's likely redundant
        if line_before_semicolon.strip() == '' and line_after_semicolon.strip() == '':
            return True
        
        # Conservative approach: only flag obvious cases
        return False
    
    def _get_semicolon_context(self, semicolon_node, ctx):
        """Get context information about the semicolon for debugging."""
        parent_type = semicolon_node.parent.type if semicolon_node.parent else "none"
        
        # Get surrounding text for context
        start = max(0, semicolon_node.start_byte - 20)
        end = min(len(ctx.text), semicolon_node.end_byte + 20)
        source_text = ctx.text
        if isinstance(source_text, bytes):
            source_text = source_text.decode('utf-8', errors='ignore')
        surrounding = source_text[start:end]
        
        return {
            "parent_type": parent_type,
            "surrounding_text": surrounding,
            "byte_position": semicolon_node.start_byte
        }


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(StyleRedundantSemicolonsRule())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


