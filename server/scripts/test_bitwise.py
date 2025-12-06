import sys; sys.path.insert(0, '.')
from engine.validation import ValidationService
vs = ValidationService()
vs.ensure_rules_loaded()
from engine.registry import get_rule
rule = get_rule('bug.boolean_bitwise_misuse')

# Now let's use the enhanced context
from engine.types import RuleContext
from engine.tree_sitter_compat import make_compatible_context

class FakeAdapter:
    language_id = 'python'

text = '''# Should trigger: bug.boolean_bitwise_misuse
def check_conditions(a, b, c, d):
    if (a == 1) & (b > 0):  # using bitwise & instead of logical and
        return True
    if (c < 10) | (d == 5):  # using bitwise | instead of logical or
        return True
    return False
'''

# Create a context using dataclass
base_ctx = RuleContext(
    file_path='test.py',
    text=text,
    tree=None,
    adapter=FakeAdapter(),
    config={}
)

# Enhance it
ctx = make_compatible_context(base_ctx)

print(f'ctx.language = {ctx.language}')
print(f'ctx.adapter.language_id = {ctx.adapter.language_id}')
print(f'ctx.text[:50] = {repr(ctx.text[:50])}')
print(f'ctx.raw_text[:50] = {repr(ctx.raw_text[:50])}')

findings = list(rule.visit(ctx))
print(f'Found {len(findings)} findings:')
for f in findings:
    print(f'  {f}')
