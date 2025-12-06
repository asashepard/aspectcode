#!/usr/bin/env python3
"""
Alpha Rule QA Matrix Generator

This script analyzes all rules in ALPHA_DEFAULT_RULE_IDS and generates
a comprehensive QA matrix showing test coverage and metadata.
"""

import os
import re
import ast
from pathlib import Path
from typing import Dict, List, Set, Optional, Any
import json

# Import the alpha rule IDs
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.profiles import ALPHA_DEFAULT_RULE_IDS
from engine.registry import discover_rules, get_rule, get_rule_ids
from engine.runner import setup_adapters

def analyze_rule_file(rule_id: str) -> Dict[str, Any]:
    """Analyze a rule implementation file to extract metadata."""
    
    # Convert rule ID to expected file name
    rule_file_name = rule_id.replace('.', '_') + '.py'
    rule_file_path = Path('rules') / rule_file_name
    
    if not rule_file_path.exists():
        return {
            'file_exists': False,
            'file_path': str(rule_file_path),
            'category': rule_id.split('.')[0],
            'languages': [],
            'autofix_safety': 'unknown',
            'priority': 'unknown',
            'tier': 'unknown'
        }
    
    try:
        content = rule_file_path.read_text(encoding='utf-8')
        
        # Extract basic info
        result = {
            'file_exists': True,
            'file_path': str(rule_file_path),
            'category': rule_id.split('.')[0],
            'languages': [],
            'autofix_safety': 'unknown', 
            'priority': 'unknown',
            'tier': 'unknown'
        }
        
        # Parse RuleMeta if possible
        meta_match = re.search(r'meta\s*=\s*RuleMeta\s*\(([^)]*)\)', content, re.DOTALL)
        if meta_match:
            meta_content = meta_match.group(1)
            
            # Extract id
            id_match = re.search(r'id\s*=\s*["\']([^"\']+)["\']', meta_content)
            if id_match:
                result['actual_id'] = id_match.group(1)
            
            # Extract languages
            langs_match = re.search(r'langs\s*=\s*\[([^\]]*)\]', meta_content)
            if langs_match:
                langs_str = langs_match.group(1)
                langs = re.findall(r'["\']([^"\']+)["\']', langs_str)
                result['languages'] = langs
            
            # Extract autofix_safety
            autofix_match = re.search(r'autofix_safety\s*=\s*["\']([^"\']+)["\']', meta_content)
            if autofix_match:
                result['autofix_safety'] = autofix_match.group(1)
            
            # Extract priority
            priority_match = re.search(r'priority\s*=\s*["\']([^"\']+)["\']', meta_content)
            if priority_match:
                result['priority'] = priority_match.group(1)
                
            # Extract tier
            tier_match = re.search(r'tier\s*=\s*(\d+)', meta_content)
            if tier_match:
                result['tier'] = tier_match.group(1)
        
        return result
        
    except Exception as e:
        return {
            'file_exists': True,
            'file_path': str(rule_file_path),
            'category': rule_id.split('.')[0],
            'languages': [],
            'autofix_safety': 'unknown',
            'priority': 'unknown',
            'tier': 'unknown',
            'error': str(e)
        }

def find_unit_tests(rule_id: str) -> Dict[str, Any]:
    """Find existing unit tests for a rule."""
    
    test_patterns = [
        f'test_{rule_id.replace(".", "_")}.py',
        f'test_{rule_id.replace(".", "_")}_*.py',
        f'test_*{rule_id.replace(".", "_")}.py'
    ]
    
    tests_dir = Path('tests')
    if not tests_dir.exists():
        return {'has_tests': False, 'test_files': [], 'test_patterns_checked': test_patterns}
    
    found_files = []
    
    # Check direct pattern matches
    for pattern in test_patterns:
        for test_file in tests_dir.glob(f'**/{pattern}'):
            if test_file.is_file():
                found_files.append(str(test_file))
    
    # Also check if the rule is mentioned in any test file
    mentioned_in = []
    for test_file in tests_dir.glob('**/*.py'):
        if test_file.is_file():
            try:
                content = test_file.read_text(encoding='utf-8')
                if rule_id in content or rule_id.replace('.', '_') in content:
                    mentioned_in.append(str(test_file))
            except Exception:
                pass
    
    return {
        'has_tests': len(found_files) > 0,
        'test_files': found_files,
        'mentioned_in': mentioned_in,
        'test_patterns_checked': test_patterns
    }

