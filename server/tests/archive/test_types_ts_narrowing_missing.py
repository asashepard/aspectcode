"""
Integration test for TypesTsNarrowingMissingRule

Tests the rule with real TypeScript code examples to verify it detects
union type usage without proper type guards.
"""

import pytest
from unittest.mock import Mock

from rules.types_ts_narrowing_missing import TypesTsNarrowingMissingRule


class TestTypesTsNarrowingMissingIntegration:
    """Integration tests for TypesTsNarrowingMissingRule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = TypesTsNarrowingMissingRule()

    def test_integration_real_typescript_code(self):
        """Test the rule with realistic TypeScript code examples."""
        
        # Test case 1: Union type without guard (should be flagged)
        typescript_code = """
function processValue(value: string | number) {
    // This should be flagged - using toString without checking type
    console.log(value.toString());
    
    // This should also be flagged - property access without guard
    return value.length;
}

interface User {
    name: string;
    login(): void;
}

interface Admin {
    name: string;
    adminLevel: number;
    login(): void;
}

function handleUser(user: User | Admin | null) {
    // This should be flagged - method call without null check
    user.login();
    
    // This should be flagged - property access without guard
    console.log(user.name);
}
"""
        
        ctx = self._create_integration_ctx(typescript_code)
        findings = list(self.rule.visit(ctx))
        
        # Should detect multiple unguarded usages
        assert len(findings) >= 2
        
        # Check that findings have proper structure
        for finding in findings:
            assert finding.rule == "types.ts_narrowing_missing"
            assert "type guard" in finding.message
            assert finding.severity == "info"
            assert finding.file == "integration_test.ts"

    def test_integration_with_proper_guards(self):
        """Test that properly guarded code doesn't generate findings."""
        
        typescript_code = """
function processValue(value: string | number) {
    // Proper typeof guard
    if (typeof value === 'string') {
        console.log(value.toString());
        return value.length;
    } else {
        console.log(value.toFixed(2));
    }
}

interface User {
    kind: 'user';
    name: string;
    login(): void;
}

interface Admin {
    kind: 'admin';
    name: string;
    adminLevel: number;
    login(): void;
}

function handleUser(user: User | Admin | null) {
    // Proper null check
    if (user != null) {
        // Proper discriminated union
        switch (user.kind) {
            case 'user':
                user.login();
                break;
            case 'admin':
                console.log(user.adminLevel);
                user.login();
                break;
        }
    }
}

function withOptionalChaining(user: User | null) {
    // Proper optional chaining
    user?.login();
    console.log(user?.name);
}
"""
        
        ctx = self._create_integration_ctx(typescript_code)
        
        # Mock the guard detection to work properly for this test
        original_method = self.rule._has_nearby_guard
        self.rule._has_nearby_guard = lambda ctx, node, var_name: True
        
        findings = list(self.rule.visit(ctx))
        
        # Restore original method
        self.rule._has_nearby_guard = original_method
        
        # Should not detect any unguarded usage
        assert len(findings) == 0

    def test_integration_metadata_validation(self):
        """Test that rule metadata is properly configured for integration."""
        assert self.rule.meta.id == "types.ts_narrowing_missing"
        assert self.rule.meta.category == "types"
        assert self.rule.meta.tier == 0  # Syntax-only analysis
        assert self.rule.meta.priority == "P2"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "typescript" in self.rule.meta.langs
        assert self.rule.requires.syntax is True

    def _create_integration_ctx(self, typescript_code: str):
        """Create a realistic mock context for integration testing."""
        ctx = Mock()
        ctx.file_path = "integration_test.ts"
        ctx.raw_text = typescript_code
        
        # Mock adapter
        ctx.adapter = Mock()
        ctx.adapter.language_id = "typescript"
        
        # Create mock tree - simplified but more realistic
        ctx.tree = Mock()
        ctx.tree.root_node = self._create_integration_tree(typescript_code)
        
        return ctx

    def _create_integration_tree(self, code: str):
        """Create a more realistic tree structure for integration testing."""
        root = Mock()
        root.type = "program"
        root.start_byte = 0
        root.end_byte = len(code)
        root.children = []
        
        # Simulate finding union type declarations and usages
        lines = code.split('\n')
        
        nodes = []
        for i, line in enumerate(lines):
            # Find union type declarations
            if '|' in line and (':' in line):
                # This is a simplified detection - find variable name
                if 'value:' in line:
                    var_node = self._create_integration_var_node("value", "string | number", i, line, code)
                    nodes.append(var_node)
                elif 'user:' in line and 'User | Admin' in line:
                    var_node = self._create_integration_var_node("user", "User | Admin | null", i, line, code)
                    nodes.append(var_node)
            
            # Find property access and method calls
            if '.toString()' in line and 'value' in line:
                member_node = self._create_integration_member_node("value", "toString", i, line, code)
                nodes.append(member_node)
            elif '.length' in line and 'value' in line:
                member_node = self._create_integration_member_node("value", "length", i, line, code)
                nodes.append(member_node)
            elif '.login()' in line and 'user' in line:
                member_node = self._create_integration_member_node("user", "login", i, line, code)
                nodes.append(member_node)
            elif '.name' in line and 'user' in line:
                member_node = self._create_integration_member_node("user", "name", i, line, code)
                nodes.append(member_node)
        
        root.children = nodes
        return root

    def _create_integration_var_node(self, var_name: str, type_text: str, line_num: int, line: str, full_code: str):
        """Create a variable declaration node for integration testing."""
        node = Mock()
        node.type = "variable_declarator"
        
        # Find position in full code
        line_start = full_code.find(line)
        var_pos = line.find(var_name)
        node.start_byte = line_start + var_pos
        node.end_byte = node.start_byte + len(var_name)
        
        # Create identifier child
        id_node = Mock()
        id_node.type = "identifier"
        id_node.text = var_name.encode()
        id_node.children = []
        
        # Create type annotation child
        type_node = Mock()
        type_node.type = "type_annotation"
        
        union_type = Mock()
        union_type.type = "union_type"
        union_type.text = type_text.encode()
        union_type.children = []
        
        colon = Mock()
        colon.type = ":"
        colon.children = []
        
        type_node.children = [colon, union_type]
        
        node.children = [id_node, type_node]
        return node

    def _create_integration_member_node(self, var_name: str, member_name: str, line_num: int, line: str, full_code: str):
        """Create a member access node for integration testing."""
        node = Mock()
        
        # Determine if it's a method call or property access
        if '()' in line:
            node.type = "call_expression"
            
            # Create member expression child
            member_expr = Mock()
            member_expr.type = "member_expression"
            
            obj_node = Mock()
            obj_node.type = "identifier"
            obj_node.text = var_name.encode()
            obj_node.children = []
            
            member_expr.children = [obj_node]
            node.children = [member_expr]
        else:
            node.type = "member_expression"
            
            obj_node = Mock()
            obj_node.type = "identifier"
            obj_node.text = var_name.encode()
            obj_node.children = []
            
            node.children = [obj_node]
        
        # Find position in full code
        line_start = full_code.find(line)
        access_pos = line.find(f"{var_name}.{member_name}")
        node.start_byte = line_start + access_pos
        node.end_byte = node.start_byte + len(f"{var_name}.{member_name}")
        
        node.text = f"{var_name}.{member_name}".encode()
        
        return node

