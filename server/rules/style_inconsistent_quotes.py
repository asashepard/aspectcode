"""
Rule to detect and fix inconsistent quote styles for string literals.

This rule identifies string literals that don't match the configured quote style
(single or double quotes) and provides safe autofix for simple literals.
"""

from typing import Iterator, List, Optional, Dict, Any
import re

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority


DEFAULT_STYLE = "single"  # Default to single quotes


class StyleInconsistentQuotesRule(Rule):
    """Rule to normalize string literals to a consistent quote style."""
    
    meta = RuleMeta(
        id="style.inconsistent_quotes",
        category="style",
        tier=0,
        priority="P2",
        autofix_safety="safe",
        description="Normalize string literals to a consistent quote style (single or double).",
        langs=["python", "javascript", "typescript", "ruby"]
    )
    
    requires = Requires(raw_text=True, syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect inconsistent quote styles."""
        # Check if this language is supported
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        # Get configured quote style, default to single
        config = ctx.config or {}
        style = config.get("quote_style", DEFAULT_STYLE)
        
        if style not in ["single", "double"]:
            # Invalid configuration, default to single
            style = DEFAULT_STYLE
        
        target_quote = "'" if style == "single" else '"'
        opposite_quote = '"' if target_quote == "'" else "'"
        
        # Find string nodes in the syntax tree
        def find_string_nodes(node):
            """Recursively find string nodes."""
            if node.type == "string":
                yield node
            
            for child in node.children:
                yield from find_string_nodes(child)
        
        if not ctx.tree or not hasattr(ctx.tree, 'root_node'):
            return
        
        # Find all string nodes and check their quote style
        for string_node in find_string_nodes(ctx.tree.root_node):
            # Get the text of the string node
            try:
                text = string_node.text.decode('utf-8')
            except (UnicodeDecodeError, AttributeError):
                # Skip tokens that can't be decoded
                continue
            
            if not text or len(text) < 2:
                continue
            
            # Check if this is a simple quoted literal
            current_quote = text[0]
            if current_quote not in ("'", '"'):
                continue  # Not a simple quoted literal
            
            if current_quote == target_quote:
                continue  # Already using the correct style
            
            # Check if conversion is safe
            if not self._is_convertible(text, target_quote, opposite_quote):
                continue
            
            # Generate the replacement
            replacement = self._convert_literal(text, target_quote, opposite_quote)
            if replacement is None or replacement == text:
                continue
            
            # Create the finding with autofix
            yield Finding(
                rule=self.meta.id,
                message=f"Use {style} quotes for string literals.",
                file=ctx.file_path,
                start_byte=string_node.start_byte,
                end_byte=string_node.end_byte,
                severity="info",
                autofix=[Edit(
                    start_byte=string_node.start_byte,
                    end_byte=string_node.end_byte,
                    replacement=replacement
                )],
                meta={
                    "quote_style": style,
                    "original_quote": current_quote,
                    "target_quote": target_quote,
                    "original_text": text,
                    "replacement_text": replacement
                }
            )
    
    def _get_tokens_from_tree(self, ctx: RuleContext) -> List[Dict[str, Any]]:
        """Extract tokens from the syntax tree."""
        tokens = []
        
        def traverse_node(node):
            # If this node has children, traverse them
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    traverse_node(child)
            else:
                # This is a leaf node (token)
                tokens.append({
                    'text': node.text,
                    'type': node.type,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'start_point': getattr(node, 'start_point', (0, 0)),
                    'end_point': getattr(node, 'end_point', (0, 0))
                })
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            traverse_node(ctx.tree.root_node)
        
        return tokens
    
    def _is_string_token(self, language: str, token: Dict[str, Any]) -> bool:
        """Check if the token represents a string literal."""
        token_type = token['type'].lower()
        
        if language in ("javascript", "typescript"):
            return token_type in ("string", "string_literal", "string_token", "template_string", "template_literal")
        elif language == "python":
            return token_type in ("string", "string_literal")
        elif language == "ruby":
            return token_type in ("string", "string_literal", "tstring_content", "string_literal_token")
        
        return False
    
    def _is_simple_string(self, language: str, token: Dict[str, Any]) -> bool:
        """Check if this is a simple string that can be safely converted."""
        text_bytes = token['text']
        
        # Disallow template literals/backticks (JS/TS)
        if language in ("javascript", "typescript") and text_bytes.startswith(b"`"):
            return False
        
        # Disallow Python triple quotes and prefixes r/f/b/u variants
        if language == "python":
            lower_text = text_bytes.lower()
            
            # Check for string prefixes (r, u, b, f, and combinations)
            if lower_text.startswith((b"r", b"u", b"b", b"f")):
                return False
            
            # Check for triple quotes
            if lower_text.startswith(b"'''") or lower_text.startswith(b'"""'):
                return False
        
        # Disallow Ruby %q/%Q/%() and heredocs
        if language == "ruby":
            if text_bytes.startswith((b"%q", b"%Q", b"<<")):
                return False
        
        return True
    
    def _is_convertible(self, text: str, target_quote: str, opposite_quote: str) -> bool:
        """
        Check if the string literal can be safely converted.
        
        Convert only if:
        - Literal is delimited by ' or "
        - Contains no newline characters (different escaping across languages)
        - Contains no complex escape sequences that could change semantics
        - Does not contain the target quote character unescaped
        """
        if len(text) < 2:
            return False
        
        if text[0] not in ("'", '"') or text[-1] != text[0]:
            return False
        
        inner = text[1:-1]
        
        # Avoid converting if it contains newline characters
        if "\n" in inner or "\r" in inner:
            return False
            
        # Check if inner content contains the target quote type unescaped
        if target_quote in inner:
            # Check if target quote is properly escaped
            # This is a simplified check - look for unescaped target quotes
            i = 0
            while i < len(inner):
                if inner[i] == target_quote:
                    # Check if it's escaped (preceded by odd number of backslashes)
                    backslash_count = 0
                    j = i - 1
                    while j >= 0 and inner[j] == '\\':
                        backslash_count += 1
                        j -= 1
                    
                    # If even number of backslashes (or zero), quote is not escaped
                    if backslash_count % 2 == 0:
                        return False  # Contains unescaped target quote
                i += 1
        
        # Check for complex escape sequences that might change semantics
        # Allow only escaping of quotes and backslashes
        unsafe_escape_pattern = r'\\(?!["\'\\])'
        if re.search(unsafe_escape_pattern, inner):
            return False
        
        return True
    
    def _convert_literal(self, text: str, target_quote: str, opposite_quote: str) -> Optional[str]:
        """
        Convert string literal to use the target quote style.
        
        Args:
            text: Original string literal including quotes
            target_quote: The quote character to convert to (' or ")
            opposite_quote: The other quote character (" or ')
            
        Returns:
            Converted string literal or None if conversion fails
        """
        if text[0] not in ("'", '"') or text[-1] != text[0]:
            return None
        
        inner = text[1:-1]
        
        # Use a placeholder for literal backslashes to avoid interference
        placeholder = "\x00"  # Null character as placeholder
        
        # Step 1: Protect literal backslashes
        inner = inner.replace("\\\\", placeholder)
        
        # Step 2: Handle quote escaping based on target
        if target_quote == "'":
            # Converting to single quotes
            # Unescape any escaped single quotes from the original
            inner = inner.replace("\\'", "'")
            # Escape any unescaped single quotes
            inner = inner.replace("'", "\\'")
        else:
            # Converting to double quotes
            # Unescape any escaped double quotes from the original
            inner = inner.replace('\\"', '"')
            # Escape any unescaped double quotes
            inner = inner.replace('"', '\\"')
        
        # Step 3: Restore literal backslashes
        inner = inner.replace(placeholder, "\\\\")
        
        return f"{target_quote}{inner}{target_quote}"


# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(StyleInconsistentQuotesRule())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


