/**
 * Tests for KB (Knowledge Base) generation.
 * 
 * These tests verify invariants for the generated KB files:
 * - architecture.md: Guardrails and high-risk zones
 * - map.md: Symbol index with signatures
 * - context.md: Flow and clustering information
 */

// Mocha globals for VS Code test runner
declare function suite(name: string, fn: () => void): void;
declare function test(name: string, fn: () => void): void;

// ============================================================================
// KB Content Invariants
// ============================================================================

/**
 * Invariants that should hold for all generated KB files.
 */
export interface KBInvariants {
  /** All paths should use forward slashes */
  pathsUseForwardSlashes: boolean;
  /** No duplicate entries in lists */
  noDuplicateEntries: boolean;
  /** File stays within line budget */
  withinLineBudget: boolean;
  /** Has required sections */
  hasRequiredSections: boolean;
  /** Timestamps are valid ISO format */
  hasValidTimestamp: boolean;
}

/**
 * Size budget limits for KB files
 */
export const KB_SIZE_LIMITS = {
  architecture: 200,
  map: 300,
  context: 200
} as const;

// ============================================================================
// Validation Functions
// ============================================================================

/**
 * Check if all paths in content use forward slashes
 */
export function validatePathsUseForwardSlashes(content: string): boolean {
  // Match backtick-quoted paths (the way KB files show paths)
  const pathMatches = content.matchAll(/`([^`]+\.(ts|tsx|js|jsx|py|java|cs|go|rs|cpp|c))`/g);
  for (const match of pathMatches) {
    const pathStr = match[1];
    if (pathStr.includes('\\')) {
      return false;
    }
  }
  return true;
}

/**
 * Check for duplicate entries in list items
 */
export function validateNoDuplicateEntries(content: string): { valid: boolean; duplicates: string[] } {
  const listItems: string[] = [];
  const duplicates: string[] = [];
  
  // Extract list items (lines starting with -)
  const lines = content.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed.startsWith('- `')) {
      // Extract the path from the list item
      const match = trimmed.match(/- `([^`]+)`/);
      if (match) {
        const item = match[1];
        if (listItems.includes(item)) {
          duplicates.push(item);
        } else {
          listItems.push(item);
        }
      }
    }
  }
  
  return { valid: duplicates.length === 0, duplicates };
}

/**
 * Check if content is within line budget
 */
export function validateWithinLineBudget(content: string, maxLines: number): { valid: boolean; actualLines: number } {
  const lineCount = content.split('\n').length;
  return { valid: lineCount <= maxLines, actualLines: lineCount };
}

/**
 * Check for required sections in architecture.md
 */
export function validateArchitectureSections(content: string): { valid: boolean; missingSections: string[] } {
  const requiredSections = [
    '# Architecture',
    '## Entry Points',
  ];
  
  const optionalSections = [
    '## ⚠️ High-Risk Architectural Hubs',
    '## Directory Layout',
    '## ⚠️ Circular Dependencies',
  ];
  
  const missingSections = requiredSections.filter(section => !content.includes(section));
  return { valid: missingSections.length === 0, missingSections };
}

/**
 * Check for required sections in map.md
 */
export function validateMapSections(content: string): { valid: boolean; missingSections: string[] } {
  const requiredSections = [
    '# Map',
  ];
  
  const optionalSections = [
    '## Data Models',
    '## Symbol Index',
    '## Conventions',
  ];
  
  const missingSections = requiredSections.filter(section => !content.includes(section));
  return { valid: missingSections.length === 0, missingSections };
}

/**
 * Check for required sections in context.md
 */
export function validateContextSections(content: string): { valid: boolean; missingSections: string[] } {
  const requiredSections = [
    '# Context',
  ];
  
  const optionalSections = [
    '## Module Clusters',
    '## Critical Flows',
    '## Dependency Chains',
    '## Quick Reference',
  ];
  
  const missingSections = requiredSections.filter(section => !content.includes(section));
  return { valid: missingSections.length === 0, missingSections };
}

/**
 * Check for valid ISO timestamp at end of file
 */
export function validateTimestamp(content: string): boolean {
  const timestampPattern = /_Generated: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;
  return timestampPattern.test(content);
}

/**
 * Run all invariant checks on a KB file
 */
export function validateKBFile(
  content: string, 
  fileType: 'architecture' | 'map' | 'context'
): KBInvariants & { errors: string[] } {
  const errors: string[] = [];
  
  const pathsValid = validatePathsUseForwardSlashes(content);
  if (!pathsValid) {
    errors.push('Found paths with backslashes - should use forward slashes');
  }
  
  const dupeCheck = validateNoDuplicateEntries(content);
  if (!dupeCheck.valid) {
    errors.push(`Found duplicate entries: ${dupeCheck.duplicates.join(', ')}`);
  }
  
  const budgetCheck = validateWithinLineBudget(content, KB_SIZE_LIMITS[fileType]);
  if (!budgetCheck.valid) {
    errors.push(`Exceeds line budget: ${budgetCheck.actualLines} > ${KB_SIZE_LIMITS[fileType]}`);
  }
  
  let sectionsCheck: { valid: boolean; missingSections: string[] };
  switch (fileType) {
    case 'architecture':
      sectionsCheck = validateArchitectureSections(content);
      break;
    case 'map':
      sectionsCheck = validateMapSections(content);
      break;
    case 'context':
      sectionsCheck = validateContextSections(content);
      break;
  }
  if (!sectionsCheck.valid) {
    errors.push(`Missing required sections: ${sectionsCheck.missingSections.join(', ')}`);
  }
  
  const timestampValid = validateTimestamp(content);
  if (!timestampValid) {
    errors.push('Missing or invalid timestamp');
  }
  
  return {
    pathsUseForwardSlashes: pathsValid,
    noDuplicateEntries: dupeCheck.valid,
    withinLineBudget: budgetCheck.valid,
    hasRequiredSections: sectionsCheck.valid,
    hasValidTimestamp: timestampValid,
    errors
  };
}

// ============================================================================
// Test Suite (for VS Code extension testing)
// ============================================================================

suite('KB Generation Invariants', () => {
  
  test('validatePathsUseForwardSlashes detects backslashes', () => {
    const contentWithBackslash = '- `src\\utils\\helper.ts`\n- `app/main.py`';
    const contentWithForwardSlash = '- `src/utils/helper.ts`\n- `app/main.py`';
    
    if (validatePathsUseForwardSlashes(contentWithBackslash)) {
      throw new Error('Should detect backslash paths as invalid');
    }
    if (!validatePathsUseForwardSlashes(contentWithForwardSlash)) {
      throw new Error('Should accept forward slash paths as valid');
    }
  });
  
  test('validateNoDuplicateEntries detects duplicates', () => {
    const contentWithDupes = '- `src/main.ts`\n- `src/utils.ts`\n- `src/main.ts`';
    const contentNoDupes = '- `src/main.ts`\n- `src/utils.ts`\n- `src/app.ts`';
    
    const dupeResult = validateNoDuplicateEntries(contentWithDupes);
    if (dupeResult.valid) {
      throw new Error('Should detect duplicate entries');
    }
    if (!dupeResult.duplicates.includes('src/main.ts')) {
      throw new Error('Should identify the duplicate path');
    }
    
    const noDupeResult = validateNoDuplicateEntries(contentNoDupes);
    if (!noDupeResult.valid) {
      throw new Error('Should accept unique entries as valid');
    }
  });
  
  test('validateWithinLineBudget checks line count', () => {
    const shortContent = 'Line 1\nLine 2\nLine 3';
    const longContent = Array(250).fill('Line').join('\n');
    
    const shortResult = validateWithinLineBudget(shortContent, 200);
    if (!shortResult.valid) {
      throw new Error('Short content should be within budget');
    }
    
    const longResult = validateWithinLineBudget(longContent, 200);
    if (longResult.valid) {
      throw new Error('Long content should exceed budget');
    }
    if (longResult.actualLines !== 250) {
      throw new Error(`Expected 250 lines, got ${longResult.actualLines}`);
    }
  });
  
  test('validateTimestamp checks ISO format', () => {
    const validContent = 'Some content\n\n_Generated: 2024-01-15T10:30:45.123Z_\n';
    const invalidContent = 'Some content\n\nGenerated: Jan 15 2024\n';
    
    if (!validateTimestamp(validContent)) {
      throw new Error('Should accept valid ISO timestamp');
    }
    if (validateTimestamp(invalidContent)) {
      throw new Error('Should reject non-ISO timestamp');
    }
  });
  
  test('validateArchitectureSections checks required sections', () => {
    const validContent = '# Architecture\n\nSome intro.\n\n## Entry Points\n\nEntry point list.';
    const invalidContent = '# Architecture\n\nSome intro.\n\n## Directory Layout\n\nDirs.';
    
    const validResult = validateArchitectureSections(validContent);
    if (!validResult.valid) {
      throw new Error(`Should accept valid architecture: missing ${validResult.missingSections.join(', ')}`);
    }
    
    const invalidResult = validateArchitectureSections(invalidContent);
    if (invalidResult.valid) {
      throw new Error('Should detect missing Entry Points section');
    }
  });
  
});

// ============================================================================
// Sample Golden File Content (for reference)
// ============================================================================

export const SAMPLE_ARCHITECTURE_MD = `# Architecture

