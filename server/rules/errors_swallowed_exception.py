# server/rules/errors_swallowed_exception.py
"""
Rule to detect swallowed exceptions in catch/except handlers.

This rule analyzes exception handling constructs across multiple languages for:
- Empty catch/except blocks
- Handlers that neither rethrow nor log context
- Handlers with only trivial statements (pass, TODO comments, etc.)

When swallowed exceptions are detected, it suggests adding proper error handling
through rethrowing or logging with context to avoid masking errors.
"""

from typing import Set, Optional, List, Tuple
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsSwallowedExceptionRule:
    """Rule to detect swallowed exceptions in catch/except handlers."""
    
    meta = RuleMeta(
        id="errors.swallowed_exception",
        category="errors",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects empty catch/except handlers or those that neither rethrow nor log context.",
        langs=["python", "java", "csharp", "ruby", "javascript", "typescript"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific catch/except node types
    CATCH_NODE_TYPES = {
        "python": {"except_clause"},
        "java": {"catch_clause"},
        "csharp": {"catch_clause", "general_catch_clause"},
        "ruby": {"rescue_clause", "rescue"},
        "javascript": {"catch_clause"},
        "typescript": {"catch_clause"},
    }

    # Keywords that indicate proper error handling (non-swallowing)
    RETHROW_LOG_KEYWORDS = {
        "python": ["raise", "logging.", "logger.", "log.", "print(", "return "],
        "java": ["throw", "log.", "logger.", "System.err.", "System.out.println", "LOG.", "LOGGER.", "return "],
        "csharp": ["throw", "Log.", "logger.", "Console.Error", "Console.WriteLine", "_log.", "_logger.", "return "],
        "ruby": ["raise", "logger.", "Rails.logger", "warn", "puts", "p ", "return "],
        # Node.js callback patterns: fn(err), callback(err), cb(err), done(err), next(err)
        # Also: error variable assignment for later handling (err = e, error = e)
        "javascript": ["throw", "console.", "logger.", "log(", "error(", "return ", "reject(", "Promise.reject", 
                       "callback(", "fn(", "cb(", "done(", "next(", "(err)", "(error)",
                       "err = ", "error = ", "err=", "error="],
        "typescript": ["throw", "console.", "logger.", "log(", "error(", "return ", "reject(", "Promise.reject",
                       "callback(", "fn(", "cb(", "done(", "next(", "(err)", "(error)",
                       "err = ", "error = ", "err=", "error="],
    }
    
    # Comments that indicate intentional error handling (suppress false positives)
    INTENTIONAL_HANDLING_PATTERNS = [
        "handled by",  # "error is handled by useAuth hook"
        "intentionally",  # "intentionally ignored"
        "expected",  # "expected error" 
        "ignore",  # "we ignore this error"
        "fallback",  # "fallback to default"
        "retry",  # "will be retried"
        "suppress",  # "suppress this error"
        "silently",  # "silently fail"
        "graceful",  # "graceful degradation"
    ]

    # Trivial statements that indicate swallowed exceptions
    TRIVIAL_STATEMENTS = {
        "python": ["pass", "# TODO", "# FIXME", "# XXX"],
        "java": [";", "// TODO", "// FIXME", "/* TODO"],
        "csharp": [";", "// TODO", "// FIXME", "/* TODO"],
        "ruby": ["# TODO", "# FIXME", "# XXX"],
        "javascript": [";", "// TODO", "// FIXME", "/* TODO"],
        "typescript": [";", "// TODO", "// FIXME", "/* TODO"],
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for swallowed exceptions."""
        language = ctx.adapter.language_id
        
        # Skip unsupported languages
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get catch node types for this language
        catch_types = self.CATCH_NODE_TYPES.get(language, set())
        if not catch_types:
            return

        # Walk the syntax tree looking for catch/except constructs
        for node in ctx.walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in catch_types:
                if self._is_swallowed(node, language, ctx.text):
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

    def _is_swallowed(self, node, language: str, file_text: str) -> bool:
        """Check if a catch/except handler swallows exceptions."""
        # Get the handler body
        body = self._get_handler_body(node, language)
        if not body:
            return True  # No body means empty handler
        
        # Get the text content of the handler body
        body_text = self._get_body_text(body, file_text)
        if not body_text or not body_text.strip():
            return True  # Empty or whitespace-only body
        
        body_lower = body_text.lower()
        
        # Check for comments that explain intentional handling (not a swallowed exception)
        for pattern in self.INTENTIONAL_HANDLING_PATTERNS:
            if pattern in body_lower:
                return False  # Developer has documented why this is handled this way
        
        # Check for rethrow/logging keywords
        keywords = self.RETHROW_LOG_KEYWORDS.get(language, [])
        if any(keyword in body_text for keyword in keywords):
            return False  # Found rethrow or logging - not swallowed
        
        # Check for trivial statements only
        trivial = self.TRIVIAL_STATEMENTS.get(language, [])
        body_clean = body_text.strip()
        
        # If body contains only trivial statements, it's swallowed
        if trivial and any(stmt in body_clean for stmt in trivial):
            # Check if it's ONLY trivial statements (no other meaningful code)
            lines = [line.strip() for line in body_clean.split('\n') if line.strip()]
            if all(any(stmt in line for stmt in trivial) for line in lines):
                return True
        
        # For very short bodies that don't contain error handling keywords, consider swallowed
        if len(body_clean) < 20 and not any(keyword in body_text for keyword in keywords):
            return True
            
        # Default: if no clear error handling detected, consider swallowed
        return True

    def _get_handler_body(self, node, language: str):
        """Get the body/block of a catch/except handler."""
        # Try different attributes that might contain the handler body
        body_attrs = ['body', 'block', 'suite', 'statements']
        
        for attr in body_attrs:
            if hasattr(node, attr):
                body = getattr(node, attr)
                if body is not None:
                    return body
        
        # Fallback: look for a child that might be the body
        if hasattr(node, 'children'):
            children = getattr(node, 'children', [])
            if children:
                try:
                    # Look for common body node types
                    body_types = {'block', 'suite', 'compound_statement', 'statement_block'}
                    for child in children:
                        if hasattr(child, 'type') and child.type in body_types:
                            return child
                    
                    # If no specific body type found, use the last child (common pattern)
                    if len(children) > 1:
                        return children[-1]
                except (TypeError, AttributeError):
                    pass
        
        return None

    def _get_body_text(self, body, file_text: str) -> str:
        """Extract text content of a handler body."""
        if not body:
            return ""
        
        # First try to get text from the node itself (for mock objects)
        if hasattr(body, 'text'):
            text = body.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Otherwise extract from file text using byte positions
        if hasattr(body, 'start_byte') and hasattr(body, 'end_byte'):
            try:
                return file_text[body.start_byte:body.end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""

    def _create_finding(self, ctx: RuleContext, node, language: str) -> Optional[Finding]:
        """Create a finding for a swallowed exception."""
        # Generate language-specific message and suggestion
        message, suggestion = self._get_message_and_suggestion(language, node, ctx.text)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=getattr(node, 'start_byte', 0),
            end_byte=getattr(node, 'end_byte', 0),
            severity="error",
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "language": language,
                "handler_type": self._identify_handler_type(node, language, ctx.text)
            }
        )
        
        return finding

    def _get_message_and_suggestion(self, language: str, node, file_text: str) -> tuple:
        """Generate appropriate message and suggestion for the language."""
        handler_type = self._identify_handler_type(node, language, file_text)
        
        if handler_type == "empty":
            message = "Exception caught but ignored\u2014errors will fail silently. Log or re-raise."
        elif handler_type == "trivial":
            message = "Exception caught but only contains pass/TODO\u2014errors will fail silently. Add proper handling."
        else:
            message = "Exception caught without logging or re-raising\u2014this hides errors."
        
        suggestion = self._create_refactoring_suggestion(language, handler_type)
        
        return message, suggestion

    def _identify_handler_type(self, node, language: str, file_text: str) -> str:
        """Identify the type of swallowed exception handler."""
        body = self._get_handler_body(node, language)
        if not body:
            return "empty"
        
        body_text = self._get_body_text(body, file_text)
        if not body_text or not body_text.strip():
            return "empty"
        
        trivial = self.TRIVIAL_STATEMENTS.get(language, [])
        if trivial and any(stmt in body_text for stmt in trivial):
            return "trivial"
        
        return "no_handling"

    def _create_refactoring_suggestion(self, language: str, handler_type: str) -> str:
        """Create language-specific refactoring suggestion."""
        if language == "python":
            return self._create_python_suggestion(handler_type)
        elif language == "java":
            return self._create_java_suggestion(handler_type)
        elif language == "csharp":
            return self._create_csharp_suggestion(handler_type)
        elif language == "ruby":
            return self._create_ruby_suggestion(handler_type)
        elif language in {"javascript", "typescript"}:
            return self._create_js_suggestion(handler_type)
        else:
            return "Add proper error handling: either rethrow the exception or log it with context."

    def _create_python_suggestion(self, handler_type: str) -> str:
        """Create Python-specific refactoring suggestion."""
        if handler_type == "empty":
            return """Empty exception handler silently swallows errors. Add proper handling:

# Option 1: Re-raise the exception
try:
    risky_operation()
except SpecificException as e:
    # Log the error with context
    logging.error("Operation failed: %s", e)
    raise  # Re-raise to propagate the error

# Option 2: Log and handle gracefully (only if appropriate)
try:
    risky_operation()
except SpecificException as e:
    logging.warning("Operation failed, using default: %s", e)
    return default_value

# Option 3: Wrap and re-raise with more context
try:
    risky_operation()
except SpecificException as e:
    raise CustomError(f"Failed to perform operation: {e}") from e"""
        else:
            return """Replace trivial handler with proper error handling:

# Instead of:
try:
    risky_operation()
except Exception:
    pass  # Bad: silently swallows errors

# Use one of these patterns:
try:
    risky_operation()
except SpecificException as e:
    logging.error("Operation failed: %s", e)
    raise  # Re-raise if caller should handle it

# Or if you need to continue:
try:
    risky_operation()
except SpecificException as e:
    logging.warning("Operation failed, continuing: %s", e)
    # Handle the error appropriately"""

    def _create_java_suggestion(self, handler_type: str) -> str:
        """Create Java-specific refactoring suggestion."""
        return """Add proper error handling to avoid swallowing exceptions:

// Option 1: Re-throw the exception
try {
    riskyOperation();
} catch (SpecificException e) {
    logger.error("Operation failed: {}", e.getMessage(), e);
    throw e;  // Re-throw to propagate
}

// Option 2: Wrap and re-throw with more context
try {
    riskyOperation();
} catch (SpecificException e) {
    throw new RuntimeException("Failed to perform operation", e);
}

// Option 3: Log and handle gracefully (only if appropriate)
try {
    riskyOperation();
} catch (SpecificException e) {
    logger.warn("Operation failed, using default: {}", e.getMessage(), e);
    return defaultValue;
}"""

    def _create_csharp_suggestion(self, handler_type: str) -> str:
        """Create C#-specific refactoring suggestion."""
        return """Add proper error handling to avoid swallowing exceptions:

// Option 1: Re-throw the exception
try
{
    RiskyOperation();
}
catch (SpecificException ex)
{
    _logger.LogError(ex, "Operation failed: {Message}", ex.Message);
    throw;  // Re-throw to propagate
}

// Option 2: Wrap and re-throw with more context
try
{
    RiskyOperation();
}
catch (SpecificException ex)
{
    throw new InvalidOperationException("Failed to perform operation", ex);
}

// Option 3: Log and handle gracefully (only if appropriate)
try
{
    RiskyOperation();
}
catch (SpecificException ex)
{
    _logger.LogWarning(ex, "Operation failed, using default: {Message}", ex.Message);
    return defaultValue;
}"""

    def _create_ruby_suggestion(self, handler_type: str) -> str:
        """Create Ruby-specific refactoring suggestion."""
        return """Add proper error handling to avoid swallowing exceptions:

# Option 1: Re-raise the exception
begin
  risky_operation
rescue SpecificError => e
  logger.error "Operation failed: #{e.message}"
  logger.error e.backtrace.join("\n")
  raise  # Re-raise to propagate the error
end

# Option 2: Wrap and re-raise with more context
begin
  risky_operation
rescue SpecificError => e
  raise CustomError, "Failed to perform operation: #{e.message}"
end

# Option 3: Log and handle gracefully (only if appropriate)
begin
  risky_operation
rescue SpecificError => e
  logger.warn "Operation failed, using default: #{e.message}"
  return default_value
end"""

    def _create_js_suggestion(self, handler_type: str) -> str:
        """Create JavaScript/TypeScript-specific refactoring suggestion."""
        return """Add proper error handling to avoid swallowing exceptions:

// Option 1: Re-throw the exception
try {
    riskyOperation();
} catch (error) {
    console.error('Operation failed:', error);
    throw error;  // Re-throw to propagate
}

// Option 2: Wrap and re-throw with more context
try {
    riskyOperation();
} catch (error) {
    throw new Error(`Failed to perform operation: ${error.message}`);
}

// Option 3: Log and handle gracefully (only if appropriate)
try {
    riskyOperation();
} catch (error) {
    console.warn('Operation failed, using default:', error);
    return defaultValue;
}

// Option 4: Use async/await error handling
async function example() {
    try {
        await riskyAsyncOperation();
    } catch (error) {
        logger.error('Async operation failed:', error);
        throw error;  // Let caller decide how to handle
    }
}"""


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

register_rule(ErrorsSwallowedExceptionRule())


