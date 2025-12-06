#!/usr/bin/env python3
"""
Diagnose alpha rule test failures.
Identifies whether failure is due to:
1. Adapter issues (language not supported)
2. Rule not triggering (fixture pattern mismatch)
3. Rule implementation bug
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.validation import ValidationService
from engine.profiles import ALPHA_DEFAULT_RULE_IDS
from engine.registry import get_rules_for_language, get_rule

# Test fixtures directory
FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures" / "alpha_rule_triggers"
TARGET_LANGS = ["python", "typescript", "javascript", "java", "csharp"]
EXTENSIONS = {"python": ".py", "typescript": ".ts", "javascript": ".js", "java": ".java", "csharp": ".cs"}

# Special rules that need project-level analysis
SKIP_RULES = {
    "imports.cycle", "analysis.change_impact", "architecture.dependency_cycle_impact",
    "architecture.critical_dependency", "deadcode.unused_public"
}

def main():
    vs = ValidationService()
    vs.ensure_adapters_loaded()
    vs.ensure_rules_loaded()
    
    results = {"passed": [], "failed": [], "skipped": [], "no_fixture": []}
    
    print("=== ALPHA RULE TRIGGER DIAGNOSIS ===\n")
    
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        if rule_id in SKIP_RULES:
            results["skipped"].append((rule_id, "all", "Requires project graph"))
            continue
        
        rule = get_rule(rule_id)
        if not rule:
            print(f"[WARN] Rule not found: {rule_id}")
            continue
        
        supported_langs = [l for l in rule.meta.langs if l in TARGET_LANGS]
        
        for lang in supported_langs:
            ext = EXTENSIONS[lang]
            fixture_name = rule_id.replace(".", "_") + ext
            fixture_path = FIXTURES_DIR / lang / fixture_name
            
            if not fixture_path.exists():
                results["no_fixture"].append((rule_id, lang, str(fixture_path)))
                continue
            
            # Run validation - explicitly specify language to process
            result = vs.validate_paths(
                paths=[str(fixture_path)],
                profile="alpha_default",
                enable_project_graph=False,
                languages=[lang]  # Explicitly set the language!
            )
            
            findings = result.get("findings", [])
            triggered_rules = {f.get("rule_id", f.get("rule")) for f in findings}
            
            if rule_id in triggered_rules:
                results["passed"].append((rule_id, lang))
                print(f"[PASS] {rule_id} ({lang})")
            else:
                # Debug: show what rules DID trigger
                results["failed"].append((rule_id, lang, list(triggered_rules)))
                print(f"[FAIL] {rule_id} ({lang}) - triggered: {triggered_rules}")
    
    # Summary
    print("\n=== SUMMARY ===")
    print(f"Passed: {len(results['passed'])}")
    print(f"Failed: {len(results['failed'])}")
    print(f"Skipped: {len(results['skipped'])}")
    print(f"No fixture: {len(results['no_fixture'])}")
    
    # Group failures by rule
    print("\n=== FAILED RULES ===")
    failed_by_rule = {}
    for rule_id, lang, triggered in results["failed"]:
        if rule_id not in failed_by_rule:
            failed_by_rule[rule_id] = []
        failed_by_rule[rule_id].append((lang, triggered))
    
    for rule_id, failures in sorted(failed_by_rule.items()):
        langs = [l for l, _ in failures]
        print(f"  {rule_id}: {', '.join(langs)}")

if __name__ == "__main__":
    main()
