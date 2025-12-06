"""Rule to detect use of non-cryptographic random number generators for sensitive operations.

Detects usage of weak (non-cryptographic) random number generators that should not 
be used for security-sensitive operations like generating tokens, passwords, or secrets:

- Python: random module functions (random.random, random.randint, etc.)
- JavaScript: Math.random
- Java: java.util.Random, java.util.concurrent.ThreadLocalRandom
- C#: System.Random
- Ruby: Random class, Kernel.rand
- Go: math/rand package

Recommends using cryptographically secure alternatives like secrets module (Python),
crypto.getRandomValues (JavaScript), SecureRandom (Java/Ruby), RandomNumberGenerator (C#),
or crypto/rand (Go).
"""

import re
from typing import Iterator, Set

from engine.types import RuleContext, Finding, RuleMeta, Requires, Rule


class SecInsecureRandomRule:
    """Detect use of non-cryptographic random number generators for sensitive operations."""
    
    meta = RuleMeta(
        id="sec.insecure_random",
        category="sec",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects use of non-cryptographic RNG for sensitive operations",
        langs=["python", "javascript", "java", "csharp", "ruby", "go"]
    )
    
    requires = Requires(syntax=True)
    
    # Insecure RNG patterns by language
    INSECURE_TARGETS = {
        "python": {
            "random.random", "random.randint", "random.randrange", "random.choice", 
            "random.getrandbits", "random.uniform", "random.sample", "random.shuffle",
            "random.SystemRandom"  # Often misused; recommend secrets instead
        },
        "javascript": {
            "Math.random"
        },
        "java": {
            "java.util.Random", "java.util.concurrent.ThreadLocalRandom",
            "Random", "ThreadLocalRandom"  # Short names after import
        },
        "csharp": {
            "System.Random", "Random"  # Short name after using
        },
        "ruby": {
            "Random.rand", "Random.new", "Kernel.rand", "rand"
        },
        "go": {
            "math/rand", "rand"  # Package and short references
        }
    }
    
    # Insecure type patterns (for method calls on insecure types)
    INSECURE_TYPES = {
        "java": {"Random", "ThreadLocalRandom", "java.util.Random", "java.util.concurrent.ThreadLocalRandom"},
        "csharp": {"Random", "System.Random"},
        "ruby": {"Random"},
        "go": {"rand"}  # For calls like rand.Int(), rand.Intn()
    }
    
    # Cryptographic alternatives by language
    REPLACEMENTS = {
        "python": "Use `secrets` module (e.g., `secrets.token_urlsafe()`, `secrets.randbelow()`, `secrets.choice()`).",
        "javascript": "Use Web Crypto API: `crypto.getRandomValues(new Uint8Array(n))`.",
        "java": "Use `java.security.SecureRandom` for cryptographic operations.",
        "csharp": "Use `System.Security.Cryptography.RandomNumberGenerator` (e.g., `RandomNumberGenerator.GetBytes()`).",
        "ruby": "Use `SecureRandom` (e.g., `SecureRandom.hex`, `SecureRandom.random_bytes`).",
        "go": "Use `crypto/rand` package (e.g., `rand.Read` from `crypto/rand`)."
    }
    
    # Patterns for detecting sensitive contexts
    SENSITIVE_CONTEXT = re.compile(
        r"\b(password|passwd|pwd|token|secret|auth|session|apikey|api_key|credential|"
        r"login|signin|nonce|salt|key|cryptographic|crypto|security|secure|random)\b", 
        re.IGNORECASE
    )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for insecure random number generator usage."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Get language from adapter
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        for node in ctx.tree.walk():
            node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
            
            # Check for function/method calls and constructor calls
            if node_kind in ["call_expression", "method_call", "call", "invocation_expression", "new_expression", "object_creation_expression"]:
                if self._is_insecure_rng_call(node, ctx, language):
                    # Only flag if in a security-sensitive context
                    if not self._is_sensitive_context(node, ctx):
                        continue
                        
                    start_byte, end_byte = self._get_node_span(node)
                    callee_text = self._get_callee_text(node, ctx)
                    replacement = self.REPLACEMENTS.get(language, "Use a cryptographically secure random generator.")
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=f"'{callee_text}' is not cryptographically secure—use {replacement.rstrip('.')} for security-sensitive values.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="warning"
                    )
            
            # Check for member expressions (like Math.random)
            elif node_kind in ["member_expression", "field_expression", "attribute"]:
                if self._is_insecure_rng_member(node, ctx, language):
                    # Only flag if in a security-sensitive context  
                    if not self._is_sensitive_context(node, ctx):
                        continue
                        
                    start_byte, end_byte = self._get_node_span(node)
                    member_text = self._get_node_text(node, ctx)
                    replacement = self.REPLACEMENTS.get(language, "Use a cryptographically secure random generator.")
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=f"'{member_text}' is not cryptographically secure—use {replacement.rstrip('.')} for security-sensitive values.",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="warning"
                    )
    
    def _is_insecure_rng_call(self, node, ctx: RuleContext, language: str) -> bool:
        """Check if this is a call to an insecure RNG function."""
        callee_text = self._get_callee_text(node, ctx)
        if not callee_text:
            return False
        
        insecure_apis = self.INSECURE_TARGETS.get(language, set())
        insecure_types = self.INSECURE_TYPES.get(language, set())
        
        # Check for secure alternatives first to avoid false positives
        secure_patterns = {
            "python": ["secrets.", "SecureRandom", "cryptographically_strong"],
            "javascript": ["crypto.getRandomValues", "window.crypto.getRandomValues"],
            "java": ["SecureRandom", "java.security.SecureRandom"],
            "csharp": ["RandomNumberGenerator", "RNGCryptoServiceProvider"],
            "ruby": ["SecureRandom"],
            "go": ["crypto/rand", "cryptorand"]
        }
        
        secure_alts = secure_patterns.get(language, [])
        for secure_alt in secure_alts:
            if secure_alt in callee_text.lower() or secure_alt in callee_text:
                return False
        
        # Direct API match
        for api in insecure_apis:
            if callee_text == api:
                return True
            # Handle dotted names like random.random, Math.random
            if "." in api and callee_text.endswith(api):
                return True
            # Handle short names after import
            api_short = api.split(".")[-1]
            if callee_text == api_short:
                return True
        
        # Check for method calls on insecure types (e.g., random.nextInt())
        for insecure_type in insecure_types:
            if callee_text.startswith(f"{insecure_type.lower()}.") or callee_text.startswith(f"{insecure_type}."):
                return True
            # Handle constructor calls like "new Random" or type identifiers
            if callee_text.endswith(insecure_type) and "Secure" not in callee_text:
                return True
        
        return False
    
    def _is_insecure_rng_member(self, node, ctx: RuleContext, language: str) -> bool:
        """Check if this is a member expression accessing insecure RNG."""
        member_text = self._get_node_text(node, ctx)
        if not member_text:
            return False
        
        insecure_apis = self.INSECURE_TARGETS.get(language, set())
        
        # Check for secure alternatives first
        secure_patterns = {
            "python": ["secrets.", "SecureRandom"],
            "javascript": ["crypto.getRandomValues", "window.crypto.getRandomValues"],
            "java": ["SecureRandom"],
            "csharp": ["RandomNumberGenerator", "RNGCryptoServiceProvider"],
            "ruby": ["SecureRandom"],
            "go": ["crypto/rand", "cryptorand"]
        }
        
        secure_alts = secure_patterns.get(language, [])
        for secure_alt in secure_alts:
            if secure_alt in member_text.lower() or secure_alt in member_text:
                return False
        
        # Check for exact matches or patterns like Math.random
        for api in insecure_apis:
            if member_text == api or member_text.endswith(api):
                return True
        
        return False
    
    # Non-sensitive context patterns - don't flag random in these contexts
    NON_SENSITIVE_PATTERNS = re.compile(
        r"\b(display|color|animation|ui|shuffle|sample|position|offset|delay|"
        r"jitter|noise|mock|example|placeholder|width|height|size|"
        r"duration|timeout|interval|opacity|z-?index|font|render|draw|"
        r"game|play|dice|roll|select|pick|choose|random_element|"
        r"uuid|guid|uniqueid|component|element|item)\b", 
        re.IGNORECASE
    )
    
    def _is_sensitive_context(self, node, ctx: RuleContext) -> bool:
        """Check if the random generation is in a security-sensitive context.
        
        Returns True if context suggests security-sensitive use (tokens, passwords, secrets).
        Returns False if context clearly suggests non-security use (UI, animation, games).
        Defaults to True (flag) if context is ambiguous - security-conscious default.
        """
        # Get the broader context around this node
        context_text = self._get_context_text(node, ctx)
        
        # Check variable assignment context first
        parent = self._get_parent_assignment(node)
        parent_text = self._get_node_text(parent, ctx) if parent else ""
        
        # Check function/method context
        func_context = self._get_enclosing_function_context(node)
        func_text = self._get_node_text(func_context, ctx) if func_context else ""
        
        # Combine all context
        all_context = f"{context_text} {parent_text} {func_text}"
        
        # If any context is clearly non-sensitive, don't flag
        if self.NON_SENSITIVE_PATTERNS.search(all_context):
            # But if there's ALSO security-sensitive context, still flag
            if self.SENSITIVE_CONTEXT.search(all_context):
                return True
            return False
        
        # If explicitly security-sensitive, flag
        if self.SENSITIVE_CONTEXT.search(all_context):
            return True
        
        # Default: flag to be safe (security-conscious default)
        # Insecure random is generally discouraged even if context is ambiguous
        return True
    
    def _get_context_text(self, node, ctx: RuleContext) -> str:
        """Get text from the node and its surrounding context."""
        node_text = self._get_node_text(node, ctx)
        
        # Walk up to get parent context (up to 3 levels)
        current = node
        for _ in range(3):
            if hasattr(current, 'parent') and current.parent:
                current = current.parent
                parent_text = self._get_node_text(current, ctx)
                if len(parent_text) > len(node_text):
                    node_text = parent_text
                    if len(node_text) > 500:  # Enough context
                        break
        
        return node_text
    
    # Legacy method - kept for compatibility
    def _looks_sensitive_context(self, node, ctx: RuleContext) -> bool:
        """Deprecated - use _is_sensitive_context instead."""
        return self._is_sensitive_context(node, ctx)
    
    # Helper methods
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the text of the function/method being called."""
        # Find the callee node
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "member_expression", "field_expression", "attribute", "dotted_name"]:
                return self._get_node_text(child, ctx)
        
        # For constructor calls, look for the type being constructed
        if hasattr(node, 'children'):
            for child in node.children:
                child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
                if child_kind in ["type_identifier", "generic_name", "qualified_name"]:
                    return self._get_node_text(child, ctx)
        
        return ""
    
    def _get_parent_assignment(self, node):
        """Find parent assignment expression if it exists."""
        parent = getattr(node, 'parent', None)
        while parent:
            parent_kind = getattr(parent, 'kind', '') or getattr(parent, 'type', '')
            if parent_kind in ["assignment_expression", "variable_declaration", "local_variable_declaration"]:
                return parent
            parent = getattr(parent, 'parent', None)
        return None
    
    def _get_enclosing_function_context(self, node):
        """Find enclosing function/method for context."""
        parent = getattr(node, 'parent', None)
        while parent:
            parent_kind = getattr(parent, 'kind', '') or getattr(parent, 'type', '')
            if parent_kind in ["function_declaration", "method_declaration", "function_definition", "method_definition"]:
                return parent
            parent = getattr(parent, 'parent', None)
        return None
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
        """Extract text from a node."""
        if not node:
            return ""
            
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Fallback: use span to extract from source
        start_byte, end_byte = self._get_node_span(node)
        if hasattr(ctx, 'text') and ctx.text:
            try:
                return ctx.text[start_byte:end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""
    
    def _get_node_span(self, node) -> tuple:
        """Get the start and end byte positions of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        # If no span info, try to estimate
        if start_byte == end_byte == 0:
            # Use a default span
            end_byte = start_byte + 10
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [SecInsecureRandomRule()]


