# server/rules/errors_broad_catch.py
"""
Rule to detect overly broad exception catching patterns.

This rule analyzes exception handling constructs across multiple languages for:
- Python: bare except:, except Exception, except BaseException
- Java: catch (Exception e), catch (Throwable e)  
- C#: catch (Exception e), untyped catch
- Ruby: rescue Exception (generic rescue catches StandardError but may still be too broad)
- JavaScript/TypeScript: catch (...) without specific error handling

When broad catches are detected, it suggests narrowing to specific exception types
to improve error handling precision and avoid masking unexpected errors.
"""

from typing import Set, Optional, List, Iterator
from engine.types import RuleContext, Finding, RuleMeta, Requires, Rule

class ErrorsBroadCatchRule(Rule):
    """Rule to detect overly broad exception catching patterns."""
    
    meta = RuleMeta(
        id="errors.broad_catch",
        category="errors",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects overly broad exception catching (Exception, Throwable, bare except) and suggests narrowing to specific error types.",
        langs=["python", "java", "csharp", "ruby", "javascript", "typescript"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific broad exception patterns
    BROAD_EXCEPTION_TYPES = {
        "python": {"Exception", "BaseException"},
        "java": {"Exception", "Throwable", "java.lang.Exception", "java.lang.Throwable"},
        "csharp": {"Exception", "System.Exception"},
        "ruby": {"Exception", "StandardError"},  # StandardError is Ruby's general catch-all
        "javascript": set(),  # JS catch is inherently broad
        "typescript": set(),  # TS catch is inherently broad
    }

    # Node types that represent catch/except constructs by language
    CATCH_NODE_TYPES = {
        "python": {"except_clause"},
        "java": {"catch_clause"},
        "csharp": {"catch_clause", "general_catch_clause"},
        "ruby": {"rescue_clause", "rescue"},
        "javascript": {"catch_clause"},
        "typescript": {"catch_clause"},
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and detect broad catch statements."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
        
        # Get catch node types for this language
        catch_types = self.CATCH_NODE_TYPES.get(language, set())
        if not catch_types:
            return

        # Walk the syntax tree looking for catch/except constructs
        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return
            
        for node in self._walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in catch_types:
                if self._is_broad_catch(node, language, ctx.text):
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

    def _is_broad_catch(self, node, language: str, file_text: str) -> bool:
        """Check if a catch/except node represents a broad catch."""
        if language == "python":
            return self._py_is_broad(node, file_text)
        elif language == "java":
            return self._java_is_broad(node, file_text)
        elif language == "csharp":
            return self._cs_is_broad(node, file_text)
        elif language == "ruby":
            return self._rb_is_broad(node, file_text)
        elif language in {"javascript", "typescript"}:
            return self._js_is_broad(node, file_text)
        return False

    def _py_is_broad(self, node, file_text: str) -> bool:
        """Check if Python except clause is broad."""
        # Get the text of the except clause
        try:
            node_text = self._get_node_text(node, file_text)
        except:
            return False
            
        # Bare except: is always broad
        if "except:" in node_text:
            return True
            
        # Check for broad exception types
        broad_types = self.BROAD_EXCEPTION_TYPES["python"]
        for exc_type in broad_types:
            if f"except {exc_type}" in node_text:
                return True
            if f"except({exc_type}" in node_text:  # except(Exception)
                return True
                
        return False

    def _java_is_broad(self, node, file_text: str) -> bool:
        """Check if Java catch clause is broad."""
        try:
            node_text = self._get_node_text(node, file_text)
        except:
            return False
            
        broad_types = self.BROAD_EXCEPTION_TYPES["java"]
        for exc_type in broad_types:
            if f"catch ({exc_type}" in node_text or f"catch({exc_type}" in node_text:
                return True
                
        # Check for multi-catch with broad types (e.g., IOException | Exception)
        if "|" in node_text:
            for exc_type in broad_types:
                if exc_type in node_text:
                    return True
                    
        return False

    def _cs_is_broad(self, node, file_text: str) -> bool:
        """Check if C# catch clause is broad."""
        try:
            node_text = self._get_node_text(node, file_text)
        except:
            return False
            
        # Untyped catch is broad
        if node_text.strip() == "catch":
            return True
            
        broad_types = self.BROAD_EXCEPTION_TYPES["csharp"]
        for exc_type in broad_types:
            if f"catch ({exc_type}" in node_text or f"catch({exc_type}" in node_text:
                return True
                
        return False

    def _rb_is_broad(self, node, file_text: str) -> bool:
        """Check if Ruby rescue clause is broad."""
        try:
            node_text = self._get_node_text(node, file_text)
        except:
            return False
            
        broad_types = self.BROAD_EXCEPTION_TYPES["ruby"]
        for exc_type in broad_types:
            if f"rescue {exc_type}" in node_text:
                return True
                
        # Generic rescue without specific type catches StandardError (may be too broad)
        if node_text.strip() == "rescue":
            return True
            
        return False

    def _js_is_broad(self, node, file_text: str) -> bool:
        """Check if JavaScript/TypeScript catch clause is broad.
        
        In JS/TS, all catch clauses are inherently untyped. We only flag cases where:
        1. The catch block does something significant with the error
        2. But doesn't check the error type or rethrow
        
        We skip:
        - Empty catch blocks (intentional swallowing)
        - Catch blocks that log and rethrow
        - Catch blocks that check error type (instanceof, name, message checks)
        """
        try:
            node_text = self._get_node_text(node, file_text)
        except:
            return False
            
        if "catch" not in node_text:
            return False
            
        # Get the catch body content (after the parameter)
        # node_text looks like: catch (e) { ... }
        body_start = node_text.find('{')
        body_end = node_text.rfind('}')
        if body_start == -1 or body_end == -1:
            return False
        body = node_text[body_start+1:body_end].strip()
        
        # Skip empty catch blocks - often intentional (try-catch for optional operations)
        if not body or body in ['{}', '']:
            return False
            
        # Skip if it has proper error handling patterns
        good_patterns = [
            "throw",           # rethrows
            "console.error",   # logs properly  
            "console.warn",    # logs warning
            "console.log",     # logs (common pattern)
            "logger.",         # uses logger
            "log.",            # logging
            "instanceof",      # type checking
            ".name",           # checking error name
            ".code",           # checking error code
            ".message",        # accessing error message (proper use)
            ".source",         # accessing error source
            ".stack",          # accessing stack trace
            ".response",       # accessing error response (axios pattern)
            "reject(",         # Promise rejection
            "next(",           # Express/Koa error middleware
            "callback(",       # Node.js callback pattern
            "assert.",         # test assertions
            "expect(",         # test expectations
            "should.",         # test assertions (chai)
        ]
        if any(pattern in node_text for pattern in good_patterns):
            return False
            
        # Skip very simple assignment/return patterns (fallback behavior)
        # e.g., catch (e) { actual = null; } or catch (e) { return null; }
        body_lines = [l.strip() for l in body.split('\n') if l.strip()]
        if len(body_lines) <= 2:
            # Simple fallback pattern is okay
            simple_patterns = ['= null', '= false', '= undefined', '= []', '= {}', 'return null', 'return false', 'return;']
            if any(any(p in line for p in simple_patterns) for line in body_lines):
                return False
        
        # If we get here, it's a catch that does something non-trivial but doesn't
        # check error type or use proper logging - this is worth flagging
        return True

    def _get_node_text(self, node, file_text: str) -> str:
        """Extract text content of a node."""
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

    def _create_finding(self, ctx: RuleContext, node, language: str) -> Optional[Finding]:
        """Create a finding for a broad catch."""
        # Generate language-specific message and suggestion
        message, suggestion = self._get_message_and_suggestion(language, node, ctx.text)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=getattr(node, 'start_byte', 0),
            end_byte=getattr(node, 'end_byte', 0),
            severity="warning",
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "language": language,
                "broad_catch_type": self._identify_broad_type(node, language, ctx.text)
            }
        )
        
        return finding

    def _get_message_and_suggestion(self, language: str, node, file_text: str) -> tuple:
        """Generate appropriate message and suggestion for the language."""
        node_text = self._get_node_text(node, file_text)
        broad_type = self._identify_broad_type(node, language, file_text)
        
        if language == "python":
            if "except:" in node_text:
                message = "Bare 'except:' catches everything including KeyboardInterrupt—specify the exception types you expect."
                suggestion = self._create_python_suggestion("bare")
            else:
                message = f"Catching '{broad_type}' is too broad—catch specific exceptions to avoid hiding bugs."
                suggestion = self._create_python_suggestion(broad_type)
                
        elif language == "java":
            message = f"Catching '{broad_type}' is too broad—catch specific exceptions to avoid hiding bugs."
            suggestion = self._create_java_suggestion(broad_type)
            
        elif language == "csharp":
            if "catch" == node_text.strip():
                message = "Untyped 'catch' catches everything—specify exception types for clearer error handling."
                suggestion = self._create_csharp_suggestion("untyped")
            else:
                message = f"Catching '{broad_type}' is too broad—catch specific exceptions to avoid hiding bugs."
                suggestion = self._create_csharp_suggestion(broad_type)
                
        elif language == "ruby":
            if "rescue" == node_text.strip():
                message = "Generic 'rescue' catches StandardError and subclasses. Consider specific error types."
                suggestion = self._create_ruby_suggestion("generic")
            else:
                message = f"Broad rescue of '{broad_type}' may mask unexpected errors. Use specific error types."
                suggestion = self._create_ruby_suggestion(broad_type)
                
        elif language in {"javascript", "typescript"}:
            message = "JavaScript catch is inherently broad. Consider error type checking or immediate rethrow patterns."
            suggestion = self._create_js_suggestion()
            
        else:
            message = "Broad exception catch detected. Consider narrowing to specific exception types."
            suggestion = "Replace with specific exception types appropriate for your use case."
            
        return message, suggestion

    def _identify_broad_type(self, node, language: str, file_text: str) -> str:
        """Identify which broad exception type is being caught."""
        node_text = self._get_node_text(node, file_text)
        
        broad_types = self.BROAD_EXCEPTION_TYPES.get(language, set())
        # Sort by length descending to check longer names first (e.g., "System.Exception" before "Exception")
        sorted_types = sorted(broad_types, key=len, reverse=True)
        for exc_type in sorted_types:
            if exc_type in node_text:
                return exc_type
                
        if language == "python" and "except:" in node_text:
            return "bare_except"
        elif language == "csharp" and node_text.strip() == "catch":
            return "untyped_catch"
        elif language == "ruby" and node_text.strip() == "rescue":
            return "generic_rescue"
        elif language in {"javascript", "typescript"}:
            return "js_catch"
            
        return "unknown"

    def _create_python_suggestion(self, broad_type: str) -> str:
        """Create Python-specific refactoring suggestion."""
        if broad_type == "bare":
            return """Replace bare 'except:' with specific exception types:

# Instead of:
try:
    risky_operation()
except:
    handle_error()

# Use:
try:
    risky_operation()
except (ValueError, TypeError) as e:
    handle_error(e)
except IOError as e:
    handle_io_error(e)"""
        else:
            return f"""Replace broad '{broad_type}' with specific exception types:

# Instead of:
try:
    risky_operation()
except {broad_type} as e:
    handle_error(e)

# Use:
try:
    risky_operation()
except ValueError as e:
    handle_value_error(e)
except IOError as e:
    handle_io_error(e)"""

    def _create_java_suggestion(self, broad_type: str) -> str:
        """Create Java-specific refactoring suggestion."""
        return f"""Replace broad '{broad_type}' with specific exception types:

// Instead of:
try {{
    riskyOperation();
}} catch ({broad_type} e) {{
    handleError(e);
}}

// Use:
try {{
    riskyOperation();
}} catch (IOException e) {{
    handleIOError(e);
}} catch (IllegalArgumentException e) {{
    handleInvalidArgument(e);
}}"""

    def _create_csharp_suggestion(self, broad_type: str) -> str:
        """Create C#-specific refactoring suggestion."""
        if broad_type == "untyped":
            return """Add specific exception types to catch clause:

// Instead of:
try
{
    RiskyOperation();
}
catch
{
    HandleError();
}

// Use:
try
{
    RiskyOperation();
}
catch (ArgumentException ex)
{
    HandleArgumentError(ex);
}
catch (IOException ex)
{
    HandleIOError(ex);
}"""
        else:
            return f"""Replace broad '{broad_type}' with specific exception types:

// Instead of:
try
{{
    RiskyOperation();
}}
catch ({broad_type} ex)
{{
    HandleError(ex);
}}

// Use:
try
{{
    RiskyOperation();
}}
catch (ArgumentException ex)
{{
    HandleArgumentError(ex);
}}
catch (IOException ex)
{{
    HandleIOError(ex);
}}"""

    def _create_ruby_suggestion(self, broad_type: str) -> str:
        """Create Ruby-specific refactoring suggestion."""
        if broad_type == "generic":
            return """Specify exception types in rescue clause:

# Instead of:
begin
  risky_operation
rescue
  handle_error
end

# Use:
begin
  risky_operation
rescue ArgumentError => e
  handle_argument_error(e)
rescue IOError => e
  handle_io_error(e)
end"""
        else:
            return f"""Replace broad '{broad_type}' with specific error types:

# Instead of:
begin
  risky_operation
rescue {broad_type} => e
  handle_error(e)
end

# Use:
begin
  risky_operation
rescue ArgumentError => e
  handle_argument_error(e)
rescue IOError => e
  handle_io_error(e)
end"""

    def _create_js_suggestion(self) -> str:
        """Create JavaScript/TypeScript-specific refactoring suggestion."""
        return """Consider error type checking or structured error handling:

// Instead of:
try {
    riskyOperation();
} catch (error) {
    handleError(error);
}

// Use error type checking:
try {
    riskyOperation();
} catch (error) {
    if (error instanceof TypeError) {
        handleTypeError(error);
    } else if (error instanceof RangeError) {
        handleRangeError(error);
    } else {
        // Re-throw unexpected errors
        throw error;
    }
}

// Or use structured errors:
try {
    riskyOperation();
} catch (error) {
    if (error.code === 'VALIDATION_ERROR') {
        handleValidationError(error);
    } else {
        throw error; // Re-throw unexpected errors
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

register_rule(ErrorsBroadCatchRule())


