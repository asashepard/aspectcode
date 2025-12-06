"""
Rule: imports.unused

Detects unused import statements and provides safe autofixes to remove them.
Supports multiple languages and handles complex cases like partial unused imports.
"""

from typing import Iterator, Set, List, Dict, Optional
import re

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
    from ..engine.scopes import Symbol, Ref, ScopeGraph
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
    from engine.scopes import Symbol, Ref, ScopeGraph


class ImportsUnusedRule:
    """Detect and autofix unused imports across multiple languages."""
    
    meta = RuleMeta(
        id="imports.unused",
        category="imports",
        tier=1,  # Requires scopes
        priority="P2",
        autofix_safety="safe",
        description="Unused import; remove to clean up namespace",
        langs=["python", "typescript", "javascript", "go", "java", "csharp", "ruby", "rust"],
        surface="kb"
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=True,  # This rule needs scope analysis
        project_graph=False
    )
    
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find unused imports in the file."""
        if not ctx.scopes:
            return
        
        # Get language-specific configuration
        language = self._detect_language(ctx.file_path)
        config = getattr(ctx, 'config', {})
        
        # Language-specific settings
        consider_type_checking = config.get('imports.unused.consider_type_checking_usage', False)
        consider_exports = config.get('imports.unused.consider_exports', True)
        
        # Find language-specific exports
        exports = set()
        if consider_exports:
            exports = self._find_exports(ctx.text, language)
        
        # Check each import symbol for usage
        for symbol in ctx.scopes.iter_symbols(kind="import"):
            if not self._is_symbol_used(symbol, ctx.scopes, ctx.text, exports, consider_type_checking, language):
                yield self._create_finding_for_unused_import(symbol, ctx, language)
    
    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        if file_path.endswith('.py'):
            return 'python'
        elif file_path.endswith('.ts') or file_path.endswith('.tsx'):
            return 'typescript'
        elif file_path.endswith('.js') or file_path.endswith('.jsx'):
            return 'javascript'
        elif file_path.endswith('.go'):
            return 'go'
        elif file_path.endswith('.java'):
            return 'java'
        elif file_path.endswith('.cs'):
            return 'csharp'
        elif file_path.endswith('.rb'):
            return 'ruby'
        elif file_path.endswith('.rs'):
            return 'rust'
        else:
            return 'unknown'
    
    def _is_symbol_used(self, symbol: Symbol, scopes: ScopeGraph, text: str, 
                       exports: Set[str], consider_type_checking: bool, language: str) -> bool:
        """Check if an import symbol is used anywhere in the file.
        
        Args:
            consider_type_checking: If False, type-only usage counts as "used".
                                   If True, type-only usage is ignored (stricter).
        """
        # Check for direct references in scope graph
        if scopes.has_refs_to(symbol):
            # Language-specific handling for type-only imports
            if consider_type_checking and language in ['typescript', 'python']:
                # Strict mode: only count runtime usage as "used"
                if self._has_runtime_usage(symbol, scopes, text, language):
                    return True
                # Type-only usage doesn't count in strict mode, fall through
            else:
                # Default: any usage (including type-only) counts as "used"
                return True
        
        # Check if it's re-exported
        if symbol.name in exports:
            return True
        
        # Check for indirect usage (getattr, reflection, etc.)
        if self._has_indirect_usage(symbol.name, text, language):
            return True
        
        # Fallback: text-based check for direct usage (scope graph may miss some cases)
        # Look for the symbol name used as a function call or accessed outside the import line
        if self._has_text_based_usage(symbol, text, language):
            return True
        
        return False
    
    def _has_text_based_usage(self, symbol: Symbol, text: str, language: str) -> bool:
        """Fallback text-based check for symbol usage.
        
        This catches cases where the scope graph may miss references, such as
        when the symbol is called as a function: name(...) or name=...
        """
        import re
        name = symbol.name
        
        # Find all occurrences of the name in the text
        usage_pattern = rf'(?<!["\'\w.])({re.escape(name)})(?!["\'\w])'
        
        # We need to skip the import statement itself
        # Find where the import block ends for this file
        import_block_end = self._find_import_block_end(text, language)
        
        # Search only after the import block
        text_to_search = text[import_block_end:]
        
        for match in re.finditer(usage_pattern, text_to_search):
            # Check context to exclude false positives
            match_start = match.start()
            line_start = text_to_search.rfind('\n', 0, match_start) + 1
            line_end = text_to_search.find('\n', match_start)
            if line_end == -1:
                line_end = len(text_to_search)
            line = text_to_search[line_start:line_end]
            
            # Skip if this is another import statement
            if re.match(r'^\s*(from\s+\S+\s+)?import\s+', line):
                continue
            
            # Skip if it's in a comment
            if language == 'python':
                if '#' in line and line.index('#') < (match_start - line_start):
                    continue
            elif language in ['javascript', 'typescript', 'java', 'csharp']:
                if '//' in line and line.index('//') < (match_start - line_start):
                    continue
            
            # Found a real usage
            return True
        
        return False
    
    def _find_import_block_end(self, text: str, language: str) -> int:
        """Find where the import statements end in a file."""
        import re
        
        if language == 'python':
            # Find the last import statement (including multi-line from...import)
            # Look for patterns like:
            # - import x
            # - from x import y
            # - from x import (
            #       y,
            #       z,
            #   )
            lines = text.split('\n')
            last_import_end = 0
            in_multiline_import = False
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                
                if in_multiline_import:
                    # Look for closing paren
                    if ')' in line:
                        in_multiline_import = False
                        last_import_end = sum(len(lines[j]) + 1 for j in range(i + 1))
                    continue
                
                if stripped.startswith('import ') or stripped.startswith('from '):
                    if '(' in line and ')' not in line:
                        in_multiline_import = True
                    last_import_end = sum(len(lines[j]) + 1 for j in range(i + 1))
                elif stripped and not stripped.startswith('#') and not in_multiline_import:
                    # Non-empty, non-comment, non-import line - imports are done
                    if last_import_end > 0:
                        break
            
            return last_import_end
        
        elif language in ['javascript', 'typescript']:
            # Find last import/require statement
            lines = text.split('\n')
            last_import_end = 0
            
            for i, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith('import ') or 'require(' in stripped:
                    last_import_end = sum(len(lines[j]) + 1 for j in range(i + 1))
                elif stripped and not stripped.startswith('//') and not stripped.startswith('/*'):
                    if last_import_end > 0:
                        break
            
            return last_import_end
        
        # Default: return 0 to search entire file
        return 0
    
    def _has_runtime_usage(self, symbol: Symbol, scopes: ScopeGraph, text: str, language: str) -> bool:
        """Check if symbol has runtime (non-type-only) usage."""
        if language == 'python':
            # Check if all refs are in TYPE_CHECKING blocks
            refs_outside_type_checking = False
            for ref in scopes.refs_to(symbol):
                if not self._is_in_type_checking_block(ref.byte, text):
                    refs_outside_type_checking = True
                    break
            return refs_outside_type_checking
        
        elif language == 'typescript':
            # Check if all refs are type-only
            for ref in scopes.refs_to(symbol):
                if not self._is_type_only_usage(ref.byte, text):
                    return True
            return False
        
        # Default: assume runtime usage
        return True
    
    def _find_exports(self, text: str, language: str) -> Set[str]:
        """Find exported names based on language."""
        exports = set()
        
        if language == 'python':
            exports.update(self._find_python_exports(text))
        elif language in ['typescript', 'javascript']:
            exports.update(self._find_js_ts_exports(text))
        elif language == 'go':
            exports.update(self._find_go_exports(text))
        elif language == 'java':
            exports.update(self._find_java_exports(text))
        elif language == 'csharp':
            exports.update(self._find_csharp_exports(text))
        elif language == 'ruby':
            exports.update(self._find_ruby_exports(text))
        elif language == 'rust':
            exports.update(self._find_rust_exports(text))
        
        return exports
    
    def _find_python_exports(self, text: str) -> Set[str]:
        """Find Python __all__ exports and re-export patterns."""
        exports = set()
        
        # Look for __all__ = [...] patterns
        all_pattern = r'__all__\s*=\s*\[(.*?)\]'
        matches = re.finditer(all_pattern, text, re.DOTALL)
        
        for match in matches:
            content = match.group(1)
            # Extract string literals
            string_pattern = r'["\']([^"\']+)["\']'
            names = re.findall(string_pattern, content)
            exports.update(names)
        
        # Detect "from X import Y as Y" re-export pattern
        # This is a Python idiom for intentionally re-exporting a symbol
        # Examples:
        #   from .v1 import BaseConfig as BaseConfig
        #   from pydantic import Field as Field
        reexport_pattern = r'from\s+\S+\s+import\s+(\w+)\s+as\s+\1\b'
        matches = re.finditer(reexport_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        # Also detect "import X as X" pattern (less common but valid)
        import_as_pattern = r'import\s+(\w+)\s+as\s+\1\b'
        matches = re.finditer(import_as_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_js_ts_exports(self, text: str) -> Set[str]:
        """Find JavaScript/TypeScript exports."""
        exports = set()
        
        # export { name1, name2 }
        export_pattern = r'export\s*\{\s*([^}]+)\s*\}'
        matches = re.finditer(export_pattern, text)
        for match in matches:
            content = match.group(1)
            names = re.findall(r'\b(\w+)\b', content)
            exports.update(names)
        
        # export default
        default_pattern = r'export\s+default\s+(\w+)'
        matches = re.finditer(default_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_go_exports(self, text: str) -> Set[str]:
        """Find Go public symbols (capitalized names)."""
        # In Go, capitalized identifiers are exported
        # This is a simplified heuristic
        exports = set()
        public_pattern = r'\bfunc\s+([A-Z]\w*)\s*\('
        matches = re.finditer(public_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_java_exports(self, text: str) -> Set[str]:
        """Find Java public members."""
        exports = set()
        
        # public class/interface/enum
        public_pattern = r'public\s+(?:class|interface|enum)\s+(\w+)'
        matches = re.finditer(public_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_csharp_exports(self, text: str) -> Set[str]:
        """Find C# public members."""
        exports = set()
        
        # public class/interface/enum
        public_pattern = r'public\s+(?:class|interface|enum|struct)\s+(\w+)'
        matches = re.finditer(public_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_ruby_exports(self, text: str) -> Set[str]:
        """Find Ruby public symbols."""
        # Ruby doesn't have explicit exports, but modules define public interface
        exports = set()
        
        # class/module definitions
        class_pattern = r'(?:class|module)\s+(\w+)'
        matches = re.finditer(class_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _find_rust_exports(self, text: str) -> Set[str]:
        """Find Rust public items."""
        exports = set()
        
        # pub fn/struct/enum/trait
        pub_pattern = r'pub\s+(?:fn|struct|enum|trait)\s+(\w+)'
        matches = re.finditer(pub_pattern, text)
        for match in matches:
            exports.add(match.group(1))
        
        return exports
    
    def _is_in_type_checking_block(self, byte_offset: int, text: str) -> bool:
        """Check if a byte offset is inside a TYPE_CHECKING block (Python)."""
        # Find the line containing the byte offset
        line_start = text.rfind('\n', 0, byte_offset) + 1
        
        # Search backwards for TYPE_CHECKING block start
        search_start = max(0, line_start - 2000)
        text_before = text[search_start:line_start]
        
        # Look for if TYPE_CHECKING: pattern
        if_pattern = r'if\s+TYPE_CHECKING\s*:'
        if re.search(if_pattern, text_before):
            # Check indentation to see if we're still in the block
            line_end = text.find('\n', byte_offset)
            if line_end == -1:
                line_end = len(text)
            
            current_line = text[line_start:line_end]
            current_indent = len(current_line) - len(current_line.lstrip())
            
            # Find the TYPE_CHECKING line
            lines_before = text_before.split('\n')
            for i in range(len(lines_before) - 1, -1, -1):
                line = lines_before[i]
                if re.search(if_pattern, line):
                    type_checking_indent = len(line) - len(line.lstrip())
                    return current_indent > type_checking_indent
        
        return False
    
    def _is_type_only_usage(self, byte_offset: int, text: str) -> bool:
        """Check if usage is type-only in TypeScript."""
        # Simple heuristic: check if used in type annotations
        line_start = text.rfind('\n', 0, byte_offset) + 1
        line_end = text.find('\n', byte_offset)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end]
        
        # Find the name at this offset
        text_around = text[max(0, byte_offset-20):min(len(text), byte_offset+50)]
        
        # If followed by ( or <...>( it's a function call, NOT type-only
        # e.g. useQuery<T>({ ... }) is a function call
        import re
        call_pattern = re.compile(r'\w+\s*(?:<[^>]+>)?\s*\(')
        if call_pattern.search(text_around):
            # Check if the identifier is followed by call syntax
            after_offset = text[byte_offset:min(len(text), byte_offset+100)]
            # Skip the identifier name
            match = re.match(r'\w+\s*(<[^>]+>)?\s*\(', after_offset)
            if match:
                return False  # It's a function call, not type-only
        
        # Check for type annotation contexts (not calls)
        # These are patterns where the name is used purely as a type
        type_only_patterns = [
            r':\s*\w+(?:\s*\||\s*&|\s*<)',  # Type annotation: : Type | or : Type<
            r':\s*\w+\s*$',                   # End of type annotation: : Type
            r'implements\s+\w+',
            r'extends\s+\w+',
            r'as\s+\w+',                      # Type assertion: as Type
        ]
        for pattern in type_only_patterns:
            if re.search(pattern, line):
                # But still check if it's a call on the same line
                if re.search(r'\w+\s*\(', line):
                    # There's a function call on this line, may not be type-only
                    continue
                return True
        
        return False
    
    def _has_indirect_usage(self, name: str, text: str, language: str) -> bool:
        """Check for indirect usage like reflection or getattr."""
        if language == 'python':
            return self._has_python_indirect_usage(name, text)
        elif language in ['javascript', 'typescript']:
            return self._has_js_indirect_usage(name, text)
        elif language == 'java':
            return self._has_java_indirect_usage(name, text)
        # Add more languages as needed
        
        return False
    
    def _has_python_indirect_usage(self, name: str, text: str) -> bool:
        """Check for Python indirect usage."""
        patterns = [
            rf'getattr\s*\([^,]+,\s*["\']' + re.escape(name) + rf'["\'].*?\)',
            rf'hasattr\s*\([^,]+,\s*["\']' + re.escape(name) + rf'["\'].*?\)',
            rf'setattr\s*\([^,]+,\s*["\']' + re.escape(name) + rf'["\'].*?\)',
            rf'__import__\s*\(\s*["\']' + re.escape(name) + rf'["\'].*?\)',
            rf'globals\(\)\s*\[\s*["\']' + re.escape(name) + rf'["\'].*?\]',
        ]
        
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _has_js_indirect_usage(self, name: str, text: str) -> bool:
        """Check for JavaScript/TypeScript indirect usage."""
        patterns = [
            rf'window\[\s*["\']' + re.escape(name) + rf'["\'].*?\]',
            rf'global\[\s*["\']' + re.escape(name) + rf'["\'].*?\]',
            rf'this\[\s*["\']' + re.escape(name) + rf'["\'].*?\]',
        ]
        
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _has_java_indirect_usage(self, name: str, text: str) -> bool:
        """Check for Java reflection usage."""
        patterns = [
            rf'Class\.forName\s*\(\s*["\']' + re.escape(name) + rf'["\'].*?\)',
            rf'getClass\(\)\.getField\s*\(\s*["\']' + re.escape(name) + rf'["\'].*?\)',
        ]
        
        for pattern in patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _create_finding_for_unused_import(self, symbol: Symbol, ctx: RuleContext, language: str) -> Finding:
        """Create a finding for an unused import."""
        # Generate autofix
        autofix_edits = self._generate_autofix(symbol, ctx.text, language)
        
        # Create metadata
        meta = {
            "symbol_name": symbol.name,
            "module": symbol.meta.get("module", ""),
            "import_type": self._classify_import_type(symbol, ctx.text, language),
            "language": language
        }
        
        finding = Finding(
            rule=self.meta.id,
            message=f"'{symbol.name}' is imported but never used in this file",
            severity="info",
            file=ctx.file_path,
            start_byte=symbol.start_byte,
            end_byte=symbol.end_byte,
            autofix=autofix_edits,
            meta=meta
        )
        
        return finding
    
    def _classify_import_type(self, symbol: Symbol, text: str, language: str) -> str:
        """Classify the type of import statement."""
        # Get the line containing the import
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end].strip()
        
        if language == 'python':
            if line.startswith('from '):
                return "from_import"
            elif line.startswith('import '):
                return "import"
        elif language in ['typescript', 'javascript']:
            if 'import' in line and 'from' in line:
                return "es_import"
            elif line.startswith('const ') or line.startswith('let ') or line.startswith('var '):
                return "require"
        elif language == 'go':
            return "go_import"
        elif language == 'java':
            return "java_import"
        elif language == 'csharp':
            return "using"
        elif language == 'ruby':
            return "require"
        elif language == 'rust':
            return "use"
        
        return "unknown"
    
    def _generate_autofix(self, symbol: Symbol, text: str, language: str) -> Optional[List[Edit]]:
        """Generate safe autofix edits to remove unused import."""
        import_type = self._classify_import_type(symbol, text, language)
        
        if language == 'python':
            return self._fix_python_import(symbol, text, import_type)
        elif language in ['typescript', 'javascript']:
            return self._fix_js_ts_import(symbol, text, import_type)
        elif language == 'go':
            return self._fix_go_import(symbol, text)
        elif language == 'java':
            return self._fix_java_import(symbol, text)
        elif language == 'csharp':
            return self._fix_csharp_import(symbol, text)
        elif language == 'ruby':
            return self._fix_ruby_import(symbol, text)
        elif language == 'rust':
            return self._fix_rust_import(symbol, text)
        
        return None
    
    def _fix_python_import(self, symbol: Symbol, text: str, import_type: str) -> Optional[List[Edit]]:
        """Fix Python import statements."""
        if import_type == "from_import":
            return self._fix_from_import(symbol, text)
        elif import_type == "import":
            return self._fix_import(symbol, text)
        return None
    
    def _fix_js_ts_import(self, symbol: Symbol, text: str, import_type: str) -> Optional[List[Edit]]:
        """Fix JavaScript/TypeScript import statements."""
        # Find the import line
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end]
        
        # Check if this is a multi-name import
        if ',' in line and '{' in line:
            # Remove just this name from destructured import
            return self._remove_from_destructured_import(symbol, text, line_start)
        else:
            # Remove entire import line
            if line_end < len(text) and text[line_end] == '\n':
                line_end += 1
            return [Edit(line_start, line_end, "")]
    
    def _fix_go_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix Go import statements."""
        return self._remove_import_line(symbol, text)
    
    def _fix_java_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix Java import statements."""
        return self._remove_import_line(symbol, text)
    
    def _fix_csharp_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix C# using statements."""
        return self._remove_import_line(symbol, text)
    
    def _fix_ruby_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix Ruby require statements."""
        return self._remove_import_line(symbol, text)
    
    def _fix_rust_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix Rust use statements."""
        return self._remove_import_line(symbol, text)
    
    def _remove_import_line(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Generic helper to remove an entire import line."""
        # Find line boundaries around the symbol
        # Use symbol.start_byte to find the newline BEFORE the symbol
        line_start = text.rfind('\n', 0, symbol.start_byte)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1  # Move past the newline
        
        # Find the end of this line
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        else:
            # Include the newline
            line_end += 1
        
        return [Edit(line_start, line_end, "")]
    
    def _remove_from_destructured_import(self, symbol: Symbol, text: str, line_start: int) -> Optional[List[Edit]]:
        """Remove a name from a destructured import like { name1, name2 }."""
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end]
        
        # Find the name and its surrounding commas/spaces
        name_pattern = rf'\b{re.escape(symbol.name)}\b'
        match = re.search(name_pattern, line)
        
        if match:
            name_start = line_start + match.start()
            name_end = line_start + match.end()
            
            # Handle commas
            trailing_comma = False
            i = match.end()
            while i < len(line) and line[i] in ' \t':
                i += 1
            if i < len(line) and line[i] == ',':
                trailing_comma = True
                name_end = line_start + i + 1
            
            leading_comma = False
            if not trailing_comma:
                i = match.start() - 1
                while i >= 0 and line[i] in ' \t':
                    i -= 1
                if i >= 0 and line[i] == ',':
                    leading_comma = True
                    name_start = line_start + i
            
            # Include surrounding whitespace
            if trailing_comma:
                i = name_end - line_start
                while i < len(line) and line[i] in ' \t':
                    i += 1
                name_end = line_start + i
            
            return [Edit(name_start, name_end, "")]
        
        return None
    
    
    def _fix_from_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix 'from module import ...' statements."""
        # Find the full import line
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end]
        
        # Check if this is a multi-name import
        if ',' in line:
            # Multiple imports - just remove this specific name
            name_pattern = rf'\b{re.escape(symbol.name)}\b'
            match = re.search(name_pattern, line)
            
            if match:
                name_start = line_start + match.start()
                name_end = line_start + match.end()
                
                # Handle commas and whitespace
                trailing_comma = False
                i = match.end()
                while i < len(line) and line[i] in ' \t':
                    i += 1
                if i < len(line) and line[i] == ',':
                    trailing_comma = True
                    name_end = line_start + i + 1
                
                leading_comma = False
                if not trailing_comma:
                    i = match.start() - 1
                    while i >= 0 and line[i] in ' \t':
                        i -= 1
                    if i >= 0 and line[i] == ',':
                        leading_comma = True
                        name_start = line_start + i
                
                # Include surrounding whitespace
                if trailing_comma:
                    i = name_end - line_start
                    while i < len(line) and line[i] in ' \t':
                        i += 1
                    name_end = line_start + i
                
                return [Edit(name_start, name_end, "")]
        else:
            # Single import - remove the entire line
            if line_end < len(text) and text[line_end] == '\n':
                line_end += 1
            return [Edit(line_start, line_end, "")]
        
        return None
    
    def _fix_import(self, symbol: Symbol, text: str) -> Optional[List[Edit]]:
        """Fix 'import ...' statements."""
        # Find the full import line
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end]
        
        # Check if this is a multi-module import
        if ',' in line:
            # Multiple imports - remove just this module
            module_name = symbol.meta.get("module", symbol.name)
            module_pattern = rf'\b{re.escape(module_name)}\b(?:\s+as\s+{re.escape(symbol.name)})?'
            match = re.search(module_pattern, line)
            
            if match:
                mod_start = line_start + match.start()
                mod_end = line_start + match.end()
                
                # Handle commas
                trailing_comma = False
                i = match.end()
                while i < len(line) and line[i] in ' \t':
                    i += 1
                if i < len(line) and line[i] == ',':
                    trailing_comma = True
                    mod_end = line_start + i + 1
                
                leading_comma = False
                if not trailing_comma:
                    i = match.start() - 1
                    while i >= 0 and line[i] in ' \t':
                        i -= 1
                    if i >= 0 and line[i] == ',':
                        leading_comma = True
                        mod_start = line_start + i
                
                return [Edit(mod_start, mod_end, "")]
        else:
            # Single import - remove the entire line
            if line_end < len(text) and text[line_end] == '\n':
                line_end += 1
            return [Edit(line_start, line_end, "")]
        
        return None


# Export rule for auto-discovery
RULES = [ImportsUnusedRule()]


