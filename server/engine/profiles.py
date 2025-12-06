"""
Rule profile definitions for Aspect Code engine.

This module defines predefined rule profiles that control which rules
are active during analysis. Profiles provide curated rule sets for
different use cases and maturity levels.
"""

from typing import List, Dict, Set
from enum import Enum


class RuleProfile(str, Enum):
    """Predefined rule profiles."""
    ALPHA_DEFAULT = "alpha_default"
    ALL = "all"


# ============================================================================
# ALPHA PROFILE RULE REGISTRY
# ============================================================================
# 
# This is the SINGLE SOURCE OF TRUTH for rules included in the alpha profile.
# 
# To DISABLE a rule for alpha:
#   1. Set enabled=False in the tuple below
#   2. Add a comment explaining why (e.g., "# Too noisy - needs precision work")
#
# To ADD a rule:
#   1. Add a new tuple with (rule_id, enabled, notes)
#   2. Ensure the rule exists in server/rules/
#
# Format: (rule_id, enabled, notes)
#   - rule_id: The rule's unique identifier
#   - enabled: True = active in alpha, False = disabled for alpha
#   - notes: Brief description for maintainers
#
ALPHA_RULES_REGISTRY: List[tuple] = [
    # -------------------------------------------------------------------------
    # IMPORTS & DEPENDENCIES
    # -------------------------------------------------------------------------
    ("imports.cycle.advanced", True, "Tier 2: Cross-file import cycles"),
    ("imports.unused", True, "Tier 1: Unused import detection - KB-only (noisy for user display)"),
    
    # -------------------------------------------------------------------------
    # ARCHITECTURE & CODE QUALITY (Tier 1)
    # -------------------------------------------------------------------------
    ("arch.global_state_usage", True, "Detects mutable global state"),
    ("deadcode.unused_variable", True, "Tier 1: Unused variable detection"),
    ("ident.shadowing", False, "Disabled: too noisy on 'id' in data models - common pattern"),
    
    # -------------------------------------------------------------------------
    # KB-ENRICHING RULES (info severity - for AI agent context)
    # -------------------------------------------------------------------------
    ("arch.entry_point", True, "HTTP handlers, CLI commands, main functions"),
    ("arch.external_integration", True, "HTTP clients, databases, message queues"),
    ("arch.data_model", True, "ORM models, dataclasses, interfaces"),
    
    # -------------------------------------------------------------------------
    # ADVANCED ARCHITECTURAL ANALYSIS (Tier 2 - requires project_graph)
    # -------------------------------------------------------------------------
    ("analysis.change_impact", True, "Tier 2: Change impact analysis"),
    ("architecture.dependency_cycle_impact", True, "Tier 2: Cycle impact scoring"),
    ("architecture.critical_dependency", True, "Tier 2: Critical dependency detection"),
    ("deadcode.unused_public", True, "Tier 2: Unused public API detection"),
    
    # -------------------------------------------------------------------------
    # SECURITY - Cross-language vulnerabilities
    # -------------------------------------------------------------------------
    ("sec.sql_injection_concat", True, "SQL injection via string concat"),
    ("sec.hardcoded_secret", True, "Hardcoded passwords/API keys"),
    ("sec.path_traversal", True, "Path traversal vulnerabilities"),
    ("sec.open_redirect", True, "Open redirect vulnerabilities"),
    ("sec.insecure_random", True, "Insecure random number generation"),
    ("security.jwt_without_exp", True, "JWT tokens without expiration"),
    
    # -------------------------------------------------------------------------
    # HIGH-IMPACT BUGS
    # -------------------------------------------------------------------------
    ("bug.incompatible_comparison", False, "Disabled: false positives on len(x) > 0 and similar"),
    ("bug.float_equality", True, "Floating point equality checks"),
    ("bug.iteration_modification", True, "Modifying collection during iteration"),
    ("bug.boolean_bitwise_misuse", True, "Boolean vs bitwise operator misuse"),
    ("bug.recursion_no_base_case", False, "Disabled: false positives on super() delegation patterns"),
    
    # -------------------------------------------------------------------------
    # CONCURRENCY ISSUES
    # -------------------------------------------------------------------------
    ("concurrency.lock_not_released", True, "Lock acquired but not released"),
    ("concurrency.blocking_in_async", True, "Blocking calls in async context"),
    
    # -------------------------------------------------------------------------
    # ERROR HANDLING
    # -------------------------------------------------------------------------
    ("errors.swallowed_exception", True, "Caught exceptions that are ignored"),
    ("errors.broad_catch", True, "Overly broad exception catching"),
    ("errors.partial_function_implementation", True, "NotImplementedError patterns"),
    
    # -------------------------------------------------------------------------
    # COMPLEXITY & MAINTAINABILITY
    # -------------------------------------------------------------------------
    ("complexity.high_cyclomatic", True, "High cyclomatic complexity"),
    ("complexity.long_function", True, "Functions exceeding line threshold"),
    ("style.mixed_indentation", True, "Mixed tabs and spaces"),
    
    # -------------------------------------------------------------------------
    # TESTING QUALITY
    # -------------------------------------------------------------------------
    ("test.flaky_sleep", True, "time.sleep in tests (flaky)"),
    ("test.no_assertions", False, "Disabled: false positives on fixture/side-effect tests"),
    
    # -------------------------------------------------------------------------
    # NAMING & DUPLICATE DETECTION
    # -------------------------------------------------------------------------
    ("naming.project_term_inconsistency", True, "Inconsistent terminology - KB-only (stylistic, not bugs)"),
    ("ident.duplicate_definition", True, "Duplicate function/class definitions"),
]