_Read this first. Describes the project layout and "Do Not Break" zones._

**Files:** 42 | **Dependencies:** 156 | **Cycles:** 0

## ⚠️ High-Risk Architectural Hubs

> **These files are architectural load-bearing walls.**
> Modify with extreme caution. Do not change signatures without checking \`map.md\`.

| Rank | File | Imports | Imported By | Issues | Risk |
|------|------|---------|-------------|--------|------|
| 1 | \`src/core/engine.ts\` | 8 | 12 | 2 | 🔴 High |
| 2 | \`src/utils/helpers.ts\` | 2 | 8 | 0 | 🟡 Medium |

### Hub Details & Blast Radius

_Blast radius = files that would be affected if this hub breaks._

**1. \`src/core/engine.ts\`** — Blast radius: 18 files
   - Direct dependents: 12
   - Indirect dependents: ~6

   Imported by:
   - \`src/commands/run.ts\`
   - \`src/commands/scan.ts\`
   - \`src/api/handler.ts\`

## Entry Points

_Where requests enter the system. Confidence indicates detection reliability._

**API Routes** (5 endpoints) — 🟢 High confidence
- \`src/api/routes.ts\`: GET /api/status
- \`src/api/routes.ts\`: POST /api/scan

**Application Entry:**
- \`src/main.ts\`: Entry point (main) — 🟢 High

## Directory Layout

| Directory | Files | Purpose |
|-----------|-------|---------|
| \`src/\` | 15 | Source code |
| \`src/commands/\` | 5 | CLI commands |
| \`src/utils/\` | 8 | Utilities |

_Generated: 2024-01-15T10:30:45.123Z_
`;

