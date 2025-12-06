/**
 * Aspect Code Asymptotic Code Quality Score Configuration
 * 
 * This file contains the asymptotic scoring system where the first finding in each category
 * has higher impact than subsequent findings (diminishing returns).
 * 
 * Asymptotic Formula:
 * impact = maxImpact * (1 - e^(-steepness * weightedFindings))
 * 
 * Category weight system:
 * - Each category has a percentage weight of the total score
 * - Security: 25%, Reliability: 20%, Architecture: 15%, etc.
 * - The first security finding is weighted more than the second, third, etc.
 * 
 * Alpha Default Profile (28 enabled rules):
 * - Security: 6 rules (sec.*, security.*)
 * - Architecture: 4 rules (arch.*, architecture.*, analysis.*)  [includes Tier 2]
 * - Reliability/Bugs: 2 rules (bug.float_equality, bug.iteration_modification, bug.boolean_bitwise_misuse)
 *   [Disabled: bug.incompatible_comparison, bug.recursion_no_base_case - false positives]
 * - Error Handling: 3 rules (errors.*)
 * - Concurrency: 2 rules (concurrency.*)
 * - Complexity: 2 rules (complexity.*)
 * - Deadcode: 2 rules (deadcode.*)
 * - Identifiers: 1 rule (ident.duplicate_definition)
 *   [Disabled: ident.shadowing - too noisy on 'id' in data models]
 * - Imports: 2 rules (imports.*)
 * - Testing: 1 rule (test.flaky_sleep)
 *   [Disabled: test.no_assertions - false positives on fixture tests]
 * - Naming: 1 rule (naming.*) [KB-only]
 * - Style: 1 rule (style.*)
 */

export interface ScoreConfig {
  // Asymptotic function parameters
  asymptoteFunctions: {
    [key: string]: {
      maxImpact: number;    // Maximum impact this category can have
      steepness: number;    // How quickly diminishing returns kick in (higher = faster)
    };
  };
  
  // Category percentage weights (should sum to 100%)
  categoryWeights: {
    security: number;
    architecture: number;    // Tier 2 architectural rules included here
    reliability: number;
    errorHandling: number;
    concurrency: number;
    complexity: number;
    deadcode: number;
    identifiers: number;
    imports: number;
    testing: number;
    naming: number;
    style: number;
  };
  
  // Severity multipliers for findings within categories
  severityWeights: {
    critical: number;
    high: number;
    medium: number;
    low: number;
    info: number;
  };
  
  // File type impact (multipliers based on file importance)
  fileTypeWeights: {
    core: number;        // Main application files
    config: number;      // Configuration files
    test: number;        // Test files
    documentation: number; // Docs, README, etc.
    build: number;       // Build/deployment files
    other: number;       // Other files
  };
  
  // Base scoring parameters (kept for compatibility)
  baseScore: number;
  
  // Concentration penalties (when many findings are in few files)
  concentrationPenalty: {
    enabled: boolean;
    threshold: number;   // Findings per file threshold
    multiplier: number;  // Additional penalty multiplier
  };
  
  // Volume penalties (total number of findings)
  volumePenalties: {
    thresholds: number[];  // Finding count thresholds
    multipliers: number[]; // Penalty multipliers for each threshold
  };
  
  // Sub-scores (informational, not included in main score)
  subScores: {
    complexity: {
      enabled: boolean;
      cyclomaticThreshold: number;
      cognitiveThreshold: number;
      fileCountThreshold: number;
    };
    coverage: {
      enabled: boolean;
      testFileRatio: number; // Expected ratio of test files to source files
    };
    documentation: {
      enabled: boolean;
      readmeWeight: number;
      commentDensity: number;
    };
  };
}

