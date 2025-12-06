"""
Memory Use After Free Rule

Detects intra-procedural use of pointers after they have been freed or deleted
within the same function scope.

Examples:
- C: free(p); *p = 0;
- C++: delete q; q->f();
- C: free(b); b[i] = 1;
"""

from typing import Iterable, Optional, Dict, Any, List
try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryUseAfterFreeRule(Rule):
    """Rule to detect use-after-free vulnerabilities within function scopes."""
    
    meta = RuleMeta(
        id="memory.use_after_free",
        category="memory",
        tier=1,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects pointer use after free/delete within the same function",
        langs=["c", "cpp"]
    )
    
    requires = Requires(syntax=True, scopes=True, raw_text=True)
    
    # Function calls that free memory
    FREE_CALLS = {"free"}
    
    # C++ delete expression kinds
    CPP_DELETE_KINDS = {"delete_expression"}
    
    # Literals that reset pointers to safe states
    RESET_LITERALS = {"NULL", "nullptr", "0"}
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for use-after-free patterns."""
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
        }
        
        return node.kind in function_kinds.get(language, set())
    
    def _check_function_scope(self, ctx: RuleContext, function_node) -> Iterable[Finding]:
        """Check a single function scope for use-after-free patterns."""
        # Track pointer state: name -> {"freed": bool}
        pointer_state = {}
        
        # Walk through statements in the function
        for stmt in self._get_statements(function_node):
            # 1) Handle free() calls
            if self._is_free_call(stmt):
                freed_pointer = self._get_first_arg_identifier(stmt)
                if freed_pointer:
                    pointer_state[freed_pointer] = {"freed": True}
                continue
            
            # 2) Handle C++ delete expressions
            if self._is_delete_expression(stmt):
                deleted_pointer = self._get_deleted_identifier(ctx, stmt)
                if deleted_pointer:
                    pointer_state[deleted_pointer] = {"freed": True}
                continue
            
            # 3) Clear state on reassignment or explicit nulling
            assigned_var = self._get_assigned_variable(ctx, stmt)
            if assigned_var:
                if self._is_null_assignment(ctx, stmt):
                    # Explicit null assignment - clear from tracking
                    pointer_state.pop(assigned_var, None)
                elif not self._is_assignment_to_freed_value(ctx, stmt):
                    # Reinitialize to non-null value - clear from tracking
                    pointer_state.pop(assigned_var, None)
            
            # 4) Check for dereferences of freed pointers
            for deref_info in self._find_pointer_dereferences(ctx, stmt):
                pointer_name, deref_node = deref_info
                
                if pointer_name in pointer_state and pointer_state[pointer_name]["freed"]:
                    # Use-after-free detected!
                    span = self._get_node_span(ctx, deref_node)
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Use-after-free: pointer '{pointer_name}' is dereferenced after being freed/deleted",
                        file=ctx.file_path,
                        start_byte=span[0],
                        end_byte=span[1],
                        severity="error"
                    )
    
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
                "variable_declaration", "local_variable_declaration", "compound_statement"
            }
            
            if hasattr(node, 'kind') and node.kind in statement_kinds:
                statements.append(node)
            
            # For compound statements, also collect their children
            if hasattr(node, 'kind') and node.kind == "compound_statement":
                # Don't add compound statement itself, but traverse its children
                pass
            
            # Recurse into children
            if hasattr(node, 'children') and callable(node.children):
                for child in node.children:
                    collect_statements(child)
            elif hasattr(node, 'children') and hasattr(node.children, '__iter__'):
                for child in node.children:
                    collect_statements(child)
        
        collect_statements(function_node)
        return statements
    
    def _is_free_call(self, stmt) -> bool:
        """Check if statement is a free() function call."""
        if not hasattr(stmt, 'kind') or stmt.kind != "call_expression":
            return False
        
        # Check if the function being called is 'free'
        function_name = self._get_function_name(stmt)
        return function_name in self.FREE_CALLS
    
    def _get_function_name(self, stmt) -> Optional[str]:
        """Get the function name from a call expression."""
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
                func_node = stmt.function
                if hasattr(func_node, 'text'):
                    text = func_node.text
                    if isinstance(text, str):
                        return text
                    elif hasattr(text, 'decode'):
                        return text.decode('utf-8', errors='ignore')
        except:
            pass
        return None
    
    def _get_first_arg_identifier(self, stmt) -> Optional[str]:
        """Get the identifier of the first argument in a function call."""
        try:
            if hasattr(stmt, 'arguments') and stmt.arguments:
                first_arg = stmt.arguments[0]
                return self._extract_identifier_name(first_arg)
        except:
            pass
        return None
    
    def _is_delete_expression(self, stmt) -> bool:
        """Check if statement is a C++ delete expression."""
        return hasattr(stmt, 'kind') and stmt.kind in self.CPP_DELETE_KINDS
    
    def _get_deleted_identifier(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the identifier being deleted in a C++ delete expression."""
        try:
            if hasattr(stmt, 'argument'):
                return self._extract_identifier_name(stmt.argument)
        except:
            pass
        return None
    
    def _get_assigned_variable(self, ctx: RuleContext, stmt) -> Optional[str]:
        """Get the variable being assigned to."""
        try:
            # Assignment expressions
            if hasattr(stmt, 'left'):
                return self._extract_identifier_name(stmt.left)
            # Variable declarations
            elif hasattr(stmt, 'declarator'):
                if hasattr(stmt.declarator, 'name'):
                    return self._extract_identifier_name(stmt.declarator.name)
            elif hasattr(stmt, 'name'):
                return self._extract_identifier_name(stmt.name)
        except:
            pass
        return None
    
    def _is_null_assignment(self, ctx: RuleContext, stmt) -> bool:
        """Check if statement assigns a null value to a pointer."""
        stmt_text = self._get_node_text(ctx, stmt).replace(" ", "")
        return any(f"={literal}" in stmt_text for literal in self.RESET_LITERALS)
    
    def _is_assignment_to_freed_value(self, ctx: RuleContext, stmt) -> bool:
        """Check if assignment assigns another freed pointer (not implemented for simplicity)."""
        # For now, assume all non-null assignments are safe reinitializations
        return False
    
    def _find_pointer_dereferences(self, ctx: RuleContext, stmt) -> List[tuple]:
        """Find all pointer dereferences in a statement."""
        dereferences = []
        
        def find_derefs(node):
            if not node or not hasattr(node, 'kind'):
                return
                
            # Unary dereference: *p
            if node.kind == "unary_expression":
                if self._is_dereference_operator(ctx, node):
                    operand_name = self._extract_identifier_name(getattr(node, 'argument', None))
                    if operand_name:
                        dereferences.append((operand_name, node))
            
            # Pointer member access: p->member
            elif node.kind in {"pointer_expression", "ptr_member_expression"}:
                base_name = self._extract_identifier_name(getattr(node, 'object', None))
                if base_name:
                    dereferences.append((base_name, node))
            
            # Array subscript: p[i]
            elif node.kind == "subscript_expression":
                array_name = self._extract_identifier_name(getattr(node, 'object', None))
                if array_name:
                    dereferences.append((array_name, node))
            
            # Recurse into children
            if hasattr(node, 'children') and callable(node.children):
                for child in node.children:
                    find_derefs(child)
            elif hasattr(node, 'children') and hasattr(node.children, '__iter__'):
                for child in node.children:
                    find_derefs(child)
        
        find_derefs(stmt)
        return dereferences
    
    def _is_dereference_operator(self, ctx: RuleContext, node) -> bool:
        """Check if unary expression is a dereference operator."""
        try:
            if hasattr(node, 'operator'):
                op_text = self._get_node_text(ctx, node.operator)
                return op_text == "*"
        except:
            pass
        return False
    
    def _extract_identifier_name(self, node) -> Optional[str]:
        """Extract identifier name from various node types."""
        if not node:
            return None
            
        try:
            # Direct identifier
            if hasattr(node, 'kind') and node.kind == "identifier":
                if hasattr(node, 'text'):
                    text = node.text
                    if isinstance(text, str):
                        return text
                    elif hasattr(text, 'decode'):
                        return text.decode('utf-8', errors='ignore')
            
            # For other node types, try to find nested identifier
            if hasattr(node, 'children'):
                if callable(node.children):
                    children = node.children
                else:
                    children = node.children
                    
                for child in children:
                    name = self._extract_identifier_name(child)
                    if name:
                        return name
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
    
    def _get_node_span(self, ctx: RuleContext, node) -> tuple:
        """Get the span of a node for reporting."""
        try:
            if hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(node)
        except:
            pass
            
        # Fallback span
        return (0, 10)


# Register the rule
rule = MemoryUseAfterFreeRule()
RULES = [rule]


