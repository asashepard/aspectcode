"""
Centralized file filtering for the Aspect Code engine.

This module provides a single helper to decide whether a file should be
analyzed for a given rule, based on:
- Vendor/generated directory exclusions (node_modules, .venv, dist, etc.)
- Language-appropriate extension filtering
- Test file handling for certain rule categories

Usage:
    from engine.file_filter import should_analyze_file

    # In runner.py or individual rules:
    if not should_analyze_file(file_path, rule_id):
        return  # skip this file for this rule
"""

import os
import re
from typing import Optional, Set, FrozenSet
from functools import lru_cache


# ============================================================================
# VENDOR / GENERATED DIRECTORY EXCLUSIONS
# ============================================================================
# These directories are universally excluded from analysis.
# They contain third-party code, build artifacts, or generated files.
EXCLUDED_DIRS: FrozenSet[str] = frozenset([
    # Package managers / dependencies
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "virtualenv",
    "__pycache__",
    ".pyc",
    "site-packages",
    "vendor",
    "vendors",
    "bower_components",
    "jspm_packages",
    
    # Build output
    "dist",
    "build",
    "out",
    "output",
    "target",  # Java/Maven/Rust
    "bin",
    "obj",  # C#/.NET
    ".next",  # Next.js
    ".nuxt",  # Nuxt.js
    ".svelte-kit",  # SvelteKit
    ".vercel",
    ".netlify",
    
    # Version control
    ".git",
    ".svn",
    ".hg",
    
    # IDE / editor
    ".idea",
    ".vscode",
    ".vs",
    
    # Cache / temp
    ".cache",
    ".parcel-cache",
    ".turbo",
    ".nx",
    "__snapshots__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    "coverage",
    ".coverage",
    "htmlcov",
    ".nyc_output",
    
    # Generated code markers
    "generated",
    "auto-generated",
    "autogen",
    "__generated__",
    
    # Aspect Code's own output
    ".aspect",
])

# Compiled regex for efficient directory matching
# Pattern: /dirname/ or /dirname at end of path (requires full directory name match)
_EXCLUDED_DIR_PATTERN = re.compile(
    r'[/\\](?:' + '|'.join(re.escape(d) for d in EXCLUDED_DIRS) + r')(?:[/\\]|$)',
    re.IGNORECASE
)


# ============================================================================
# LANGUAGE EXTENSION FILTERS
# ============================================================================
# Map of language -> extensions that should be EXCLUDED from analysis.
# For example, we don't want to run Python rules on .pyi stub files.
EXCLUDED_EXTENSIONS_BY_LANG: dict[str, FrozenSet[str]] = {
    "python": frozenset([
        ".pyi",      # Type stubs - not runtime code
        ".ipynb",    # Notebooks - different analysis needed
        ".pyx",      # Cython - different syntax
        ".pxd",      # Cython declarations
    ]),
    "typescript": frozenset([
        ".d.ts",     # Type declarations only
    ]),
    "javascript": frozenset([
        # JS doesn't have many excluded extensions
    ]),
    "java": frozenset([
        # Java doesn't have excluded extensions
    ]),
    "csharp": frozenset([
        ".Designer.cs",  # Auto-generated designer files
    ]),
    "go": frozenset([
        "_test.go",  # Test files handled separately
    ]),
}


# ============================================================================
# TEST FILE PATTERNS
# ============================================================================
# Files matching these patterns are considered test files.
# Some rules skip test files to reduce noise.
TEST_FILE_PATTERNS = [
    # Python
    r"test_[^/\\]+\.py$",
    r"[^/\\]+_test\.py$",
    r"tests?[/\\]",
    r"conftest\.py$",
    
    # JavaScript/TypeScript
    r"\.test\.[jt]sx?$",
    r"\.spec\.[jt]sx?$",
    r"\.e2e\.[jt]sx?$",  # End-to-end tests (Playwright, Cypress, etc.)
    r"__tests__[/\\]",
    r"playwright[/\\]",  # Playwright test directories
    r"cypress[/\\]",  # Cypress test directories
    r"e2e[/\\]",  # Generic e2e test directories
    r"\.stories\.[jt]sx?$",  # Storybook - not production code
    
    # Java
    r"Test[^/\\]*\.java$",
    r"[^/\\]+Test\.java$",
    
    # C#
    r"[^/\\]+Tests?\.cs$",
    
    # Go
    r"_test\.go$",
]

_TEST_FILE_PATTERN = re.compile(
    '|'.join(f'(?:{p})' for p in TEST_FILE_PATTERNS),
    re.IGNORECASE
)