def get_alpha_enabled_rules() -> List[str]:
    """Get list of enabled rule IDs for alpha profile."""
    return [rule_id for rule_id, enabled, _ in ALPHA_RULES_REGISTRY if enabled]


def get_alpha_disabled_rules() -> List[str]:
    """Get list of disabled rule IDs (for debugging/review)."""
    return [rule_id for rule_id, enabled, _ in ALPHA_RULES_REGISTRY if not enabled]


# Backwards compatibility: maintain ALPHA_DEFAULT_RULE_IDS list
ALPHA_DEFAULT_RULE_IDS: List[str] = get_alpha_enabled_rules()


# Auto-Fix v1 rule profile - safe subset of alpha rules for automatic fixing
#
# These rules have been validated as safe for automatic application:
# 1. autofix_safety="safe" in rule metadata
# 2. Support Python, TypeScript, or JavaScript 
# 3. Fixes are idempotent and undoable
# 4. No semantic changes that could break functionality
#
# Rules are prioritized by impact and safety:
# - P0: Critical bugs and imports (highest priority)
# - P1: Code style and deadcode cleanup
# - P3: Cosmetic style fixes (lowest priority)
# 
# NOTE: Temporarily restricted to the most obviously safe rules until manual audit complete.
AUTO_FIX_V1_RULE_IDS: List[str] = [
    # Style fixes - completely safe
    "style.trailing_whitespace",     # Safe whitespace cleanup
    "style.missing_newline_eof",     # Safe EOF formatting
    "style.mixed_indentation",       # Safe formatting fix
    
    # Import cleanup - very safe
    "imports.unused",                # Safe import cleanup
    "deadcode.duplicate_import",     # Safe import deduplication
    "deadcode.unused_variable",      # Safe variable cleanup (when obvious)
    
    # TEMPORARILY REMOVED (pending manual audit):
    # "bug.assignment_in_conditional", # Could change logic behavior
    # "bug.python_is_vs_eq",           # Could change logic behavior  
    # "deadcode.redundant_condition",  # Could change logic behavior
    # "lang.ts_loose_equality",        # Could change behavior in edge cases
]


def get_profile_rule_ids(profile: RuleProfile) -> Set[str]:
    """
    Get the set of rule IDs for a given profile.
    
    This function is used by the registry system to filter rules
    during profile-based rule loading. The returned rule IDs must
    exist in the global rule registry.
    
    Args:
        profile: The rule profile to get rules for
        
    Returns:
        Set of rule IDs included in the profile
        
    Note:
        For ALPHA_DEFAULT: Returns the fixed set of 32 rule IDs.
        For ALL: Returns empty set, which signals the registry to include all discovered rules.
    """
    if profile == RuleProfile.ALPHA_DEFAULT:
        return set(ALPHA_DEFAULT_RULE_IDS)
    elif profile == RuleProfile.ALL:
        # Return empty set - this means "all rules" and should be handled
        # by the caller to include all discovered rules
        return set()
    else:
        raise ValueError(f"Unknown rule profile: {profile}")


def get_default_profile() -> RuleProfile:
    """Get the default rule profile."""
    return RuleProfile.ALPHA_DEFAULT


