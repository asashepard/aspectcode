"""Rule to detect dynamic code execution on variable input (eval/exec/Function).

Detects potentially dangerous dynamic code execution where user-controlled or variable 
input is passed to eval-like functions across multiple languages:

- Python: eval(), exec(), builtins.eval(), builtins.exec()
- JavaScript: eval(), Function constructor
- Ruby: eval, Kernel.eval, Object.instance_eval, Module.class_eval, Module.module_eval

Only flags usage with variable input (not literal strings) to reduce false positives.
Recommends safer alternatives like JSON.parse, ast.literal_eval, or explicit dispatch.
"""

import re
from typing import Iterator, Set

from engine.types import RuleContext, Finding, RuleMeta, Requires, Rule


class SecEvalExecUsageRule:
    """Detect dynamic code execution on variable input."""
    
    meta = RuleMeta(
        id="sec.eval_exec_usage",
        category="sec",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects dynamic code execution on variable input (eval/Function/exec)",
        langs=["python", "javascript", "ruby"]
    )
    
    requires = Requires(syntax=True)
    
    # Dynamic code execution functions by language
    TARGETS = {
        "python": {
            "eval", "exec", "builtins.eval", "builtins.exec", "__builtins__.eval", "__builtins__.exec"
        },
        "javascript": {
            "eval", "Function"
        },
        "ruby": {
            "eval", "Kernel.eval", "Object.instance_eval", "Module.class_eval", "Module.module_eval",
            "instance_eval", "class_eval", "module_eval"
        }
    }
    
    # Safe alternative recommendations by language
    SUGGESTIONS = {
        "python": "Avoid `eval/exec`. Prefer safe parsers (e.g., `ast.literal_eval` for data) or explicit dispatch.",
        "javascript": "Avoid `eval/Function`. Prefer JSON.parse, structured cloning, or table-driven dispatch.",
        "ruby": "Avoid `eval` family. Prefer safe parsing (JSON.parse) or explicit method dispatch."
    }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for dynamic code execution on variable input."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Get language from adapter
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        for node in ctx.tree.walk():
            node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
            
            # Check for function/method calls and constructor calls
            if node_kind in ["call_expression", "function_call", "method_call", "call", "invocation_expression", "new_expression"]:
                if self._is_dynamic_exec_call(node, ctx, language):
                    if self._has_variable_input(node, ctx):
                        start_byte, end_byte = self._get_node_span(node)
                        callee_text = self._get_callee_text(node, ctx)
                        suggestion = self.SUGGESTIONS.get(language, "Avoid dynamic code execution.")
                        
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Dynamic code execution (`{callee_text}`) on variable input. {suggestion}",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="error"
                        )
    
    def _is_dynamic_exec_call(self, node, ctx: RuleContext, language: str) -> bool:
        """Check if this is a call to a dynamic code execution function."""
        callee_text = self._get_callee_text(node, ctx)
        if not callee_text:
            return False
        
        targets = self.TARGETS.get(language, set())
        
        # Direct function name match
        for target in targets:
            if callee_text == target:
                return True
            # Handle dotted names like builtins.eval, Kernel.eval
            if "." in target and callee_text.endswith(target):
                return True
            # Handle method calls like obj.instance_eval
            if callee_text.endswith(f".{target.split('.')[-1]}"):
                return True
        
        # Special case for JavaScript Function constructor
        if language == "javascript":
            node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
            if node_kind == "new_expression" and "Function" in callee_text:
                return True
        
        # Special case for Ruby metaprogramming methods
        if language == "ruby":
            ruby_meta_methods = ["instance_eval", "class_eval", "module_eval"]
            for method in ruby_meta_methods:
                if callee_text.endswith(f".{method}"):
                    return True
        
        return False
    
    def _has_variable_input(self, node, ctx: RuleContext) -> bool:
        """Check if the first argument is variable input (not a literal string)."""
        args = self._get_call_arguments(node)
        if not args:
            return False
        
        first_arg = args[0]
        return not self._is_literal_string(first_arg, ctx)
    
    def _is_literal_string(self, node, ctx: RuleContext) -> bool:
        """Check if a node represents a literal string."""
        if not node:
            return False
        
        node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        
        # String literals
        if node_kind in ["string_literal", "string", "template_string"]:
            node_text = self._get_node_text(node, ctx)
            # Check if it's a pure string literal (not interpolated)
            if node_text.startswith(('"', "'", "`")) and node_text.endswith(('"', "'", "`")):
                # Check for template literal interpolation
                if "${" in node_text or "#{" in node_text:
                    return False  # Interpolated templates are not safe literals
                return True
        
        # Concatenation of literals might be safe, but we'll be conservative
        # and treat it as variable input for security
        return False
    
    # Helper methods
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the text of the function/method being called."""
        # Find the callee node
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "member_expression", "field_expression", "attribute", "dotted_name"]:
                return self._get_node_text(child, ctx)
        
        # For constructor calls, look for the type being constructed
        if hasattr(node, 'children'):
            for child in node.children:
                child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
                if child_kind in ["type_identifier", "generic_name", "qualified_name"]:
                    return self._get_node_text(child, ctx)
        
        return ""
    
    def _get_call_arguments(self, node) -> list:
        """Extract arguments from a call expression."""
        args = []
        
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["arguments", "argument_list", "parameter_list"]:
                # Get individual argument nodes
                for arg_child in getattr(child, 'children', []):
                    arg_kind = getattr(arg_child, 'kind', '') or getattr(arg_child, 'type', '')
                    if arg_kind not in [',', '(', ')', 'comma']:
                        args.append(arg_child)
                break
        
        return args
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
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
        start_byte, end_byte = self._get_node_span(node)
        if hasattr(ctx, 'text') and ctx.text:
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
            end_byte = start_byte + 10
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [SecEvalExecUsageRule()]
RULES = [SecEvalExecUsageRule()]


