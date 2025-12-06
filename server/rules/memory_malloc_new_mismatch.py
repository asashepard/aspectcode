"""
Memory Malloc/New Mismatch Rule

Detects C++ allocation/deallocation mismatches:
- new ... free(p) (should be delete p)
- new[] ... delete p (should be delete[] p)  
- malloc/calloc/realloc/... ... delete/delete[] (should be free(p))
- Any cross-form mismatch

Examples:
- int* p = new int; free(p); // BAD: new + free
- int* p = (int*)malloc(4); delete p; // BAD: malloc + delete
- int* p = new int[3]; delete p; // BAD: new[] + delete
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


class MemoryMallocNewMismatchRule(Rule):
    """Rule to detect allocation/deallocation mismatches in C++."""
    
    meta = RuleMeta(
        id="memory.malloc_new_mismatch",
        category="memory",
        tier=0,  # Syntax-only analysis
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects allocation/deallocation mismatches in C++",
        langs=["cpp"]
    )
    
    requires = Requires(syntax=True)
    
    # Malloc family functions
    MALLOC_FAMILY = {"malloc", "calloc", "realloc", "strdup", "strndup", "aligned_alloc", "posix_memalign"}
    
    # Valid allocation/deallocation pairs
    VALID_PAIRS = {("new", "delete"), ("new_array", "delete_array"), ("malloc", "free")}
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for allocation/deallocation mismatches."""
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
        """Check a function for allocation/deallocation mismatches."""
        # Track variable provenance: var_name -> allocation_type
        provenance: Dict[str, str] = {}
        
        # Find the function body
        body = self._get_function_body(function_node)
        if not body:
            return
            
        # Walk through statements in the function
        for stmt in self._get_statements(body):
            # Check for allocations
            allocation = self._get_allocation_info(ctx, stmt)
            if allocation:
                var_name, alloc_type = allocation
                if var_name:
                    provenance[var_name] = alloc_type
                continue
            
            # Check for reassignments that clear provenance
            reassignment = self._get_reassignment_info(ctx, stmt)
            if reassignment:
                var_name, is_allocator = reassignment
                if var_name and not is_allocator:
                    provenance.pop(var_name, None)
                continue
            
            # Check for deallocations
            deallocation = self._get_deallocation_info(ctx, stmt)
            if deallocation:
                var_name, dealloc_type, node = deallocation
                if var_name in provenance:
                    alloc_type = provenance[var_name]
                    if not self._is_valid_pair(alloc_type, dealloc_type):
                        yield Finding(
                            rule=self.meta.id,
                            message=f"Mismatched allocation/deallocation for '{var_name}': allocated with {alloc_type} but released with {dealloc_type}",
                            file=ctx.file_path,
                            start_byte=node.start_byte,
                            end_byte=node.end_byte,
                            severity="error"
                        )
                    else:
                        # Valid pair, clear provenance
                        provenance.pop(var_name, None)
    
    def _get_function_body(self, function_node):
        """Get the compound statement (body) of a function."""
        for child in function_node.children:
            if child.type == "compound_statement":
                return child
        return None
    
    def _get_statements(self, body_node):
        """Get all statements from a compound statement."""
        statements = []
        for child in body_node.children:
            if child.type not in {"{", "}"}:  # Skip braces
                statements.append(child)
        return statements
    
    def _get_allocation_info(self, ctx: RuleContext, stmt) -> Optional[Tuple[str, str]]:
        """Get allocation info from a statement. Returns (var_name, alloc_type) or None."""
        # Handle declarations and assignments
        if stmt.type in {"declaration", "expression_statement"}:
            # For declarations like: int* p = new int;
            if stmt.type == "declaration":
                var_name = self._get_declared_variable_name(stmt)
                initializer = self._get_initializer(stmt)
                if var_name and initializer:
                    alloc_type = self._get_allocation_type(ctx, initializer)
                    if alloc_type:
                        return (var_name, alloc_type)
            
            # For assignments like: p = new int;
            elif stmt.type == "expression_statement":
                expr = self._get_expression_from_statement(stmt)
                if expr and expr.type == "assignment_expression":
                    var_name = self._get_assignment_target(expr)
                    rhs = self._get_assignment_value(expr)
                    if var_name and rhs:
                        alloc_type = self._get_allocation_type(ctx, rhs)
                        if alloc_type:
                            return (var_name, alloc_type)
        
        return None
    
    def _get_reassignment_info(self, ctx: RuleContext, stmt) -> Optional[Tuple[str, bool]]:
        """Get reassignment info. Returns (var_name, is_allocator) or None."""
        if stmt.type == "expression_statement":
            expr = self._get_expression_from_statement(stmt)
            if expr and expr.type == "assignment_expression":
                var_name = self._get_assignment_target(expr)
                rhs = self._get_assignment_value(expr)
                if var_name and rhs:
                    is_allocator = bool(self._get_allocation_type(ctx, rhs))
                    return (var_name, is_allocator)
        return None
    
    def _get_deallocation_info(self, ctx: RuleContext, stmt) -> Optional[Tuple[str, str, any]]:
        """Get deallocation info. Returns (var_name, dealloc_type, node) or None."""
        # Handle delete expressions
        if stmt.type == "expression_statement":
            expr = self._get_expression_from_statement(stmt)
            if expr and expr.type in {"delete_expression", "call_expression"}:
                if expr.type == "delete_expression":
                    var_name = self._get_deleted_variable_name(expr)
                    is_array = self._is_array_delete(expr)
                    dealloc_type = "delete_array" if is_array else "delete"
                    if var_name:
                        return (var_name, dealloc_type, expr)
                
                elif expr.type == "call_expression":
                    callee_name = self._get_function_name(ctx, expr)
                    if callee_name == "free":
                        args = self._get_call_arguments(expr)
                        if args:
                            var_name = self._get_argument_variable_name(ctx, args[0])
                            if var_name:
                                return (var_name, "free", expr)
        
        return None
    
    def _get_allocation_type(self, ctx: RuleContext, node) -> Optional[str]:
        """Determine allocation type from a node."""
        if node.type == "new_expression":
            # Check if this is array new by looking for new_declarator
            for child in node.children:
                if child.type == "new_declarator":
                    return "new_array"
            return "new"
        elif node.type == "cast_expression":
            # Handle cast expressions like (int*)malloc(4)
            # Look for the actual expression being cast
            for child in node.children:
                if child.type == "call_expression":
                    return self._get_allocation_type(ctx, child)
        elif node.type in {"call_expression"}:
            # Handle array new: new int[size] might be parsed differently
            text = self._get_node_text(ctx, node)
            if "new" in text and "[" in text and "]" in text:
                return "new_array"
            # Handle function calls like malloc
            callee_name = self._get_function_name(ctx, node)
            if callee_name in self.MALLOC_FAMILY:
                return "malloc"
        elif node.type == "subscript_expression":
            # Handle new[] expressions that might be parsed as subscript
            for child in node.children:
                if self._get_node_text(ctx, child).strip() == "new":
                    return "new_array"
        
        # Try to detect new[] by looking at text content
        text = self._get_node_text(ctx, node)
        if "new" in text:
            if "[" in text and "]" in text:
                return "new_array"
            else:
                return "new"
        
        return None
    
    def _get_declared_variable_name(self, declaration_node) -> Optional[str]:
        """Get variable name from a declaration."""
        for child in declaration_node.children:
            if child.type == "init_declarator":
                # Look for identifier in nested declarators (pointer_declarator, etc.)
                return self._find_identifier_in_declarator(child)
        return None
    
    def _find_identifier_in_declarator(self, declarator_node) -> Optional[str]:
        """Recursively find identifier in declarator node."""
        for child in declarator_node.children:
            if child.type == "identifier":
                return child.text.decode('utf-8')
            elif child.type in {"pointer_declarator", "array_declarator", "function_declarator"}:
                # Recursively search in nested declarators
                result = self._find_identifier_in_declarator(child)
                if result:
                    return result
        return None
    
    def _get_initializer(self, declaration_node):
        """Get initializer from a declaration."""
        for child in declaration_node.children:
            if child.type == "init_declarator":
                for i, subchild in enumerate(child.children):
                    if subchild.type == "=" and i + 1 < len(child.children):
                        return child.children[i + 1]
        return None
    
    def _get_expression_from_statement(self, stmt):
        """Get expression from an expression statement."""
        for child in stmt.children:
            if child.type != ";":
                return child
        return None
    
    def _get_assignment_target(self, assignment_expr) -> Optional[str]:
        """Get target variable name from assignment expression."""
        if assignment_expr.children:
            left = assignment_expr.children[0]
            if left.type == "identifier":
                return left.text.decode('utf-8')
        return None
    
    def _get_assignment_value(self, assignment_expr):
        """Get value from assignment expression."""
        for i, child in enumerate(assignment_expr.children):
            if child.type == "=" and i + 1 < len(assignment_expr.children):
                return assignment_expr.children[i + 1]
        return None
    
    def _get_deleted_variable_name(self, delete_expr) -> Optional[str]:
        """Get variable name from delete expression."""
        for child in delete_expr.children:
            if child.type == "identifier":
                return child.text.decode('utf-8')
        return None
    
    def _is_array_delete(self, delete_expr) -> bool:
        """Check if this is array delete (delete[])."""
        text = delete_expr.text.decode('utf-8') if hasattr(delete_expr, 'text') else ""
        return "delete[]" in text or "delete []" in text
    
    def _get_function_name(self, ctx: RuleContext, call_expr) -> Optional[str]:
        """Get function name from call expression."""
        for child in call_expr.children:
            if child.type == "identifier":
                return child.text.decode('utf-8')
        return None
    
    def _get_call_arguments(self, call_expr):
        """Get arguments from call expression."""
        for child in call_expr.children:
            if child.type == "argument_list":
                args = []
                for subchild in child.children:
                    if subchild.type not in {"(", ")", ","}:
                        args.append(subchild)
                return args
        return []
    
    def _get_argument_variable_name(self, ctx: RuleContext, arg_node) -> Optional[str]:
        """Get variable name from argument node."""
        if arg_node.type == "identifier":
            return arg_node.text.decode('utf-8')
        return None
    
    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        try:
            return ctx.text[node.start_byte:node.end_byte]
        except:
            return ""
    
    def _is_valid_pair(self, alloc_type: str, dealloc_type: str) -> bool:
        """Check if allocation/deallocation pair is valid."""
        return (alloc_type, dealloc_type) in self.VALID_PAIRS