def find_e2e_coverage(rule_id: str) -> Dict[str, Any]:
    """Find E2E test coverage for a rule."""
    
    # Look for rule mentions in e2e test files
    e2e_patterns = [
        'test_*e2e*.py',
        'test_*integration*.py', 
        'test_*profile*.py',
        'test_*acceptance*.py'
    ]
    
    coverage = {
        'has_e2e': False,
        'e2e_files': [],
        'mentioned_in_e2e': []
    }
    
    for pattern in e2e_patterns:
        for test_file in Path('.').glob(f'**/{pattern}'):
            if test_file.is_file():
                try:
                    content = test_file.read_text(encoding='utf-8')
                    if rule_id in content:
                        coverage['mentioned_in_e2e'].append(str(test_file))
                        coverage['has_e2e'] = True
                except Exception:
                    pass
    
    return coverage

def generate_qa_matrix():
    """Generate the complete QA matrix for alpha rules."""
    
    print("Analyzing alpha default rules...")
    print(f"Total alpha rules to analyze: {len(ALPHA_DEFAULT_RULE_IDS)}")
    
    matrix_data = []
    
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        print(f"Analyzing {rule_id}...")
        
        # Get rule metadata
        rule_info = analyze_rule_file(rule_id)
        
        # Get test coverage
        unit_test_info = find_unit_tests(rule_id)
        e2e_info = find_e2e_coverage(rule_id)
        
        # Compile row data
        row = {
            'rule_id': rule_id,
            'category': rule_info['category'],
            'languages': ', '.join(rule_info['languages']) if rule_info['languages'] else 'unknown',
            'autofix_safety': rule_info['autofix_safety'],
            'priority': rule_info['priority'],
            'tier': rule_info['tier'],
            'has_unit_tests': 'yes' if unit_test_info['has_tests'] else 'no',
            'unit_test_files': '; '.join(unit_test_info['test_files']) if unit_test_info['test_files'] else '',
            'mentioned_in_tests': '; '.join(unit_test_info['mentioned_in'][:3]) if unit_test_info['mentioned_in'] else '',  # limit to first 3
            'has_e2e_coverage': 'yes' if e2e_info['has_e2e'] else 'no',
            'e2e_files': '; '.join(e2e_info['mentioned_in_e2e']) if e2e_info['mentioned_in_e2e'] else '',
            'file_exists': rule_info['file_exists'],
            'notes': []
        }
        
        # Add notes based on analysis
        if not rule_info['file_exists']:
            row['notes'].append('TODO: Rule file missing')
        if rule_info['autofix_safety'] == 'unknown':
            row['notes'].append('TODO: Confirm autofix safety')
        if not rule_info['languages']:
            row['notes'].append('TODO: Confirm supported languages')
        if not unit_test_info['has_tests']:
            row['notes'].append('TODO: Add unit tests')
        if not e2e_info['has_e2e']:
            row['notes'].append('TODO: Add E2E coverage')
        if rule_info['priority'] in ['P0', 'P1'] and not unit_test_info['has_tests']:
            row['notes'].append('HIGH PRIORITY: P0/P1 rule needs unit tests')
            
        row['notes'] = '; '.join(row['notes']) if row['notes'] else ''
        
        matrix_data.append(row)
    
    return matrix_data

