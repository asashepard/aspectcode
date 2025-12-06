"""
Comprehensive tests for imports.side_effect_only rule.

Tests side effect import detection across Python, TypeScript, and JavaScript.
"""

import pytest
from unittest.mock import Mock, MagicMock
from engine.types import RuleContext, Edit, Finding
from engine.scopes import Symbol, Scope
from rules.imports_side_effect_only import ImportsSideEffectOnlyRule


class TestImportsSideEffectOnlyRule:
    """Test the imports side effect only rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = ImportsSideEffectOnlyRule()
    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        assert self.rule.meta.id == "imports.side_effect_only"
        assert self.rule.meta.category == "imports"
        assert self.rule.meta.tier == 1
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.meta.priority == "P1"
        assert set(self.rule.meta.langs) == {"python", "typescript", "javascript"}
        assert self.rule.requires.scopes is True
    
    # Language Detection Tests
    def test_detect_language_python(self):
        """Test Python file detection."""
        assert self.rule._detect_language("test.py") == "python"
        assert self.rule._detect_language("module.py") == "python"
    
    def test_detect_language_typescript(self):
        """Test TypeScript file detection."""
        assert self.rule._detect_language("test.ts") == "typescript"
        assert self.rule._detect_language("module.ts") == "typescript"
    
    def test_detect_language_javascript(self):
        """Test JavaScript file detection."""
        assert self.rule._detect_language("test.js") == "javascript"
        assert self.rule._detect_language("module.js") == "javascript"
    
    def test_detect_language_unknown(self):
        """Test unknown file type detection."""
        assert self.rule._detect_language("test.txt") == "unknown"
        assert self.rule._detect_language("test.rs") == "unknown"
    
    # Python Import Finding Tests
    def test_find_python_imports_simple(self):
        """Test finding simple Python imports."""
        text = "import os\nimport sys"
        imports = self.rule._find_python_imports(text)
        
        assert len(imports) == 2
        assert imports[0]['type'] == 'import'
        assert imports[0]['module'] == 'os'
        assert imports[0]['imported_name'] == 'os'
        assert imports[1]['module'] == 'sys'
    
    def test_find_python_imports_dotted(self):
        """Test finding dotted Python imports."""
        text = "import logging.config\nimport xml.etree.ElementTree"
        imports = self.rule._find_python_imports(text)
        
        assert len(imports) == 2
        assert imports[0]['module'] == 'logging.config'
        assert imports[0]['imported_name'] == 'logging'  # Top-level name
        assert imports[1]['module'] == 'xml.etree.ElementTree'
        assert imports[1]['imported_name'] == 'xml'
    
    def test_find_python_imports_skip_from_import(self):
        """Test skipping from imports."""
        text = "import os\nfrom sys import path\nimport json"
        imports = self.rule._find_python_imports(text)
        
        assert len(imports) == 2
        assert imports[0]['module'] == 'os'
        assert imports[1]['module'] == 'json'
    
    def test_find_python_imports_with_comments(self):
        """Test finding imports with comments and empty lines."""
        text = """# Header comment
import os
# Comment about logging
import logging

import json"""
        imports = self.rule._find_python_imports(text)
        
        assert len(imports) == 3
        assert imports[0]['module'] == 'os'
        assert imports[1]['module'] == 'logging'
        assert imports[2]['module'] == 'json'
    
    # JavaScript/TypeScript Import Finding Tests
    def test_find_js_ts_imports_es6(self):
        """Test finding ES6 imports."""
        text = """import React from 'react';
import lodash from 'lodash';"""
        imports = self.rule._find_js_ts_imports(text)
        
        assert len(imports) == 2
        assert imports[0]['type'] == 'es6_import'
        assert imports[0]['module'] == 'react'
        assert imports[0]['imported_name'] == 'React'
        assert imports[1]['module'] == 'lodash'
        assert imports[1]['imported_name'] == 'lodash'
    
    def test_find_js_ts_imports_require(self):
        """Test finding CommonJS require imports."""
        text = """const fs = require('fs');
let path = require('path');
var util = require('util');"""
        imports = self.rule._find_js_ts_imports(text)
        
        assert len(imports) == 3
        assert imports[0]['type'] == 'require'
        assert imports[0]['module'] == 'fs'
        assert imports[0]['imported_name'] == 'fs'
        assert imports[1]['imported_name'] == 'path'
        assert imports[2]['imported_name'] == 'util'
    
    def test_find_js_ts_imports_skip_destructured(self):
        """Test skipping destructured imports."""
        text = """import React from 'react';
