# server/rules/errors_ignored_return_status.py
"""
Rule to detect function calls whose return values are ignored.

This rule analyzes function call expressions across multiple languages for:
- C/C++: Function calls used as bare expression statements without assignment or void cast
- Go: Function calls that return error values but are not handled
- Rust: Function calls returning Result or Option types without handling
- C#/Java: Method calls returning values that are ignored

When ignored return values are detected, it suggests handling the return value
through assignment, error checking, or explicit discard patterns per language conventions.
"""

from typing import Set, Optional, List
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsIgnoredReturnStatusRule:
    """Rule to detect function calls whose return values are ignored."""
    
    meta = RuleMeta(
        id="errors.ignored_return_status",
        category="errors",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects function calls whose return values are ignored; suggests handling status/error or explicit discard.",
        langs=["c", "cpp", "go", "rust", "csharp", "java"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific expression statement node types
    EXPRESSION_STATEMENT_TYPES = {
        "c": "expression_statement",
        "cpp": "expression_statement", 
        "go": "expression_statement",
        "rust": "expression_statement",  # Sometimes expr_stmt in tree-sitter-rust
        "csharp": "expression_statement",
        "java": "expression_statement",
    }

    # Language-specific call expression node types
    CALL_EXPRESSION_TYPES = {
        "c": {"call_expression"},
        "cpp": {"call_expression"},
        "go": {"call_expression"},
        "rust": {"call_expression", "method_call_expression"},
        "csharp": {"invocation_expression"},
        "java": {"method_invocation"},
    }

    # Non-meaningful node types that should be ignored
    TRIVIAL_NODE_TYPES = {
        "comment", "whitespace", "line_comment", "block_comment", 
        "newline", ";", "semicolon"
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for ignored return values."""
        language = ctx.adapter.language_id
        
        # Skip unsupported languages
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Walk the syntax tree looking for expression statements
        for node in ctx.walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            if self._is_bare_call_expr_stmt(node, language, ctx.text):
                finding = self._create_finding(ctx, node, language)
                if finding:
                    yield finding

    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        if not tree or not hasattr(tree, 'root_node'):
            return

        def walk_recursive(node):
            yield node
            if hasattr(node, 'children'):
                children = getattr(node, 'children', [])
                if children:
                    try:
                        for child in children:
                            yield from walk_recursive(child)
                    except (TypeError, AttributeError):
                        # Handle mock objects or tree-sitter iteration issues
                        pass

        yield from walk_recursive(tree.root_node)

    def _matches_language(self, ctx: RuleContext, supported_langs: List[str]) -> bool:
        """Check if the current language is supported."""
        return ctx.adapter.language_id in supported_langs

    def _is_bare_call_expr_stmt(self, node, language: str, file_text: str) -> bool:
        """Check if node is an expression statement containing only a bare function call."""
        # Check if this is an expression statement
        stmt_type = self.EXPRESSION_STATEMENT_TYPES.get(language)
        if not stmt_type:
            return False
        
        # Handle both exact match and alternative forms (e.g., expr_stmt vs expression_statement)
        node_type = getattr(node, 'type', '')
        if node_type != stmt_type and node_type != "expr_stmt":
            return False
        
        # Get meaningful children (excluding trivial nodes)
        meaningful_children = self._get_meaningful_children(node)
        
        # Must have exactly one meaningful child
        if len(meaningful_children) != 1:
            return False
        
        child = meaningful_children[0]
        child_type = getattr(child, 'type', '')
        
        # Check if the child is a call expression for this language
        call_types = self.CALL_EXPRESSION_TYPES.get(language, set())
        if child_type not in call_types:
            return False
        
        # Additional checks to avoid false positives
        return self._is_likely_ignored_call(child, language, file_text)

    def _get_meaningful_children(self, node) -> List:
        """Extract meaningful children from node, excluding trivial ones."""
        if not node or not hasattr(node, 'children'):
            return []
        
        children = getattr(node, 'children', [])
        meaningful = []
        
        try:
            for child in children:
                if hasattr(child, 'type'):
                    child_type = child.type
                    # Skip trivial nodes
                    if child_type not in self.TRIVIAL_NODE_TYPES:
                        meaningful.append(child)
        except (TypeError, AttributeError):
            pass
        
        return meaningful

    def _is_likely_ignored_call(self, call_node, language: str, file_text: str) -> bool:
        """Additional checks to determine if a call is likely an ignored return value."""
        # Get the call text to check for explicit discard patterns
        call_text = self._get_node_text(call_node, file_text)
        if not call_text:
            return True  # Default to flagging if we can't get text
        
        # Language-specific patterns to avoid flagging
        if language in ["c", "cpp"]:
            return self._should_flag_c_cpp_call(call_text, call_node)
        elif language == "go":
            return self._should_flag_go_call(call_text, call_node)
        elif language == "rust":
            return self._should_flag_rust_call(call_text, call_node)
        elif language in ["csharp", "java"]:
            return self._should_flag_csharp_java_call(call_text, call_node)
        
        return True

    def _get_node_text(self, node, file_text: str) -> str:
        """Extract text content of a node."""
        if not node:
            return ""
        
        # First try to get text from the node itself (for mock objects)
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Otherwise extract from file text using byte positions
        if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            try:
                return file_text[node.start_byte:node.end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""

    def _should_flag_c_cpp_call(self, call_text: str, call_node) -> bool:
        """Check if C/C++ call should be flagged."""
        # Don't flag void casts: (void)function()
        if call_text.strip().startswith("(void)"):
            return False
        
        # Don't flag calls that are clearly for side effects
        side_effect_functions = {
            "printf", "fprintf", "puts", "putchar", "putc",
            "cout", "cerr", "endl", "flush",
            "free", "delete", "close", "fclose",
            "assert", "abort", "exit"
        }
        
        # Extract function name (basic heuristic)
        func_name = self._extract_function_name(call_text)
        if func_name and func_name in side_effect_functions:
            return False
        
        return True

    def _should_flag_go_call(self, call_text: str, call_node) -> bool:
        """Check if Go call should be flagged."""
        # Don't flag blank identifier assignments (handled elsewhere)
        # This is a bare call, so we should flag it unless it's clearly side-effect only
        
        side_effect_functions = {
            "panic", "print", "println", 
            "close", "recover",
            "runtime.GC", "runtime.Gosched"
        }
        
        func_name = self._extract_function_name(call_text)
        if func_name and func_name in side_effect_functions:
            return False
        
        return True

    def _should_flag_rust_call(self, call_text: str, call_node) -> bool:
        """Check if Rust call should be flagged."""
        # Don't flag calls with explicit handling patterns
        if ".expect(" in call_text or ".unwrap(" in call_text:
            return False
        
        if ".map(" in call_text or ".and_then(" in call_text:
            return False
        
        # Don't flag calls that are clearly for side effects
        side_effect_patterns = {
            "println!", "print!", "eprintln!", "eprint!",
            "panic!", "unreachable!", "unimplemented!",
            "drop(", "mem::drop(", "std::mem::drop("
        }
        
        if any(pattern in call_text for pattern in side_effect_patterns):
            return False
        
        return True

    def _should_flag_csharp_java_call(self, call_text: str, call_node) -> bool:
        """Check if C#/Java call should be flagged."""
        # Don't flag calls that are clearly for side effects
        side_effect_patterns = {
            "Console.Write", "Console.WriteLine", "System.out.print",
            "System.err.print", "printStackTrace", "close()",
            "dispose()", "Dispose()", "flush()", "Flush()"
        }
        
        if any(pattern in call_text for pattern in side_effect_patterns):
            return False
        
        return True

    def _extract_function_name(self, call_text: str) -> Optional[str]:
        """Extract function name from call text (basic heuristic)."""
        # Handle basic patterns like "func()" or "obj.method()"
        if not call_text:
            return None
        
        # Find the opening parenthesis
        paren_pos = call_text.find('(')
        if paren_pos == -1:
            return None
        
        # Get everything before the parenthesis
        before_paren = call_text[:paren_pos].strip()
        
        # Handle member access (obj.method)
        if '.' in before_paren:
            parts = before_paren.split('.')
            return parts[-1] if parts else None
        
        # Handle namespace/module access (ns::func)
        if '::' in before_paren:
            parts = before_paren.split('::')
            return parts[-1] if parts else None
        
        return before_paren

    def _create_finding(self, ctx: RuleContext, node, language: str) -> Optional[Finding]:
        """Create a finding for an ignored return value."""
        # Generate language-specific message and suggestion
        message, suggestion = self._get_message_and_suggestion(language, node, ctx.text)
        
        # Get the span for the call head (callee if available, otherwise the call)
        start_byte, end_byte = self._get_call_head_span(node, language, ctx.text)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning",  # As specified in requirements
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "language": language,
                "call_type": self._identify_call_type(node, language, ctx.text)
            }
        )
        
        return finding

    def _get_call_head_span(self, stmt_node, language: str, file_text: str) -> tuple:
        """Get the byte span for the call head (callee and opening paren)."""
        # Get the call expression from the statement
        meaningful_children = self._get_meaningful_children(stmt_node)
        if not meaningful_children:
            # Fallback to statement span
            return getattr(stmt_node, 'start_byte', 0), getattr(stmt_node, 'end_byte', 0)
        
        call_node = meaningful_children[0]
        
        # Try to get the callee specifically
        if hasattr(call_node, 'children'):
            children = getattr(call_node, 'children', [])
            if children:
                try:
                    # Look for function/callee node
                    for child in children:
                        if hasattr(child, 'type'):
                            child_type = child.type
                            # Common callee types
                            if child_type in {'identifier', 'field_expression', 'member_expression', 
                                            'scoped_identifier', 'qualified_name'}:
                                start_byte = getattr(child, 'start_byte', 0)
                                end_byte = getattr(child, 'end_byte', start_byte + 20)
                                return start_byte, end_byte
                except (TypeError, AttributeError):
                    pass
        
        # Fallback: use the whole call expression but limit size
        start_byte = getattr(call_node, 'start_byte', 0)
        end_byte = getattr(call_node, 'end_byte', start_byte + 50)
        
        # Try to limit to just the function name and opening paren
        if hasattr(call_node, 'start_byte') and hasattr(call_node, 'end_byte'):
            try:
                call_text = file_text[start_byte:end_byte]
                paren_pos = call_text.find('(')
                if paren_pos >= 0:
                    # Include function name and opening paren
                    end_byte = start_byte + paren_pos + 1
            except (IndexError, TypeError):
                pass
        
        return start_byte, min(end_byte, start_byte + 100)

    def _get_message_and_suggestion(self, language: str, node, file_text: str) -> tuple:
        """Generate appropriate message and suggestion for the language."""
        call_type = self._identify_call_type(node, language, file_text)
        
        message = "Ignored return value; handle status/error or explicitly document discard."
        
        suggestion = self._create_refactoring_suggestion(language, call_type)
        
        return message, suggestion

    def _identify_call_type(self, stmt_node, language: str, file_text: str) -> str:
        """Identify the type of call being made."""
        meaningful_children = self._get_meaningful_children(stmt_node)
        if not meaningful_children:
            return "unknown"
        
        call_node = meaningful_children[0]
        call_text = self._get_node_text(call_node, file_text)
        
        if not call_text:
            return "unknown"
        
        # Basic classification
        if '.' in call_text:
            return "method_call"
        elif '::' in call_text:
            return "qualified_call"
        else:
            return "function_call"

    def _create_refactoring_suggestion(self, language: str, call_type: str) -> str:
        """Create language-specific refactoring suggestion."""
        if language in ["c", "cpp"]:
            return self._create_c_cpp_suggestion(call_type)
        elif language == "go":
            return self._create_go_suggestion(call_type)
        elif language == "rust":
            return self._create_rust_suggestion(call_type)
        elif language == "csharp":
            return self._create_csharp_suggestion(call_type)
        elif language == "java":
            return self._create_java_suggestion(call_type)
        else:
            return "Handle the return value appropriately or explicitly discard it."

    def _create_c_cpp_suggestion(self, call_type: str) -> str:
        """Create C/C++-specific refactoring suggestion."""
        return """Function call return value is ignored. Consider one of these approaches:

// Option 1: Assign and check the return value
int result = function_call();
if (result != 0) {
    // Handle error condition
    fprintf(stderr, "Function failed with code: %d\\n", result);
    return -1;
}

// Option 2: Explicitly document that you're ignoring the return value
(void)function_call();  // Explicitly ignore return value

// Option 3: Use the return value directly in a condition
if (function_call() != 0) {
    // Handle error
}

// For C++, consider RAII and exceptions:
try {
    auto result = function_call();
    // Use result...
} catch (const std::exception& e) {
    // Handle exception
}"""

    def _create_go_suggestion(self, call_type: str) -> str:
        """Create Go-specific refactoring suggestion."""
        return """Function call return value is ignored. Consider one of these approaches:

// Option 1: Handle the error explicitly
result, err := functionCall()
if err != nil {
    return fmt.Errorf("function call failed: %w", err)
}
// Use result...

// Option 2: Use blank identifier to explicitly ignore
_ = functionCall()  // Explicitly ignore return value

// Option 3: Handle error inline
if result, err := functionCall(); err != nil {
    log.Printf("Warning: function call failed: %v", err)
} else {
    // Use result...
}

// Option 4: For functions returning only error
if err := functionCall(); err != nil {
    return err
}"""

    def _create_rust_suggestion(self, call_type: str) -> str:
        """Create Rust-specific refactoring suggestion."""
        return """Function call return value is ignored. Consider one of these approaches:

// Option 1: Handle Result/Option explicitly
match function_call() {
    Ok(value) => {
        // Use value...
    }
    Err(error) => {
        eprintln!("Function failed: {}", error);
        return Err(error);
    }
}

// Option 2: Use explicit handling methods
let result = function_call()
    .expect("Function should not fail");
// Or: .unwrap_or_default() or .unwrap_or_else(|_| fallback_value)

// Option 3: Explicitly ignore with let binding
let _ = function_call();  // Explicitly ignore return value

// Option 4: Chain operations
let processed = function_call()
    .map(|value| process(value))
    .unwrap_or_else(|err| {
        eprintln!("Error: {}", err);
        default_value()
    });"""

    def _create_csharp_suggestion(self, call_type: str) -> str:
        """Create C#-specific refactoring suggestion."""
        return """Method call return value is ignored. Consider one of these approaches:

// Option 1: Assign and use the return value
var result = MethodCall();
if (result != null) {
    // Use result...
} else {
    // Handle null/error case
}

// Option 2: Use in conditional directly
if (MethodCall() is var result && result != null) {
    // Use result...
}

// Option 3: For Try* pattern methods
if (int.TryParse(input, out var value)) {
    // Use value...
} else {
    // Handle parse failure
}

// Option 4: Explicit discard (C# 7.0+)
_ = MethodCall();  // Explicitly ignore return value

// Option 5: Handle exceptions properly
try {
    var result = MethodCall();
    // Use result...
} catch (Exception ex) {
    _logger.LogError(ex, "Method call failed");
    throw;
}"""

    def _create_java_suggestion(self, call_type: str) -> str:
        """Create Java-specific refactoring suggestion."""
        return """Method call return value is ignored. Consider one of these approaches:

// Option 1: Assign and check the return value
Integer result = Integer.parseInt(input);
if (result != null) {
    // Use result...
}

// Option 2: Use in conditional or try-catch
try {
    int value = Integer.parseInt(input);
    // Use value...
} catch (NumberFormatException e) {
    logger.error("Failed to parse input: {}", input, e);
    throw new IllegalArgumentException("Invalid input", e);
}

// Option 3: Use Optional for null-safe operations
Optional<String> result = Optional.ofNullable(methodCall());
result.ifPresent(value -> {
    // Use value...
});

// Option 4: Store in variable even if temporarily unused
@SuppressWarnings("unused")
var ignoredResult = methodCall();  // Document why ignored

// Option 5: Use return value in functional style
methodCall()
    .map(this::processValue)
    .orElseThrow(() -> new IllegalStateException("Method failed"));"""


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
except ImportError:
    try:
        from engine.registry import register_rule
    except ImportError:
        # For test execution - registry may not be available
        def register_rule(rule):
            pass

register_rule(ErrorsIgnoredReturnStatusRule())