# ============================================================================
# MIGRATION / FIXTURE PATTERNS  
# ============================================================================
# Directories/files that contain database migrations or test fixtures.
# Many "code smells" are acceptable in these files.
MIGRATION_PATTERNS = [
    r"migrations?[/\\]",
    r"alembic[/\\]",
    r"flyway[/\\]",
    r"db[/\\]migrate[/\\]",
    r"schema[/\\]",
    r"fixtures?[/\\]",
    r"seeds?[/\\]",
    r"factories?[/\\]",
]

_MIGRATION_PATTERN = re.compile(
    '|'.join(f'(?:{p})' for p in MIGRATION_PATTERNS),
    re.IGNORECASE
)


# ============================================================================
# TUTORIAL / DOCS / EXAMPLES PATTERNS
# ============================================================================
# Directories containing documentation, tutorials, or example code.
# Security and some other rules should skip these to reduce false positives
# from intentional "bad" example code.
TUTORIAL_DOCS_PATTERNS = [
    r"docs?[/\\]",
    r"docs_src[/\\]",
    r"documentation[/\\]",
    r"examples?[/\\]",
    r"samples?[/\\]",
    r"tutorials?[/\\]",
    r"snippets?[/\\]",
    r"demos?[/\\]",
    r"cookbook[/\\]",
    r"recipes?[/\\]",
    r"playground[/\\]",
    r"sandbox[/\\]",
    r"quickstart[/\\]",
    r"getting[_-]?started[/\\]",
]

_TUTORIAL_DOCS_PATTERN = re.compile(
    '|'.join(f'(?:{p})' for p in TUTORIAL_DOCS_PATTERNS),
    re.IGNORECASE
)


# ============================================================================
# RULES THAT SHOULD SKIP TEST FILES
# ============================================================================
# These rule categories/IDs should not run on test files because:
# - Test files often have intentional "smells" (e.g., complex setup)
# - False positive rate is too high in tests
# - Finding is not actionable in test context
RULES_SKIP_TESTS: FrozenSet[str] = frozenset([
    # Complexity rules - tests often have intentional verbosity
    "complexity.high_cyclomatic",
    "complexity.long_function", 
    "complexity.long_file",
    "complexity.long_parameter_list",
    "complexity.complex_expression",
    "complexity.deep_nesting",
    
    # Dead code - test helpers may appear "unused"
    "deadcode.unused_variable",
    "deadcode.unused_public",
    
    # Naming - test names are intentionally verbose
    "naming.project_term_inconsistency",
    
    # Architecture - test files have different patterns
    "arch.global_state_usage",
    
    # Style - test files may use different conventions
    "style.mixed_indentation",
    
    # Bugs - tests intentionally use patterns that would be bugs in production
    "bug.float_equality",  # Tests often compare exact float values intentionally
    
    # Security - test code is not production attack surface
    "sec.path_traversal",  # Test variables named 'path' are not security issues
    "sec.hardcoded_secret",  # Tests need hardcoded dummy credentials for testing
    "sec.insecure_random",  # Test code doesn't need crypto-secure random
    "sec.open_redirect",  # Test redirect assertions are not vulnerabilities
    
    # Concurrency - tests may intentionally use blocking calls
    "concurrency.blocking_in_async",  # Test fixtures may use sleep() intentionally
    
    # Error handling - tests intentionally raise/use NotImplementedError
    "errors.partial_function_implementation",
    "errors.swallowed_exception",  # Tests use empty catch to verify error-throwing behavior
])


# ============================================================================
# RULES THAT SHOULD SKIP MIGRATION FILES
# ============================================================================
# These rules should not run on migration/schema files because:
# - Migrations often have generated or intentionally verbose code
# - Schema files are declarative, not logic
RULES_SKIP_MIGRATIONS: FrozenSet[str] = frozenset([
    "complexity.high_cyclomatic",
    "complexity.long_function",
    "complexity.long_file",
    "deadcode.unused_variable",
    "naming.project_term_inconsistency",
    "arch.global_state_usage",
])