def generate_markdown_table(matrix_data: List[Dict]) -> str:
    """Generate markdown table from matrix data."""
    
    # Header
    markdown = """# Alpha Default Rules QA Matrix

This document tracks the test coverage and metadata for all 47 rules in the `ALPHA_DEFAULT_RULE_IDS` profile.

**Legend:**
- **Priority**: P0 (critical), P1 (high), P2 (medium), P3 (low)
- **Autofix Safety**: `safe` (auto-apply), `suggest-only` (suggest but don't auto-apply), `caution` (careful review needed)
- **Tier**: 0 (syntax only), 1 (basic analysis), 2 (advanced analysis)

| Rule ID | Category | Languages | Priority | Tier | Autofix Safety | Unit Tests | E2E Coverage | Notes |
|---------|----------|-----------|----------|------|----------------|------------|--------------|-------|
"""
    
    # Sort by priority then category then rule_id
    def sort_key(row):
        priority_order = {'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3, 'unknown': 4}
        return (priority_order.get(row['priority'], 4), row['category'], row['rule_id'])
    
    sorted_data = sorted(matrix_data, key=sort_key)
    
    for row in sorted_data:
        # Format cells
        rule_id = row['rule_id']
        category = row['category']
        languages = row['languages'] if len(row['languages']) < 30 else row['languages'][:27] + '...'
        priority = row['priority']
        tier = row['tier']
        autofix_safety = row['autofix_safety']
        
        # Unit tests column
        if row['has_unit_tests'] == 'yes':
            unit_tests = f"✅ {row['unit_test_files'][:50]}{'...' if len(row['unit_test_files']) > 50 else ''}"
        else:
            unit_tests = "❌ No"
            
        # E2E coverage column  
        if row['has_e2e_coverage'] == 'yes':
            e2e_coverage = f"✅ {row['e2e_files'][:50]}{'...' if len(row['e2e_files']) > 50 else ''}"
        else:
            e2e_coverage = "❌ No"
            
        # Notes column
        notes = row['notes'][:100] + ('...' if len(row['notes']) > 100 else '') if row['notes'] else ''
        
        markdown += f"| `{rule_id}` | {category} | {languages} | {priority} | {tier} | {autofix_safety} | {unit_tests} | {e2e_coverage} | {notes} |\n"
    
    # Add summary statistics
    total_rules = len(matrix_data)
    rules_with_unit_tests = sum(1 for row in matrix_data if row['has_unit_tests'] == 'yes')
    rules_with_e2e = sum(1 for row in matrix_data if row['has_e2e_coverage'] == 'yes')
    p0_p1_rules = sum(1 for row in matrix_data if row['priority'] in ['P0', 'P1'])
    p0_p1_with_tests = sum(1 for row in matrix_data if row['priority'] in ['P0', 'P1'] and row['has_unit_tests'] == 'yes')
    
    markdown += f"""
## Summary Statistics

- **Total Alpha Rules**: {total_rules}
- **Rules with Unit Tests**: {rules_with_unit_tests}/{total_rules} ({rules_with_unit_tests/total_rules*100:.1f}%)
- **Rules with E2E Coverage**: {rules_with_e2e}/{total_rules} ({rules_with_e2e/total_rules*100:.1f}%)
- **P0/P1 Rules**: {p0_p1_rules}
- **P0/P1 Rules with Unit Tests**: {p0_p1_with_tests}/{p0_p1_rules} ({p0_p1_with_tests/max(p0_p1_rules,1)*100:.1f}%)

## Priority Focus Areas

### High Priority (Missing Unit Tests)
"""
    
    high_priority_missing = [row for row in matrix_data if row['priority'] in ['P0', 'P1'] and row['has_unit_tests'] == 'no']
    if high_priority_missing:
        for row in high_priority_missing:
            markdown += f"- `{row['rule_id']}` ({row['priority']}) - {row['category']}\n"
    else:
        markdown += "✅ All P0/P1 rules have unit tests!\n"
    
    markdown += "\n### Missing Unit Tests (All Priorities)\n"
    missing_tests = [row for row in matrix_data if row['has_unit_tests'] == 'no']
    if missing_tests:
        for row in missing_tests:
            markdown += f"- `{row['rule_id']}` ({row['priority']}) - {row['category']}\n"
    else:
        markdown += "✅ All rules have unit tests!\n"
    
    markdown += "\n### Missing E2E Coverage\n"
    missing_e2e = [row for row in matrix_data if row['has_e2e_coverage'] == 'no']
    if missing_e2e:
        for row in missing_e2e:
            markdown += f"- `{row['rule_id']}` - {row['category']}\n"
    else:
        markdown += "✅ All rules have E2E coverage!\n"
    
    markdown += """
## Maintenance

This matrix is generated by `scripts/generate_alpha_qa_matrix.py` and should be updated when:
- New rules are added to `ALPHA_DEFAULT_RULE_IDS`
- Test coverage changes
- Rule metadata is updated

To regenerate: `python scripts/generate_alpha_qa_matrix.py`
"""
    
    return markdown

if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    os.chdir('..')  # Go to server root
    
    try:
        # Generate the matrix
        matrix_data = generate_qa_matrix()
        
        # Generate markdown
        markdown_content = generate_markdown_table(matrix_data)
        
        # Ensure docs directory exists
        docs_dir = Path('docs')
        docs_dir.mkdir(exist_ok=True)
        
        # Write the file
        output_file = docs_dir / 'alpha_default_rules.md'
        output_file.write_text(markdown_content, encoding='utf-8')
        
        print(f"\nAlpha Rule QA Matrix generated: {output_file}")
        print(f"Total alpha rules: {len(matrix_data)}")
        print(f"Rules with unit tests: {sum(1 for row in matrix_data if row['has_unit_tests'] == 'yes')}")
        print(f"Rules with E2E coverage: {sum(1 for row in matrix_data if row['has_e2e_coverage'] == 'yes')}")
        
        # Also output JSON for programmatic use
        json_file = docs_dir / 'alpha_default_rules.json'
        with open(json_file, 'w') as f:
            json.dump(matrix_data, f, indent=2)
        print(f"JSON data also saved to: {json_file}")
        
    except Exception as e:
        print(f"Error generating matrix: {e}")
        import traceback
        traceback.print_exc()
        exit(1)