import { useState, useEffect } from 'react';
import lodash from 'lodash';"""
        imports = self.rule._find_js_ts_imports(text)
        
        # Should skip the destructured import
        assert len(imports) == 2
        assert imports[0]['imported_name'] == 'React'
        assert imports[1]['imported_name'] == 'lodash'
    
    def test_find_js_ts_imports_skip_side_effect(self):
        """Test skipping explicit side effect imports."""
        text = """import React from 'react';
import 'polyfills';
import lodash from 'lodash';"""
        imports = self.rule._find_js_ts_imports(text)
        
        # Should skip the side effect import
        assert len(imports) == 2
        assert imports[0]['imported_name'] == 'React'
        assert imports[1]['imported_name'] == 'lodash'
    
    # Direct Usage Detection Tests
    def test_has_direct_usage_property_access(self):
        """Test detecting property access usage."""
        import_info = {'end_byte': 10}
        text = "import os\nos.path.join('a', 'b')"
        
        assert self.rule._has_direct_usage("os", text, import_info) is True
    
    def test_has_direct_usage_method_call(self):
        """Test detecting method call usage."""
        import_info = {'end_byte': 12}
        text = "import json\njson.loads(data)"
        
        assert self.rule._has_direct_usage("json", text, import_info) is True
    
    def test_has_direct_usage_bracket_access(self):
        """Test detecting bracket access usage."""
        import_info = {'end_byte': 15}
        text = "import myModule\nmyModule['key']"
        
        assert self.rule._has_direct_usage("myModule", text, import_info) is True
    
    def test_has_direct_usage_assignment(self):
        """Test detecting assignment usage."""
        import_info = {'end_byte': 15}
        text = "import myModule\ndata = myModule"
        
        assert self.rule._has_direct_usage("myModule", text, import_info) is True
    
    def test_has_direct_usage_function_arg(self):
        """Test detecting function argument usage."""
        import_info = {'end_byte': 15}
        text = "import myModule\nprocess(myModule)"
        
        assert self.rule._has_direct_usage("myModule", text, import_info) is True
    
    def test_has_direct_usage_no_usage(self):
        """Test no usage detection."""
        import_info = {'end_byte': 10}
        text = "import os\nprint('hello')"
        
        assert self.rule._has_direct_usage("os", text, import_info) is False
    
    # Known Side Effect Module Tests
    def test_is_known_side_effect_module_python(self):
        """Test Python known side effect modules."""
        assert self.rule._is_known_side_effect_module("logging.config", "python") is True
        assert self.rule._is_known_side_effect_module("dotenv", "python") is True
        assert self.rule._is_known_side_effect_module("warnings", "python") is True
        assert self.rule._is_known_side_effect_module("matplotlib.pyplot", "python") is True
        assert self.rule._is_known_side_effect_module("os", "python") is False
    
    def test_is_known_side_effect_module_javascript(self):
        """Test JavaScript known side effect modules."""
        assert self.rule._is_known_side_effect_module("babel-polyfill", "javascript") is True
        assert self.rule._is_known_side_effect_module("core-js", "javascript") is True
        assert self.rule._is_known_side_effect_module("polyfills", "javascript") is True
        assert self.rule._is_known_side_effect_module("react", "javascript") is False
    
    def test_is_known_side_effect_module_typescript(self):
        """Test TypeScript known side effect modules."""
        assert self.rule._is_known_side_effect_module("reflect-metadata", "typescript") is True
        assert self.rule._is_known_side_effect_module("core-js", "typescript") is True
        assert self.rule._is_known_side_effect_module("@angular/core", "typescript") is False
    
    # Scope Usage Tests
    def test_has_scope_usage_found(self):
        """Test scope usage detection when usage is found."""
        symbol1 = Mock()
        symbol1.name = "os"
        symbol1.kind = "reference"
        
        symbol2 = Mock()
        symbol2.name = "sys"
        symbol2.kind = "import"
        
        scope = Mock()
        scope.symbols = [symbol1, symbol2]
        
        ctx = Mock()
        ctx.scopes = [scope]
        
        assert self.rule._has_scope_usage("os", ctx) is True
    
    def test_has_scope_usage_metadata_references(self):
        """Test scope usage detection via metadata references."""
        symbol = Mock()
        symbol.name = "other"
        symbol.kind = "variable"
        symbol.meta = {"references": ["os", "sys"]}
        
        scope = Mock()
        scope.symbols = [symbol]
        
        ctx = Mock()
        ctx.scopes = [scope]
        
        assert self.rule._has_scope_usage("os", ctx) is True
    
    def test_has_scope_usage_not_found(self):
        """Test scope usage detection when no usage found."""
        symbol = Mock()
        symbol.name = "other"
        symbol.kind = "variable"
        symbol.meta = {}
        
        scope = Mock()
        scope.symbols = [symbol]
        
        ctx = Mock()
        ctx.scopes = [scope]
        
        assert self.rule._has_scope_usage("os", ctx) is False
    
    def test_has_scope_usage_no_scopes(self):
        """Test scope usage with no scopes."""
        ctx = Mock()
        ctx.scopes = None
        
        assert self.rule._has_scope_usage("os", ctx) is False
    
    # Side Effect Detection Integration Tests
    def test_is_side_effect_only_import_true(self):
        """Test detecting side effect only import."""
        import_info = {
            'imported_name': 'unused_module',
            'module': 'unused_module',
            'end_byte': 20
        }
        
        ctx = Mock()
        ctx.text = "import unused_module\nprint('hello')"
        ctx.scopes = []
        
        result = self.rule._is_side_effect_only_import(import_info, ctx, "python")
        assert result is True
    
    def test_is_side_effect_only_import_has_usage(self):
        """Test import with direct usage is not side effect only."""
        import_info = {
            'imported_name': 'os',
            'module': 'os',
            'end_byte': 10
        }
        
        ctx = Mock()
        ctx.text = "import os\nos.path.join('a', 'b')"
        ctx.scopes = []
        
        result = self.rule._is_side_effect_only_import(import_info, ctx, "python")
        assert result is False
    
    def test_is_side_effect_only_import_known_side_effect(self):
        """Test known side effect module is not flagged."""
        import_info = {
            'imported_name': 'logging',
            'module': 'logging.config',
            'end_byte': 20
        }
        
        ctx = Mock()
        ctx.text = "import logging.config\nprint('hello')"
        ctx.scopes = []
        
        result = self.rule._is_side_effect_only_import(import_info, ctx, "python")
        assert result is False
    
    def test_is_side_effect_only_import_scope_usage(self):
        """Test import with scope usage is not side effect only."""
        import_info = {
            'imported_name': 'os',
            'module': 'os',
            'end_byte': 10
        }
        
        symbol = Mock()
        symbol.name = "os"
        symbol.kind = "reference"
        
        scope = Mock()
        scope.symbols = [symbol]
        
        ctx = Mock()
        ctx.text = "import os\nprint('hello')"
        ctx.scopes = [scope]
        
        result = self.rule._is_side_effect_only_import(import_info, ctx, "python")
        assert result is False
    
    # Suggestion Text Tests
    def test_get_suggestion_text_python(self):
        """Test Python suggestion text."""
        import_info = {
            'imported_name': 'mymodule',
            'module': 'mymodule',
            'type': 'import'
        }
        
        suggestion = self.rule._get_suggestion_text(import_info, "python")
        assert "Consider adding: # Import mymodule for side effects" in suggestion
    
    def test_get_suggestion_text_javascript_es6(self):
        """Test JavaScript ES6 suggestion text."""
        import_info = {
            'imported_name': 'mymodule',
            'module': 'mymodule',
            'type': 'es6_import'
        }
        
        suggestion = self.rule._get_suggestion_text(import_info, "javascript")
        assert "Consider using: import 'mymodule' // Side effects only" in suggestion
    
    def test_get_suggestion_text_javascript_require(self):
        """Test JavaScript require suggestion text."""
        import_info = {
            'imported_name': 'mymodule',
            'module': 'mymodule',
            'type': 'require'
        }
        
        suggestion = self.rule._get_suggestion_text(import_info, "javascript")
        assert "Consider using: require('mymodule') // Side effects only" in suggestion
    
    # Finding Creation Tests
    def test_create_finding_structure(self):
        """Test finding creation structure."""
        import_info = {
            'imported_name': 'unused_module',
            'module': 'unused_module',
            'type': 'import',
            'start_byte': 0,
            'end_byte': 20
        }
        
        ctx = Mock()
        ctx.file_path = "test.py"
        
        finding = self.rule._create_finding_for_side_effect_import(import_info, ctx, "python")
        
        assert finding.rule == "imports.side_effect_only"
        assert "unused_module" in finding.message
        assert "side effects" in finding.message.lower()
        assert finding.severity == "info"
        assert finding.file == "test.py"
        assert finding.start_byte == 0
        assert finding.end_byte == 20
        assert finding.autofix is None  # suggest-only
        assert finding.meta["imported_name"] == "unused_module"
        assert finding.meta["language"] == "python"
        assert "suggestion" in finding.meta
    
    # Integration Tests with Mock Context
    def test_visit_python_side_effect_import(self):
        """Test visiting Python file with side effect import."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.text = "import unused_module\nprint('hello world')"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "imports.side_effect_only"
        assert "unused_module" in findings[0].message
    
    def test_visit_python_with_usage(self):
        """Test visiting Python file with used import."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.text = "import os\nos.path.join('a', 'b')"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_visit_javascript_side_effect_import(self):
        """Test visiting JavaScript file with side effect import."""
        ctx = Mock()
        ctx.file_path = "test.js"
        ctx.text = "const unused = require('unused-module');\nconsole.log('hello');"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "imports.side_effect_only"
        assert "unused" in findings[0].message
    
    def test_visit_typescript_side_effect_import(self):
        """Test visiting TypeScript file with side effect import."""
        ctx = Mock()
        ctx.file_path = "test.ts"
        ctx.text = "import unused from 'unused-module';\nconsole.log('hello');"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert findings[0].rule == "imports.side_effect_only"
        assert "unused" in findings[0].message
    
    def test_visit_no_scopes_returns_empty(self):
        """Test visiting without scopes returns empty."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.text = "import os"
        ctx.scopes = None
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    def test_visit_unknown_language_returns_empty(self):
        """Test visiting unknown language returns empty."""
        ctx = Mock()
        ctx.file_path = "test.rs"
        ctx.text = "use std::io;"
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0
    
    # Edge Cases and Real World Examples
    def test_python_multiple_imports_mixed_usage(self):
        """Test Python file with mix of used and unused imports."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.text = """import os
