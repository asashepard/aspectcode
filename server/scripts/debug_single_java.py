#!/usr/bin/env python3
"""Debug script to test a single Java file with a single rule."""

import sys
import os

# Add server to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from engine.validation import ValidationService

# Test file
fixture_path = os.path.join(server_dir, "tests", "fixtures", "alpha_rule_triggers", "java", "sec_path_traversal.java")

# Read fixture
with open(fixture_path, "r") as f:
    content = f.read()
    print("=== FIXTURE CONTENT ===")
    print(content)
    print("=" * 50)

# Create service
vs = ValidationService()
vs.ensure_adapters_loaded()
vs.ensure_rules_loaded()

# Get the Java adapter
from engine.registry import get_adapter
java_adapter = get_adapter("java")
print(f"\nJava adapter: {java_adapter}")

# Try parsing the file
if java_adapter:
    tree = java_adapter.parse(content)
    print(f"Parse result: {tree}")
    if tree:
        print(f"Root node: {tree.root_node}")
        print(f"Root node type: {tree.root_node.type}")
        print(f"Children: {[c.type for c in tree.root_node.children]}")
else:
    print("ERROR: No Java adapter found!")

# Now try validation
print("\n=== VALIDATION ===")
result = vs.validate_paths([fixture_path], profile="alpha_default")
print(f"Result type: {type(result)}")
if isinstance(result, dict):
    print(f"Keys: {result.keys()}")
    if 'findings' in result:
        findings = result['findings']
        print(f"Total findings: {len(findings)}")
        for finding in findings:
            if isinstance(finding, dict):
                print(f"  - {finding.get('rule', 'N/A')}: {finding.get('message', '')[:80]}...")
            elif hasattr(finding, 'rule'):
                print(f"  - {finding.rule}: {finding.message[:80]}...")
            else:
                print(f"  - Finding: {finding}")
else:
    print(f"Result: {result}")
