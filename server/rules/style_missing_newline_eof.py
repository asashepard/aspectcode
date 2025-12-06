"""
Style Rule: Missing Newline at EOF Detection

Detects files that don't end with a newline.
"""

from typing import Iterator

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class MissingNewlineEofRule(Rule):
    """Rule to detect missing newline at end of file."""
    
    meta = RuleMeta(
        id="style.missing_newline_eof",
        category="style",
        tier=0,
        priority="P3",
        autofix_safety="safe",
        description="Detects files that don't end with a newline",
        langs=["python", "javascript", "typescript", "java", "csharp", "cpp", "c", "go"]
    )
    
    requires = Requires(raw_text=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and check for newline at EOF."""
        
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
        
        if ctx.text and not ctx.text.endswith('\n'):
            start_byte = len(ctx.text)
            end_byte = start_byte
            
            yield Finding(
                rule=self.meta.id,
                message="File should end with a newline",
                file=ctx.file_path,
                start_byte=start_byte,
                end_byte=end_byte,
                severity="info",
                autofix=[Edit(
                    start_byte=start_byte,
                    end_byte=end_byte,
                    replacement="\n"
                )]
            )


rule = MissingNewlineEofRule()
RULES = [rule]



