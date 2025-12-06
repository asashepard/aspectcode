"""
Memory Double Free/Close Rule

Detects when the same resource/handle/pointer is released twice within a single
function without proper nulling or reassignment between releases.

Examples:
- C: free(p); free(p);
- C++: delete p; delete p;
- Python: f.close(); f.close();
- Java: in.close(); in.close();
- C#: fs.Dispose(); fs.Dispose();
"""

from typing import Iterable, Optional, Dict, Any, Tuple

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryDoubleFreeOrCloseRule(Rule):
    """Rule to detect double releases of resources within a single function."""
    
    meta = RuleMeta(
        id="memory.double_free_or_close",
        category="memory",
        tier=1,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects double releases (free/close/delete/Dispose) of the same resource within a function",
        langs=["c", "cpp", "python", "java", "csharp"]
    )
    
    requires = Requires(syntax=True, scopes=True, raw_text=True)
    
    # Release function signatures by language
    RELEASE_SIGS = {
        "c": {"free", "fclose", "close"},
        "cpp": {"free", "fclose", "close", "delete", "delete[]"},
        "python": {"close"},
        "java": {"close"},
        "csharp": {"Close", "Dispose"},
    }
    
    # Acquisition hints to help track resource variables
    ACQUIRE_HINTS = {
        "c": {"malloc", "calloc", "realloc", "fopen", "open", "socket"},
        "cpp": {"new", "new[]", "malloc", "calloc", "realloc", "fopen", "open", "socket"},
        "python": {"open"},
        "java": {"new "},  # constructors yielding closeable resources
        "csharp": {"new "},  # constructors/streams/sockets
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for double releases."""
        if not ctx.tree or ctx.language not in self.meta.langs:
            return
            
        # Walk through function scopes and check each one
        for node in ctx.walk_nodes():
            if self._is_function_scope(node, ctx.language):
                yield from self._check_function_scope(ctx, node)
    
    def _walk_nodes(self, ctx: RuleContext):
        """Walk all nodes in the syntax tree."""
        if not ctx.tree:
            return
            
        def walk(node):
            yield node
            if hasattr(node, 'children') and callable(node.children):
                for child in node.children:
                    yield from walk(child)
            elif hasattr(node, 'children') and hasattr(node.children, '__iter__'):
                for child in node.children:
                    yield from walk(child)
                    
        yield from walk(ctx.tree)
    
    def _is_function_scope(self, node, language: str) -> bool:
        """Check if node represents a function scope."""
        if not hasattr(node, 'kind'):
            return False
            
        function_kinds = {
            "c": {"function_definition"},
            "cpp": {"function_definition"},
            "python": {"function_definition"},
            "java": {"method_declaration", "constructor_declaration"},
            "csharp": {"method_declaration", "constructor_declaration"}
        }
        
        return node.kind in function_kinds.get(language, set())
    
    def _check_function_scope(self, ctx: RuleContext, function_node) -> Iterable[Finding]:
        """Check a single function scope for double releases."""
        # Track resource variables and their release state
        resource_state = {}  # name -> {"released": bool, "last_release_node": node}
        
        # Walk through statements in the function
        for stmt in self._get_statements(function_node):
            # Check for variable reassignment/nulling (resets state)
            if self._is_assignment_or_nulling(ctx, stmt):
                var_name = self._get_assigned_variable(ctx, stmt)
                if var_name and var_name in resource_state:
                    resource_state.pop(var_name, None)
            
            # Check for resource acquisition (start tracking)
            if self._is_resource_acquisition(ctx, stmt):
                var_name = self._get_target_variable(ctx, stmt)
                if var_name:
                    resource_state[var_name] = {"released": False, "last_release_node": None}
            
            # Check for resource release
            release_info = self._get_release_info(ctx, stmt)
            if release_info:
                var_name, release_node = release_info
                
                if var_name in resource_state and resource_state[var_name]["released"]:
                    # Double release detected!
                    span = self._get_node_span(ctx, release_node)
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Resource '{var_name}' appears to be released/closed more than once",
                        file=ctx.file_path,
                        start_byte=span[0],
                        end_byte=span[1],
                        severity="error"
                    )
                else:
                    # First release or not tracked - mark as released
                    if var_name not in resource_state:
                        resource_state[var_name] = {"released": False, "last_release_node": None}
                    resource_state[var_name]["released"] = True
                    resource_state[var_name]["last_release_node"] = release_node
    
    def _get_statements(self, function_node):
        """Get all statements from a function node."""
        statements = []
        
        def collect_statements(node):
            if not node:
                return
                
            # Common statement kinds to collect
            statement_kinds = {
                "expression_statement", "assignment", "assignment_expression", 
                "declaration", "call_expression", "delete_expression",
                "variable_declaration", "local_variable_declaration"
            }
            
            if hasattr(node, 'kind') and node.kind in statement_kinds:
                statements.append(node)
            
            # Recurse into children
            if hasattr(node, 'children') and callable(node.children):
                for child in node.children:
                    collect_statements(child)
            elif hasattr(node, 'children') and hasattr(node.children, '__iter__'):
                for child in node.children:
                    collect_statements(child)
        
        collect_statements(function_node)
        return statements
    
    def _is_assignment_or_nulling(self, ctx: RuleContext, stmt) -> bool:
        """Check if statement is an assignment or nulling operation."""
        if not hasattr(stmt, 'kind'):
            return False
            
        assignment_kinds = {
            "assignment", "assignment_expression", "declaration", 
            "variable_declaration", "local_variable_declaration"
        }
        
        if stmt.kind not in assignment_kinds:
            return False
        
        # Check for nulling patterns
        stmt_text = self._get_node_text(ctx, stmt).lower().replace(" ", "")
        nulling_patterns = ["=null", "=nullptr", "=none"]
        return any(pattern in stmt_text for pattern in nulling_patterns)
    
    def _get_assigned_variable(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the variable being assigned to."""
        try:
            # Try to find left-hand side of assignment
            if hasattr(stmt, 'left'):
                return self._get_identifier_text(ctx, stmt.left)
            elif hasattr(stmt, 'name'):
                return self._get_identifier_text(ctx, stmt.name)
            elif hasattr(stmt, 'declarator'):
                if hasattr(stmt.declarator, 'name'):
                    return self._get_identifier_text(ctx, stmt.declarator.name)
            
            # Handle C declarations: declaration -> init_declarator -> declarator -> identifier
            if stmt.type == "declaration":
                for child in stmt.children:
                    if child.type == "init_declarator":
                        # Look for declarator (which could be pointer_declarator or identifier)
                        for declarator_child in child.children:
                            if declarator_child.type in ("pointer_declarator", "identifier"):
                                # For pointer_declarator, find the identifier child
                                if declarator_child.type == "pointer_declarator":
                                    for ptr_child in declarator_child.children:
                                        if ptr_child.type == "identifier":
                                            return ptr_child.text.decode()
                                # For direct identifier
                                elif declarator_child.type == "identifier":
                                    return declarator_child.text.decode()
        except:
            pass
        return None
    
    def _is_resource_acquisition(self, ctx: RuleContext, stmt) -> bool:
        """Check if statement acquires a resource."""
        stmt_text = self._get_node_text(ctx, stmt)
        acquire_hints = self.ACQUIRE_HINTS.get(ctx.language, set())
        
        return any(hint in stmt_text for hint in acquire_hints)
    
    def _get_target_variable(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the variable that receives the resource."""
        return self._get_assigned_variable(ctx, stmt)
    
    def _get_release_info(self, ctx: RuleContext, stmt) -> Optional[Tuple[str, Any]]:
        """Get release information if statement is a resource release."""
        if not hasattr(stmt, 'kind'):
            return None
            
        lang = ctx.language
        release_sigs = self.RELEASE_SIGS.get(lang, set())
        
        # Handle method calls like obj.close(), obj.Dispose()
        if self._is_method_call(stmt):
            receiver = self._get_receiver_name(ctx, stmt)
            method_name = self._get_method_name(ctx, stmt)
            
            if receiver and method_name in release_sigs:
                return (receiver, stmt)
        
        # Handle function calls like free(p), fclose(fp)
        if self._is_function_call(stmt):
            function_name = self._get_function_name(ctx, stmt)
            
            if function_name in release_sigs:
                # Get first argument as the resource variable
                arg_var = self._get_first_argument_name(ctx, stmt)
                if arg_var:
                    return (arg_var, stmt)
        
        # Handle C++ delete expressions
        if lang == "cpp" and stmt.kind == "delete_expression":
            deleted_var = self._get_deleted_variable(ctx, stmt)
            if deleted_var:
                return (deleted_var, stmt)
        
        return None
    
    def _is_method_call(self, stmt) -> bool:
        """Check if statement is a method call."""
        return (hasattr(stmt, 'kind') and 
                stmt.kind in {"call_expression", "method_invocation"} and
                self._has_receiver(stmt))
    
    def _has_receiver(self, stmt) -> bool:
        """Check if call has a receiver/object."""
        if hasattr(stmt, 'function'):
            func = stmt.function
            return hasattr(func, 'object') or hasattr(func, 'receiver')
        return False
    
    def _get_receiver_name(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the receiver/object name from a method call."""
        try:
            if hasattr(stmt, 'function'):
                func = stmt.function
                if hasattr(func, 'object'):
                    return self._get_identifier_text(ctx, func.object)
                elif hasattr(func, 'receiver'):
                    return self._get_identifier_text(ctx, func.receiver)
        except:
            pass
        return None
    
    def _get_method_name(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the method name from a method call."""
        try:
            if hasattr(stmt, 'function'):
                func = stmt.function
                if hasattr(func, 'attribute'):
                    return self._get_identifier_text(ctx, func.attribute)
                elif hasattr(func, 'name'):
                    return self._get_identifier_text(ctx, func.name)
        except:
            pass
        return None
    
    def _is_function_call(self, stmt) -> bool:
        """Check if statement is a function call."""
        return (hasattr(stmt, 'kind') and 
                stmt.kind in {"call_expression"} and
                not self._has_receiver(stmt))
    
    def _get_function_name(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the function name from a function call."""
        try:
            # For tree-sitter, the function name is typically the first child of call_expression
            if hasattr(stmt, 'children') and stmt.children:
                for child in stmt.children:
                    if child.type == "identifier":
                        if hasattr(child, 'text'):
                            text = child.text
                            if hasattr(text, 'decode'):
                                return text.decode()
                            else:
                                return str(text)
                        break
                        
            # Fallback: try function attribute (for other parsers)
            if hasattr(stmt, 'function'):
                return self._get_identifier_text(ctx, stmt.function)
        except:
            pass
        return None
    
    def _get_first_argument_name(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the first argument name from a function call."""
        try:
            # For tree-sitter, arguments are in argument_list child
            if hasattr(stmt, 'children') and stmt.children:
                for child in stmt.children:
                    if child.type == "argument_list":
                        # Find first non-punctuation child in argument list
                        for arg_child in child.children:
                            if arg_child.type == "identifier":
                                if hasattr(arg_child, 'text'):
                                    text = arg_child.text
                                    if hasattr(text, 'decode'):
                                        return text.decode()
                                    else:
                                        return str(text)
                        break
                        
            # Fallback: try arguments attribute (for other parsers)
            if hasattr(stmt, 'arguments') and stmt.arguments:
                first_arg = stmt.arguments[0]
                return self._get_identifier_text(ctx, first_arg)
        except:
            pass
        return None
    
    def _get_deleted_variable(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the variable being deleted in a C++ delete expression."""
        try:
            if hasattr(stmt, 'argument'):
                return self._get_identifier_text(ctx, stmt.argument)
        except:
            pass
        return None
    
    def _get_identifier_text(self, ctx: RuleContext, node) -> Optional[str]:
        """Extract identifier text from a node."""
        if not node:
            return None
            
        try:
            # Try direct text attribute
            if hasattr(node, 'text'):
                text = node.text
                if isinstance(text, str):
                    return text
                elif hasattr(text, 'decode'):
                    return text.decode('utf-8', errors='ignore')
            
            # Try getting text from span
            if hasattr(ctx.adapter, 'node_span') and ctx.text:
                start, end = ctx.adapter.node_span(node)
                if start is not None and end is not None and start >= 0 and end <= len(ctx.text):
                    return ctx.text[start:end]
        except:
            pass
            
        return None
    
    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
            
        try:
            # Try text attribute first
            if hasattr(node, 'text'):
                text = node.text
                if isinstance(text, str):
                    return text
                elif hasattr(text, 'decode'):
                    return text.decode('utf-8', errors='ignore')
                    
            # Fallback to span extraction
            if hasattr(ctx.adapter, 'node_span') and ctx.text:
                start, end = ctx.adapter.node_span(node)
                if start is not None and end is not None and start >= 0 and end <= len(ctx.text):
                    return ctx.text[start:end]
        except:
            pass
            
        return ""
    
    def _get_node_span(self, ctx: RuleContext, node) -> Tuple[int, int]:
        """Get the span of a node for reporting."""
        try:
            if hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(node)
        except:
            pass
            
        # Fallback span
        return (0, 10)


# Register the rule
rule = MemoryDoubleFreeOrCloseRule()
RULES = [rule]


