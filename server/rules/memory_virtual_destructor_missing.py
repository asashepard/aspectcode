"""
Memory Virtual Destructor Missing Rule

Detects C++ classes/structs that declare virtual functions but lack a virtual destructor.
This can lead to undefined behavior when deleting derived objects through base pointers.

Examples:
- class Base { virtual void f(); ~Base(); }; // BAD: non-virtual destructor
- class Base2 { virtual void f(); }; // BAD: implicit non-virtual destructor
- class Good { virtual ~Good(); virtual void f(); }; // OK: virtual destructor
"""

from typing import Iterable, Optional
try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class MemoryVirtualDestructorMissingRule(Rule):
    """Rule to detect classes with virtual functions but missing virtual destructor."""
    
    meta = RuleMeta(
        id="memory.virtual_destructor_missing",
        category="memory",
        tier=0,  # Syntax-only analysis
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects classes with virtual functions but missing virtual destructor",
        langs=["cpp"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit the file and check for classes missing virtual destructors."""
        if not ctx.tree:
            return
            
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
            
        for node in ctx.walk_nodes():
            if self._is_class_or_struct(node):
                yield from self._check_class(ctx, node)
    
    def _walk_nodes(self, ctx: RuleContext):
        """Walk all nodes in the syntax tree."""
        if not ctx.tree:
            return
            
        def walk(node):
            yield node
            for child in node.children:
                yield from walk(child)
                    
        yield from walk(ctx.tree.root_node)
    
    def _is_class_or_struct(self, node) -> bool:
        """Check if node is a class or struct specifier."""
        if not hasattr(node, 'type'):
            return False
        return node.type in {"class_specifier", "struct_specifier"}
    
    def _check_class(self, ctx: RuleContext, class_node) -> Iterable[Finding]:
        """Check a class for virtual destructor requirements."""
        # Get class name for reporting
        class_name = self._get_class_name(ctx, class_node)
        if not class_name:
            return
            
        # Skip final classes (not intended as base classes)
        if self._is_final_class(ctx, class_node):
            return
            
        # Analyze class members
        has_virtual_function = False
        destructor_info = self._analyze_destructor(ctx, class_node)
        
        # Check for virtual functions
        for member in self._get_class_members(class_node):
            if self._is_virtual_function(ctx, member):
                has_virtual_function = True
                break
        
        # If class has virtual functions but no virtual destructor, report issue
        if has_virtual_function and not destructor_info["is_virtual"]:
            name_span = self._get_class_name_span(ctx, class_node)
            if destructor_info["exists"]:
                message = f"Class '{class_name}' has virtual functions but a non-virtual destructor; make the destructor virtual"
            else:
                message = f"Class '{class_name}' has virtual functions but no virtual destructor; add 'virtual ~{class_name}()'"
                
            yield Finding(
                rule=self.meta.id,
                message=message,
                file=ctx.file_path,
                start_byte=name_span[0],
                end_byte=name_span[1],
                severity="error"
            )
    
    def _get_class_name(self, ctx: RuleContext, class_node) -> Optional[str]:
        """Extract the class name."""
        try:
            # Look for type_identifier in class declaration
            for child in class_node.children:
                if child.type == "type_identifier":
                    return self._get_node_text(ctx, child)
        except:
            pass
        return None
    
    def _get_class_name_span(self, ctx: RuleContext, class_node) -> tuple:
        """Get the span of the class name for reporting."""
        try:
            # Find the type_identifier node
            for child in class_node.children:
                if child.type == "type_identifier":
                    return self._get_node_span(ctx, child)
        except:
            pass
        
        # Fallback to class node span
        return self._get_node_span(ctx, class_node)
    
    def _is_final_class(self, ctx: RuleContext, class_node) -> bool:
        """Check if class is marked as final."""
        try:
            class_text = self._get_node_text(ctx, class_node)
            return "final" in class_text
        except:
            pass
        return False
    
    def _get_class_members(self, class_node):
        """Get all members of a class."""
        try:
            # Look for field_declaration_list (class body)
            for child in class_node.children:
                if child.type == "field_declaration_list":
                    # Return all children of the class body
                    return child.children
        except:
            pass
        return []
    
    def _is_virtual_function(self, ctx: RuleContext, member_node) -> bool:
        """Check if a member is a virtual function."""
        try:
            # Check for virtual functions in different node types
            if member_node.type in {"function_definition", "declaration", "field_declaration"}:
                # Check if the member contains 'virtual' keyword
                member_text = self._get_node_text(ctx, member_node)
                return "virtual" in member_text and "(" in member_text  # Has function signature
        except:
            pass
        return False
    
    def _analyze_destructor(self, ctx: RuleContext, class_node) -> dict:
        """Analyze destructor presence and virtuality."""
        result = {"exists": False, "is_virtual": False, "node": None}
        
        try:
            class_name = self._get_class_name(ctx, class_node)
            if not class_name:
                return result
                
            destructor_pattern = f"~{class_name}"
            
            for member in self._get_class_members(class_node):
                member_text = self._get_node_text(ctx, member)
                
                # Check if this member is a destructor
                if destructor_pattern in member_text:
                    result["exists"] = True
                    result["node"] = member
                    
                    # Check if destructor is virtual
                    if "virtual" in member_text:
                        result["is_virtual"] = True
                    break
        except:
            pass
            
        return result
    
    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
            
        try:
            # Try getting text from span
            if hasattr(ctx.adapter, 'node_span') and ctx.text:
                start, end = ctx.adapter.node_span(node)
                if start is not None and end is not None and start >= 0 and end <= len(ctx.text):
                    return ctx.text[start:end]
        except:
            pass
            
        try:
            # Try direct text attribute
            if hasattr(node, 'text'):
                text = node.text
                if isinstance(text, str):
                    return text
                elif hasattr(text, 'decode'):
                    return text.decode('utf-8', errors='ignore')
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
rule = MemoryVirtualDestructorMissingRule()
RULES = [rule]


