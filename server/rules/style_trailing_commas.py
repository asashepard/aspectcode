# server/rules/style_trailing_commas.py
try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority

DEFAULT_POLICY = "multiline-only"  # "always" | "never" | "multiline-only"

class RuleStyleTrailingCommas(Rule):
    meta = RuleMeta(
        id="style.trailing_commas",
        description="Enforce trailing comma policy on lists/objects/args (always/never/multiline-only).",
        category="style",
        tier=0,
        priority="P3",
        autofix_safety="suggest-only",
        langs=["python", "javascript", "typescript", "ruby"],
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext):
        """Visit the file and detect trailing comma violations."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        # Get policy from config, default to multiline-only
        config = ctx.config or {}
        policy = config.get("trailing_commas", DEFAULT_POLICY)
        
        # Validate policy
        if policy not in {"always", "never", "multiline-only"}:
            policy = DEFAULT_POLICY

        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return

        # Find container nodes (lists, objects, function parameters)
        for container in self._find_containers(ctx.tree.root_node):
            for finding in self._check_container(container, ctx, policy):
                yield finding

    def _find_containers(self, node):
        """Find nodes that represent containers with potential trailing commas."""
        container_types = {
            "list", "array", "object", "dictionary", "tuple", "set",
            "arguments", "parameters", "formal_parameters", "argument_list",
            "parameter_list", "array_literal", "object_literal", "list_literal"
        }
        
        if node.type in container_types:
            yield node
        
        for child in node.children:
            yield from self._find_containers(child)

    def _check_container(self, container, ctx, policy):
        """Check a container for trailing comma policy compliance."""
        if not container.children:
            return  # Empty container
            
        # Find the last meaningful child and the closing bracket
        last_child = None
        closing_bracket = None
        has_content = False
        
        for child in reversed(container.children):
            if self._is_closing_bracket(child):
                closing_bracket = child
            elif not self._is_whitespace_or_comment(child):
                if last_child is None:  # First non-whitespace from the end
                    last_child = child
                # If we find another non-whitespace node, we have content
                if not self._is_opening_bracket(child):
                    has_content = True
        
        if not last_child or not closing_bracket or not has_content:
            return  # Empty or malformed container
            
        # Check if this is a multiline container
        is_multiline = self._is_multiline_container(container, ctx)
        
        # Check if there's a trailing comma
        has_trailing_comma = (last_child.type == "," or 
                             (hasattr(last_child, 'text') and last_child.text == b','))
        
        # Determine if comma is needed/allowed based on policy
        need_comma = (policy == "always") or (policy == "multiline-only" and is_multiline)
        forbid_comma = (policy == "never") or (policy == "multiline-only" and not is_multiline)
        
        violation = False
        want = None  # "add" | "remove"
        
        if has_trailing_comma and forbid_comma:
            violation, want = True, "remove"
        elif (not has_trailing_comma) and need_comma:
            violation, want = True, "add"
        
        if violation:
            yield from self._report_violation(ctx, container, closing_bracket, last_child, want, policy)

    def _is_opening_bracket(self, node):
        """Check if node is an opening bracket."""
        return (node.type in ("(", "[", "{") or 
                (hasattr(node, 'text') and node.text in (b"(", b"[", b"{")))

    def _is_closing_bracket(self, node):
        """Check if node is a closing bracket."""
        return (node.type in (")", "]", "}") or 
                (hasattr(node, 'text') and node.text in (b")", b"]", b"}")))

    def _is_whitespace_or_comment(self, node):
        """Check if node is whitespace or comment."""
        whitespace_types = {"whitespace", "comment", "line_comment", "block_comment", "newline"}
        return node.type in whitespace_types

    def _is_multiline_container(self, container, ctx):
        """Check if container spans multiple lines."""
        file_bytes = ctx.text
        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode('utf-8')
            
        start_line = file_bytes.count(b'\n', 0, container.start_byte)
        end_line = file_bytes.count(b'\n', 0, container.end_byte)
        
        return end_line > start_line

    def _report_violation(self, ctx, container, closing_bracket, last_child, want, policy):
        """Report a trailing comma violation with suggestion."""
        file_bytes = ctx.text
        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode('utf-8')

        if want == "remove":
            # Create diff showing removal of trailing comma
            line_start = file_bytes.rfind(b"\n", 0, last_child.start_byte) + 1
            line_end = file_bytes.find(b"\n", last_child.end_byte)
            if line_end == -1:
                line_end = len(file_bytes)
                
            original_line = file_bytes[line_start:line_end].decode("utf-8", errors="ignore")
            
            # Calculate position within line
            pos_in_line = last_child.start_byte - line_start
            modified_line = original_line[:pos_in_line] + original_line[pos_in_line + 1:]
            
            diff = f"""--- a/file
+++ b/file
-{original_line}
+{modified_line}"""
            
            rationale = f"Trailing comma not allowed by policy '{policy}'. Remove it."
            
        else:  # want == "add"
            # Create diff showing addition of trailing comma
            insertion_point = closing_bracket.start_byte
            
            line_start = file_bytes.rfind(b"\n", 0, insertion_point) + 1
            line_end = file_bytes.find(b"\n", insertion_point)
            if line_end == -1:
                line_end = len(file_bytes)
                
            original_line = file_bytes[line_start:line_end].decode("utf-8", errors="ignore")
            
            # Calculate position within line
            pos_in_line = insertion_point - line_start
            modified_line = original_line[:pos_in_line] + "," + original_line[pos_in_line:]
            
            diff = f"""--- a/file
+++ b/file
-{original_line}
+{modified_line}"""
            
            rationale = f"Trailing comma required by policy '{policy}'. Add it."

        # Create suggestion
        # For suggest-only rules, we don't provide autofix but include rationale in meta
        yield Finding(
            rule=self.meta.id,
            message=f"Inconsistent trailing comma usage (policy: {policy}).",
            file=ctx.file_path,
            start_byte=closing_bracket.start_byte,
            end_byte=closing_bracket.end_byte,
            severity="info",
            meta={
                "policy": policy,
                "action": want,
                "diff": diff,
                "rationale": rationale
            }
        )


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(RuleStyleTrailingCommas())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


