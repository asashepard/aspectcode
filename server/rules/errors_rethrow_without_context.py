# server/rules/errors_rethrow_without_context.py
"""
Rule to detect exception handlers that immediately rethrow without adding context.

This rule analyzes exception handling constructs across multiple languages for:
- Python: except handlers with bare "raise" or "raise e" as the only statement
- Java: catch handlers with "throw e;" as the only statement  
- C#: catch handlers with "throw;" or "throw e;" as the only statement

When redundant rethrows are detected, it suggests either enriching the error context
with logging/wrapping or removing the redundant catch block entirely.
"""

from typing import Set, Optional, List
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsRethrowWithoutContextRule:
    """Rule to detect exception handlers that rethrow without adding context."""
    
    meta = RuleMeta(
        id="errors.rethrow_without_context",
        category="errors",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects catch/except handlers that immediately rethrow without adding context or enrichment.",
        langs=["python", "java", "csharp"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific catch/except node types
    CATCH_NODE_TYPES = {
        "python": {"except_clause"},
        "java": {"catch_clause"},
        "csharp": {"catch_clause", "general_catch_clause"},
    }

    # Language-specific rethrow statement types
    RETHROW_STATEMENT_TYPES = {
        "python": {"raise_statement"},
        "java": {"throw_statement"},
        "csharp": {"throw_statement"},
    }

    # Non-meaningful statement types that should be ignored
    TRIVIAL_STATEMENT_TYPES = {
        "comment", "whitespace", "line_comment", "block_comment", 
        "newline", "indent", "dedent"
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for redundant rethrows."""
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
                if self._is_immediate_rethrow(node, language, ctx.text):
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

    def _is_immediate_rethrow(self, node, language: str, file_text: str) -> bool:
        """Check if a catch/except handler contains only an immediate rethrow."""
        body = self._get_handler_body(node, language)
        if not body:
            return False
        
        # Get all meaningful statements (non-trivial)
        meaningful_stmts = self._get_meaningful_statements(body, language)
        
        # Must have exactly one meaningful statement
        if len(meaningful_stmts) != 1:
            return False
        
        first_stmt = meaningful_stmts[0]
        
        # Check if it's a rethrow statement for this language
        return self._is_rethrow_statement(first_stmt, language, file_text)

    def _get_handler_body(self, node, language: str):
        """Get the body/block of a catch/except handler."""
        # Try different attributes that might contain the handler body
        body_attrs = ['body', 'block', 'suite', 'statements', 'compound_statement']
        
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

    def _get_meaningful_statements(self, body, language: str) -> List:
        """Extract meaningful statements from handler body, excluding trivial ones."""
        if not body:
            return []
        
        statements = []
        
        # Get children if available
        if hasattr(body, 'children'):
            children = getattr(body, 'children', [])
            if children:
                try:
                    for child in children:
                        if hasattr(child, 'type'):
                            # Skip trivial statements
                            if child.type not in self.TRIVIAL_STATEMENT_TYPES:
                                statements.append(child)
                except (TypeError, AttributeError):
                    pass
        
        return statements

    def _is_rethrow_statement(self, stmt, language: str, file_text: str) -> bool:
        """Check if a statement is a bare rethrow for the given language."""
        if not hasattr(stmt, 'type'):
            return False
        
        stmt_type = stmt.type
        rethrow_types = self.RETHROW_STATEMENT_TYPES.get(language, set())
        
        if stmt_type not in rethrow_types:
            return False
        
        # Get the statement text to analyze the pattern
        stmt_text = self._get_statement_text(stmt, file_text)
        if not stmt_text:
            return False
        
        # Language-specific rethrow patterns
        if language == "python":
            return self._is_python_bare_rethrow(stmt_text)
        elif language == "java":
            return self._is_java_bare_rethrow(stmt_text)
        elif language == "csharp":
            return self._is_csharp_bare_rethrow(stmt_text)
        
        return False

    def _get_statement_text(self, stmt, file_text: str) -> str:
        """Extract text content of a statement."""
        if not stmt:
            return ""
        
        # First try to get text from the node itself (for mock objects)
        if hasattr(stmt, 'text'):
            text = stmt.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Otherwise extract from file text using byte positions
        if hasattr(stmt, 'start_byte') and hasattr(stmt, 'end_byte'):
            try:
                return file_text[stmt.start_byte:stmt.end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""

    def _is_python_bare_rethrow(self, stmt_text: str) -> bool:
        """Check if Python statement is a bare rethrow."""
        # Remove whitespace and normalize
        text = stmt_text.strip()
        
        # Bare raise statement
        if text == "raise":
            return True
        
        # Raise with the caught exception variable (still considered bare)
        # Pattern: "raise e" or "raise exception" etc.
        if text.startswith("raise ") and len(text.split()) == 2:
            # Check that it's not creating a new exception or adding context
            var_name = text.split()[1]
            # Simple variable name (not function call, not new exception)
            if var_name.isidentifier():
                return True
        
        return False

    def _is_java_bare_rethrow(self, stmt_text: str) -> bool:
        """Check if Java statement is a bare rethrow."""
        # Remove whitespace and normalize
        text = stmt_text.strip()
        
        # Pattern: "throw e;" or "throw exception;"
        if text.startswith("throw ") and text.endswith(";"):
            # Extract what's being thrown
            thrown_part = text[6:-1].strip()  # Remove "throw " and ";"
            
            # Check if it's just a variable name (not a new exception)
            if thrown_part.isidentifier():
                return True
            
            # Also check for simple field access like "this.e"
            if "." in thrown_part:
                parts = thrown_part.split(".")
                if len(parts) == 2 and all(part.isidentifier() for part in parts):
                    return True
        
        return False

    def _is_csharp_bare_rethrow(self, stmt_text: str) -> bool:
        """Check if C# statement is a bare rethrow."""
        # Remove whitespace and normalize
        text = stmt_text.strip()
        
        # Bare throw (preserves stack trace)
        if text == "throw;":
            return True
        
        # Throw with variable (loses stack trace info but still bare)
        if text.startswith("throw ") and text.endswith(";"):
            # Extract what's being thrown
            thrown_part = text[6:-1].strip()  # Remove "throw " and ";"
            
            # Check if it's just a variable name (not a new exception)
            if thrown_part.isidentifier():
                return True
        
        return False

    def _create_finding(self, ctx: RuleContext, node, language: str) -> Optional[Finding]:
        """Create a finding for a redundant rethrow."""
        # Generate language-specific message and suggestion
        message, suggestion = self._get_message_and_suggestion(language, node, ctx.text)
        
        # Get the span for the catch header (not the whole body)
        start_byte, end_byte = self._get_header_span(node, language, ctx.text)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="info",  # As specified in requirements
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "language": language,
                "rethrow_type": self._identify_rethrow_type(node, language, ctx.text)
            }
        )
        
        return finding

    def _get_header_span(self, node, language: str, file_text: str) -> tuple:
        """Get the byte span for the catch/except header."""
        # For the header, we want to span from the start of the catch/except
        # to the end of the header (before the body)
        
        start_byte = getattr(node, 'start_byte', 0)
        
        # Try to find the end of the header
        if hasattr(node, 'children'):
            children = getattr(node, 'children', [])
            if children:
                try:
                    # Look for the body and use its start as the end of header
                    body_types = {'block', 'suite', 'compound_statement', 'statement_block', 'body'}
                    for child in children:
                        if hasattr(child, 'type') and child.type in body_types:
                            # Header ends just before the body
                            return start_byte, getattr(child, 'start_byte', start_byte + 50)
                    
                    # If no body found, use the last non-body child's end
                    if len(children) > 1:
                        header_end = getattr(children[-2], 'end_byte', start_byte + 50)
                        return start_byte, header_end
                except (TypeError, AttributeError):
                    pass
        
        # Fallback: use the whole node or estimate header size
        end_byte = getattr(node, 'end_byte', start_byte + 50)
        
        # For estimate, try to find the colon (Python) or opening brace (Java/C#)
        if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            try:
                node_text = file_text[start_byte:end_byte]
                if language == "python":
                    colon_pos = node_text.find(':')
                    if colon_pos >= 0:
                        return start_byte, start_byte + colon_pos + 1
                else:  # Java, C#
                    brace_pos = node_text.find('{')
                    if brace_pos >= 0:
                        return start_byte, start_byte + brace_pos
            except (IndexError, TypeError):
                pass
        
        return start_byte, min(end_byte, start_byte + 100)

    def _get_message_and_suggestion(self, language: str, node, file_text: str) -> tuple:
        """Generate appropriate message and suggestion for the language."""
        rethrow_type = self._identify_rethrow_type(node, language, file_text)
        
        message = "Rethrow without added context; consider enriching the message/metadata or removing the catch."
        
        suggestion = self._create_refactoring_suggestion(language, rethrow_type)
        
        return message, suggestion

    def _identify_rethrow_type(self, node, language: str, file_text: str) -> str:
        """Identify the type of bare rethrow."""
        body = self._get_handler_body(node, language)
        if not body:
            return "unknown"
        
        statements = self._get_meaningful_statements(body, language)
        if not statements:
            return "unknown"
        
        stmt_text = self._get_statement_text(statements[0], file_text)
        
        if language == "python":
            if stmt_text.strip() == "raise":
                return "bare_raise"
            elif stmt_text.strip().startswith("raise "):
                return "raise_variable"
        elif language == "java":
            return "throw_variable"
        elif language == "csharp":
            if stmt_text.strip() == "throw;":
                return "bare_throw"
            elif stmt_text.strip().startswith("throw "):
                return "throw_variable"
        
        return "unknown"

    def _create_refactoring_suggestion(self, language: str, rethrow_type: str) -> str:
        """Create language-specific refactoring suggestion."""
        if language == "python":
            return self._create_python_suggestion(rethrow_type)
        elif language == "java":
            return self._create_java_suggestion(rethrow_type)
        elif language == "csharp":
            return self._create_csharp_suggestion(rethrow_type)
        else:
            return "Add proper error handling context or remove redundant catch block."

    def _create_python_suggestion(self, rethrow_type: str) -> str:
        """Create Python-specific refactoring suggestion."""
        return """Redundant exception handler detected. Consider one of these approaches:

# Option 1: Add logging or context before rethrowing
try:
    risky_operation()
except ValueError as e:
    logger.error("Operation failed in context X: %s", e)
    raise  # Preserves original traceback

# Option 2: Wrap with more specific context
try:
    risky_operation()
except ValueError as e:
    raise RuntimeError(f"Failed to process data: {e}") from e

# Option 3: Remove redundant catch (if no specific handling needed)
try:
    risky_operation()
# Remove the except block entirely if not adding value

# Option 4: Let the exception propagate naturally
risky_operation()  # No try/catch if not handling the error"""

    def _create_java_suggestion(self, rethrow_type: str) -> str:
        """Create Java-specific refactoring suggestion."""
        return """Redundant exception handler detected. Consider one of these approaches:

// Option 1: Add logging or context before rethrowing
try {
    riskyOperation();
} catch (IOException e) {
    logger.error("Operation failed in context X: {}", e.getMessage(), e);
    throw e;  // Or just 'throw;' in some contexts
}

// Option 2: Wrap with more specific context
try {
    riskyOperation();
} catch (IOException e) {
    throw new RuntimeException("Failed to process data", e);
}

// Option 3: Remove redundant catch (if no specific handling needed)
try {
    riskyOperation();
}
// Remove the catch block entirely if not adding value

// Option 4: Let the exception propagate naturally
riskyOperation();  // No try/catch if not handling the error"""

    def _create_csharp_suggestion(self, rethrow_type: str) -> str:
        """Create C#-specific refactoring suggestion."""
        return """Redundant exception handler detected. Consider one of these approaches:

// Option 1: Add logging or context before rethrowing
try
{
    RiskyOperation();
}
catch (IOException ex)
{
    _logger.LogError(ex, "Operation failed in context X: {Message}", ex.Message);
    throw;  // Preserves stack trace
}

// Option 2: Wrap with more specific context
try
{
    RiskyOperation();
}
catch (IOException ex)
{
    throw new InvalidOperationException("Failed to process data", ex);
}

// Option 3: Remove redundant catch (if no specific handling needed)
try
{
    RiskyOperation();
}
// Remove the catch block entirely if not adding value

// Option 4: Let the exception propagate naturally
RiskyOperation();  // No try/catch if not handling the error"""


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

register_rule(ErrorsRethrowWithoutContextRule())


