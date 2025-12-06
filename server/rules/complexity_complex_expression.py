# server/rules/complexity_complex_expression.py
"""
Rule to detect overly complex expressions and suggest stepwise refactoring.

This rule analyzes expressions for:
- Deeply chained member accesses and function calls
- Dense boolean operator chains (&&, ||, and, or)
- Nested ternary operations (?: in JS/TS, if-else in Python)
- Long arithmetic and bitwise operator chains
- Combined complexity score based on weighted heuristics

When thresholds are exceeded, it suggests inserting guidance comments with stepwise refactor strategies.
"""

from typing import List, Set, Optional, Tuple, Iterable, Dict, Any
import re
from engine.types import RuleContext, Finding, RuleMeta, Requires

# Default configuration thresholds
DEFAULTS = {
    "max_chain": 4,             # maximum allowed member/call chain depth
    "max_bool_ops": 4,          # maximum boolean operator count in one expression  
    "max_ternary_nesting": 1,   # maximum nested ternary depth
    "max_op_chain": 6,          # arithmetic/bitwise operator count
    "max_score": 10,            # fallback: combined heuristic score cap
}

# Language-agnostic node kind hints for expressions
EXPR_KINDS = {
    "member_access": {"member_expression", "field_expression", "attribute", "scoped_identifier", "subscript_expression"},
    "call": {"call_expression", "function_call"},
    "ternary": {"conditional_expression", "ternary_expression", "if_expression"},
    "boolean_op": {"binary_expression", "logical_expression", "boolean_operator"},
    "arithmetic_op": {"binary_expression", "arithmetic_expression"},
    "paren": {"parenthesized_expression"},
}

# Token patterns for different operator types
BOOL_TOKENS = {"&&", "||", "and", "or", "And", "Or"}
ARITH_TOKENS = {"+", "-", "*", "/", "%", "|", "&", "^", "<<", ">>", "**", "//"}