export const defaultScoreConfig: ScoreConfig = {
  baseScore: 100,
  
  // Asymptotic function parameters for each category
  // Steepness tuned based on number of rules in each category:
  // - Categories with fewer rules get gentler curves (more impact per finding)
  // - Categories with more rules get steeper curves (faster diminishing returns)
  asymptoteFunctions: {
    security: {
      maxImpact: 100,     // 6 rules - moderate steepness
      steepness: 0.020    // ~86% impact at 100 weighted findings
    },
    architecture: {
      maxImpact: 100,     // 4 rules (includes Tier 2) - gentler curve
      steepness: 0.025    // Each finding matters more with fewer rules
    },
    reliability: {
      maxImpact: 100,     // 5 rules - moderate steepness  
      steepness: 0.022    // ~89% impact at 100 weighted findings
    },
    errorHandling: {
      maxImpact: 100,     // 3 rules - gentler curve
      steepness: 0.028    // Each finding matters more
    },
    concurrency: {
      maxImpact: 100,     // 2 rules - gentle curve (high impact per finding)
      steepness: 0.035    // Critical issues, few rules
    },
    complexity: {
      maxImpact: 100,     // 2 rules - moderate
      steepness: 0.030    // Complexity findings add up quickly
    },
    deadcode: {
      maxImpact: 100,     // 2 rules - gentle
      steepness: 0.015    // Deadcode is lower impact per finding
    },
    identifiers: {
      maxImpact: 100,     // 2 rules - moderate
      steepness: 0.025    // Shadowing/duplicates are meaningful
    },
    imports: {
      maxImpact: 100,     // 2 rules - gentle
      steepness: 0.012    // Import issues are common, lower impact each
    },
    testing: {
      maxImpact: 100,     // 2 rules - moderate
      steepness: 0.020    // Test quality matters
    },
    naming: {
      maxImpact: 100,     // 1 rule - gentle
      steepness: 0.010    // Naming issues are common
    },
    style: {
      maxImpact: 100,     // 1 rule - very gentle
      steepness: 0.005    // Style issues have lowest per-finding impact
    }
  },
  
  // Category percentage weights (MUST sum to exactly 100%)
  // Weights reflect severity and importance to production quality
  categoryWeights: {
    security: 25,        // Security is highest priority (6 rules)
    architecture: 15,    // Architecture/Tier 2 rules (4 rules, critical for large codebases)
    reliability: 15,     // Bug prevention (5 rules)
    errorHandling: 10,   // Error handling quality (3 rules)
    concurrency: 8,      // Concurrency issues are critical but rare (2 rules)
    complexity: 7,       // Code complexity (2 rules)
    deadcode: 5,         // Dead code cleanup (2 rules)
    identifiers: 5,      // Identifier issues (2 rules)
    imports: 4,          // Import issues (2 rules)
    testing: 3,          // Test quality (2 rules)
    naming: 2,           // Naming consistency (1 rule)
    style: 1             // Style issues (1 rule)
  },
  
  // Severity multipliers for findings within categories
  // Higher severity = more weight in the asymptotic formula
  severityWeights: {
    critical: 4.0,   // Critical findings have 4x weight (security vulns, crashes)
    high: 2.5,       // High findings have 2.5x weight (bugs, concurrency)
    medium: 1.0,     // Medium findings have base weight
    low: 0.4,        // Low findings have reduced weight
    info: 0.1        // Info findings have minimal weight
  },
  
  // File type importance multipliers
  fileTypeWeights: {
    core: 1.0,         // Main application files (normal weight)
    config: 1.5,       // Config files more important (security secrets, etc.)
    test: 0.5,         // Test files less critical for production
    documentation: 0.2, // Docs less critical for production
    build: 1.3,        // Build files moderately important (CI/CD)
    other: 0.7         // Other files slightly less important
  },
  
  // Concentration penalty (when issues cluster in few files) - More forgiving
  concentrationPenalty: {
    enabled: true,
    threshold: 15,     // More than 15 findings per file triggers penalty
    multiplier: 1.2    // 20% additional penalty (reduced from 30%)
  },
  
  // Volume penalties (more findings = worse, but gradual)
  volumePenalties: {
    thresholds: [20, 50, 100, 200, 400],
    multipliers: [1.0, 1.1, 1.25, 1.5, 2.0, 2.5] // Gradual escalation
  },
  
  // Sub-scores for detailed analysis
  subScores: {
    complexity: {
      enabled: true,
      cyclomaticThreshold: 10,
      cognitiveThreshold: 15,
      fileCountThreshold: 100
    },
    coverage: {
      enabled: true,
      testFileRatio: 0.3 // Expect at least 30% test files
    },
    documentation: {
      enabled: true,
      readmeWeight: 5.0,
      commentDensity: 0.15 // Expect 15% comment density
    }
  }
};

