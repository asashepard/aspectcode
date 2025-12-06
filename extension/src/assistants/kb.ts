import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';

/**
 * Ensures .aspect/ is added to .gitignore.
 * If .gitignore doesn't exist, prompts the user to create one.
 */
async function ensureGitignore(workspaceRoot: vscode.Uri, outputChannel: vscode.OutputChannel): Promise<void> {
  const gitignorePath = vscode.Uri.joinPath(workspaceRoot, '.gitignore');
  const aspectEntry = '.aspect/';
  
  try {
    // Try to read existing .gitignore
    const content = await vscode.workspace.fs.readFile(gitignorePath);
    const text = Buffer.from(content).toString('utf8');
    
    // Check if .aspect/ is already in .gitignore
    const lines = text.split(/\r?\n/);
    const hasAspect = lines.some(line => {
      const trimmed = line.trim();
      return trimmed === '.aspect/' || trimmed === '.aspect' || trimmed === '/.aspect/' || trimmed === '/.aspect';
    });
    
    if (!hasAspect) {
      // Add .aspect/ to .gitignore, preserving existing content
      const newContent = text.endsWith('\n') 
        ? text + aspectEntry + '\n'
        : text + '\n' + aspectEntry + '\n';
      
      await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
      outputChannel.appendLine('[KB] Added .aspect/ to .gitignore');
    }
  } catch (error) {
    // .gitignore doesn't exist - prompt the user
    const action = await vscode.window.showInformationMessage(
      'No .gitignore found. Create one with .aspect/ excluded?',
      'Create .gitignore',
      'Dismiss'
    );
    
    if (action === 'Create .gitignore') {
      const defaultContent = `# Aspect Code knowledge base (auto-generated)
${aspectEntry}
`;
      await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(defaultContent, 'utf8'));
      outputChannel.appendLine('[KB] Created .gitignore with .aspect/ excluded');
    } else {
      outputChannel.appendLine('[KB] Warning: .aspect/ not added to .gitignore');
    }
  }
}

/**
 * Aspect Code Knowledge Base v2 - Architectural Intelligence for AI Coding Agents
 * 
 * STRUCTURE (5 files):
 * - structure.md: Directory layout + dependency graph + hubs + cycles
 * - awareness.md: Contextual guidance on high-impact areas + risk zones
 * - code.md: Symbol index with call relationships and exports
 * - flows.md: Data flows and request paths through the codebase
 * - conventions.md: Naming patterns, import styles, framework idioms
 * 
 * Design philosophy: Provide structural intelligence, not just issue lists.
 * Guide agents toward understanding architecture and making informed changes.
 * Issues are supplementary context, not the primary focus.
 * 
 * KB-Enriching Rules:
 * - arch.entry_point: HTTP handlers, CLI commands, main functions, event listeners
 * - arch.external_integration: HTTP clients, DB connections, message queues, SDKs
 * - arch.data_model: ORM models, dataclasses, interfaces, schemas
 */

// KB-enriching rule IDs
const KB_ENRICHING_RULES = {
  ENTRY_POINT: 'arch.entry_point',
  EXTERNAL_INTEGRATION: 'arch.external_integration',
  DATA_MODEL: 'arch.data_model',
};

interface KBEnrichingFinding {
  file: string;
  message: string;
  meta?: Record<string, unknown>;
}

/**
 * Extract KB-enriching findings by rule type.
 * These findings provide architectural intelligence rather than issue reports.
 */
function extractKBEnrichingFindings(
  state: AspectCodeState,
  ruleId: string
): KBEnrichingFinding[] {
  return state.s.findings
    .filter(f => f.code === ruleId)
    .map(f => ({
      file: f.file,
      message: f.message,
      meta: f.meta || {},
    }));
}

/**
 * Automatically regenerate KB files when findings change.
 * Called after incremental validation or full validation.
 */
export async function autoRegenerateKBFiles(
  state: AspectCodeState,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    return;
  }

  const workspaceRoot = workspaceFolders[0].uri;
  
  try {
    // Calculate score from current findings
    const findings = state.s.findings;
    let scoreResult: ScoreResult | null = null;

    if (findings.length > 0) {
      const { AsymptoticScoreEngine } = await import('../scoring/scoreEngine');
      const scoreEngine = new AsymptoticScoreEngine();
      
      // Convert state findings to scoring format
      const scoringFindings = findings.map(f => {
        let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';
        if (f.severity === 'error') {
          severity = 'critical';
        } else if (f.severity === 'warn') {
          severity = 'medium';
        } else {
          severity = 'info';
        }

        return {
          id: f.id || '',
          rule: f.code,
          severity,
          message: f.message,
          file: f.file,
          locations: [],
          fixable: f.fixable
        };
      });

      scoreResult = scoreEngine.calculateScore(scoringFindings);
    }

    // Regenerate KB files
    await generateKnowledgeBase(workspaceRoot, state, scoreResult, outputChannel);
    
    outputChannel.appendLine('[KB] Auto-regenerated after examination update');
  } catch (error) {
    outputChannel.appendLine(`[KB] Auto-regeneration failed (non-critical): ${error}`);
  }
}

/**
 * Generates the .aspect/ knowledge base directory with architectural intelligence.
 * 
 * Files generated:
 * - structure.md: Codebase layout + dependencies + hubs
 * - awareness.md: Contextual guidance on high-impact areas
 * - code.md: Symbol index with relationships
 * - flows.md: Data flows and request paths
 * - conventions.md: Naming patterns and styles
 */
export async function generateKnowledgeBase(
  workspaceRoot: vscode.Uri,
  state: AspectCodeState,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const aspectCodeDir = vscode.Uri.joinPath(workspaceRoot, '.aspect');
  
  // Ensure .aspect directory exists
  try {
    await vscode.workspace.fs.createDirectory(aspectCodeDir);
  } catch (e) {
    // Directory may already exist, ignore
  }

  // Ensure .aspect/ is in .gitignore
  await ensureGitignore(workspaceRoot, outputChannel);

  outputChannel.appendLine('[KB] Generating lean knowledge base in .aspect/');

  // Pre-fetch shared data
  const files = await discoverWorkspaceFiles(workspaceRoot);
  const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, files, outputChannel);

  // Generate all KB files in parallel
  await Promise.all([
    generateStructureFile(aspectCodeDir, state, workspaceRoot, files, depData, allLinks, outputChannel),
    generateAwarenessFile(aspectCodeDir, state, workspaceRoot, depData, allLinks, outputChannel),
    generateCodeFile(aspectCodeDir, state, workspaceRoot, allLinks, outputChannel),
    generateFlowsFile(aspectCodeDir, state, workspaceRoot, files, allLinks, outputChannel),
    generateConventionsFile(aspectCodeDir, state, workspaceRoot, files, outputChannel)
  ]);

  outputChannel.appendLine('[KB] Knowledge base generation complete (5 files)');
}

// ============================================================================
// structure.md - Codebase Layout + Dependencies
// ============================================================================

/**
 * Generate .aspect/structure.md - merged architecture + dependencies
 * 
 * Purpose: Help agents understand WHERE code lives and HOW it connects.
 * Answers: "Where should I put this new code?" and "What will this change affect?"
 */
