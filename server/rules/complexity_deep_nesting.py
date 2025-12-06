# server/rules/complexity_deep_nesting.py
"""
Rule to detect excessive nesting depth and suggest guard clauses / extraction.

This rule analyzes control flow structures for:
- Nesting depth of if/else, loops, switch/case, try/catch, etc.
- Suggests guard clauses, early returns, and function extraction when depth exceeds threshold

When thresholds are exceeded, it suggests inserting guidance comments with refactoring strategies.
"""

from typing import List, Set, Optional, Tuple, Iterator

try:
    from ..engine.types import Rule, RuleContext, Finding, RuleMeta, Requires
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleContext, Finding, RuleMeta, Requires

# Control flow node types by language that contribute to nesting depth
CONTROL_KINDS = {
    "python": {
        "if_statement", "elif_clause", "else_clause", 
        "for_statement", "while_statement", 
        "try_statement", "except_clause", "finally_clause", 
        "with_statement", "match_statement", "case_clause"
    },
    "javascript": {
        "if_statement", "else_clause", 
        "for_statement", "for_in_statement", "for_of_statement", 
        "while_statement", "do_statement", 
        "switch_statement", "switch_case", 
        "try_statement", "catch_clause", "finally_clause"
    },
    "typescript": {
        "if_statement", "else_clause", 
        "for_statement", "for_in_statement", "for_of_statement", 
        "while_statement", "do_statement", 
        "switch_statement", "switch_case", 
        "try_statement", "catch_clause", "finally_clause"
    },
    "go": {
        "if_statement", "else_clause", 
        "for_statement", 
        "switch_statement", "case_clause", 
        "type_switch_statement", 
        "select_statement", "comm_clause"
    },
    "java": {
        "if_statement", "else_clause", 
        "while_statement", "for_statement", "enhanced_for_statement", 
        "switch_block", "switch_label", 
        "try_statement", "catch_clause", "finally_clause"
    },
    "csharp": {
        "if_statement", "else_clause", 
        "while_statement", "for_statement", "foreach_statement", 
        "switch_statement", "switch_section", 
        "try_statement", "catch_clause", "finally_clause"
    },
    "cpp": {
        "if_statement", "else_clause", 
        "while_statement", "for_statement", 
        "switch_statement", "case_statement", 
        "try_statement", "catch_clause"
    },
    "c": {
        "if_statement", "else_clause", 
        "while_statement", "for_statement", 
        "switch_statement", "case_statement"
    },
    "ruby": {
        "if", "elsif", "else", 
        "while", "until", "for", 
        "case", "when", 
        "rescue", "ensure", "begin", 
        "do_block"
    },
    "rust": {
        "if_expression", "else_clause", 
        "while_expression", "for_expression", 
        "loop_expression", 
        "match_expression", "match_arm"
    },
    "swift": {
        "if_statement", "else_clause", 
        "while_statement", "for_in_statement", 
        "switch_statement", "switch_case", 
        "guard_statement", "do_statement", 
        "catch_clause", "defer_statement"
    },
}

DEFAULT_MAX_DEPTH = 3

