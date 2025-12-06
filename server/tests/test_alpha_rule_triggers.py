#!/usr/bin/env python3
"""
Comprehensive Alpha Rule Trigger Test Suite

This test validates that every alpha default rule triggers correctly 
in all supported languages (Python, TypeScript, JavaScript, Java, C#).

For each rule×language combination where the rule supports that language,
we have a minimal fixture file designed to trigger that specific rule.
The test runs the validation engine and asserts the expected rule fired.
"""

import pytest
from pathlib import Path
from typing import Dict, List, Set, Tuple
import json
import sys
import os

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.profiles import ALPHA_DEFAULT_RULE_IDS
from engine.validation import ValidationService
from engine.registry import get_rule


# Constants
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "alpha_rule_triggers"
TARGET_LANGS = ["python", "typescript", "javascript", "java", "csharp"]
LANG_EXTENSIONS = {
    "python": ".py",
    "typescript": ".ts", 
    "javascript": ".js",
    "java": ".java",
    "csharp": ".cs"
}

# Tier 2 rules that require project_graph
# These rules need cross-file analysis and need project_graph enabled
TIER2_RULES = {
    "naming.project_term_inconsistency",  # Needs project-wide symbol index for term analysis
    "imports.cycle.advanced",  # Needs to analyze multiple files to detect cycles
    "analysis.change_impact",  # Needs project graph to find dependents
    "architecture.dependency_cycle_impact",  # Needs project graph for cycle analysis
    "architecture.critical_dependency",  # Needs project graph for dependency analysis
    "deadcode.unused_public",  # Needs project graph to check if exported symbols are used
}

# Rules that require many dependent files (high threshold rules)
# These are informational rules that only fire on heavily-used symbols
# Skip in fixture tests - they work in real repos but require 5-15+ dependents
HIGH_THRESHOLD_RULES = {
    "analysis.change_impact",  # Needs min_impact_threshold of 5 dependents
    "architecture.critical_dependency",  # Needs critical_threshold of 15 dependents
}

# Rules with partial language support (from matrix extraction)
PARTIAL_SUPPORT = {
    "ident.shadowing": ["python"],  # Only Python
    "sec.insecure_random": ["python", "javascript", "java", "csharp"],  # No TypeScript
    "concurrency.lock_not_released": ["python", "java", "csharp"],  # No JS/TS
    "concurrency.blocking_in_async": ["python", "typescript", "javascript"],  # No Java/C#
}

# Global validation service
_validation_service = None


def get_validation_service() -> ValidationService:
    """Get or create the validation service."""
    global _validation_service
    if _validation_service is None:
        _validation_service = ValidationService()
        _validation_service.ensure_adapters_loaded()
        _validation_service.ensure_rules_loaded()
    return _validation_service


def setup_module():
    """Set up the test environment."""
    get_validation_service()


def get_fixture_path(rule_id: str, lang: str) -> Path:
    """Get the fixture file path for a rule/language combination."""
    safe_rule_name = rule_id.replace(".", "_")
    ext = LANG_EXTENSIONS[lang]
    return FIXTURES_DIR / lang / f"{safe_rule_name}{ext}"


def get_supported_languages(rule_id: str) -> List[str]:
    """Get languages supported by a rule."""
    if rule_id in PARTIAL_SUPPORT:
        return PARTIAL_SUPPORT[rule_id]
    
    # Check if rule exists and get its langs
    rule = get_rule(rule_id)
    if rule:
        return [lang for lang in rule.meta.langs if lang in TARGET_LANGS]
    
    # Default: assume all target languages for rules not found
    return TARGET_LANGS


def collect_test_cases() -> List[Tuple[str, str, Path]]:
    """Collect all test cases (rule_id, language, fixture_path)."""
    test_cases = []
    
    for rule_id in ALPHA_DEFAULT_RULE_IDS:
        # Skip high-threshold rules that need many dependents to trigger
        if rule_id in HIGH_THRESHOLD_RULES:
            continue
            
        for lang in get_supported_languages(rule_id):
            fixture_path = get_fixture_path(rule_id, lang)
            if fixture_path.exists():
                test_cases.append((rule_id, lang, fixture_path))
    
    return test_cases


