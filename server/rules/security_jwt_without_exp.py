"""
Security Rule: JWT Without Expiration Detection

Detects JWT tokens created without expiration time.
"""

from typing import Iterator
import re

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class JwtWithoutExpRule(Rule):
    """Rule to detect JWT tokens without expiration."""
    
    meta = RuleMeta(
        id="security.jwt_without_exp",
        category="security",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects JWT tokens created without expiration time",
        langs=["python", "javascript", "typescript", "java", "csharp"]
    )
    
    requires = Requires(raw_text=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and detect JWT without expiration."""
        
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
        
        # Patterns for JWT creation without exp claim - vary by language
        patterns = {
            "python": [
                re.compile(r'jwt\.encode\([^)]*\)', re.IGNORECASE),
                re.compile(r'PyJWT\.encode\([^)]*\)', re.IGNORECASE),
            ],
            "javascript": [
                re.compile(r'jwt\.sign\([^)]*\)', re.IGNORECASE),
                re.compile(r'jsonwebtoken\.sign\([^)]*\)', re.IGNORECASE),
            ],
            "typescript": [
                re.compile(r'jwt\.sign\([^)]*\)', re.IGNORECASE),
                re.compile(r'jsonwebtoken\.sign\([^)]*\)', re.IGNORECASE),
            ],
            "java": [
                re.compile(r'Jwts\.builder\(\).*?\.compact\(\)', re.DOTALL),
                re.compile(r'JWT\.create\(\).*?\.sign\([^)]*\)', re.DOTALL),
            ],
            "csharp": [
                re.compile(r'JwtSecurityToken\([^)]*\)', re.IGNORECASE),
                re.compile(r'new\s+JwtSecurityToken\([^)]*\)', re.IGNORECASE),
                re.compile(r'WriteToken\([^)]*\)', re.IGNORECASE),
            ],
        }
        
        lang_patterns = patterns.get(language, [])
        
        # For Java, we need to look at the whole file since JWT builder calls are multiline
        if language == "java":
            text = ctx.text
            for pattern in lang_patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group()
                    # Check if 'exp' or 'setExpiration' is in the JWT creation
                    if 'exp' not in matched_text.lower() and 'expiration' not in matched_text.lower():
                        start_byte = match.start()
                        end_byte = match.end()
                        
                        yield Finding(
                            rule=self.meta.id,
                            message="JWT created without expiration—tokens should expire to limit damage if stolen.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )
            return
        
        # For C#, check the whole file - need to look at SecurityTokenDescriptor context
        if language == "csharp":
            text = ctx.text
            
            # For C#, we need to check if SecurityTokenDescriptor has Expires set
            # The pattern is: new SecurityTokenDescriptor { ..., Expires = ..., ... }
            # followed by: CreateToken(...) and WriteToken(...)
            
            # Look for SecurityTokenDescriptor with Expires
            has_descriptor_with_expires = 'SecurityTokenDescriptor' in text and 'Expires' in text
            
            # Look for JwtSecurityToken constructor with expires parameter
            has_jwt_with_expires = ('JwtSecurityToken(' in text and 'expires' in text.lower())
            
            # If either pattern shows expiration is set, skip all WriteToken matches
            if has_descriptor_with_expires or has_jwt_with_expires:
                return
            
            # Otherwise, flag JWT creation patterns
            for pattern in lang_patterns:
                for match in pattern.finditer(text):
                    matched_text = match.group()
                    # Check if 'exp' or 'Expires' is in the immediate JWT creation
                    if 'exp' not in matched_text.lower() and 'expires' not in matched_text.lower():
                        start_byte = match.start()
                        end_byte = match.end()
                        
                        yield Finding(
                            rule=self.meta.id,
                            message="JWT created without expiration—tokens should expire to limit damage if stolen.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )
            return
        
        # For other languages, process line by line
        lines = ctx.text.split('\n')
        
        for line_num, line in enumerate(lines):
            for pattern in lang_patterns:
                for match in pattern.finditer(line):
                    # Check if 'exp' is not in the JWT payload
                    if 'exp' not in match.group() and 'expir' not in match.group().lower():
                        start_byte = sum(len(lines[i]) + 1 for i in range(line_num)) + match.start()
                        end_byte = start_byte + len(match.group())
                        
                        yield Finding(
                            rule=self.meta.id,
                            message="JWT created without expiration—tokens should expire to limit damage if stolen.",
                            file=ctx.file_path,
                            start_byte=start_byte,
                            end_byte=end_byte,
                            severity="warning"
                        )


rule = JwtWithoutExpRule()
RULES = [rule]



