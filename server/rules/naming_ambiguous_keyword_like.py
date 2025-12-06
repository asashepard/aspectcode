"""
Rule to detect identifiers whose names are ambiguous or keyword-like.

This rule flags user-defined symbols (locals, params, functions, classes) that match
language keywords, builtin types, or common standard library types, and suggests
clearer alternatives to avoid confusion or shadowing.
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


# Per-language reserved/keyword-like terms
DEFAULT_SETS = {
    "python": {
        "keywords": {"False", "None", "True", "and", "as", "assert", "break", "class", "continue", "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield"},
        "builtins": {"list", "dict", "set", "tuple", "str", "int", "float", "bool", "object", "type", "bytes", "len", "map", "filter", "sum", "min", "max", "any", "all", "open", "range", "print", "input", "eval", "exec", "compile", "abs", "round", "pow", "divmod", "complex", "sorted", "reversed", "enumerate", "zip", "iter", "next"},
        "common_types": {"Path", "Dict", "List", "Set", "Tuple", "Optional", "Union", "Any", "Callable", "ClassVar", "Final", "Literal", "TypeVar", "Generic"},
    },
    "javascript": {
        "keywords": {"break", "case", "catch", "class", "const", "continue", "debugger", "default", "delete", "do", "else", "enum", "export", "extends", "false", "finally", "for", "function", "if", "import", "in", "instanceof", "new", "null", "return", "super", "switch", "this", "throw", "true", "try", "typeof", "var", "void", "while", "with", "yield", "await", "let"},
        "builtins": {"Array", "Map", "Set", "String", "Number", "Boolean", "Object", "Symbol", "BigInt", "Promise", "Math", "JSON", "Date", "RegExp", "Error", "Function", "console"},
        "common_types": {"ReadonlyArray", "Record", "Partial", "Required", "NonNullable", "Pick", "Omit"},
    },
    "typescript": {
        "keywords": {"abstract", "any", "as", "asserts", "bigint", "boolean", "break", "case", "catch", "class", "const", "continue", "declare", "default", "delete", "do", "else", "enum", "export", "extends", "false", "finally", "for", "from", "function", "if", "import", "in", "infer", "instanceof", "interface", "is", "keyof", "let", "module", "namespace", "never", "new", "null", "number", "object", "package", "private", "protected", "public", "readonly", "require", "global", "return", "set", "static", "string", "super", "switch", "symbol", "this", "throw", "true", "try", "type", "typeof", "undefined", "unique", "unknown", "var", "void", "while", "with", "yield"},
        "builtins": {"Array", "Map", "Set", "String", "Number", "Boolean", "Object", "Symbol", "BigInt", "Promise", "ReadonlyArray", "Record", "Partial", "Required", "Date", "RegExp", "Error", "Function", "console"},
        "common_types": {"Readonly", "NonNullable", "Pick", "Omit", "Exclude", "Extract", "ReturnType", "Parameters", "ConstructorParameters", "InstanceType", "ThisType"},
    },
    "go": {
        "keywords": {"break", "case", "chan", "const", "continue", "default", "defer", "else", "fallthrough", "for", "func", "go", "goto", "if", "import", "interface", "map", "package", "range", "return", "select", "struct", "switch", "type", "var"},
        "builtins": {"string", "int", "int64", "uint", "byte", "rune", "error", "bool", "complex64", "complex128", "make", "new", "len", "cap", "append", "copy", "close", "delete", "panic", "recover", "print", "println"},
        "common_types": {"Context", "Time", "Duration", "sync", "io", "fmt"},
    },
    "java": {
        "keywords": {"abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class", "const", "continue", "default", "do", "double", "else", "enum", "extends", "final", "finally", "float", "for", "goto", "if", "implements", "import", "instanceof", "int", "interface", "long", "native", "new", "package", "private", "protected", "public", "return", "short", "static", "strictfp", "super", "switch", "synchronized", "this", "throw", "throws", "transient", "try", "void", "volatile", "while"},
        "builtins": {"String", "Object", "Integer", "Long", "Double", "List", "Map", "Set", "Boolean", "Character", "Byte", "Short", "Float", "Class", "System"},
        "common_types": {"Optional", "Stream", "Collection", "ArrayList", "HashMap", "HashSet", "Comparator", "Predicate", "Function", "Supplier", "Consumer"},
    },
    "csharp": {
        "keywords": {"abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char", "checked", "class", "const", "continue", "decimal", "default", "delegate", "do", "double", "else", "enum", "event", "explicit", "extern", "false", "finally", "fixed", "float", "for", "foreach", "goto", "if", "implicit", "in", "int", "interface", "internal", "is", "lock", "long", "namespace", "new", "null", "object", "operator", "out", "override", "params", "private", "protected", "public", "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof", "stackalloc", "static", "string", "struct", "switch", "this", "throw", "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe", "ushort", "using", "virtual", "void", "volatile", "while"},
        "builtins": {"String", "Object", "Int32", "List", "Dictionary", "Task", "Boolean", "Char", "Byte", "Int16", "Int64", "UInt32", "UInt64", "Single", "Double", "Decimal", "DateTime", "TimeSpan", "Guid", "Console"},
        "common_types": {"IEnumerable", "Span", "Memory", "ICollection", "IDictionary", "IList", "Func", "Action", "Predicate", "Task", "ValueTask"},
    },
    "cpp": {
        "keywords": {"alignas", "alignof", "and", "and_eq", "asm", "atomic_cancel", "atomic_commit", "atomic_noexcept", "auto", "bitand", "bitor", "bool", "break", "case", "catch", "char", "char8_t", "char16_t", "char32_t", "class", "compl", "concept", "const", "consteval", "constexpr", "constinit", "const_cast", "continue", "co_await", "co_return", "co_yield", "decltype", "default", "delete", "do", "double", "dynamic_cast", "else", "enum", "explicit", "export", "extern", "false", "float", "for", "friend", "goto", "if", "inline", "int", "long", "mutable", "namespace", "new", "noexcept", "not", "not_eq", "nullptr", "operator", "or", "or_eq", "private", "protected", "public", "register", "reinterpret_cast", "requires", "return", "short", "signed", "sizeof", "static", "static_assert", "static_cast", "struct", "switch", "template", "this", "thread_local", "throw", "true", "try", "typedef", "typeid", "typename", "union", "unsigned", "using", "virtual", "void", "volatile", "wchar_t", "while", "xor", "xor_eq"},
        "builtins": {"string", "vector", "map", "set", "list", "deque", "queue", "stack", "pair", "tuple", "array", "unordered_map", "unordered_set"},
        "common_types": {"optional", "variant", "any", "function", "shared_ptr", "unique_ptr", "weak_ptr"},
    },
    "c": {
        "keywords": {"auto", "break", "case", "char", "const", "continue", "default", "do", "double", "else", "enum", "extern", "float", "for", "goto", "if", "inline", "int", "long", "register", "restrict", "return", "short", "signed", "sizeof", "static", "struct", "switch", "typedef", "union", "unsigned", "void", "volatile", "while", "_Alignas", "_Alignof", "_Atomic", "_Bool", "_Complex", "_Generic", "_Imaginary", "_Noreturn", "_Static_assert", "_Thread_local"},
        "builtins": {"printf", "scanf", "malloc", "free", "calloc", "realloc", "memcpy", "memset", "strlen", "strcpy", "strcmp", "strcat", "FILE", "size_t", "NULL"},
        "common_types": {"ptrdiff_t", "wchar_t", "intptr_t", "uintptr_t", "int8_t", "int16_t", "int32_t", "int64_t", "uint8_t", "uint16_t", "uint32_t", "uint64_t"},
    },
    "ruby": {
        "keywords": {"__ENCODING__", "__LINE__", "__FILE__", "BEGIN", "END", "alias", "and", "begin", "break", "case", "class", "def", "defined?", "do", "else", "elsif", "end", "ensure", "false", "for", "if", "in", "module", "next", "nil", "not", "or", "redo", "rescue", "retry", "return", "self", "super", "then", "true", "undef", "unless", "until", "when", "while", "yield"},
        "builtins": {"String", "Array", "Hash", "Object", "Module", "Class", "Integer", "Float", "Numeric", "Symbol", "Proc", "Method", "Time", "File", "IO", "Kernel", "puts", "print", "p", "gets", "require", "load"},
        "common_types": {"Enumerable", "Comparable", "StandardError", "ArgumentError", "RuntimeError", "TypeError", "NameError"},
    },
    "rust": {
        "keywords": {"as", "break", "const", "continue", "crate", "else", "enum", "extern", "false", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref", "return", "self", "Self", "static", "struct", "super", "trait", "true", "type", "unsafe", "use", "where", "while", "async", "await", "dyn", "abstract", "become", "box", "do", "final", "macro", "override", "priv", "try", "typeof", "unsized", "virtual", "yield"},
        "builtins": {"String", "Vec", "Option", "Result", "str", "bool", "char", "u8", "u16", "u32", "u64", "u128", "usize", "i8", "i16", "i32", "i64", "i128", "isize", "f32", "f64", "Box", "Rc", "Arc", "Cell", "RefCell", "Mutex", "RwLock"},
        "common_types": {"Duration", "PathBuf", "Path", "HashMap", "HashSet", "BTreeMap", "BTreeSet", "VecDeque", "LinkedList", "BinaryHeap"},
    },
    "swift": {
        "keywords": {"associatedtype", "class", "deinit", "enum", "extension", "fileprivate", "func", "import", "init", "inout", "internal", "let", "open", "operator", "private", "protocol", "public", "static", "struct", "subscript", "typealias", "var", "break", "case", "catch", "continue", "default", "defer", "do", "else", "fallthrough", "for", "guard", "if", "in", "repeat", "return", "throw", "throws", "where", "while", "as", "Any", "false", "is", "nil", "rethrows", "super", "self", "Self", "true", "try"},
        "builtins": {"String", "Int", "Array", "Dictionary", "Set", "Bool", "Double", "Float", "Character", "Optional", "AnyObject", "AnyClass", "Error", "CustomStringConvertible", "Equatable", "Hashable", "Comparable"},
        "common_types": {"URL", "Data", "Date", "UUID", "IndexPath", "NSError", "DispatchQueue", "Result"},
    },
}


class RuleNamingAmbiguousKeywordLike(Rule):
    """Rule to detect identifiers whose names are ambiguous or keyword-like."""
    
    meta = RuleMeta(
        id="naming.ambiguous_keyword_like",
        description="Avoid naming identifiers after keywords or builtin/common types; suggest clearer alternatives.",
        category="naming",
        tier=1,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"],
    )

    requires = Requires(syntax=True, scopes=True, raw_text=True)

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect keyword-like identifiers."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        lang = ctx.adapter.language_id
        config = ctx.config or {}
        custom = set(config.get("keyword_like_extra", []))
        allow_shadow = set(config.get("keyword_like_allow", []))
        
        sets = DEFAULT_SETS.get(lang, {"keywords": set(), "builtins": set(), "common_types": set()})
        reserved = sets["keywords"] | sets["builtins"] | sets["common_types"]
        reserved |= custom

        if not ctx.scopes:
            return

        # Find all user-defined symbols that might shadow keywords/builtins
        for symbol in ctx.scopes.iter_symbols():
            # Only user-defined code symbols
            if symbol.kind not in ("param", "local", "variable", "function", "class", "const", "field"):
                continue
                
            name = symbol.name
            if not name or name in allow_shadow:
                continue
                
            # Skip exported/public API
            if self._looks_exported(ctx, symbol):
                continue
                
            # Skip uppercase constants that might legitimately match type names
            if self._is_constant_like(name):
                continue

            if self._is_keyword_like(lang, name, reserved):
                suggestion = self._suggest_name(ctx, lang, name, symbol.kind, symbol.scope_id)
                diff, rationale = self._make_diff(ctx, symbol, suggestion, name)

                yield Finding(
                    rule=self.meta.id,
                    message=f"Identifier '{name}' is keyword/type-like; consider a clearer name.",
                    file=ctx.file_path,
                    start_byte=symbol.start_byte,
                    end_byte=symbol.end_byte,
                    severity="warning",
                    meta={
                        "original_name": name,
                        "suggested_name": suggestion,
                        "shadow_type": self._classify_shadow_type(lang, name, sets),
                        "symbol_kind": symbol.kind,
                        "language": lang,
                        "diff": diff,
                        "rationale": rationale
                    }
                )

    def _looks_exported(self, ctx: RuleContext, symbol: Symbol) -> bool:
        """
        Heuristic: avoid renaming public API.
        Check if symbol appears to be exported/public.
        """
        # In module/global scope, might be exported
        scope = ctx.scopes.get_scope(symbol.scope_id)
        if scope and scope.kind in ("module", "global"):
            # For Python, check if name starts with underscore (private convention)
            if ctx.adapter.language_id == "python":
                # Only skip if it starts with underscore AND it's not a problematic builtin/keyword
                # We still want to flag module-level 'list', 'dict', etc. even if they're "exported"
                return symbol.name.startswith("_")
            # For other languages, assume module-level definitions might be exported
            # But for now, let's be more aggressive and flag them anyway
            return False
        return False

    def _is_constant_like(self, name: str) -> bool:
        """Check if identifier looks like a constant (ALL_CAPS)."""
        return name.isupper() and len(name) > 1

    def _is_keyword_like(self, lang: str, name: str, reserved: Set[str]) -> bool:
        """Check if name matches a reserved keyword/builtin/type."""
        # Case-sensitive check - different languages have different conventions
        return name in reserved

    def _classify_shadow_type(self, lang: str, name: str, sets: Dict[str, Set[str]]) -> str:
        """Classify what type of reserved word is being shadowed."""
        if name in sets["keywords"]:
            return "keyword"
        elif name in sets["builtins"]:
            return "builtin"
        elif name in sets["common_types"]:
            return "common_type"
        else:
            return "custom"

    def _suggest_name(self, ctx: RuleContext, lang: str, name: str, kind: str, scope_id: int) -> str:
        """
        Generate a clearer alternative name.
        """
        # Mapping of common problematic names to better alternatives
        base_map = {
            # Python/general
            "list": "items", "dict": "mapping", "set": "values", "tuple": "values",
            "str": "text", "string": "text", "String": "text", "bytes": "data",
            "int": "count", "float": "value", "bool": "flag", "Boolean": "flag",
            "object": "obj", "Object": "obj", "type": "cls", "Type": "cls",
            "len": "length", "map": "mapping", "Map": "mapping",
            "class": "cls", "return": "result", "function": "func", "Function": "func",
            
            # JavaScript/TypeScript
            "Array": "items", "Number": "value", "Symbol": "sym",
            "Promise": "promise_val", "Date": "date_val", "RegExp": "pattern",
            "Math": "math_utils", "JSON": "json_data", "console": "logger",
            
            # Java/C#
            "Integer": "count", "Long": "long_val", "Double": "double_val",
            "List": "items", "Set": "values", "Dictionary": "mapping",
            "Task": "task_val", "System": "sys",
            
            # Go
            "interface": "iface", "struct": "s", "chan": "channel",
            "make": "create", "new": "create", "error": "err",
            
            # C/C++
            "vector": "items", "pair": "pair_val", "tuple": "tuple_val",
            "optional": "opt", "variant": "var_val",
            
            # Rust
            "Vec": "items", "Option": "opt", "Result": "res",
            "Box": "boxed", "Rc": "shared", "Arc": "atomic_shared",
            
            # Swift
            "URL": "url_val", "Data": "data_val", "UUID": "uuid_val",
        }
        
        base = base_map.get(name, f"{name}_val")
        
        # Apply language-specific styling
        base = self._apply_naming_style(lang, base, kind)
        
        # Ensure no collision in scope
        if ctx.scopes:
            used = {sym.name for sym in ctx.scopes.symbols_in_scope(scope_id)}
            candidate = base
            i = 2
            while candidate in used:
                candidate = f"{base}{i}"
                i += 1
            return candidate
        
        return base

    def _apply_naming_style(self, lang: str, name: str, kind: str) -> str:
        """Apply language-appropriate naming conventions."""
        if lang == "python":
            # Python uses snake_case for variables and functions
            if kind in ("param", "local", "variable", "function"):
                return self._to_snake_case(name)
        elif lang in ("javascript", "typescript"):
            # JS/TS use camelCase for variables and functions
            if kind in ("param", "local", "variable", "function"):
                return self._to_camel_case(name)
        elif lang == "go":
            # Go uses camelCase for unexported, PascalCase for exported
            if kind in ("param", "local", "variable"):
                return self._to_camel_case(name)
        elif lang in ("java", "csharp"):
            # Java/C# use camelCase for variables, PascalCase for types
            if kind in ("param", "local", "variable", "function"):
                return self._to_camel_case(name)
        elif lang in ("cpp", "c"):
            # C/C++ vary, but lowercase with underscores is common
            return self._to_snake_case(name)
        elif lang == "rust":
            # Rust uses snake_case for variables and functions
            if kind in ("param", "local", "variable", "function"):
                return self._to_snake_case(name)
        elif lang == "swift":
            # Swift uses camelCase for variables and functions
            if kind in ("param", "local", "variable", "function"):
                return self._to_camel_case(name)
        elif lang == "ruby":
            # Ruby uses snake_case for variables and methods
            if kind in ("param", "local", "variable", "function"):
                return self._to_snake_case(name)
        
        return name

    def _to_snake_case(self, name: str) -> str:
        """Convert to snake_case."""
        # Insert underscores before capital letters
        name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name)
        return name.lower()

    def _to_camel_case(self, name: str) -> str:
        """Convert to camelCase."""
        parts = name.replace("_", " ").replace("-", " ").split()
        if not parts:
            return name
        return parts[0].lower() + "".join(word.capitalize() for word in parts[1:])

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
            f"'{old_name}' is keyword/builtin-like in {ctx.adapter.language_id}. "
            f"Rename to avoid confusion or shadowing. Suggestion is local-only and does not update references."
        )
        
        return diff, rationale


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(RuleNamingAmbiguousKeywordLike())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


