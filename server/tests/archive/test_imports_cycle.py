"""
Comprehensive tests for imports.cycle rule.

Tests circular import detection using project import graph SCC analysis
across multiple languages with P0 priority and suggest-only autofix.
"""

import pytest
from unittest.mock import Mock, MagicMock

from rules.imports_cycle import ImportsCycleRule
from engine.types import RuleContext, Finding


class TestImportsCycleRule:
    """Test the imports cycle rule."""
    
    def setup_method(self):
        self.rule = ImportsCycleRule()
    
    def test_rule_metadata(self):
        """Test rule metadata matches specification."""
        assert self.rule.meta.id == "imports.cycle"
        assert self.rule.meta.category == "imports"
        assert self.rule.meta.tier == 2
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.description == "Circular import detected"
        
        # Check multi-language support
        expected_langs = ["python", "typescript", "javascript", "go", "java", "csharp", "rust"]
        assert set(self.rule.meta.langs) == set(expected_langs)
    
    def test_requires_project_graph(self):
        """Test that the rule requires project graph analysis."""
        assert self.rule.requires.project_graph == True
        assert self.rule.requires.syntax == True
        assert self.rule.requires.raw_text == True
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
        
        # Other languages
        assert self.rule._is_supported_file("main.go") == True
        assert self.rule._is_supported_file("App.java") == True
        assert self.rule._is_supported_file("Program.cs") == True
        assert self.rule._is_supported_file("main.rs") == True
        
        # Unsupported
        assert self.rule._is_supported_file("file.txt") == False
        assert self.rule._is_supported_file("README.md") == False
        assert self.rule._is_supported_file("config.json") == False
    
    def test_get_file_extension(self):
        """Test file extension extraction."""
        assert self.rule._get_file_extension("module.py") == ".py"
        assert self.rule._get_file_extension("Component.tsx") == ".tsx"
        assert self.rule._get_file_extension("MAIN.GO") == ".go"
        assert self.rule._get_file_extension("/path/to/file.rs") == ".rs"
    
    def test_extract_module_from_import_python(self):
        """Test module extraction from Python import info."""
        # Mock import info with module attribute
        import_info = Mock()
        import_info.module = "my_module"
        # Ensure other attributes return None when accessed
        for attr in ['target', 'path', 'source', 'from_module', 'import_name']:
            if not hasattr(import_info, attr):
                setattr(import_info, attr, None)
        
        result = self.rule._extract_module_from_import(import_info, ".py")
        assert result == "my_module"
        
        # Test with from_module attribute
        import_info2 = Mock()
        import_info2.module = None
        import_info2.target = None
        import_info2.path = None
        import_info2.source = None
        import_info2.from_module = "from_module"
        import_info2.import_name = None
        
        result2 = self.rule._extract_module_from_import(import_info2, ".py")
        assert result2 == "from_module"
    
    def test_extract_module_from_import_javascript(self):
        """Test module extraction from JavaScript/TypeScript import info."""
        # Mock import info with source attribute
        import_info = Mock()
        import_info.module = None
        import_info.target = None
        import_info.path = None
        import_info.source = "./relative_module"
        
        result = self.rule._extract_module_from_import(import_info, ".js")
        assert result == "./relative_module"
        
        # Test with specifier attribute
        import_info2 = Mock()
        import_info2.module = None
        import_info2.target = None
        import_info2.path = None
        import_info2.source = None
        import_info2.specifier = "lodash"
        
        result2 = self.rule._extract_module_from_import(import_info2, ".ts")
        assert result2 == "lodash"
    
    def test_resolve_import_module_python_relative(self):
        """Test Python relative import resolution."""
        current_module = "package.subpackage.module"
        
        # Single dot (same package)
        result = self.rule._resolve_import_module(".sibling", current_module, ".py")
        assert result == "package.subpackage.sibling"
        
        # Double dot (parent package)
        result2 = self.rule._resolve_import_module("..parent_module", current_module, ".py")
        assert result2 == "package.parent_module"
        
        # Absolute import (no change)
        result3 = self.rule._resolve_import_module("absolute.module", current_module, ".py")
        assert result3 == "absolute.module"
    
    def test_resolve_import_module_javascript_relative(self):
        """Test JavaScript/TypeScript relative import resolution."""
        current_module = "src/components/Button"
        
        # Same directory
        result = self.rule._resolve_import_module("./Icon", current_module, ".ts")
        assert result == "src/components/Icon"
        
        # Parent directory
        result2 = self.rule._resolve_import_module("../utils/helper", current_module, ".js")
        assert result2 == "src/utils/helper"
        
        # Absolute import (no change)
        result3 = self.rule._resolve_import_module("lodash", current_module, ".tsx")
        assert result3 == "lodash"
    
    def test_get_import_range(self):
        """Test import statement range extraction."""
        # Test with range tuple
        import_info = Mock()
        import_info.range = (10, 50)
        
        result = self.rule._get_import_range(import_info)
        assert result == (10, 50)
        
        # Test with start_byte/end_byte
        import_info2 = Mock()
        del import_info2.range
        import_info2.start_byte = 20
        import_info2.end_byte = 60
        
        result2 = self.rule._get_import_range(import_info2)
        assert result2 == (20, 60)
        
        # Test fallback
        import_info3 = Mock()
        del import_info3.range
        del import_info3.start_byte
        del import_info3.end_byte
        import_info3.start = 30
        import_info3.end = 70
        
        result3 = self.rule._get_import_range(import_info3)
        assert result3 == (30, 70)
    
    def test_format_cycle_message_specific_import(self):
        """Test cycle message formatting for specific imports."""
        scc = ["module_a", "module_b"]
        cycle_edges = [("module_a", "module_b"), ("module_b", "module_a")]
        target_module = "module_b"
        
        message = self.rule._format_cycle_message(scc, cycle_edges, target_module)
        assert message == "Circular import detected: import of 'module_b' creates cycle"
    
    def test_format_cycle_message_short_cycle(self):
        """Test cycle message formatting for short cycles."""
        scc = ["a", "b", "c"]
        cycle_edges = [("a", "b"), ("b", "c"), ("c", "a")]
        
        message = self.rule._format_cycle_message(scc, cycle_edges)
        assert message == "Circular import detected: a → b → c → a"
    
    def test_format_cycle_message_long_cycle(self):
        """Test cycle message formatting for long cycles."""
        scc = ["a", "b", "c", "d", "e"]
        cycle_edges = [("a", "b"), ("b", "c"), ("c", "d"), ("d", "e"), ("e", "a")]
        
        message = self.rule._format_cycle_message(scc, cycle_edges)
        assert message == "Circular import detected involving 5 modules"
    
    def test_describe_cycle(self):
        """Test cycle description generation."""
        cycle_edges = [("module_a", "module_b"), ("module_b", "module_c"), ("module_c", "module_a")]
        
        description = self.rule._describe_cycle(cycle_edges)
        assert description == "module_a imports module_b imports module_c imports module_a"
        
        # Empty cycle
        description_empty = self.rule._describe_cycle([])
        assert description_empty == "Complex cycle detected"
    
    def test_generate_cycle_suggestions_two_modules(self):
        """Test suggestion generation for two-module cycle."""
        scc = ["module_a", "module_b"]
        cycle_edges = [("module_a", "module_b"), ("module_b", "module_a")]
        current_module = "module_a"
        
        suggestions = self.rule._generate_cycle_suggestions(scc, cycle_edges, current_module)
        
        assert len(suggestions) <= 4
        assert any("merging" in suggestion.lower() for suggestion in suggestions)
        assert any("separate module" in suggestion.lower() for suggestion in suggestions)
    
    def test_generate_cycle_suggestions_small_cycle(self):
        """Test suggestion generation for small cycles."""
        scc = ["a", "b", "c"]
        cycle_edges = [("a", "b"), ("b", "c"), ("c", "a")]
        current_module = "a"
        
        suggestions = self.rule._generate_cycle_suggestions(scc, cycle_edges, current_module)
        
        assert len(suggestions) <= 4
        assert any("interface" in suggestion.lower() for suggestion in suggestions)
    
    def test_generate_cycle_suggestions_large_cycle(self):
        """Test suggestion generation for large cycles."""
        scc = ["a", "b", "c", "d", "e", "f"]
        cycle_edges = []
        current_module = "a"
        
        suggestions = self.rule._generate_cycle_suggestions(scc, cycle_edges, current_module)
        
        assert len(suggestions) <= 4
        assert any("architecture" in suggestion.lower() for suggestion in suggestions)
    
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
    
    def test_visit_no_current_module(self):
        """Test visit when current module cannot be determined."""
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = None
        
        import_graph = Mock()
        symbol_index = Mock()
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "module.py"
        
        findings = list(self.rule.visit(ctx))
        assert findings == []
    
    def test_visit_with_cycle_detection(self):
        """Test visit with actual cycle detection."""
        # Mock project graph components
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = "module_a"
        
        import_graph = Mock()
        # Mock SCC detection returning a cycle containing current module
        import_graph.sccs.return_value = [
            ["module_a", "module_b"],  # Cycle containing current module
            ["module_c"]              # No cycle
        ]
        import_graph.module_file_path.return_value = "/path/to/file.py"
        import_graph.minimal_cycle_example.return_value = [("module_a", "module_b"), ("module_b", "module_a")]
        
        symbol_index = Mock()
        
        # Mock adapter and import parsing
        adapter = Mock()
        import_info = Mock()
        import_info.module = "module_b"
        import_info.target = None
        import_info.path = None
        import_info.source = None
        import_info.range = (10, 50)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "module_a.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.text = "import module_b\n"
        
        # Mock config
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.rule == "imports.cycle"
        assert finding.severity == "error"
        assert "Circular import detected" in finding.message
        assert finding.start_byte == 10
        assert finding.end_byte == 50
        assert finding.autofix is None  # Suggest-only
        
        # Check metadata
        assert finding.meta["current_module"] == "module_a"
        assert finding.meta["cycle_modules"] == ["module_a", "module_b"]
        assert finding.meta["cycle_size"] == 2
        assert finding.meta["target_module"] == "module_b"
        assert "suggestions" in finding.meta
    
    def test_visit_with_external_modules_ignored(self):
        """Test cycle detection ignoring external modules."""
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = "internal_module"
        
        import_graph = Mock()
        # Mock SCC with external modules
        import_graph.sccs.return_value = [
            ["internal_module", "external_lib"]  # Cycle with external module
        ]
        # Only internal module has file path
        import_graph.module_file_path.side_effect = lambda mod: "/path/file.py" if mod == "internal_module" else None
        
        symbol_index = Mock()
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "internal_module.py"
        ctx.config = {"imports.cycle.ignore_external": True}
        
        findings = list(self.rule.visit(ctx))
        
        # Should find no cycles since external modules are filtered out
        assert len(findings) == 0
    
    def test_visit_fallback_whole_file_finding(self):
        """Test fallback to whole-file finding when import parsing fails."""
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = "module_a"
        
        import_graph = Mock()
        import_graph.sccs.return_value = [["module_a", "module_b"]]
        import_graph.module_file_path.return_value = "/path/to/file.py"
        import_graph.minimal_cycle_example.return_value = [("module_a", "module_b"), ("module_b", "module_a")]
        
        symbol_index = Mock()
        
        # Mock adapter that returns no imports (or fails)
        adapter = Mock()
        adapter.iter_imports.return_value = []
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "module_a.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.text = "some code"
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        finding = findings[0]
        assert finding.start_byte == 0  # Whole file
        assert finding.end_byte == len(ctx.text)
        assert "target_module" not in finding.meta  # No specific target
    
    def test_autofix_safety_suggest_only(self):
        """Test that autofix is always None (suggest-only)."""
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = "module_a"
        
        import_graph = Mock()
        import_graph.sccs.return_value = [["module_a", "module_b"]]
        import_graph.module_file_path.return_value = "/path/to/file.py"
        import_graph.minimal_cycle_example.return_value = [("module_a", "module_b"), ("module_b", "module_a")]
        
        symbol_index = Mock()
        
        adapter = Mock()
        import_info = Mock()
        import_info.module = "module_b"
        import_info.target = None
        import_info.path = None
        import_info.source = None
        import_info.range = (10, 50)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "module_a.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.text = "import module_b\n"
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        # All findings should have no autofix (suggest-only)
        for finding in findings:
            assert finding.autofix is None
            assert "suggestions" in finding.meta  # Should have suggestions instead of autofix
    
    def test_priority_p0_behavior(self):
        """Test P0 priority behavior - should report all cycles."""
        resolver = Mock()
        resolver.canonical_module_for_file.return_value = "module_a"
        
        import_graph = Mock()
        # Multiple cycles, rule should report all but limit to one per file
        import_graph.sccs.return_value = [
            ["module_a", "module_b"],        # First cycle
            ["module_a", "module_c", "module_d"]  # Second cycle
        ]
        import_graph.module_file_path.return_value = "/path/to/file.py"
        import_graph.minimal_cycle_example.return_value = [("module_a", "module_b"), ("module_b", "module_a")]
        
        symbol_index = Mock()
        
        adapter = Mock()
        import_info = Mock()
        import_info.module = "module_b"
        import_info.range = (10, 50)
        adapter.iter_imports.return_value = [import_info]
        
        ctx = Mock()
        ctx.project_graph = (resolver, import_graph, symbol_index)
        ctx.file_path = "module_a.py"
        ctx.adapter = adapter
        ctx.tree = Mock()
        ctx.text = "import module_b\n"
        ctx.config = {}
        
        findings = list(self.rule.visit(ctx))
        
        # Should find the cycle (P0 priority means report critical issues)
        assert len(findings) >= 1
        finding = findings[0]
        assert finding.severity == "error"  # P0 rules typically use error severity