export const SAMPLE_MAP_MD = `# Map

_Symbol index with signatures and conventions. Use to find types, functions, and coding patterns._

## Data Models

_Core data structures. Check these before modifying data handling._

### TypeScript Interfaces & Types

**\`src/types/config.ts\`**: \`interface Config { apiKey: string; timeout: number; ... }\`

**\`src/types/result.ts\`**: \`interface ScanResult { findings: Finding[]; metrics: Metrics }\`

## Symbol Index

_Functions, classes, and exports with call relationships._

### \`src/core/engine.ts\`

| Symbol | Kind | Signature | Used In (files) |
|--------|------|-----------|-----------------|
| \`Engine\` | class | \`class Engine\` | \`run.ts\`, \`scan.ts\` |
| \`scan\` | function | \`function scan(path)\` | \`handler.ts\` |

---

## Conventions

_Naming patterns and styles. Follow these for consistency._

### File Naming

| Pattern | Example | Count |
|---------|---------|-------|
| kebab-case | \`scan-result.ts\` | 12 |

**Use:** kebab-case for new files.

_Generated: 2024-01-15T10:30:45.123Z_
`;

export const SAMPLE_CONTEXT_MD = `# Context

_Data flow and co-location context. Use to understand which files work together._

## Module Clusters

_Files commonly imported together. Editing one likely requires editing the others._

### commands

_Co-imported by: \`src/cli.ts\`, \`src/main.ts\` and others_

- \`src/commands/run.ts\`
- \`src/commands/scan.ts\`
- \`src/commands/help.ts\`

## Critical Flows

_Most central modules by connectivity. Changes here propagate widely._

| Module | Callers | Dependencies |
|--------|---------|--------------|
| \`src/core/engine.ts\` | 12 | 8 |
| \`src/utils/helpers.ts\` | 8 | 2 |

## Dependency Chains

_Top data/call flow paths. Shows how changes propagate through the codebase._

**Chain 1** (4 modules):
\`\`\`
src/main.ts → src/commands/run.ts → src/core/engine.ts → src/utils/helpers.ts
\`\`\`

---

## Quick Reference

**"What files work together for feature X?"**
→ Check Module Clusters above.

**"Where does data flow from this endpoint?"**
→ Check Critical Flows and Dependency Chains.

**"Where are external connections?"**
→ Check External Integrations.


_Generated: 2024-01-15T10:30:45.123Z_
`;

