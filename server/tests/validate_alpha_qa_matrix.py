"""
Alpha QA Matrix Final Validation

This script provides a final validation that our Alpha Rule QA Matrix implementation 
is working correctly and comprehensively covers all alpha default rules.
"""

import sys
from pathlib import Path
import subprocess

# Add the server directory to path so we can import modules
sys.path.append(str(Path(__file__).parent.parent))

from engine.profiles import ALPHA_DEFAULT_RULE_IDS

def run_qa_matrix_generation():
    """Run the QA matrix generation script and capture output."""
    print("Running QA matrix generation script...")
    
    script_path = Path(__file__).parent.parent / "scripts" / "generate_alpha_qa_matrix.py"
    
    result = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(script_path.parent.parent),
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"❌ QA matrix script failed: {result.stderr}")
        return False
        
    print("✅ QA matrix script executed successfully")
    print(result.stdout)
    return True

def validate_documentation_generated():
    """Validate that the documentation was properly generated."""
    print("\nValidating generated documentation...")
    
    docs_file = Path(__file__).parent.parent / "docs" / "alpha_default_rules.md"
    
    if not docs_file.exists():
        print("❌ Documentation file not generated")
        return False
        
    content = docs_file.read_text(encoding='utf-8')
    
    # Check basic structure
    if "Alpha Default Rules QA Matrix" not in content:
        print("❌ Documentation missing expected title")
        return False
        
    # Check all rules are mentioned
    missing_rules = []
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        if rule_id not in content:
            missing_rules.append(rule_id)
    
    if missing_rules:
        print(f"❌ Missing rules in documentation: {missing_rules}")
        return False
        
    print(f"✅ Documentation contains all {len(ALPHA_DEFAULT_RULE_IDS)} alpha rules")
    
    # Extract coverage statistics from the file
    lines = content.split('\n')
    stats_lines = [line for line in lines if '📋 Rules with unit tests:' in line or '🧪 Rules with E2E coverage:' in line]
    
    if stats_lines:
        for stat_line in stats_lines:
            print(f"  {stat_line.strip()}")
    
    return True

def validate_json_data():
    """Validate the JSON data file was generated."""
    print("\nValidating JSON data...")
    
    json_file = Path(__file__).parent.parent / "docs" / "alpha_default_rules.json"
    
    if not json_file.exists():
        print("❌ JSON data file not generated")
        return False
        
    try:
        import json
        with open(json_file) as f:
            data = json.load(f)
            
        if len(data) != len(ALPHA_DEFAULT_RULE_IDS):
            print(f"❌ JSON contains {len(data)} rules, expected {len(ALPHA_DEFAULT_RULE_IDS)}")
            return False
            
        print(f"✅ JSON data contains all {len(data)} alpha rules")
        
        # Count rules with unit tests and E2E coverage
        unit_test_count = sum(1 for rule in data if rule.get('has_unit_tests') == 'yes')
        e2e_count = sum(1 for rule in data if rule.get('has_e2e_coverage') == 'yes')
        
        print(f"  📋 Unit test coverage: {unit_test_count}/{len(data)} ({unit_test_count/len(data)*100:.1f}%)")
        print(f"  🧪 E2E coverage: {e2e_count}/{len(data)} ({e2e_count/len(data)*100:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"❌ Failed to parse JSON: {e}")
        return False

def validate_themed_projects():
    """Validate that themed E2E projects exist."""
    print("\nValidating themed E2E projects...")
    
    e2e_dir = Path(__file__).parent / "e2e"
    
    expected_projects = [
        "alpha_security",
        "alpha_async", 
        "alpha_imports",
        "alpha_typescript",
        "alpha_style", 
        "alpha_tests"
    ]
    
    missing_projects = []
    for project in expected_projects:
        project_dir = e2e_dir / project
        if project_dir.exists():
            print(f"  ✅ Found: {project}")
        else:
            missing_projects.append(project)
            print(f"  ❌ Missing: {project}")
    
    if missing_projects:
        print(f"❌ Missing themed projects: {missing_projects}")
        return False
        
    print(f"✅ All {len(expected_projects)} themed projects exist")
    return True

def validate_rule_files_exist():
    """Validate that rule implementation files exist."""
    print("\nValidating rule implementation files...")
    
    rules_dir = Path(__file__).parent.parent / "rules"
    
    # These are the special cases with non-standard names
    special_cases = {
        "func.async_mismatch.await_in_sync": "async_mismatch_await_in_sync.py",
        "lang.ts_loose_equality": "ts_loose_equality.py"
    }
    
    missing_files = []
    found_files = []
    
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        if rule_id in special_cases:
            rule_file = rules_dir / special_cases[rule_id]
        else:
            rule_file_name = rule_id.replace('.', '_') + '.py'
            rule_file = rules_dir / rule_file_name
            
        if rule_file.exists():
            found_files.append(rule_id)
        else:
            missing_files.append(rule_id)
            
    if missing_files:
        print(f"❌ Missing rule files: {missing_files}")
        return False
        
    print(f"✅ All {len(found_files)} rule implementation files exist")
    return True

def main():
    """Run the complete validation."""
    print("🔍 Alpha Rule QA Matrix Final Validation")
    print("=" * 50)
    
    validation_steps = [
        ("Rule implementation files", validate_rule_files_exist),
        ("QA matrix generation", run_qa_matrix_generation),
        ("Generated documentation", validate_documentation_generated),
        ("JSON data export", validate_json_data),
        ("Themed E2E projects", validate_themed_projects)
    ]
    
    passed = 0
    failed = 0
    
    for step_name, validation_func in validation_steps:
        print(f"\n{step_name}:")
        print("-" * (len(step_name) + 1))
        
        try:
            if validation_func():
                passed += 1
                print(f"✅ {step_name} validation PASSED")
            else:
                failed += 1
                print(f"❌ {step_name} validation FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {step_name} validation ERROR: {e}")
    
    print(f"\n{'='*50}")
    print(f"📊 FINAL VALIDATION SUMMARY")
    print(f"{'='*50}")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {passed/(passed+failed)*100:.1f}%")
    
    if failed == 0:
        print(f"\n🎉 ALL VALIDATIONS PASSED! Alpha Rule QA Matrix is working perfectly!")
        return 0
    else:
        print(f"\n⚠️  {failed} validation(s) failed. Please review and fix issues.")
        return 1

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)