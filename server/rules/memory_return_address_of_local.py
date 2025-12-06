"""
Memory Return Address of Local Rule

Detects returning addresses/references of local (stack) objects in C/C++ which
creates dangling pointers/references.

Examples:
- C: return &x; (where x is local)
- C: return buf; (where buf is local array decaying to pointer)
- C++: return x; (where x is local and return type is reference)
"""

from typing import Iterable, Optional, Dict, Any
try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryReturnAddressOfLocalRule(Rule):
    """Rule to detect returning addresses/references of local stack objects."""
    
    meta = RuleMeta(
        id="memory.return_address_of_local",
        category="memory",
        tier=0,  # Syntax-only analysis
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects returning address/reference of local stack objects which creates dangling pointers",
        langs=["c", "cpp"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for returning addresses of local objects."""
        if not ctx.tree:
            return
            
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            
        # Walk through function definitions and check each one
        for node in ctx.walk_nodes():
            if self._is_function_definition(node):
                yield from self._check_function(ctx, node)
    
    def _walk_nodes(self, ctx: RuleContext):
        """Walk all nodes in the syntax tree."""
        if not ctx.tree:
            return
            
        def walk(node):
            yield node
            for child in node.children:
                yield from walk(child)
                    
        yield from walk(ctx.tree.root_node)
    
    def _is_function_definition(self, node) -> bool:
        """Check if node is a function definition."""
        if not hasattr(node, 'type'):
            return False
        return node.type in {"function_definition", "method_definition"}
    
    def _check_function(self, ctx: RuleContext, function_node) -> Iterable[Finding]:
        """Check a function for returning addresses of local objects."""
        # Collect local variable declarations
        locals_by_name = self._collect_local_declarations(ctx, function_node)
        
        # Get return type for analysis
        return_type = self._get_return_type(ctx, function_node)
        
        # Find all return statements and analyze them
        for return_stmt in self._find_return_statements(function_node):
            return_expr = self._get_return_expression(return_stmt)
            if not return_expr:
                continue
            
            # Case A: Address-of local object (&local)
            if self._is_address_of_expression(ctx, return_expr):
                operand = self._get_address_of_operand(return_expr)
                local_name = self._extract_identifier_name(ctx, operand)
                
                if local_name and local_name in locals_by_name:
                    local_decl = locals_by_name[local_name]
                    if not self._is_static_storage(ctx, local_decl):
                        span = self._get_node_span(ctx, return_expr)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Returning address of local '{local_name}' results in a dangling pointer/reference",
                            file=ctx.file_path,
                            start_byte=span[0],
                            end_byte=span[1],
                            severity="error"
                        )
                        continue
            
            # Case B: Local array decay (returning local array as pointer)
            if self._is_identifier_or_subscript(ctx, return_expr):
                array_name = self._extract_identifier_name(ctx, return_expr)
                
                if array_name and array_name in locals_by_name:
                    local_decl = locals_by_name[array_name]
                    if (self._is_array_declaration(ctx, local_decl) and 
                        self._return_type_is_pointer_like(ctx, return_type) and
                        not self._is_static_storage(ctx, local_decl)):
                        
                        span = self._get_node_span(ctx, return_expr)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Returning local array '{array_name}' (decays to pointer) escapes stack storage",
                            file=ctx.file_path,
                            start_byte=span[0],
                            end_byte=span[1],
                            severity="error"
                        )
                        continue
            
            # Case C (C++): Returning by reference a local object
            if (ctx.adapter.language_id == "cpp" and 
                self._return_type_is_reference(ctx, return_type) and
                self._is_identifier_expression(ctx, return_expr)):
                
                local_name = self._extract_identifier_name(ctx, return_expr)
                
                if local_name and local_name in locals_by_name:
                    local_decl = locals_by_name[local_name]
                    if not self._is_static_storage(ctx, local_decl):
                        span = self._get_node_span(ctx, return_expr)
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Returning reference to local '{local_name}' produces a dangling reference",
                            file=ctx.file_path,
                            start_byte=span[0],
                            end_byte=span[1],
                            severity="error"
                        )
    
    def _collect_local_declarations(self, ctx: RuleContext, function_node) -> Dict[str, Any]:
        """Collect all local variable declarations in the function."""
        locals_by_name = {}
        
        def collect_declarations(node):
            if not node or not hasattr(node, 'type'):
                return
                
            # Variable declarations
            if node.type in {"declaration", "variable_declaration", "local_variable_declaration"}:
                var_name = self._get_declaration_name(ctx, node)
                if var_name:
                    locals_by_name[var_name] = node
            
            # Parameter declarations
            elif node.type in {"parameter_declaration", "parameter"}:
                param_name = self._get_declaration_name(ctx, node)
                if param_name:
                    # Parameters are not considered "local" for this rule
                    # since returning their addresses is often valid
                    pass
            
            # Recurse into children
            for child in node.children:
                collect_declarations(child)
        
        collect_declarations(function_node)
        return locals_by_name
    
    def _get_declaration_name(self, ctx: RuleContext, decl_node) -> Optional[str]:
        """Extract the variable name from a declaration node."""
        try:
            # Walk through the declaration looking for identifiers
            # In C: declaration -> init_declarator -> identifier
            # In C++: similar patterns
            def find_identifier(node):
                if node.type in ["identifier", "id"]:
                    return self._extract_identifier_name(ctx, node)
                
                for child in node.children:
                    result = find_identifier(child)
                    if result:
                        return result
                return None
            
            return find_identifier(decl_node)
        except:
            pass
        
        return None
    
    def _get_children(self, node):
        """Get children of a node."""
        if hasattr(node, 'children'):
            if callable(node.children):
                return node.children
            elif hasattr(node.children, '__iter__'):
                return node.children
        return []
    
    def _get_return_type(self, ctx: RuleContext, function_node) -> Optional[Any]:
        """Get the return type of a function."""
        try:
            if hasattr(function_node, 'type'):
                return function_node.type
            elif hasattr(function_node, 'return_type'):
                return function_node.return_type
        except:
            pass
        return None
    
    def _find_return_statements(self, function_node):
        """Find all return statements in a function."""
        return_statements = []
        
        def find_returns(node):
            if not node:
                return
                
            if node.type in ["return_statement", "return"]:
                return_statements.append(node)
            
            # Recurse into children
            for child in node.children:
                find_returns(child)
        
        find_returns(function_node)
        return return_statements
    
    def _get_return_expression(self, return_stmt) -> Optional[Any]:
        """Get the expression being returned."""
        try:
            # For tree-sitter, the return expression is usually the child after 'return' keyword
            for child in return_stmt.children:
                # Skip 'return' keyword and ';' semicolon
                if child.type not in {"return", ";"}:
                    return child
        except:
            pass
        return None
    
    def _is_address_of_expression(self, ctx: RuleContext, expr) -> bool:
        """Check if expression is an address-of operation (&)."""
        if not expr or not hasattr(expr, 'type'):
            return False
        
        if expr.type == "unary_expression":
            operator = self._get_operator_text(ctx, expr)
            return operator == "&"
        
        # C parser uses pointer_expression for &variable
        if expr.type == "pointer_expression":
            # Check if it starts with &
            text = self._get_node_text(ctx, expr)
            return text.startswith("&")
        
        return False
    
    def _get_operator_text(self, ctx: RuleContext, expr) -> str:
        """Get the operator text from a unary expression."""
        try:
            if hasattr(expr, 'operator'):
                return self._get_node_text(ctx, expr.operator)
        except:
            pass
        return ""
    
    def _get_address_of_operand(self, expr) -> Optional[Any]:
        """Get the operand of an address-of expression."""
        try:
            # For tree-sitter, look for the operand in children
            # For pointer_expression: & identifier
            # Skip the & operator and get the identifier
            for child in expr.children:
                if child.type == "identifier":
                    return child
                # Could also be a more complex expression
                elif child.type in {"subscript_expression", "member_expression"}:
                    return child
        except:
            pass
        return None
    
    def _is_identifier_or_subscript(self, ctx: RuleContext, expr) -> bool:
        """Check if expression is an identifier or subscript expression."""
        if not expr or not hasattr(expr, 'kind'):
            return False
        return expr.type in {"identifier", "subscript_expression"}
    
    def _is_identifier_expression(self, ctx: RuleContext, expr) -> bool:
        """Check if expression is a simple identifier."""
        if not expr or not hasattr(expr, 'kind'):
            return False
        return expr.type == "identifier"
    
    def _is_array_declaration(self, ctx: RuleContext, decl_node) -> bool:
        """Check if declaration is an array declaration."""
        try:
            # Check for array declarator
            if hasattr(decl_node, 'declarator'):
                declarator = decl_node.declarator
                if hasattr(declarator, 'type') and declarator.type == "array_declarator":
                    return True
            
            # Check for array syntax in the text
            decl_text = self._get_node_text(ctx, decl_node)
            return "[" in decl_text and "]" in decl_text
        except:
            pass
        return False
    
    def _is_static_storage(self, ctx: RuleContext, decl_node) -> bool:
        """Check if declaration has static storage class."""
        try:
            # Check storage class specifier
            if hasattr(decl_node, 'storage_class'):
                storage_class = self._get_node_text(ctx, decl_node.storage_class)
                return "static" in storage_class
            
            # Check in the declaration text
            decl_text = self._get_node_text(ctx, decl_node)
            return "static" in decl_text
        except:
            pass
        return False
    
    def _return_type_is_pointer_like(self, ctx: RuleContext, return_type) -> bool:
        """Check if return type is pointer-like."""
        if not return_type:
            return False
        
        type_text = self._get_node_text(ctx, return_type)
        return "*" in type_text
    
    def _return_type_is_reference(self, ctx: RuleContext, return_type) -> bool:
        """Check if return type is a reference."""
        if not return_type:
            return False
        
        type_text = self._get_node_text(ctx, return_type)
        return "&" in type_text and "&&" not in type_text  # Single reference, not rvalue reference
    
    def _extract_identifier_name(self, ctx: RuleContext, node) -> Optional[str]:
        """Extract identifier name from various node types."""
        if not node:
            return None
            
        try:
            # Direct identifier
            if hasattr(node, 'type') and node.type in ["identifier", "id"]:
                return self._get_node_text(ctx, node)
            
            # For subscript expressions, get the base identifier
            if hasattr(node, 'type') and node.type == "subscript_expression":
                if hasattr(node, 'object'):
                    return self._extract_identifier_name(ctx, node.object)
                elif hasattr(node, 'array'):
                    return self._extract_identifier_name(ctx, node.array)
            
            # For other expressions, try to find nested identifier
            if hasattr(node, 'children'):
                children = node.children if callable(node.children) else node.children
                for child in children:
                    name = self._extract_identifier_name(ctx, child)
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
rule = MemoryReturnAddressOfLocalRule()
RULES = [rule]


