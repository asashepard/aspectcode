"""
Rule: ident.shadowing

Detects variable shadowing in Python - when a variable in an inner scope
shadows a variable, import, or builtin from an outer scope.

Supports: Python
"""

import re
from typing import Iterator, Set, Dict, Optional, List
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext, Edit
from engine.scopes import Symbol


class IdentShadowingRule:
    """
    Detects variable shadowing in Python.
    
    Examples of shadowing:
    
    Shadowing outer variable:
        x = 10
        def func():
            x = 20  # Shadows outer x
    
    Shadowing import:
        import os
        def func():
            os = "not the module"  # Shadows import
    
    Shadowing builtin:
        def func():
            list = []  # Shadows builtin list
    """
    
    meta = RuleMeta(
        id="ident.shadowing",
        category="ident",
        tier=1,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects variable shadowing where inner scope variables hide outer scope or builtin names",
        langs=["python"]
    )
    
    requires = Requires(
        raw_text=False,
        syntax=True,
        scopes=True,
        project_graph=False
    )
    
    # Python builtins that are commonly shadowed
    PYTHON_BUILTINS = {
        'abs', 'all', 'any', 'ascii', 'bin', 'bool', 'bytearray', 'bytes',
        'callable', 'chr', 'classmethod', 'compile', 'complex', 'delattr',
        'dict', 'dir', 'divmod', 'enumerate', 'eval', 'exec', 'filter',
        'float', 'format', 'frozenset', 'getattr', 'globals', 'hasattr',
        'hash', 'help', 'hex', 'id', 'input', 'int', 'isinstance', 'issubclass',
        'iter', 'len', 'list', 'locals', 'map', 'max', 'memoryview', 'min',
        'next', 'object', 'oct', 'open', 'ord', 'pow', 'print', 'property',
        'range', 'repr', 'reversed', 'round', 'set', 'setattr', 'slice',
        'sorted', 'staticmethod', 'str', 'sum', 'super', 'tuple', 'type',
        'vars', 'zip', '__import__', '__name__', '__file__', '__builtins__',
        'Exception', 'BaseException', 'StopIteration', 'KeyboardInterrupt',
        'SystemExit', 'GeneratorExit', 'ValueError', 'TypeError', 'AttributeError',
        'NameError', 'IndexError', 'KeyError', 'FileNotFoundError', 'OSError',
        'IOError', 'ImportError', 'ModuleNotFoundError', 'RuntimeError',
        'NotImplementedError', 'ZeroDivisionError', 'OverflowError', 'True',
        'False', 'None'
    }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the context to find variable shadowing."""
        if ctx.scopes is None:
            return
        
        # Only handle Python files
        if not ctx.file_path.endswith('.py'):
            return
        
        # Analyze each scope for shadowing
        # ctx.scopes is a ScopeGraph, we need to iterate through its scopes
        for scope_id in ctx.scopes._scopes:
            scope = ctx.scopes.get_scope(scope_id)
            if scope:
                yield from self._analyze_scope_for_shadowing(scope, ctx)
    
    def _analyze_scope_for_shadowing(self, scope, ctx: RuleContext) -> Iterator[Finding]:
        """Analyze a single scope for variable shadowing."""
        # Get all defined variables in this scope
        defined_vars = self._get_defined_variables(scope, ctx)
        
        for var_symbol in defined_vars:
            # Check what this variable is shadowing
            shadowed_info = self._find_shadowed_entity(var_symbol, scope, ctx)
            
            if shadowed_info:
                yield self._create_shadowing_finding(var_symbol, shadowed_info, ctx)
    
    def _get_defined_variables(self, scope, ctx: RuleContext) -> List[Symbol]:
        """Get all variables defined in this scope (not references)."""
        # Get symbols from the scope graph for this specific scope
        symbols_in_scope = ctx.scopes.symbols_in_scope(scope.id)
        
        defined_vars = []
        for symbol in symbols_in_scope:
            # Look for variable definitions, assignments, parameters
            if symbol.kind in ['variable', 'parameter', 'assignment', 'local', 'param']:
                defined_vars.append(symbol)
        
        return defined_vars
    
    def _find_shadowed_entity(self, var_symbol: Symbol, current_scope, ctx: RuleContext) -> Optional[Dict]:
        """Find what entity (if any) this variable is shadowing."""
        var_name = var_symbol.name
        
        # Skip single underscore (conventional throwaway variable)
        if var_name == '_':
            return None
        
        # Check if shadowing a builtin
        if var_name in self.PYTHON_BUILTINS:
            return {
                'type': 'builtin',
                'name': var_name,
                'location': 'builtin scope',
                'suggestion': self._suggest_builtin_rename(var_name)
            }
        
        # Check if shadowing something from outer scopes
        outer_entity = self._find_in_outer_scopes(var_name, current_scope, ctx)
        if outer_entity:
            return outer_entity
        
        return None
    
    def _find_in_outer_scopes(self, var_name: str, current_scope, ctx: RuleContext) -> Optional[Dict]:
        """Find if the variable name exists in any outer scope."""
        # Use the scope graph to resolve what this variable would reference
        # Start from the parent scope and walk up the hierarchy
        parent_scope_id = current_scope.parent_id
        
        while parent_scope_id is not None:
            # Check all symbols in the parent scope
            symbols_in_parent = ctx.scopes.symbols_in_scope(parent_scope_id)
            
            for symbol in symbols_in_parent:
                if symbol.name == var_name:
                    parent_scope = ctx.scopes.get_scope(parent_scope_id)
                    
                    # Determine what kind of entity we're shadowing
                    if symbol.kind == 'import':
                        return {
                            'type': 'import',
                            'name': var_name,
                            'location': self._get_scope_description(parent_scope),
                            'original_symbol': symbol,
                            'suggestion': self._suggest_import_rename(var_name)
                        }
                    elif symbol.kind in ['variable', 'parameter', 'assignment', 'local', 'param']:
                        return {
                            'type': 'variable',
                            'name': var_name,
                            'location': self._get_scope_description(parent_scope),
                            'original_symbol': symbol,
                            'suggestion': self._suggest_variable_rename(var_name)
                        }
                    elif symbol.kind == 'function':
                        return {
                            'type': 'function',
                            'name': var_name,
                            'location': self._get_scope_description(parent_scope),
                            'original_symbol': symbol,
                            'suggestion': self._suggest_function_rename(var_name)
                        }
                    elif symbol.kind == 'class':
                        return {
                            'type': 'class',
                            'name': var_name,
                            'location': self._get_scope_description(parent_scope),
                            'original_symbol': symbol,
                            'suggestion': self._suggest_class_rename(var_name)
                        }
            
            # Move to the next parent scope
            parent_scope = ctx.scopes.get_scope(parent_scope_id)
            parent_scope_id = parent_scope.parent_id if parent_scope else None
            
        return None
    
    def _get_scope_description(self, scope) -> str:
        """Get a human-readable description of where the scope is."""
        # In a real implementation, scope would have more metadata
        # For now, return a generic description
        if hasattr(scope, 'scope_type'):
            return f"{scope.scope_type} scope"
        return "outer scope"
    
    def _suggest_builtin_rename(self, name: str) -> str:
        """Suggest a rename for a shadowed builtin."""
        common_renames = {
            'list': 'items',
            'dict': 'mapping',
            'set': 'items_set',
            'str': 'text',
            'int': 'number',
            'float': 'value',
            'bool': 'flag',
            'type': 'cls',
            'input': 'user_input',
            'open': 'file_open',
            'map': 'mapping',
            'filter': 'filtered',
            'zip': 'zipped',
            'sum': 'total',
            'max': 'maximum',
            'min': 'minimum',
            'len': 'length',
            'id': 'identifier',
            'hash': 'hash_value',
        }
        
        if name in common_renames:
            return common_renames[name]
        
        # Generic suggestions
        return f"{name}_var" if len(name) > 3 else f"my_{name}"
    
    def _suggest_import_rename(self, name: str) -> str:
        """Suggest a rename for a variable that shadows an import."""
        return f"{name}_value"
    
    def _suggest_variable_rename(self, name: str) -> str:
        """Suggest a rename for a variable that shadows another variable."""
        return f"inner_{name}"
    
    def _suggest_function_rename(self, name: str) -> str:
        """Suggest a rename for a variable that shadows a function."""
        return f"{name}_var"
    
    def _suggest_class_rename(self, name: str) -> str:
        """Suggest a rename for a variable that shadows a class."""
        return f"{name}_instance"
    
    def _create_shadowing_finding(self, var_symbol: Symbol, shadowed_info: Dict, ctx: RuleContext) -> Finding:
        """Create a finding for variable shadowing."""
        var_name = var_symbol.name
        shadowed_type = shadowed_info['type']
        shadowed_location = shadowed_info['location']
        suggestion = shadowed_info['suggestion']
        
        # Generate appropriate message
        if shadowed_type == 'builtin':
            message = f"'{var_name}' shadows the built-in '{var_name}'—use a different name to avoid confusion."
        elif shadowed_type == 'import':
            message = f"'{var_name}' shadows the imported '{var_name}' from {shadowed_location}—use a different name."
        else:
            message = f"'{var_name}' shadows {shadowed_type} '{var_name}' from {shadowed_location}—use a different name."
        
        # Generate autofix (suggest-only)
        autofix_edits = self._generate_autofix_suggestions(var_symbol, suggestion, ctx)
        
        # Create metadata
        meta = {
            "variable_name": var_name,
            "shadowed_type": shadowed_type,
            "shadowed_location": shadowed_location,
            "suggested_name": suggestion,
            "is_builtin": shadowed_type == 'builtin'
        }
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            severity="warning",
            file=ctx.file_path,
            start_byte=var_symbol.start_byte,
            end_byte=var_symbol.end_byte,
            autofix=autofix_edits,
            meta=meta
        )
        
        return finding
    
    def _generate_autofix_suggestions(self, var_symbol: Symbol, suggestion: str, ctx: RuleContext) -> Optional[List[Edit]]:
        """Generate autofix suggestions (suggest-only)."""
        # For suggest-only, we return None but provide the suggestion in metadata
        return None


# Export the rule instance
RULES = [IdentShadowingRule()]