/**
 * Rule to category mapping
 * Maps rule names/patterns to their categories for asymptotic scoring
 * 
 * Alpha Default Profile (32 rules) mapped to 12 scoring categories:
 * - security: sec.*, security.* (6 rules)
 * - architecture: arch.*, architecture.*, analysis.* (4 rules, includes Tier 2)
 * - reliability: bug.* (5 rules)
 * - errorHandling: errors.* (3 rules)
 * - concurrency: concurrency.* (2 rules)
 * - complexity: complexity.* (2 rules)
 * - deadcode: deadcode.* (2 rules)
 * - identifiers: ident.* (2 rules)
 * - imports: imports.* (2 rules)
 * - testing: test.* (2 rules)
 * - naming: naming.* (1 rule)
 * - style: style.* (1 rule)
 */
export const ruleCategoryMap: { [key: string]: keyof ScoreConfig['categoryWeights'] } = {
  // === Security (6 rules in alpha_default) ===
  // sec.sql_injection_concat, sec.hardcoded_secret, sec.path_traversal,
  // sec.open_redirect, sec.insecure_random, security.jwt_without_exp
  'sec.': 'security',
  'security.': 'security',
  'sql_injection': 'security',
  'hardcoded_secret': 'security',
  'path_traversal': 'security',
  'open_redirect': 'security',
  'insecure_random': 'security',
  'jwt_without_exp': 'security',
  'command_injection': 'security',
  'xss': 'security',
  'csrf': 'security',
  'auth': 'security',
  'crypto': 'security',
  
  // === Architecture (4 rules in alpha_default - includes Tier 2) ===
  // arch.global_state_usage, analysis.change_impact,
  // architecture.dependency_cycle_impact, architecture.critical_dependency
  'arch.': 'architecture',
  'architecture.': 'architecture',
  'analysis.': 'architecture',
  'global_state_usage': 'architecture',
  'change_impact': 'architecture',
  'dependency_cycle_impact': 'architecture',
  'critical_dependency': 'architecture',
  
  // === Reliability / Bugs (3 rules in alpha_default) ===
  // bug.float_equality, bug.iteration_modification, bug.boolean_bitwise_misuse
  // [Disabled: bug.incompatible_comparison, bug.recursion_no_base_case]
  'bug.': 'reliability',
  'incompatible_comparison': 'reliability',
  'float_equality': 'reliability',
  'iteration_modification': 'reliability',
  'boolean_bitwise_misuse': 'reliability',
  'recursion_no_base_case': 'reliability',
  'operator_precedence': 'reliability',
  'null': 'reliability',
  'undefined': 'reliability',
  'crash': 'reliability',
  
  // === Error Handling (3 rules in alpha_default) ===
  // errors.swallowed_exception, errors.broad_catch, errors.partial_function_implementation
  'errors.': 'errorHandling',
  'swallowed_exception': 'errorHandling',
  'broad_catch': 'errorHandling',
  'partial_function_implementation': 'errorHandling',
  'exception': 'errorHandling',
  
  // === Concurrency (2 rules in alpha_default) ===
  // concurrency.lock_not_released, concurrency.blocking_in_async
  'concurrency.': 'concurrency',
  'lock_not_released': 'concurrency',
  'blocking_in_async': 'concurrency',
  'race': 'concurrency',
  'async': 'concurrency',
  
  // === Complexity (2 rules in alpha_default) ===
  // complexity.high_cyclomatic, complexity.long_function
  'complexity.': 'complexity',
  'high_cyclomatic': 'complexity',
  'long_function': 'complexity',
  'cognitive': 'complexity',
  
  // === Deadcode (2 rules in alpha_default) ===
  // deadcode.unused_variable, deadcode.unused_public
  'deadcode.': 'deadcode',
  'unused_variable': 'deadcode',
  'unused_public': 'deadcode',
  'unreachable': 'deadcode',
  
  // === Identifiers (1 rule in alpha_default) ===
  // ident.duplicate_definition [Disabled: ident.shadowing]
  'ident.': 'identifiers',
  'shadowing': 'identifiers',
  'duplicate_definition': 'identifiers',
  
  // === Imports (2 rules in alpha_default) ===
  // imports.cycle, imports.unused
  'imports.': 'imports',
  'import_cycle': 'imports',
  'unused_import': 'imports',
  'duplicate_import': 'imports',
  
  // === Testing (1 rule in alpha_default) ===
  // test.flaky_sleep [Disabled: test.no_assertions]
  'test.': 'testing',
  'flaky_sleep': 'testing',
  'no_assertions': 'testing',
  'mock': 'testing',
  'coverage': 'testing',
  
  // === Naming (1 rule in alpha_default) ===
  // naming.project_term_inconsistency
  'naming.': 'naming',
  'project_term_inconsistency': 'naming',
  
  // === Style (1 rule in alpha_default) ===
  // style.mixed_indentation
  'style.': 'style',
  'mixed_indentation': 'style',
  'trailing_whitespace': 'style',
  'missing_newline_eof': 'style',
  'inconsistent_quotes': 'style',
  'format': 'style',
  'lint': 'style',
  'whitespace': 'style',
  'indent': 'style',
  
  // === Legacy mappings (for backward compatibility) ===
  // Types/TypeScript patterns -> map to complexity
  'types.': 'complexity',
  'ts_any_overuse': 'complexity',
  'ts_narrowing_missing': 'complexity',
  'ts_nullable_unchecked': 'complexity',
  'ts_loose_equality': 'complexity',
  'lang.': 'complexity',
  'loose_equality': 'complexity',
  
  // Performance patterns -> map to complexity (no perf rules in alpha_default)
  'perf.': 'complexity',
  'performance': 'complexity',
  'memory': 'security',  // Memory issues are security-related
  'cpu': 'complexity',
  'cache': 'complexity',
  
  // Documentation -> map to style (no doc rules in alpha_default)
  'doc': 'style',
  'comment': 'style',
  'readme': 'style',
  'todo': 'style',
  'todo_comment': 'style'
};

/**
 * File type classification patterns
 */
export const fileTypePatterns = {
  core: [
    /\.(js|ts|jsx|tsx|py|java|cpp|c|cs|php|rb|go|rs)$/i,
    /src\/.*\.(js|ts|jsx|tsx|py)$/i,
    /lib\/.*\.(js|ts|jsx|tsx|py)$/i
  ],
  config: [
    /\.(json|yaml|yml|toml|ini|conf|config)$/i,
    /package\.json$/i,
    /tsconfig\.json$/i,
    /\.env/i,
    /webpack\.config\./i,
    /babel\.config\./i
  ],
  test: [
    /\.(test|spec)\./i,
    /test\/.*\./i,
    /tests\/.*\./i,
    /__tests__\/.*\./i,
    /\.test\./i,
    /\.spec\./i
  ],
  documentation: [
    /\.(md|txt|rst|adoc)$/i,
    /README/i,
    /CHANGELOG/i,
    /LICENSE/i,
    /docs?\//i
  ],
  build: [
    /Dockerfile/i,
    /docker-compose/i,
    /Makefile/i,
    /\.github\//i,
    /\.gitlab/i,
    /build\//i,
    /dist\//i
  ]
};
