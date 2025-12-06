"""
Comprehensive tests for imports.missing_file_target rule.

Tests missing import detection using resolver+FS approach with tried paths
across Python, TypeScript, and JavaScript with P0 priority and suggest-only autofix.
"""

import pytest
import os
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch

from rules.imports_missing_file_target import ImportsMissingFileTargetRule
from engine.types import RuleContext, Finding


class TestImportsMissingFileTargetRule:
    """Test the imports missing file target rule."""
    
    def setup_method(self):
        self.rule = ImportsMissingFileTargetRule()
        
    def test_rule_metadata(self):
        """Test rule metadata matches specification."""
        assert self.rule.meta.id == "imports.missing_file_target"
        assert self.rule.meta.category == "imports"
        assert self.rule.meta.tier == 2
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.description == "Unresolvable import target"
        
        # Check multi-language support
        expected_langs = ["python", "typescript", "javascript"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_requires_project_graph(self):
        """Test that the rule requires project graph analysis."""
        assert self.rule.requires.project_graph == True
        assert self.rule.requires.syntax == True
        assert self.rule.requires.raw_text == False
        assert self.rule.requires.scopes == False
    
    def test_is_supported_file(self):
        """Test supported file type detection."""
        # Python
        assert self.rule._is_supported_file("module.py") == True
        
        # TypeScript/JavaScript
        assert self.rule._is_supported_file("component.ts") == True
        assert self.rule._is_supported_file("component.tsx") == True
        assert self.rule._is_supported_file("script.js") == True
        assert self.rule._is_supported_file("component.jsx") == True
        assert self.rule._is_supported_file("module.mjs") == True
        
        # Unsupported
        assert self.rule._is_supported_file("file.txt") == False
        assert self.rule._is_supported_file("README.md") == False
        assert self.rule._is_supported_file("main.go") == False
        assert self.rule._is_supported_file("App.java") == False
    
    def test_get_file_type(self):
        """Test file type detection."""
        assert self.rule._get_file_type("module.py") == "python"
        assert self.rule._get_file_type("component.ts") == "typescript"
        assert self.rule._get_file_type("component.tsx") == "typescript"
        assert self.rule._get_file_type("script.js") == "javascript"
        assert self.rule._get_file_type("component.jsx") == "javascript"
        assert self.rule._get_file_type("module.mjs") == "javascript"
        assert self.rule._get_file_type("unknown.txt") == "unknown"
    
    def test_extract_import_details(self):
        """Test import details extraction."""
        # Test with a simple object instead of Mock to avoid Mock complications
        class MockImportInfo:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)
        
        # Test with module attribute
        import_info = MockImportInfo(
            module="test_module",
            level=0,
            names=["func"],
            range=(10, 30)
        )
        
        details = self.rule._extract_import_details(import_info, "test.py")
        assert details == ("test_module", 0, ["func"], (10, 30))
        
        # Test with target attribute (no module attribute at all)
        import_info2 = MockImportInfo(
            target="target_module",
            level=1,
            names=[],
            range=None,
            start_byte=None,
            end_byte=None,
            start=20,
            end=40
        )
        
        details2 = self.rule._extract_import_details(import_info2, "test.py")
        assert details2 == ("target_module", 1, [], (20, 40))
    
    def test_get_import_range(self):
        """Test import statement range extraction."""
        # Test with range tuple
        import_info = Mock()
        import_info.range = (15, 45)
        
        result = self.rule._get_import_range(import_info)
        assert result == (15, 45)
        
        # Test with start_byte/end_byte
        import_info2 = Mock()
        del import_info2.range
        import_info2.start_byte = 25
        import_info2.end_byte = 55
        
        result2 = self.rule._get_import_range(import_info2)
        assert result2 == (25, 55)
    
    def test_build_resolve_module(self):
        """Test module name building for resolution."""
        # Absolute import
        result = self.rule._build_resolve_module("module", 0)
        assert result == "module"
        
        # Relative imports
        result2 = self.rule._build_resolve_module("sibling", 1)
        assert result2 == ".sibling"
        
        result3 = self.rule._build_resolve_module("parent_module", 2)
        assert result3 == "..parent_module"
    
    def test_resolve_import_with_resolver(self):
        """Test import resolution using resolver."""
        # Mock resolver that reports missing
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        mock_result.meta = {"tried_paths": ["/path/to/missing.py"]}
        resolver.resolve.return_value = mock_result
        
        result = self.rule._resolve_import(resolver, "test.py", "missing_module", [])
        assert result["kind"] == "missing"
        assert result["resolved"] == False
        assert "tried_paths" in result["meta"]
        
        # Mock resolver that finds module
        mock_result2 = Mock()
        mock_result2.kind = "resolved"
        resolver.resolve.return_value = mock_result2
        
        result2 = self.rule._resolve_import(resolver, "test.py", "found_module", [])
        assert result2["kind"] == "resolved"
        assert result2["resolved"] == True
    
    def test_manual_resolve_absolute(self):
        """Test manual resolution for absolute imports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test file structure
            test_file = os.path.join(temp_dir, "test.py")
            module_file = os.path.join(temp_dir, "existing_module.py")
            package_dir = os.path.join(temp_dir, "package")
            init_file = os.path.join(package_dir, "__init__.py")
            
            os.makedirs(package_dir)
            open(test_file, 'w').close()
            open(module_file, 'w').close()
            open(init_file, 'w').close()
            
            # Test resolving existing module
            result = self.rule._manual_resolve(test_file, "existing_module")
            assert result == module_file
            
            # Test resolving package
            result2 = self.rule._manual_resolve(test_file, "package")
            assert result2 == init_file
            
            # Test resolving missing module
            result3 = self.rule._manual_resolve(test_file, "missing_module")
            assert result3 is None
    
    def test_manual_resolve_relative(self):
        """Test manual resolution for relative imports."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create nested structure
            subdir = os.path.join(temp_dir, "subdir")
            os.makedirs(subdir)
            
            test_file = os.path.join(subdir, "test.py")
            sibling_file = os.path.join(subdir, "sibling.py")
            parent_file = os.path.join(temp_dir, "parent.py")
            
            open(test_file, 'w').close()
            open(sibling_file, 'w').close()
            open(parent_file, 'w').close()
            
            # Test same-level relative import
            result = self.rule._manual_resolve(test_file, ".sibling")
            assert result == sibling_file
            
            # Test parent-level relative import
            result2 = self.rule._manual_resolve(test_file, "..parent")
            assert result2 == parent_file
    
    def test_generate_tried_paths(self):
        """Test generation of tried paths."""
        # Python paths
        paths = self.rule._generate_tried_paths("/project", "mymodule", "python")
        assert any("mymodule.py" in path for path in paths)
        assert any("__init__.py" in path for path in paths)
        
        # TypeScript paths
        paths2 = self.rule._generate_tried_paths("/project", "component", "typescript")
        assert any(".ts" in path for path in paths2)
        assert any(".tsx" in path for path in paths2)
        assert any("index.ts" in path for path in paths2)
        
        # JavaScript paths
        paths3 = self.rule._generate_tried_paths("/project", "script", "javascript")
        assert any(".js" in path for path in paths3)
        assert any(".jsx" in path for path in paths3)
        assert any("index.js" in path for path in paths3)
    
    def test_format_error_message(self):
        """Test error message formatting."""
        # Absolute import
        message = self.rule._format_error_message("missing_module", 0, "test.py")
        assert "Unresolvable import target 'missing_module'" in message
        
        # Relative import
        message2 = self.rule._format_error_message("sibling", 1, "test.py")
        assert "Unresolvable relative import target 'sibling'" in message2
    
    def test_looks_like_external_python(self):
        """Test external module detection for Python."""
        # Standard/external packages should be considered external
        assert self.rule._looks_like_external("numpy", "test.py") == True
        assert self.rule._looks_like_external("requests", "test.py") == True
        assert self.rule._looks_like_external("django", "test.py") == True
        assert self.rule._looks_like_external("os", "test.py") == True
        
        # Internal modules should not be external
        assert self.rule._looks_like_external("my_module", "test.py") == False
        assert self.rule._looks_like_external("project.utils", "test.py") == False
        
        # Relative imports are never external
        assert self.rule._looks_like_external(".sibling", "test.py") == False
        assert self.rule._looks_like_external("..parent", "test.py") == False
    
    def test_looks_like_external_javascript(self):
        """Test external module detection for JavaScript/TypeScript."""
        # Common npm packages should be external
        assert self.rule._looks_like_external("react", "component.tsx") == True
        assert self.rule._looks_like_external("lodash", "utils.js") == True
        assert self.rule._looks_like_external("axios", "api.ts") == True
        
        # Scoped packages should be external
        assert self.rule._looks_like_external("@angular/core", "app.ts") == True
        assert self.rule._looks_like_external("@types/node", "types.ts") == True
        
        # Node.js built-ins should be external
        assert self.rule._looks_like_external("fs", "server.js") == True
        assert self.rule._looks_like_external("path", "utils.ts") == True
        
        # Relative imports are never external
        assert self.rule._looks_like_external("./component", "index.ts") == False
        assert self.rule._looks_like_external("../utils", "app.js") == False
    
    def test_generate_suggestions(self):
        """Test suggestion generation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create similar files
            similar_file = os.path.join(temp_dir, "similar_module.py")
            open(similar_file, 'w').close()
            
            tried_paths = [os.path.join(temp_dir, "simlar_module.py")]  # Typo
            
            suggestions = self.rule._generate_suggestions("simlar_module", 0, tried_paths, "test.py")
            
            # Should suggest similarity fixes
            assert any("similar_module" in suggestion for suggestion in suggestions)
            # Should have general suggestions
            assert len(suggestions) > 0
    
    def test_find_similar_files(self):
        """Test finding similar files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test files
            files = ["module.py", "module_utils.py", "similar.py"]
            for f in files:
                open(os.path.join(temp_dir, f), 'w').close()
            
            # Find similar to a typo
            similar = self.rule._find_similar_files(temp_dir, "modul.py", "python")
            assert "module" in similar
    
    def test_similar_name(self):
        """Test name similarity checking."""
        # Exact match
        assert self.rule._similar_name("module", "module") == True
        
        # One character difference
        assert self.rule._similar_name("module", "nodule") == True  # m->n
        assert self.rule._similar_name("test", "best") == True      # t->b
        
        # Length difference by one
        assert self.rule._similar_name("module", "modules") == True  # +s
        assert self.rule._similar_name("modules", "module") == True  # -s
        
        # Too many differences
        assert self.rule._similar_name("module", "different") == False
        assert self.rule._similar_name("abc", "xyz") == False
        
        # Short names must be exact
        assert self.rule._similar_name("ab", "ac") == False
        assert self.rule._similar_name("ab", "ab") == True
    
    def test_visit_no_project_graph(self):
        """Test visit when no project graph is available."""
        ctx = Mock()
        ctx.project_graph = None
        
        findings = list(self.rule.visit(ctx))
        assert findings == []
    
    def test_visit_unsupported_file(self):
        """Test visit with unsupported file type."""
        ctx = Mock()
        ctx.project_graph = ("resolver", "graph", "index")
        ctx.file_path = "README.md"
        
        findings = list(self.rule.visit(ctx))
        assert findings == []
    
    def test_visit_with_missing_import(self):
        """Test visit with actual missing import detection."""
        # Mock project graph components
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        mock_result.meta = {"tried_paths": ["/project/missing_module.py"]}
        resolver.resolve.return_value = mock_result
        
        import_graph = Mock()
        symbol_index = Mock()
        
        # Mock adapter and import parsing
        adapter = Mock()
        import_info = Mock()
        import_info.module = "missing_module"
        import_info.level = 0
        import_info.names = ["func"]
        import_info.range = (10, 50)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "test.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "imports.missing_file_target"
        assert finding.severity == "error"
        assert "missing_module" in finding.message
        assert finding.start_byte == 10
        assert finding.end_byte == 50
        assert finding.autofix is None  # Suggest-only
        
        # Check metadata
        assert finding.meta["module"] == "missing_module"
        assert finding.meta["level"] == 0
        assert finding.meta["is_relative"] == False
        assert finding.meta["file_type"] == "python"
        assert "tried_paths" in finding.meta
        assert "suggestions" in finding.meta
    
    def test_visit_with_external_filtering(self):
        """Test that external modules are filtered when configured."""
        # Mock resolver that reports numpy as missing
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        resolver.resolve.return_value = mock_result
        
        import_graph = Mock()
        symbol_index = Mock()
        
        # Mock adapter with numpy import
        adapter = Mock()
        import_info = Mock()
        import_info.module = "numpy"
        import_info.level = 0
        import_info.names = ["array"]
        import_info.range = (10, 30)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "test.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {"imports.missing_file_target.ignore_external": True}
        
        findings = list(self.rule.visit(ctx))
        
        # Should be filtered out as external
        assert len(findings) == 0
    
    def test_visit_relative_import_missing(self):
        """Test detection of missing relative imports."""
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        mock_result.meta = {}
        
        # Mock resolve to handle relative import resolution
        def mock_resolve(file_path, module_name, names):
            return mock_result
        resolver.resolve = mock_resolve
        
        import_graph = Mock()
        symbol_index = Mock()
        
        # Mock adapter with relative import
        adapter = Mock()
        import_info = Mock()
        import_info.module = "sibling"
        import_info.level = 1  # Relative import
        import_info.names = ["func"]
        import_info.range = (5, 25)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "/project/subdir/test.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["is_relative"] == True
        assert finding.meta["level"] == 1
        assert "relative import" in finding.message
    
    def test_visit_javascript_import_missing(self):
        """Test detection of missing imports in JavaScript/TypeScript."""
        resolver = Mock()
        
        # Mock resolve method to return missing for JS imports
        def mock_resolve(file_path, module_name, names):
            result = Mock()
            result.kind = "missing"
            result.meta = {}
            return result
        resolver.resolve = mock_resolve
        
        import_graph = Mock()
        symbol_index = Mock()
        
        # Mock adapter with JS import
        adapter = Mock()
        import_info = Mock()
        import_info.module = None
        import_info.target = None
        import_info.source = "./missing-component"  # JS-style import
        import_info.path = None
        import_info.level = 0
        import_info.names = ["Component"]
        import_info.range = (0, 40)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "src/app.tsx"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.meta["file_type"] == "typescript"
        assert finding.meta["module"] == "./missing-component"
    
    def test_autofix_safety_suggest_only(self):
        """Test that autofix is always None (suggest-only)."""
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        mock_result.meta = {}
        resolver.resolve.return_value = mock_result
        
        import_graph = Mock()
        symbol_index = Mock()
        
        adapter = Mock()
        import_info = Mock()
        import_info.module = "missing_module"
        import_info.level = 0
        import_info.names = []
        import_info.range = (10, 30)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "test.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        # All findings should have no autofix (suggest-only)
        for finding in findings:
            assert finding.autofix is None
            assert "suggestions" in finding.meta  # Should have suggestions instead
    
    def test_priority_p0_behavior(self):
        """Test P0 priority behavior - should report all missing imports."""
        resolver = Mock()
        mock_result = Mock()
        mock_result.kind = "missing"
        mock_result.meta = {}
        resolver.resolve.return_value = mock_result
        
        import_graph = Mock()
        symbol_index = Mock()
        
        # Multiple missing imports
        adapter = Mock()
        import_info1 = Mock()
        import_info1.module = "missing_module1"
        import_info1.level = 0
        import_info1.names = []
        import_info1.range = (10, 30)
        
        import_info2 = Mock()
        import_info2.module = "missing_module2"
        import_info2.level = 0
        import_info2.names = []
        import_info2.range = (40, 60)
        
        adapter.iter_imports.return_value = [import_info1, import_info2]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "test.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        # P0 priority should report all missing imports
        assert len(findings) == 2
        for finding in findings:
            assert finding.severity == "error"  # P0 rules use error severity

