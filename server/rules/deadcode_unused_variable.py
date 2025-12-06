"""
Rule: deadcode.unused_variable

Detects locals/parameters that are never read using scopes/refs and safely
fixes them by renaming to a throwaway identifier (default) or deleting
simple declarations when configured.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
    from ..engine.scopes import Symbol, Ref, ScopeGraph
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
    from engine.scopes import Symbol, Ref, ScopeGraph

from typing import List, Set, Optional, Tuple
import re


class DeadcodeUnusedVariableRule:
    """Detect locals/parameters that are never read."""
    
    meta = RuleMeta(
        id="deadcode.unused_variable",
        category="deadcode", 
        tier=1,  # Requires scopes
        priority="P2",
        autofix_safety="safe",
        description="Detect locals/parameters that are never read. Replace with '_' (or language-appropriate form) or remove trivial decls.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=True,  # This rule needs scope analysis
        project_graph=False
    )
    
    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Find unused variables in the file."""
        findings = []
        
        if not ctx.scopes:
            return findings
        
        # Get configuration options
        config = getattr(ctx, 'config', {}) or {}
        mode = (config.get("unused_var_fix") or "underscore").lower()  # "underscore" | "remove"
        allowlist = set(config.get("unused_allowlist", []))  # names never flagged (e.g., "_", "_ctx")
        
        # Language-specific handling
        language = self._get_language_from_path(ctx.file_path)
        if language not in self.meta.langs:
            return findings
        
        # Find unused symbols in function/method/block scopes
        for scope in self._get_relevant_scopes(ctx.scopes):
            for symbol in ctx.scopes.symbols_in_scope(scope.id):
                if not self._is_trackable_symbol(symbol):
                    continue
                    
                name = symbol.name
                if name in allowlist:
                    continue
                
                # Skip already-suppressed names
                if self._is_already_suppressed(name, language):
                    continue
                
                # Check if symbol has any read references
                if self._has_read_references(symbol, ctx.scopes):
                    continue  # Used → not dead
                
                # Fallback: check if variable appears in a return statement
                # This catches cases like: return { showSuccessToast, showErrorToast }
                # where the scope graph may not recognize object shorthand as a read
                if self._is_used_in_return_statement(name, ctx.text):
                    continue
                
                # Create finding with appropriate autofix
                finding = self._create_finding(symbol, ctx, mode, language)
                if finding:
                    findings.append(finding)
        
        return findings
    
    def _get_language_from_path(self, file_path: str) -> str:
        """Extract language from file extension."""
        ext = file_path.split('.')[-1].lower()
        ext_map = {
            'py': 'python',
            'ts': 'typescript', 
            'tsx': 'typescript',
            'js': 'javascript',
            'jsx': 'javascript',
            'go': 'go',
            'java': 'java',
            'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp',
            'c': 'c',
            'cs': 'csharp',
            'rb': 'ruby',
            'rs': 'rust',
            'swift': 'swift'
        }
        return ext_map.get(ext, 'python')
    
    def _get_relevant_scopes(self, scopes: ScopeGraph) -> List:
        """Get scopes where unused variables should be tracked.
        
        NOTE: We only track function/method scopes, NOT class scopes.
        Class-level variables are typically intentional declarations 
        (Pydantic fields, dataclass fields, ORM columns, etc.)
        """
        # Only track variables in function/method scopes, not class scopes
        # Class-level variables are almost always intentional field declarations
        relevant_kinds = {"function", "method", "block"}
        relevant_scopes = []
        
        for scope_id, scope in scopes._scopes.items():
            if scope.kind in relevant_kinds:
                relevant_scopes.append(scope)
        
        return relevant_scopes
    
    def _is_trackable_symbol(self, symbol: Symbol) -> bool:
        """Check if symbol should be tracked for unused analysis."""
        # Track local variables, parameters, and loop variables
        # NOTE: Exclude 'field' - class fields are intentional declarations
        trackable_kinds = {"local", "variable", "param", "parameter", "loop_var", "const", "let"}
        return symbol.kind in trackable_kinds
    
    def _is_class_field_annotation(self, symbol: Symbol, ctx: RuleContext) -> bool:
        """Check if symbol is a class field type annotation (not a real variable).
        
        Pattern: `name: Type` in a class body (Pydantic, dataclass, ORM, etc.)
        These are declarations, not unused variables.
        """
        # Get the scope this symbol is in
        if not ctx.scopes:
            return False
        
        scope = ctx.scopes.get_scope(symbol.scope_id)
        if scope and scope.kind == "class":
            return True  # Any symbol in class scope is likely a field declaration
        
        # Also check if the parent scope is a class
        if scope and scope.parent_id is not None:
            parent_scope = ctx.scopes.get_scope(scope.parent_id)
            if parent_scope and parent_scope.kind == "class":
                # But only if we're not in a method
                if scope.kind not in {"function", "method"}:
                    return True
        
        return False
    
    def _is_already_suppressed(self, name: str, language: str) -> bool:
        """Check if the name is already a suppression pattern."""
        if name == "_":
            return True
        
        if language == "rust" and name.startswith("_"):
            return True
        
        # Common throwaway patterns
        if name in {"_unused", "_ignore", "__unused__"}:
            return True
            
        return False
    
    def _is_used_in_return_statement(self, name: str, file_text: str) -> bool:
        """Check if variable is used in a return statement.
        
        This catches cases where the scope graph misses object shorthand syntax:
          return { showSuccessToast, showErrorToast }
        
        The variable is clearly being read/returned, so it's not unused.
        """
        # Look for return statements containing this name
        # Patterns: return name, return { name }, return { name, ... }, return [name]
        import re
        
        # Pattern 1: return variable directly
        if re.search(rf'\breturn\s+{re.escape(name)}\b', file_text):
            return True
        
        # Pattern 2: return in object shorthand { name } or { name, ... }
        # This is JS/TS specific but harmless for other languages
        if re.search(rf'\breturn\s*\{{[^}}]*\b{re.escape(name)}\b[^}}]*\}}', file_text):
            return True
        
        # Pattern 3: return in array [name] or [name, ...]
        if re.search(rf'\breturn\s*\[[^\]]*\b{re.escape(name)}\b[^\]]*\]', file_text):
            return True
        
        return False
    
    def _has_read_references(self, symbol: Symbol, scopes: ScopeGraph) -> bool:
        """Check if symbol has any read references (non-write usage)."""
        # Check the symbol's own scope and descendant scopes for references
        scope_ids_to_check = [symbol.scope_id] + scopes.descendants_of(symbol.scope_id)
        
        # Count references to this symbol
        reference_count = 0
        
        for scope_id in scope_ids_to_check:
            for ref in scopes.refs_in_scope(scope_id):
                if ref.name == symbol.name:
                    # Check if this ref would resolve to our symbol
                    resolved = scopes.resolve_visible(ref.scope_id, ref.name)
                    if resolved and resolved == symbol:
                        reference_count += 1
        
        # If there are 2+ references, at least one must be a read (not just the definition)
        # This handles cases like: result = result + [item]
        # where both the LHS (definition) and RHS (read) reference the same symbol
        if reference_count >= 2:
            return True
        
        # Check if there are OTHER symbols with the same name in the same scope
        # This indicates a reassignment pattern (e.g., result = result + x)
        # where each assignment creates a new symbol but they're all the same variable
        same_name_symbols = []
        for sym in scopes.symbols_in_scope(symbol.scope_id):
            if sym.name == symbol.name:
                same_name_symbols.append(sym)
        
        # If there are multiple symbols with the same name in the same scope,
        # this is a reassignment pattern and we should not flag any of them as unused
        # (unless they truly are - checked by reference_count above)
        if len(same_name_symbols) > 1:
            # Check if ANY of the same-name symbols has references
            # If so, the variable is used and we shouldn't flag this specific assignment
            for other_sym in same_name_symbols:
                if other_sym != symbol:
                    other_ref_count = 0
                    for scope_id in scope_ids_to_check:
                        for ref in scopes.refs_in_scope(scope_id):
                            if ref.name == other_sym.name:
                                resolved = scopes.resolve_visible(ref.scope_id, ref.name)
                                if resolved and resolved == other_sym:
                                    other_ref_count += 1
                    if other_ref_count >= 1:
                        # Another symbol with the same name has references,
                        # so this is part of a reassignment chain
                        return True
        
        # For single reference: check if it's outside the definition location
        if reference_count == 1:
            for scope_id in scope_ids_to_check:
                for ref in scopes.refs_in_scope(scope_id):
                    if ref.name == symbol.name:
                        resolved = scopes.resolve_visible(ref.scope_id, ref.name)
                        if resolved and resolved == symbol:
                            # Original heuristic: exclude refs at the definition location
                            if ref.byte < symbol.start_byte or ref.byte >= symbol.end_byte:
                                return True
        
        return False
    
    def _create_finding(self, symbol: Symbol, ctx: RuleContext, mode: str, language: str) -> Optional[Finding]:
        """Create a finding with appropriate autofix for unused symbol."""
        name = symbol.name
        kind = symbol.kind or "variable"
        
        # Try to generate autofix
        autofix = None
        message = f"Unused {kind} '{name}'"
        
        if mode == "remove" and kind != "param" and self._can_safely_remove(symbol, ctx.text):
            # Generate removal edit
            start_byte, end_byte = self._get_removal_span(symbol, ctx.text)
            if start_byte is not None and end_byte is not None:
                autofix = [Edit(start_byte, end_byte, "")]
                message = f"'{name}' is assigned but never used—safe to remove."
        else:
            # Generate rename edit - find the ACTUAL variable name in the text
            replacement = self._get_throwaway_name(name, language)
            if replacement and replacement != name:
                # CRITICAL: Find the actual position of the variable name, not the entire symbol span
                # The symbol.start_byte may point to the entire assignment/declaration
                name_start, name_end = self._find_variable_name_position(symbol, ctx.text)
                if name_start is not None and name_end is not None:
                    autofix = [Edit(name_start, name_end, replacement)]
                    message = f"'{name}' is assigned but never used—rename to '{replacement}' if intentional."
        
        if not autofix:
            # Fallback: report without fix
            message = f"'{name}' is assigned but never used."
        
        return Finding(
            rule=self.meta.id,
            message=message,
            severity="info",
            file=ctx.file_path,
            start_byte=symbol.start_byte,
            end_byte=symbol.end_byte,
            autofix=autofix,
            meta={
                "symbol_name": name,
                "symbol_kind": kind,
                "language": language,
                "mode": mode
            }
        )
    
    def _can_safely_remove(self, symbol: Symbol, text: str) -> bool:
        """Check if symbol declaration can be safely removed."""
        # Only remove simple declarations without initializers
        # This is a conservative heuristic based on the symbol position
        
        # Get the line containing the symbol
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        
        line = text[line_start:line_end].strip()
        
        # Simple heuristics for safe removal:
        # - Single variable declaration without assignment
        # - Not a parameter (already checked)
        # - Not part of destructuring or multiple declarations
        
        simple_patterns = [
            f"let {symbol.name};",           # JS/TS: let x;
            f"var {symbol.name};",           # JS: var x;
            f"int {symbol.name};",           # C/C++/Java: int x;
            f"{symbol.name} := ",            # Go: check it's not an assignment
        ]
        
        # Very conservative: only remove if it looks like a simple declaration
        for pattern in simple_patterns:
            if pattern in line and '=' not in line:
                return True
        
        return False
    
    def _find_variable_name_position(self, symbol: Symbol, text: str) -> Tuple[Optional[int], Optional[int]]:
        """
        Find the actual position of the variable name in the text.
        
        The symbol.start_byte and symbol.end_byte may span an entire expression
        (e.g., "result = result + [item]" for an assignment), but we only want
        to replace the variable name itself (e.g., just "result" on the left side).
        
        Strategy:
        1. Search for the variable name within the symbol's span
        2. For assignments, prioritize the left-hand side occurrence
        3. Handle edge cases like tuple unpacking, declarations, etc.
        """
        name = symbol.name
        
        # Get the text around the symbol
        symbol_text = text[symbol.start_byte:symbol.end_byte]
        
        # Pattern to match the variable name as a complete identifier (word boundary)
        pattern = r'\b' + re.escape(name) + r'\b'
        
        # Search within the symbol span
        match = re.search(pattern, symbol_text)
        if match:
            # Calculate absolute position
            name_start = symbol.start_byte + match.start()
            name_end = symbol.start_byte + match.end()
            
            # Validate that we found the right occurrence
            actual_name = text[name_start:name_end]
            if actual_name == name:
                return name_start, name_end
        
        # Fallback: if we can't find it safely, don't provide an autofix
        return None, None
    
    def _get_removal_span(self, symbol: Symbol, text: str) -> Tuple[Optional[int], Optional[int]]:
        """Get byte span for removing entire declaration statement."""
        # Find the line boundaries
        line_start = text.rfind('\n', 0, symbol.start_byte) + 1
        line_end = text.find('\n', symbol.start_byte)
        if line_end == -1:
            line_end = len(text)
        else:
            line_end += 1  # Include the newline
        
        line = text[line_start:line_end]
        
        # Only remove if the line looks like a simple declaration
        if symbol.name in line and line.strip().endswith(';'):
            return line_start, line_end
        
        return None, None
    
    def _get_throwaway_name(self, original_name: str, language: str) -> str:
        """Get appropriate throwaway name for the language."""
        if language == "go":
            return "_"  # Go's blank identifier
        elif language == "rust":
            # Rust prefers underscore prefix to keep the binding
            if original_name.startswith("_"):
                return original_name  # Already suppressed
            return f"_{original_name}"
        else:
            # Most languages accept underscore as throwaway
            return "_"


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    from . import register
    register_rule(DeadcodeUnusedVariableRule())  # Global registry
    register(DeadcodeUnusedVariableRule())       # Local RULES list
except ImportError:
    from engine.registry import register_rule
    from rules import register
    register_rule(DeadcodeUnusedVariableRule())  # Global registry
    register(DeadcodeUnusedVariableRule())       # Local RULES list


