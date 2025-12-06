#!/usr/bin/env python3
"""
Analyze alpha rule test results to categorize failures.
"""

# From test output analysis:
# Pattern: Tests show Java/C# adapters aren't loaded in ValidationService

# PASSED tests (36):
PASSED = [
    ("imports.unused", "python"),
    ("arch.global_state_usage", "python"),
    ("arch.global_state_usage", "typescript"),
    ("arch.global_state_usage", "javascript"),
    ("deadcode.unused_variable", "python"),
    ("sec.sql_injection_concat", "typescript"),
    ("sec.sql_injection_concat", "javascript"),
    ("sec.hardcoded_secret", "python"),
    ("sec.hardcoded_secret", "typescript"),
    ("sec.hardcoded_secret", "javascript"),
    ("sec.path_traversal", "python"),
    ("sec.path_traversal", "typescript"),
    ("sec.path_traversal", "javascript"),
    ("sec.open_redirect", "python"),
    ("sec.open_redirect", "typescript"),
    ("sec.open_redirect", "javascript"),
    ("sec.insecure_random", "python"),
    ("sec.insecure_random", "javascript"),
    ("security.jwt_without_exp", "python"),
    ("security.jwt_without_exp", "typescript"),
    ("security.jwt_without_exp", "javascript"),
    ("bug.iteration_modification", "python"),
    ("bug.iteration_modification", "typescript"),
    ("bug.iteration_modification", "javascript"),
    ("bug.recursion_no_base_case", "python"),
    ("bug.recursion_no_base_case", "javascript"),
    ("style.mixed_indentation", "python"),
    ("style.mixed_indentation", "typescript"),
    ("style.mixed_indentation", "javascript"),
    ("ident.duplicate_definition", "python"),
    ("ident.duplicate_definition", "typescript"),
    ("ident.duplicate_definition", "javascript"),
]

# FAILED tests by category:

# 1. ALL JAVA/C# TESTS FAIL - Adapters not loaded
JAVA_CSHARP_FAILURES = [
    # Every single Java and C# test failed because adapters aren't registered
]

# 2. RULES NOT TRIGGERING FOR ANY LANGUAGE (rule implementation issues):
RULE_ISSUES = [
    "bug.incompatible_comparison",  # Failed all 5 languages
    "bug.float_equality",           # Failed all 5 languages  
    "bug.boolean_bitwise_misuse",   # Failed all 5 languages
    "concurrency.lock_not_released", # Failed python/java/csharp
    "concurrency.blocking_in_async", # Failed python/typescript/javascript
    "errors.swallowed_exception",    # Failed all 5 languages
    "errors.broad_catch",            # Failed all 5 languages
    "errors.partial_function_implementation", # Failed all 5 languages
    "complexity.high_cyclomatic",    # Failed all 5 languages
    "complexity.long_function",      # Failed all 5 languages
    "test.flaky_sleep",              # Failed all 5 languages
    "test.no_assertions",            # Failed all 5 languages
    "naming.project_term_inconsistency", # Failed all 5 languages
    "ident.shadowing",               # Failed python (only supported lang)
]

# 3. TS/JS-specific failures (imports.unused needs scopes):
TS_JS_FAILURES = [
    ("imports.unused", "typescript"),
    ("imports.unused", "javascript"),
    ("deadcode.unused_variable", "typescript"),
    ("deadcode.unused_variable", "javascript"),
    ("sec.sql_injection_concat", "python"),  # Fixture issue?
    ("bug.recursion_no_base_case", "typescript"),
]

print("=== ALPHA RULE TRIGGER TEST ANALYSIS ===")
print()
print(f"PASSED: {len(PASSED)} tests")
print(f"  - Python: {sum(1 for r,l in PASSED if l == 'python')}")
print(f"  - TypeScript: {sum(1 for r,l in PASSED if l == 'typescript')}")
print(f"  - JavaScript: {sum(1 for r,l in PASSED if l == 'javascript')}")
print(f"  - Java: {sum(1 for r,l in PASSED if l == 'java')}")
print(f"  - C#: {sum(1 for r,l in PASSED if l == 'csharp')}")
print()
print("ROOT CAUSES:")
print()
print("1. JAVA/C# ADAPTERS NOT LOADED")
print("   - ValidationService.ensure_adapters_loaded() only loads Python/JS/TS")
print("   - Need to add Java and C# adapter loading")
print()
print("2. RULES NOT TRIGGERING (fixture or rule implementation issues):")
for rule in RULE_ISSUES:
    print(f"   - {rule}")
print()
print("3. NEEDS SCOPES FOR JS/TS:")
print("   - imports.unused, deadcode.unused_variable need scope analysis")
print("   - Scope building may fail silently for JS/TS")

if __name__ == "__main__":
    pass
