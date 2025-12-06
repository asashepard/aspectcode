"""
Sample test rule for smoke testing the rule system.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    # Fallback for direct execution
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class SampleTestRule:
    """A simple test rule that looks for TODO comments in Python files."""
    
    meta = RuleMeta(
        id="test.todo_comment",
        category="code-quality",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Finds TODO comments in code",
        langs=["python"]
    )
    
    requires = Requires(
        raw_text=True,
        syntax=False
    )
    
    def visit(self, ctx: RuleContext) -> list[Finding]:
        """Find TODO comments in the file."""
        findings = []
        
        # Simple string search for TODO comments
        lines = ctx.text.split('\n')
        
        for line_num, line in enumerate(lines, 1):
            if 'TODO' in line:
                # Calculate byte offset (simplified)
                byte_offset = sum(len(l) + 1 for l in lines[:line_num-1])
                todo_start = line.find('TODO')
                
                finding = Finding(
                    rule=self.meta.id,
                    message=f"TODO comment found: {line.strip()}",
                    severity="info",
                    file=ctx.file_path,
                    start_byte=byte_offset + todo_start,
                    end_byte=byte_offset + len(line)
                )
                findings.append(finding)
        
        return findings


# Register this rule when the module is imported
_rule = SampleTestRule()
RULES = [_rule]

def register_rules():
    """Register this rule with the rule system."""
    try:
        from ..engine.registry import register_rule
    except ImportError:
        from engine.registry import register_rule
    
    register_rule(_rule)  # Use global function


# Auto-register when imported
register_rules()


