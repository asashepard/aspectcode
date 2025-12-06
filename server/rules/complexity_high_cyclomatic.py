# server/rules/complexity_high_cyclomatic.py
"""
Rule to detect functions with high McCabe cyclomatic complexity and suggest refactoring.

This rule analyzes functions for:
- McCabe Cyclomatic Complexity (CC = 1 + decision points)
- Decision points include if/elif, loops, switch/case, try/catch, boolean operators, ternary
- Suggests guard clauses, decomposition, and function extraction when CC exceeds threshold

When thresholds are exceeded, it suggests inserting guidance comments with refactoring strategies.
"""

from typing import List, Set, Optional, Tuple, Iterable
import re
from engine.types import RuleContext, Finding, RuleMeta, Requires

# Default configuration
DEFAULT_MAX_CC = 10

# Function node types by language
FUNC_KINDS = {
    "python": {"function_definition", "method_definition"},
    "javascript": {"function_declaration", "method_definition", "arrow_function", "function_expression"},
    "typescript": {"function_declaration", "method_signature", "method_definition", "arrow_function", "function_expression"},
    "go": {"function_declaration", "method_declaration"},
    "java": {"method_declaration", "constructor_declaration"},
    "csharp": {"method_declaration", "constructor_declaration"},
    "cpp": {"function_definition", "method_definition", "constructor_definition"},
    "c": {"function_definition"},
    "ruby": {"method", "def"},
    "rust": {"function_item", "impl_item"},
    "swift": {"function_declaration", "initializer_declaration"},
}

# Decision node kinds per language (structures that add complexity)
DECISION_KINDS = {
    "python": {
        "if_statement", "elif_clause", "for_statement", "while_statement", 
        "try_statement", "except_clause", "with_statement", 
        "match_statement", "case_clause", "boolean_operator"
    },
    "javascript": {
        "if_statement", "for_statement", "for_in_statement", "for_of_statement", 
        "while_statement", "do_statement", "switch_case", "catch_clause",
        "conditional_expression", "binary_expression"
    },
    "typescript": {
        "if_statement", "for_statement", "for_in_statement", "for_of_statement", 
        "while_statement", "do_statement", "switch_case", "catch_clause",
        "conditional_expression", "binary_expression"
    },
    "go": {
        "if_statement", "for_statement", "switch_statement", "case_clause", 
        "type_switch_statement", "select_statement", "comm_clause"
    },
    "java": {
        "if_statement", "while_statement", "for_statement", "enhanced_for_statement", 
        "switch_label", "catch_clause", "conditional_expression"
    },
    "csharp": {
        "if_statement", "while_statement", "for_statement", "foreach_statement", 
        "switch_section", "catch_clause", "conditional_expression"
    },
    "cpp": {
        "if_statement", "while_statement", "for_statement", "switch_statement", 
        "case_statement", "catch_clause", "conditional_expression"
    },
    "c": {
        "if_statement", "while_statement", "for_statement", "switch_statement", 
        "case_statement", "conditional_expression"
    },
    "ruby": {
        "if", "elsif", "while", "until", "for", "case", "when", 
        "rescue", "binary"
    },
    "rust": {
        "if_expression", "while_expression", "for_expression", "match_arm", 
        "loop_expression", "binary_expression"
    },
    "swift": {
        "if_statement", "while_statement", "for_in_statement", "switch_case", 
        "catch_clause", "guard_statement", "ternary_expression"
    },
}

# Token-based regex for additional complexity indicators within function body
TOK_RE = re.compile(
    rb"(\&\&)|(\|\|)|\?[^:\n?]*:", # && || and ternary operators
    re.MULTILINE
)