class ComplexityComplexExpressionRule:
    """Rule to detect overly complex expressions and suggest stepwise refactors."""
    
    meta = RuleMeta(
        id="complexity.complex_expression",
        category="complexity",
        tier=0,
        priority="P2", 
        autofix_safety="suggest-only",
        description="Detect overly complex expressions and suggest stepwise refactors.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit a file and check for overly complex expressions."""
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get configuration
        config = getattr(ctx, "config", {}) or {}
        limits = {k: int(config.get(k, v)) for k, v in DEFAULTS.items()}
        
        text_bytes = ctx.text.encode('utf-8', errors='ignore')

        # Find and analyze expressions
        for expr in self._find_expression_nodes(ctx):
            metrics = self._measure_complexity(expr, text_bytes, ctx.adapter.language_id)
            score = self._calculate_score(metrics)
            
            # Check if any threshold is exceeded
            exceeds = (
                metrics["chain"] > limits["max_chain"] or
                metrics["bool_ops"] > limits["max_bool_ops"] or
                metrics["ternary_depth"] > limits["max_ternary_nesting"] or
                metrics["op_chain"] > limits["max_op_chain"] or
                score > limits["max_score"]
            )
            
            if not exceeds:
                continue

            # Create finding with suggestion
            finding = self._create_finding(ctx, expr, metrics, limits, score)
            if finding:
                yield finding

    def _matches_language(self, ctx: RuleContext, supported_langs: List[str]) -> bool:
        """Check if the current language is supported."""
        return ctx.adapter.language_id in supported_langs

    def _find_expression_nodes(self, ctx: RuleContext) -> List:
        """Find expression nodes that could be complex."""
        if not hasattr(ctx.tree, 'root_node'):
            return []
            
        expressions = []
        
        def walk_node(node):
            if not hasattr(node, 'type'):
                return
                
            node_type = node.type
            
            # Look for various expression types that could be complex
            if any(keyword in node_type for keyword in [
                "expression", "call", "member", "binary", "conditional", 
                "ternary", "assignment", "subscript", "attribute"
            ]):
                # Exclude simple expressions that are unlikely to be complex
                if not any(simple in node_type for simple in [
                    "literal", "identifier", "string", "number", "boolean"
                ]):
                    expressions.append(node)
            
            # Continue walking children
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    walk_node(child)
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            walk_node(ctx.tree.root_node)
            
        return expressions

    def _measure_complexity(self, node, text_bytes: bytes, language: str) -> Dict[str, int]:
        """Measure various complexity metrics for an expression."""
        metrics = {
            "chain": 0,
            "bool_ops": 0,
            "ternary_depth": 0,
            "op_chain": 0,
        }
        
        # Use DFS to traverse the expression tree
        stack = [(node, 0)]  # (node, depth)
        max_chain_depth = 0
        current_chain = 0
        max_ternary_depth = 0
        current_ternary_depth = 0
        
        while stack:
            current_node, depth = stack.pop()
            
            if not hasattr(current_node, 'type'):
                continue
                
            node_type = current_node.type
            
            # Get node text for token analysis
            node_text = ""
            if hasattr(current_node, 'start_byte') and hasattr(current_node, 'end_byte'):
                try:
                    node_text = text_bytes[current_node.start_byte:current_node.end_byte].decode('utf-8', errors='ignore')
                except (AttributeError, IndexError):
                    node_text = ""
            
            # Count member access and call chains
            if self._is_chainable_node(node_type):
                current_chain += 1
                max_chain_depth = max(max_chain_depth, current_chain)
            else:
                current_chain = 0
            
            # Count boolean operators
            if self._is_boolean_node(node_type, node_text):
                metrics["bool_ops"] += self._count_boolean_operators(node_text)
            
            # Count ternary expressions
            if self._is_ternary_node(node_type, node_text, language):
                current_ternary_depth += 1
                max_ternary_depth = max(max_ternary_depth, current_ternary_depth)
            
            # Count arithmetic operators
            if self._is_arithmetic_node(node_type, node_text):
                metrics["op_chain"] += self._count_arithmetic_operators(node_text)
            
            # Add children to stack
            if hasattr(current_node, 'children') and current_node.children:
                for child in current_node.children:
                    stack.append((child, depth + 1))
        
        metrics["chain"] = max_chain_depth
        metrics["ternary_depth"] = max_ternary_depth
        
        return metrics

    def _is_chainable_node(self, node_type: str) -> bool:
        """Check if a node represents a chainable operation (member access or call)."""
        chainable_types = {
            "member_expression", "field_expression", "attribute", "scoped_identifier",
            "call_expression", "function_call", "subscript_expression"
        }
        return any(chainable in node_type for chainable in chainable_types)

    def _is_boolean_node(self, node_type: str, node_text: str) -> bool:
        """Check if a node represents a boolean operation."""
        boolean_types = {"binary_expression", "logical_expression", "boolean_operator"}
        return (any(bool_type in node_type for bool_type in boolean_types) and 
                any(token in node_text for token in BOOL_TOKENS))

    def _is_ternary_node(self, node_type: str, node_text: str, language: str) -> bool:
        """Check if a node represents a ternary operation."""
        ternary_types = {"conditional_expression", "ternary_expression", "if_expression"}
        
        # Direct node type check
        if any(ternary in node_type for ternary in ternary_types):
            return True
            
        # Text-based detection for ternary operators
        if language in ["javascript", "typescript", "java", "c", "cpp", "csharp"]:
            return "?" in node_text and ":" in node_text
        elif language == "python":
            return " if " in node_text and " else " in node_text
            
        return False

    def _is_arithmetic_node(self, node_type: str, node_text: str) -> bool:
        """Check if a node represents an arithmetic operation."""
        arithmetic_types = {"binary_expression", "arithmetic_expression"}
        return (any(arith_type in node_type for arith_type in arithmetic_types) and 
                any(token in node_text for token in ARITH_TOKENS))

    def _count_boolean_operators(self, text: str) -> int:
        """Count boolean operators in text."""
        count = 0
        for token in BOOL_TOKENS:
            count += text.count(token)
        return count

    def _count_arithmetic_operators(self, text: str) -> int:
        """Count arithmetic operators in text."""
        count = 0
        for token in ARITH_TOKENS:
            count += text.count(token)
        return count

    def _calculate_score(self, metrics: Dict[str, int]) -> int:
        """Calculate a weighted complexity score from metrics."""
        # Weighted heuristic scoring - tuned for conservatism
        score = (
            metrics["chain"] * 2 +           # Chain depth is heavily weighted
            metrics["bool_ops"] * 1 +        # Boolean operators add linearly
            metrics["ternary_depth"] * 3 +   # Nested ternaries are heavily weighted
            metrics["op_chain"] * 1          # Arithmetic operators add linearly
        )
        return score

    def _create_finding(self, ctx: RuleContext, expr_node, metrics: Dict[str, int], 
                       limits: Dict[str, int], score: int) -> Optional[Finding]:
        """Create a finding for a complex expression."""
        message = (
            f"Complex expression: chain={metrics['chain']}, bool_ops={metrics['bool_ops']}, "
            f"ternary_depth={metrics['ternary_depth']}, ops={metrics['op_chain']} (score={score}). "
            "Consider stepwise refactor."
        )
        
        # Create refactoring suggestion
        suggestion = self._create_refactoring_suggestion(ctx, expr_node, metrics, limits)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=getattr(expr_node, 'start_byte', 0),
            end_byte=getattr(expr_node, 'end_byte', 0),
            severity="info",
            autofix=None,  # suggest-only, no autofix
            meta={
                "suggestion": suggestion,
                "metrics": metrics,
                "limits": limits,
                "score": score
            }
        )
        
        return finding

    def _create_refactoring_suggestion(self, ctx: RuleContext, expr_node, 
                                     metrics: Dict[str, int], limits: Dict[str, int]) -> str:
        """Create a refactoring suggestion for the complex expression."""
        language = ctx.adapter.language_id
        leader = self._get_comment_leader(language)
        
        # Concrete refactoring steps
        suggestions = [
            "introduce well-named intermediate variables for sub-expressions",
            "split long boolean chains into guard clauses or early returns", 
            "replace nested ternaries with if/else or strategy helpers",
            "extract a helper function for a meaningful sub-part",
        ]
        
        # Format as comment block
        bullets = "\n".join(f"{leader}   - {suggestion}" for suggestion in suggestions[:3])
        
        exceeded_limits = []
        if metrics["chain"] > limits["max_chain"]:
            exceeded_limits.append(f"chain={metrics['chain']}>{limits['max_chain']}")
        if metrics["bool_ops"] > limits["max_bool_ops"]:
            exceeded_limits.append(f"bool_ops={metrics['bool_ops']}>{limits['max_bool_ops']}")
        if metrics["ternary_depth"] > limits["max_ternary_nesting"]:
            exceeded_limits.append(f"ternary_depth={metrics['ternary_depth']}>{limits['max_ternary_nesting']}")
        if metrics["op_chain"] > limits["max_op_chain"]:
            exceeded_limits.append(f"ops={metrics['op_chain']}>{limits['max_op_chain']}")
        
        exceeded_text = " or ".join(exceeded_limits) if exceeded_limits else "score threshold exceeded"
        
        header = (
            f"{leader} Complex expression detected ({exceeded_text}).\n"
            f"{leader} Consider stepwise refactor:\n"
            f"{bullets}\n"
            f"{leader}\n"
        )
        
        return (
            f"Breaking complex expressions into named steps improves readability, debuggability, and testability. "
            f"Consider inserting this guidance comment above the expression:\n\n"
            f"{header}"
        )

    def _get_comment_leader(self, language: str) -> str:
        """Get the appropriate comment leader for the language."""
        comment_leaders = {
            "python": "#",
            "ruby": "#", 
            "javascript": "//",
            "typescript": "//",
            "go": "//",
            "java": "//",
            "csharp": "//", 
            "cpp": "//",
            "c": "//",
            "rust": "//",
            "swift": "//",
        }
        return comment_leaders.get(language, "//")

    def _suggest_comment_above(self, text_bytes: bytes, expr_node, metrics: Dict[str, int], 
                             limits: Dict[str, int], language: str) -> Tuple[str, str]:
        """Create a suggested diff for inserting a comment above the expression."""
        leader = self._get_comment_leader(language)
        
        # Find the start of the line containing the expression
        try:
            line_start = text_bytes.rfind(b"\n", 0, expr_node.start_byte) + 1
            before_line = text_bytes[line_start:expr_node.start_byte].decode("utf-8", "ignore")
        except (AttributeError, IndexError):
            before_line = ""
            
        # Create refactoring tips
        bullets = [
            "introduce well-named intermediate variables for sub-expressions", 
            "split long boolean chains into guard clauses / early returns",
            "replace nested ternaries with if/else or strategy helpers",
            "extract a helper function for a meaningful sub-part",
        ]
        tips = "\n".join(f"{leader}   - {x}" for x in bullets[:3])

        exceeded_limits = []
        if metrics["chain"] > limits["max_chain"]:
            exceeded_limits.append(f"chain={metrics['chain']}>{limits['max_chain']}")
        if metrics["bool_ops"] > limits["max_bool_ops"]:
            exceeded_limits.append(f"bool_ops={metrics['bool_ops']}>{limits['max_bool_ops']}")
        if metrics["ternary_depth"] > limits["max_ternary_nesting"]:
            exceeded_limits.append(f"ternary_depth={metrics['ternary_depth']}>{limits['max_ternary_nesting']}")
        if metrics["op_chain"] > limits["max_op_chain"]:
            exceeded_limits.append(f"ops={metrics['op_chain']}>{limits['max_op_chain']}")
            
        exceeded_text = " or ".join(exceeded_limits) if exceeded_limits else "score threshold exceeded"

        comment = (
            f"{leader} Complex expression detected ({exceeded_text}).\n"
            f"{leader} Consider stepwise refactor:\n{tips}\n"
        )

        diff = (
            "--- a/expr\n"
            "+++ b/expr\n"
            f"-{before_line}\n"
            f"+{comment}{before_line}"
        )
        rationale = "Breaking complex expressions into named steps improves readability, debuggability, and testability."
        return diff, rationale


# Register the rule
try:
    from . import register
    register(ComplexityComplexExpressionRule())
except ImportError:
    # Handle direct execution or testing
    pass


