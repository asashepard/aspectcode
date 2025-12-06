"""
Rule to detect too-short identifiers for locals and parameters.

This rule analyzes variable bindings and their usage patterns to suggest
clearer names for identifiers that are too short to be descriptive.
"""

from typing import Iterator, Dict, Any, Tuple, Optional, Set
import re

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
    from engine.scopes import ScopeGraph, Symbol, Scope
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
    from engine.scopes import ScopeGraph, Symbol, Scope


DEFAULT_MIN_LEN = 3
DEFAULT_ALLOWED = {"i", "j", "k", "_", "__"}
LANG_STYLE = {
    # Used when fabricating a suggested name
    "python": "snake",
    # Most others prefer lowerCamel for locals/params
}


class RuleNamingTooShortIdentifier(Rule):
    """Rule to suggest clearer names for too-short local variables and parameters."""
    
    meta = RuleMeta(
        id="naming.too_short_identifier",
        description="Suggest clearer names for too-short local variables and parameters.",
        category="naming",
        tier=1,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"],
    )

    requires = Requires(syntax=True, scopes=True, raw_text=True)

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect too-short identifiers."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        config = ctx.config or {}
        min_len = int(config.get("min_identifier_length", DEFAULT_MIN_LEN))
        allowed = set(config.get("short_ident_whitelist", list(DEFAULT_ALLOWED)))

        # Collect parameters from function definitions directly 
        for param in self._find_function_parameters(ctx):
            name = param["name"]
            if len(name) >= min_len or name in allowed:
                continue
                
            suggestion = self._suggest_name(ctx, name, "param", 0)
            diff, rationale = self._make_diff(ctx, param, suggestion, "param", min_len)

            yield Finding(
                rule=self.meta.id,
                message=f"Identifier '{name}' is too short for a param; consider renaming to a clearer name.",
                file=ctx.file_path,
                start_byte=param["start_byte"],
                end_byte=param["end_byte"],
                severity="info",
                meta={
                    "kind": "param",
                    "original_name": name,
                    "suggested_name": suggestion,
                    "min_length": min_len,
                    "diff": diff,
                    "rationale": rationale
                }
            )

        # Also check local variables from scope analysis if available
        if ctx.scopes:
            for symbol in ctx.scopes.iter_symbols():
                if symbol.kind != "local":
                    continue
                    
                name = symbol.name
                if len(name) >= min_len or name in allowed:
                    continue

                # Check reference count for locals
                ref_count = self._count_refs(ctx, symbol)
                if ref_count <= 1:  # Skip single-use locals
                    continue

                # Don't flag exported/public API symbols
                if self._looks_exported(ctx, symbol):
                    continue

                suggestion = self._suggest_name(ctx, name, "local", symbol.scope_id)
                diff, rationale = self._make_diff_for_symbol(ctx, symbol, suggestion, "local", min_len)

                yield Finding(
                    rule=self.meta.id,
                    message=f"Identifier '{name}' is too short for a local; consider renaming to a clearer name.",
                    file=ctx.file_path,
                    start_byte=symbol.start_byte,
                    end_byte=symbol.end_byte,
                    severity="info",
                    meta={
                        "kind": "local",
                        "original_name": name,
                        "suggested_name": suggestion,
                        "min_length": min_len,
                        "diff": diff,
                        "rationale": rationale
                    }
                )

    def _find_function_parameters(self, ctx: RuleContext):
        """
        Find function parameters directly from the syntax tree.
        Returns dicts with keys: name, start_byte, end_byte
        """
        results = []
        
        def visit_node(node):
            if hasattr(node, 'type'):
                # Look for function definitions
                if node.type == 'function_definition':
                    # Find the parameters node
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'parameters':
                            # Extract parameter names from the parameters node
                            results.extend(self._extract_param_names(child))
                            break
                
                # Also handle lambda functions
                elif node.type == 'lambda':
                    # Lambda parameters come before the colon
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'lambda_parameters':
                            results.extend(self._extract_param_names(child))
                            break
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    visit_node(child)
        
        # Start from root
        tree = ctx.tree
        root_node = tree.root_node if hasattr(tree, 'root_node') else tree
        visit_node(root_node)
        
        return results

    def _extract_param_names(self, params_node):
        """Extract parameter names from a parameters or lambda_parameters node."""
        params = []
        
        def visit_param_node(node):
            if hasattr(node, 'type'):
                # Regular parameter (just an identifier)
                if node.type == 'identifier':
                    name = node.text.decode('utf-8')
                    # Skip 'self' and 'cls' which are conventional
                    if name not in ('self', 'cls'):
                        params.append({
                            "name": name,
                            "start_byte": node.start_byte,
                            "end_byte": node.end_byte
                        })
                
                # Default parameter (identifier = default_value)
                elif node.type == 'default_parameter':
                    # First child should be the identifier
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            name = child.text.decode('utf-8')
                            if name not in ('self', 'cls'):
                                params.append({
                                    "name": name,
                                    "start_byte": child.start_byte,
                                    "end_byte": child.end_byte
                                })
                            break
                
                # Typed parameter (identifier: type)
                elif node.type == 'typed_parameter':
                    # First child should be the identifier
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            name = child.text.decode('utf-8')
                            if name not in ('self', 'cls'):
                                params.append({
                                    "name": name,
                                    "start_byte": child.start_byte,
                                    "end_byte": child.end_byte
                                })
                            break
                
                # Typed default parameter (identifier: type = default)
                elif node.type == 'typed_default_parameter':
                    # First child should be the identifier
                    for child in node.children:
                        if hasattr(child, 'type') and child.type == 'identifier':
                            name = child.text.decode('utf-8')
                            if name not in ('self', 'cls'):
                                params.append({
                                    "name": name,
                                    "start_byte": child.start_byte,
                                    "end_byte": child.end_byte
                                })
                            break
            
            # Visit children for nested parameters
            if hasattr(node, 'children'):
                for child in node.children:
                    visit_param_node(child)
        
        visit_param_node(params_node)
        return params

    def _decls_of_interest(self, ctx: RuleContext):
        """
        DEPRECATED: Use _find_function_parameters instead.
        Yield dicts with keys: name, symbol, kind ('param'|'local'), scope_id
        Use scope graph to find function/method parameters and local variable declarations.
        """
        results = []
        
        if not ctx.scopes:
            return results
        
        # Iterate through all symbols in the scope graph
        for symbol in ctx.scopes.iter_symbols():
            # Only interested in parameters and local variables
            if symbol.kind not in ("param", "local", "variable"):
                continue
                
            # Classify as parameter or local variable
            kind = "param" if symbol.kind == "param" else "local"
            
            # Skip if no name
            if not symbol.name:
                continue
                
            results.append({
                "name": symbol.name,
                "symbol": symbol,
                "kind": kind,
                "scope_id": symbol.scope_id
            })
            
        return results

    def _count_refs(self, ctx: RuleContext, symbol: Symbol) -> int:
        """Count references to a symbol across all scopes."""
        ref_count = 0
        for ref in ctx.scopes.iter_refs():
            if ref.name == symbol.name:
                # Check if this reference could be referring to our symbol
                # by resolving the name in the reference's scope
                resolved = ctx.scopes.resolve_visible(ref.scope_id, ref.name)
                if resolved and resolved.scope_id == symbol.scope_id and resolved.start_byte == symbol.start_byte:
                    ref_count += 1
        return ref_count

    def _looks_exported(self, ctx: RuleContext, symbol: Symbol) -> bool:
        """
        Heuristic: avoid renaming public API:
        - Declared in module/global scope (not function/block) and not a local variable
        """
        scope = ctx.scopes.get_scope(symbol.scope_id)
        if scope and scope.kind in ("module", "global", "package"):
            return True
        return False

    def _suggest_name(self, ctx: RuleContext, old: str, kind: str, scope_id: Optional[int]) -> str:
        """
        Produce a readable placeholder:
        - params: 'arg' + index if conflicts
        - locals: 'val', 'item', or 'idx' (if numeric loop counter detected)
        Style: snake (py) else lowerCamel
        """
        base = "arg" if kind == "param" else "val"
        
        # Check for common short variable patterns
        if old in ("x", "y", "z") and kind == "local":
            base = "value"
        elif old in ("n", "m") and kind == "local":
            base = "count"
        elif old == "s" and kind == "local":
            base = "text"
        elif old == "f" and kind == "local":
            base = "func"
            
        # Ensure no collision in scope (if scope info available)
        candidate = self._apply_style(ctx.adapter.language_id, base)
        
        if ctx.scopes and scope_id is not None:
            used = {sym.name for sym in ctx.scopes.symbols_in_scope(scope_id)}
            
            i = 2
            while candidate in used:
                candidate = self._apply_style(ctx.adapter.language_id, f"{base}{i}")
                i += 1
        
        return candidate

    def _apply_style(self, lang: str, s: str) -> str:
        """Apply language-appropriate naming style."""
        if lang == "python":
            # Convert to snake_case
            s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
            s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s).lower()
            return s
        else:
            # lowerCamelCase for most other languages
            parts = s.replace("-", "_").split("_")
            return parts[0].lower() + "".join(p.title() for p in parts[1:])

    def _make_diff(self, ctx: RuleContext, param: Dict[str, Any], suggestion: str, kind: str, min_len: int) -> Tuple[str, str]:
        """Generate a diff suggestion for renaming a parameter."""
        file_bytes = ctx.text
        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode('utf-8')
            
        start_byte = param["start_byte"]
        end_byte = param["end_byte"]
            
        line_start = file_bytes.rfind(b"\n", 0, start_byte) + 1
        line_end = file_bytes.find(b"\n", end_byte)
        if line_end == -1:
            line_end = len(file_bytes)
            
        before = file_bytes[line_start:line_end].decode("utf-8", errors="ignore")
        after = (
            file_bytes[line_start:start_byte].decode("utf-8", errors="ignore") +
            suggestion +
            file_bytes[end_byte:line_end].decode("utf-8", errors="ignore")
        )
        
        diff = f"""--- a/identifier
+++ b/identifier
-{before}
+{after}"""
        
        rationale = (
            f"Name is shorter than configured minimum ({min_len}). "
            f"Suggest renaming this {kind} to a more descriptive identifier."
        )
        
        return diff, rationale

    def _make_diff_for_symbol(self, ctx: RuleContext, symbol: Symbol, suggestion: str, kind: str, min_len: int) -> Tuple[str, str]:
        """Generate a diff suggestion for renaming a symbol."""
        file_bytes = ctx.text
        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode('utf-8')
            
        line_start = file_bytes.rfind(b"\n", 0, symbol.start_byte) + 1
        line_end = file_bytes.find(b"\n", symbol.end_byte)
        if line_end == -1:
            line_end = len(file_bytes)
            
        before = file_bytes[line_start:line_end].decode("utf-8", errors="ignore")
        after = (
            file_bytes[line_start:symbol.start_byte].decode("utf-8", errors="ignore") +
            suggestion +
            file_bytes[symbol.end_byte:line_end].decode("utf-8", errors="ignore")
        )
        
        diff = f"""--- a/identifier
+++ b/identifier
-{before}
+{after}"""
        
        rationale = (
            f"Name is shorter than configured minimum ({min_len}). "
            f"Suggest renaming this {kind} to a more descriptive identifier."
        )
        
        return diff, rationale


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(RuleNamingTooShortIdentifier())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


