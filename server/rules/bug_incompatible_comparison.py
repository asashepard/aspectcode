"""
Rule: bug.incompatible_comparison

Detects semantically wrong or incompatible comparisons across multiple languages:
- Java/C# string/object compared with == instead of .equals/.Equals
- C/C++ pointer vs string literal with == (address compare instead of content)
- JavaScript/TypeScript loose equality between different types
- Cross-type comparisons (number ↔ string/boolean)
- Ordering between non-numeric types

Priority: P1 (high impact correctness issues)
Autofix: suggest-only
"""

from typing import Iterable, Optional, Any, FrozenSet
from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugIncompatibleComparisonRule:
    meta = RuleMeta(
        id="bug.incompatible_comparison",
        category="bug",
        tier=0,  # Tier 0 - syntax only
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects semantically wrong comparisons like Java string == or C pointer vs string literal",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)
    
    # Comparison operators to check
    EQ_OPS: FrozenSet[str] = frozenset({"==", "!=", "===", "!=="})
    ORDER_OPS: FrozenSet[str] = frozenset({"<", ">", "<=", ">="})
    ALL_COMPARISON_OPS: FrozenSet[str] = EQ_OPS | ORDER_OPS
    
    # Node types that can contain comparisons - limits tree walking
    COMPARISON_NODE_TYPES: FrozenSet[str] = frozenset({
        "comparison_expression", "binary_expression", "relational_expression",
        "equality_expression", "comparison", "binary_operator",
        # Tree-sitter specific types
        "comparison_operator", "boolean_operator"
    })
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit syntax tree and detect incompatible comparisons."""
        if not ctx.syntax_tree:
            return
            
        yield from self._analyze_syntax_tree(ctx, ctx.syntax_tree)
    
    def _analyze_syntax_tree(self, ctx: RuleContext, root) -> Iterable[Finding]:
        """Walk the syntax tree looking for comparison operations - OPTIMIZED."""
        # Only process relevant node types for efficiency
        for node in ctx.walk_nodes(root):
            node_type = getattr(node, 'type', None) or getattr(node, 'kind', None)
            
            # Quick filter: skip non-comparison nodes entirely
            if node_type and node_type not in self.COMPARISON_NODE_TYPES:
                # Still check if it has comparison children (for binary expressions)
                if not self._might_contain_comparison(node):
                    continue
            
            yield from self._check_comparison_node(ctx, node)
    
    def _might_contain_comparison(self, node) -> bool:
        """Quick check if node might contain a comparison operator."""
        # Check children for operator tokens
        if not hasattr(node, 'children'):
            return False
        
        for child in node.children:
            child_type = getattr(child, 'type', None)
            if child_type in self.ALL_COMPARISON_OPS:
                return True
            # Check child text
            if hasattr(child, 'text'):
                text = child.text
                if isinstance(text, bytes):
                    text = text.decode('utf-8', errors='ignore')
                if text in self.ALL_COMPARISON_OPS:
                    return True
        return False
    
    def _check_comparison_node(self, ctx: RuleContext, node) -> Iterable[Finding]:
        """Check if a node represents a problematic comparison."""
        # Get operator from node
        operator = self._get_operator(node)
        if not operator or operator not in self.ALL_COMPARISON_OPS:
            return
        
        # Get left and right operands
        left = self._get_left_operand(node)
        right = self._get_right_operand(node)
        if not left or not right:
            return
        
        # Quick text extraction (cached per node)
        left_text = self._get_node_text_fast(left)
        right_text = self._get_node_text_fast(right)
        
        # Check various incompatible comparison patterns
        finding = None
        
        if self._is_java_csharp_object_equality_issue(ctx.language, operator, left_text, right_text):
            finding = self._create_finding(
                ctx, node, operator,
                "Object/string compared with '=='. Use value equality (e.g., .equals / string.Equals).",
                "java_csharp_object_equality"
            )
        elif self._is_c_pointer_vs_string_literal(ctx.language, operator, left_text, right_text):
            finding = self._create_finding(
                ctx, node, operator,
                "Pointer compared to string literal with '=='. Compare contents (e.g., strcmp/strncmp).",
                "c_pointer_string_literal"
            )
        elif self._is_js_ts_loose_cross_type_equality(ctx.language, operator, left_text, right_text):
            finding = self._create_finding(
                ctx, node, operator,
                "Possible cross-type comparison. Prefer strict/typed equality (===/!==) or convert types.",
                "js_ts_loose_equality"
            )
        elif self._is_obviously_mismatched_literal_types(ctx.language, operator, left_text, right_text):
            finding = self._create_finding(
                ctx, node, operator,
                "Comparison between unrelated literal types (e.g., number vs string/boolean).",
                "mismatched_literal_types"
            )
        elif self._is_suspicious_ordering_between_non_numeric(ctx.language, operator, left_text, right_text):
            finding = self._create_finding(
                ctx, node, operator,
                "Ordering comparison between non-numeric or mismatched types; verify intent.",
                "suspicious_ordering"
            )
        
        if finding:
            yield finding
    
    def _create_finding(self, ctx: RuleContext, node, operator: str, message: str, pattern: str) -> Finding:
        """Create a finding for an incompatible comparison."""
        # Try to get operator token span, fallback to node span
        start_byte, end_byte = self._get_operator_span(ctx, node, operator)
        
        return Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning",  # P1 priority uses warn severity
            meta={
                "pattern": pattern,
                "operator": operator
            }
        )
    
    def _get_operator_span(self, ctx: RuleContext, node, operator: str):
        """Get the byte span for the comparison operator."""
        # Fallback to node span
        if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            start = node.start_byte
            end = node.end_byte
            if isinstance(start, int) and isinstance(end, int):
                return start, end
        
        # Final fallback to safe integers
        return 0, 10  # Reasonable default span
    
    def _get_operator(self, node) -> Optional[str]:
        """Extract the comparison operator from a node."""
        # Check children for operator token (most reliable for tree-sitter)
        if hasattr(node, 'children'):
            for child in node.children:
                if hasattr(child, 'type') and child.type in self.ALL_COMPARISON_OPS:
                    return child.type
                if hasattr(child, 'text'):
                    text = child.text
                    if isinstance(text, bytes):
                        text = text.decode('utf-8', errors='ignore')
                    if text in self.ALL_COMPARISON_OPS:
                        return text
        
        return None
    
    def _get_left_operand(self, node):
        """Get the left operand of a comparison."""
        if hasattr(node, 'children') and len(node.children) >= 2:
            return node.children[0]
        return None
    
    def _get_right_operand(self, node):
        """Get the right operand of a comparison."""
        if hasattr(node, 'children') and len(node.children) >= 2:
            return node.children[-1]  # Last child is usually right operand
        return None
    
    # === Optimized text extraction ===
    
    def _get_node_text_fast(self, node) -> str:
        """Get the text content of a node - optimized."""
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return text
        return ""
    
    # === Optimized type detection ===
    
    def _is_string_literal_text(self, text: str) -> bool:
        """Check if text represents a string literal."""
        text = text.strip()
        if len(text) >= 2:
            first, last = text[0], text[-1]
            if (first in '"\'`' and last == first) or text.startswith('"""') or text.startswith("'''"):
                return True
        return False
    
    def _is_numeric_literal_text(self, text: str) -> bool:
        """Check if text represents a numeric literal."""
        text = text.strip().lower().replace('_', '')
        if not text:
            return False
        
        # Quick check for simple integers
        if text.isdigit():
            return True
        
        # Check for floats/hex/binary
        if text.startswith(('0x', '0b', '0o')):
            return True
        
        # Remove suffixes and check
        for suffix in ['f', 'l', 'd', 'ul', 'ull', 'u']:
            if text.endswith(suffix):
                text = text[:-len(suffix)]
                break
        
        try:
            float(text)
            return True
        except ValueError:
            return False
    
    def _is_boolean_literal_text(self, text: str) -> bool:
        """Check if text represents a boolean literal."""
        return text.strip().lower() in ('true', 'false')
    
    def _is_null_literal_text(self, text: str) -> bool:
        """Check if text represents a null/undefined literal."""
        return text.strip().lower() in ('null', 'undefined', 'nil', 'none')
    
    # === Incompatible comparison detection methods - now using text ===
    
    def _is_java_csharp_object_equality_issue(self, language: str, operator: str, left_text: str, right_text: str) -> bool:
        """Detect Java/C# object equality using == instead of .equals/.Equals."""
        if language not in ('java', 'csharp') or operator not in ('==', '!='):
            return False
        
        # If either side is a string literal, == is likely wrong
        if self._is_string_literal_text(left_text) or self._is_string_literal_text(right_text):
            return True
        
        # Look for 'new' keyword indicating object construction
        if 'new ' in left_text or 'new ' in right_text:
            return True
        
        return False
    
    def _is_c_pointer_vs_string_literal(self, language: str, operator: str, left_text: str, right_text: str) -> bool:
        """Detect C/C++ pointer vs string literal comparison."""
        if language not in ('c', 'cpp') or operator not in ('==', '!='):
            return False
        
        left_is_string = self._is_string_literal_text(left_text)
        right_is_string = self._is_string_literal_text(right_text)
        
        # One side is string literal, other is likely a pointer
        if left_is_string ^ right_is_string:
            other_text = right_text if left_is_string else left_text
            # Heuristic: if the other side isn't a string literal
            if other_text.strip() and not self._is_string_literal_text(other_text):
                return True
        
        return False
    
    def _is_js_ts_loose_cross_type_equality(self, language: str, operator: str, left_text: str, right_text: str) -> bool:
        """Detect JavaScript/TypeScript loose equality between different types."""
        if language not in ('javascript', 'typescript') or operator != '==':
            return False
        
        # Check for different literal types being compared
        left_num = self._is_numeric_literal_text(left_text)
        right_num = self._is_numeric_literal_text(right_text)
        left_str = self._is_string_literal_text(left_text)
        right_str = self._is_string_literal_text(right_text)
        left_bool = self._is_boolean_literal_text(left_text)
        right_bool = self._is_boolean_literal_text(right_text)
        left_null = self._is_null_literal_text(left_text)
        right_null = self._is_null_literal_text(right_text)
        
        # Cross-type comparisons
        if (left_num and (right_str or right_bool)) or (right_num and (left_str or left_bool)):
            return True
        if (left_str and right_bool) or (right_str and left_bool):
            return True
        if left_null or right_null:
            return True
        
        return False
    
    def _is_obviously_mismatched_literal_types(self, language: str, operator: str, left_text: str, right_text: str) -> bool:
        """Detect comparisons between obviously mismatched literal types."""
        left_num = self._is_numeric_literal_text(left_text)
        right_num = self._is_numeric_literal_text(right_text)
        left_str = self._is_string_literal_text(left_text)
        right_str = self._is_string_literal_text(right_text)
        left_bool = self._is_boolean_literal_text(left_text)
        right_bool = self._is_boolean_literal_text(right_text)
        
        # Number vs string/boolean
        if (left_num and (right_str or right_bool)) or (right_num and (left_str or left_bool)):
            return True
        
        # String vs boolean
        if (left_str and right_bool) or (right_str and left_bool):
            return True
        
        return False
    
    def _is_suspicious_ordering_between_non_numeric(self, language: str, operator: str, left_text: str, right_text: str) -> bool:
        """Detect suspicious ordering comparisons between non-numeric types."""
        if operator not in self.ORDER_OPS:
            return False
        
        left_num = self._is_numeric_literal_text(left_text)
        right_num = self._is_numeric_literal_text(right_text)
        left_str = self._is_string_literal_text(left_text)
        right_str = self._is_string_literal_text(right_text)
        left_bool = self._is_boolean_literal_text(left_text)
        right_bool = self._is_boolean_literal_text(right_text)
        
        # Boolean ordering is usually suspicious
        if left_bool or right_bool:
            return True
        
        # String vs non-string ordering
        if (left_str and not right_str) or (right_str and not left_str):
            return True
        
        # Python-specific: different types in ordering
        if language == "python":
            if (left_str != right_str) or (left_bool != right_bool) or (left_num != right_num):
                return True
        
        return False


# Register the rule
_rule = BugIncompatibleComparisonRule()
RULES = [_rule]