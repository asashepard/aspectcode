import sys; sys.path.insert(0, '.')
from engine.validation import ValidationService

vs = ValidationService()
vs.ensure_adapters_loaded()
vs.ensure_rules_loaded()

# Load the rule
from engine.registry import get_rule
rule = get_rule('bug.incompatible_comparison')

# Load the fixture
with open('tests/fixtures/alpha_rule_triggers/python/bug_incompatible_comparison.py', 'r') as f:
    text = f.read()

# Get adapter and parse  
from engine.python_adapter import default_python_adapter
adapter = default_python_adapter
tree = adapter.parse(text)

# Create context
from engine.types import RuleContext
from engine.tree_sitter_compat import make_compatible_context

ctx = RuleContext(
    file_path='test.py',
    text=text,
    tree=tree,
    adapter=adapter,
    config={}
)
ctx = make_compatible_context(ctx)

# Manually test the visit flow
print('=== Testing visit flow ===')
print(f'ctx.syntax_tree: {ctx.syntax_tree}')

# Count nodes walked
print('\nWalking nodes with ctx.walk_nodes():')
comparison_nodes_found = 0
for node in ctx.walk_nodes(ctx.syntax_tree):
    node_type = getattr(node, 'type', None)
    if node_type == 'comparison_operator':
        comparison_nodes_found += 1
        print(f'  Found comparison_operator: {getattr(node, "text", b"").decode() if isinstance(getattr(node, "text", b""), bytes) else getattr(node, "text", "")}')
        
        # Manually call _check_comparison_node
        findings = list(rule._check_comparison_node(ctx, node))
        print(f'  _check_comparison_node returned {len(findings)} findings')
        for f in findings:
            print(f'    {f}')

print(f'\nTotal comparison_operator nodes found: {comparison_nodes_found}')

# Test the full visit
print('\n=== Full rule.visit() ===')
findings = list(rule.visit(ctx))
print(f'Total findings: {len(findings)}')


