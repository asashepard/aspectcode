"""
Rule: deadcode.unused_parameter

Detects unused parameters via scopes/refs and provides suggested changes
(underscore-style rename or parameter removal hints). No direct edits.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
    from ..engine.scopes import Symbol, Ref, ScopeGraph
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
    from engine.scopes import Symbol, Ref, ScopeGraph

from typing import List, Set, Optional, Dict, Any


# Preferred "mark as intentionally unused" styles per language
THROWAWAY = {
    "python": "_",
    "javascript": "_",
    "typescript": "_",
    "go": "_",
    "rust": None,   # prefer leading underscore on the original name, e.g., `_arg`
    "java": "_",
    "csharp": "_",
    "cpp": "_",
    "c": "_",
    "ruby": "_",
    "swift": "_",
}


class DeadcodeUnusedParameterRule:
    """Suggest changes for parameters that are never read."""
    
    meta = RuleMeta(
        id="deadcode.unused_parameter",
        category="deadcode", 
        tier=1,  # Requires scopes
        priority="P1",
        autofix_safety="suggest-only",
        description="Suggest changes for parameters that are never read (underscore-rename or removal hint).",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=True,  # This rule needs scope analysis
        project_graph=False
    )
    
    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Find unused parameters in the file."""
        findings = []
        
        if not ctx.scopes or not ctx.tree:
            return findings
        
        # Get configuration options
        config = getattr(ctx, 'config', {}) or {}
        allowlist = set(config.get("unused_param_allowlist", []))  # e.g., {"_","_ctx","_req"}
        prefer_remove = bool(config.get("suggest_param_remove_when_safe", False))
        
        # Language-specific handling
        language = self._get_language_from_path(ctx.file_path)
        if language not in self.meta.langs:
            return findings
        
        # Since the Python adapter doesn't extract parameters as symbols,
        # we need to find function definitions directly and analyze their parameters
        function_nodes = self._find_function_definitions(ctx.tree)
        
        for func_node in function_nodes:
            # Skip probable override methods
            if self._is_probable_override_node(func_node, ctx.text):
                continue
            
            parameters = self._extract_parameters(func_node)
            
            for param_info in parameters:
                param_name = param_info['name']
                param_start = param_info['start_byte']
                param_end = param_info['end_byte']
                
                if param_name in allowlist or self._already_suppressed(language, param_name):
                    continue
                
                # Check if parameter has read references by looking at scope references
                if self._parameter_has_read_references(param_name, func_node, ctx.scopes, param_start, param_end):
                    continue  # Used → not unused
                
                # Create suggestion for unused parameter
                finding = self._create_parameter_suggestion(param_info, ctx, language, prefer_remove)
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
    
    def _find_function_definitions(self, tree) -> List:
        """Find all function definition nodes in the tree."""
        function_nodes = []
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type in ['function_definition', 'method_definition']:
                function_nodes.append(node)
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    visit_node(child)
        
        visit_node(tree.root_node)
        return function_nodes
    
    def _extract_parameters(self, func_node) -> List[Dict]:
        """Extract parameter information from a function definition node."""
        parameters = []
        
        # Look for parameters node
        for child in func_node.children:
            if hasattr(child, 'type') and child.type == 'parameters':
                # Extract individual parameters
                for param_child in child.children:
                    if hasattr(param_child, 'type') and param_child.type == 'identifier':
                        param_name = param_child.text.decode('utf-8', 'ignore')
                        parameters.append({
                            'name': param_name,
                            'start_byte': param_child.start_byte,
                            'end_byte': param_child.end_byte,
                            'node': param_child
                        })
        
        return parameters
    
    def _is_probable_override_node(self, func_node, text: str) -> bool:
        """Check if function node is likely an override method."""
        # Get text around the function to check for override indicators
        start_byte = max(0, func_node.start_byte - 200)
        end_byte = min(len(text), func_node.end_byte + 100)
        func_text = text[start_byte:end_byte]
        
        # Check for override indicators
        override_indicators = [
            "@Override",
            " override ",
            "override ",
            "public ",
            "export ",
            "abstract ",
            "virtual "
        ]
        
        for indicator in override_indicators:
            if indicator in func_text:
                return True
        
        return False
    
    def _parameter_has_read_references(self, param_name: str, func_node, scopes: ScopeGraph, param_start: int, param_end: int) -> bool:
        """Check if parameter has read references within the function scope."""
        # Get all references to this parameter name
        all_refs = []
        for scope_id in scopes._scopes.keys():
            for ref in scopes.refs_in_scope(scope_id):
                if ref.name == param_name:
                    all_refs.append(ref)
        
        # Find references that are within this function's body but outside the parameter declaration
        func_start = func_node.start_byte
        func_end = func_node.end_byte
        
        for ref in all_refs:
            # Check if reference is within this function
            if func_start <= ref.byte <= func_end:
                # Exclude the parameter declaration itself
                if ref.byte < param_start or ref.byte >= param_end:
                    return True  # Found a read reference within this function
        
        return False
    
    def _create_parameter_suggestion(self, param_info: Dict, ctx: RuleContext, language: str, prefer_remove: bool) -> Optional[Finding]:
        """Create a suggestion finding for unused parameter."""
        param_name = param_info['name']
        start_byte = param_info['start_byte']
        end_byte = param_info['end_byte']
        
        # Generate suggested placeholder name
        suggested_name = self._suggest_placeholder(language, param_name)
        
        # Create diff showing the suggested change
        diff = self._create_parameter_diff(ctx, param_info, suggested_name)
        
        # Create rationale explaining the suggestion
        rationale = self._create_rationale(language, param_name)
        
        # Check if removal hint should be added
        extra_note = ""
        if prefer_remove and self._looks_like_last_parameter(param_info, ctx.text):
            extra_note = " If this is an internal function and the trailing parameter has no callers expecting it, consider removing it."
        
        message = f"Unused parameter '{param_name}'. Consider renaming to a throwaway identifier.{extra_note}"
        
        return Finding(
            rule=self.meta.id,
            message=message,
            severity="info",
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            autofix=None,  # suggest-only, no direct edits
            meta={
                "parameter_name": param_name,
                "suggested_name": suggested_name,
                "language": language,
                "diff": diff,
                "rationale": rationale + extra_note,
                "suggest_removal": prefer_remove and self._looks_like_last_parameter(param_info, ctx.text)
            }
        )
    
    def _create_parameter_diff(self, ctx: RuleContext, param_info: Dict, replacement: str) -> str:
        """Create a unified diff showing the suggested parameter change."""
        text = ctx.text.encode('utf-8') if isinstance(ctx.text, str) else ctx.text
        start_byte = param_info['start_byte']
        end_byte = param_info['end_byte']
        
        # Find line boundaries
        line_start = text.rfind(b'\n', 0, start_byte) + 1
        line_end = text.find(b'\n', end_byte)
        if line_end == -1:
            line_end = len(text)
        
        # Get the original line
        before_line = text[line_start:line_end].decode('utf-8', 'ignore')
        
        # Create the modified line
        before_param = text[line_start:start_byte].decode('utf-8', 'ignore')
        after_param = text[end_byte:line_end].decode('utf-8', 'ignore')
        after_line = before_param + replacement + after_param
        
        # Create unified diff format
        return (
            "--- a/parameter\n"
            "+++ b/parameter\n"
            f"-{before_line}\n"
            f"+{after_line}\n"
        )
    
    def _looks_like_last_parameter(self, param_info: Dict, text: str) -> bool:
        """Check if parameter appears to be the last in the parameter list."""
        param_end = param_info['end_byte']
        
        # Look for closing parenthesis after this parameter
        search_end = min(len(text), param_end + 50)
        after_param = text[param_end:search_end]
        
        # Find next significant characters
        paren_pos = after_param.find(')')
        comma_pos = after_param.find(',')
        
        # If we find ')' before ',' (or no comma), this might be the last parameter
        return paren_pos != -1 and (comma_pos == -1 or paren_pos < comma_pos)
    
    def _already_suppressed(self, language: str, name: str) -> bool:
        """Check if the parameter name is already suppressed."""
        # Single underscore is universally suppressed
        if name == "_":
            return True
        
        # Language-specific suppression patterns
        if language == "rust" and name.startswith("_"):
            return True
        
        # Common suppression patterns across languages
        suppressed_patterns = ["_unused", "_ignore", "__unused__"]
        if name in suppressed_patterns:
            return True
        
        # Python-specific: 'self' and 'cls' are special parameters
        if language == "python" and name in {"self", "cls"}:
            return True
        
        return False
    
    def _suggest_placeholder(self, language: str, name: str) -> str:
        """Get appropriate throwaway name for the language."""
        if language == "rust":
            return name if name.startswith("_") else f"_{name}"
        return THROWAWAY.get(language, "_")
    
    def _create_rationale(self, language: str, name: str) -> str:
        """Create rationale explaining the suggestion."""
        if language == "rust":
            return "In Rust, prefixing with '_' silences unused warnings without changing the signature."
        elif language == "go":
            return "In Go, the blank identifier '_' indicates the value is intentionally unused."
        elif language == "python":
            return "In Python, '_' is a conventional placeholder for intentionally unused parameters."
        else:
            return "Use an underscore-style placeholder to document intent without altering behavior."


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    from . import register
    register_rule(DeadcodeUnusedParameterRule())  # Global registry
    register(DeadcodeUnusedParameterRule())       # Local RULES list
except ImportError:
    from engine.registry import register_rule
    from rules import register
    register_rule(DeadcodeUnusedParameterRule())  # Global registry
    register(DeadcodeUnusedParameterRule())       # Local RULES list


