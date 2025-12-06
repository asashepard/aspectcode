# Alpha Default Rules QA Matrix

This document tracks the test coverage and metadata for all 47 rules in the `ALPHA_DEFAULT_RULE_IDS` profile.

**Legend:**
- **Priority**: P0 (critical), P1 (high), P2 (medium), P3 (low)
- **Autofix Safety**: `safe` (auto-apply), `suggest-only` (suggest but don't auto-apply), `caution` (careful review needed)
- **Tier**: 0 (syntax only), 1 (basic analysis), 2 (advanced analysis)

| Rule ID | Category | Languages | Priority | Tier | Autofix Safety | Unit Tests | E2E Coverage | Notes |
|---------|----------|-----------|----------|------|----------------|------------|--------------|-------|
| `bug.incompatible_comparison` | bug | python, typescript, javascr... | P0 | 0 | suggest-only | ✅ tests\test_bug_incompatible_comparison.py; tests\t... | ✅ test_profiles.py |  |
| `bug.iteration_modification` | bug | python, java, csharp, javas... | P0 | 0 | suggest-only | ✅ tests\test_bug_iteration_modification.py; tests\te... | ❌ No | TODO: Add E2E coverage |
| `bug.recursion_no_base_case` | bug | python, typescript, javascr... | P0 | 0 | suggest-only | ✅ tests\test_bug_recursion_no_base_case.py; tests\te... | ❌ No | TODO: Add E2E coverage |
| `concurrency.lock_not_released` | concurrency | java, csharp, cpp, python | P0 | 0 | suggest-only | ✅ tests\test_concurrency_lock_not_released.py; tests... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `sec.hardcoded_secret` | sec | python, typescript, javascr... | P0 | 0 | suggest-only | ✅ tests\test_sec_hardcoded_secret.py; tests\test_sec... | ✅ tests\test_alpha_e2e_coverage.py; test_profiles.py |  |
| `sec.sql_injection_concat` | sec | python, javascript, typescr... | P0 | 0 | suggest-only | ✅ tests\test_sec_sql_injection_concat.py; tests\test... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `arch.global_state_usage` | arch | python, typescript, javascr... | P1 | 1 | suggest-only | ✅ tests\test_arch_global_state_usage.py; tests\test_... | ✅ test_acceptance.py |  |
| `bug.boolean_bitwise_misuse` | bug | unknown | P1 | 0 | suggest-only | ✅ tests\test_bug_boolean_bitwise_misuse.py; tests\te... | ❌ No | TODO: Confirm supported languages; TODO: Add E2E coverage |
| `concurrency.blocking_in_async` | concurrency | javascript, typescript, pyt... | P1 | 0 | suggest-only | ✅ tests\test_concurrency_blocking_in_async.py; tests... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `errors.broad_catch` | errors | unknown | P1 | 0 | suggest-only | ✅ tests\test_errors_broad_catch.py; tests\test_error... | ✅ test_profiles.py | TODO: Confirm supported languages |
| `errors.swallowed_exception` | errors | python, java, csharp, ruby,... | P1 | 0 | suggest-only | ✅ tests\test_errors_swallowed_exception.py; tests\te... | ❌ No | TODO: Add E2E coverage |
| `ident.duplicate_definition` | ident | unknown | P1 | 1 | suggest-only | ❌ No | ✅ test_profiles.py | TODO: Confirm supported languages; TODO: Add unit tests; HIGH PRIORITY: P0/P1 rule needs unit tests |
| `ident.shadowing` | ident | python | P1 | 1 | suggest-only | ✅ tests\test_ident_shadowing.py; tests\test_ident_sh... | ❌ No | TODO: Add E2E coverage |
| `sec.insecure_random` | sec | python, javascript, java, c... | P1 | 0 | suggest-only | ✅ tests\test_sec_insecure_random.py; tests\test_sec_... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `sec.open_redirect` | sec | javascript, typescript, pyt... | P1 | 0 | suggest-only | ✅ tests\test_sec_open_redirect.py; tests\test_sec_op... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `sec.path_traversal` | sec | python, javascript, typescr... | P1 | 0 | suggest-only | ✅ tests\test_sec_path_traversal.py; tests\test_sec_p... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `security.jwt_without_exp` | security | python, javascript, typescr... | P1 | 0 | suggest-only | ✅ tests\test_security_jwt_without_exp.py; tests\test... | ✅ tests\test_alpha_e2e_coverage.py |  |
| `test.flaky_sleep` | test | unknown | P1 | 0 | suggest-only | ✅ tests\test_test_flaky_sleep.py; tests\test_test_fl... | ✅ tests\test_alpha_e2e_coverage.py | TODO: Confirm supported languages |
| `test.no_assertions` | test | unknown | P1 | 0 | suggest-only | ✅ tests\test_test_no_assertions.py; tests\test_test_... | ✅ tests\test_alpha_e2e_coverage.py | TODO: Confirm supported languages |
| `bug.float_equality` | bug | python, java, csharp, cpp, ... | P2 | 0 | suggest-only | ✅ tests\test_bug_float_equality.py; tests\test_bug_f... | ❌ No | TODO: Add E2E coverage |
| `complexity.high_cyclomatic` | complexity | python, typescript, javascr... | P2 | 0 | suggest-only | ✅ tests\test_complexity_high_cyclomatic.py; tests\te... | ✅ test_profiles.py |  |
| `complexity.long_function` | complexity | python, javascript, typescr... | P2 | 0 | suggest-only | ✅ tests\test_complexity_long_function.py; tests\test... | ❌ No | TODO: Add E2E coverage |
| `deadcode.unused_variable` | deadcode | unknown | P2 | 1 | safe | ✅ tests\test_deadcode_unused_variable.py; tests\test... | ✅ tests\test_alpha_e2e_coverage.py; tests\test_autof... | TODO: Confirm supported languages |
| `errors.partial_function_implementation` | errors | python, typescript, javascr... | P2 | 0 | suggest-only | ✅ tests\test_errors_partial_function_implementation.... | ❌ No | TODO: Add E2E coverage |
| `imports.unused` | imports | python, typescript, javascr... | P2 | 1 | safe | ✅ tests\test_imports_unused.py; tests\test_imports_u... | ✅ test_profile_e2e.py; tests\test_alpha_e2e_coverage... |  |
| `style.mixed_indentation` | style | python, typescript, javascr... | P2 | 0 | safe | ✅ tests\test_style_mixed_indentation.py; tests\test_... | ✅ tests\test_alpha_e2e_coverage.py; tests\test_autof... |  |
| `analysis.change_impact` | analysis | unknown | unknown | unknown | unknown | ❌ No | ✅ test_alpha_profile_integrity.py | TODO: Rule file missing; TODO: Confirm autofix safety; TODO: Confirm supported languages; TODO: Add ... |
| `architecture.critical_dependency` | architecture | unknown | unknown | unknown | unknown | ❌ No | ✅ test_alpha_profile_integrity.py | TODO: Rule file missing; TODO: Confirm autofix safety; TODO: Confirm supported languages; TODO: Add ... |
| `architecture.dependency_cycle_impact` | architecture | unknown | unknown | unknown | unknown | ❌ No | ✅ test_alpha_profile_integrity.py | TODO: Rule file missing; TODO: Confirm autofix safety; TODO: Confirm supported languages; TODO: Add ... |
| `deadcode.unused_public` | deadcode | unknown | unknown | unknown | unknown | ❌ No | ✅ test_alpha_profile_integrity.py | TODO: Rule file missing; TODO: Confirm autofix safety; TODO: Confirm supported languages; TODO: Add ... |
| `imports.cycle.advanced` | imports | unknown | unknown | unknown | unknown | ❌ No | ❌ No | TODO: Rule file missing; TODO: Confirm autofix safety; TODO: Confirm supported languages; TODO: Add ... |
| `naming.project_term_inconsistency` | naming | unknown | unknown | unknown | unknown | ✅ tests\test_naming_project_term_inconsistency.py; t... | ✅ test_engine_integration.py; test_final_integration... | TODO: Confirm autofix safety; TODO: Confirm supported languages |

## Summary Statistics

- **Total Alpha Rules**: 32
- **Rules with Unit Tests**: 26/32 (81.2%)
- **Rules with E2E Coverage**: 23/32 (71.9%)
- **P0/P1 Rules**: 19
- **P0/P1 Rules with Unit Tests**: 18/19 (94.7%)

## Priority Focus Areas

### High Priority (Missing Unit Tests)
- `ident.duplicate_definition` (P1) - ident

### Missing Unit Tests (All Priorities)
- `imports.cycle.advanced` (unknown) - imports
- `analysis.change_impact` (unknown) - analysis
- `architecture.dependency_cycle_impact` (unknown) - architecture
- `architecture.critical_dependency` (unknown) - architecture
- `deadcode.unused_public` (unknown) - deadcode
- `ident.duplicate_definition` (P1) - ident

### Missing E2E Coverage
- `imports.cycle.advanced` - imports
- `ident.shadowing` - ident
- `bug.float_equality` - bug
- `bug.iteration_modification` - bug
- `bug.boolean_bitwise_misuse` - bug
- `bug.recursion_no_base_case` - bug
- `errors.swallowed_exception` - errors
- `errors.partial_function_implementation` - errors
- `complexity.long_function` - complexity

## Maintenance

This matrix is generated by `scripts/generate_alpha_qa_matrix.py` and should be updated when:
- New rules are added to `ALPHA_DEFAULT_RULE_IDS`
- Test coverage changes
- Rule metadata is updated

To regenerate: `python scripts/generate_alpha_qa_matrix.py`
