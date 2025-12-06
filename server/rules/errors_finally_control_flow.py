# server/rules/errors_finally_control_flow.py
"""
Rule to detect control flow statements in finally blocks.

This rule analyzes finally blocks across multiple languages for:
- Python: return, break, continue statements in finally clauses
- Java: return, break, continue statements in finally blocks  
- C#: return, break, continue statements in finally blocks

When control flow statements are detected in finally blocks, it suggests avoiding
them as they can suppress exceptions or override the normal control flow.
"""

from typing import Set, Optional, List
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsFinallyControlFlowRule:
    """Rule to detect control flow statements in finally blocks."""
    
    meta = RuleMeta(
        id="errors.finally_control_flow",
        category="errors",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects return/break/continue statements in finally blocks that can suppress exceptions or override results.",
        langs=["python", "java", "csharp"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific finally block node types
    FINALLY_BLOCK_TYPES = {
        "python": {"finally_clause"},
        "java": {"finally_clause"},
        "csharp": {"finally_clause"},
    }

    # Language-specific control flow statement types
    CONTROL_FLOW_STATEMENT_TYPES = {
        "python": {"return_statement", "break_statement", "continue_statement"},
        "java": {"return_statement", "break_statement", "continue_statement"},
        "csharp": {"return_statement", "break_statement", "continue_statement"},
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for control flow in finally blocks."""
        language = ctx.adapter.language_id
        
        # Skip unsupported languages
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get finally block types for this language
        finally_types = self.FINALLY_BLOCK_TYPES.get(language, set())
        if not finally_types:
            return

        # Walk the syntax tree looking for finally blocks
        for node in ctx.walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in finally_types:
                # Find control flow statements within this finally block
                control_flow_stmts = self._find_control_flow(node, language, ctx.text)
                for stmt in control_flow_stmts:
                    finding = self._create_finding(ctx, stmt, node, language)
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

    def _find_control_flow(self, finally_node, language: str, file_text: str) -> List:
        """Find control flow statements within a finally block."""
        control_flow_types = self.CONTROL_FLOW_STATEMENT_TYPES.get(language, set())
        if not control_flow_types:
            return []
        
        control_flow_stmts = []
        
        # Walk through all descendants of the finally block
        for node in self._walk_descendants(finally_node):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in control_flow_types:
                # Check if this statement is actually within the finally block's scope
                if self._within(finally_node, node):
                    control_flow_stmts.append(node)
        
        return control_flow_stmts

    def _walk_descendants(self, node):
        """Walk all descendant nodes of a given node."""
        if not node:
            return
        
        if hasattr(node, 'children'):
            children = getattr(node, 'children', [])
            if children:
                try:
                    for child in children:
                        yield child
                        yield from self._walk_descendants(child)
                except (TypeError, AttributeError):
                    pass

    def _within(self, ancestor_node, descendant_node) -> bool:
        """Check if descendant_node is within the span of ancestor_node."""
        if not ancestor_node or not descendant_node:
            return False
        
        # Get byte positions
        anc_start = getattr(ancestor_node, 'start_byte', 0)
        anc_end = getattr(ancestor_node, 'end_byte', 0)
        desc_start = getattr(descendant_node, 'start_byte', 0)
        desc_end = getattr(descendant_node, 'end_byte', 0)
        
        # Check if descendant is within ancestor's span
        return anc_start <= desc_start and desc_end <= anc_end

    def _create_finding(self, ctx: RuleContext, control_flow_stmt, finally_block, language: str) -> Optional[Finding]:
        """Create a finding for a control flow statement in finally block."""
        # Generate language-specific message and suggestion
        message, suggestion = self._get_message_and_suggestion(language, control_flow_stmt, ctx.text)
        
        # Get the span for the control flow statement
        start_byte = getattr(control_flow_stmt, 'start_byte', 0)
        end_byte = getattr(control_flow_stmt, 'end_byte', start_byte + 10)
        
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
                "control_flow_type": self._identify_control_flow_type(control_flow_stmt, language, ctx.text),
                "finally_span": {
                    "start": getattr(finally_block, 'start_byte', 0),
                    "end": getattr(finally_block, 'end_byte', 0)
                }
            }
        )
        
        return finding

    def _get_message_and_suggestion(self, language: str, control_flow_stmt, file_text: str) -> tuple:
        """Generate appropriate message and suggestion for the language."""
        control_flow_type = self._identify_control_flow_type(control_flow_stmt, language, file_text)
        
        message = f"Control flow in finally can suppress exceptions or override results; avoid {control_flow_type} here."
        
        suggestion = self._create_refactoring_suggestion(language, control_flow_type)
        
        return message, suggestion

    def _identify_control_flow_type(self, control_flow_stmt, language: str, file_text: str) -> str:
        """Identify the specific type of control flow statement."""
        if not hasattr(control_flow_stmt, 'type'):
            return "control flow"
        
        stmt_type = control_flow_stmt.type
        
        if "return" in stmt_type:
            return "return"
        elif "break" in stmt_type:
            return "break"
        elif "continue" in stmt_type:
            return "continue"
        else:
            return "control flow"

    def _create_refactoring_suggestion(self, language: str, control_flow_type: str) -> str:
        """Create language-specific refactoring suggestion."""
        if language == "python":
            return self._create_python_suggestion(control_flow_type)
        elif language == "java":
            return self._create_java_suggestion(control_flow_type)
        elif language == "csharp":
            return self._create_csharp_suggestion(control_flow_type)
        else:
            return "Avoid control flow statements in finally blocks to prevent suppressing exceptions."

    def _create_python_suggestion(self, control_flow_type: str) -> str:
        """Create Python-specific refactoring suggestion."""
        if control_flow_type == "return":
            return """Return statement in finally block can suppress exceptions and override results. Consider these alternatives:

# Problem: Return in finally suppresses exceptions
try:
    risky_operation()
except Exception as e:
    handle_error(e)
    raise  # This raise will be suppressed!
finally:
    return "success"  # ❌ This overrides the exception

# Solution 1: Move return outside try/finally
result = None
try:
    result = risky_operation()
except Exception as e:
    handle_error(e)
    raise
finally:
    cleanup()
return result  # ✅ Return after cleanup

# Solution 2: Store result and return after finally
result = None
try:
    result = risky_operation()
except Exception as e:
    handle_error(e)
    raise
finally:
    cleanup()
    # No return here
# Return or re-raise outside"""

        elif control_flow_type in ["break", "continue"]:
            return f"""{control_flow_type.title()} statement in finally block can suppress exceptions. Consider these alternatives:

# Problem: {control_flow_type.title()} in finally suppresses exceptions
for item in items:
    try:
        process_item(item)
    except Exception as e:
        handle_error(e)
        raise  # This raise will be suppressed!
    finally:
        {control_flow_type}  # ❌ This overrides the exception

# Solution 1: Use flag to control loop flow
should_continue = True
for item in items:
    try:
        process_item(item)
    except Exception as e:
        handle_error(e)
        should_continue = False
        break  # Handle error outside finally
    finally:
        cleanup()
    
    if not should_continue:
        break

# Solution 2: Restructure to avoid {control_flow_type} in finally
for item in items:
    try:
        process_item(item)
        cleanup()  # Move cleanup before potential {control_flow_type}
        if should_{control_flow_type}():
            {control_flow_type}
    except Exception as e:
        cleanup()  # Ensure cleanup happens
        handle_error(e)
        raise"""

        else:
            return """Control flow statements in finally blocks can suppress exceptions. Move control flow outside the finally block and ensure cleanup happens in all paths."""

    def _create_java_suggestion(self, control_flow_type: str) -> str:
        """Create Java-specific refactoring suggestion."""
        if control_flow_type == "return":
            return """Return statement in finally block can suppress exceptions and override results. Consider these alternatives:

// Problem: Return in finally suppresses exceptions
public String problematicMethod() {
    try {
        riskyOperation();
    } catch (Exception e) {
        logger.error("Error occurred", e);
        throw new RuntimeException(e);  // This will be suppressed!
    } finally {
        return "success";  // ❌ This overrides the exception
    }
}

// Solution 1: Move return outside try/finally
public String betterMethod() {
    String result = null;
    try {
        result = riskyOperation();
    } catch (Exception e) {
        logger.error("Error occurred", e);
        throw new RuntimeException(e);
    } finally {
        cleanup();
    }
    return result;  // ✅ Return after cleanup
}

// Solution 2: Store result and return after finally
public String anotherApproach() {
    String result = null;
    Exception caughtException = null;
    
    try {
        result = riskyOperation();
    } catch (Exception e) {
        caughtException = e;
    } finally {
        cleanup();
    }
    
    if (caughtException != null) {
        throw new RuntimeException(caughtException);
    }
    return result;
}"""

        elif control_flow_type in ["break", "continue"]:
            return f"""{control_flow_type.title()} statement in finally block can suppress exceptions. Consider these alternatives:

// Problem: {control_flow_type.title()} in finally suppresses exceptions
for (Item item : items) {{
    try {{
        processItem(item);
    }} catch (Exception e) {{
        logger.error("Error processing item", e);
        throw new RuntimeException(e);  // This will be suppressed!
    }} finally {{
        {control_flow_type};  // ❌ This overrides the exception
    }}
}}

// Solution 1: Use flag to control loop flow
boolean shouldContinue = true;
for (Item item : items) {{
    try {{
        processItem(item);
    }} catch (Exception e) {{
        logger.error("Error processing item", e);
        shouldContinue = false;
        break;  // Handle error outside finally
    }} finally {{
        cleanup();
    }}
    
    if (!shouldContinue) {{
        break;
    }}
}}

// Solution 2: Restructure to avoid {control_flow_type} in finally
for (Item item : items) {{
    try {{
        processItem(item);
        cleanup();  // Move cleanup before potential {control_flow_type}
        if (should{control_flow_type.title()}()) {{
            {control_flow_type};
        }}
    }} catch (Exception e) {{
        cleanup();  // Ensure cleanup happens
        logger.error("Error processing item", e);
        throw new RuntimeException(e);
    }}
}}"""

        else:
            return """Control flow statements in finally blocks can suppress exceptions. Move control flow outside the finally block and ensure cleanup happens in all code paths."""

    def _create_csharp_suggestion(self, control_flow_type: str) -> str:
        """Create C#-specific refactoring suggestion."""
        if control_flow_type == "return":
            return """Return statement in finally block can suppress exceptions and override results. Consider these alternatives:

// Problem: Return in finally suppresses exceptions
public string ProblematicMethod()
{
    try
    {
        RiskyOperation();
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Error occurred");
        throw;  // This will be suppressed!
    }
    finally
    {
        return "success";  // ❌ This overrides the exception
    }
}

// Solution 1: Move return outside try/finally
public string BetterMethod()
{
    string result = null;
    try
    {
        result = RiskyOperation();
    }
    catch (Exception ex)
    {
        _logger.LogError(ex, "Error occurred");
        throw;
    }
    finally
    {
        Cleanup();
    }
    return result;  // ✅ Return after cleanup
}

// Solution 2: Use using statement for automatic cleanup
public string WithUsingStatement()
{
    using (var resource = AcquireResource())
    {
        try
        {
            return RiskyOperation();
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Error occurred");
            throw;
        }
        // Cleanup happens automatically
    }
}

// Solution 3: Store result and return after finally
public string AnotherApproach()
{
    string result = null;
    Exception caughtException = null;
    
    try
    {
        result = RiskyOperation();
    }
    catch (Exception ex)
    {
        caughtException = ex;
    }
    finally
    {
        Cleanup();
    }
    
    if (caughtException != null)
    {
        throw caughtException;
    }
    return result;
}"""

        elif control_flow_type in ["break", "continue"]:
            return f"""{control_flow_type.title()} statement in finally block can suppress exceptions. Consider these alternatives:

// Problem: {control_flow_type.title()} in finally suppresses exceptions
foreach (var item in items)
{{
    try
    {{
        ProcessItem(item);
    }}
    catch (Exception ex)
    {{
        _logger.LogError(ex, "Error processing item");
        throw;  // This will be suppressed!
    }}
    finally
    {{
        {control_flow_type};  // ❌ This overrides the exception
    }}
}}

// Solution 1: Use flag to control loop flow
bool shouldContinue = true;
foreach (var item in items)
{{
    try
    {{
        ProcessItem(item);
    }}
    catch (Exception ex)
    {{
        _logger.LogError(ex, "Error processing item");
        shouldContinue = false;
        break;  // Handle error outside finally
    }}
    finally
    {{
        Cleanup();
    }}
    
    if (!shouldContinue)
    {{
        break;
    }}
}}

// Solution 2: Restructure to avoid {control_flow_type} in finally
foreach (var item in items)
{{
    try
    {{
        ProcessItem(item);
        Cleanup();  // Move cleanup before potential {control_flow_type}
        if (Should{control_flow_type.title()}())
        {{
            {control_flow_type};
        }}
    }}
    catch (Exception ex)
    {{
        Cleanup();  // Ensure cleanup happens
        _logger.LogError(ex, "Error processing item");
        throw;
    }}
}}

// Solution 3: Use LINQ and exception handling
try
{{
    var processedItems = items
        .Where(item => !ShouldSkip(item))
        .Select(item => 
        {{
            using (var scope = CreateScope())
            {{
                return ProcessItem(item);
            }}
        }})
        .ToList();
}}
catch (Exception ex)
{{
    _logger.LogError(ex, "Error processing items");
    throw;
}}"""

        else:
            return """Control flow statements in finally blocks can suppress exceptions. Move control flow outside the finally block and ensure cleanup happens in all code paths using 'using' statements or explicit cleanup."""


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

register_rule(ErrorsFinallyControlFlowRule())


