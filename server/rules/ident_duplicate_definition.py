"""
Rule: ident.duplicate_definition

Detects duplicate top-level symbol definitions in the SAME FILE that are likely
to be LLM / copy-paste artifacts and cause confusion or bugs.

Supported languages: Python, TypeScript, JavaScript, Java, C#

This rule detects:
- Two or more functions with the same name in the same file
- Two or more classes with the same name in the same file
- For TS/JS: multiple exports of the same name from a module
- For Java/C#: multiple top-level types with same name in same compilation unit
"""

from typing import Iterator, Dict, List, Set, Tuple, Optional
from collections import defaultdict
import re

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
    from ..engine.scopes import Symbol, ScopeGraph
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
    from engine.scopes import Symbol, ScopeGraph


class IdentDuplicateDefinitionRule:
    """
    Detect duplicate top-level symbol definitions in the same file.
    
    This catches LLM / copy-paste artifacts where the same function or class
    is defined multiple times at the top level of a file, which typically
    indicates an error rather than intentional overloading.
    
    Examples:
    
    Python:
        def process_data(x):
            return x * 2
        
        def process_data(x):  # DUPLICATE!
            return x + 1
    
    TypeScript:
        function calculate(n: number) { return n * 2; }
        function calculate(n: number) { return n + 1; }  // DUPLICATE!
    
    Java:
        public class User { }
        public class User { }  // DUPLICATE!
    """
    
    meta = RuleMeta(
        id="ident.duplicate_definition",
        category="ident",
        tier=1,  # Requires scopes to identify top-level definitions
        priority="P1",
        autofix_safety="suggest-only",
        description="Detect duplicate top-level symbol definitions (functions, classes) in the same file - likely LLM/copy-paste artifacts",
        langs=["python", "typescript", "javascript", "java", "csharp"]
    )
    
    requires = Requires(
        raw_text=False,
        syntax=True,
        scopes=True,  # Need scopes to identify top-level symbols
        project_graph=False
    )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find duplicate top-level definitions in the file."""
        if not ctx.scopes:
            return
        
        # Get language from file extension
        language = self._get_language_from_path(ctx.file_path)
        if language not in self.meta.langs:
            return
        
        # Collect all top-level symbol definitions
        top_level_symbols = self._collect_top_level_symbols(ctx.scopes, language)
        
        # Group symbols by (name, kind) to find duplicates
        symbol_groups = self._group_symbols_by_name_and_kind(top_level_symbols)
        
        # Generate findings for each group with duplicates
        for (name, kind), symbols in symbol_groups.items():
            if len(symbols) > 1:
                # For Java/C#: skip method overloads (same name, different signatures)
                if language in ('java', 'csharp') and kind == 'function':
                    if self._are_method_overloads(symbols, ctx.text):
                        continue  # Valid overloads, not duplicates
                
                # We have duplicates!
                yield from self._create_duplicate_findings(name, kind, symbols, ctx, language)
    
    def _get_language_from_path(self, file_path: str) -> str:
        """Extract language from file extension."""
        ext = file_path.split('.')[-1].lower()
        ext_map = {
            'py': 'python',
            'ts': 'typescript',
            'tsx': 'typescript',
            'js': 'javascript',
            'jsx': 'javascript',
            'java': 'java',
            'cs': 'csharp',
        }
        return ext_map.get(ext, '')
    
    def _collect_top_level_symbols(self, scopes: ScopeGraph, language: str) -> List[Symbol]:
        """
        Collect all top-level symbol definitions.
        
        Top-level means symbols defined at module/file scope, not nested
        inside functions, methods, or inner classes.
        """
        top_level_symbols = []
        
        # Find the module/file scope (typically the root scope with kind='module' or 'file')
        module_scope_id = self._find_module_scope(scopes)
        
        if module_scope_id is None:
            # Fallback: collect from all scopes with no parent (top-level)
            for scope_id, scope in scopes._scopes.items():
                if scope.parent_id is None or scope.parent_id == 0:
                    symbols = scopes.symbols_in_scope(scope_id)
                    top_level_symbols.extend(self._filter_relevant_symbols(symbols, language))
        else:
            # Collect symbols directly in the module scope
            symbols = scopes.symbols_in_scope(module_scope_id)
            top_level_symbols.extend(self._filter_relevant_symbols(symbols, language))
            
            # Also check immediate child scopes for class/function definitions
            # (they may be in their own scopes but still top-level from module perspective)
            for scope_id, scope in scopes._scopes.items():
                if scope.parent_id == module_scope_id:
                    # This is a direct child of module scope
                    # Check if the scope itself represents a top-level definition
                    if scope.kind in {'function', 'class', 'method', 'type'}:
                        # Create a pseudo-symbol for this scope
                        if hasattr(scope, 'name') and scope.name:
                            # Use the scope's metadata to create a symbol representation
                            symbols = scopes.symbols_in_scope(scope_id)
                            # Look for the defining symbol
                            for sym in symbols:
                                if sym.kind in {'function', 'class', 'interface', 'enum', 'type'}:
                                    if scope.parent_id == module_scope_id:
                                        top_level_symbols.append(sym)
        
        return top_level_symbols
    
    def _find_module_scope(self, scopes: ScopeGraph) -> Optional[int]:
        """Find the module/file root scope."""
        for scope_id, scope in scopes._scopes.items():
            if scope.kind in {'module', 'file', 'program'}:
                return scope_id
        
        # Fallback: find scope with no parent
        for scope_id, scope in scopes._scopes.items():
            if scope.parent_id is None or scope.parent_id == 0:
                return scope_id
        
        return None
    
    def _filter_relevant_symbols(self, symbols: List[Symbol], language: str) -> List[Symbol]:
        """
        Filter to only symbols that should be checked for duplicates.
        
        We care about:
        - Functions (def, function, method when top-level)
        - Classes (class)
        - Interfaces (interface, for TS/Java)
        - Enums (enum, for TS/Java/C#)
        - Exported constants (for TS/JS: export const foo = ...)
        """
        relevant_kinds = {
            'function', 'class', 'interface', 'enum', 'type', 
            'method',  # Top-level methods in some languages
            'const',   # For exported constants in TS/JS
        }
        
        filtered = []
        for symbol in symbols:
            if symbol.kind in relevant_kinds:
                # Additional filtering for language-specific cases
                if language in {'typescript', 'javascript'}:
                    # For TS/JS, only include if it's exported or a declaration
                    # Check metadata or name for export hints
                    if self._is_exported_or_declaration(symbol):
                        filtered.append(symbol)
                else:
                    # For Python, Java, C#: include all top-level functions/classes
                    filtered.append(symbol)
        
        return filtered
    
    def _is_exported_or_declaration(self, symbol: Symbol) -> bool:
        """
        Check if a symbol is exported or a declaration (for TS/JS).
        
        For now, we include all function/class declarations at top level.
        A more sophisticated check would parse export statements.
        """
        # Simple heuristic: include all function/class symbols
        # In practice, the scope system should distinguish exported vs internal
        return symbol.kind in {'function', 'class', 'interface', 'enum', 'type'}
    
    def _group_symbols_by_name_and_kind(self, symbols: List[Symbol]) -> Dict[Tuple[str, str], List[Symbol]]:
        """
        Group symbols by (name, kind) to find duplicates.
        
        We group by kind as well as name because having a function and a class
        with the same name might be intentional (e.g., factory pattern), but
        having two functions with the same name is almost certainly a bug.
        
        Note: For Java/C#, method overloads (same name, different parameters) are valid.
        We detect this by checking if methods have different signatures.
        """
        groups = defaultdict(list)
        
        for symbol in symbols:
            # Normalize kind for grouping purposes
            normalized_kind = self._normalize_kind(symbol.kind)
            key = (symbol.name, normalized_kind)
            groups[key].append(symbol)
        
        return groups
    
    def _normalize_kind(self, kind: str) -> str:
        """
        Normalize symbol kinds for grouping.
        
        For example, 'method' at top-level should be grouped with 'function'.
        """
        if kind in {'function', 'method'}:
            return 'function'
        elif kind in {'class', 'interface'}:
            return 'class'
        elif kind in {'enum', 'type'}:
            return 'type'
        else:
            return kind
    
    def _are_method_overloads(self, symbols: List[Symbol], source_text: str) -> bool:
        """
        Check if multiple methods with the same name are valid overloads (Java/C#).
        
        In Java and C#, method overloading is valid when methods have the same name
        but different parameter lists. We detect this by extracting the parameter
        portion of each method signature and checking if they differ.
        
        Returns True if these are valid overloads, False if they're duplicates.
        """
        if len(symbols) < 2:
            return True  # Single method is not a duplicate
        
        # Ensure source_text is a string
        if isinstance(source_text, bytes):
            source_text = source_text.decode('utf-8', errors='replace')
        
        # Extract parameter signatures for each symbol
        signatures = set()
        
        for symbol in symbols:
            # Get the source line(s) for this symbol
            try:
                # Extract a portion of code around the symbol definition
                start = symbol.start_byte
                # Find the next 300 chars or until end of source
                end = min(start + 300, len(source_text))
                snippet = source_text[start:end]
                
                # Extract the parameter portion specifically for this method name
                # We need to find "methodName(params)" not just any parentheses
                # Pattern: method_name followed by params, accounting for possible generics
                method_pattern = rf'{re.escape(symbol.name)}\s*\([^)]*\)'
                param_match = re.search(method_pattern, snippet)
                if param_match:
                    # Extract just the params portion
                    full_match = param_match.group(0)
                    params_start = full_match.find('(')
                    param_sig = full_match[params_start:]
                    signatures.add(param_sig)
                else:
                    # Couldn't extract params, assume it's unique
                    signatures.add(f"_unknown_{symbol.start_byte}")
            except Exception:
                # If extraction fails, assume unique
                signatures.add(f"_error_{symbol.start_byte}")
        
        # If all signatures are different, these are valid overloads
        return len(signatures) > 1
    
    def _create_duplicate_findings(
        self, 
        name: str, 
        kind: str, 
        symbols: List[Symbol], 
        ctx: RuleContext,
        language: str
    ) -> Iterator[Finding]:
        """
        Create findings for duplicate symbols.
        
        Strategy: Report each duplicate occurrence with a message listing all other
        occurrences. This makes it clear to the user where all the duplicates are.
        """
        # Sort symbols by position (start_byte) to show them in order
        sorted_symbols = sorted(symbols, key=lambda s: s.start_byte)
        
        # Get line numbers for each symbol
        symbol_lines = []
        for symbol in sorted_symbols:
            line_num = self._get_line_number(symbol.start_byte, ctx.text)
            symbol_lines.append((symbol, line_num))
        
        # Create a finding for each duplicate after the first
        first_symbol, first_line = symbol_lines[0]
        duplicate_lines = [line for _, line in symbol_lines[1:]]
        
        # Strategy: Report the first occurrence with a summary of all duplicates
        # This is similar to how naming.project_term_inconsistency works
        yield self._create_finding_for_first_duplicate(
            name, kind, first_symbol, first_line, duplicate_lines, ctx, language
        )
        
        # Also report each subsequent duplicate with a reference back to the first
        for symbol, line_num in symbol_lines[1:]:
            yield self._create_finding_for_nth_duplicate(
                name, kind, symbol, line_num, first_line, ctx, language
            )
    
    def _get_line_number(self, byte_offset: int, text: str) -> int:
        """Convert byte offset to 1-based line number."""
        if byte_offset < 0 or byte_offset > len(text):
            return 1
        
        line_num = text[:byte_offset].count('\n') + 1
        return line_num
    
    def _create_finding_for_first_duplicate(
        self,
        name: str,
        kind: str,
        symbol: Symbol,
        line_num: int,
        duplicate_lines: List[int],
        ctx: RuleContext,
        language: str
    ) -> Finding:
        """Create a finding for the first occurrence of a duplicate."""
        duplicate_lines_str = ", ".join(str(line) for line in duplicate_lines)
        
        message = (
            f"'{name}' is defined multiple times in this file (also at line{'s' if len(duplicate_lines) > 1 else ''} {duplicate_lines_str})—"
            f"keep one definition and remove the others."
        )
        
        return Finding(
            rule=self.meta.id,
            message=message,
            severity="warning",
            file=ctx.file_path,
            start_byte=symbol.start_byte,
            end_byte=symbol.end_byte,
            autofix=None,  # suggest-only, no autofix
            meta={
                "symbol_name": name,
                "symbol_kind": kind,
                "language": language,
                "duplicate_count": len(duplicate_lines) + 1,
                "duplicate_lines": duplicate_lines,
                "is_first_occurrence": True
            }
        )
    
    def _create_finding_for_nth_duplicate(
        self,
        name: str,
        kind: str,
        symbol: Symbol,
        line_num: int,
        first_line: int,
        ctx: RuleContext,
        language: str
    ) -> Finding:
        """Create a finding for a subsequent duplicate occurrence."""
        message = (
            f"'{name}' is already defined at line {first_line}—"
            f"remove this duplicate or rename it."
        )
        
        return Finding(
            rule=self.meta.id,
            message=message,
            severity="warning",
            file=ctx.file_path,
            start_byte=symbol.start_byte,
            end_byte=symbol.end_byte,
            autofix=None,  # suggest-only, no autofix
            meta={
                "symbol_name": name,
                "symbol_kind": kind,
                "language": language,
                "first_occurrence_line": first_line,
                "is_first_occurrence": False
            }
        )


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    from . import register
    register_rule(IdentDuplicateDefinitionRule())
    register(IdentDuplicateDefinitionRule())
except ImportError:
    from engine.registry import register_rule
    from rules import register
    register_rule(IdentDuplicateDefinitionRule())
    register(IdentDuplicateDefinitionRule())