def validate_profile(profile_name: str) -> RuleProfile:
    """
    Validate and normalize a profile name.
    
    Args:
        profile_name: Profile name to validate
        
    Returns:
        Validated RuleProfile enum
        
    Raises:
        ValueError: If profile name is not recognized
    """
    try:
        return RuleProfile(profile_name)
    except ValueError:
        valid_profiles = [p.value for p in RuleProfile]
        raise ValueError(
            f"Invalid profile '{profile_name}'. "
            f"Valid profiles are: {', '.join(valid_profiles)}"
        )


def get_profile_info() -> Dict[str, Dict[str, any]]:
    """
    Get information about all available profiles.
    
    Returns:
        Dictionary mapping profile names to their metadata
    """
    return {
        RuleProfile.ALPHA_DEFAULT.value: {
            "name": "Alpha Default",
            "description": "Cross-language, high-impact rules that prevent production failures",
            "rule_count": len(ALPHA_DEFAULT_RULE_IDS),
            "recommended": True
        },
        RuleProfile.ALL.value: {
            "name": "All Rules",
            "description": "Complete set of all implemented rules",
            "rule_count": "dynamic",
            "recommended": False
        }
    }


def debug_profile_coverage(profile: RuleProfile = RuleProfile.ALPHA_DEFAULT) -> Dict[str, any]:
    """
    Debug helper function to analyze profile rule coverage.
    
    This function provides detailed information about which rules are
    included in a profile and helps diagnose coverage issues.
    
    Args:
        profile: The profile to analyze (default: ALPHA_DEFAULT)
        
    Returns:
        Dictionary with detailed profile analysis information
        
    Note:
        This function requires the registry to be initialized with discovered rules.
    """
    from .registry import get_rule_ids, get_rules_for_profile, discover_rules
    from .runner import setup_adapters as runner_setup_adapters
    
    try:
        # Ensure rules are discovered
        runner_setup_adapters()
        discover_rules(["rules"])
        
        all_registered_rule_ids = set(get_rule_ids())
        profile_rule_ids = get_profile_rule_ids(profile)
        
        # Test multiple languages to get comprehensive coverage
        test_languages = ["python", "typescript", "javascript", "c", "cpp"]
        loaded_rules_by_language = {}
        all_loaded_rule_ids = set()
        
        for lang in test_languages:
            try:
                rules = get_rules_for_profile(profile, lang)
                rule_ids = {rule.meta.id for rule in rules}
                loaded_rules_by_language[lang] = {
                    "count": len(rules),
                    "rule_ids": sorted(rule_ids)
                }
                all_loaded_rule_ids.update(rule_ids)
            except Exception as e:
                loaded_rules_by_language[lang] = {
                    "count": 0,
                    "rule_ids": [],
                    "error": str(e)
                }
        
        # Calculate coverage statistics
        if profile == RuleProfile.ALPHA_DEFAULT:
            expected_rule_ids = set(ALPHA_DEFAULT_RULE_IDS)
            missing_from_registry = expected_rule_ids - all_registered_rule_ids
            missing_from_loading = expected_rule_ids - all_loaded_rule_ids
            extra_in_loading = all_loaded_rule_ids - expected_rule_ids
        else:
            expected_rule_ids = all_registered_rule_ids
            missing_from_registry = set()
            missing_from_loading = set()
            extra_in_loading = set()
        
        return {
            "profile": profile.value,
            "registry_status": {
                "total_registered_rules": len(all_registered_rule_ids),
                "profile_specified_rules": len(expected_rule_ids),
                "rules_missing_from_registry": len(missing_from_registry),
                "missing_rule_ids": sorted(missing_from_registry)
            },
            "loading_status": {
                "total_loaded_across_languages": len(all_loaded_rule_ids),
                "rules_missing_from_loading": len(missing_from_loading),
                "extra_rules_loaded": len(extra_in_loading),
                "missing_rule_ids": sorted(missing_from_loading),
                "extra_rule_ids": sorted(extra_in_loading)
            },
            "language_breakdown": loaded_rules_by_language,
            "coverage_summary": {
                "expected_rules": len(expected_rule_ids),
                "actually_loaded": len(all_loaded_rule_ids),
                "coverage_percentage": len(all_loaded_rule_ids) / max(len(expected_rule_ids), 1) * 100,
                "is_complete": len(missing_from_loading) == 0 and len(extra_in_loading) == 0
            }
        }
        
    except Exception as e:
        return {
            "profile": profile.value,
            "error": f"Failed to analyze profile: {str(e)}",
            "registry_status": {},
            "loading_status": {},
            "language_breakdown": {},
            "coverage_summary": {}
        }

