/**
 * Auto-Fix v1 Configuration
 * 
 * Constants and configuration for the Auto-Fix v1 pipeline.
 * This must stay in sync with server/engine/profiles.py AUTO_FIX_V1_RULE_IDS.
 */

/**
 * Auto-Fix v1 rule IDs - safe subset of alpha rules for automatic fixing.
 * 
 * These rules have been validated as safe for automatic application:
 * 1. autofix_safety="safe" in rule metadata
 * 2. Support Python, TypeScript, or JavaScript 
 * 3. Fixes are idempotent and undoable
 * 4. No semantic changes that could break functionality
 * 
 * NOTE: Temporarily restricted to the most obviously safe rules until manual audit complete.
 */
export const AUTO_FIX_V1_RULE_IDS = new Set([
    // Style fixes - completely safe
    "style.trailing_whitespace",     // Safe whitespace cleanup
    "style.missing_newline_eof",     // Safe EOF formatting
    "style.mixed_indentation",       // Safe formatting fix
    
    // Import cleanup - very safe
    "imports.unused",                // Safe import cleanup
    "deadcode.duplicate_import",     // Safe import deduplication
    "deadcode.unused_variable",      // Safe variable cleanup (when obvious)
    
    // TEMPORARILY REMOVED (pending manual audit):
    // "bug.assignment_in_conditional", // Could change logic behavior
    // "bug.python_is_vs_eq",           // Could change logic behavior  
    // "deadcode.redundant_condition",  // Could change logic behavior
    // "lang.ts_loose_equality",        // Could change behavior in edge cases
]);

/**
 * Check if a rule ID is eligible for Auto-Fix v1.
 */
export function isAutoFixV1Rule(ruleId: string): boolean {
    return AUTO_FIX_V1_RULE_IDS.has(ruleId);
}

/**
 * Check if a finding is eligible for Auto-Fix v1.
 */
export function isAutoFixV1Finding(finding: { rule_id: string; autofix?: any[] }): boolean {
    return !!(finding.autofix && 
              finding.autofix.length > 0 && 
              isAutoFixV1Rule(finding.rule_id));
}

/**
 * Auto-Fix v1 backend API interface.
 */
export interface AutofixRequest {
    repo_root: string;
    rule_id?: string;
    finding_id?: string; 
    file_path?: string;
    start_byte?: number;
    end_byte?: number;
    max_fixes?: number;
}

export interface AutofixResponse {
    fixes_applied: number;
    files_changed: number;
    took_ms: number;
    patched_diff?: string;
    files?: Array<{
        relpath: string;
        content: string;
    }>;
    skipped?: Array<{
        finding_id: string;
        reason: string;
    }>;
}