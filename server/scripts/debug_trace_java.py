#!/usr/bin/env python3
"""Debug script to trace sec.path_traversal on Java file."""

import sys
import os

# Add server to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from engine.registry import register_adapter, get_adapter, register_rule, get_rule
from engine.validation import ValidationService

# Test file
fixture_path = os.path.join(server_dir, "tests", "fixtures", "alpha_rule_triggers", "java", "sec_path_traversal.java")

# Read fixture
with open(fixture_path, "r") as f:
    content = f.read()

# Setup
vs = ValidationService()
vs.ensure_adapters_loaded()
vs.ensure_rules_loaded()

# Get adapter and parse
java_adapter = get_adapter("java")
tree = java_adapter.parse(content)

# Get the rule
rule = get_rule("sec.path_traversal")
print(f"Rule: {rule}")
print(f"Rule meta.langs: {rule.meta.langs}")

# Create context manually - use the REAL RuleContext
from engine.types import RuleContext

ctx = RuleContext(
    file_path=fixture_path,
    text=content,
    tree=tree,
    adapter=java_adapter,
    config={},
    scopes=None,
    project_graph=None
)

# Apply compatibility layer
from engine.tree_sitter_compat import make_compatible_context
enhanced_ctx = make_compatible_context(ctx)

# Walk the tree to see node types
print("\n=== TREE NODE TYPES ===")
def walk_tree(node, depth=0):
    node_type = getattr(node, 'type', 'unknown')
    text_preview = ""
    if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
        text_preview = content[node.start_byte:node.end_byte][:30].replace('\n', '\\n')
    print(f"{'  ' * depth}{node_type}: {text_preview}")
    for child in (node.children if hasattr(node, 'children') else []):
        walk_tree(child, depth + 1)

walk_tree(tree.root_node)

# Try running the rule
print("\n=== RULE EXECUTION ===")
print(f"enhanced tree type: {type(enhanced_ctx.tree)}")
print(f"enhanced tree.walk: {enhanced_ctx.tree.walk}")

# Check what walk returns
walker = enhanced_ctx.tree.walk()
print(f"walker type: {type(walker)}")

# Try iterating
node_count = 0
for node in enhanced_ctx.tree.walk():
    node_count += 1
    if node_count > 3:
        print(f"  ... (more nodes)")
        break
    print(f"  Node: type={type(node)}, kind={getattr(node, 'type', getattr(node, 'kind', 'unknown'))}")

# Manually trace rule logic
print("\n=== MANUAL TRACE ===")
language = 'java'
print(f"Language: {language}")
print(f"Sinks for {language}: {rule.SINK_TAILS.get(language, set())}")

for node in enhanced_ctx.tree.walk():
    node_kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
    if rule._is_call_node(node):
        callee = rule._get_callee_text(node, enhanced_ctx)
        print(f"  Call node found: kind={node_kind}, callee='{callee}'")
        is_sink = rule._is_sink(language, callee)
        print(f"    Is sink? {is_sink}")
        
        if is_sink:
            # Get path argument
            path_arg = rule._get_path_argument(node)
            print(f"    Path arg: {path_arg}")
            if path_arg:
                # Check if user controlled
                is_user = rule._looks_user_controlled(path_arg, enhanced_ctx)
                has_traversal = rule._has_traversal_literal(path_arg, enhanced_ctx)
                print(f"    User controlled? {is_user}")
                print(f"    Has traversal? {has_traversal}")
                if is_user or has_traversal:
                    # Check for normalization
                    has_norm = rule._has_normalization_guard(node, path_arg, language, enhanced_ctx)
                    print(f"    Has normalization guard? {has_norm}")

# Try direct iteration on enhanced context
print("\n=== RULE FINDINGS ===")
findings = list(rule.visit(enhanced_ctx))
print(f"Findings: {len(findings)}")
for f in findings:
    print(f"  - {f}")
