"""
Rule to detect identifier naming convention violations and suggest compliant names.

This rule analyzes declarations (functions, classes, variables, etc.) and checks
if they follow the configured naming conventions. It provides suggestions for
renaming without modifying the code.
"""

from typing import Iterator, Dict, Any, Tuple, Optional
import re

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority


DEFAULT_MAP = {
    # Default naming conventions by symbol kind
    "function": "snake",       # Python default
    "method": "camel",
    "class": "pascal",
    "type": "pascal",
    "variable": "camel",
    "const": "upper_snake",
    "enum": "pascal",
    "enum_member": "upper_snake",
    "package": "lower_snake",
    "module": "lower_snake",
}


class RuleNamingConventionViolation(Rule):
    """Rule to suggest compliant names according to configured naming conventions."""
    
    meta = RuleMeta(
        id="naming.convention_violation",
        description="Suggest compliant names according to configured naming conventions per symbol kind.",
        category="naming",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"],
    )

    requires = Requires(syntax=True)

    # Case conversion helpers
    _re_word = re.compile(r"[A-Za-z0-9]+")

    def _to_snake(self, s: str) -> str:
        """Convert to snake_case: fooBar -> foo_bar"""
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
        return re.sub(r"[\W]+", "_", s).strip("_").lower()

    def _to_camel(self, s: str) -> str:
        """Convert to camelCase: foo_bar -> fooBar"""
        # First convert to snake case to split camelCase/PascalCase words properly
        snake_version = self._to_snake(s)
        parts = re.split(r"[_\W]+", snake_version)
        parts = [p for p in parts if p]
        if not parts:
            return s
        head, *rest = parts
        return head.lower() + "".join(p.capitalize() for p in rest)

    def _to_pascal(self, s: str) -> str:
        """Convert to PascalCase: foo_bar -> FooBar"""
        # First convert to snake case to split camelCase words properly
        snake_version = self._to_snake(s)
        parts = re.split(r"[_\W]+", snake_version)
        return "".join(p.capitalize() for p in parts if p)

    def _to_upper_snake(self, s: str) -> str:
        """Convert to UPPER_SNAKE_CASE: fooBar -> FOO_BAR"""
        return self._to_snake(s).upper()

    def _style_ok(self, style: str, name: str) -> bool:
        """Check if name matches the given style."""
        if style == "snake" or style == "lower_snake":
            return bool(re.fullmatch(r"[a-z][a-z0-9_]*", name))
        elif style == "camel":
            return bool(re.fullmatch(r"[a-z][A-Za-z0-9]*", name)) and name[:1].islower()
        elif style == "pascal":
            return bool(re.fullmatch(r"[A-Z][A-Za-z0-9]*", name))
        elif style == "upper_snake":
            return bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", name))
        return True  # Unknown style → don't block

    def _convert(self, style: str, name: str) -> str:
        """Convert name to the given style."""
        core = name.strip("_")
        if style in ("snake", "lower_snake"):
            return self._to_snake(core)
        elif style == "camel":
            return self._to_camel(core)
        elif style == "pascal":
            return self._to_pascal(core)
        elif style == "upper_snake":
            return self._to_upper_snake(core)
        return name

    def _config_map(self, ctx: RuleContext) -> Dict[str, str]:
        """Get the naming convention map from config."""
        config = ctx.config or {}
        naming_map = dict(DEFAULT_MAP)
        naming_map.update(config.get("naming_map", {}))
        return naming_map

    def _possible_decl_nodes(self, ctx: RuleContext):
        """
        Yield (node, kind, name_token) for declaration-like nodes.
        Uses conservative syntax kinds to avoid false positives.
        """
        lang = ctx.adapter.language_id
        target_kinds = set()
        
        if lang in ("javascript", "typescript"):
            target_kinds = {
                "function_declaration", "method_definition", "class_declaration",
                "lexical_declaration", "variable_declaration", "enum_declaration",
                "type_alias_declaration", "interface_declaration"
            }
        elif lang == "python":
            target_kinds = {
                "function_definition", "class_definition", "assignment"
            }
        elif lang in ("java", "csharp", "cpp", "c", "swift", "go", "rust", "ruby"):
            target_kinds = {
                "function_declaration", "method_declaration", "class_declaration",
                "struct_declaration", "enum_declaration", "const_declaration",
                "var_declaration", "let_declaration", "type_declaration"
            }
        else:
            # Fallback for unknown languages
            target_kinds = {"identifier"}

        # Walk the tree looking for declaration nodes
        def walk_tree(node):
            if hasattr(node, 'type') and node.type in target_kinds:
                yield node
            if hasattr(node, 'children'):
                for child in node.children:
                    yield from walk_tree(child)

        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return

        for node in walk_tree(ctx.tree.root_node):
            name_token = self._find_name_token(node)
            if not name_token:
                continue
            
            kind = self._classify_kind(ctx, node)
            yield (node, kind, name_token)

    def _find_name_token(self, node) -> Optional[Any]:
        """Find the identifier token in a declaration node."""
        # Try common patterns for finding the name
        if hasattr(node, 'name'):
            return node.name
        if hasattr(node, 'identifier'):
            return node.identifier
        
        # For JavaScript/TypeScript variable declarations, look for variable_declarator child
        if hasattr(node, 'children'):
            for child in node.children:
                if hasattr(child, 'type'):
                    if child.type == "variable_declarator":
                        # Look for the name field in the variable_declarator
                        if hasattr(child, 'name'):
                            return child.name
                        # Or find identifier in the variable_declarator children
                        if hasattr(child, 'children'):
                            for grandchild in child.children:
                                if hasattr(grandchild, 'type') and grandchild.type == "identifier":
                                    return grandchild
                    elif child.type in ("identifier", "type_identifier"):
                        return child
        
        return None

    def _classify_kind(self, ctx: RuleContext, node) -> str:
        """Classify the kind of declaration based on node type."""
        node_type = getattr(node, 'type', '')
        lang = ctx.adapter.language_id
        
        if lang == "python":
            if node_type == "function_definition":
                return "function"
            elif node_type == "class_definition":
                return "class"
            elif node_type == "assignment":
                return "variable"
        elif lang in ("javascript", "typescript"):
            if node_type == "function_declaration":
                return "function"
            elif node_type == "method_definition":
                return "method"
            elif node_type == "class_declaration":
                return "class"
            elif node_type == "enum_declaration":
                return "enum"
            elif node_type in ("variable_declaration", "lexical_declaration"):
                # Check if it's a const declaration
                if hasattr(node, 'children'):
                    for child in node.children:
                        if hasattr(child, 'text') and child.text == b'const':
                            return "const"
                return "variable"
            elif node_type in ("type_alias_declaration", "interface_declaration"):
                return "type"
        else:
            # Generic classification for other languages
            if "method" in node_type:
                return "method"
            elif "function" in node_type:
                return "function"
            elif "class" in node_type or "struct" in node_type:
                return "class"
            elif "enum" in node_type:
                return "enum"
            elif "const" in node_type:
                return "const"
            elif "var" in node_type or "let" in node_type:
                return "variable"
            elif "type" in node_type:
                return "type"
        
        return "variable"  # Default fallback

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect naming convention violations."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        naming_map = self._config_map(ctx)
        
        for node, kind, name_token in self._possible_decl_nodes(ctx):
            if not name_token or not hasattr(name_token, 'text'):
                continue
                
            name = name_token.text
            if isinstance(name, bytes):
                name = name.decode("utf-8", errors="ignore")
            
            # Skip empty names or reserved names
            if not name or name.startswith('__') and name.endswith('__'):
                continue
                
            style = naming_map.get(kind)
            if not style:
                continue
                
            if self._style_ok(style, name):
                continue

            suggestion = self._convert(style, name)
            if suggestion == name or not suggestion:
                continue

            diff, rationale = self._rename_suggestion(ctx, name_token, suggestion, style, kind)
            
            yield Finding(
                rule=self.meta.id,
                message=f"Rename {kind} '{name}' to match {style} case.",
                file=ctx.file_path,
                start_byte=name_token.start_byte,
                end_byte=name_token.end_byte,
                severity="info",
                meta={
                    "kind": kind,
                    "style": style,
                    "original_name": name,
                    "suggested_name": suggestion,
                    "diff": diff,
                    "rationale": rationale
                }
            )

    def _rename_suggestion(self, ctx: RuleContext, name_token, new_name: str, style: str, kind: str) -> Tuple[str, str]:
        """Generate a diff suggestion for renaming."""
        file_bytes = ctx.text
        if isinstance(file_bytes, str):
            file_bytes = file_bytes.encode('utf-8')
            
        line_start = file_bytes.rfind(b"\n", 0, name_token.start_byte) + 1
        line_end = file_bytes.find(b"\n", name_token.end_byte)
        if line_end == -1:
            line_end = len(file_bytes)
            
        before = file_bytes[line_start:line_end].decode("utf-8", errors="ignore")
        after = (
            file_bytes[line_start:name_token.start_byte].decode("utf-8", errors="ignore") +
            new_name +
            file_bytes[name_token.end_byte:line_end].decode("utf-8", errors="ignore")
        )
        
        diff = f"""--- a/declaration
+++ b/declaration
-{before}
+{after}"""
        
        rationale = (
            f"Project naming_map requires {kind} names in {style} case. "
            "This is a suggestion-only change to avoid breaking references."
        )
        
        return diff, rationale


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(RuleNamingConventionViolation())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


