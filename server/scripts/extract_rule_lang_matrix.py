#!/usr/bin/env python3
"""
Extract rule×language compatibility matrix from alpha default rules.

This script reads the ALPHA_DEFAULT_RULE_IDS from profiles.py,
then extracts the `langs` field from each rule's meta definition.

Output: JSON file with rule_id -> [languages] mapping
"""

import sys
import os
import json
import re
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.profiles import ALPHA_DEFAULT_RULE_IDS

# Map rule_id to filename pattern
def rule_id_to_filename(rule_id: str) -> str:
    """Convert rule_id like 'sec.sql_injection_concat' to filename like 'sec_sql_injection_concat.py'"""
    return rule_id.replace(".", "_") + ".py"

def extract_langs_from_file(filepath: Path) -> list:
    """Extract langs array from a rule file by parsing the meta definition."""
    content = filepath.read_text(encoding='utf-8')
    
    # Pattern 1: langs=[...] in RuleMeta(...)
    pattern1 = r'langs\s*=\s*\[([^\]]+)\]'
    match = re.search(pattern1, content)
    if match:
        langs_str = match.group(1)
        # Extract quoted strings
        langs = re.findall(r'["\'](\w+)["\']', langs_str)
        return langs
    
    # Pattern 2: "langs": [...] (JSON-like)
    pattern2 = r'"langs"\s*:\s*\[([^\]]+)\]'
    match = re.search(pattern2, content)
    if match:
        langs_str = match.group(1)
        langs = re.findall(r'["\'](\w+)["\']', langs_str)
        return langs
    
    return []

def main():
    rules_dir = Path(__file__).parent.parent / "rules"
    output_file = Path(__file__).parent / "rule_lang_matrix.json"
    
    matrix = {}
    missing_rules = []
    target_langs = {"python", "typescript", "javascript", "java", "csharp"}
    
    print(f"Extracting languages for {len(ALPHA_DEFAULT_RULE_IDS)} alpha default rules...")
    print(f"Rules directory: {rules_dir}")
    print()
    
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        filename = rule_id_to_filename(rule_id)
        filepath = rules_dir / filename
        
        if not filepath.exists():
            # Try alternate naming patterns
            alt_filename = rule_id.split(".")[-1] + ".py"
            alt_filepath = rules_dir / alt_filename
            if alt_filepath.exists():
                filepath = alt_filepath
            else:
                missing_rules.append((rule_id, filename))
                continue
        
        langs = extract_langs_from_file(filepath)
        matrix[rule_id] = langs
        
        # Check coverage of target languages
        covered = set(langs) & target_langs
        missing = target_langs - covered
        
        status = "✓" if len(covered) == 5 else f"⚠ missing: {', '.join(sorted(missing))}"
        print(f"  {rule_id}: {langs} {status}")
    
    # Save matrix to JSON
    with open(output_file, 'w') as f:
        json.dump(matrix, f, indent=2)
    
    print()
    print(f"Matrix saved to: {output_file}")
    
    if missing_rules:
        print()
        print(f"WARNING: {len(missing_rules)} rules not found:")
        for rule_id, filename in missing_rules:
            print(f"  - {rule_id} (expected: {filename})")
    
    # Summary statistics
    print()
    print("=== COVERAGE SUMMARY ===")
    for lang in sorted(target_langs):
        count = sum(1 for langs in matrix.values() if lang in langs)
        print(f"  {lang}: {count}/{len(matrix)} rules")
    
    # Rules that support all 5 languages
    full_coverage = [r for r, langs in matrix.items() 
                     if target_langs.issubset(set(langs))]
    print()
    print(f"Rules with full 5-language coverage: {len(full_coverage)}")
    for r in full_coverage:
        print(f"  - {r}")

if __name__ == "__main__":
    main()
