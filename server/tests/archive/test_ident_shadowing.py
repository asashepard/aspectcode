"""
Comprehensive tests for ident.shadowing rule.

Tests variable shadowing detection in Python.
"""

import pytest
from unittest.mock import Mock, MagicMock
from engine.types import RuleContext, Edit, Finding
from engine.scopes import Symbol, Scope
from rules.ident_shadowing import IdentShadowingRule


class TestIdentShadowingRule:
    """Test the ident shadowing rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = IdentShadowingRule()
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "ident.shadowing"
        assert self.rule.meta.category == "ident"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.priority == "P0"
        assert "python" in self.rule.meta.langs
        assert self.rule.requires.scopes is True
    
    # Builtin Shadowing Tests
    def test_builtin_shadowing_detection(self):
        """Test detection of builtin shadowing."""
        var_symbol = Mock()
        var_symbol.name = "list"
        var_symbol.kind = "variable"
        
        scope = Mock()
        ctx = Mock()
        ctx.scopes = [scope]
        
        shadowed_info = self.rule._find_shadowed_entity(var_symbol, scope, ctx)
        
        assert shadowed_info is not None
        assert shadowed_info['type'] == 'builtin'
        assert shadowed_info['name'] == 'list'
        assert shadowed_info['suggestion'] == 'items'
    
    def test_builtin_suggestions(self):
        """Test builtin rename suggestions."""
        test_cases = [
            ('list', 'items'),
            ('dict', 'mapping'),
            ('str', 'text'),
            ('int', 'number'),
            ('bool', 'flag'),
            ('type', 'cls'),
            ('len', 'length'),
            ('id', 'identifier'),
            ('open', 'file_open'),
            ('input', 'user_input'),
        ]
        
        for builtin_name, expected_suggestion in test_cases:
            suggestion = self.rule._suggest_builtin_rename(builtin_name)
            assert suggestion == expected_suggestion
    
    def test_builtin_generic_suggestions(self):
        """Test generic builtin suggestions."""
        # Short names get "my_" prefix
        assert self.rule._suggest_builtin_rename("all") == "my_all"
        assert self.rule._suggest_builtin_rename("any") == "my_any"
        
        # Longer names get "_var" suffix
        assert self.rule._suggest_builtin_rename("enumerate") == "enumerate_var"
        assert self.rule._suggest_builtin_rename("staticmethod") == "staticmethod_var"
    
    # Scope Detection Tests
    def test_get_defined_variables(self):
        """Test getting defined variables from scope."""
        # Create mock symbols
        var_symbol = Mock()
        var_symbol.kind = "variable"
        
        param_symbol = Mock()
        param_symbol.kind = "parameter"
        
        assignment_symbol = Mock()
        assignment_symbol.kind = "assignment"
        
        ref_symbol = Mock()
        ref_symbol.kind = "reference"  # Should not be included
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [var_symbol, param_symbol, assignment_symbol, ref_symbol]
        
        defined_vars = self.rule._get_defined_variables(scope)
        
        assert len(defined_vars) == 3
        assert var_symbol in defined_vars
        assert param_symbol in defined_vars
        assert assignment_symbol in defined_vars
        assert ref_symbol not in defined_vars
    
    def test_find_in_outer_scopes_import(self):
        """Test finding shadowed import."""
        var_name = "os"
        
        # Create mock import symbol
        import_symbol = Mock()
        import_symbol.name = "os"
        import_symbol.kind = "import"
        
        # Create mock scopes
        current_scope = Mock()
        outer_scope = Mock()
        outer_scope.symbols = [import_symbol]
        
        ctx = Mock()
        ctx.scopes = [current_scope, outer_scope]
        
        result = self.rule._find_in_outer_scopes(var_name, current_scope, ctx)
        
        assert result is not None
        assert result['type'] == 'import'
        assert result['name'] == 'os'
        assert result['suggestion'] == 'os_value'
    
    def test_find_in_outer_scopes_variable(self):
        """Test finding shadowed variable."""
        var_name = "x"
        
        # Create mock variable symbol
        var_symbol = Mock()
        var_symbol.name = "x"
        var_symbol.kind = "variable"
        
        # Create mock scopes
        current_scope = Mock()
        outer_scope = Mock()
        outer_scope.symbols = [var_symbol]
        
        ctx = Mock()
        ctx.scopes = [current_scope, outer_scope]
        
        result = self.rule._find_in_outer_scopes(var_name, current_scope, ctx)
        
        assert result is not None
        assert result['type'] == 'variable'
        assert result['name'] == 'x'
        assert result['suggestion'] == 'inner_x'
    
    def test_find_in_outer_scopes_function(self):
        """Test finding shadowed function."""
        var_name = "func"
        
        # Create mock function symbol
        func_symbol = Mock()
        func_symbol.name = "func"
        func_symbol.kind = "function"
        
        # Create mock scopes
        current_scope = Mock()
        outer_scope = Mock()
        outer_scope.symbols = [func_symbol]
        
        ctx = Mock()
        ctx.scopes = [current_scope, outer_scope]
        
        result = self.rule._find_in_outer_scopes(var_name, current_scope, ctx)
        
        assert result is not None
        assert result['type'] == 'function'
        assert result['name'] == 'func'
        assert result['suggestion'] == 'func_var'
    
    def test_find_in_outer_scopes_class(self):
        """Test finding shadowed class."""
        var_name = "MyClass"
        
        # Create mock class symbol
        class_symbol = Mock()
        class_symbol.name = "MyClass"
        class_symbol.kind = "class"
        
        # Create mock scopes
        current_scope = Mock()
        outer_scope = Mock()
        outer_scope.symbols = [class_symbol]
        
        ctx = Mock()
        ctx.scopes = [current_scope, outer_scope]
        
        result = self.rule._find_in_outer_scopes(var_name, current_scope, ctx)
        
        assert result is not None
        assert result['type'] == 'class'
        assert result['name'] == 'MyClass'
        assert result['suggestion'] == 'MyClass_instance'
    
    def test_find_in_outer_scopes_no_match(self):
        """Test no shadowing when name not found in outer scopes."""
        var_name = "unique_name"
        
        # Create mock symbol with different name
        other_symbol = Mock()
        other_symbol.name = "different_name"
        other_symbol.kind = "variable"
        
        # Create mock scopes
        current_scope = Mock()
        outer_scope = Mock()
        outer_scope.symbols = [other_symbol]
        
        ctx = Mock()
        ctx.scopes = [current_scope, outer_scope]
        
        result = self.rule._find_in_outer_scopes(var_name, current_scope, ctx)
        
        assert result is None
    
    # Ignore Underscore Tests
    def test_ignore_single_underscore(self):
        """Test that single underscore is ignored."""
        var_symbol = Mock()
        var_symbol.name = "_"
        var_symbol.kind = "variable"
        
        scope = Mock()
        ctx = Mock()
        ctx.scopes = [scope]
        
        shadowed_info = self.rule._find_shadowed_entity(var_symbol, scope, ctx)
        
        assert shadowed_info is None
    
    # Finding Creation Tests
    def test_create_shadowing_finding_builtin(self):
        """Test creating finding for builtin shadowing."""
        var_symbol = Mock()
        var_symbol.name = "list"
        var_symbol.start_byte = 10
        var_symbol.end_byte = 14
        
        shadowed_info = {
            'type': 'builtin',
            'name': 'list',
            'location': 'builtin scope',
            'suggestion': 'items'
        }
        
        ctx = Mock()
        ctx.file_path = "test.py"
        
        finding = self.rule._create_shadowing_finding(var_symbol, shadowed_info, ctx)
        
        assert finding.rule == "ident.shadowing"
        assert "shadows Python builtin" in finding.message
        assert "list" in finding.message
        assert finding.severity == "warning"
        assert finding.file == "test.py"
        assert finding.start_byte == 10
        assert finding.end_byte == 14
        assert finding.autofix is None  # suggest-only
        assert finding.meta["variable_name"] == "list"
        assert finding.meta["shadowed_type"] == "builtin"
        assert finding.meta["suggested_name"] == "items"
        assert finding.meta["is_builtin"] is True
    
    def test_create_shadowing_finding_import(self):
        """Test creating finding for import shadowing."""
        var_symbol = Mock()
        var_symbol.name = "os"
        var_symbol.start_byte = 20
        var_symbol.end_byte = 22
        
        shadowed_info = {
            'type': 'import',
            'name': 'os',
            'location': 'module scope',
            'suggestion': 'os_value'
        }
        
        ctx = Mock()
        ctx.file_path = "test.py"
        
        finding = self.rule._create_shadowing_finding(var_symbol, shadowed_info, ctx)
        
        assert "shadows imported module" in finding.message
        assert "os" in finding.message
        assert "module scope" in finding.message
        assert finding.meta["shadowed_type"] == "import"
        assert finding.meta["suggested_name"] == "os_value"
        assert finding.meta["is_builtin"] is False
    
    def test_create_shadowing_finding_variable(self):
        """Test creating finding for variable shadowing."""
        var_symbol = Mock()
        var_symbol.name = "x"
        var_symbol.start_byte = 30
        var_symbol.end_byte = 31
        
        shadowed_info = {
            'type': 'variable',
            'name': 'x',
            'location': 'outer scope',
            'suggestion': 'inner_x'
        }
        
        ctx = Mock()
        ctx.file_path = "test.py"
        
        finding = self.rule._create_shadowing_finding(var_symbol, shadowed_info, ctx)
        
        assert "shadows variable" in finding.message
        assert finding.meta["shadowed_type"] == "variable"
        assert finding.meta["suggested_name"] == "inner_x"
    
    # Integration Tests with Mock Scope Analysis
    def test_analyze_scope_for_shadowing(self):
        """Test analyzing a scope for shadowing."""
        # Create mock variable that shadows builtin
        var_symbol = Mock()
        var_symbol.name = "list"
        var_symbol.kind = "variable"
        var_symbol.start_byte = 10
        var_symbol.end_byte = 14
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [var_symbol]
        
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = [scope]
        
        findings = list(self.rule._analyze_scope_for_shadowing(scope, ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "ident.shadowing"
        assert "list" in findings[0].message
    
    def test_analyze_scope_no_shadowing(self):
        """Test analyzing scope with no shadowing."""
        # Create mock variable that doesn't shadow anything
        var_symbol = Mock()
        var_symbol.name = "unique_var"
        var_symbol.kind = "variable"
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [var_symbol]
        
        ctx = Mock()
        ctx.scopes = [scope]
        
        findings = list(self.rule._analyze_scope_for_shadowing(scope, ctx))
        
        assert len(findings) == 0
    
    # Visit Method Tests
    def test_visit_python_file(self):
        """Test visiting Python file."""
        # Create mock variable that shadows builtin
        var_symbol = Mock()
        var_symbol.name = "dict"
        var_symbol.kind = "variable"
        var_symbol.start_byte = 5
        var_symbol.end_byte = 9
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [var_symbol]
        
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = [scope]
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "ident.shadowing"
        assert "dict" in findings[0].message
    
    def test_visit_non_python_file(self):
        """Test visiting non-Python file returns empty."""
        ctx = Mock()
        ctx.file_path = "test.js"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_visit_no_scopes(self):
        """Test visiting with no scopes returns empty."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = None
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    # Comprehensive Builtin Tests
    def test_common_builtins_detected(self):
        """Test that common builtins are detected."""
        common_builtins = [
            'list', 'dict', 'set', 'tuple', 'str', 'int', 'float', 'bool',
            'len', 'max', 'min', 'sum', 'all', 'any', 'map', 'filter',
            'open', 'input', 'print', 'range', 'enumerate', 'zip',
            'Exception', 'ValueError', 'TypeError', 'AttributeError'
        ]
        
        for builtin_name in common_builtins:
            assert builtin_name in self.rule.PYTHON_BUILTINS
    
    def test_constants_detected(self):
        """Test that builtin constants are detected."""
        constants = ['True', 'False', 'None']
        
        for constant in constants:
            assert constant in self.rule.PYTHON_BUILTINS
    
    # Edge Cases and Real World Examples
    def test_multiple_shadowing_in_scope(self):
        """Test multiple variables shadowing in same scope."""
        # Create multiple mock variables shadowing builtins
        list_symbol = Mock()
        list_symbol.name = "list"
        list_symbol.kind = "variable"
        list_symbol.start_byte = 10
        list_symbol.end_byte = 14
        
        dict_symbol = Mock()
        dict_symbol.name = "dict"
        dict_symbol.kind = "variable"  
        dict_symbol.start_byte = 20
        dict_symbol.end_byte = 24
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [list_symbol, dict_symbol]
        
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = [scope]
        
        findings = list(self.rule._analyze_scope_for_shadowing(scope, ctx))
        
        assert len(findings) == 2
        finding_names = [f.meta["variable_name"] for f in findings]
        assert "list" in finding_names
        assert "dict" in finding_names
    
    def test_mixed_shadowing_types(self):
        """Test mix of builtin and import shadowing."""
        # Builtin shadowing
        list_symbol = Mock()
        list_symbol.name = "list"
        list_symbol.kind = "variable"
        list_symbol.start_byte = 10
        list_symbol.end_byte = 14
        
        # Import shadowing
        os_symbol = Mock()
        os_symbol.name = "os"
        os_symbol.kind = "variable"
        os_symbol.start_byte = 30
        os_symbol.end_byte = 32
        
        # Import symbol in outer scope
        import_symbol = Mock()
        import_symbol.name = "os"
        import_symbol.kind = "import"
        
        # Create mock scopes
        inner_scope = Mock()
        inner_scope.symbols = [list_symbol, os_symbol]
        
        outer_scope = Mock()
        outer_scope.symbols = [import_symbol]
        
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = [inner_scope, outer_scope]
        
        findings = list(self.rule._analyze_scope_for_shadowing(inner_scope, ctx))
        
        assert len(findings) == 2
        finding_types = [f.meta["shadowed_type"] for f in findings]
        assert "builtin" in finding_types
        assert "import" in finding_types
    
    def test_parameter_shadowing(self):
        """Test function parameter shadowing builtin."""
        # Create mock parameter that shadows builtin
        param_symbol = Mock()
        param_symbol.name = "len"
        param_symbol.kind = "parameter"
        param_symbol.start_byte = 15
        param_symbol.end_byte = 18
        
        # Create mock scope
        scope = Mock()
        scope.symbols = [param_symbol]
        
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.scopes = [scope]
        
        findings = list(self.rule._analyze_scope_for_shadowing(scope, ctx))
        
        assert len(findings) == 1
        assert findings[0].meta["variable_name"] == "len"
        assert findings[0].meta["shadowed_type"] == "builtin"
    
    def test_autofix_safety_metadata(self):
        """Test autofix safety is suggest-only."""
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        # Test that autofix generation returns None
        var_symbol = Mock()
        result = self.rule._generate_autofix_suggestions(var_symbol, "test_suggestion", Mock())
        assert result is None
    
    def test_priority_p0(self):
        """Test that this is a P0 priority rule."""
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 1
        assert self.rule.requires.scopes is True