# ============================================================================
# RULES THAT SHOULD SKIP TUTORIAL / DOCS / EXAMPLE FILES
# ============================================================================
# These rules should not run on tutorial/example code because:
# - Examples intentionally show "bad" patterns for teaching
# - Docs may have simplified code that triggers false positives
# - Security findings on example code are not actionable
RULES_SKIP_TUTORIALS: FrozenSet[str] = frozenset([
    # Security rules - examples often have dummy credentials
    "sec.hardcoded_secret",
    "sec.sql_injection",
    "sec.path_traversal",
    "sec.command_injection",
    "sec.insecure_random",
    "sec.open_redirect",  # Examples use simplified redirect patterns
    "security.jwt_without_exp",
    "security.jwt_weak_algorithm",
    
    # Architecture rules - examples use simplified patterns
    "architecture.dependency_cycle_impact",
    "arch.global_state_usage",
    
    # Complexity - examples are intentionally simplified or verbose for teaching
    "complexity.high_cyclomatic",
    "complexity.long_function",
    "complexity.deep_nesting",
    
    # Naming - tutorial code intentionally uses varied naming for illustration
    "naming.project_term_inconsistency",
    
    # Unused imports/variables - tutorials may have demo code
    "imports.unused",
    "deadcode.unused_variable",  # Examples often have illustrative unused vars
])


# ============================================================================
# SCRIPTS DIRECTORY PATTERNS
# ============================================================================
# Directories containing internal tooling, build scripts, or CI scripts.
# Security rules should skip these as they're not user-facing code.
SCRIPTS_DIR_PATTERNS = [
    r"scripts?[/\\]",
    r"tooling[/\\]",
    r"tools[/\\]",
    r"ci[/\\]",
    r"\.github[/\\]",
    r"\.circleci[/\\]",
    r"devops[/\\]",
    r"build[_-]?scripts?[/\\]",
    r"perf[/\\]",  # Performance benchmarks, not production code
    r"benchmark[s]?[/\\]",  # Benchmark scripts
]

_SCRIPTS_DIR_PATTERN = re.compile(
    '|'.join(f'(?:{p})' for p in SCRIPTS_DIR_PATTERNS),
    re.IGNORECASE
)


# ============================================================================
# RULES THAT SHOULD SKIP SCRIPTS DIRECTORIES
# ============================================================================
# These rules should not run on internal scripts/tooling because:
# - Scripts are often quick-and-dirty internal tools
# - Security findings on internal tooling are low-priority
# - Error handling patterns in scripts differ from production code
RULES_SKIP_SCRIPTS: FrozenSet[str] = frozenset([
    # Security rules - scripts don't need production-level security
    "sec.path_traversal",
    "sec.command_injection",
    "sec.insecure_random",
    
    # Error handling - scripts often have intentionally simple error handling
    "errors.swallowed_exception",
    "errors.broad_catch",
])


# ============================================================================
# MINIMUM FILE SIZE FOR CERTAIN RULES
# ============================================================================
# Some rules should only fire on files with enough content to be meaningful.
# Key: rule_id, Value: minimum lines (approximate, based on newline count)
MIN_LINES_FOR_RULE: dict[str, int] = {
    "complexity.long_file": 50,  # Don't flag a 30-line file as "long"
    "imports.cycle.advanced": 5,  # Need some imports to have a cycle
    "naming.project_term_inconsistency": 10,  # Need enough context
}


# ============================================================================
# MAIN API
# ============================================================================

@lru_cache(maxsize=4096)
def is_excluded_path(file_path: str) -> bool:
    """
    Check if a file path is in an excluded directory.
    
    Uses LRU cache for performance since the same paths are checked repeatedly.
    
    Args:
        file_path: Absolute or relative path to check
        
    Returns:
        True if the file should be excluded, False otherwise
    """
    normalized = file_path.replace('\\', '/')
    return bool(_EXCLUDED_DIR_PATTERN.search(normalized))


@lru_cache(maxsize=2048)
def is_test_file(file_path: str) -> bool:
    """
    Check if a file is a test file.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if this is a test file, False otherwise
    """
    return bool(_TEST_FILE_PATTERN.search(file_path))


@lru_cache(maxsize=2048)
def is_migration_file(file_path: str) -> bool:
    """
    Check if a file is a migration/schema/fixture file.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if this is a migration-related file, False otherwise
    """
    return bool(_MIGRATION_PATTERN.search(file_path))


@lru_cache(maxsize=2048)
def is_tutorial_or_docs_file(file_path: str) -> bool:
    """
    Check if a file is in a tutorial, docs, or examples directory.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if this is a tutorial/docs/example file, False otherwise
    """
    return bool(_TUTORIAL_DOCS_PATTERN.search(file_path))


@lru_cache(maxsize=2048)
def is_scripts_dir(file_path: str) -> bool:
    """
    Check if a file is in a scripts/tooling directory.
    
    Args:
        file_path: Path to check
        
    Returns:
        True if this is in a scripts/tooling directory, False otherwise
    """
    return bool(_SCRIPTS_DIR_PATTERN.search(file_path))


