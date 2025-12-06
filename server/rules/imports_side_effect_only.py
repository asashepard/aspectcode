"""
Rule: imports.side_effect_only

Detects module imports that are only used for side effects (not accessed directly).
Suggests making them explicit with comments or explicit side-effect syntax.

Supports: Python, TypeScript, JavaScript
"""

import re
from typing import Iterator, Set, Dict, Optional, List
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext, Edit
from engine.scopes import Symbol


class ImportsSideEffectOnlyRule:
    """
    Detects imports that are only used for side effects.
    
    Examples:
    Python:
        import logging.config  # No direct access to logging.config
        import my_module  # No access to my_module.* 
    
    JavaScript/TypeScript:
        import 'side-effects'  # Explicit side effect (OK)
        import myModule from 'module'  # No access to myModule (flag)
        const myModule = require('module')  # No access to myModule (flag)
    """
    
    @property
    def meta(self) -> RuleMeta:
        return RuleMeta(
            id="imports.side_effect_only",
            category="imports",
            tier=1,
            autofix_safety="suggest-only",
            priority="P1",
            description="Import used only for side effects; consider explicit annotation",
            langs=["python", "typescript", "javascript"],
        )
    
    @property
    def requires(self) -> Requires:
        return Requires(scopes=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the context to find side-effect-only imports."""
        if ctx.scopes is None:
            return
        
        # Detect language
        language = self._detect_language(ctx.file_path)
        if language not in ["python", "typescript", "javascript"]:
            return
        
        # Find all import statements and their usage
        imports = self._find_import_statements(ctx.text, language)
        
        for import_info in imports:
            if self._is_side_effect_only_import(import_info, ctx, language):
                yield self._create_finding_for_side_effect_import(import_info, ctx, language)
    
    def _detect_language(self, file_path: str) -> str:
        """Detect the programming language from file extension."""
        if file_path.endswith('.py'):
            return "python"
        elif file_path.endswith('.ts'):
            return "typescript"
        elif file_path.endswith('.js'):
            return "javascript"
        return "unknown"
    
    def _find_import_statements(self, text: str, language: str) -> List[Dict]:
        """Find all import statements in the code."""
        imports = []
        
        if language == "python":
            imports.extend(self._find_python_imports(text))
        elif language in ["typescript", "javascript"]:
            imports.extend(self._find_js_ts_imports(text))
        
        return imports
    
    def _find_python_imports(self, text: str) -> List[Dict]:
        """Find Python import statements."""
        imports = []
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                continue
            
            # Regular import: import module
            import_match = re.match(r'^import\s+([a-zA-Z_][a-zA-Z0-9_.]*)', stripped)
            if import_match:
                module_name = import_match.group(1)
                start_byte = sum(len(lines[i]) + 1 for i in range(line_num)) - 1 if line_num > 0 else 0
                end_byte = start_byte + len(line)
                
                imports.append({
                    'type': 'import',
                    'module': module_name,
                    'imported_name': module_name.split('.')[0],  # Top-level name
                    'line_num': line_num,
                    'line': line,
                    'start_byte': start_byte,
                    'end_byte': end_byte
                })
                continue
            
            # From import: from module import name (skip these for now)
            from_match = re.match(r'^from\s+([a-zA-Z_][a-zA-Z0-9_.]*)\s+import\s+', stripped)
            if from_match:
                # This is a from import, not side-effect only
                continue
        
        return imports
    
    def _find_js_ts_imports(self, text: str) -> List[Dict]:
        """Find JavaScript/TypeScript import statements."""
        imports = []
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('//') or stripped.startswith('/*'):
                continue
            
            start_byte = sum(len(lines[i]) + 1 for i in range(line_num)) - 1 if line_num > 0 else 0
            end_byte = start_byte + len(line)
            
            # ES6 import with binding: import name from 'module'
            es6_import_match = re.match(r'^import\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s+from\s+[\'"]([^\'"]+)[\'"]', stripped)
            if es6_import_match:
                imported_name = es6_import_match.group(1)
                module_name = es6_import_match.group(2)
                imports.append({
                    'type': 'es6_import',
                    'module': module_name,
                    'imported_name': imported_name,
                    'line_num': line_num,
                    'line': line,
                    'start_byte': start_byte,
                    'end_byte': end_byte
                })
                continue
            
            # ES6 destructured import: import { name } from 'module' (skip)
            destructure_match = re.match(r'^import\s+\{[^}]+\}\s+from\s+[\'"]([^\'"]+)[\'"]', stripped)
            if destructure_match:
                # These are explicit imports, not side-effect only
                continue
            
            # Side-effect import: import 'module' (this is already explicit, skip)
            side_effect_match = re.match(r'^import\s+[\'"]([^\'"]+)[\'"]', stripped)
            if side_effect_match:
                # This is already explicit side-effect import, don't flag
                continue
            
            # CommonJS require: const name = require('module')
            require_match = re.match(r'^(?:const|let|var)\s+([a-zA-Z_$][a-zA-Z0-9_$]*)\s*=\s*require\s*\([\'"]([^\'"]+)[\'"]\)', stripped)
            if require_match:
                imported_name = require_match.group(1)
                module_name = require_match.group(2)
                imports.append({
                    'type': 'require',
                    'module': module_name,
                    'imported_name': imported_name,
                    'line_num': line_num,
                    'line': line,
                    'start_byte': start_byte,
                    'end_byte': end_byte
                })
                continue
        
        return imports
    
    def _is_side_effect_only_import(self, import_info: Dict, ctx: RuleContext, language: str) -> bool:
        """Check if an import is only used for side effects."""
        imported_name = import_info['imported_name']
        
        # Look for any usage of the imported name in the code
        if self._has_direct_usage(imported_name, ctx.text, import_info):
            return False
        
        # Check if it's a known side-effect module pattern
        if self._is_known_side_effect_module(import_info['module'], language):
            return False  # These are expected to be side-effect only
        
        # Check scope graph for symbol usage
        if self._has_scope_usage(imported_name, ctx):
            return False
        
        return True
    
    def _has_direct_usage(self, name: str, text: str, import_info: Dict) -> bool:
        """Check for direct usage of the imported name."""
        # Get text after the import line to avoid matching the import itself
        import_line_end = import_info['end_byte']
        text_after_import = text[import_line_end:]
        
        # Look for usage patterns
        usage_patterns = [
            rf'\b{re.escape(name)}\.',  # name.something
            rf'\b{re.escape(name)}\[',  # name[something]
            rf'\b{re.escape(name)}\(',  # name(something)
            rf'\b{re.escape(name)}\s*=',  # name = something (reassignment)
            rf'=\s*{re.escape(name)}\b',  # something = name
            rf'\({re.escape(name)}\)',  # (name)
            rf',\s*{re.escape(name)}\b',  # , name
            rf'\s{re.escape(name)}\s',  # space name space
        ]
        
        for pattern in usage_patterns:
            if re.search(pattern, text_after_import):
                return True
        
        return False
    
    def _is_known_side_effect_module(self, module: str, language: str) -> bool:
        """Check if this is a known side-effect module that's expected to not be used directly."""
        side_effect_modules = {
            'python': {
                'logging.config',
                'dotenv',
                'warnings',
                'matplotlib.pyplot',  # Often imported for side effects
                'seaborn',  # Often imported for side effects
                'pkg_resources',  # setuptools side effects
            },
            'javascript': {
                'polyfills',
                'babel-polyfill',
                '@babel/polyfill',
                'core-js',
                'regenerator-runtime',
            },
            'typescript': {
                'polyfills',
                'babel-polyfill', 
                '@babel/polyfill',
                'core-js',
                'regenerator-runtime',
                'reflect-metadata',
            }
        }
        
        return module in side_effect_modules.get(language, set())
    
    def _has_scope_usage(self, name: str, ctx: RuleContext) -> bool:
        """Check if the name is used in the scope graph."""
        if ctx.scopes is None:
            return False
        
        # Use iter_symbols to properly iterate over all symbols
        for symbol in ctx.scopes.iter_symbols():
            # Check if this symbol references the imported name
            if symbol.name == name and symbol.kind in ['reference', 'usage']:
                return True
                
            # Check if any symbol has the imported name as part of its metadata
            if symbol.meta and symbol.meta.get('references', []):
                if name in symbol.meta['references']:
                    return True
        
        return False
    
    def _create_finding_for_side_effect_import(self, import_info: Dict, ctx: RuleContext, language: str) -> Finding:
        """Create a finding for a side-effect-only import."""
        imported_name = import_info['imported_name']
        module = import_info['module']
        
        # Generate appropriate message based on import type
        if language == "python":
            message = f"Import '{imported_name}' appears to be used only for side effects. Consider adding a comment to clarify intent."
        else:
            message = f"Import '{imported_name}' from '{module}' appears to be used only for side effects. Consider using explicit side-effect import syntax."
        
        # Generate autofix suggestions
        autofix_edits = self._generate_autofix_suggestions(import_info, language)
        
        # Create metadata
        meta = {
            "imported_name": imported_name,
            "module": module,
            "import_type": import_info['type'],
            "language": language,
            "suggestion": self._get_suggestion_text(import_info, language)
        }
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            severity="info",
            file=ctx.file_path,
            start_byte=import_info['start_byte'],
            end_byte=import_info['end_byte'],
            autofix=autofix_edits,
            meta=meta
        )
        
        return finding
    
    def _generate_autofix_suggestions(self, import_info: Dict, language: str) -> Optional[List[Edit]]:
        """Generate autofix suggestions (suggest-only)."""
        # For suggest-only, we return None but provide suggestions in metadata
        return None
    
    def _get_suggestion_text(self, import_info: Dict, language: str) -> str:
        """Get suggestion text for the autofix."""
        imported_name = import_info['imported_name']
        module = import_info['module']
        import_type = import_info['type']
        
        if language == "python":
            if import_type == "import":
                return f"Consider adding: # Import {imported_name} for side effects"
        
        elif language in ["typescript", "javascript"]:
            if import_type == "es6_import":
                return f"Consider using: import '{module}' // Side effects only"
            elif import_type == "require":
                return f"Consider using: require('{module}') // Side effects only"
        
        return "Add a comment to clarify that this import is for side effects only"


# Export the rule class
RULES = [ImportsSideEffectOnlyRule]


