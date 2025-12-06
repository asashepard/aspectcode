"""Rule to detect unescaped HTML injection vulnerabilities.

Detects potentially unsafe HTML injection where user-controlled content is rendered 
without proper escaping across multiple languages and frameworks:

- JavaScript/TypeScript: innerHTML, outerHTML, document.write, insertAdjacentHTML
- React: dangerouslySetInnerHTML with dynamic content
- Ruby: Rails raw(), html_safe with non-literal content
- Python: Django mark_safe() with non-literal content

Recommends using safer APIs (textContent, innerText) or proper sanitization.
"""

import re
from typing import Iterator

from engine.types import RuleContext, Finding, RuleMeta, Requires, Rule


class SecXssUnescapedHtmlRule(Rule):
    """Detect unescaped HTML injection vulnerabilities."""
    
    meta = RuleMeta(
        id="sec.xss_unescaped_html",
        category="sec",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects unescaped HTML injection where user-controlled content is rendered without escaping",
        langs=["javascript", "typescript", "ruby", "python"]
    )
    requires = Requires(syntax=True)
    
    # HTML sink properties for JavaScript/TypeScript
    JS_HTML_SINK_PROPS = {"innerHTML", "outerHTML"}
    
    # HTML sink method calls
    JS_HTML_SINK_CALLS = {"document.write", "insertAdjacentHTML"}
    
    # React JSX dangerous attributes
    JSX_HTML_ATTRS = {"dangerouslySetInnerHTML"}
    
    # Ruby Rails HTML helper methods
    RUBY_SINK_CALLS = {"raw", "html_safe"}
    
    # Python Django HTML helper methods
    PY_SINK_CALLS = {"mark_safe"}
    
    # Pattern to identify user-controlled variable names
    NAME_HINTS = re.compile(r"(html|raw|user|input|body|content|data|msg|comment|params|request|req)", re.I)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for unescaped HTML injection vulnerabilities."""
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
            
            # JavaScript/TypeScript: Property assignments to HTML sinks
            if language in ["javascript", "typescript"] and node_kind in ["assignment_expression", "assignment"]:
                findings = list(self._check_js_html_property_assignment(node, ctx))
                yield from findings
                
            # JavaScript/TypeScript: HTML sink method calls
            if language in ["javascript", "typescript"] and node_kind in ["call_expression", "function_call"]:
                findings = list(self._check_js_html_method_call(node, ctx))
                yield from findings
                
            # React JSX: dangerouslySetInnerHTML attribute
            if language in ["javascript", "typescript"] and node_kind in ["jsx_attribute", "jsx_opening_element"]:
                findings = list(self._check_react_dangerous_html(node, ctx))
                yield from findings
                
            # Ruby: raw() and html_safe method calls
            if language == "ruby" and node_kind in ["call", "method_call", "call_expression", "function_call"]:
                findings = list(self._check_ruby_html_helpers(node, ctx))
                yield from findings
                
            # Python: mark_safe() calls
            if language == "python" and node_kind in ["call", "call_expression", "function_call"]:
                findings = list(self._check_python_mark_safe(node, ctx))
                yield from findings
    
    def _check_js_html_property_assignment(self, node, ctx: RuleContext) -> Iterator[Finding]:
        """Check JavaScript/TypeScript property assignments to HTML sinks."""
        # Look for pattern: element.innerHTML = expression
        left_node = None
        right_node = None
        
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["member_expression", "property_access", "field_expression"]:
                left_node = child
            elif child_kind not in ["=", "assignment_operator"]:
                right_node = child
        
        if not left_node or not right_node:
            return
        
        # Check if left side is an HTML sink property
        if self._is_js_html_property(left_node, ctx):
            if self._rhs_looks_unescaped(right_node, ctx):
                start_byte, end_byte = self._get_node_span(left_node)
                yield Finding(
                    rule=self.meta.id,
                    message="Unescaped HTML assigned to innerHTML/outerHTML. Use textContent or sanitize explicitly (e.g., DOMPurify).",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    def _check_js_html_method_call(self, node, ctx: RuleContext) -> Iterator[Finding]:
        """Check JavaScript/TypeScript method calls to HTML sinks."""
        callee = self._get_callee_text(node, ctx)
        
        if any(sink in callee for sink in self.JS_HTML_SINK_CALLS):
            args = self._get_call_arguments(node)
            
            # Check the HTML content argument
            if callee.endswith("insertAdjacentHTML") and len(args) >= 2:
                # insertAdjacentHTML(position, html) - check second argument
                suspect_arg = args[1]
            elif args:
                # document.write(html) - check first argument
                suspect_arg = args[0]
            else:
                return
            
            if self._rhs_looks_unescaped(suspect_arg, ctx):
                callee_node = self._get_callee_node(node)
                start_byte, end_byte = self._get_node_span(callee_node or node)
                yield Finding(
                    rule=self.meta.id,
                    message="Unescaped HTML passed to HTML-writing API. Prefer safe text APIs or sanitize input.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    def _check_react_dangerous_html(self, node, ctx: RuleContext) -> Iterator[Finding]:
        """Check React dangerouslySetInnerHTML JSX attributes."""
        # Check if this is a dangerouslySetInnerHTML attribute
        attr_name = self._get_jsx_attribute_name(node)
        
        if attr_name == "dangerouslySetInnerHTML":
            # Extract the __html property value from the attribute
            html_expr = self._extract_jsx_html_expr(node)
            
            if html_expr and self._rhs_looks_unescaped(html_expr, ctx, liberal=True):
                start_byte, end_byte = self._get_node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message="dangerouslySetInnerHTML with non-literal content. Sanitize (e.g., DOMPurify) or avoid raw HTML.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    def _check_ruby_html_helpers(self, node, ctx: RuleContext) -> Iterator[Finding]:
        """Check Ruby Rails HTML helper methods."""
        callee = self._get_callee_text(node, ctx)
        
        if any(sink in callee for sink in self.RUBY_SINK_CALLS):
            args = self._get_call_arguments(node)
            
            # For html_safe, check if it's called on a variable (method call)
            if "html_safe" in callee and not args:
                # Check if the receiver looks dynamic (e.g., variable.html_safe)
                receiver = self._get_method_receiver(node, ctx)
                if receiver and self._rhs_looks_unescaped(receiver, ctx, liberal=True):
                    start_byte, end_byte = self._get_node_span(node)
                    yield Finding(
                        rule=self.meta.id,
                        message="Unescaped HTML render via raw/html_safe. Escape or sanitize before rendering.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="error"
                    )
            elif args and self._rhs_looks_unescaped(args[0], ctx, liberal=True):
                # For raw(content), check the argument
                callee_node = self._get_callee_node(node)
                start_byte, end_byte = self._get_node_span(callee_node or node)
                yield Finding(
                    rule=self.meta.id,
                    message="Unescaped HTML render via raw/html_safe. Escape or sanitize before rendering.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    def _check_python_mark_safe(self, node, ctx: RuleContext) -> Iterator[Finding]:
        """Check Python Django mark_safe() calls."""
        callee = self._get_callee_text(node, ctx)
        
        if "mark_safe" in callee:
            args = self._get_call_arguments(node)
            
            if args and self._rhs_looks_unescaped(args[0], ctx, liberal=True):
                callee_node = self._get_callee_node(node)
                start_byte, end_byte = self._get_node_span(callee_node or node)
                yield Finding(
                    rule=self.meta.id,
                    message="Unescaped HTML via mark_safe. Only pass vetted sanitized content.",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    # Helper methods
    
    def _is_js_html_property(self, node, ctx: RuleContext) -> bool:
        """Check if a member expression targets an HTML sink property."""
        # Look for property name in member expression
        prop_name = ""
        
        # First, specifically look for property_identifier (the property name in member expressions)
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind == "property_identifier":
                prop_name = self._get_node_text(child, ctx)
                break
        
        # If no property_identifier found, fallback to identifier
        if not prop_name:
            for child in getattr(node, 'children', []):
                child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
                if child_kind == "identifier":
                    text = self._get_node_text(child, ctx)
                    # Skip object names, look for property-like names
                    if text in self.JS_HTML_SINK_PROPS:
                        prop_name = text
                        break
        
        # Also check for direct property name from full text
        if not prop_name:
            full_text = self._get_node_text(node, ctx)
            if '.' in full_text:
                prop_name = full_text.split('.')[-1]
        
        return prop_name in self.JS_HTML_SINK_PROPS
    
    def _rhs_looks_unescaped(self, node, ctx: RuleContext, liberal: bool = False) -> bool:
        """Heuristic: treat as risky if not a simple static literal."""
        if not node:
            return False
        
        node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        node_text = self._get_node_text(node, ctx)
        
        # Safe if strict static string literal
        if node_kind in ["string_literal", "string", "template_string"]:
            # Check for template interpolation
            if "${" in node_text or "#{" in node_text:
                return True
            # Pure literal is safe
            if node_text.startswith(('"', "'", "`")) and node_text.endswith(('"', "'", "`")):
                return False
        
        # Dynamic string construction
        if node_kind in ["binary_expression", "comparison_operator"]:
            # Check if it's string concatenation
            operator = self._get_binary_operator(node)
            if operator == "+":
                return True
        
        # Template strings with interpolation
        if node_kind in ["template_literal", "template_string"] and "${" in node_text:
            return True
        
        # Identifiers/variables
        if node_kind in ["identifier", "name"]:
            name = node_text.strip()
            # Check for suspicious variable names
            if self.NAME_HINTS.search(name):
                return True
            # In liberal mode, treat variables as risky by default
            return liberal
        
        # Function calls (might return user content)
        if node_kind in ["call", "call_expression", "function_call", "method_call"]:
            return liberal
        
        # Member access (like req.params.content)
        if node_kind in ["member_expression", "field_expression", "attribute"]:
            member_text = node_text.lower()
            if any(hint in member_text for hint in ["params", "request", "body", "query", "input"]):
                return True
            return liberal
        
        # Object expressions (for React)
        if node_kind == "object_expression":
            # Look for __html property
            for child in getattr(node, 'children', []):
                if self._is_html_property(child, ctx):
                    value = self._get_property_value(child)
                    if value and self._rhs_looks_unescaped(value, ctx, liberal=True):
                        return True
            return False
        
        # Default to risky in liberal mode
        return liberal
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the text of the function/method being called."""
        # Find the callee node
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "member_expression", "field_expression", "attribute", "dotted_name"]:
                return self._get_node_text(child, ctx)
        
        return ""
    
    def _get_callee_node(self, node):
        """Get the callee node from a call expression."""
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "member_expression", "field_expression", "attribute", "dotted_name"]:
                return child
        return None
    
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
    
    def _get_jsx_attribute_name(self, node) -> str:
        """Get the name of a JSX attribute."""
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["property_identifier", "identifier"]:
                return self._get_node_text(child, {}).strip()
        
        # Check if this is the attribute node itself
        node_text = getattr(node, 'text', b'').decode() if hasattr(node, 'text') else ''
        if '=' in node_text:
            return node_text.split('=')[0].strip()
        
        return ""
    
    def _extract_jsx_html_expr(self, node):
        """Extract the __html expression from dangerouslySetInnerHTML={{ __html: expr }}."""
        # Look for JSX expression containing object with __html property
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["jsx_expression", "jsx_expression_container"]:
                # Look inside the JSX expression for object expression
                for expr_child in getattr(child, 'children', []):
                    expr_kind = getattr(expr_child, 'kind', '') or getattr(expr_child, 'type', '')
                    if expr_kind == "object_expression":
                        # Find __html property
                        return self._find_html_property_value(expr_child)
        
        return None
    
    def _find_html_property_value(self, obj_node):
        """Find the value of __html property in an object expression."""
        for child in getattr(obj_node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["property", "pair", "object_property"]:
                # Check if this is the __html property
                key = self._get_property_key(child)
                if key == "__html":
                    return self._get_property_value(child)
        
        return None
    
    def _get_property_key(self, prop_node) -> str:
        """Get the key of a property node."""
        for child in getattr(prop_node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "property_identifier", "string_literal", "string"]:
                text = self._get_node_text(child, {})
                # Remove quotes if it's a string literal
                if text.startswith(('"', "'")) and text.endswith(('"', "'")):
                    return text[1:-1]
                return text
        return ""
    
    def _get_property_value(self, prop_node):
        """Get the value node of a property."""
        # Skip the key and find the value
        found_key = False
        for child in getattr(prop_node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in [":", "=>"]:
                found_key = True
                continue
            if found_key and child_kind not in [":", "=>", ","]:
                return child
        
        # Alternative: look for second non-punctuation child
        non_punct_children = []
        for child in getattr(prop_node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind not in [":", "=>", ",", "(", ")", "[", "]", "{", "}"]:
                non_punct_children.append(child)
        
        if len(non_punct_children) >= 2:
            return non_punct_children[1]
        
        return None
    
    def _is_html_property(self, node, ctx: RuleContext) -> bool:
        """Check if a property node is the __html property."""
        key = self._get_property_key(node)
        return key == "__html"
    
    def _get_method_receiver(self, node, ctx: RuleContext):
        """Get the receiver of a method call (object before the dot)."""
        # For method calls like obj.method(), get the obj part
        node_text = self._get_node_text(node, ctx)
        if '.' in node_text:
            # Find the part before the last dot
            parts = node_text.split('.')
            if len(parts) >= 2:
                receiver_text = '.'.join(parts[:-1])
                # Create a simple node-like object for the receiver
                class SimpleNode:
                    def __init__(self, text):
                        self.text = text.encode() if isinstance(text, str) else text
                        self.start_byte = 0
                        self.end_byte = len(text)
                        # Determine kind based on the text pattern
                        if (text.startswith('"') and text.endswith('"')) or \
                           (text.startswith("'") and text.endswith("'")):
                            self.kind = 'string_literal'
                        elif text.startswith('[') and text.endswith(']'):
                            self.kind = 'array_literal'
                        else:
                            self.kind = 'identifier'
                
                return SimpleNode(receiver_text)
        
        return None
    
    def _get_binary_operator(self, node) -> str:
        """Get the operator from a binary expression."""
        for child in getattr(node, 'children', []):
            child_text = self._get_node_text(child, {})
            if child_text in ["+", "-", "*", "/", "&&", "||", "==", "!=", "<", ">", "<=", ">="]:
                return child_text
        return ""
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
        """Get the text content of a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode()
            return str(text)
        
        # Fallback: try to get text from context if we have byte positions
        if hasattr(ctx, 'text') and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            start = getattr(node, 'start_byte', 0)
            end = getattr(node, 'end_byte', start)
            return ctx.text[start:end]
        
        return ""
    
    def _get_node_span(self, node) -> tuple:
        """Get the byte span of a node for reporting."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte)
        return (start_byte, end_byte)


# Export rule for registration
RULES = [SecXssUnescapedHtmlRule()]


