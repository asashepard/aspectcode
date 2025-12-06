"""
Memory Buffer Overflow API Rule

Detects use of classic, non-bounds-checked C/C++ APIs that commonly cause buffer
overflows. Flags functions like gets, strcpy, strcat, sprintf, vsprintf, scanf
without width specifiers, and other unsafe APIs.

Rule ID: memory.buffer_overflow_api
Category: memory
Severity: error
Priority: P0
Languages: c, cpp
Autofix: suggest-only
"""

import re
from typing import Iterable, Optional, List

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryBufferOverflowApiRule(Rule):
    """Rule to detect unsafe C/C++ APIs that can cause buffer overflows."""
    
    meta = RuleMeta(
        id="memory.buffer_overflow_api",
        category="memory",
        tier=0,  # Syntax-only analysis
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects use of non-bounds-checked APIs that can cause buffer overflows",
        langs=["c", "cpp"]
    )
    requires = Requires(syntax=True)

    # Always-unsafe or generally non-bounded APIs
    BAD_CALLEES = {
        "gets", "strcpy", "wcscpy", "strcat", "wcscat",
        "sprintf", "vsprintf", "swprintf", "vswprintf",
        "getwd", "streadd", "strecpy", "strtrns"
    }
    
    # scanf-family functions that need width checking for %s/%c/%[ patterns
    SCANF_FAMILY = {
        "scanf", "sscanf", "fscanf", "vscanf", "vsscanf", 
        "vfscanf", "swscanf", "wscanf"
    }

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for unsafe API usage."""
        # Check language compatibility
        if not ctx.tree:
            return
# Get language ID
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            return
            
        for call_node in self._find_function_calls(ctx):
            callee = self._get_callee_name(ctx, call_node)
            if not callee:
                continue
                
            # Check for always-unsafe APIs
            if callee in self.BAD_CALLEES:
                callee_node = self._get_callee_node(call_node)
                start_pos = callee_node.start_point if callee_node else call_node.start_point
                end_pos = callee_node.end_point if callee_node else call_node.end_point
                
                yield Finding(
                    rule=self.meta.id,
                    message=f"Use of non-bounds-checked function '{callee}' can cause buffer overflow. Use a length-bounded alternative (e.g., fgets/snprintf/strlcpy/std::string).",
                    severity="error",
                    file="",
                    start_byte=callee_node.start_byte if callee_node else call_node.start_byte,
                    end_byte=callee_node.end_byte if callee_node else call_node.end_byte
                )
                continue
            
            # Check for unbounded scanf-family functions
            if callee in self.SCANF_FAMILY and self._is_scanf_unbounded(ctx, call_node):
                callee_node = self._get_callee_node(call_node)
                start_pos = callee_node.start_point if callee_node else call_node.start_point
                end_pos = callee_node.end_point if callee_node else call_node.end_point
                
                yield Finding(
                    rule=self.meta.id,
                    message="Unbounded scanf-style format (e.g., `%s` without width). Specify field widths or use safer parsing.",
                    severity="error",
                    file="",
                    start_byte=callee_node.start_byte if callee_node else call_node.start_byte,
                    end_byte=callee_node.end_byte if callee_node else call_node.end_byte
                )

    def _find_function_calls(self, ctx: RuleContext):
        """Find all function call nodes in the syntax tree."""
        def walk(node):
            if node.type == "call_expression":
                yield node
            for child in node.children:
                yield from walk(child)
        
        yield from walk(ctx.tree.root_node)

    def _get_callee_name(self, ctx: RuleContext, call_node) -> Optional[str]:
        """Extract the function name from a call expression."""
        # Get the function node (first child of call_expression)
        if not call_node.children:
            return None
            
        function_node = call_node.children[0]
        return self._get_node_text(ctx, function_node).strip()

    def _get_callee_node(self, call_node):
        """Get the callee node from a call expression."""
        if call_node.children:
            return call_node.children[0]
        return None

    def _is_scanf_unbounded(self, ctx: RuleContext, call_node) -> bool:
        """
        Check if a scanf-family call has unbounded format specifiers.
        Returns True if the format string contains %s, %c, or %[ without width.
        """
        args = self._get_call_arguments(call_node)
        if not args:
            return False
            
        # Get the first argument (format string)
        format_arg = args[0]
        format_text = self._get_node_text(ctx, format_arg)
        
        # Only check simple string literals
        if not (format_text.startswith('"') and format_text.endswith('"')):
            return False
            
        # Strip quotes to get the actual format string
        format_spec = format_text[1:-1]
        
        # Check for risky patterns: %s, %c, %[ without preceding width
        # Pattern explanation:
        # - %(?!\d)    : % not followed by a digit (no width)
        # - (?:\*?)    : optional * flag (for assignment suppression)
        # - [sc\[]     : s, c, or [ characters (risky format specifiers)
        risky_patterns = [
            r'%(?!\d)(?:\*?)[sc]',  # %s or %c without width
            r'%(?!\d)(?:\*?)\[',    # %[ without width
        ]
        
        for pattern in risky_patterns:
            if re.search(pattern, format_spec):
                return True
                
        return False

    def _get_call_arguments(self, call_node):
        """Get the argument list from a call expression."""
        if len(call_node.children) < 2:
            return []
            
        # Second child should be argument_list
        arg_list_node = call_node.children[1]
        if arg_list_node.type != "argument_list":
            return []
            
        # Extract individual arguments (skip parentheses and commas)
        arguments = []
        for child in arg_list_node.children:
            if child.type not in {"(", ")", ","}:
                arguments.append(child)
                
        return arguments

    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get the text content of a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return text
        
        # Fallback: get text from source using byte positions
        if ctx.raw_text and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.raw_text[node.start_byte:node.end_byte]
        
        return ""


# Register the rule for auto-discovery
rule = MemoryBufferOverflowApiRule()
RULES = [rule]


