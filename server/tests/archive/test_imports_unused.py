"""Tests for imports.unused rule."""

import pytest
from unittest.mock import Mock

from rules.imports_unused import ImportsUnusedRule


class MockContext:
    """Mock context for testing."""
    
    def __init__(self, content, file_path="test.py", language="python"):
        self.content = content
        self.file_path = file_path
        self.text = content
        self.lines = content.split('\n')
        self.tree = self._create_mock_tree()
        self.adapter = Mock()
        self.adapter.language_id.return_value = language
        self.config = {}
        self.scopes = self._create_mock_scopes()
    
    def _create_mock_tree(self):
        """Create a simple mock tree for text-based analysis."""
        mock_tree = Mock()
        mock_tree.root_node = Mock()
        mock_tree.root_node.children = []
        return mock_tree
    
    def _create_mock_scopes(self):
        """Create mock scope graph."""
        mock_scopes = Mock()
        mock_scopes.iter_symbols = Mock(return_value=[])
        mock_scopes.has_refs_to = Mock(return_value=False)
        mock_scopes.refs_to = Mock(return_value=[])
        return mock_scopes


class TestImportsUnusedRule:
    """Test cases for the unused imports rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ImportsUnusedRule()
    
    def _run_rule(self, code: str, language: str = "python") -> list:
        """Helper to run the rule on code and return findings."""
        context = MockContext(code, file_path=f"test.{self._get_extension(language)}", language=language)
        return list(self.rule.visit(context))
    
    def _get_extension(self, language: str) -> str:
        """Get file extension for language."""
        extensions = {
            'python': 'py',
            'typescript': 'ts', 
            'javascript': 'js',
            'go': 'go',
            'java': 'java',
            'csharp': 'cs',
            'ruby': 'rb',
            'rust': 'rs'
        }
        return extensions.get(language, 'txt')
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "imports.unused"
        assert self.rule.meta.category == "imports"
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.autofix_safety == "safe"
        assert "python" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
        assert "go" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert "rust" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 8
    
    # Test language detection
    
    def test_detect_language_python(self):
        """Test Python language detection."""
        language = self.rule._detect_language("test.py")
        assert language == "python"
    
    def test_detect_language_typescript(self):
        """Test TypeScript language detection."""
        language = self.rule._detect_language("test.ts")
        assert language == "typescript"
    
    def test_detect_language_javascript(self):
        """Test JavaScript language detection."""
        language = self.rule._detect_language("test.js") 
        assert language == "javascript"
    
    def test_detect_language_go(self):
        """Test Go language detection."""
        language = self.rule._detect_language("test.go")
        assert language == "go"
    
    def test_detect_language_java(self):
        """Test Java language detection."""
        language = self.rule._detect_language("test.java")
        assert language == "java"
    
    def test_detect_language_csharp(self):
        """Test C# language detection."""
        language = self.rule._detect_language("test.cs")
        assert language == "csharp"
    
    def test_detect_language_ruby(self):
        """Test Ruby language detection."""
        language = self.rule._detect_language("test.rb")
        assert language == "ruby"
    
    def test_detect_language_rust(self):
        """Test Rust language detection."""
        language = self.rule._detect_language("test.rs")
        assert language == "rust"
    
    def test_detect_language_unknown(self):
        """Test unknown language detection."""
        language = self.rule._detect_language("test.xyz")
        assert language == "unknown"
    
    # Test export finding for different languages
    
    def test_find_python_exports(self):
        """Test finding Python __all__ exports."""
        code = '__all__ = ["func1", "Class1", "CONST"]'
        exports = self.rule._find_python_exports(code)
        assert "func1" in exports
        assert "Class1" in exports
        assert "CONST" in exports
        assert len(exports) == 3
    
    def test_find_js_ts_exports(self):
        """Test finding JavaScript/TypeScript exports."""
        code = """
        export { func1, Class1 };
        export default MyClass;
        """
        exports = self.rule._find_js_ts_exports(code)
        assert "func1" in exports
        assert "Class1" in exports
        assert "MyClass" in exports
    
    def test_find_go_exports(self):
        """Test finding Go public exports."""
        code = """
        func PublicFunc() {}
        func privateFunc() {}
        """
        exports = self.rule._find_go_exports(code)
        assert "PublicFunc" in exports
        assert "privateFunc" not in exports
    
    def test_find_java_exports(self):
        """Test finding Java public exports."""
        code = """
        public class PublicClass {}
        class PackageClass {}
        public interface PublicInterface {}
        """
        exports = self.rule._find_java_exports(code)
        assert "PublicClass" in exports
        assert "PublicInterface" in exports
        assert "PackageClass" not in exports
    
    def test_find_csharp_exports(self):
        """Test finding C# public exports."""
        code = """
        public class PublicClass {}
        internal class InternalClass {}
        public struct PublicStruct {}
        """
        exports = self.rule._find_csharp_exports(code)
        assert "PublicClass" in exports
        assert "PublicStruct" in exports
        assert "InternalClass" not in exports
    
    def test_find_ruby_exports(self):
        """Test finding Ruby module/class exports."""
        code = """
        class MyClass
        end
        module MyModule
        end
        """
        exports = self.rule._find_ruby_exports(code)
        assert "MyClass" in exports
        assert "MyModule" in exports
    
    def test_find_rust_exports(self):
        """Test finding Rust public exports."""
        code = """
        pub fn public_func() {}
        fn private_func() {}
        pub struct PublicStruct {}
        """
        exports = self.rule._find_rust_exports(code)
        assert "public_func" in exports
        assert "PublicStruct" in exports
        assert "private_func" not in exports
    
    # Test import classification
    
    def test_classify_python_import_types(self):
        """Test Python import type classification."""
        # Mock symbol for from import
        symbol1 = Mock()
        symbol1.start_byte = 5  # after "from "
        text1 = "from os import path"
        import_type1 = self.rule._classify_import_type(symbol1, text1, "python")
        assert import_type1 == "from_import"
        
        # Mock symbol for regular import
        symbol2 = Mock()
        symbol2.start_byte = 7  # after "import "
        text2 = "import os"
        import_type2 = self.rule._classify_import_type(symbol2, text2, "python")
        assert import_type2 == "import"
    
    def test_classify_js_ts_import_types(self):
        """Test JavaScript/TypeScript import type classification."""
        # ES6 import
        symbol1 = Mock()
        symbol1.start_byte = 7
        text1 = "import { func } from 'module'"
        import_type1 = self.rule._classify_import_type(symbol1, text1, "javascript")
        assert import_type1 == "es_import"
        
        # CommonJS require
        symbol2 = Mock()
        symbol2.start_byte = 6
        text2 = "const fs = require('fs')"
        import_type2 = self.rule._classify_import_type(symbol2, text2, "javascript")
        assert import_type2 == "require"
    
    def test_classify_other_language_imports(self):
        """Test import classification for other languages."""
        symbol = Mock()
        symbol.start_byte = 0
        
        # Go
        go_type = self.rule._classify_import_type(symbol, 'import "fmt"', "go")
        assert go_type == "go_import"
        
        # Java
        java_type = self.rule._classify_import_type(symbol, 'import java.util.List;', "java")
        assert java_type == "java_import"
        
        # C#
        cs_type = self.rule._classify_import_type(symbol, 'using System;', "csharp")
        assert cs_type == "using"
        
        # Ruby
        ruby_type = self.rule._classify_import_type(symbol, "require 'json'", "ruby")
        assert ruby_type == "require"
        
        # Rust
        rust_type = self.rule._classify_import_type(symbol, 'use std::collections::HashMap;', "rust")
        assert rust_type == "use"
    
    # Test indirect usage detection
    
    def test_python_indirect_usage(self):
        """Test Python indirect usage detection."""
        # getattr usage
        assert self.rule._has_python_indirect_usage("myvar", "getattr(obj, 'myvar')")
        assert self.rule._has_python_indirect_usage("myvar", 'hasattr(obj, "myvar")')
        assert self.rule._has_python_indirect_usage("myvar", "setattr(obj, 'myvar', value)")
        assert self.rule._has_python_indirect_usage("mymodule", "__import__('mymodule')")
        assert self.rule._has_python_indirect_usage("myvar", "globals()['myvar']")
        
        # No usage
        assert not self.rule._has_python_indirect_usage("myvar", "regular code without myvar")
    
    def test_js_indirect_usage(self):
        """Test JavaScript/TypeScript indirect usage detection."""
        assert self.rule._has_js_indirect_usage("myvar", "window['myvar']")
        assert self.rule._has_js_indirect_usage("myvar", 'global["myvar"]')
        assert self.rule._has_js_indirect_usage("myvar", "this['myvar']")
        
        # No usage
        assert not self.rule._has_js_indirect_usage("myvar", "regular code without myvar")
    
    def test_java_indirect_usage(self):
        """Test Java reflection usage detection."""
        assert self.rule._has_java_indirect_usage("MyClass", "Class.forName('MyClass')")
        assert self.rule._has_java_indirect_usage("myfield", 'getClass().getField("myfield")')
        
        # No usage
        assert not self.rule._has_java_indirect_usage("MyClass", "regular code")
    
    # Test type checking block detection (Python)
    
    def test_is_in_type_checking_block_true(self):
        """Test detection of code inside TYPE_CHECKING block."""
        code = """
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mymodule import MyClass
    
def func():
    pass
        """
        # Find byte offset of "MyClass" import
        myclass_offset = code.find("MyClass")
        result = self.rule._is_in_type_checking_block(myclass_offset, code)
        assert result is True
    
    def test_is_in_type_checking_block_false(self):
        """Test detection of code outside TYPE_CHECKING block."""
        code = """
from typing import TYPE_CHECKING
from os import path

if TYPE_CHECKING:
    from mymodule import MyClass
        """
        # Find byte offset of "path" import
        path_offset = code.find("path")
        result = self.rule._is_in_type_checking_block(path_offset, code)
        assert result is False
    
    # Test type-only usage detection (TypeScript)
    
    def test_is_type_only_usage_true(self):
        """Test detection of type-only usage in TypeScript."""
        code = "function test(param: MyType): void {}"
        # Find byte offset of "MyType"
        mytype_offset = code.find("MyType")
        result = self.rule._is_type_only_usage(mytype_offset, code)
        assert result is True
    
    def test_is_type_only_usage_false(self):
        """Test detection of runtime usage in TypeScript.""" 
        code = "const instance = new MyClass();"
        # Find byte offset of "MyClass"
        myclass_offset = code.find("MyClass")
        result = self.rule._is_type_only_usage(myclass_offset, code)
        assert result is False
    
    # Test autofix generation
    
    def test_remove_import_line(self):
        """Test generic import line removal."""
        symbol = Mock()
        symbol.start_byte = 5
        text = "line1\nimport something\nline3"
        
        edits = self.rule._remove_import_line(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 6  # Start of import line
        assert edits[0].end_byte == 23  # End of import line including newline
        assert edits[0].replacement == ""
    
    def test_remove_from_destructured_import(self):
        """Test removing from destructured imports."""
        symbol = Mock()
        symbol.name = "func2"
        symbol.start_byte = 15  # Position of func2
        
        text = "import { func1, func2, func3 } from 'module'"
        line_start = 0
        
        edits = self.rule._remove_from_destructured_import(symbol, text, line_start)
        assert len(edits) == 1
        # Should remove ", func2" (including comma and space)
        edit = edits[0]
        removed_text = text[edit.start_byte:edit.end_byte]
        assert "func2" in removed_text
        assert edit.replacement == ""
    
    def test_python_from_import_single(self):
        """Test Python from import with single name."""
        symbol = Mock()
        symbol.name = "path"
        symbol.start_byte = 16
        text = "from os import path\n"
        
        edits = self.rule._fix_from_import(symbol, text)
        assert len(edits) == 1
        # Should remove entire line
        assert edits[0].start_byte == 0
        assert edits[0].end_byte == 20  # Including newline
        assert edits[0].replacement == ""
    
    def test_python_from_import_multiple(self):
        """Test Python from import with multiple names."""
        symbol = Mock()
        symbol.name = "path"
        symbol.start_byte = 16
        text = "from os import dirname, path, basename"
        
        edits = self.rule._fix_from_import(symbol, text)
        assert len(edits) == 1
        # Should remove just "path, " or ", path"
        edit = edits[0]
        removed_text = text[edit.start_byte:edit.end_byte]
        assert "path" in removed_text
        assert edit.replacement == ""
    
    def test_python_regular_import_single(self):
        """Test Python regular import with single module."""
        symbol = Mock()
        symbol.name = "os"
        symbol.meta = {"module": "os"}
        symbol.start_byte = 7
        text = "import os\n"
        
        edits = self.rule._fix_import(symbol, text)
        assert len(edits) == 1
        # Should remove entire line
        assert edits[0].start_byte == 0
        assert edits[0].end_byte == 10  # Including newline
        assert edits[0].replacement == ""
    
    def test_python_regular_import_multiple(self):
        """Test Python regular import with multiple modules."""
        symbol = Mock()
        symbol.name = "sys"
        symbol.meta = {"module": "sys"}
        symbol.start_byte = 11
        text = "import os, sys, json"
        
        edits = self.rule._fix_import(symbol, text)
        assert len(edits) == 1
        # Should remove just "sys, " or ", sys"
        edit = edits[0]
        removed_text = text[edit.start_byte:edit.end_byte]
        assert "sys" in removed_text
        assert edit.replacement == ""
    
    # Test language-specific autofix
    
    def test_fix_javascript_import(self):
        """Test JavaScript import autofix."""
        symbol = Mock()
        symbol.name = "func1"
        symbol.start_byte = 9
        text = "import { func1 } from 'module'"
        
        edits = self.rule._fix_js_ts_import(symbol, text, "es_import")
        assert len(edits) == 1
        # Should remove entire line (single destructured import)
        assert edits[0].replacement == ""
    
    def test_fix_go_import(self):
        """Test Go import autofix.""" 
        symbol = Mock()
        symbol.start_byte = 8
        text = 'import "fmt"\n'
        
        edits = self.rule._fix_go_import(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 0
        assert edits[0].replacement == ""
    
    def test_fix_java_import(self):
        """Test Java import autofix."""
        symbol = Mock()
        symbol.start_byte = 7
        text = "import java.util.List;\n"
        
        edits = self.rule._fix_java_import(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 0
        assert edits[0].replacement == ""
    
    def test_fix_csharp_import(self):
        """Test C# using statement autofix."""
        symbol = Mock()
        symbol.start_byte = 6
        text = "using System;\n"
        
        edits = self.rule._fix_csharp_import(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 0
        assert edits[0].replacement == ""
    
    def test_fix_ruby_import(self):
        """Test Ruby require autofix."""
        symbol = Mock()
        symbol.start_byte = 8
        text = "require 'json'\n"
        
        edits = self.rule._fix_ruby_import(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 0
        assert edits[0].replacement == ""
    
    def test_fix_rust_import(self):
        """Test Rust use statement autofix."""
        symbol = Mock()
        symbol.start_byte = 4
        text = "use std::collections::HashMap;\n"
        
        edits = self.rule._fix_rust_import(symbol, text)
        assert len(edits) == 1
        assert edits[0].start_byte == 0
        assert edits[0].replacement == ""
    
    # Test finding generation
    
    def test_create_finding_structure(self):
        """Test finding creation structure."""
        symbol = Mock()
        symbol.name = "unused_import"
        symbol.start_byte = 10
        symbol.end_byte = 25
        symbol.meta = {"module": "somemodule"}
        
        ctx = MockContext("import unused_import", "test.py")
        
        finding = self.rule._create_finding_for_unused_import(symbol, ctx, "python")
        
        assert finding.rule == "imports.unused"
        assert finding.message == "Unused import 'unused_import'"
        assert finding.severity == "warning"
        assert finding.file == "test.py"
        assert finding.start_byte == 10
        assert finding.end_byte == 25
        assert finding.meta["symbol_name"] == "unused_import"
        assert finding.meta["module"] == "somemodule"
        assert finding.meta["language"] == "python"
        assert isinstance(finding.autofix, list) or finding.autofix is None
    
    # Test comprehensive scenarios
    
    def test_no_scopes_returns_empty(self):
        """Test that rule returns empty when no scopes available."""
        ctx = MockContext("import os", "test.py")
        ctx.scopes = None
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_comprehensive_language_support(self):
        """Test that all supported languages are handled."""
        languages = ["python", "typescript", "javascript", "go", "java", "csharp", "ruby", "rust"]
        
        for lang in languages:
            # Test language detection
            ext = self._get_extension(lang)
            detected = self.rule._detect_language(f"test.{ext}")
            assert detected == lang
            
            # Test export finding (should not crash)
            exports = self.rule._find_exports("sample code", lang)
            assert isinstance(exports, set)
            
            # Test import classification (should not crash)
            symbol = Mock()
            symbol.start_byte = 0
            import_type = self.rule._classify_import_type(symbol, "sample code", lang)
            assert isinstance(import_type, str)
    
    def test_edge_cases(self):
        """Test edge cases and boundary conditions."""
        symbol = Mock()
        symbol.name = "test"
        symbol.start_byte = 0
        symbol.end_byte = 4
        symbol.meta = {}
        
        # Empty text
        edits = self.rule._remove_import_line(symbol, "")
        assert isinstance(edits, list)
        
        # Text without newlines
        edits = self.rule._remove_import_line(symbol, "import test")
        assert isinstance(edits, list)
        
        # Test with unknown language
        ctx = MockContext("import test", "test.xyz")
        finding = self.rule._create_finding_for_unused_import(symbol, ctx, "unknown")
        assert finding.meta["language"] == "unknown"
    
    def test_autofix_safety_metadata(self):
        """Test that autofix safety is marked as safe."""
        assert self.rule.meta.autofix_safety == "safe"
        
        # All autofixes should be safe transformations
        symbol = Mock()
        symbol.name = "test"
        symbol.start_byte = 0
        symbol.end_byte = 4
        symbol.meta = {}
        
        edits = self.rule._generate_autofix(symbol, "import test", "python")
        
        # Autofix should be safe removal only
        if edits:
            for edit in edits:
                assert edit.replacement == "" or edit.replacement.isspace()
    
    def test_tier_1_requirement(self):
        """Test that rule requires scopes (tier 1)."""
        assert self.rule.meta.tier == 1
        assert self.rule.requires.scopes is True

