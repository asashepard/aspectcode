# server/rules/complexity_long_function.py
"""
Rule to detect overly long or complex functions and suggest refactoring.

This rule analyzes functions for:
- Lines of Code (LOC) - excluding empty lines, comments, and braces
- Cyclomatic Complexity (CC) - 1 + decision points (if, for, while, etc.)

When thresholds are exceeded, it suggests inserting a TODO comment with refactoring guidance.
"""

from typing import List, Tuple, Set, Iterator
import re

try:
    from ..engine.types import Rule, RuleContext, Finding, RuleMeta, Requires
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleContext, Finding, RuleMeta, Requires

# Default configuration
DEFAULTS = {
    "max_loc": 50,
    "max_cyclomatic": 10,
}

# Decision point regex (bytes) used within a function body slice; conservative and language-agnostic
DECISION_RE = re.compile(
    rb"\b(if|elif|else\s+if|for|while|case|catch|when|guard|match)\b"
    rb"|(\&\&)|(\|\|)|\?|(?:\breturn\s+if\b)",  # includes ternary ?:
    re.IGNORECASE
)

# Function node types by language
FUNC_KINDS = {
    "python": {"function_definition", "method_definition"},
    "javascript": {"function_declaration", "method_definition", "function_expression"},
    "typescript": {"function_declaration", "method_signature", "method_definition", "function_expression"},
    "go": {"function_declaration", "method_declaration"},
    "java": {"method_declaration", "constructor_declaration"},
    "csharp": {"method_declaration", "constructor_declaration"},
    "cpp": {"function_definition", "method_definition", "constructor_definition"},
    "c": {"function_definition"},
    "ruby": {"method", "def"},
    "rust": {"function_item", "impl_item"},
    "swift": {"function_declaration", "initializer_declaration"},
}

