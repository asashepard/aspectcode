"""
Memory Malloc Null Check Missing Rule

Detects when the result of malloc family functions (malloc, calloc, realloc, strdup, etc.)
is used without a prior null check in C/C++. This can lead to undefined behavior if the
allocation fails.

Rule ID: memory.malloc_null_check_missing
Category: memory
Severity: warn  
Priority: P1
Languages: c, cpp
Autofix: suggest-only
"""

from typing import Iterable, Optional, Dict, Set, Tuple

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryMallocNullCheckMissingRule(Rule):
    """Rule to detect malloc usage without null checks in C/C++."""
    
    meta = RuleMeta(
        id="memory.malloc_null_check_missing",
        category="memory", 
        tier=0,  # Syntax-only analysis
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects when malloc family allocations are used without null checks",
        langs=["c", "cpp"]
    )
    requires = Requires(syntax=True)

    # Functions that allocate memory and can return NULL
    MALLOC_FAMILY = {
        "malloc", "calloc", "realloc", "strdup", "strndup", 
        "aligned_alloc", "posix_memalign"
    }
    
    # Literals that represent null in checks
    NULL_TOKENS = {"NULL", "nullptr", "0"}
    
    # Functions that commonly dereference their pointer arguments
    DEREF_CONSUMERS = {
        "memcpy", "memmove", "memset", "strcpy", "strncpy", 
        "strlen", "fwrite", "fread", "printf", "sprintf",
        "snprintf", "fprintf"
    }

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for malloc null check issues."""
        if not ctx.tree:
            return
            
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            
        for function_node in self._find_functions(ctx):
            yield from self._check_function(ctx, function_node)

    def _find_functions(self, ctx: RuleContext):
        """Find all function definitions in the tree."""
        def walk(node):
            if node.type in {"function_definition", "method_definition", "constructor_definition"}:
                yield node
            for child in node.children:
                yield from walk(child)
        
        yield from walk(ctx.tree.root_node)

    def _check_function(self, ctx: RuleContext, function_node) -> Iterable[Finding]:
        """Check a function for malloc usage without null checks."""
        # Track variables that have been assigned malloc results
        # var_name -> {"alloc_node": node, "checked": bool}
        pending_allocations = {}
        
        # Get function body statements
        body = self._get_function_body(function_node)
        if not body:
            return
            
        statements = self._get_statements(body)
        
        for stmt in statements:
            # Check for new allocations
            allocation = self._detect_allocation(ctx, stmt)
            if allocation:
                var_name, alloc_node = allocation
                pending_allocations[var_name] = {
                    "alloc_node": alloc_node, 
                    "checked": False
                }
                continue
            
            # Check if this statement contains null checks for tracked variables
            for var_name in list(pending_allocations.keys()):
                if self._statement_checks_variable(ctx, stmt, var_name):
                    pending_allocations[var_name]["checked"] = True
            
            # Check for unguarded uses of allocated variables
            for var_name, allocation_info in list(pending_allocations.items()):
                if not allocation_info["checked"]:
                    use_node = self._find_unguarded_use(ctx, stmt, var_name)
                    if use_node:
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Result of allocation assigned to '{var_name}' is used without a prior null check.",
                            file="",  # Will be set by the engine
                            start_byte=use_node.start_byte,
                            end_byte=use_node.end_byte,
                            severity="warning"
                        )
                        # Mark as checked to avoid duplicate reports
                        pending_allocations[var_name]["checked"] = True
            
            # Check for reassignments that reset tracking
            assigned_var = self._get_assigned_variable(ctx, stmt)
            if assigned_var and assigned_var in pending_allocations:
                # Variable is being reassigned, stop tracking the malloc result
                del pending_allocations[assigned_var]

    def _get_function_body(self, fn_node):
        """Extract the function body from a function node."""
        for child in fn_node.children:
            if child.type == "compound_statement":
                return child
        return None

    def _get_statements(self, body_node):
        """Get all statements from a function body."""
        statements = []
        for child in body_node.children:
            if child.type.endswith("_statement") or child.type == "declaration":
                statements.append(child)
        return statements

    def _detect_allocation(self, ctx: RuleContext, stmt):
        """
        Detect if this statement assigns the result of a malloc family function.
        Returns (variable_name, allocation_node) or None.
        """
        # Handle assignment statements: p = malloc(size);
        if stmt.type == "expression_statement":
            expr = self._get_first_child(stmt)
            if expr and expr.type == "assignment_expression":
                left = self._get_child_by_field(expr, "left")
                right = self._get_child_by_field(expr, "right")
                
                if left and right:
                    var_name = self._extract_variable_name(left)
                    if var_name and self._is_malloc_call(ctx, right):
                        return (var_name, right)
        
        # Handle variable declarations: char* p = malloc(size);
        elif stmt.type == "declaration":
            declarator = self._find_declarator_with_initializer(stmt)
            if declarator:
                var_name = self._extract_variable_name(declarator)
                initializer = self._get_child_by_field(declarator, "value")
                
                if var_name and initializer and self._is_malloc_call(ctx, initializer):
                    return (var_name, initializer)
        
        return None

    def _find_declarator_with_initializer(self, decl_node):
        """Find a declarator that has an initializer in a declaration."""
        for child in decl_node.children:
            if child.type == "init_declarator":
                return child
        return None

    def _is_malloc_call(self, ctx: RuleContext, node):
        """Check if a node represents a call to a malloc family function."""
        if node.type == "call_expression":
            function_node = self._get_child_by_field(node, "function")
            if function_node:
                func_name = self._get_node_text(ctx, function_node)
                return func_name in self.MALLOC_FAMILY
        
        # Handle cast expressions: (char*)malloc(size)
        elif node.type == "cast_expression":
            value = self._get_child_by_field(node, "value")
            return value and self._is_malloc_call(ctx, value)
        
        return False

    def _extract_variable_name(self, node):
        """Extract variable name from various node types."""
        if node.type == "identifier":
            return node.text.decode('utf-8') if isinstance(node.text, bytes) else node.text
        elif node.type == "pointer_declarator":
            declarator = self._get_child_by_field(node, "declarator")
            return self._extract_variable_name(declarator) if declarator else None
        elif node.type == "init_declarator":
            declarator = self._get_child_by_field(node, "declarator")
            return self._extract_variable_name(declarator) if declarator else None
        
        # Look for identifier children
        for child in node.children:
            if child.type == "identifier":
                return child.text.decode('utf-8') if isinstance(child.text, bytes) else child.text
        
        return None

    def _statement_checks_variable(self, ctx: RuleContext, stmt, var_name):
        """
        Check if this statement contains a null check for the given variable.
        Handles patterns like:
        - if (!p) return;
        - if (p == NULL) { ... }
        - if (p != NULL) { ... }
        - assert(p);
        - if (!(p = malloc(...))) { ... }
        """
        stmt_text = self._get_node_text(ctx, stmt).replace(" ", "").replace("\t", "").replace("\n", "")
        
        # Direct null checks
        patterns = [
            f"!{var_name}",
            f"{var_name}==NULL",
            f"{var_name}==nullptr", 
            f"{var_name}!=NULL",
            f"{var_name}!=nullptr",
            f"NULL=={var_name}",
            f"nullptr=={var_name}",
            f"NULL!={var_name}",
            f"nullptr!={var_name}"
        ]
        
        for pattern in patterns:
            if pattern in stmt_text:
                return True
        
        # Assert checks
        if "assert(" in stmt_text and var_name in stmt_text:
            return True
        
        # Inline allocation and check: if (!(p = malloc(...))) ...
        if (f"{var_name}=" in stmt_text and 
            any(malloc_func in stmt_text for malloc_func in self.MALLOC_FAMILY) and
            ("if(" in stmt_text or "while(" in stmt_text)):
            return True
        
        return False

    def _find_unguarded_use(self, ctx: RuleContext, stmt, var_name):
        """
        Find the first use of var_name that requires it to be non-null.
        Returns the node of the problematic use, or None.
        """
        def walk(node):
            # Pointer dereference: *p
            if node.type == "pointer_expression":
                operand = self._get_child_by_field(node, "argument")
                if operand and self._get_node_text(ctx, operand) == var_name:
                    return node
            
            # Member access: p->field
            elif node.type == "field_expression":
                object_node = self._get_child_by_field(node, "argument")
                if object_node and self._get_node_text(ctx, object_node) == var_name:
                    return node
            
            # Array subscript: p[i]
            elif node.type == "subscript_expression":
                array_node = self._get_child_by_field(node, "argument")
                if array_node and self._get_node_text(ctx, array_node) == var_name:
                    return node
            
            # Function calls that likely dereference
            elif node.type == "call_expression":
                function_node = self._get_child_by_field(node, "function")
                if function_node:
                    func_name = self._get_node_text(ctx, function_node)
                    if func_name in self.DEREF_CONSUMERS:
                        # Check if var_name is passed as an argument
                        args = self._get_child_by_field(node, "arguments")
                        if args and self._contains_variable_usage(ctx, args, var_name):
                            return node
            
            # Recursively check children
            for child in node.children:
                result = walk(child)
                if result:
                    return result
            
            return None
        
        return walk(stmt)

    def _contains_variable_usage(self, ctx: RuleContext, args_node, var_name):
        """Check if the arguments contain usage of the given variable."""
        for child in args_node.children:
            if child.type == "identifier" and self._get_node_text(ctx, child) == var_name:
                return True
            # Recursively check
            if self._contains_variable_usage(ctx, child, var_name):
                return True
        return False

    def _get_assigned_variable(self, ctx: RuleContext, stmt):
        """Extract the variable being assigned to in an assignment statement."""
        if stmt.type == "expression_statement":
            expr = self._get_first_child(stmt)
            if expr and expr.type == "assignment_expression":
                left = self._get_child_by_field(expr, "left")
                if left:
                    return self._extract_variable_name(left)
        return None

    def _get_first_child(self, node):
        """Get the first child of a node."""
        children = list(node.children)
        return children[0] if children else None

    def _get_child_by_field(self, node, field_name):
        """Get a child node by field name."""
        # Tree-sitter specific field access
        if hasattr(node, 'child_by_field_name'):
            return node.child_by_field_name(field_name)
        
        # Fallback: use heuristics based on node type and position
        if field_name == "left" and node.type == "assignment_expression":
            return node.children[0] if node.children else None
        elif field_name == "right" and node.type == "assignment_expression":
            return node.children[2] if len(node.children) > 2 else None
        elif field_name == "function" and node.type == "call_expression":
            return node.children[0] if node.children else None
        elif field_name == "arguments" and node.type == "call_expression":
            return node.children[1] if len(node.children) > 1 else None
        elif field_name == "argument" and node.type in {"pointer_expression", "field_expression", "subscript_expression"}:
            return node.children[0] if node.children else None
        elif field_name == "value" and node.type in {"cast_expression", "init_declarator"}:
            return node.children[-1] if node.children else None
        elif field_name == "declarator" and node.type in {"pointer_declarator", "init_declarator"}:
            return node.children[0] if node.children else None
        
        return None

    def _get_node_text(self, ctx: RuleContext, node):
        """Get the text content of a node."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8')
            return text
        
        # Fallback: get text from source
        if ctx.raw_text and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.raw_text[node.start_byte:node.end_byte]
        
        return ""


# Register the rule for auto-discovery
rule = MemoryMallocNullCheckMissingRule()
RULES = [rule]


