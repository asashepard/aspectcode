import sys; sys.path.insert(0, '.')
from engine.validation import ValidationService
vs = ValidationService()
vs.ensure_adapters_loaded()
vs.ensure_rules_loaded()

from engine.registry import get_rule
rule = get_rule('errors.broad_catch')

# Load the fixture
with open('tests/fixtures/alpha_rule_triggers/python/errors_broad_catch.py', 'r') as f:
    text = f.read()

# Get adapter and parse  
from engine.python_adapter import default_python_adapter
adapter = default_python_adapter
tree = adapter.parse(text)

# Find and test except_clause
for node in rule._walk_nodes(tree):
    if hasattr(node, 'type') and node.type == 'except_clause':
        print(f'Found except_clause:')
        print(f'  node: {node}')
        print(f'  children count: {len(node.children) if hasattr(node, "children") else "N/A"}')
        
        # Show children
        if hasattr(node, 'children'):
            for i, child in enumerate(node.children):
                child_type = getattr(child, 'type', 'unknown')
                child_text = ''
                if hasattr(child, 'text'):
                    child_text = child.text
                    if isinstance(child_text, bytes):
                        child_text = child_text.decode('utf-8', errors='ignore')
                print(f'  child[{i}]: type={child_type}, text={repr(child_text[:50] if len(child_text) > 50 else child_text)}')
        
        # Test _py_is_broad directly
        is_broad = rule._py_is_broad(node, text)
        print(f'  _py_is_broad: {is_broad}')
        
        # Test _is_broad_catch 
        is_broad2 = rule._is_broad_catch(node, 'python', text)
        print(f'  _is_broad_catch: {is_broad2}')