class ComplexityLongFunctionRule(Rule):
    """Rule to detect overly long or complex functions."""
    
    meta = RuleMeta(
        id="complexity.long_function",
        category="complexity", 
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects overly long or complex functions and suggests refactoring",
        langs=["python", "javascript", "typescript", "java", "csharp", "cpp", "c"]
    )
    
    requires = Requires(syntax=True)
    
    meta = RuleMeta(
        id="complexity.long_function",
        category="complexity",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Flag functions exceeding LOC or cyclomatic complexity thresholds; suggest extraction/refactor.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Visit file and analyze function complexity."""
        findings = []
        
        # Check language support
        adapter_language = getattr(ctx.adapter, 'language_id', '')
        if adapter_language not in self.meta.langs:
            return findings

        # Get configuration
        config = ctx.config or {}
        max_loc = int(config.get("max_loc", DEFAULTS["max_loc"]))
        max_cyc = int(config.get("max_cyclomatic", DEFAULTS["max_cyclomatic"]))
        
        # Get function node types for this language
        kinds = FUNC_KINDS.get(adapter_language, set())
        if not kinds:
            return findings

        # Get file content as bytes
        file_bytes = ctx.text.encode('utf-8')

        # Find and analyze functions
        def visit_node(node):
            if hasattr(node, 'type') and node.type in kinds:
                finding = self._analyze_function(ctx, node, file_bytes, max_loc, max_cyc)
                if finding:
                    findings.append(finding)
            
            # Recursively visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    visit_node(child)
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            visit_node(ctx.tree.root_node)

        return findings

    def _analyze_function(self, ctx: RuleContext, fn_node, file_bytes: bytes, max_loc: int, max_cyc: int) -> Finding:
        """Analyze a single function for complexity."""
        # Get function body span
        body_start, body_end = self._get_body_span(fn_node)
        body_bytes = file_bytes[body_start:body_end]
        
        # Skip functions without meaningful bodies
        if not body_bytes.strip():
            return None

        # Calculate metrics
        loc = self._count_loc(body_bytes)
        cyclomatic = self._calculate_cyclomatic_complexity(body_bytes)

        # Check if thresholds are exceeded
        if loc <= max_loc and cyclomatic <= max_cyc:
            return None

        # Get function name
        name = self._get_function_name(fn_node)
        
        # Create finding with suggestion
        message = f"'{name}' is {loc} lines with {cyclomatic} decision points—consider breaking into smaller functions."
        
        # Create suggested diff
        suggestion = self._create_suggestion(ctx, fn_node, file_bytes, name, loc, cyclomatic, max_loc, max_cyc)
        
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=fn_node.start_byte,
            end_byte=fn_node.end_byte,
            severity="warning",  # Add severity here
            autofix=None,  # suggest-only, no autofix
            meta={
                "suggestion": suggestion,
                "loc": loc,
                "cyclomatic_complexity": cyclomatic,
                "max_loc": max_loc,
                "max_cyclomatic": max_cyc
            }
        )
        
        return finding

    def _get_body_span(self, fn_node) -> Tuple[int, int]:
        """Get the byte span of the function body."""
        # Try to find a body node
        if hasattr(fn_node, 'children'):
            for child in fn_node.children:
                if hasattr(child, 'type') and child.type in ['block', 'compound_statement', 'statement_block', 'body']:
                    return child.start_byte, child.end_byte
        
        # Fallback: use entire function span
        return fn_node.start_byte, fn_node.end_byte

    def _count_loc(self, body_bytes: bytes) -> int:
        """Count logical lines of code, excluding empty lines, comments, and braces."""
        try:
            text = body_bytes.decode("utf-8", "ignore")
        except:
            return 0
            
        lines = text.splitlines()
        non_empty = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in ("{", "}", "{}", "};"):
                continue
            # More comprehensive comment detection
            if stripped.startswith(("//", "#")):
                continue
            # Block comment detection - check for comment start/continuation/end
            if (stripped.startswith(("/*", "*")) or 
                stripped.endswith("*/") or 
                stripped in ("*", "*/")):
                continue
            # Skip lines that are just closing braces or semicolons
            if stripped in ("}", ";"):
                continue
            non_empty += 1
            
        return non_empty

    def _calculate_cyclomatic_complexity(self, body_bytes: bytes) -> int:
        """Calculate cyclomatic complexity (1 + decision points)."""
        decisions = len(DECISION_RE.findall(body_bytes))
        return 1 + decisions

    def _get_function_name(self, fn_node) -> str:
        """Extract function name from the AST node."""
        # Try common attribute names for function identifiers
        for attr in ['name', 'identifier', 'function_name']:
            if hasattr(fn_node, attr):
                name_node = getattr(fn_node, attr)
                if hasattr(name_node, 'text'):
                    return name_node.text.decode('utf-8', 'ignore')
        
        # Try to find identifier in children - look deeper for C/C++ style
        if hasattr(fn_node, 'children'):
            for child in fn_node.children:
                # For C/C++, check function_declarator -> identifier
                if hasattr(child, 'type') and child.type == 'function_declarator':
                    if hasattr(child, 'children'):
                        for grandchild in child.children:
                            if hasattr(grandchild, 'type') and grandchild.type == 'identifier':
                                if hasattr(grandchild, 'text'):
                                    return grandchild.text.decode('utf-8', 'ignore')
                
                # Direct identifier check
                if hasattr(child, 'type') and child.type == 'identifier':
                    if hasattr(child, 'text'):
                        return child.text.decode('utf-8', 'ignore')
        
        return "<function>"

    def _create_suggestion(self, ctx: RuleContext, fn_node, file_bytes: bytes, name: str, 
                          loc: int, cyclomatic: int, max_loc: int, max_cyc: int) -> str:
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
        
        # Generate extraction suggestions based on function size
        body_start, body_end = self._get_body_span(fn_node)
        body_text = file_bytes[body_start:body_end].decode("utf-8", "ignore")
        
        # Estimate number of helper functions needed
        approx_helpers = max(1, min(5, body_text.count("\n") // 10))
        if loc > max_loc:
            approx_helpers = max(approx_helpers, (loc // max_loc) + 1)
        
        bullets = "\n".join([f"{leader}   - Extract helper method {i+1} for specific logic" for i in range(approx_helpers)])
        
        suggestion = (
            f"{leader} TODO: '{name}' exceeds complexity limits (LOC={loc}>{max_loc} or CC={cyclomatic}>{max_cyc}).\n"
            f"{leader} Refactor plan:\n"
            f"{bullets}\n"
            f"{leader} Consider: reduce nesting depth, split conditional logic, extract constants\n"
        )
        
        return suggestion


# Create rule instance
_rule = ComplexityLongFunctionRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register the rule
try:
    from ..engine.registry import register_rule
    register_rule(_rule)
except ImportError:
    # Handle local testing
    pass