import sys  
import json
import unused_module

print(os.path.join('a', 'b'))
data = json.loads('{}')"""
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        # Should find sys and unused_module as side effect only
        assert len(findings) == 2
        finding_names = [f.meta["imported_name"] for f in findings]
        assert "sys" in finding_names
        assert "unused_module" in finding_names
    
    def test_javascript_complex_usage_patterns(self):
        """Test JavaScript with complex usage patterns."""
        ctx = Mock()
        ctx.file_path = "test.js"
        ctx.text = """const fs = require('fs');
const unused1 = require('unused1');
const path = require('path');
const unused2 = require('unused2');

fs.readFileSync('file.txt');
console.log(path.join('a', 'b'));"""
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        # Should find unused1 and unused2
        assert len(findings) == 2
        finding_names = [f.meta["imported_name"] for f in findings]
        assert "unused1" in finding_names
        assert "unused2" in finding_names
    
    def test_python_with_known_side_effect_modules(self):
        """Test Python with known side effect modules."""
        ctx = Mock()
        ctx.file_path = "test.py"
        ctx.text = """import logging.config
import dotenv
import warnings
import unknown_module"""
        ctx.scopes = []
        
        findings = list(self.rule.visit(ctx))
        
        # Should only find unknown_module
        assert len(findings) == 1
        assert findings[0].meta["imported_name"] == "unknown_module"
    
    def test_autofix_safety_metadata(self):
        """Test autofix safety is suggest-only."""
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        # Test that autofix generation returns None
        import_info = {"imported_name": "test", "module": "test", "type": "import"}
        result = self.rule._generate_autofix_suggestions(import_info, "python")
        assert result is None
    
    def test_tier_1_requirement(self):
        """Test that this is a tier 1 rule requiring scopes."""
        assert self.rule.meta.tier == 1
        assert self.rule.requires.scopes is True