def has_excluded_extension(file_path: str, language: Optional[str] = None) -> bool:
    """
    Check if a file has an extension that should be excluded for its language.
    
    Args:
        file_path: Path to check
        language: Language ID (python, typescript, etc.) or None to auto-detect
        
    Returns:
        True if this extension should be excluded, False otherwise
    """
    if language is None:
        language = _detect_language(file_path)
    
    if language not in EXCLUDED_EXTENSIONS_BY_LANG:
        return False
    
    excluded = EXCLUDED_EXTENSIONS_BY_LANG[language]
    lower_path = file_path.lower()
    
    return any(lower_path.endswith(ext) for ext in excluded)


def _detect_language(file_path: str) -> Optional[str]:
    """Detect language from file extension."""
    lower = file_path.lower()
    if lower.endswith('.py'):
        return 'python'
    elif lower.endswith('.ts') or lower.endswith('.tsx'):
        return 'typescript'
    elif lower.endswith('.js') or lower.endswith('.jsx'):
        return 'javascript'
    elif lower.endswith('.java'):
        return 'java'
    elif lower.endswith('.cs'):
        return 'csharp'
    elif lower.endswith('.go'):
        return 'go'
    elif lower.endswith('.rb'):
        return 'ruby'
    elif lower.endswith('.rs'):
        return 'rust'
    elif lower.endswith('.c') or lower.endswith('.h'):
        return 'c'
    elif lower.endswith('.cpp') or lower.endswith('.hpp') or lower.endswith('.cc'):
        return 'cpp'
    return None


def should_analyze_file(
    file_path: str, 
    rule_id: Optional[str] = None,
    language: Optional[str] = None,
    content: Optional[str] = None
) -> bool:
    """
    Central decision point: should we analyze this file for this rule?
    
    This function implements the layered filtering strategy:
    1. Exclude vendor/generated directories (always)
    2. Exclude language-inappropriate extensions
    3. Skip test files for certain rules
    4. Skip migration files for certain rules
    5. Skip files below minimum size for certain rules
    
    Args:
        file_path: Path to the file being analyzed
        rule_id: Rule ID (e.g., "complexity.high_cyclomatic") or None for all rules
        language: Language ID or None to auto-detect
        content: File content (optional, for size checks)
        
    Returns:
        True if the file should be analyzed, False if it should be skipped
    """
    # Layer 1: Always exclude vendor/generated directories
    if is_excluded_path(file_path):
        return False
    
    # Layer 2: Exclude language-inappropriate extensions
    if has_excluded_extension(file_path, language):
        return False
    
    # If no rule specified, we've done the universal checks
    if rule_id is None:
        return True
    
    # Layer 3: Skip test files for rules that shouldn't run on tests
    if rule_id in RULES_SKIP_TESTS and is_test_file(file_path):
        return False
    
    # Layer 4: Skip migration files for rules that shouldn't run on migrations
    if rule_id in RULES_SKIP_MIGRATIONS and is_migration_file(file_path):
        return False
    
    # Layer 5: Skip tutorial/docs/example files for security and some other rules
    if rule_id in RULES_SKIP_TUTORIALS and is_tutorial_or_docs_file(file_path):
        return False
    
    # Layer 6: Skip scripts/tooling directories for certain rules
    if rule_id in RULES_SKIP_SCRIPTS and is_scripts_dir(file_path):
        return False
    
    # Layer 7: Check minimum file size if content provided
    if content is not None and rule_id in MIN_LINES_FOR_RULE:
        min_lines = MIN_LINES_FOR_RULE[rule_id]
        line_count = content.count('\n') + 1
        if line_count < min_lines:
            return False
    
    return True


def filter_files(
    files: list[str],
    rule_id: Optional[str] = None,
    language: Optional[str] = None
) -> list[str]:
    """
    Filter a list of files to only those that should be analyzed.
    
    Convenience function for batch filtering.
    
    Args:
        files: List of file paths
        rule_id: Rule ID or None for universal filtering
        language: Language ID or None to auto-detect per file
        
    Returns:
        Filtered list of files that should be analyzed
    """
    return [f for f in files if should_analyze_file(f, rule_id, language)]


def clear_caches():
    """Clear all LRU caches. Useful for testing."""
    is_excluded_path.cache_clear()
    is_test_file.cache_clear()
    is_migration_file.cache_clear()
    is_tutorial_or_docs_file.cache_clear()
    is_scripts_dir.cache_clear()
