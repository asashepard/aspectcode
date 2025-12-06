"""
Style Rule: Trailing Whitespace Detection

Detects trailing whitespace at end of lines.
"""

from typing import Iterator
import re

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class TrailingWhitespaceRule(Rule):
    """Rule to detect trailing whitespace."""
    
    meta = RuleMeta(
        id="style.trailing_whitespace",
        category="style",
        tier=0,
        priority="P3",
        autofix_safety="safe",
        description="Detects trailing whitespace at the end of lines",
        langs=["python", "javascript", "typescript", "java", "csharp", "cpp", "c", "go"]
    )
    
    requires = Requires(raw_text=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit file and detect trailing whitespace."""
        
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
        
        lines = ctx.text.split('\n')
        
        for line_num, line in enumerate(lines):
            if line.rstrip() != line:  # Has trailing whitespace
                start_byte = sum(len(lines[i]) + 1 for i in range(line_num)) + len(line.rstrip())
                end_byte = start_byte + len(line) - len(line.rstrip())
                
                yield Finding(
                    rule=self.meta.id,
                    message="Trailing whitespace detected",
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="info",
                    autofix=[Edit(
                        start_byte=start_byte,
                        end_byte=end_byte,
                        replacement=""
                    )]
                )


rule = TrailingWhitespaceRule()
RULES = [rule]



