"""
Aspect Code Rules Package

This package contains all the rules that analyze code for issues.
Rules are automatically discovered and registered when this package is imported.

To add a new rule:
1. Create a Python file in this directory (e.g., my_rule.py)
2. Define your rule class implementing the Rule protocol
3. Create a RULES list containing your rule instance, or call register(rule)
4. The rule will be auto-discovered when --discover server.rules is used

Example rule structure:

```python
from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding

class MyRule:
    meta = RuleMeta(
        id="my.rule",
        category="style", 
        tier=0,
        priority="P2",
        autofix_safety="safe",
        description="Detects my specific issue",
        langs=["python"]
    )
    
    requires = Requires(syntax=True)
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        # Your rule logic here
        yield Finding(
            rule=self.meta.id,
            message="Found an issue",
            file=ctx.file_path,
            start_byte=0,
            end_byte=10,
            severity="warning"
        )

# Register the rule
RULES = [MyRule()]
```
"""

from typing import List
try:
    from ..engine.types import Rule
    from ..engine.registry import register_rule
except ImportError:
    # Handle direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule
    from engine.registry import register_rule

# Global list of all rules in this package
# Note: This is populated by the auto-discovery mechanism in engine.registry
# Rules are discovered automatically when engine.runner.discover_rules() is called
RULES: List[Rule] = []


def register(rule: Rule) -> None:
    """
    Register a rule in the global registry.
    
    Args:
        rule: Rule instance to register
    """
    register_rule(rule)
    RULES.append(rule)


def get_rules_from_registry():
    """
    Get all rules from the global registry and update local RULES list.
    This is used to sync with the auto-discovery mechanism.
    """
    try:
        from ..engine.registry import get_all_rules
    except ImportError:
        # Handle direct execution
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from engine.registry import get_all_rules
    
    global RULES
    RULES = get_all_rules()
    return RULES


# Export public interface
__all__ = ["RULES", "register", "get_rules_from_registry"]



