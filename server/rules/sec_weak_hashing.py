"""Rule to detect weak hashing algorithms (MD5/SHA-1) used for sensitive data.

Detects cryptographically weak hashing algorithms MD5 and SHA-1 when used 
for sensitive data like passwords, tokens, or secrets across multiple languages:

- Python: hashlib.md5, hashlib.sha1
- JavaScript: crypto.createHash, crypto.subtle.digest with weak algorithms
- Ruby: Digest::MD5, Digest::SHA1
- Java: MessageDigest.getInstance with MD5/SHA-1
- C#: MD5.Create, SHA1.Create
- Go: crypto/md5, crypto/sha1

Recommends using strong password hashers (Argon2/bcrypt/scrypt/PBKDF2) for passwords
or HMAC-SHA-256/512 with random keys for tokens and signatures.
"""

import re
from typing import Iterator

from engine.types import RuleContext, Finding, RuleMeta, Requires, Rule


class SecWeakHashingRule(Rule):
    """Detect weak hashing algorithms for sensitive data."""
    
    meta = RuleMeta(
        id="sec.weak_hashing",
        category="sec",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects weak hashing algorithms (MD5/SHA-1) used for sensitive data",
        langs=["python", "java", "csharp", "javascript", "ruby", "go"]
    )
    
    requires = Requires(syntax=True)
    
    # Weak hash API patterns by language
    WEAK_HASH_APIS = {
        "python": {
            "hashlib.md5", "hashlib.sha1", "md5", "sha1"
        },
        "javascript": {
            "crypto.createHash", "crypto.subtle.digest", 
            "window.crypto.subtle.digest", "createHash"
        },
        "ruby": {
            "Digest::MD5.new", "Digest::MD5.hexdigest", "Digest::MD5.digest",
            "Digest::SHA1.new", "Digest::SHA1.hexdigest", "Digest::SHA1.digest",
            "MD5.new", "MD5.hexdigest", "SHA1.new", "SHA1.hexdigest"
        },
        "java": {
            "MessageDigest.getInstance", "java.security.MessageDigest.getInstance"
        },
        "csharp": {
            "MD5.Create", "SHA1.Create", "System.Security.Cryptography.MD5.Create",
            "System.Security.Cryptography.SHA1.Create", "MD5CryptoServiceProvider",
            "SHA1CryptoServiceProvider"
        },
        "go": {
            "md5.New", "sha1.New", "md5.Sum", "sha1.Sum",
            "crypto/md5.New", "crypto/sha1.New", "crypto/md5.Sum", "crypto/sha1.Sum"
        }
    }
    
    # Regular expressions for algorithm detection
    ALG_MD5 = re.compile(r"\b(md5|MD5)\b")
    ALG_SHA1 = re.compile(r"\b(sha-?1|SHA-?1)\b")
    
    # Patterns for sensitive data context
    SENSITIVE_HINT = re.compile(
        r"\b(pass(word|wd)?|token|secret|auth|session|apikey|api_key|credential|login|signin|pwd)\b", 
        re.IGNORECASE
    )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for weak hashing algorithms used with sensitive data."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Get language from adapter
        if hasattr(ctx.adapter, 'language_id'):
            language = ctx.adapter.language_id
        elif hasattr(ctx.adapter, 'get_language'):
            language = ctx.adapter.get_language()
        else:
            language = 'unknown'
        if language not in self.meta.langs:
            return
        
        for node in ctx.tree.walk():
            node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
            
            # Check for function/method calls
            if node_kind in ["call_expression", "method_call", "call", "invocation_expression"]:
                if self._is_weak_hash_call(node, ctx, language):
                    if self._looks_sensitive_context(node, ctx):
                        start_byte, end_byte = self._get_node_span(node)
                        yield Finding(
                            rule=self.meta.id,
                            message="Weak hashing (MD5/SHA-1) used for sensitive data. Use Argon2/bcrypt/scrypt/PBKDF2 for passwords, or HMAC-SHA-256/512 with a random key for tokens.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )
    
    def _is_weak_hash_call(self, node, ctx: RuleContext, language: str) -> bool:
        """Check if this is a call to a weak hashing API."""
        callee_text = self._get_callee_text(node, ctx)
        if not callee_text:
            return False
        
        weak_apis = self.WEAK_HASH_APIS.get(language, set())
        
        # Direct API match
        for api in weak_apis:
            if callee_text.endswith(api) or callee_text == api:
                # For generic APIs like MessageDigest.getInstance, check algorithm parameter
                if api in ["MessageDigest.getInstance", "java.security.MessageDigest.getInstance"]:
                    return self._has_weak_algorithm_param(node, ctx)
                elif api in ["crypto.createHash", "crypto.subtle.digest", "window.crypto.subtle.digest", "createHash"]:
                    return self._has_weak_algorithm_param(node, ctx)
                else:
                    # Direct weak hash APIs (hashlib.md5, Digest::MD5, etc.)
                    return True
        
        return False
    
    def _has_weak_algorithm_param(self, node, ctx: RuleContext) -> bool:
        """Check if the call has MD5 or SHA-1 as algorithm parameter."""
        node_text = self._get_node_text(node, ctx)
        
        # Check for weak algorithms in the call text
        if self.ALG_MD5.search(node_text) or self.ALG_SHA1.search(node_text):
            return True
        
        # Check arguments for algorithm strings
        args = self._get_call_arguments(node)
        for arg in args:
            arg_text = self._get_node_text(arg, ctx).strip().strip('"\'')
            if arg_text.lower() in ['md5', 'sha1', 'sha-1']:
                return True
        
        return False
    
    def _looks_sensitive_context(self, node, ctx: RuleContext) -> bool:
        """Check if the hashing is happening in a sensitive context."""
        # Check the immediate call context
        node_text = self._get_node_text(node, ctx)
        if self.SENSITIVE_HINT.search(node_text):
            return True
        
        # Check variable assignment context
        parent = self._get_parent_assignment(node)
        if parent:
            parent_text = self._get_node_text(parent, ctx)
            if self.SENSITIVE_HINT.search(parent_text):
                return True
        
        # Check function/method parameter names
        func_context = self._get_enclosing_function_context(node)
        if func_context:
            func_text = self._get_node_text(func_context, ctx)
            if self.SENSITIVE_HINT.search(func_text):
                return True
        
        # Conservative: treat weak hashing as problematic by default
        # This catches cases where sensitive data isn't obvious from variable names
        return True
    
    # Helper methods
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the text of the function/method being called."""
        # Find the callee node
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["identifier", "member_expression", "field_expression", "attribute", "dotted_name"]:
                return self._get_node_text(child, ctx)
        
        return ""
    
    def _get_call_arguments(self, node) -> list:
        """Extract arguments from a call expression."""
        args = []
        
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["arguments", "argument_list", "parameter_list"]:
                # Get individual argument nodes
                for arg_child in getattr(child, 'children', []):
                    arg_kind = getattr(arg_child, 'kind', '') or getattr(arg_child, 'type', '')
                    if arg_kind not in [',', '(', ')', 'comma']:
                        args.append(arg_child)
                break
        
        return args
    
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
RULES = [SecWeakHashingRule()]