class ComplexityHighCyclomaticRule:
    """Rule to detect functions with high cyclomatic complexity."""
    
    meta = RuleMeta(
        id="complexity.high_cyclomatic",
        category="complexity",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Flag functions whose McCabe complexity exceeds a threshold; suggest refactors.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit file and analyze cyclomatic complexity of functions."""
        # Check language support
        adapter_language = getattr(ctx.adapter, 'language_id', '')
        if adapter_language not in self.meta.langs:
            return

        # Get configuration
        config = ctx.config or {}
        max_cc = int(config.get("max_cyclomatic", DEFAULT_MAX_CC))
        
        # Get function and decision node types for this language
        func_kinds = FUNC_KINDS.get(adapter_language, set())
        decision_kinds = DECISION_KINDS.get(adapter_language, set())
        
        if not func_kinds or not decision_kinds:
            return

        # Find all functions and analyze their complexity
        for func_info in self._find_functions_with_complexity(ctx, func_kinds, decision_kinds):
            if func_info["complexity"] > max_cc:
                finding = self._create_finding(ctx, func_info, max_cc)
                if finding:
                    yield finding

    def _find_functions_with_complexity(self, ctx: RuleContext, func_kinds: Set[str], decision_kinds: Set[str]) -> List[dict]:
        """Find all functions and calculate their cyclomatic complexity."""
        functions = []
        
        def walk_node(node, parent_function=None):
            if not hasattr(node, 'type'):
                return
            
            node_type = node.type
            
            # Check if this is a function node
            if node_type in func_kinds:
                func_info = self._analyze_function_complexity(node, decision_kinds, ctx.text)
                if func_info:
                    functions.append(func_info)
                    parent_function = node  # Set as parent for nested functions
            
            # Continue walking children
            if hasattr(node, 'children'):
                for child in node.children:
                    walk_node(child, parent_function)
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            walk_node(ctx.tree.root_node)
        
        return functions

    def _analyze_function_complexity(self, func_node, decision_kinds: Set[str], file_text: str) -> Optional[dict]:
        """Analyze a single function's cyclomatic complexity."""
        # Extract function name
        func_name = self._get_function_name(func_node)
        
        # Find function body boundaries
        body_start, body_end = self._get_function_body_span(func_node)
        
        # Skip functions without bodies (declarations, interfaces)
        if body_start == body_end:
            return None
        
        body_text = file_text[body_start:body_end].encode('utf-8', errors='ignore')
        if not body_text.strip():
            return None
        
        # Calculate complexity: CC = 1 + decision points
        complexity = 1
        
        # Count decision nodes within function body
        complexity += self._count_decision_nodes(func_node, decision_kinds)
        
        # Add token-based complexity (boolean operators, ternary)
        token_complexity = len(TOK_RE.findall(body_text))
        complexity += token_complexity
        
        return {
            "node": func_node,
            "name": func_name,
            "complexity": complexity,
            "body_start": body_start,
            "body_end": body_end,
            "token_complexity": token_complexity
        }

    def _get_function_name(self, func_node) -> str:
        """Extract function name from the function node."""
        # Try different ways to get the function name based on node structure
        if hasattr(func_node, 'name') and func_node.name:
            name_text = getattr(func_node.name, 'text', None)
            if name_text:
                return name_text.decode('utf-8', errors='ignore')
        
        # Try identifier field
        if hasattr(func_node, 'identifier') and func_node.identifier:
            name_text = getattr(func_node.identifier, 'text', None)
            if name_text:
                return name_text.decode('utf-8', errors='ignore')
        
        # Look for name in children
        if hasattr(func_node, 'children'):
            for child in func_node.children:
                if hasattr(child, 'type') and 'identifier' in child.type:
                    name_text = getattr(child, 'text', None)
                    if name_text:
                        return name_text.decode('utf-8', errors='ignore')
        
        return "<function>"

    def _get_function_body_span(self, func_node) -> Tuple[int, int]:
        """Get the byte span of the function body."""
        # Try to find body node first
        if hasattr(func_node, 'body') and func_node.body:
            return func_node.body.start_byte, func_node.body.end_byte
        
        # Look for body in children
        if hasattr(func_node, 'children'):
            for child in func_node.children:
                if hasattr(child, 'type') and any(body_type in child.type.lower() for body_type in ['body', 'block', 'suite']):
                    return child.start_byte, child.end_byte
        
        # Fallback to entire function span
        return func_node.start_byte, func_node.end_byte

    def _count_decision_nodes(self, func_node, decision_kinds: Set[str]) -> int:
        """Count decision points within a function."""
        count = 0
        
        def walk_for_decisions(node):
            nonlocal count
            if not hasattr(node, 'type'):
                return
            
            node_type = node.type
            
            # Count this node if it's a decision point
            if node_type in decision_kinds:
                # Special handling for binary expressions (&&, ||)
                if 'binary' in node_type.lower() or 'boolean' in node_type.lower():
                    count += self._count_binary_operators(node)
                else:
                    count += 1
            
            # Recursively check children
            if hasattr(node, 'children'):
                for child in node.children:
                    walk_for_decisions(child)
        
        walk_for_decisions(func_node)
        return count

    def _count_binary_operators(self, binary_node) -> int:
        """Count logical operators in binary expressions."""
        if not hasattr(binary_node, 'operator'):
            return 1
        
        operator_text = getattr(binary_node.operator, 'text', b'').decode('utf-8', errors='ignore')
        if operator_text in ['&&', '||', 'and', 'or']:
            return 1
        return 0

    def _create_finding(self, ctx: RuleContext, func_info: dict, max_cc: int) -> Finding:
        """Create a finding for high complexity function."""
        complexity = func_info["complexity"]
        func_name = func_info["name"]
        node = func_info["node"]
        
        message = f"'{func_name}' has {complexity} decision points (max {max_cc})—consider splitting into smaller functions."
        
        # Create refactoring suggestion
        suggestion = self._create_refactoring_suggestion(ctx, node, func_name, complexity, max_cc)
        
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
                "complexity": complexity,
                "max_complexity": max_cc,
                "function_name": func_name,
                "token_complexity": func_info.get("token_complexity", 0)
            }
        )
        
        return finding

    def _create_refactoring_suggestion(self, ctx: RuleContext, func_node, func_name: str, complexity: int, max_cc: int) -> str:
        """Create refactoring suggestion comment."""
        # Determine comment style based on language
        adapter_language = getattr(ctx.adapter, 'language_id', '')
        comment_leaders = {
            "python": "#", "ruby": "#",
            "javascript": "//", "typescript": "//",
            "go": "//", "java": "//", "csharp": "//", "cpp": "//", "c": "//",
            "rust": "//", "swift": "//",
        }
        leader = comment_leaders.get(adapter_language, "//")
        
        # Create targeted suggestions based on complexity level
        suggestions = []
        
        if complexity > max_cc * 2:
            # Very high complexity
            suggestions.extend([
                "Break this function into multiple smaller functions with single responsibilities",
                "Consider using the Strategy pattern to replace complex conditional logic",
                "Extract nested blocks into separate helper methods"
            ])
        elif complexity > max_cc * 1.5:
            # Moderately high complexity
            suggestions.extend([
                "Use guard clauses to reduce nesting and early returns to simplify flow",
                "Extract complex switch/case logic into polymorphic methods",
                "Consider decomposing long if-else chains into lookup tables or strategy objects"
            ])
        else:
            # Slightly above threshold
            suggestions.extend([
                "Introduce guard clauses to reduce nesting levels",
                "Extract some conditional logic into helper methods",
                "Consider using early returns to simplify control flow"
            ])
        
        # Format the suggestion
        suggestion_lines = [
            f"{leader} TODO: High cyclomatic complexity (CC={complexity}, limit={max_cc}).",
            f"{leader} Refactoring suggestions for '{func_name}':",
        ]
        
        for i, suggestion in enumerate(suggestions[:3], 1):  # Limit to 3 suggestions
            suggestion_lines.append(f"{leader}   {i}. {suggestion}")
        
        suggestion_lines.append(f"{leader} Lowering CC improves readability, testability, and reduces defect risk.")
        
        return "\n".join(suggestion_lines) + "\n"


# Create rule instance
_rule = ComplexityHighCyclomaticRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register this rule when the module is imported
try:
    from . import register
    register(_rule)
except ImportError:
    from rules import register
    register(_rule)


