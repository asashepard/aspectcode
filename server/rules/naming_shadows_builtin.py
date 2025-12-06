"""
Rule to detect identifiers that shadow language builtins.

This rule flags user-defined symbols (locals, params, functions, classes) that shadow
language builtins and suggests safer alternative names to avoid confusion and
accidental shadowing.
"""

from typing import Iterator, Dict, Any, Set, Optional
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


# Language-specific builtin sets
BUILTINS = {
    "python": {
        # Core builtins + common stdlib types/functions that frequently cause confusion
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes", "callable", "chr", "classmethod", "compile", "complex",
        "delattr", "dict", "dir", "divmod", "enumerate", "eval", "exec", "filter", "float", "format", "frozenset", "getattr",
        "globals", "hasattr", "hash", "help", "hex", "id", "input", "int", "isinstance", "issubclass", "iter", "len", "list",
        "locals", "map", "max", "min", "next", "object", "oct", "open", "ord", "pow", "print", "property", "range", "repr", "reversed",
        "round", "set", "setattr", "slice", "sorted", "staticmethod", "str", "sum", "super", "tuple", "type", "vars", "zip",
        # Common stdlib that often gets shadowed
        "datetime", "time", "math", "random", "os", "sys", "json", "re", "copy", "collections", "itertools", "functools",
    },
    "javascript": {
        # Global objects/functions frequently shadowed
        "Array", "Boolean", "BigInt", "Date", "Error", "Function", "JSON", "Map", "Math", "Number", "Object", "Promise", "Proxy",
        "Reflect", "RegExp", "Set", "String", "Symbol", "WeakMap", "WeakSet", "Intl", "parseInt", "parseFloat", "isNaN", "isFinite",
        "eval", "decodeURI", "decodeURIComponent", "encodeURI", "encodeURIComponent", "setTimeout", "setInterval", "clearTimeout",
        "clearInterval", "queueMicrotask",
        # Browser globals that are commonly shadowed
        "console", "window", "document", "location", "history", "navigator", "screen", "localStorage", "sessionStorage",
        # Node.js globals
        "process", "Buffer", "global", "require", "module", "exports", "__dirname", "__filename",
    },
    "ruby": {
        # Core classes/modules and kernel methods
        "Array", "BasicObject", "Binding", "Class", "Comparable", "Dir", "ENV", "Enumerable", "Exception", "FalseClass", "File",
        "Float", "Hash", "Integer", "Kernel", "Module", "NilClass", "Object", "Proc", "Range", "Regexp", "String", "Struct", "Symbol",
        "Thread", "Time", "TrueClass", "IO", "Math", "GC", "puts", "print", "p", "loop", "raise", "require", "load", "autoload",
        # Common methods that get shadowed
        "select", "reject", "collect", "each", "map", "reduce", "inject", "find", "detect", "sort", "reverse", "join", "split",
        "match", "gsub", "sub", "scan", "strip", "chomp", "downcase", "upcase", "capitalize", "swapcase",
    },
}