async function generateStructureFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  depData: Map<string, { inDegree: number; outDegree: number }>,
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Codebase Structure\n\n';
  content += '_Where code lives and how modules connect. Use this before adding or moving code._\n\n';

  if (files.length === 0) {
    content += '_No source files found._\n';
  } else {
    // Quick stats
    const totalEdges = allLinks.length;
    const circularLinks = allLinks.filter(l => l.type === 'circular');
    const cycleCount = Math.ceil(circularLinks.length / 2);
    
    content += `**Files:** ${files.length} | **Dependencies:** ${totalEdges} | **Cycles:** ${cycleCount}\n\n`;

    // Entry points (most important for understanding flow)
    const entryPoints = detectEntryPoints(files, workspaceRoot.fsPath);
    if (entryPoints.length > 0) {
      content += '## Entry Points\n\n';
      for (const entry of entryPoints.slice(0, 5)) {
        content += `- \`${entry.path}\` — ${entry.reason}\n`;
      }
      content += '\n';
    }

    // Hub modules - high fan-in/out (most impactful files)
    const hubs = Array.from(depData.entries())
      .map(([file, info]) => ({
        file,
        inDegree: info.inDegree,
        outDegree: info.outDegree,
        totalDegree: info.inDegree + info.outDegree
      }))
      .filter(h => h.totalDegree > 3)
      .sort((a, b) => b.totalDegree - a.totalDegree)
      .slice(0, 10);

    if (hubs.length > 0) {
      content += '## Hub Modules (High Impact)\n\n';
      content += '_Changes to these files affect many dependents. Proceed with caution._\n\n';
      
      content += '| File | Imports | Imported By | Risk |\n';
      content += '|------|---------|-------------|------|\n';
      
      for (const hub of hubs) {
        const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
        const risk = hub.inDegree > 10 ? 'High' : hub.inDegree > 5 ? 'Medium' : 'Low';
        content += `| \`${relPath}\` | ${hub.outDegree} | ${hub.inDegree} | ${risk} |\n`;
      }
      content += '\n';
    }

    // Circular dependencies (blockers for clean architecture)
    if (circularLinks.length > 0) {
      content += '## Circular Dependencies\n\n';
      content += '_These create tight coupling. Consider refactoring._\n\n';
      
      const processedPairs = new Set<string>();
      let cycleIndex = 0;
      
      for (const link of circularLinks) {
        if (cycleIndex >= 5) break;
        
        const pairKey = [link.source, link.target].sort().join('::');
        if (processedPairs.has(pairKey)) continue;
        processedPairs.add(pairKey);
        
        const sourceRel = makeRelativePath(link.source, workspaceRoot.fsPath);
        const targetRel = makeRelativePath(link.target, workspaceRoot.fsPath);
        
        content += `${cycleIndex + 1}. \`${sourceRel}\` ↔ \`${targetRel}\`\n`;
        cycleIndex++;
      }
      content += '\n';
    }

    // Directory structure with purposes (condensed)
    const dirStructure = analyzeDirStructure(files, workspaceRoot.fsPath);
    const topDirs = Array.from(dirStructure.entries())
      .filter(([_, info]) => info.files.length >= 3)
      .slice(0, 15);

    if (topDirs.length > 0) {
      content += '## Directory Layout\n\n';
      content += '| Directory | Files | Purpose |\n';
      content += '|-----------|-------|--------|\n';
      
      for (const [dir, info] of topDirs) {
        const relDir = makeRelativePath(dir, workspaceRoot.fsPath) || '.';
        const purpose = info.purpose || inferDirPurpose(relDir);
        content += `| \`${relDir}/\` | ${info.files.length} | ${purpose} |\n`;
      }
      content += '\n';
    }

    // Test organization
    const testInfo = analyzeTestOrganization(files, workspaceRoot.fsPath);
    if (testInfo.testFiles.length > 0) {
      content += '## Tests\n\n';
      content += `**Test files:** ${testInfo.testFiles.length}\n`;
      if (testInfo.testDirs.length > 0) {
        content += `**Test dirs:** ${testInfo.testDirs.slice(0, 3).join(', ')}\n`;
      }
      if (testInfo.testPatterns.length > 0) {
        content += `**Patterns:** ${testInfo.testPatterns.join(', ')}\n`;
      }
      content += '\n';
    }
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  const structureFile = vscode.Uri.joinPath(aspectCodeDir, 'structure.md');
  await vscode.workspace.fs.writeFile(structureFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated structure.md`);
}

// ============================================================================
// awareness.md - Contextual Guidance and Risk Zones
// ============================================================================

/**
 * Generate .aspect/awareness.md - contextual guidance on high-impact areas
 * 
 * Purpose: Provide structural intelligence about where caution is needed.
 * Answers: "What areas need care?" and "What context should I have?"
 * 
 * This is supplementary guidance, not a to-do list. Focus on:
 * - Understanding architectural impact zones
 * - Knowing which files are highly coupled
 * - Being aware of patterns that have caused issues
 */
async function generateAwarenessFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  depData: Map<string, { inDegree: number; outDegree: number }>,
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Codebase Awareness\n\n';
  content += '_Contextual guidance for understanding high-impact areas. This is supplementary context—focus on architecture and code understanding first._\n\n';

  const findings = state.s.findings;

  if (findings.length === 0) {
    content += '_No examination data available. Run examination to generate awareness context._\n';
  } else {
    // Summary stats
    const errorCount = findings.filter(f => f.severity === 'error').length;
    const warnCount = findings.filter(f => f.severity === 'warn').length;
    
    content += `**Examination context:** ${findings.length} items | ${errorCount} high-priority | ${warnCount} informational\n\n`;

    // Hotspot files (files with most issues)
    const fileMap = new Map<string, typeof findings>();
    for (const finding of findings) {
      if (!fileMap.has(finding.file)) {
        fileMap.set(finding.file, []);
      }
      fileMap.get(finding.file)!.push(finding);
    }

    const hotspots = Array.from(fileMap.entries())
      .map(([file, fileFindings]) => ({
        file,
        total: fileFindings.length,
        critical: fileFindings.filter(f => f.severity === 'error').length,
        depInfo: depData.get(file)
      }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 10);

    content += '## High-Impact Files\n\n';
    content += '_Files with high coupling or many observations. Changes here require extra care._\n\n';
    
    content += '| File | Issues | Critical | Dependents | Risk |\n';
    content += '|------|--------|----------|------------|------|\n';
    
    for (const hs of hotspots) {
      const relPath = makeRelativePath(hs.file, workspaceRoot.fsPath);
      const deps = hs.depInfo?.inDegree || 0;
      const risk = (hs.critical > 0 && deps > 5) ? 'High' : (hs.total > 3 || deps > 5) ? 'Medium' : 'Low';
      content += `| \`${relPath}\` | ${hs.total} | ${hs.critical} | ${deps} | ${risk} |\n`;
    }
    content += '\n';

    // Top findings with stable IDs
    // Tier 2 architectural rules
    const tier2RuleIds = new Set([
      'analysis.change_impact',
      'architecture.dependency_cycle_impact', 
      'architecture.critical_dependency',
      'deadcode.unused_public'
    ]);
    
    // KB-enriching rules are informational (entry points, data models, integrations)
    // These should NOT appear in issue sections - they are architectural intelligence, not problems
    const kbEnrichingRuleIds = new Set(Object.values(KB_ENRICHING_RULES));
    
    // Low-priority rules that shouldn't be labeled "critical" even if severity is error
    const lowPriorityRules = new Set([
      'imports.unused', 'deadcode.unused_import', 'deadcode.unused_variable',
      'style.mixed_indentation', 'style.trailing_whitespace', 'style.missing_newline_eof',
      'naming.inconsistent_case', 'naming.non_conventional'
    ]);
    
    // Rules that may indicate potential past changes, incomplete implementations, or deleted code
    const potentialArchSignalRules = new Set([
      'imports.unused', 'deadcode.unused_import', 'deadcode.unused_variable',
      'deadcode.unused_public', 'deadcode.unreachable_code'
    ]);

    const tier2Findings = findings.filter(f => tier2RuleIds.has(f.code)).slice(0, 10);
    // Truly critical: security, bugs - not low-priority style/unused issues
    const criticalFindings = findings.filter(f => 
      f.severity === 'error' && 
      !tier2RuleIds.has(f.code) && 
      !lowPriorityRules.has(f.code) &&
      !kbEnrichingRuleIds.has(f.code)
    ).slice(0, 15);
    // Code quality issues: includes low-priority errors and all warnings (but not KB-enriching rules)
    const qualityFindings = findings.filter(f => 
      !kbEnrichingRuleIds.has(f.code) && (
        (f.severity === 'error' && lowPriorityRules.has(f.code)) ||
        (f.severity === 'warn' && !tier2RuleIds.has(f.code))
      )
    ).slice(0, 15);

    let findingId = 1;

    // Structural observations (Tier 2)
    if (tier2Findings.length > 0) {
      content += '## Structural Observations\n\n';
      content += '_Cross-file patterns and dependencies to be aware of when making changes._\n\n';
      
      for (const finding of tier2Findings) {
        const fId = `F-${String(findingId++).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const line = finding.span?.start?.line || '';
        
        content += `### ${fId}: \`${finding.code}\`\n\n`;
        content += `**Location:** \`${relPath}${line ? ':' + line : ''}\`\n\n`;
        content += `${finding.message}\n\n`;
      }
    }

    // Security & correctness notes (for context, not a to-do list)
    if (criticalFindings.length > 0) {
      content += '## Security & Correctness Notes\n\n';
      content += '_Areas flagged for review. These are observations to consider, not necessarily problems._\n\n';
      
      for (const finding of criticalFindings) {
        const fId = `F-${String(findingId++).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const line = finding.span?.start?.line || '';
        const guidanceNote = getPatternGuidanceNote(finding.code);
        
        content += `### ${fId}: \`${finding.code}\`\n\n`;
        content += `**Location:** \`${relPath}${line ? ':' + line : ''}\`\n\n`;
        content += `${finding.message}\n\n`;
        if (guidanceNote) {
          content += `**Context:** ${guidanceNote}\n\n`;
        }
      }
    }

    // Additional context (code quality observations)
    if (qualityFindings.length > 0) {
      content += '## Additional Context\n\n';
      content += '_Observations about code patterns. May indicate areas worth understanding better._\n\n';
      content += '_Note: Unused imports/variables sometimes indicate past changes or incomplete implementations._\n\n';
      
      for (const finding of qualityFindings) {
        const fId = `F-${String(findingId++).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const line = finding.span?.start?.line || '';
        const isPotentialArchSignal = potentialArchSignalRules.has(finding.code);
        
        content += `- **${fId}:** \`${finding.code}\` in \`${relPath}${line ? ':' + line : ''}\``;
        if (isPotentialArchSignal) {
          content += ' *(review: may indicate incomplete implementation)*';
        }
        content += '\n';
      }
      content += '\n';
    }

    // Common patterns to avoid (derived from findings)
    // Exclude KB-enriching rules - they are informational, not patterns to avoid
    const ruleGroups = new Map<string, number>();
    for (const finding of findings) {
      if (!kbEnrichingRuleIds.has(finding.code)) {
        ruleGroups.set(finding.code, (ruleGroups.get(finding.code) || 0) + 1);
      }
    }
    
    const topRules = Array.from(ruleGroups.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 8)
      .filter(([_, count]) => count >= 2);

    if (topRules.length > 0) {
      content += '## Patterns to Watch\n\n';
      content += '_Recurring patterns in this codebase. Be aware of these when making changes._\n\n';
      
      for (const [rule, count] of topRules) {
        const note = getPatternGuidanceNote(rule);
        content += `- **\`${rule}\`** (${count}x)`;
        if (note) {
          content += ` — ${note}`;
        }
        content += '\n';
      }
      content += '\n';
    }

    // Safe zones (files with no critical issues and low coupling)
    const allFiles = Array.from(new Set(findings.map(f => f.file)));
    const safeFiles = allFiles
      .filter(f => {
        const fileFindings = fileMap.get(f) || [];
        const depInfo = depData.get(f);
        return fileFindings.every(ff => ff.severity !== 'error') && 
               (depInfo?.inDegree || 0) < 3;
      })
      .slice(0, 5);

    if (safeFiles.length > 0) {
      content += '## Stable Files\n\n';
      content += '_Files with lower coupling and fewer observations. Good reference examples._\n\n';
      for (const file of safeFiles) {
        const relPath = makeRelativePath(file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`\n`;
      }
      content += '\n';
    }
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  const awarenessFile = vscode.Uri.joinPath(aspectCodeDir, 'awareness.md');
  await vscode.workspace.fs.writeFile(awarenessFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated awareness.md`);
}

/**
 * Get contextual guidance note for a pattern
 */
function getPatternGuidanceNote(rule: string): string | null {
  const notes: Record<string, string> = {
    'sec.sql_injection_concat': 'Use parameterized queries instead of string concatenation',
    'sec.hardcoded_secret': 'Use environment variables or secrets management',
    'sec.path_traversal': 'Validate and sanitize file paths',
    'sec.open_redirect': 'Validate redirect URLs against an allowlist',
    'sec.insecure_random': 'Use cryptographic randomness for security contexts',
    'bug.float_equality': 'Use approximate comparison for floating-point numbers',
    'bug.iteration_modification': 'Iterate over a copy when modifying collections',
    'errors.swallowed_exception': 'Log or re-raise exceptions instead of silencing',
    'errors.broad_catch': 'Catch specific exception types',
    'deadcode.unused_variable': 'Remove or prefix with underscore (note: may indicate deleted code or incomplete implementation)',
    'deadcode.unused_import': 'Remove unused imports (note: may indicate deleted code or incomplete implementation)',
    'imports.unused': 'Remove unused imports (note: may indicate deleted code or incomplete implementation)',
    'complexity.high_cyclomatic': 'Extract helper functions to reduce complexity',
    'complexity.long_function': 'Split into smaller, focused functions',
    'naming.inconsistent_case': 'Follow consistent naming conventions',
  };
  
  return notes[rule] || null;
}

// ============================================================================
// code.md - Symbol Index with Relationships
// ============================================================================

/**
 * Generate .aspect/code.md - symbol index (renamed from symbols.md)
 * 
 * Purpose: Help agents understand WHAT is defined WHERE and HOW symbols connect.
 * Answers: "Where is this function defined?" and "What calls this?"
 */
async function generateCodeFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Code Index\n\n';
  content += '_Functions, classes, and their relationships. Use before modifying symbols._\n\n';

  const findings = state.s.findings;
  
  // KB-Enriching: Data Models section
  const dataModels = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.DATA_MODEL);
  
  if (dataModels.length > 0) {
    content += '## Data Models\n\n';
    content += '_Core data structures and schemas. Understand these before modifying data handling._\n\n';
    
    // Group by model type
    const ormModels = dataModels.filter(f => 
      f.message.includes('ORM') || f.message.includes('Entity')
    );
    const dataClasses = dataModels.filter(f => 
      f.message.includes('Data Class') || f.message.includes('dataclass') || 
      f.message.includes('Pydantic') || f.message.includes('BaseModel')
    );
    const interfaces = dataModels.filter(f => 
      f.message.includes('Interface') || f.message.includes('Type Alias')
    );
    const schemas = dataModels.filter(f => 
      f.message.includes('Schema') || f.message.includes('Validator')
    );
    const other = dataModels.filter(f => 
      !ormModels.includes(f) && !dataClasses.includes(f) && 
      !interfaces.includes(f) && !schemas.includes(f)
    );

    if (ormModels.length > 0) {
      content += '### ORM Models\n\n';
      content += '| File | Model |\n';
      content += '|------|-------|\n';
      for (const model of ormModels.slice(0, 20)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `| \`${relPath}\` | ${model.message.replace('Data model: ', '')} |\n`;
      }
      content += '\n';
    }

    if (dataClasses.length > 0) {
      content += '### Data Classes\n\n';
      content += '| File | Model |\n';
      content += '|------|-------|\n';
      for (const model of dataClasses.slice(0, 20)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `| \`${relPath}\` | ${model.message.replace('Data model: ', '')} |\n`;
      }
      content += '\n';
    }

    if (interfaces.length > 0) {
      content += '### TypeScript Interfaces & Types\n\n';
      content += '| File | Type |\n';
      content += '|------|------|\n';
      for (const model of interfaces.slice(0, 20)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `| \`${relPath}\` | ${model.message.replace('Data model: ', '')} |\n`;
      }
      content += '\n';
    }

    if (schemas.length > 0) {
      content += '### Validation Schemas\n\n';
      for (const model of schemas.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${model.message}\n`;
      }
      content += '\n';
    }

    if (other.length > 0) {
      content += '### Other Data Structures\n\n';
      for (const model of other.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${model.message}\n`;
      }
      content += '\n';
    }
  }

  // Get relevant files (with findings or in dependency graph)
  const relevantFiles = new Set<string>();
  for (const finding of findings) {
    relevantFiles.add(finding.file);
  }
  for (const link of allLinks) {
    relevantFiles.add(link.source);
    relevantFiles.add(link.target);
  }

  if (relevantFiles.size === 0) {
    content += '_No files indexed. Run examination first._\n';
  } else {
    // Score files by importance
    const fileScores = new Map<string, number>();
    for (const file of relevantFiles) {
      const findingCount = findings.filter(f => f.file === file).length;
      const outLinks = allLinks.filter(l => l.source === file).length;
      const inLinks = allLinks.filter(l => l.target === file).length;
      fileScores.set(file, findingCount * 10 + outLinks + inLinks);
    }

    const sortedFiles = Array.from(relevantFiles)
      .sort((a, b) => (fileScores.get(b) || 0) - (fileScores.get(a) || 0))
      .slice(0, 50); // Top 50 files

    content += `**Files indexed:** ${sortedFiles.length}\n\n`;

    for (const file of sortedFiles) {
      const relPath = makeRelativePath(file, workspaceRoot.fsPath);
      const symbols = await extractFileSymbols(file, allLinks);

      if (symbols.length === 0) continue;

      content += `## \`${relPath}\`\n\n`;
      content += '| Symbol | Kind | Calls | Called By |\n';
      content += '|--------|------|-------|----------|\n';

      for (const symbol of symbols.slice(0, 15)) {
        const calls = symbol.callsInto.slice(0, 3).map(c => `\`${c}\``).join(', ') || '—';
        const calledBy = symbol.calledBy.slice(0, 3).map(c => `\`${c}\``).join(', ') || '—';
        content += `| \`${symbol.name}\` | ${symbol.kind} | ${calls} | ${calledBy} |\n`;
      }

      if (symbols.length > 15) {
        content += `\n_+${symbols.length - 15} more symbols_\n`;
      }
      content += '\n';
    }
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  const codeFile = vscode.Uri.joinPath(aspectCodeDir, 'code.md');
  await vscode.workspace.fs.writeFile(codeFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated code.md (${relevantFiles.size} files)`);
}

// ============================================================================
// flows.md - Data Flows and Request Paths
// ============================================================================

/**
 * Generate .aspect/flows.md - data flows through the codebase
 * 
 * Purpose: Show agents HOW data/requests flow through the architecture.
 * Answers: "What happens when a request comes in?" and "Where should new code go?"
 * 
 * Design principles:
 * - Top N prioritization (most central, most risky)
 * - Group by module/feature, not flat lists
 * - Actionable: "Where should a new login route go?"
 */
async function generateFlowsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Data Flows\n\n';
  content += '_How data moves through the codebase. Use this to understand change impact and find the right place for new code._\n\n';

  if (allLinks.length === 0) {
    content += '_No dependency data available. Run examination first._\n';
  } else {
    // Calculate centrality scores for all files
    const centralityScores = calculateCentralityScores(allLinks);
    
    // 1. TOP CRITICAL FLOWS - Prioritized view
    content += '## Critical Flows (Top 10)\n\n';
    content += '_Most central modules ranked by connectivity and risk. Changes here affect many files._\n\n';
    
    const topModules = Array.from(centralityScores.entries())
      .sort((a, b) => b[1].score - a[1].score)
      .slice(0, 10);
    
    if (topModules.length > 0) {
      content += '| Rank | Module | Callers | Dependencies | Risk |\n';
      content += '|------|--------|---------|--------------|------|\n';
      for (let i = 0; i < topModules.length; i++) {
        const [file, stats] = topModules[i];
        const relPath = makeRelativePath(file, workspaceRoot.fsPath);
        const riskLevel = stats.score > 20 ? '🔴 High' : stats.score > 10 ? '🟡 Medium' : '🟢 Low';
        content += `| ${i + 1} | \`${relPath}\` | ${stats.inDegree} | ${stats.outDegree} | ${riskLevel} |\n`;
      }
      content += '\n';
      
      // Show detailed info for top 3 modules
      content += '### Hub Details\n\n';
      for (let i = 0; i < Math.min(3, topModules.length); i++) {
        const [topFile, topStats] = topModules[i];
        const topRelPath = makeRelativePath(topFile, workspaceRoot.fsPath);
        const topCallers = allLinks.filter(l => l.target === topFile && l.source !== topFile);
        const topDeps = allLinks.filter(l => l.source === topFile && l.target !== topFile);
        
        content += `**${i + 1}. \`${topRelPath}\`** (${topStats.inDegree} callers, ${topStats.outDegree} deps)\n\n`;
        
        if (topCallers.length > 0) {
          content += 'Called by:\n';
          for (const caller of topCallers.slice(0, 5)) {
            const callerRel = makeRelativePath(caller.source, workspaceRoot.fsPath);
            content += `- \`${callerRel}\`\n`;
          }
          if (topCallers.length > 5) {
            content += `- _...and ${topCallers.length - 5} more_\n`;
          }
          content += '\n';
        }
        
        if (topDeps.length > 0) {
          content += 'Depends on:\n';
          for (const dep of topDeps.slice(0, 5)) {
            const depRel = makeRelativePath(dep.target, workspaceRoot.fsPath);
            content += `- \`${depRel}\`\n`;
          }
          if (topDeps.length > 5) {
            content += `- _...and ${topDeps.length - 5} more_\n`;
          }
          content += '\n';
        }
      }
    } else {
      content += '_No high-connectivity modules detected._\n\n';
    }

    // 2. DEPENDENCY CHAINS - Show multi-hop flows
    content += '## Dependency Chains\n\n';
    content += '_How modules chain together. Useful for understanding transitive impact._\n\n';
    
    const chains = findDependencyChains(allLinks, workspaceRoot.fsPath, 3);
    if (chains.length > 0) {
      for (const chain of chains.slice(0, 5)) {
        content += `\`\`\`\n${chain}\n\`\`\`\n\n`;
      }
    } else {
      content += '_No significant dependency chains detected._\n\n';
    }

    // 3. ENTRY POINTS - Grouped by module/prefix
    const ruleEntryPoints = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.ENTRY_POINT);
    const entryPoints = detectEntryPoints(files, workspaceRoot.fsPath);
    
    if (ruleEntryPoints.length > 0 || entryPoints.length > 0) {
      content += '## Entry Points\n\n';
      content += '_Where requests enter the system. Group new endpoints with related ones._\n\n';
      
      // Group HTTP handlers by route prefix/module
      const httpHandlers = ruleEntryPoints.filter(f => f.message.includes('HTTP'));
      
      if (httpHandlers.length > 0) {
        const groupedRoutes = groupEndpointsByModule(httpHandlers, workspaceRoot.fsPath);
        
        content += '### API Routes\n\n';
        for (const [moduleName, endpoints] of Object.entries(groupedRoutes).slice(0, 10)) {
          const methods = endpoints.map(e => {
            const match = e.message.match(/(GET|POST|PUT|DELETE|PATCH)/);
            return match ? match[1] : '?';
          });
          const methodSummary = [...new Set(methods)].join('/');
          
          content += `**${moduleName}** (${endpoints.length} endpoints, ${methodSummary})\n`;
          
          // Show first 5 endpoints as examples
          for (const ep of endpoints.slice(0, 5)) {
            const handler = ep.message.replace('HTTP entry point: ', '').replace(/^(GET|POST|PUT|DELETE|PATCH)\s+/, '');
            content += `- ${handler}\n`;
          }
          if (endpoints.length > 5) {
            content += `- _...and ${endpoints.length - 5} more_\n`;
          }
          content += '\n';
        }
        
        // Quick reference for adding new routes
        if (Object.keys(groupedRoutes).length > 0) {
          content += '> **Adding a new route?** Find the module above that matches your feature.\n\n';
        }
      }
      
      // Other entry points (CLI, events, main)
      const cliCommands = ruleEntryPoints.filter(f => f.message.includes('CLI'));
      const eventListeners = ruleEntryPoints.filter(f => f.message.includes('Event') || f.message.includes('listener'));
      const mainFunctions = ruleEntryPoints.filter(f => f.message.includes('Main'));
      
      if (cliCommands.length > 0) {
        content += '### CLI Commands\n\n';
        for (const entry of cliCommands.slice(0, 8)) {
          const relPath = makeRelativePath(entry.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${entry.message}\n`;
        }
        content += '\n';
      }
      
      if (eventListeners.length > 0) {
        content += '### Event Handlers\n\n';
        for (const entry of eventListeners.slice(0, 8)) {
          const relPath = makeRelativePath(entry.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${entry.message}\n`;
        }
        content += '\n';
      }
      
      if (mainFunctions.length > 0) {
        content += '### Application Entry\n\n';
        for (const entry of mainFunctions.slice(0, 5)) {
          const relPath = makeRelativePath(entry.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${entry.message}\n`;
        }
        content += '\n';
      }
    }

    // 4. DATA MODELS
    const dataModels = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.DATA_MODEL);
    if (dataModels.length > 0) {
      content += '## Data Models\n\n';
      content += '_Core data structures. Check these when adding new fields or relationships._\n\n';
      
      // Group by file
      const modelsByFile = new Map<string, typeof dataModels>();
      for (const model of dataModels) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        if (!modelsByFile.has(relPath)) {
          modelsByFile.set(relPath, []);
        }
        modelsByFile.get(relPath)!.push(model);
      }
      
      for (const [filePath, models] of Array.from(modelsByFile.entries()).slice(0, 8)) {
        content += `**\`${filePath}\`**\n`;
        for (const model of models.slice(0, 5)) {
          // Extract model name from message
          const modelInfo = model.message.replace('Data model: ', '').replace('ORM model: ', '');
          content += `- ${modelInfo}\n`;
        }
        if (models.length > 5) {
          content += `- _...and ${models.length - 5} more_\n`;
        }
        content += '\n';
      }
    }

    // 5. EXTERNAL INTEGRATIONS - Grouped by type
    const externalIntegrations = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.EXTERNAL_INTEGRATION);
    
    if (externalIntegrations.length > 0) {
      content += '## External Integrations\n\n';
      content += '_Connections to external services. Check these when debugging connectivity issues._\n\n';
      
      // Group by type with counts
      const databases = externalIntegrations.filter(f => 
        f.message.includes('Database') || f.message.includes('DB') || f.message.includes('SQL')
      );
      const httpClients = externalIntegrations.filter(f => 
        f.message.includes('HTTP') || f.message.includes('API') || f.message.includes('fetch')
      );
      const queues = externalIntegrations.filter(f => 
        f.message.includes('Queue') || f.message.includes('Kafka') || f.message.includes('Redis')
      );
      const other = externalIntegrations.filter(f => 
        !databases.includes(f) && !httpClients.includes(f) && !queues.includes(f)
      );

      // Summary table
      content += '| Type | Count | Primary Location |\n';
      content += '|------|-------|------------------|\n';
      if (databases.length > 0) {
        const dbLoc = databases[0] ? makeRelativePath(databases[0].file, workspaceRoot.fsPath) : '-';
        content += `| Database | ${databases.length} | \`${dbLoc}\` |\n`;
      }
      if (httpClients.length > 0) {
        const httpLoc = httpClients[0] ? makeRelativePath(httpClients[0].file, workspaceRoot.fsPath) : '-';
        content += `| HTTP/API | ${httpClients.length} | \`${httpLoc}\` |\n`;
      }
      if (queues.length > 0) {
        const qLoc = queues[0] ? makeRelativePath(queues[0].file, workspaceRoot.fsPath) : '-';
        content += `| Message Queue | ${queues.length} | \`${qLoc}\` |\n`;
      }
      if (other.length > 0) {
        const otherLoc = other[0] ? makeRelativePath(other[0].file, workspaceRoot.fsPath) : '-';
        content += `| Other | ${other.length} | \`${otherLoc}\` |\n`;
      }
      content += '\n';
      
      // Show details for each integration type
      if (databases.length > 0) {
        content += '### Database Connections\n\n';
        for (const db of databases.slice(0, 5)) {
          const relPath = makeRelativePath(db.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${db.message}\n`;
        }
        content += '\n';
      }
      
      if (httpClients.length > 0) {
        content += '### HTTP/API Clients\n\n';
        for (const http of httpClients.slice(0, 5)) {
          const relPath = makeRelativePath(http.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${http.message}\n`;
        }
        content += '\n';
      }
    }

    // 6. ARCHITECTURAL LAYERS
    const layerFlows = detectLayerFlows(files, allLinks, workspaceRoot.fsPath);
    if (layerFlows.length > 0) {
      content += '## Request Flow Pattern\n\n';
      content += '_How a typical request flows through the architecture._\n\n';
      
      for (const layer of layerFlows) {
        content += `**${layer.name}:**\n`;
        content += `\`\`\`\n${layer.flow}\n\`\`\`\n\n`;
      }
    }

    // 7. CIRCULAR DEPENDENCIES - Only real cycles, not self-refs
    const circularLinks = allLinks.filter(l => 
      l.type === 'circular' && l.source !== l.target
    );
    
    if (circularLinks.length > 0) {
      content += '## ⚠️ Circular Dependencies\n\n';
      content += '_Bidirectional imports that may cause issues. Consider refactoring._\n\n';
      
      const processedPairs = new Set<string>();
      let cycleCount = 0;
      
      for (const link of circularLinks) {
        if (cycleCount >= 8) break;
        
        const pairKey = [link.source, link.target].sort().join('::');
        if (processedPairs.has(pairKey)) continue;
        processedPairs.add(pairKey);
        
        const sourceRel = makeRelativePath(link.source, workspaceRoot.fsPath);
        const targetRel = makeRelativePath(link.target, workspaceRoot.fsPath);
        
        content += `- \`${sourceRel}\` ↔ \`${targetRel}\`\n`;
        cycleCount++;
      }
      if (circularLinks.length > 8) {
        content += `\n_...and ${circularLinks.length - 8} more circular dependencies_\n`;
      }
      content += '\n';
    }

    // 8. MODULE CLUSTERS - Files that are often imported together
    const clusters = findModuleClusters(allLinks, workspaceRoot.fsPath);
    if (clusters.length > 0) {
      content += '## Module Clusters\n\n';
      content += '_Files that are commonly used together. Useful for understanding feature boundaries._\n\n';
      
      for (const cluster of clusters.slice(0, 5)) {
        content += `**${cluster.name}** (${cluster.files.length} files)\n`;
        for (const file of cluster.files.slice(0, 4)) {
          content += `- \`${file}\`\n`;
        }
        if (cluster.files.length > 4) {
          content += `- _...and ${cluster.files.length - 4} more_\n`;
        }
        content += '\n';
      }
    }

    // 9. QUICK REFERENCE - Actionable guidance
    content += '## Quick Reference\n\n';
    content += '**"Where should a new API route go?"**\n';
    content += '→ Check Entry Points > API Routes above. Add to the matching module.\n\n';
    content += '**"What happens when X endpoint is called?"**\n';
    content += '→ Find it in Entry Points, then trace through Critical Flows to see dependencies.\n\n';
    content += '**"Is it safe to change this file?"**\n';
    content += '→ Check if it appears in Critical Flows. High-rank modules need extra care.\n\n';
    content += '**"What files work together for feature X?"**\n';
    content += '→ Check Module Clusters to see commonly co-imported files.\n';
  }

  content += `\n---\n_Generated: ${new Date().toISOString()}_\n`;

  const flowsFile = vscode.Uri.joinPath(aspectCodeDir, 'flows.md');
  await vscode.workspace.fs.writeFile(flowsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated flows.md`);
}

/**
 * Calculate centrality scores for modules based on connectivity
 */
function calculateCentralityScores(
  allLinks: DependencyLink[]
): Map<string, { inDegree: number; outDegree: number; score: number }> {
  const scores = new Map<string, { inDegree: number; outDegree: number; score: number }>();
  
  const allFiles = new Set(allLinks.flatMap(l => [l.source, l.target]));
  
  for (const file of allFiles) {
    const inDegree = allLinks.filter(l => l.target === file && l.source !== file).length;
    const outDegree = allLinks.filter(l => l.source === file && l.target !== file).length;
    // Score: inDegree weighted higher (callers = more impact)
    const score = (inDegree * 2) + outDegree;
    scores.set(file, { inDegree, outDegree, score });
  }
  
  return scores;
}

/**
 * Group HTTP endpoints by module/route prefix
 */
function groupEndpointsByModule(
  handlers: Array<{ file: string; message: string }>,
  workspaceRoot: string
): Record<string, Array<{ file: string; message: string }>> {
  const groups: Record<string, Array<{ file: string; message: string }>> = {};
  
  for (const handler of handlers) {
    const relPath = makeRelativePath(handler.file, workspaceRoot);
    
    // Extract module name from path
    // e.g., "backend/app/api/routes/items.py" -> "items"
    // e.g., "src/routes/auth/login.ts" -> "auth"
    const parts = relPath.split(/[/\\]/);
    let moduleName = path.basename(handler.file, path.extname(handler.file));
    
    // Try to find a more meaningful parent directory
    const routeIdx = parts.findIndex(p => p === 'routes' || p === 'api' || p === 'endpoints');
    if (routeIdx >= 0 && routeIdx < parts.length - 1) {
      // Use the directory after routes/api
      const nextPart = parts[routeIdx + 1];
      if (!nextPart.includes('.')) {
        moduleName = nextPart;
      }
    }
    
    // Capitalize and clean up
    moduleName = moduleName.charAt(0).toUpperCase() + moduleName.slice(1);
    
    if (!groups[moduleName]) {
      groups[moduleName] = [];
    }
    groups[moduleName].push(handler);
  }
  
  // Sort by endpoint count
  return Object.fromEntries(
    Object.entries(groups).sort((a, b) => b[1].length - a[1].length)
  );
}

/**
 * Build flows starting from entry points
 */
async function buildEntryPointFlows(
  entryPoints: Array<{ path: string; reason: string }>,
  files: string[],
  allLinks: DependencyLink[],
  workspaceRoot: vscode.Uri
): Promise<Array<{ title: string; chain: string[] }>> {
  const flows: Array<{ title: string; chain: string[] }> = [];
  
  for (const entry of entryPoints.slice(0, 5)) {
    const entryFile = files.find(f => makeRelativePath(f, workspaceRoot.fsPath) === entry.path);
    if (!entryFile) continue;
    
    const chain: string[] = [];
    chain.push(`→ ${entry.path} (${entry.reason})`);
    
    // Follow outgoing links 2 levels deep
    const level1Links = allLinks.filter(l => l.source === entryFile).slice(0, 3);
    for (const l1 of level1Links) {
      const l1Name = makeRelativePath(l1.target, workspaceRoot.fsPath);
      const l1Symbols = l1.symbols.slice(0, 2).join(', ');
      chain.push(`  → ${l1Name}${l1Symbols ? ` (${l1Symbols})` : ''}`);
      
      const level2Links = allLinks.filter(l => l.source === l1.target).slice(0, 2);
      for (const l2 of level2Links) {
        const l2Name = makeRelativePath(l2.target, workspaceRoot.fsPath);
        chain.push(`    → ${l2Name}`);
      }
    }
    
    if (chain.length > 1) {
      flows.push({ title: entry.reason, chain });
    }
  }
  
  return flows;
}

/**
 * Detect architectural layer flows (models → services → handlers)
 */
function detectLayerFlows(
  files: string[],
  allLinks: DependencyLink[],
  workspaceRoot: string
): Array<{ name: string; flow: string }> {
  const flows: Array<{ name: string; flow: string }> = [];
  
  // Detect common architectural patterns
  const hasModels = files.some(f => f.toLowerCase().includes('model'));
  const hasServices = files.some(f => f.toLowerCase().includes('service'));
  const hasHandlers = files.some(f => f.toLowerCase().includes('handler') || f.toLowerCase().includes('controller'));
  const hasApi = files.some(f => f.toLowerCase().includes('/api/') || f.toLowerCase().includes('route'));
  
  if (hasApi && hasHandlers) {
    flows.push({
      name: 'API Request Flow',
      flow: 'Client Request → Routes/API → Handlers/Controllers → Services → Models → Database'
    });
  }
  
  if (hasModels && hasServices) {
    flows.push({
      name: 'Data Flow',
      flow: 'Models (data) → Services (logic) → Handlers (HTTP) → Response'
    });
  }
  
  // Detect frontend patterns
  const hasComponents = files.some(f => f.toLowerCase().includes('component'));
  const hasHooks = files.some(f => f.toLowerCase().includes('hook') || f.includes('use'));
  
  if (hasComponents && hasHooks) {
    flows.push({
      name: 'React Data Flow',
      flow: 'Components → Hooks → State/Context → API Calls → Server'
    });
  }
  
  return flows;
}

/**
 * Find dependency chains showing how modules connect in sequence
 */
function findDependencyChains(
  allLinks: DependencyLink[],
  workspaceRoot: string,
  maxDepth: number = 3
): string[] {
  const chains: string[] = [];
  
  // Build adjacency map
  const outgoing = new Map<string, string[]>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    if (!outgoing.has(link.source)) {
      outgoing.set(link.source, []);
    }
    outgoing.get(link.source)!.push(link.target);
  }
  
  // Find files with high in-degree (good starting points for chains)
  const inDegree = new Map<string, number>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    inDegree.set(link.target, (inDegree.get(link.target) || 0) + 1);
  }
  
  // Start from high in-degree files and trace outward
  const startFiles = Array.from(inDegree.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5)
    .map(([file]) => file);
  
  for (const startFile of startFiles) {
    const deps = outgoing.get(startFile) || [];
    if (deps.length === 0) continue;
    
    // Build chain
    const chain: string[] = [makeRelativePath(startFile, workspaceRoot)];
    let current = deps[0];
    let depth = 0;
    
    while (depth < maxDepth && current) {
      chain.push(makeRelativePath(current, workspaceRoot));
      const nextDeps = outgoing.get(current) || [];
      current = nextDeps.find(d => !chain.includes(makeRelativePath(d, workspaceRoot))) || '';
      depth++;
    }
    
    if (chain.length >= 2) {
      chains.push(chain.join(' → '));
    }
  }
  
  // Remove duplicates and return
  return [...new Set(chains)];
}

/**
 * Find clusters of files that are commonly imported together
 */
function findModuleClusters(
  allLinks: DependencyLink[],
  workspaceRoot: string
): Array<{ name: string; files: string[] }> {
  const clusters: Array<{ name: string; files: string[] }> = [];
  
  // Group files by common importers (files that import the same things)
  const importedBy = new Map<string, Set<string>>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    if (!importedBy.has(link.target)) {
      importedBy.set(link.target, new Set());
    }
    importedBy.get(link.target)!.add(link.source);
  }
  
  // Find files that share many importers (they're often used together)
  const fileList = Array.from(importedBy.keys());
  const coImportScores = new Map<string, Map<string, number>>();
  
  for (let i = 0; i < fileList.length; i++) {
    for (let j = i + 1; j < fileList.length; j++) {
      const fileA = fileList[i];
      const fileB = fileList[j];
      const importersA = importedBy.get(fileA) || new Set();
      const importersB = importedBy.get(fileB) || new Set();
      
      // Count shared importers
      let shared = 0;
      for (const importer of importersA) {
        if (importersB.has(importer)) shared++;
      }
      
      if (shared >= 2) {
        if (!coImportScores.has(fileA)) {
          coImportScores.set(fileA, new Map());
        }
        coImportScores.get(fileA)!.set(fileB, shared);
      }
    }
  }
  
  // Build clusters from high co-import scores
  const processed = new Set<string>();
  
  for (const [file, relatedMap] of coImportScores.entries()) {
    if (processed.has(file)) continue;
    
    const related = Array.from(relatedMap.entries())
      .filter(([_, score]) => score >= 2)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([f]) => f);
    
    if (related.length >= 2) {
      const clusterFiles = [file, ...related].map(f => makeRelativePath(f, workspaceRoot));
      
      // Determine cluster name from common path components
      const parts = clusterFiles[0].split(/[/\\]/);
      let clusterName = parts.length > 1 ? parts[parts.length - 2] : path.basename(clusterFiles[0]);
      
      clusters.push({
        name: clusterName,
        files: clusterFiles
      });
      
      processed.add(file);
      related.forEach(f => processed.add(f));
    }
  }
  
  return clusters;
}

// ============================================================================
// conventions.md - Naming Patterns and Styles
// ============================================================================

/**
 * Generate .aspect/conventions.md - auto-detected patterns
 * 
 * Purpose: Show agents HOW code is written in this project.
 * Answers: "What naming style should I use?" and "How are imports organized?"
 */
async function generateConventionsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Conventions\n\n';
  content += '_Naming patterns and styles detected in this codebase. Follow these for consistency._\n\n';

  if (files.length === 0) {
    content += '_No source files found._\n';
  } else {
    // Detect file naming conventions
    const fileNaming = analyzeFileNaming(files, workspaceRoot.fsPath);
    
    content += '## File Naming\n\n';
    if (fileNaming.patterns.length > 0) {
      content += '| Pattern | Example | Count |\n';
      content += '|---------|---------|-------|\n';
      for (const pattern of fileNaming.patterns.slice(0, 8)) {
        content += `| ${pattern.style} | \`${pattern.example}\` | ${pattern.count} |\n`;
      }
      content += '\n';
      
      if (fileNaming.dominant) {
        content += `**Use:** ${fileNaming.dominant} for new files.\n\n`;
      }
    } else {
      content += '_No clear pattern detected._\n\n';
    }

    // Detect import patterns
    const importPatterns = await analyzeImportPatterns(files);
    
    if (importPatterns.length > 0) {
      content += '## Import Conventions\n\n';
      content += '_How imports are typically organized._\n\n';
      
      for (const pattern of importPatterns) {
        content += `**${pattern.language}:**\n`;
        content += '```' + pattern.language.toLowerCase() + '\n';
        content += pattern.example;
        content += '\n```\n\n';
      }
    }

    // Detect function naming patterns
    const funcNaming = await analyzeFunctionNaming(files);
    
    if (funcNaming.patterns.length > 0) {
      content += '## Function Naming\n\n';
      content += '| Pattern | Example | Usage |\n';
      content += '|---------|---------|-------|\n';
      for (const pattern of funcNaming.patterns.slice(0, 10)) {
        content += `| ${pattern.pattern} | \`${pattern.example}\` | ${pattern.usage} |\n`;
      }
      content += '\n';
    }

    // Detect class naming patterns
    const classNaming = await analyzeClassNaming(files);
    
    if (classNaming.patterns.length > 0) {
      content += '## Class Naming\n\n';
      content += '| Pattern | Example | Usage |\n';
      content += '|---------|---------|-------|\n';
      for (const pattern of classNaming.patterns.slice(0, 8)) {
        content += `| ${pattern.pattern} | \`${pattern.example}\` | ${pattern.usage} |\n`;
      }
      content += '\n';
    }

    // Detect framework patterns
    const frameworkPatterns = detectFrameworkPatterns(files, workspaceRoot.fsPath);
    
    if (frameworkPatterns.length > 0) {
      content += '## Framework Patterns\n\n';
      content += '_Detected frameworks and their common patterns._\n\n';
      
      for (const fw of frameworkPatterns) {
        content += `### ${fw.name}\n\n`;
        for (const pattern of fw.patterns) {
          content += `- ${pattern}\n`;
        }
        content += '\n';
      }
    }

    // Test naming conventions
    const testNaming = analyzeTestNaming(files, workspaceRoot.fsPath);
    
    if (testNaming.patterns.length > 0) {
      content += '## Test Conventions\n\n';
      content += '| Pattern | Example |\n';
      content += '|---------|--------|\n';
      for (const pattern of testNaming.patterns) {
        content += `| ${pattern.pattern} | \`${pattern.example}\` |\n`;
      }
      content += '\n';
    }

    // Summary guidelines
    content += '## Quick Reference\n\n';
    content += '**When adding new code:**\n';
    if (fileNaming.dominant) {
      content += `- Name files using ${fileNaming.dominant}\n`;
    }
    if (funcNaming.patterns.length > 0) {
      content += `- Name functions like \`${funcNaming.patterns[0].example}\`\n`;
    }
    if (classNaming.patterns.length > 0) {
      content += `- Name classes like \`${classNaming.patterns[0].example}\`\n`;
    }
    content += '- Follow existing import organization\n';
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  const conventionsFile = vscode.Uri.joinPath(aspectCodeDir, 'conventions.md');
  await vscode.workspace.fs.writeFile(conventionsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated conventions.md`);
}

/**
 * Analyze file naming conventions
 */
function analyzeFileNaming(files: string[], workspaceRoot: string): {
  patterns: Array<{ style: string; example: string; count: number }>;
  dominant: string | null;
} {
  const styleCounts: Record<string, { count: number; examples: string[] }> = {
    'kebab-case': { count: 0, examples: [] },
    'snake_case': { count: 0, examples: [] },
    'camelCase': { count: 0, examples: [] },
    'PascalCase': { count: 0, examples: [] },
  };

  for (const file of files) {
    const basename = path.basename(file, path.extname(file));
    
    // Skip index files and test files for pattern detection
    if (basename === 'index' || basename.includes('test') || basename.includes('spec')) {
      continue;
    }

    if (basename.includes('-')) {
      styleCounts['kebab-case'].count++;
      if (styleCounts['kebab-case'].examples.length < 3) {
        styleCounts['kebab-case'].examples.push(path.basename(file));
      }
    } else if (basename.includes('_')) {
      styleCounts['snake_case'].count++;
      if (styleCounts['snake_case'].examples.length < 3) {
        styleCounts['snake_case'].examples.push(path.basename(file));
      }
    } else if (basename[0] === basename[0].toUpperCase() && basename[0] !== basename[0].toLowerCase()) {
      styleCounts['PascalCase'].count++;
      if (styleCounts['PascalCase'].examples.length < 3) {
        styleCounts['PascalCase'].examples.push(path.basename(file));
      }
    } else if (/[a-z][A-Z]/.test(basename)) {
      styleCounts['camelCase'].count++;
      if (styleCounts['camelCase'].examples.length < 3) {
        styleCounts['camelCase'].examples.push(path.basename(file));
      }
    }
  }

  const patterns = Object.entries(styleCounts)
    .filter(([_, data]) => data.count > 0)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([style, data]) => ({
      style,
      example: data.examples[0] || '',
      count: data.count
    }));

  const dominant = patterns.length > 0 && patterns[0].count > files.length * 0.3
    ? patterns[0].style
    : null;

  return { patterns, dominant };
}

/**
 * Analyze import patterns
 */
async function analyzeImportPatterns(files: string[]): Promise<Array<{
  language: string;
  example: string;
}>> {
  const patterns: Array<{ language: string; example: string }> = [];
  
  // Sample a few files per language
  const pyFiles = files.filter(f => f.endsWith('.py')).slice(0, 3);
  const tsFiles = files.filter(f => f.endsWith('.ts') || f.endsWith('.tsx')).slice(0, 3);
  
  // Python import patterns
  for (const file of pyFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      const lines = text.split('\n').slice(0, 30);
      
      const imports = lines.filter(l => l.startsWith('import ') || l.startsWith('from '));
      if (imports.length >= 2) {
        patterns.push({
          language: 'Python',
          example: imports.slice(0, 4).join('\n')
        });
        break;
      }
    } catch {}
  }
  
  // TypeScript import patterns
  for (const file of tsFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      const lines = text.split('\n').slice(0, 30);
      
      const imports = lines.filter(l => l.startsWith('import '));
      if (imports.length >= 2) {
        patterns.push({
          language: 'TypeScript',
          example: imports.slice(0, 4).join('\n')
        });
        break;
      }
    } catch {}
  }
  
  return patterns;
}

/**
 * Analyze function naming patterns
 */
async function analyzeFunctionNaming(files: string[]): Promise<{
  patterns: Array<{ pattern: string; example: string; usage: string }>;
}> {
  const patternCounts: Record<string, { count: number; examples: string[] }> = {
    'get_*': { count: 0, examples: [] },
    'set_*': { count: 0, examples: [] },
    'create_*': { count: 0, examples: [] },
    'delete_*': { count: 0, examples: [] },
    'update_*': { count: 0, examples: [] },
    'is_*': { count: 0, examples: [] },
    'has_*': { count: 0, examples: [] },
    'handle_*': { count: 0, examples: [] },
    'process_*': { count: 0, examples: [] },
    'validate_*': { count: 0, examples: [] },
  };

  const sampleFiles = files.slice(0, 50);
  
  for (const file of sampleFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      
      // Python function pattern
      const pyMatches = text.matchAll(/def\s+(\w+)\s*\(/g);
      for (const match of pyMatches) {
        categorizeFunction(match[1], patternCounts);
      }
      
      // TypeScript function pattern
      const tsMatches = text.matchAll(/function\s+(\w+)\s*\(|const\s+(\w+)\s*=\s*(?:async\s+)?\(/g);
      for (const match of tsMatches) {
        categorizeFunction(match[1] || match[2], patternCounts);
      }
    } catch {}
  }

  const patterns = Object.entries(patternCounts)
    .filter(([_, data]) => data.count > 0)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([pattern, data]) => ({
      pattern,
      example: data.examples[0] || pattern.replace('*', 'example'),
      usage: `${data.count} occurrences`
    }));

  return { patterns };
}

function categorizeFunction(name: string, counts: Record<string, { count: number; examples: string[] }>): void {
  const lower = name.toLowerCase();
  const patterns: Array<[string, RegExp]> = [
    ['get_*', /^get[_A-Z]/],
    ['set_*', /^set[_A-Z]/],
    ['create_*', /^create[_A-Z]/],
    ['delete_*', /^delete[_A-Z]/],
    ['update_*', /^update[_A-Z]/],
    ['is_*', /^is[_A-Z]/],
    ['has_*', /^has[_A-Z]/],
    ['handle_*', /^handle[_A-Z]/],
    ['process_*', /^process[_A-Z]/],
    ['validate_*', /^validate[_A-Z]/],
  ];

  for (const [pattern, regex] of patterns) {
    if (regex.test(name)) {
      counts[pattern].count++;
      if (counts[pattern].examples.length < 3) {
        counts[pattern].examples.push(name);
      }
      break;
    }
  }
}

/**
 * Analyze class naming patterns
 */
async function analyzeClassNaming(files: string[]): Promise<{
  patterns: Array<{ pattern: string; example: string; usage: string }>;
}> {
  const suffixCounts: Record<string, { count: number; examples: string[] }> = {
    '*Service': { count: 0, examples: [] },
    '*Controller': { count: 0, examples: [] },
    '*Handler': { count: 0, examples: [] },
    '*Model': { count: 0, examples: [] },
    '*Repository': { count: 0, examples: [] },
    '*Manager': { count: 0, examples: [] },
    '*Provider': { count: 0, examples: [] },
    '*Factory': { count: 0, examples: [] },
    '*Component': { count: 0, examples: [] },
    '*View': { count: 0, examples: [] },
  };

  const sampleFiles = files.slice(0, 50);

  for (const file of sampleFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      
      // Python class pattern
      const pyMatches = text.matchAll(/class\s+(\w+)/g);
      for (const match of pyMatches) {
        categorizeClass(match[1], suffixCounts);
      }
      
      // TypeScript class pattern
      const tsMatches = text.matchAll(/class\s+(\w+)/g);
      for (const match of tsMatches) {
        categorizeClass(match[1], suffixCounts);
      }
    } catch {}
  }

  const patterns = Object.entries(suffixCounts)
    .filter(([_, data]) => data.count > 0)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([pattern, data]) => ({
      pattern,
      example: data.examples[0] || pattern.replace('*', 'User'),
      usage: `${data.count} classes`
    }));

  return { patterns };
}

function categorizeClass(name: string, counts: Record<string, { count: number; examples: string[] }>): void {
  const suffixes = ['Service', 'Controller', 'Handler', 'Model', 'Repository', 'Manager', 'Provider', 'Factory', 'Component', 'View'];
  
  for (const suffix of suffixes) {
    if (name.endsWith(suffix)) {
      const key = `*${suffix}`;
      counts[key].count++;
      if (counts[key].examples.length < 3) {
        counts[key].examples.push(name);
      }
      break;
    }
  }
}

/**
 * Detect framework patterns
 */
function detectFrameworkPatterns(files: string[], workspaceRoot: string): Array<{
  name: string;
  patterns: string[];
}> {
  const frameworks: Array<{ name: string; patterns: string[] }> = [];
  
  const fileNames = files.map(f => path.basename(f).toLowerCase());
  const dirNames = files.map(f => f.toLowerCase());
  
  // FastAPI detection
  if (fileNames.some(f => f.includes('fastapi')) || dirNames.some(d => d.includes('/api/') || d.includes('/routes/'))) {
    frameworks.push({
      name: 'FastAPI',
      patterns: [
        'Use `@app.get()`, `@app.post()` decorators for routes',
        'Use Pydantic models for request/response schemas',
        'Use `Depends()` for dependency injection',
        'Place routes in `/routes` or `/api` directories'
      ]
    });
  }
  
  // React detection
  if (fileNames.some(f => f.endsWith('.tsx') || f.endsWith('.jsx')) || dirNames.some(d => d.includes('/components/'))) {
    frameworks.push({
      name: 'React',
      patterns: [
        'Components in `/components` directory',
        'Hooks start with `use` prefix (e.g., `useAuth`)',
        'State management with hooks or context',
        'PascalCase for component file names'
      ]
    });
  }
  
  // Next.js detection
  if (dirNames.some(d => d.includes('/pages/') || d.includes('/app/'))) {
    frameworks.push({
      name: 'Next.js',
      patterns: [
        'Pages in `/pages` or `/app` for routing',
        'API routes in `/pages/api` or `/app/api`',
        'Use `getServerSideProps` or server components',
        'Static assets in `/public`'
      ]
    });
  }
  
  // Django detection
  if (fileNames.some(f => f === 'models.py' || f === 'views.py' || f === 'urls.py')) {
    frameworks.push({
      name: 'Django',
      patterns: [
        'Models in `models.py`, views in `views.py`',
        'URL patterns in `urls.py`',
        'Forms in `forms.py`',
        'Admin customization in `admin.py`'
      ]
    });
  }
  
  return frameworks;
}

/**
 * Analyze test naming conventions
 */
function analyzeTestNaming(files: string[], workspaceRoot: string): {
  patterns: Array<{ pattern: string; example: string }>;
} {
  const patterns: Array<{ pattern: string; example: string }> = [];
  const testFiles = files.filter(f => {
    const basename = path.basename(f).toLowerCase();
    return basename.includes('test') || basename.includes('spec');
  });

  const seenPatterns = new Set<string>();

  for (const file of testFiles.slice(0, 10)) {
    const basename = path.basename(file);
    
    if (basename.startsWith('test_') && !seenPatterns.has('test_*.py')) {
      patterns.push({ pattern: 'test_*.py', example: basename });
      seenPatterns.add('test_*.py');
    } else if (basename.endsWith('.test.ts') && !seenPatterns.has('*.test.ts')) {
      patterns.push({ pattern: '*.test.ts', example: basename });
      seenPatterns.add('*.test.ts');
    } else if (basename.endsWith('.spec.ts') && !seenPatterns.has('*.spec.ts')) {
      patterns.push({ pattern: '*.spec.ts', example: basename });
      seenPatterns.add('*.spec.ts');
    } else if (basename.endsWith('_test.py') && !seenPatterns.has('*_test.py')) {
      patterns.push({ pattern: '*_test.py', example: basename });
      seenPatterns.add('*_test.py');
    }
  }

  return { patterns };
}

/**
 * Get fix template for a rule (used in awareness.md for inline guidance)
 */
function getFixTemplate(rule: string): string | null {
  const templates: Record<string, string> = {
    'sec.sql_injection_concat': 'Use parameterized queries: `db.execute(sql, (param,))`',
    'sec.hardcoded_secret': 'Use environment variables: `os.environ.get("SECRET")`',
    'sec.path_traversal': 'Validate paths: `os.path.realpath(path).startswith(allowed_dir)`',
    'sec.open_redirect': 'Validate redirect URLs against allowlist',
    'sec.insecure_random': 'Use `secrets` module for security-sensitive randomness',
    'bug.float_equality': 'Use `math.isclose(a, b)` for float comparison',
    'bug.iteration_modification': 'Iterate over a copy: `for item in list(items):`',
    'errors.swallowed_exception': 'Log exceptions: `except Exception as e: logger.error(e)`',
    'errors.broad_catch': 'Catch specific exceptions: `except ValueError:`',
    'deadcode.unused_variable': 'Remove or prefix with `_`: `_unused = value`',
    'imports.unused': 'Remove unused imports',
    'complexity.high_cyclomatic': 'Extract helper functions to reduce branches',
    'complexity.long_function': 'Split into smaller, focused functions',
  };
  
  return templates[rule] || null;
}

// ============================================================================
// Helper Functions
// ============================================================================

async function extractFileSymbols(
  filePath: string,
  allLinks: DependencyLink[]
): Promise<Array<{ name: string; kind: string; callsInto: string[]; calledBy: string[] }>> {
  const symbols: Array<{ name: string; kind: string; callsInto: string[]; calledBy: string[] }> = [];
  
  try {
    const uri = vscode.Uri.file(filePath);
    const content = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(content).toString('utf-8');
    const lines = text.split('\n');
    const ext = path.extname(filePath).toLowerCase();
    
    if (ext === '.py') {
      for (const line of lines) {
        const funcMatch = line.match(/^def\s+(\w+)\s*\(/);
        if (funcMatch && !funcMatch[1].startsWith('_')) {
          symbols.push({
            name: funcMatch[1],
            kind: 'function',
            callsInto: getSymbolDependencies(filePath, allLinks),
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks)
          });
        }
        
        const classMatch = line.match(/^class\s+(\w+)/);
        if (classMatch) {
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            callsInto: getSymbolDependencies(filePath, allLinks),
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks)
          });
        }
      }
    } else if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
      for (const line of lines) {
        const funcMatch = line.match(/export\s+(?:async\s+)?function\s+(\w+)/);
        if (funcMatch) {
          symbols.push({
            name: funcMatch[1],
            kind: 'function',
            callsInto: getSymbolDependencies(filePath, allLinks),
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks)
          });
        }
        
        const classMatch = line.match(/export\s+(?:abstract\s+)?class\s+(\w+)/);
        if (classMatch) {
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            callsInto: getSymbolDependencies(filePath, allLinks),
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks)
          });
        }
        
        const constMatch = line.match(/export\s+const\s+(\w+)\s*[:=]/);
        if (constMatch) {
          symbols.push({
            name: constMatch[1],
            kind: 'const',
            callsInto: getSymbolDependencies(filePath, allLinks),
            calledBy: getSymbolCallers(constMatch[1], filePath, allLinks)
          });
        }
      }
    }
  } catch {
    // Skip unreadable files
  }
  
  return symbols;
}

function getSymbolDependencies(filePath: string, allLinks: DependencyLink[]): string[] {
  const deps = new Set<string>();
  for (const link of allLinks.filter(l => l.source === filePath)) {
    for (const symbol of link.symbols) {
      deps.add(symbol);
    }
  }
  return Array.from(deps);
}

function getSymbolCallers(symbolName: string, filePath: string, allLinks: DependencyLink[]): string[] {
  return allLinks
    .filter(l => l.target === filePath && l.symbols.includes(symbolName))
    .slice(0, 5)
    .map(l => path.basename(l.source, path.extname(l.source)));
}

function analyzeDirStructure(
  files: string[],
  workspaceRoot: string
): Map<string, { files: string[]; fileTypes: Map<string, number>; purpose?: string }> {
  const structure = new Map<string, { files: string[]; fileTypes: Map<string, number>; purpose?: string }>();

  for (const file of files) {
    const dir = path.dirname(file);
    
    if (!structure.has(dir)) {
      structure.set(dir, { files: [], fileTypes: new Map() });
    }
    
    const info = structure.get(dir)!;
    info.files.push(file);
    
    const ext = path.extname(file);
    info.fileTypes.set(ext, (info.fileTypes.get(ext) || 0) + 1);
  }

  for (const [dir, info] of structure.entries()) {
    info.purpose = inferDirPurpose(path.basename(dir));
  }

  return structure;
}

function inferDirPurpose(dirName: string): string {
  const lower = dirName.toLowerCase();
  const purposes: Record<string, string> = {
    'src': 'Source code',
    'source': 'Source code',
    'lib': 'Libraries',
    'test': 'Tests',
    'tests': 'Tests',
    'spec': 'Tests',
    'docs': 'Documentation',
    'doc': 'Documentation',
    'config': 'Configuration',
    'utils': 'Utilities',
    'helpers': 'Utilities',
    'api': 'API layer',
    'server': 'Server code',
    'client': 'Client code',
    'frontend': 'Frontend',
    'backend': 'Backend',
    'models': 'Data models',
    'views': 'Views/UI',
    'controllers': 'Controllers',
    'services': 'Services',
    'components': 'Components',
  };
  
  return purposes[lower] || 'General';
}

function detectEntryPoints(files: string[], workspaceRoot: string): Array<{ path: string; reason: string }> {
  const entryPoints: Array<{ path: string; reason: string }> = [];
  const entryNames = ['main', 'index', 'app', '__main__', 'server', 'start'];

  for (const file of files) {
    const basename = path.basename(file, path.extname(file)).toLowerCase();
    const relPath = makeRelativePath(file, workspaceRoot);

    if (entryNames.includes(basename)) {
      entryPoints.push({ path: relPath, reason: `Entry point (${basename})` });
    }
  }

  return entryPoints;
}

function analyzeTestOrganization(files: string[], workspaceRoot: string): {
  testFiles: string[];
  testDirs: string[];
  testPatterns: string[];
} {
  const testFiles: string[] = [];
  const testDirs = new Set<string>();
  const testPatterns = new Set<string>();

  for (const file of files) {
    const basename = path.basename(file).toLowerCase();
    const relPath = makeRelativePath(file, workspaceRoot);
    const dir = path.dirname(relPath);

    if (basename.includes('test') || basename.includes('spec')) {
      testFiles.push(relPath);
      if (dir.includes('test')) testDirs.add(dir);
      
      if (basename.startsWith('test_')) testPatterns.add('test_*.py');
      else if (basename.endsWith('.test.ts')) testPatterns.add('*.test.ts');
      else if (basename.endsWith('.spec.ts')) testPatterns.add('*.spec.ts');
    }
  }

  return { testFiles, testDirs: Array.from(testDirs), testPatterns: Array.from(testPatterns) };
}

async function getDetailedDependencyData(
  workspaceRoot: vscode.Uri,
  files: string[],
  outputChannel: vscode.OutputChannel
): Promise<{
  stats: Map<string, { inDegree: number; outDegree: number }>;
  links: DependencyLink[];
}> {
  const stats = new Map<string, { inDegree: number; outDegree: number }>();
  let links: DependencyLink[] = [];

  try {
    if (files.length === 0) return { stats, links };

    const analyzer = new DependencyAnalyzer();
    links = await analyzer.analyzeDependencies(files);

    for (const file of files) {
      stats.set(file, { inDegree: 0, outDegree: 0 });
    }

    for (const link of links) {
      const sourceStats = stats.get(link.source);
      const targetStats = stats.get(link.target);
      if (sourceStats) sourceStats.outDegree++;
      if (targetStats) targetStats.inDegree++;
    }

    outputChannel.appendLine(`[KB] Analyzed ${links.length} dependencies`);
  } catch (error) {
    outputChannel.appendLine(`[KB] Dependency analysis failed: ${error}`);
  }

  return { stats, links };
}

async function discoverWorkspaceFiles(workspaceRoot: vscode.Uri): Promise<string[]> {
  const files: string[] = [];
  const extensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.cs', '.cpp', '.c'];

  try {
    const pattern = new vscode.RelativePattern(workspaceRoot, '**/*');
    const uris = await vscode.workspace.findFiles(pattern, '**/node_modules/**', 500);

    for (const uri of uris) {
      const ext = path.extname(uri.fsPath).toLowerCase();
      if (extensions.includes(ext)) {
        files.push(uri.fsPath);
      }
    }
  } catch {
    // Ignore errors
  }

  return files;
}

function makeRelativePath(absPath: string, workspaceRoot: string): string {
  if (absPath.startsWith(workspaceRoot)) {
    return absPath.substring(workspaceRoot.length).replace(/^[\\\/]/, '');
  }
  return path.basename(absPath);
}

// ============================================================================
// ALIGNMENTS.json - Issue Tracking & Resolution Log (in workspace root)
// ============================================================================

export interface AlignmentEntry {
  timestamp: string;
  issue: string;
  files: string[];
  resolution: string;
}

interface AlignmentsFile {
  description: string;
  alignments: AlignmentEntry[];
}

/**
 * Add a new alignment entry to ALIGNMENTS.json in workspace root
 * 
 * This file tracks issues users have encountered and (once edited by human)
 * how they were resolved. Sorted by reverse timestamp so most recent 
 * entries are at the top for easy reference.
 */
export async function addAlignmentEntry(
  workspaceRoot: vscode.Uri,
  entry: { issue: string; files: string[]; resolution: string },
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const alignmentsFile = vscode.Uri.joinPath(workspaceRoot, 'ALIGNMENTS.json');

  // Read existing file or create new structure
  let alignments: AlignmentsFile;
  try {
    const bytes = await vscode.workspace.fs.readFile(alignmentsFile);
    alignments = JSON.parse(Buffer.from(bytes).toString('utf-8'));
  } catch {
    // File doesn't exist yet - create initial structure
    alignments = {
      description: "Issue tracking log - records problems encountered and their resolutions (edit 'resolution' field after verifying fix)",
      alignments: []
    };
  }

  // Create new entry with timestamp
  const newEntry: AlignmentEntry = {
    timestamp: new Date().toISOString(),
    issue: entry.issue,
    files: entry.files,
    resolution: entry.resolution
  };

  // Add to beginning (most recent first)
  alignments.alignments.unshift(newEntry);

  // Keep only last 50 entries to prevent file from growing too large
  if (alignments.alignments.length > 50) {
    alignments.alignments = alignments.alignments.slice(0, 50);
  }

  // Write back with pretty formatting for human editability
  const content = JSON.stringify(alignments, null, 2);
  await vscode.workspace.fs.writeFile(alignmentsFile, Buffer.from(content, 'utf-8'));

  outputChannel.appendLine(`[KB] Added alignment entry to ALIGNMENTS.json: "${entry.issue.substring(0, 50)}..."`);
}

/**
 * Check if ALIGNMENTS.json exists in workspace root
 */
export async function alignmentsFileExists(
  workspaceRoot: vscode.Uri
): Promise<boolean> {
  const alignmentsFile = vscode.Uri.joinPath(workspaceRoot, 'ALIGNMENTS.json');
  try {
    await vscode.workspace.fs.stat(alignmentsFile);
    return true;
  } catch {
    return false;
  }
}

/**
 * Initialize ALIGNMENTS.json in workspace root if it doesn't exist.
 * Creates the proper structure for tracking AI issues.
 */
export async function initializeAlignmentsFile(
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const alignmentsFile = vscode.Uri.joinPath(workspaceRoot, 'ALIGNMENTS.json');
  
  // Check if file already exists
  try {
    await vscode.workspace.fs.stat(alignmentsFile);
    outputChannel.appendLine('[KB] ALIGNMENTS.json already exists');
    return;
  } catch {
    // File doesn't exist, create it
  }
  
  // Create alignments file with proper structure
  const initialContent: AlignmentsFile = {
    description: "Issue tracking log - records problems encountered and their resolutions (edit 'resolution' field after verifying fix)",
    alignments: []
  };
  const content = JSON.stringify(initialContent, null, 2);
  await vscode.workspace.fs.writeFile(alignmentsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine('[KB] Created ALIGNMENTS.json');
}