class TestAlphaRuleTriggers:
    """Test suite for validating alpha rule triggers across all languages."""

    @pytest.fixture(scope="class")
    def test_cases(self):
        """Get all test cases."""
        return collect_test_cases()

    def test_fixture_files_exist(self, test_cases):
        """Verify all expected fixture files exist."""
        missing = []
        for rule_id, lang, fixture_path in test_cases:
            if not fixture_path.exists():
                missing.append((rule_id, lang, str(fixture_path)))
        
        if missing:
            pytest.fail(f"Missing fixture files:\n" + 
                       "\n".join(f"  {r} ({l}): {p}" for r, l, p in missing))

    @pytest.mark.parametrize("rule_id,lang,fixture_path", collect_test_cases(), 
                           ids=lambda x: f"{x[0]}_{x[1]}" if isinstance(x, tuple) else str(x))
    def test_rule_triggers(self, rule_id: str, lang: str, fixture_path: Path):
        """Test that a specific rule triggers for a specific language fixture."""
        if not fixture_path.exists():
            pytest.skip(f"Fixture not found: {fixture_path}")
        
        # Get validation service
        service = get_validation_service()
        
        # Tier 2 rules need project_graph enabled
        # For these rules, we use the language fixture directory as the project root
        is_tier2 = rule_id in TIER2_RULES
        
        # Run validation on the fixture file
        if is_tier2:
            # For Tier 2 rules, validate the whole language directory to build project graph
            lang_dir = fixture_path.parent
            result = service.validate_paths(
                paths=[str(lang_dir)],
                profile="alpha_default",
                enable_project_graph=True
            )
        else:
            result = service.validate_paths(
                paths=[str(fixture_path)],
                profile="alpha_default",
                enable_project_graph=False
            )
        
        # Extract rule IDs from findings
        findings = result.get("findings", [])
        triggered_rules = {f.get("rule_id", f.get("rule")) for f in findings}
        
        # Assert the expected rule was triggered
        assert rule_id in triggered_rules, (
            f"Rule '{rule_id}' did not trigger for {lang} fixture.\n"
            f"Fixture: {fixture_path}\n"
            f"Triggered rules: {triggered_rules}\n"
            f"Total findings: {len(findings)}"
        )


class TestAlphaRuleCoverage:
    """Test suite for verifying alpha rule coverage across languages."""

    def test_all_alpha_rules_have_fixtures(self):
        """Verify all alpha rules have fixtures (except high-threshold rules)."""
        missing_fixtures = []
        
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            # Skip high-threshold rules - they need many dependents
            if rule_id in HIGH_THRESHOLD_RULES:
                continue
                
            for lang in get_supported_languages(rule_id):
                fixture_path = get_fixture_path(rule_id, lang)
                if not fixture_path.exists():
                    missing_fixtures.append((rule_id, lang))
        
        if missing_fixtures:
            msg = "Missing fixtures for:\n"
            for rule_id, lang in missing_fixtures:
                msg += f"  - {rule_id} ({lang})\n"
            pytest.fail(msg)

    def test_coverage_summary(self):
        """Print coverage summary."""
        total = 0
        covered = 0
        skipped = 0
        by_lang = {lang: {"total": 0, "covered": 0} for lang in TARGET_LANGS}
        
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            # Skip high-threshold rules in coverage count
            if rule_id in HIGH_THRESHOLD_RULES:
                skipped += len(get_supported_languages(rule_id))
                continue
                
            for lang in get_supported_languages(rule_id):
                total += 1
                by_lang[lang]["total"] += 1
                
                fixture_path = get_fixture_path(rule_id, lang)
                if fixture_path.exists():
                    covered += 1
                    by_lang[lang]["covered"] += 1
        
        print(f"\n=== Alpha Rule Fixture Coverage ===")
        print(f"Total: {covered}/{total} ({100*covered/total:.1f}%)")
        print(f"Skipped high-threshold rules: {skipped}")
        for lang in TARGET_LANGS:
            stats = by_lang[lang]
            pct = 100*stats["covered"]/stats["total"] if stats["total"] > 0 else 0
            print(f"  {lang}: {stats['covered']}/{stats['total']} ({pct:.1f}%)")
        
        # Assert minimum coverage
        assert covered / total >= 0.8, f"Fixture coverage too low: {100*covered/total:.1f}%"


class TestSpecialRules:
    """Test suite for rules requiring special handling."""

    def test_imports_cycle_python(self):
        """Test imports.cycle with Python module pair."""
        cycle_dir = FIXTURES_DIR / "python"
        module_a = cycle_dir / "module_a.py"
        module_b = cycle_dir / "module_b.py"
        
        if not module_a.exists() or not module_b.exists():
            pytest.skip("Cycle test modules not found")
        
        # For cycle detection, we need project-level analysis
        # This is a placeholder - actual test would use validate_paths
        pytest.skip("imports.cycle requires project-level analysis - tested in E2E suite")

    def test_tier2_alpha_rules_are_tracked(self):
        """Verify Tier 2 alpha rules are in TIER2_RULES."""
        # Only naming.project_term_inconsistency from alpha defaults is Tier 2
        tier2_alpha_rules = [
            "naming.project_term_inconsistency",
        ]
        
        for rule_id in tier2_alpha_rules:
            assert rule_id in TIER2_RULES, f"{rule_id} should be in TIER2_RULES"


if __name__ == "__main__":
    # Run with: python -m pytest test_alpha_rule_triggers.py -v
    pytest.main([__file__, "-v", "--tb=short"])