// ============================================================================
// Additional Invariant Validation Functions
// ============================================================================

/**
 * Validate that "Used In (files)" entries are actual file paths with extensions.
 * Should not be bare identifiers like "deps", "env", "login".
 */
export function validateUsedInAreFilePaths(content: string): { valid: boolean; issues: string[] } {
  const issues: string[] = [];
  
  // Find all "Used In (files)" column values in tables
  const tableRows = content.match(/\|[^|]+\|[^|]+\|[^|]+\|[^|]+\|$/gm) || [];
  
  for (const row of tableRows) {
    // Skip header and separator rows
    if (row.includes('Symbol') || row.includes('---')) continue;
    
    // Get the last column (Used In)
    const columns = row.split('|').filter(c => c.trim());
    if (columns.length < 4) continue;
    
    const usedInCell = columns[3].trim();
    if (usedInCell === '—' || usedInCell === '') continue;
    
    // Check each file reference in the cell
    const fileRefs = usedInCell.split(',').map(f => f.trim().replace(/`/g, ''));
    for (const ref of fileRefs) {
      // Skip the (+N more) indicator
      if (ref.match(/^\(\+\d+ more\)$/)) continue;
      
      // File paths should have extensions or be relative paths
      const hasExtension = /\.\w{1,4}$/.test(ref);
      const isPath = ref.includes('/');
      
      if (!hasExtension && !isPath && ref.length > 0) {
        // Bare identifier without extension - likely wrong
        issues.push(`Bare identifier in Used In: "${ref}" - should be a file path`);
      }
    }
  }
  
  return { valid: issues.length === 0, issues };
}

/**
 * Validate hub metrics consistency:
 * - Blast radius = direct + indirect
 * - Imported By count matches list length
 */
export function validateHubMetrics(content: string): { valid: boolean; issues: string[] } {
  const issues: string[] = [];
  
  // Find hub details sections
  const hubDetailsPattern = /\*\*\d+\.\s+`([^`]+)`\*\*\s+—\s+Blast radius:\s+(\d+)\s+files\n\s+- Direct dependents:\s+(\d+)\n\s+- Indirect dependents:\s+~(\d+)/g;
  
  let match;
  while ((match = hubDetailsPattern.exec(content)) !== null) {
    const [, filePath, blastRadius, directCount, indirectCount] = match;
    const expectedBlast = parseInt(directCount) + parseInt(indirectCount);
    const actualBlast = parseInt(blastRadius);
    
    if (expectedBlast !== actualBlast) {
      issues.push(`Hub ${filePath}: Blast radius ${actualBlast} != direct(${directCount}) + indirect(${indirectCount}) = ${expectedBlast}`);
    }
  }
  
  // Check "Imported by (N files)" matches actual list
  const importedByPattern = /Imported by \((\d+) files\):\n((?:\s+- `[^`]+`\n)+)/g;
  
  while ((match = importedByPattern.exec(content)) !== null) {
    const [, countStr, listBlock] = match;
    const declaredCount = parseInt(countStr);
    const listItems = (listBlock.match(/- `[^`]+`/g) || []).length;
    const hasMore = listBlock.includes('...and');
    
    // If there's a "...and X more", the list should be truncated
    if (!hasMore && listItems !== declaredCount && listItems > 0) {
      issues.push(`Imported by count (${declaredCount}) doesn't match list length (${listItems})`);
    }
  }
  
  return { valid: issues.length === 0, issues };
}

/**
 * Validate entry points have confidence indicators and proper categorization.
 */
export function validateEntryPointStructure(content: string): { valid: boolean; issues: string[] } {
  const issues: string[] = [];
  
  // Check that Entry Points section exists and has proper subsections
  if (!content.includes('## Entry Points')) {
    issues.push('Missing "## Entry Points" section');
    return { valid: false, issues };
  }
  
  // Check for confidence indicators
  const entryPointSection = content.split('## Entry Points')[1]?.split('##')[0] || '';
  const hasConfidenceIcons = entryPointSection.includes('🟢') || 
                              entryPointSection.includes('🟡') || 
                              entryPointSection.includes('🟠');
  
  if (!hasConfidenceIcons && entryPointSection.includes('-')) {
    issues.push('Entry points should have confidence indicators (🟢/🟡/🟠)');
  }
  
  return { valid: issues.length === 0, issues };
}

/**
 * Validate cluster names are unique (no duplicates without disambiguation).
 */
export function validateClusterNamesUnique(content: string): { valid: boolean; duplicates: string[] } {
  const duplicates: string[] = [];
  
  // Find all cluster headers in context.md
  const clusterHeaders = content.match(/^###\s+([^\n]+)$/gm) || [];
  const clusterNames = clusterHeaders.map(h => h.replace('### ', '').trim());
  
  const seen = new Set<string>();
  for (const name of clusterNames) {
    if (seen.has(name)) {
      duplicates.push(name);
    }
    seen.add(name);
  }
  
  return { valid: duplicates.length === 0, duplicates };
}

// ============================================================================
// Extended Test Suite
// ============================================================================

suite('KB Generation Extended Invariants', () => {
  
  test('validateUsedInAreFilePaths detects bare identifiers', () => {
    const badContent = `
| Symbol | Kind | Signature | Used In (files) |
|--------|------|-----------|-----------------|
| \`foo\` | function | \`fn foo()\` | \`deps\`, \`env\` |
`;
    const goodContent = `
| Symbol | Kind | Signature | Used In (files) |
|--------|------|-----------|-----------------|
| \`foo\` | function | \`fn foo()\` | \`services/auth.ts\`, \`main.ts\` |
`;
    
    const badResult = validateUsedInAreFilePaths(badContent);
    if (badResult.valid) {
      throw new Error('Should detect bare identifiers as invalid');
    }
    
    const goodResult = validateUsedInAreFilePaths(goodContent);
    if (!goodResult.valid) {
      throw new Error(`Should accept file paths: ${goodResult.issues.join(', ')}`);
    }
  });
  
  test('validateHubMetrics checks blast radius math', () => {
    const validContent = `
**1. \`src/core.ts\`** — Blast radius: 15 files
   - Direct dependents: 10
   - Indirect dependents: ~5
`;
    const invalidContent = `
**1. \`src/core.ts\`** — Blast radius: 20 files
   - Direct dependents: 10
   - Indirect dependents: ~5
`;
    
    const validResult = validateHubMetrics(validContent);
    if (!validResult.valid) {
      throw new Error(`Should accept correct blast radius: ${validResult.issues.join(', ')}`);
    }
    
    const invalidResult = validateHubMetrics(invalidContent);
    if (invalidResult.valid) {
      throw new Error('Should detect incorrect blast radius math');
    }
  });
  
  test('validateClusterNamesUnique detects duplicate cluster names', () => {
    const duplicateContent = `
### Auth
Some files

### Core
More files

### Auth
Duplicate name
`;
    const uniqueContent = `
### Auth (api)
Some files

### Auth (web)
More files

### Core
Other files
`;
    
    const dupeResult = validateClusterNamesUnique(duplicateContent);
    if (dupeResult.valid) {
      throw new Error('Should detect duplicate cluster names');
    }
    
    const uniqueResult = validateClusterNamesUnique(uniqueContent);
    if (!uniqueResult.valid) {
      throw new Error(`Should accept unique names: ${uniqueResult.duplicates.join(', ')}`);
    }
  });
  
});