class ComplexityDeepNestingRule(Rule):
    """Rule to detect excessive nesting depth."""
    
    meta = RuleMeta(
        id="complexity.deep_nesting",
        category="complexity",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects excessive nesting depth and suggests refactoring",
        langs=["python", "javascript", "typescript", "java", "csharp", "cpp", "c"]
    )
    
    requires = Requires(syntax=True)
    meta = RuleMeta(
        id="complexity.deep_nesting",
        category="complexity",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detect excessive nesting depth and suggest guard-clauses / extraction.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and analyze nesting depth."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
            
        if language not in self.meta.langs:
            return
            
        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return

        # Get configuration
        config = ctx.config or {}
        max_depth_allowed = int(config.get("max_depth", DEFAULT_MAX_DEPTH))
        
        # Get control flow node types for this language
        control_kinds = CONTROL_KINDS.get(language, set())
        if not control_kinds:
            return

        # Find the deepest nesting
        deepest_info = self._find_deepest_nesting(ctx, control_kinds)
        
        if not deepest_info or deepest_info["depth"] <= max_depth_allowed:
            return

        # Create finding with suggestion
        finding = self._create_finding(ctx, deepest_info, max_depth_allowed)
        if finding:
            yield finding

    def _find_deepest_nesting(self, ctx: RuleContext, control_kinds: Set[str]) -> Optional[dict]:
        """Find the deepest nesting point in the syntax tree."""
        deepest = None
        
        def walk_node(node, current_depth: int, parent_function=None):
            nonlocal deepest
            
            if not hasattr(node, 'type'):
                return
            
            node_type = node.type
            is_control_flow = node_type in control_kinds
            
            # Track if we're entering a function/method (reset nesting context)
            is_function = self._is_function_node(node, getattr(ctx.adapter, 'language_id', ''))
            if is_function:
                parent_function = node
                current_depth = 0  # Reset depth for new function scope
            
            # Increase depth for control flow structures
            new_depth = current_depth + 1 if is_control_flow else current_depth
            
            # Update deepest if this is deeper
            if is_control_flow and (deepest is None or new_depth > deepest["depth"]):
                deepest = {
                    "depth": new_depth,
                    "node": node,
                    "function": parent_function
                }
            
            # Recursively visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    walk_node(child, new_depth, parent_function)
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            walk_node(ctx.tree.root_node, 0)
        
        return deepest

    def _is_function_node(self, node, language: str) -> bool:
        """Check if a node represents a function/method definition."""
        function_types = {
            "python": {"function_definition", "method_definition"},
            "javascript": {"function_declaration", "method_definition", "function_expression", "arrow_function"},
            "typescript": {"function_declaration", "method_definition", "function_expression", "arrow_function"},
            "go": {"function_declaration", "method_declaration"},
            "java": {"method_declaration", "constructor_declaration"},
            "csharp": {"method_declaration", "constructor_declaration"},
            "cpp": {"function_definition", "method_definition", "constructor_definition"},
            "c": {"function_definition"},
            "ruby": {"method", "def"},
            "rust": {"function_item", "impl_item"},
            "swift": {"function_declaration", "initializer_declaration"},
        }
        
        return hasattr(node, 'type') and node.type in function_types.get(language, set())

    def _create_finding(self, ctx: RuleContext, deepest_info: dict, max_depth_allowed: int) -> Finding:
        """Create a finding with refactoring suggestion."""
        depth = deepest_info["depth"]
        node = deepest_info["node"]
        
        message = f"Nesting depth {depth} exceeds max {max_depth_allowed}. Prefer guard clauses/early returns."
        
        # Create suggested refactoring comment
        suggestion = self._create_suggestion(ctx, node, depth, max_depth_allowed)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=node.start_byte,
            end_byte=node.end_byte,
            severity="warning",
            autofix=None,  # suggest-only, no autofix
            meta={
                "suggestion": suggestion,
                "depth": depth,
                "max_depth": max_depth_allowed,
                "node_type": node.type
            }
        )
        
        return finding

    def _create_suggestion(self, ctx: RuleContext, node, depth: int, max_allowed: int) -> str:
        """Create a refactoring suggestion comment."""
        # Determine comment style based on language
        adapter_language = getattr(ctx.adapter, 'language_id', '')
        comment_leaders = {
            "python": "#", "ruby": "#",
            "javascript": "//", "typescript": "//",
            "go": "//", "java": "//", "csharp": "//", "cpp": "//", "c": "//",
            "rust": "//", "swift": "//",
        }
        leader = comment_leaders.get(adapter_language, "//")
        
        # Get the specific node type for more targeted suggestions
        node_type = getattr(node, 'type', 'block')
        
        # Create targeted suggestions based on the type of nesting
        suggestions = []
        if 'if' in node_type.lower():
            suggestions.extend([
                "Use guard clauses: invert condition and return/continue early",
                "Extract nested logic into separate functions",
                "Consider using early returns to flatten structure"
            ])
        elif any(loop in node_type.lower() for loop in ['for', 'while', 'loop']):
            suggestions.extend([
                "Extract loop body into a separate function",
                "Use continue statements to skip unnecessary nesting",
                "Consider breaking complex loops into smaller functions"
            ])
        elif 'switch' in node_type.lower() or 'case' in node_type.lower():
            suggestions.extend([
                "Extract case logic into separate functions",
                "Consider using polymorphism instead of switch statements",
                "Break complex cases into helper methods"
            ])
        elif 'try' in node_type.lower() or 'catch' in node_type.lower():
            suggestions.extend([
                "Extract try block logic into separate functions",
                "Use specific exception handling",
                "Consider breaking error handling into layers"
            ])
        else:
            suggestions.extend([
                "Extract nested logic into helper functions",
                "Use guard clauses to reduce nesting",
                "Consider breaking complex logic into smaller functions"
            ])
        
        # Format the suggestion
        suggestion_lines = [
            f"{leader} TODO: Excessive nesting (depth={depth}, limit={max_allowed}). Refactor suggestions:",
        ]
        
        for i, suggestion in enumerate(suggestions[:3], 1):  # Limit to 3 suggestions
            suggestion_lines.append(f"{leader}   {i}. {suggestion}")
        
        return "\n".join(suggestion_lines) + "\n"


# Create rule instance
rule = ComplexityDeepNestingRule()

# Export rule in RULES list for auto-discovery
RULES = [rule]