class RuleNamingShadowsBuiltin(Rule):
    """
    Rule to detect identifiers that shadow language builtins.
    
    This rule flags user-defined symbols (locals, functions, classes) that shadow
    language builtins and suggests safer alternative names to avoid confusion.
    
    Note: Current scope analysis has limitations with parameter detection - 
    function parameters may not be detected as individual symbols.
    """
    
    meta = RuleMeta(
        id="naming.shadows_builtin",
        description="Warn when identifiers shadow language builtins; suggest a clearer alternative.",
        category="naming",
        tier=1,
        priority="P0",
        autofix_safety="suggest-only",
        langs=["python", "ruby", "javascript"],
    )

    requires = Requires(syntax=True, scopes=True, raw_text=True)

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect builtin shadowing."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        lang = ctx.adapter.language_id
        reserved = BUILTINS.get(lang, set())
        config = ctx.config or {}
        allow = set(config.get("shadow_allowlist", []))  # User overrides

        if not ctx.scopes:
            return

        # Collect all used names per scope for collision detection
        scope_names = {}
        for symbol in ctx.scopes.iter_symbols():
            scope_id = symbol.scope_id
            if scope_id not in scope_names:
                scope_names[scope_id] = set()
            if hasattr(symbol, "name") and symbol.name:
                scope_names[scope_id].add(symbol.name)

        # Find all user-defined symbols that shadow builtins
        for symbol in ctx.scopes.iter_symbols():
            # Only interested in user-defined symbols
            if symbol.kind not in ("param", "local", "variable", "function", "method", "class", "const", "field", "property"):
                continue

            name = symbol.name
            if not name:
                continue

            # Skip exported/public to avoid noisy cross-file refactors
            if self._looks_exported(ctx, symbol):
                continue

            # Respect allow-list and exact-match against builtin set
            if name in allow or name not in reserved:
                continue

            # Get used names in this scope for collision detection
            used_names = scope_names.get(symbol.scope_id, set())
            
            suggestion = self._suggest_name(lang, name, used_names)
            diff, rationale = self._make_diff(ctx, symbol, suggestion, name)

            yield Finding(
                rule=self.meta.id,
                message=f"Identifier '{name}' shadows a {lang} builtin; choose a different name.",
                file=ctx.file_path,
                start_byte=symbol.start_byte,
                end_byte=symbol.end_byte,
                severity="warning",
                meta={
                    "original_name": name,
                    "suggested_name": suggestion,
                    "builtin_language": lang,
                    "symbol_kind": symbol.kind,
                    "diff": diff,
                    "rationale": rationale
                }
            )

    def _looks_exported(self, ctx: RuleContext, symbol: Symbol) -> bool:
        """
        Heuristic: avoid renaming public API.
        Check if symbol appears to be exported/public.
        
        For builtin shadowing, we're more aggressive than other naming rules
        because shadowing builtins is usually unintentional.
        """
        # In module/global scope, might be exported
        scope = ctx.scopes.get_scope(symbol.scope_id)
        if scope and scope.kind in ("module", "global", "file"):
            # For Python, only skip if name starts with underscore (private convention)
            # We still want to flag module-level 'list', 'dict', etc. even if they're "exported"
            if ctx.adapter.language_id == "python":
                return symbol.name.startswith("_")
            # For other languages, be more aggressive and flag module-level definitions
            # since builtin shadowing is usually unintentional
            return False
        return False

    def _suggest_name(self, lang: str, name: str, used_names: Set[str]) -> str:
        """
        Generate a safer alternative name that doesn't shadow builtins.
        Prefer descriptive aliases; fallback: suffix underscore(s) until non-colliding.
        """
        # Common safe aliases for frequently shadowed builtins
        base_map = {
            "python": {
                "list": "items", "dict": "mapping", "set": "values", "str": "text", "int": "count", 
                "map": "mapper", "filter": "predicate", "type": "cls", "object": "obj",
                "len": "length", "max": "maximum", "min": "minimum", "sum": "total",
                "open": "file_handle", "print": "output", "input": "user_input",
                "range": "numbers", "zip": "pairs", "enumerate": "indexed",
                "datetime": "dt", "time": "timestamp", "math": "math_utils", "random": "rng",
                "json": "json_data", "re": "regex", "os": "operating_system", "sys": "system",
            },
            "javascript": {
                "Array": "arr", "Map": "map_", "Set": "set_", "String": "text", "Object": "obj", 
                "Date": "date_", "Function": "func", "Promise": "promise_", "RegExp": "regex",
                "Number": "num", "Boolean": "flag", "Error": "err", "JSON": "json_data",
                "Math": "math_utils", "Symbol": "sym", "console": "logger",
                "setTimeout": "timer", "setInterval": "interval", "parseInt": "parse_int",
                "parseFloat": "parse_float", "isNaN": "is_not_number", "isFinite": "is_finite",
                "window": "win", "document": "doc", "location": "loc", "navigator": "nav",
                "process": "proc", "Buffer": "buffer_", "require": "import_",
            },
            "ruby": {
                "Array": "arr", "Hash": "hash_", "String": "text", "Object": "obj", 
                "Proc": "proc_", "Time": "time_", "puts": "puts_", "print": "print_",
                "select": "filter", "reject": "exclude", "collect": "transform", "map": "transform",
                "reduce": "aggregate", "inject": "accumulate", "find": "locate", "detect": "locate",
                "sort": "order", "reverse": "invert", "join": "combine", "split": "divide",
                "match": "find_match", "gsub": "replace_all", "sub": "replace_first",
                "strip": "trim", "chomp": "remove_newline", "downcase": "lowercase",
                "upcase": "uppercase", "capitalize": "title_case",
            },
        }
        
        # Get the preferred base name or default to name with underscore
        base = base_map.get(lang, {}).get(name, f"{name}_")
        
        # Ensure no collision in scope
        candidate = base
        i = 2
        while candidate in used_names:
            candidate = f"{base}{i}"
            i += 1
            
        return candidate

    def _make_diff(self, ctx: RuleContext, symbol: Symbol, suggestion: str, old_name: str) -> tuple[str, str]:
        """Generate a diff suggestion for renaming."""
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
            f"'{old_name}' is a builtin in {ctx.adapter.language_id}. "
            f"Renaming avoids confusion and accidental shadowing."
        )
        
        return diff, rationale


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(RuleNamingShadowsBuiltin())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass

# Also add to local RULES list for backward compatibility
try:
    from . import register
    register(RuleNamingShadowsBuiltin())
except ImportError:
    # Handle case where rules module registration isn't available
    pass


