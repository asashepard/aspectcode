# server/rules/errors_multiple_catch_order_issue.py
"""
Rule to detect unreachable catch blocks due to improper exception ordering.

This rule analyzes try-catch sequences across multiple languages for:
- Java: catch blocks where broader exceptions are caught before specific ones
- C#: catch blocks where broader exceptions are caught before specific ones

When broader exception types (Exception, Throwable) are placed before more specific
types (IOException, ArgumentException), the specific handlers become unreachable.
"""

from typing import Set, Optional, List
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsMultipleCatchOrderIssueRule:
    """Rule to detect unreachable catch blocks due to improper exception ordering."""
    
    meta = RuleMeta(
        id="errors.multiple_catch_order_issue",
        category="errors",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects unreachable catch blocks when broader exception types are placed before specific ones.",
        langs=["java", "csharp"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific try statement node types
    TRY_STATEMENT_TYPES = {
        "java": {"try_statement", "try_with_resources_statement"},
        "csharp": {"try_statement"},
    }

    # Language-specific catch clause node types
    CATCH_CLAUSE_TYPES = {
        "java": {"catch_clause"},
        "csharp": {"catch_clause"},
    }

    # Broad exception types that catch most other exceptions
    BROAD_EXCEPTION_TYPES = {
        "java": {"Exception", "Throwable", "java.lang.Exception", "java.lang.Throwable"},
        "csharp": {"Exception", "System.Exception"},
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for catch block ordering issues."""
        language = ctx.adapter.language_id
        
        # Skip unsupported languages
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get try statement types for this language
        try_types = self.TRY_STATEMENT_TYPES.get(language, set())
        if not try_types:
            return

        # Walk the syntax tree looking for try statements
        for node in ctx.walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in try_types:
                # Analyze catch blocks in this try statement
                yield from self._analyze_catch_blocks(ctx, node, language)

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

    def _analyze_catch_blocks(self, ctx: RuleContext, try_node, language: str):
        """Analyze catch blocks for ordering issues."""
        catch_types = self.CATCH_CLAUSE_TYPES.get(language, set())
        if not catch_types:
            return

        # Find all catch clauses in this try statement
        catch_clauses = []
        for child in self._get_children(try_node):
            if hasattr(child, 'type') and child.type in catch_types:
                catch_clauses.append(child)

        # Need at least 2 catch clauses to have ordering issues
        if len(catch_clauses) < 2:
            return

        # Track seen exception types and broad types
        seen_types = set()
        seen_broad = False
        
        for idx, catch_clause in enumerate(catch_clauses):
            # Extract exception types from this catch clause
            exception_types = self._extract_catch_types(catch_clause, language, ctx.text)
            
            # Check if this catch is unreachable
            if self._is_unreachable(exception_types, seen_types, seen_broad, language):
                finding = self._create_finding(ctx, catch_clause, exception_types, language)
                if finding:
                    yield finding
            
            # Update tracking sets
            normalized_types = {self._normalize_type(t, language) for t in exception_types}
            seen_types.update(normalized_types)
            
            # Check if any of these types are broad
            if any(self._is_broad_type(t, language) for t in normalized_types):
                seen_broad = True

    def _get_children(self, node):
        """Get children of a node, handling different tree-sitter implementations."""
        if not node:
            return []
        
        children = getattr(node, 'children', [])
        if children:
            try:
                return list(children)
            except (TypeError, AttributeError):
                return []
        return []

    def _extract_catch_types(self, catch_clause, language: str, file_text: str) -> List[str]:
        """Extract exception type names from a catch clause."""
        # Get the catch header (the part with the exception declaration)
        catch_header = self._find_catch_header(catch_clause)
        if not catch_header:
            return []

        # Extract text from the header
        header_text = self._extract_node_text(catch_header, file_text)
        if not header_text:
            return []

        # Parse exception types from the header text
        return self._parse_exception_types(header_text, language)

    def _find_catch_header(self, catch_clause):
        """Find the catch header node within a catch clause."""
        # Look for common catch header node types
        header_types = {
            "catch_formal_parameter", "catch_parameters", "parameter_list",
            "formal_parameters", "catch_declaration", "exception_declaration"
        }
        
        for child in self._get_children(catch_clause):
            if hasattr(child, 'type') and child.type in header_types:
                return child
        
        # If no specific header found, use the catch clause itself
        return catch_clause

    def _extract_node_text(self, node, file_text: str) -> str:
        """Extract text content from a node."""
        if not node or not file_text:
            return ""
        
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte)
        
        # For mock objects in tests, try to extract from the mock structure
        if hasattr(node, 'text') and node.text:
            return node.text
        
        if start_byte >= 0 and end_byte > start_byte:
            try:
                # Handle both string and bytes
                if isinstance(file_text, str):
                    file_bytes = file_text.encode('utf-8')
                else:
                    file_bytes = file_text
                
                if end_byte <= len(file_bytes):
                    return file_bytes[start_byte:end_byte].decode('utf-8')
            except (UnicodeDecodeError, IndexError):
                pass
        
        return ""

    def _parse_exception_types(self, header_text: str, language: str) -> List[str]:
        """Parse exception type names from catch header text."""
        if not header_text:
            return []

        # Remove catch keyword and parentheses
        header_text = header_text.strip()
        for prefix in ["catch", "("]:
            if header_text.startswith(prefix):
                header_text = header_text[len(prefix):].strip()
        if header_text.endswith(")"):
            header_text = header_text[:-1].strip()

        # Handle Java multi-catch (Type1 | Type2 | Type3 variable)
        if language == "java" and "|" in header_text:
            # Split by | and extract types
            parts = [part.strip() for part in header_text.split("|")]
            types = []
            for i, part in enumerate(parts):
                if i == len(parts) - 1:
                    # Last part may have variable name
                    tokens = part.split()
                    if tokens:
                        types.append(tokens[0])
                else:
                    # Middle parts should just be type names
                    if part:
                        types.append(part)
            return [t for t in types if t]

        # Handle single catch (Type variable) or (Type variable when condition)
        tokens = header_text.split()
        if not tokens:
            return []

        # Remove modifiers and get the type
        filtered_tokens = []
        for token in tokens:
            # Skip modifiers and keywords
            if token not in {"final", "ref", "out", "when"}:
                filtered_tokens.append(token)

        if filtered_tokens:
            # First non-modifier token should be the exception type
            return [filtered_tokens[0]]

        return []

    def _normalize_type(self, type_name: str, language: str) -> str:
        """Normalize exception type name by removing common package prefixes."""
        if not type_name:
            return type_name

        # Remove common Java package prefixes
        if language == "java":
            if type_name.startswith("java.lang."):
                return type_name[10:]  # Remove "java.lang."
            if type_name.startswith("java.io."):
                return type_name[8:]   # Remove "java.io."
            if type_name.startswith("java.util."):
                return type_name[11:]  # Remove "java.util."

        # Remove common C# namespace prefixes
        if language == "csharp":
            if type_name.startswith("System."):
                return type_name[7:]   # Remove "System."

        return type_name

    def _is_broad_type(self, type_name: str, language: str) -> bool:
        """Check if an exception type is considered broad."""
        normalized = self._normalize_type(type_name, language)
        broad_types = self.BROAD_EXCEPTION_TYPES.get(language, set())
        
        # Check both original and normalized names
        return type_name in broad_types or normalized in {"Exception", "Throwable"}

    def _is_unreachable(self, exception_types: List[str], seen_types: Set[str], seen_broad: bool, language: str) -> bool:
        """Check if the current catch block is unreachable."""
        # If we've already seen a broad exception type, all subsequent catches are unreachable
        if seen_broad:
            return True

        # Check if any of the current types have already been caught
        normalized_current = {self._normalize_type(t, language) for t in exception_types}
        
        # Check for exact duplicates
        if any(t in seen_types for t in normalized_current):
            return True

        return False

    def _create_finding(self, ctx: RuleContext, catch_clause, exception_types: List[str], language: str) -> Optional[Finding]:
        """Create a finding for an unreachable catch block."""
        # Get the span for the catch clause header
        start_byte = getattr(catch_clause, 'start_byte', 0)
        end_byte = getattr(catch_clause, 'end_byte', start_byte + 10)

        # Try to target just the catch header if possible
        catch_header = self._find_catch_header(catch_clause)
        if catch_header and catch_header != catch_clause:
            start_byte = getattr(catch_header, 'start_byte', start_byte)
            end_byte = getattr(catch_header, 'end_byte', end_byte)

        # Generate message
        types_str = ", ".join(exception_types) if exception_types else "exception"
        message = f"Unreachable catch block for {types_str}: broader exception type caught earlier."

        # Generate suggestion
        suggestion = self._create_refactoring_suggestion(language, exception_types)

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
                "exception_types": exception_types,
                "catch_span": {
                    "start": start_byte,
                    "end": end_byte
                }
            }
        )

        return finding

    def _create_refactoring_suggestion(self, language: str, exception_types: List[str]) -> str:
        """Create language-specific refactoring suggestion."""
        if language == "java":
            return self._create_java_suggestion(exception_types)
        elif language == "csharp":
            return self._create_csharp_suggestion(exception_types)
        else:
            return "Reorder catch blocks to place specific exception types before broader ones."

    def _create_java_suggestion(self, exception_types: List[str]) -> str:
        """Create Java-specific refactoring suggestion."""
        return f"""Unreachable catch block detected. Reorder catch blocks to place specific exceptions before broader ones.

Problem: Broader exception types (Exception, Throwable) catch all their subtypes, making subsequent catch blocks unreachable.

// ❌ Problem: IOException is never reached because Exception catches it first
try {{
    Files.readAllLines(path);
}} catch (Exception e) {{
    // This catches IOException and all other exceptions
    logger.error("General error", e);
}} catch (IOException ex) {{
    // ❌ UNREACHABLE - IOException is already caught by Exception above
    logger.error("IO error", ex);
}}

// ✅ Solution: Place specific exceptions first
try {{
    Files.readAllLines(path);
}} catch (IOException ex) {{
    // Handle specific IO errors first
    logger.error("File read error", ex);
    throw new ProcessingException("Failed to read file", ex);
}} catch (Exception e) {{
    // Handle all other exceptions
    logger.error("Unexpected error", e);
    throw new ProcessingException("Unexpected error during file processing", e);
}}

// ✅ Alternative: Use multi-catch for similar handling
try {{
    processFile(path);
}} catch (IOException | SecurityException ex) {{
    // Handle file access issues
    logger.error("File access error", ex);
}} catch (Exception e) {{
    // Handle all other exceptions
    logger.error("Processing error", e);
}}

Key principles:
1. Most specific exceptions first (FileNotFoundException before IOException)
2. More general exceptions later (IOException before Exception)
3. Broadest exceptions last (Exception, Throwable)
4. Consider using multi-catch for exceptions with similar handling"""

    def _create_csharp_suggestion(self, exception_types: List[str]) -> str:
        """Create C#-specific refactoring suggestion."""
        return f"""Unreachable catch block detected. Reorder catch blocks to place specific exceptions before broader ones.

Problem: Broader exception types (Exception) catch all their subtypes, making subsequent catch blocks unreachable.

// ❌ Problem: FileNotFoundException is never reached because Exception catches it first
try
{{
    File.ReadAllText(path);
}}
catch (Exception ex)
{{
    // This catches FileNotFoundException and all other exceptions
    _logger.LogError(ex, "General error");
}}
catch (FileNotFoundException ex)
{{
    // ❌ UNREACHABLE - FileNotFoundException is already caught by Exception above
    _logger.LogError(ex, "File not found");
}}

// ✅ Solution: Place specific exceptions first
try
{{
    File.ReadAllText(path);
}}
catch (FileNotFoundException ex)
{{
    // Handle specific file not found errors first
    _logger.LogError(ex, "File not found: {{Path}}", path);
    throw new ProcessingException($"Required file not found: {{path}}", ex);
}}
catch (IOException ex)
{{
    // Handle other IO errors
    _logger.LogError(ex, "IO error reading file: {{Path}}", path);
    throw new ProcessingException($"Failed to read file: {{path}}", ex);
}}
catch (Exception ex)
{{
    // Handle all other exceptions
    _logger.LogError(ex, "Unexpected error processing file: {{Path}}", path);
    throw new ProcessingException($"Unexpected error: {{ex.Message}}", ex);
}}

// ✅ Alternative: Use exception filters for similar types
try
{{
    ProcessFile(path);
}}
catch (IOException ex) when (ex is FileNotFoundException)
{{
    // Handle file not found specifically
    _logger.LogError(ex, "Required file missing");
    return ProcessingResult.FileNotFound;
}}
catch (IOException ex)
{{
    // Handle other IO errors
    _logger.LogError(ex, "IO error during processing");
    return ProcessingResult.IoError;
}}
catch (Exception ex)
{{
    // Handle all other exceptions
    _logger.LogError(ex, "Unexpected error");
    return ProcessingResult.UnexpectedError;
}}

Key principles:
1. Most specific exceptions first (FileNotFoundException before IOException)
2. More general exceptions later (IOException before Exception)
3. Broadest exceptions last (Exception)
4. Use exception filters (when) for additional specificity within the same type
5. Consider using specific return values or custom exceptions for better error handling"""


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

register_rule(ErrorsMultipleCatchOrderIssueRule())


