import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';
import { loadGrammarsOnce, LoadedGrammars } from '../tsParser';
import { ensureGitignoreForTarget } from '../services/gitignoreService';
import { GitignoreTarget } from '../services/aspectSettings';
import { 
  extractPythonSymbols, 
  extractTSJSSymbols, 
  extractJavaSymbols, 
  extractCSharpSymbols,
  ExtractedSymbol
} from '../importExtractors';

// ============================================================================
// KB Size Budgets & Invariants
// ============================================================================

/**
 * Maximum line counts for each KB file.
 * These ensure the files stay useful for AI context windows.
 */
const KB_SIZE_LIMITS = {
  architecture: 200,  // Guardrail file - most critical, keep concise
  map: 300,           // Symbol index - can be denser
  context: 200        // Flow file - focus on key relationships
} as const;

/**
 * Maximum items per section to prevent runaway lists.
 */
const KB_SECTION_LIMITS = {
  hubs: 12,
  hubDetails: 3,
  entryPoints: 10,
  directories: 12,
  dataModels: 15,
  symbolsPerFile: 10,
  filesInSymbolIndex: 30,
  clusters: 6,
  chains: 8,
  integrations: 4
} as const;

/**
 * Trim content to stay within line budget, preserving structure.
 * Adds a note if content was truncated.
 */
function enforceLineBudget(content: string, maxLines: number, fileName: string): string {
  const lines = content.split('\n');
  if (lines.length <= maxLines) {
    return content;
  }
  
  // Find a good truncation point (end of a section)
  let truncateAt = maxLines - 3;
  for (let i = maxLines - 3; i > maxLines - 20 && i > 0; i--) {
    if (lines[i].startsWith('##') || lines[i].startsWith('---')) {
      truncateAt = i;
      break;
    }
  }
  
  const truncated = lines.slice(0, truncateAt);
  truncated.push('');
  truncated.push(`_[Content truncated at ${maxLines} lines. ${lines.length - truncateAt} lines omitted.]_`);
  truncated.push('');
  truncated.push(`_Generated: ${new Date().toISOString()}_`);
  
  return truncated.join('\n');
}

/**
 * Pre-load all file contents into a cache to avoid repeated file reads.
 * This is a major performance optimization - we read each file once and
 * share the content across all KB generators.
 */
async function preloadFileContents(files: string[]): Promise<Map<string, string>> {
  const cache = new Map<string, string>();
  const BATCH_SIZE = 30;
  
  for (let i = 0; i < files.length; i += BATCH_SIZE) {
    const batch = files.slice(i, i + BATCH_SIZE);
    const results = await Promise.allSettled(
      batch.map(async (file) => {
        try {
          const uri = vscode.Uri.file(file);
          const content = await vscode.workspace.fs.readFile(uri);
          return { file, content: Buffer.from(content).toString('utf8') };
        } catch {
          return { file, content: '' };
        }
      })
    );
    
    for (const result of results) {
      if (result.status === 'fulfilled' && result.value.content) {
        cache.set(result.value.file, result.value.content);
      }
    }
  }
  
  return cache;
}

/**
 * Aspect Code Knowledge Base v3 - Architectural Intelligence for AI Coding Agents
 * 
 * STRUCTURE (3 files):
 * - architecture.md: The Guardrail - Project layout, high-risk hubs, entry points
 * - map.md: The Context - Symbol index with signatures, data models, conventions
 * - context.md: The Flow - Module clusters, data flows, external integrations
 * 
 * Design philosophy:
 * - DEFENSIVE GUARDRAILS: Orgalion-style warnings on high-risk hubs ("load-bearing walls")
 * - CONTEXTUAL DENSITY: V2-style symbol mapping with signatures for complex edits
 * - NO LINTING DISTRACTIONS: No awareness.md, no findings lists that cause regressions
 * 
 * KB-Enriching Rules (architectural intelligence, not issues):
 * - arch.entry_point: HTTP handlers, CLI commands, main functions, event listeners
 * - arch.external_integration: HTTP clients, DB connections, message queues, SDKs
 * - arch.data_model: ORM models, dataclasses, interfaces, schemas
 * - arch.global_state_usage: Mutable global state, singletons, service locators
 * - imports.cycle.advanced: Circular import dependencies
 * - architecture.critical_dependency: High-impact hub files
 * - analysis.change_impact: Change blast radius analysis
 */

// KB-enriching rule IDs
const KB_ENRICHING_RULES = {
  // Core KB rules (used in context.md and map.md)
  ENTRY_POINT: 'arch.entry_point',
  EXTERNAL_INTEGRATION: 'arch.external_integration',
  DATA_MODEL: 'arch.data_model',
  // Extended KB rules (used in architecture.md)
  GLOBAL_STATE: 'arch.global_state_usage',
  IMPORT_CYCLE: 'imports.cycle.advanced',
  CRITICAL_DEPENDENCY: 'architecture.critical_dependency',
  CHANGE_IMPACT: 'analysis.change_impact',
};

interface KBEnrichingFinding {
  file: string;
  message: string;
}

/**
 * Extract KB-enriching findings by rule type.
 * These findings provide architectural intelligence rather than issue reports.
 */
function extractKBEnrichingFindings(
  state: AspectCodeState,
  ruleId: string
): KBEnrichingFinding[] {
  const seen = new Set<string>();
  return state.s.findings
    .filter(f => f.code === ruleId)
    .map(f => ({
      file: f.file,
      message: f.message,
    }))
    .filter(f => {
      const key = `${f.file}|${f.message}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });
}

/**
 * Automatically regenerate KB files when findings change.
 * Called after incremental validation or full validation.
 */
export async function autoRegenerateKBFiles(
  state: AspectCodeState,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
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
    await generateKnowledgeBase(workspaceRoot, state, scoreResult, outputChannel, context);
    
    outputChannel.appendLine('[KB] Auto-regenerated after examination update');
  } catch (error) {
    outputChannel.appendLine(`[KB] Auto-regeneration failed (non-critical): ${error}`);
  }
}

/**
 * Generates the .aspect/ knowledge base directory with architectural intelligence.
 * 
 * V3 Files generated:
 * - architecture.md: The Guardrail - layout, hubs, entry points
 * - map.md: The Context - symbols, data models, conventions
 * - context.md: The Flow - clusters, flows, integrations
 */
export async function generateKnowledgeBase(
  workspaceRoot: vscode.Uri,
  state: AspectCodeState,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
): Promise<void> {
  const aspectCodeDir = vscode.Uri.joinPath(workspaceRoot, '.aspect');
  
  // Ensure .aspect directory exists
  try {
    await vscode.workspace.fs.createDirectory(aspectCodeDir);
  } catch (e) {
    // Directory may already exist, ignore
  }

  // Prompt user for .aspect/ gitignore preference (opt-in per target)
  const aspectTarget: GitignoreTarget = '.aspect/';
  await ensureGitignoreForTarget(workspaceRoot, aspectTarget, outputChannel);

  const kbStart = Date.now();
  outputChannel.appendLine('[KB] Generating V3 knowledge base in .aspect/');

  // Load tree-sitter grammars if context is available
  let grammars: LoadedGrammars | null = null;
  if (context) {
    try {
      const tGrammar = Date.now();
      grammars = await loadGrammarsOnce(context, outputChannel);
      outputChannel.appendLine(`[KB] Tree-sitter grammars loaded (${Date.now() - tGrammar}ms)`);
    } catch (e) {
      outputChannel.appendLine(`[KB] Tree-sitter grammars not available, using regex fallback: ${e}`);
    }
  }

  // Pre-fetch shared data
  const tDiscover = Date.now();
  const files = await discoverWorkspaceFiles(workspaceRoot);
  outputChannel.appendLine(`[KB][Perf] discoverWorkspaceFiles: ${files.length} files in ${Date.now() - tDiscover}ms`);
  
  // Pre-load all file contents once to avoid repeated reads (major perf optimization)
  const tCache = Date.now();
  const fileContentCache = await preloadFileContents(files);
  outputChannel.appendLine(`[KB][Perf] preloadFileContents: ${fileContentCache.size} files cached in ${Date.now() - tCache}ms`);
  
  const tDeps = Date.now();
  const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, files, outputChannel, fileContentCache);
  outputChannel.appendLine(`[KB][Perf] getDetailedDependencyData: ${allLinks.length} links in ${Date.now() - tDeps}ms`);

  // Generate all KB files in parallel (V3: 3 files)
  const tWrite = Date.now();
  await Promise.all([
    generateArchitectureFile(aspectCodeDir, state, workspaceRoot, files, depData, allLinks, outputChannel, fileContentCache),
    generateMapFile(aspectCodeDir, state, workspaceRoot, files, depData, allLinks, outputChannel, grammars, fileContentCache),
    generateContextFile(aspectCodeDir, state, workspaceRoot, files, allLinks, outputChannel, fileContentCache)
  ]);
  outputChannel.appendLine(`[KB][Perf] write KB files: ${Date.now() - tWrite}ms`);

  outputChannel.appendLine(`[KB] Knowledge base generation complete (3 files) in ${Date.now() - kbStart}ms`);
}

export type ImpactSummary = {
  file: string;
  dependents_count: number;
  top_dependents: Array<{ file: string; dependent_count: number }>;
  hub_risk: 'LOW' | 'MEDIUM' | 'HIGH';
  generated_at: string;
};

/**
 * Computes a lightweight impact summary for a single file.
 * Used by the VS Code command that copies impact analysis to clipboard.
 */
export async function computeImpactSummaryForFile(
  workspaceRoot: vscode.Uri,
  absoluteFilePath: string,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
): Promise<ImpactSummary | null> {
  try {
    const files = await discoverWorkspaceFiles(workspaceRoot);
    if (files.length === 0) return null;

    const normalizedTarget = path.resolve(absoluteFilePath);
    const fileContentCache = await preloadFileContents(files);
    const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, files, outputChannel, fileContentCache);

    const targetClass = classifyFile(normalizedTarget, workspaceRoot.fsPath);
    if (targetClass === 'third_party') {
      return {
        file: makeRelativePath(normalizedTarget, workspaceRoot.fsPath),
        dependents_count: 0,
        top_dependents: [],
        hub_risk: 'LOW',
        generated_at: new Date().toISOString()
      };
    }

    const dependentAbs = dedupe(
      allLinks
        .filter(l => l.target && path.resolve(l.target) === normalizedTarget)
        .map(l => l.source)
        .filter(Boolean)
        .filter(s => s !== normalizedTarget)
        .filter(s => classifyFile(s, workspaceRoot.fsPath) !== 'third_party')
    );

    // Prefer showing app/test dependents; if none, fall back to whatever we found.
    const appOrTestDependents = dependentAbs.filter(s => {
      const c = classifyFile(s, workspaceRoot.fsPath);
      return c === 'app' || c === 'test';
    });
    const dependentsToUse = appOrTestDependents.length > 0 ? appOrTestDependents : dependentAbs;

    const dependentsWithCounts = dependentsToUse
      .map(dep => ({
        abs: dep,
        dependent_count: depData.get(dep)?.inDegree ?? 0
      }))
      .sort((a, b) => b.dependent_count - a.dependent_count);

    const dependentsCount = dependentsWithCounts.length;
    const hubRisk: ImpactSummary['hub_risk'] = dependentsCount >= 5 ? 'HIGH' : dependentsCount >= 3 ? 'MEDIUM' : 'LOW';

    const topDependents = dependentsWithCounts.slice(0, 5).map(d => ({
      file: makeRelativePath(d.abs, workspaceRoot.fsPath),
      dependent_count: d.dependent_count
    }));

    // If the target is itself a test file, keep the risk conservative.
    const hubRiskAdjusted: ImpactSummary['hub_risk'] = targetClass === 'test' && hubRisk === 'HIGH' ? 'MEDIUM' : hubRisk;

    return {
      file: makeRelativePath(normalizedTarget, workspaceRoot.fsPath),
      dependents_count: dependentsCount,
      top_dependents: topDependents,
      hub_risk: hubRiskAdjusted,
      generated_at: new Date().toISOString()
    };
  } catch (e) {
    outputChannel.appendLine(`[Impact] Impact summary failed: ${e}`);
    return null;
  }
}

// ============================================================================
// architecture.md - The Guardrail (V3)
// ============================================================================

/**
 * Generate .aspect/architecture.md - The Guardrail
 * 
 * Purpose: Defensive guide to project structure and high-risk zones.
 * Answers: "Where are the load-bearing walls?" and "What should I not break?"
 * 
 * Combines:
 * - V2 structure.md directory layout
 * - Orgalion hotspot ranking (in-degree + out-degree + finding count)
 * - Strong defensive language on hubs
 */
async function generateArchitectureFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  depData: Map<string, { inDegree: number; outDegree: number }>,
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel,
  fileContentCache: Map<string, string>
): Promise<void> {
  let content = '# Architecture\n\n';
  content += '_Read this first. Describes the project layout and "Do Not Break" zones._\n\n';

  if (files.length === 0) {
    content += '_No source files found._\n';
  } else {
    // Quick stats
    const totalEdges = allLinks.length;
    // Filter out self-references (source === target) which are bugs in dependency detection
    const circularLinks = allLinks.filter(l => l.type === 'circular' && l.source !== l.target);
    const cycleCount = Math.ceil(circularLinks.length / 2);
    
    content += `**Files:** ${files.length} | **Dependencies:** ${totalEdges} | **Cycles:** ${cycleCount}\n\n`;

    // Filter to app files for architectural views
    const appFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'app');
    const testFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'test');
    const findings = state.s.findings;

    // Build finding counts per file for Orgalion-style hotspot ranking
    // Note: findings are used as a lightweight "friction" signal; severity is not used.
    const findingCounts = new Map<string, number>();
    for (const finding of findings) {
      if (classifyFile(finding.file, workspaceRoot.fsPath) !== 'app') continue;
      findingCounts.set(finding.file, (findingCounts.get(finding.file) || 0) + 1);
    }

    // ============================================================
    // HIGH-RISK ARCHITECTURAL HUBS (Orgalion + V2 merged)
    // ============================================================
    // Ranking: (inDegree + outDegree) * 2 + findingCount
    const hubs = Array.from(depData.entries())
      .filter(([file]) => isStructuralAppFile(file, workspaceRoot.fsPath))
      .map(([file, info]) => {
        const depScore = info.inDegree + info.outDegree;
        const fc = findingCounts.get(file) || 0;
        const hotspotScore = (depScore * 2) + fc;
        return {
          file,
          inDegree: info.inDegree,
          outDegree: info.outDegree,
          totalDegree: depScore,
          findings: fc,
          hotspotScore
        };
      })
      .filter(h => h.totalDegree > 2 || h.findings > 0)
      .sort((a, b) => b.hotspotScore - a.hotspotScore)
      .slice(0, KB_SECTION_LIMITS.hubs);

    if (hubs.length > 0) {
      content += '## ⚠️ High-Risk Architectural Hubs\n\n';
      content += '> **These files are architectural load-bearing walls.**\n';
      content += '> Modify with extreme caution. Do not change signatures without checking `map.md`.\n\n';
      
      content += '| Rank | File | Imports | Imported By | Risk |\n';
      content += '|------|------|---------|-------------|------|\n';
      
      for (let i = 0; i < hubs.length; i++) {
        const hub = hubs[i];
        const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
        // Calculate app-file-only import count for consistency with details section
        const appImportCount = dedupe(
          allLinks
            .filter(l => l.target === hub.file && l.source !== hub.file)
            .filter(l => classifyFile(l.source, workspaceRoot.fsPath) === 'app'),
          l => l.source
        ).length;
        const risk = appImportCount > 8 ? '🔴 High' :
                     appImportCount > 4 || hub.findings > 3 ? '🟡 Medium' : '🟢 Low';
        content += `| ${i + 1} | \`${relPath}\` | ${hub.outDegree} | ${appImportCount} | ${risk} |\n`;
      }
      content += '\n';

      // Show top hub details with blast radius
      content += '### Hub Details & Blast Radius\n\n';
      content += '_Blast radius = direct dependents + their dependents (2 levels)._\n\n';
      
      for (let i = 0; i < Math.min(KB_SECTION_LIMITS.hubDetails, hubs.length); i++) {
        const hub = hubs[i];
        const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
        
        // Get direct importers (first-level blast radius) - only app files
        const directImporters = dedupe(
          allLinks
            .filter(l => l.target === hub.file && l.source !== hub.file)
            .filter(l => classifyFile(l.source, workspaceRoot.fsPath) === 'app'),
          l => l.source
        );
        
        // Get second-level importers (files that import the direct importers)
        const secondLevelImporters = new Set<string>();
        for (const importer of directImporters.slice(0, 10)) {
          const indirectLinks = allLinks.filter(l => 
            l.target === importer.source && 
            l.source !== hub.file &&
            classifyFile(l.source, workspaceRoot.fsPath) === 'app'
          );
          for (const il of indirectLinks.slice(0, 3)) {
            secondLevelImporters.add(il.source);
          }
        }
        
        // Use directImporters.length for consistency (same filtered source for all metrics)
        const directDependentCount = directImporters.length;
        const totalBlastRadius = directDependentCount + secondLevelImporters.size;
        
        content += `**${i + 1}. \`${relPath}\`** — Blast radius: ${totalBlastRadius} files\n`;
        content += `   - Direct dependents: ${directDependentCount}\n`;
        content += `   - Indirect dependents: ~${secondLevelImporters.size}\n`;
        
        // Show actual importers list
        if (directImporters.length > 0) {
          const shownCount = Math.min(5, directImporters.length);
          content += `\n   Imported by (${directDependentCount} files):\n`;
          for (const imp of directImporters.slice(0, shownCount)) {
            const impRel = makeRelativePath(imp.source, workspaceRoot.fsPath);
            content += `   - \`${impRel}\`\n`;
          }
          if (directImporters.length > shownCount) {
            content += `   - _...and ${directImporters.length - shownCount} more_\n`;
          }
        }
        content += '\n';
      }
    }

    // ============================================================
    // ENTRY POINTS (Language-aware content analysis)
    // ============================================================
    const ruleEntryPoints = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.ENTRY_POINT)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    
    // Use content-based detection for accurate categorization
    const contentBasedEntryPoints = detectEntryPointsWithContent(appFiles, workspaceRoot.fsPath, fileContentCache);
    
    if (ruleEntryPoints.length > 0 || contentBasedEntryPoints.length > 0) {
      content += '## Entry Points\n\n';
      content += '_Where code execution begins. Categorized by type with detection confidence._\n\n';
      
      // Group content-based entry points by category
      const runtimeEntries = contentBasedEntryPoints.filter(e => e.category === 'runtime');
      const toolingEntries = contentBasedEntryPoints.filter(e => e.category === 'tooling');
      const barrelEntries = contentBasedEntryPoints.filter(e => e.category === 'barrel');
      
      // Also add rule-based HTTP handlers if not already covered
      const httpHandlers = dedupe(
        ruleEntryPoints.filter(f => f.message.includes('HTTP')),
        f => f.file
      );
      
      // Merge rule-based HTTP handlers into runtime (deduped)
      const runtimePaths = new Set(runtimeEntries.map(e => e.path));
      for (const handler of httpHandlers) {
        const relPath = makeRelativePath(handler.file, workspaceRoot.fsPath);
        if (!runtimePaths.has(relPath)) {
          runtimeEntries.push({
            path: relPath,
            reason: handler.message.replace('HTTP entry point: ', ''),
            confidence: 'high',
            category: 'runtime',
            routeCount: 1
          });
        }
      }
      
      // ---- RUNTIME ENTRY POINTS ----
      if (runtimeEntries.length > 0) {
        content += '### Runtime Entry Points\n\n';
        content += '_Server handlers, API routes, application entry._\n\n';
        
        // Top 10 by route count, then confidence
        const topRuntime = runtimeEntries.slice(0, KB_SECTION_LIMITS.entryPoints);
        for (const entry of topRuntime) {
          const confIcon = entry.confidence === 'high' ? '🟢' : 
                          entry.confidence === 'medium' ? '🟡' : '🟠';
          content += `- ${confIcon} \`${entry.path}\`: ${entry.reason}\n`;
        }
        if (runtimeEntries.length > KB_SECTION_LIMITS.entryPoints) {
          content += `- _...and ${runtimeEntries.length - KB_SECTION_LIMITS.entryPoints} more_\n`;
        }
        content += '\n';
      }
      
      // ---- RUNNABLE SCRIPTS / TOOLING ----
      if (toolingEntries.length > 0) {
        content += '### Runnable Scripts / Tooling\n\n';
        content += '_CLI tools, build scripts, standalone utilities._\n\n';
        
        const topTooling = toolingEntries.slice(0, 5);
        for (const entry of topTooling) {
          const confIcon = entry.confidence === 'high' ? '🟢' : 
                          entry.confidence === 'medium' ? '🟡' : '🟠';
          content += `- ${confIcon} \`${entry.path}\`: ${entry.reason}\n`;
        }
        if (toolingEntries.length > 5) {
          content += `- _...and ${toolingEntries.length - 5} more_\n`;
        }
        content += '\n';
      }
      
      // ---- BARREL/INDEX EXPORTS ----
      if (barrelEntries.length > 0) {
        content += '### Barrel/Index Exports\n\n';
        content += '_Re-export hubs that aggregate module exports._\n\n';
        
        const topBarrels = barrelEntries.slice(0, 5);
        for (const entry of topBarrels) {
          content += `- 🟡 \`${entry.path}\`: ${entry.reason}\n`;
        }
        if (barrelEntries.length > 5) {
          content += `- _...and ${barrelEntries.length - 5} more_\n`;
        }
        content += '\n';
      }
    }

    // ============================================================
    // DIRECTORY LAYOUT
    // ============================================================
    const dirStructure = analyzeDirStructure(appFiles, workspaceRoot.fsPath);
    const topDirs = Array.from(dirStructure.entries())
      .filter(([_, info]) => info.files.length >= 2)
      .slice(0, 12);

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

    // ============================================================
    // CIRCULAR DEPENDENCIES (architectural issue, keep it)
    // ============================================================
    const appCircularLinks = circularLinks.filter(l => 
      isStructuralAppFile(l.source, workspaceRoot.fsPath) &&
      isStructuralAppFile(l.target, workspaceRoot.fsPath) &&
      l.source !== l.target  // Filter out self-references (bug in dependency detection)
    );
    
    // Also get cycle findings from the rule for additional context
    const cycleFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.IMPORT_CYCLE);
    
    if (appCircularLinks.length > 0 || cycleFindings.length > 0) {
      content += '## ⚠️ Circular Dependencies\n\n';
      content += '_Bidirectional imports that create tight coupling._\n\n';
      
      const processedPairs = new Set<string>();
      let cycleIndex = 0;
      
      for (const link of appCircularLinks) {
        if (cycleIndex >= 5) break;
        
        // Skip self-references and already processed pairs
        if (link.source === link.target) continue;
        
        const pairKey = [link.source, link.target].sort().join('::');
        if (processedPairs.has(pairKey)) continue;
        processedPairs.add(pairKey);
        
        const sourceRel = makeRelativePath(link.source, workspaceRoot.fsPath);
        const targetRel = makeRelativePath(link.target, workspaceRoot.fsPath);
        
        content += `- \`${sourceRel}\` ↔ \`${targetRel}\`\n`;
        cycleIndex++;
      }
      content += '\n';
    }

    // ============================================================
    // GLOBAL STATE (from arch.global_state_usage rule)
    // ============================================================
    const globalStateFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.GLOBAL_STATE)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    
    if (globalStateFindings.length > 0) {
      content += '## Shared State\n\n';
      content += '_Global/singleton state locations. Consider thread-safety and testability._\n\n';
      
      for (const finding of globalStateFindings.slice(0, 8)) {
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${finding.message}\n`;
      }
      if (globalStateFindings.length > 8) {
        content += `- _...and ${globalStateFindings.length - 8} more_\n`;
      }
      content += '\n';
    }

    // ============================================================
    // CRITICAL DEPENDENCIES (from architecture.critical_dependency rule)
    // ============================================================
    const criticalDepFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.CRITICAL_DEPENDENCY)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    
    if (criticalDepFindings.length > 0) {
      content += '## Critical Dependencies\n\n';
      content += '_Symbols with many dependents. Changes here have wide blast radius._\n\n';
      
      for (const finding of criticalDepFindings.slice(0, 6)) {
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${finding.message}\n`;
      }
      if (criticalDepFindings.length > 6) {
        content += `- _...and ${criticalDepFindings.length - 6} more_\n`;
      }
      content += '\n';
    }

    // ============================================================
    // CHANGE IMPACT ANALYSIS (from analysis.change_impact rule)
    // ============================================================
    const changeImpactFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.CHANGE_IMPACT)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    
    if (changeImpactFindings.length > 0) {
      content += '## Change Impact\n\n';
      content += '_High-impact symbols. Review carefully before modifying._\n\n';
      
      for (const finding of changeImpactFindings.slice(0, 6)) {
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${finding.message}\n`;
      }
      if (changeImpactFindings.length > 6) {
        content += `- _...and ${changeImpactFindings.length - 6} more_\n`;
      }
      content += '\n';
    }

    // ============================================================
    // TESTS SUMMARY (brief)
    // ============================================================
    const testInfo = analyzeTestOrganization(testFiles.length > 0 ? testFiles : files, workspaceRoot.fsPath);
    if (testInfo.testFiles.length > 0) {
      content += '## Tests\n\n';
      content += `**Test files:** ${testInfo.testFiles.length}`;
      if (testInfo.testDirs.length > 0) {
        content += ` | **Dirs:** ${testInfo.testDirs.slice(0, 2).join(', ')}`;
      }
      content += '\n\n';
    }
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  // Enforce size budget before writing
  const finalContent = enforceLineBudget(content, KB_SIZE_LIMITS.architecture, 'architecture.md');
  
  const architectureFile = vscode.Uri.joinPath(aspectCodeDir, 'architecture.md');
  await vscode.workspace.fs.writeFile(architectureFile, Buffer.from(finalContent, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated architecture.md (${finalContent.split('\n').length} lines)`);
}

// ============================================================================
// map.md - The Context (V3)
// ============================================================================

/**
 * Generate .aspect/map.md - The Context
 * 
 * Purpose: Dense symbol index with signatures for complex edits.
 * Answers: "What types exist?" and "What's the signature of this function?"
 * 
 * Combines:
 * - V2 code.md symbol index (enhanced with signatures)
 * - V2 conventions.md naming patterns and framework idioms
 * - Data models with field details
 */
async function generateMapFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  depData: Map<string, { inDegree: number; outDegree: number }>,
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel,
  grammars: LoadedGrammars | null | undefined,
  fileContentCache: Map<string, string>
): Promise<void> {
  let content = '# Map\n\n';
  content += '_Symbol index with signatures and conventions. Use to find types, functions, and coding patterns._\n\n';

  const findings = state.s.findings;
  const appFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'app');
  
  // ============================================================
  // DATA MODELS (with signatures/fields)
  // ============================================================
  const dataModels = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.DATA_MODEL);
  
  if (dataModels.length > 0) {
    content += '## Data Models\n\n';
    content += '_Core data structures. Check these before modifying data handling._\n\n';
    
    // Group by type for organization
    const ormModels = dataModels.filter(f => 
      f.message.includes('ORM') || f.message.includes('Entity') || f.message.includes('SQLModel')
    );
    const dataClasses = dataModels.filter(f => 
      f.message.includes('Data Class') || f.message.includes('dataclass') || 
      f.message.includes('Pydantic') || f.message.includes('BaseModel')
    );
    const interfaces = dataModels.filter(f => 
      f.message.includes('Interface') || f.message.includes('Type Alias') || f.message.includes('type ')
    );
    const other = dataModels.filter(f => 
      !ormModels.includes(f) && !dataClasses.includes(f) && !interfaces.includes(f)
    );

    // Pre-extract all model signatures in parallel for performance
    const allModelsToExtract = [
      ...ormModels.slice(0, 15).map(m => ({ model: m, type: 'orm' })),
      ...dataClasses.slice(0, 15).map(m => ({ model: m, type: 'dataclass' })),
      ...interfaces.slice(0, 15).map(m => ({ model: m, type: 'interface' }))
    ];
    
    // Extract signatures synchronously using cached content
    const signatureMap = new Map<string, { modelInfo: string; signature: string | null }>();
    for (const { model } of allModelsToExtract) {
      const modelInfo = model.message.replace('Data model: ', '').replace('ORM model: ', '');
      const signature = extractModelSignature(model.file, modelInfo, fileContentCache);
      signatureMap.set(model.file, { modelInfo, signature });
    }

    // Show models with enhanced signatures
    if (ormModels.length > 0) {
      content += '### ORM / Database Models\n\n';
      for (const model of ormModels.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const data = signatureMap.get(model.file);
        if (data?.signature) {
          content += `**\`${relPath}\`**: \`${data.signature}\`\n\n`;
        } else {
          const modelInfo = model.message.replace('Data model: ', '').replace('ORM model: ', '');
          content += `**\`${relPath}\`**: ${modelInfo}\n\n`;
        }
      }
    }

    if (dataClasses.length > 0) {
      content += '### Pydantic / Data Classes\n\n';
      for (const model of dataClasses.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const data = signatureMap.get(model.file);
        if (data?.signature) {
          content += `**\`${relPath}\`**: \`${data.signature}\`\n\n`;
        } else {
          // Clean up the model info for display
          let modelInfo = model.message.replace('Data model: ', '');
          // Remove verbose descriptors like "(dataclass) - class"
          modelInfo = modelInfo.replace(/\s*\([^)]+\)\s*-\s*\w+\s*$/, '');
          content += `**\`${relPath}\`**: ${modelInfo}\n\n`;
        }
      }
    }

    if (interfaces.length > 0) {
      content += '### TypeScript Interfaces & Types\n\n';
      for (const model of interfaces.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const data = signatureMap.get(model.file);
        if (data?.signature) {
          content += `**\`${relPath}\`**: \`${data.signature}\`\n\n`;
        } else {
          const modelInfo = model.message.replace('Data model: ', '');
          content += `**\`${relPath}\`**: ${modelInfo}\n\n`;
        }
      }
    }

    if (other.length > 0) {
      content += '### Other Data Structures\n\n';
      for (const model of other.slice(0, 10)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`: ${model.message}\n`;
      }
      content += '\n';
    }
  }

  // ============================================================
  // SYMBOL INDEX (with enhanced signatures)
  // ============================================================
  const relevantFiles = new Set<string>();
  for (const finding of findings) {
    relevantFiles.add(finding.file);
  }
  for (const link of allLinks) {
    relevantFiles.add(link.source);
    relevantFiles.add(link.target);
  }

  if (relevantFiles.size > 0) {
    content += '## Symbol Index\n\n';
    content += '_Functions, classes, and exports with call relationships._\n\n';

    // Build set of files with arch.* findings for boosting
    const archFiles = new Set<string>();
    for (const model of dataModels) {
      if (classifyFile(model.file, workspaceRoot.fsPath) === 'app') {
        archFiles.add(model.file);
      }
    }
    const entryPointFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.ENTRY_POINT);
    const integrationFindings = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.EXTERNAL_INTEGRATION);
    for (const f of entryPointFindings) {
      if (classifyFile(f.file, workspaceRoot.fsPath) === 'app') archFiles.add(f.file);
    }
    for (const f of integrationFindings) {
      if (classifyFile(f.file, workspaceRoot.fsPath) === 'app') archFiles.add(f.file);
    }

    // Score files by importance
    const fileScores = new Map<string, number>();
    for (const file of relevantFiles) {
      const kind = classifyFile(file, workspaceRoot.fsPath);
      if (kind === 'third_party') continue;

      const base = kind === 'test' ? -10 : 0;
      const archBoost = archFiles.has(file) ? 25 : 0;
      const kbEnrichingRuleIds = new Set(Object.values(KB_ENRICHING_RULES));
      const findingCount = findings.filter(f => f.file === file && !kbEnrichingRuleIds.has(f.code)).length;
      const outLinks = allLinks.filter(l => l.source === file).length;
      const inLinks = allLinks.filter(l => l.target === file).length;

      const score = base + archBoost + (findingCount * 2) + (inLinks * 2) + outLinks;
      fileScores.set(file, score);
    }

    const sortedFiles = Array.from(fileScores.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 40)
      .map(([file]) => file);

    // Extract symbols synchronously using cached content
    const symbolExtractionResults: Array<{ file: string; symbols: Array<{ name: string; kind: string; signature: string | null; calledBy: string[] }> }> = [];
    for (const file of sortedFiles) {
      const symbols = extractFileSymbolsWithSignatures(file, allLinks, workspaceRoot.fsPath, grammars, fileContentCache);
      symbolExtractionResults.push({ file, symbols });
    }
    
    for (const { file, symbols } of symbolExtractionResults) {
      if (symbols.length === 0) continue;
      
      const relPath = makeRelativePath(file, workspaceRoot.fsPath);

      if (symbols.length === 0) continue;

      content += `### \`${relPath}\`\n\n`;
      content += '| Symbol | Kind | Signature | Used In (files) |\n';
      content += '|--------|------|-----------|----------------|\n';

      for (const symbol of symbols.slice(0, 12)) {
        const sig = symbol.signature ? `\`${symbol.signature}\`` : '—';
        // Sort callers for determinism
        const sortedCallers = [...symbol.calledBy].sort();
        const usedIn = sortedCallers.slice(0, 2).map(c => `\`${c}\``).join(', ') || '—';
        content += `| \`${symbol.name}\` | ${symbol.kind} | ${sig} | ${usedIn} |\n`;
      }

      if (symbols.length > 12) {
        content += `\n_+${symbols.length - 12} more symbols_\n`;
      }
      content += '\n';
    }
  }

  // ============================================================
  // CONVENTIONS (from old conventions.md)
  // ============================================================
  if (appFiles.length > 0) {
    content += '---\n\n';
    content += '## Conventions\n\n';
    content += '_Naming patterns and styles. Follow these for consistency._\n\n';

    // File naming
    const fileNaming = analyzeFileNaming(appFiles, workspaceRoot.fsPath);
    if (fileNaming.patterns.length > 0) {
      content += '### File Naming\n\n';
      content += '| Pattern | Example | Count |\n';
      content += '|---------|---------|-------|\n';
      for (const pattern of fileNaming.patterns.slice(0, 4)) {
        content += `| ${pattern.style} | \`${pattern.example}\` | ${pattern.count} |\n`;
      }
      content += '\n';
      if (fileNaming.dominant) {
        content += `**Use:** ${fileNaming.dominant} for new files.\n\n`;
      }
    }

    // Function naming patterns
    const funcNaming = await analyzeFunctionNaming(appFiles);
    if (funcNaming.patterns.length > 0) {
      content += '### Function Naming\n\n';
      for (const pattern of funcNaming.patterns.slice(0, 5)) {
        content += `- \`${pattern.pattern}\` → \`${pattern.example}\` (${pattern.usage})\n`;
      }
      content += '\n';
    }

    // Framework patterns
    const frameworkPatterns = detectFrameworkPatterns(appFiles, workspaceRoot.fsPath);
    if (frameworkPatterns.length > 0) {
      content += '### Framework Patterns\n\n';
      for (const fw of frameworkPatterns) {
        content += `**${fw.name}:**\n`;
        for (const pattern of fw.patterns.slice(0, 3)) {
          content += `- ${pattern}\n`;
        }
        content += '\n';
      }
    }
  }

  content += `\n_Generated: ${new Date().toISOString()}_\n`;

  // Enforce size budget before writing
  const finalContent = enforceLineBudget(content, KB_SIZE_LIMITS.map, 'map.md');
  
  const mapFile = vscode.Uri.joinPath(aspectCodeDir, 'map.md');
  await vscode.workspace.fs.writeFile(mapFile, Buffer.from(finalContent, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated map.md (${finalContent.split('\n').length} lines)`);
}

/**
 * Extract model signature (first line/fields) from a file
 */
function extractModelSignature(filePath: string, modelName: string, fileContentCache: Map<string, string>): string | null {
  try {
    const text = fileContentCache.get(filePath);
    if (!text) return null;
    const lines = text.split('\n');
    const ext = path.extname(filePath).toLowerCase();
    
    // Extract just the class/model name without extra details
    // Handle formats like: "MyClass", "MyClass: description", "Data Class (dataclass) - class"
    // Also handle: "Pydantic: MyModel", "ORM: MyEntity", etc.
    let cleanName = modelName;
    
    // Remove common prefixes from detection messages
    cleanName = cleanName.replace(/^(Data Class|Pydantic|ORM|Entity|BaseModel|SQLModel|Interface|Type Alias)\s*[:(]\s*/i, '');
    // Remove descriptors like "(dataclass) - class"
    cleanName = cleanName.replace(/\s*\([^)]+\)\s*-\s*\w+\s*$/, '');
    // Remove trailing descriptors like " - class", " - function"
    cleanName = cleanName.replace(/\s*-\s*(class|function|type|interface)\s*$/i, '');
    // Take first word/identifier (the actual class name)
    cleanName = cleanName.split(/[\s:,]/)[0].trim();
    
    // Skip if we couldn't extract a valid identifier
    if (!cleanName || cleanName.length < 2 || !/^[A-Za-z_]/.test(cleanName)) {
      return null;
    }
    
    if (ext === '.py') {
      // Find class definition and capture signature
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.match(new RegExp(`^class\\s+${cleanName}\\s*[:(]`))) {
          // Get the first line as signature
          const classLine = line.trim();
          // Try to get a few field hints
          const fields: string[] = [];
          for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
            const fieldMatch = lines[j].match(/^\s+(\w+):\s*([^\s=]+)/);
            if (fieldMatch && !fieldMatch[1].startsWith('_')) {
              fields.push(`${fieldMatch[1]}: ${fieldMatch[2]}`);
              if (fields.length >= 3) break;
            }
          }
          if (fields.length > 0) {
            return `${classLine} { ${fields.join(', ')}${fields.length >= 3 ? ', ...' : ''} }`;
          }
          return classLine;
        }
      }
    } else if (['.ts', '.tsx'].includes(ext)) {
      // Find interface/type/class
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.match(new RegExp(`(interface|type|class)\\s+${cleanName}\\s*[{<]`))) {
          // Get opening line and try to capture some fields
          const typeLine = line.trim();
          const fields: string[] = [];
          for (let j = i + 1; j < Math.min(i + 8, lines.length); j++) {
            const fieldMatch = lines[j].match(/^\s+(\w+)(\?)?\s*:\s*([^;]+)/);
            if (fieldMatch) {
              fields.push(`${fieldMatch[1]}${fieldMatch[2] || ''}: ${fieldMatch[3].trim()}`);
              if (fields.length >= 3) break;
            }
            if (lines[j].includes('}')) break;
          }
          if (fields.length > 0) {
            return `${typeLine.replace('{', '').trim()} { ${fields.join('; ')}${fields.length >= 3 ? '; ...' : ''} }`;
          }
          return typeLine;
        }
      }
    } else if (ext === '.java') {
      // Find class/record definition
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.match(new RegExp(`(class|record|interface)\\s+${cleanName}\\s*`))) {
          const classLine = line.trim();
          const fields: string[] = [];
          // For records, extract from constructor-like syntax
          const recordMatch = line.match(/record\s+\w+\s*\(([^)]+)\)/);
          if (recordMatch) {
            const params = recordMatch[1].split(',').slice(0, 3).map(p => p.trim());
            return `record ${cleanName}(${params.join(', ')}${params.length >= 3 ? ', ...' : ''})`;
          }
          // For classes, look for fields
          for (let j = i + 1; j < Math.min(i + 12, lines.length); j++) {
            const fieldMatch = lines[j].match(/^\s+(?:private|protected|public)\s+([\w<>\[\]]+)\s+(\w+)\s*[;=]/);
            if (fieldMatch) {
              fields.push(`${fieldMatch[2]}: ${fieldMatch[1]}`);
              if (fields.length >= 3) break;
            }
            if (lines[j].match(/^\s*}/) || lines[j].match(/^\s*(?:public|private|protected).*\(/)) break;
          }
          if (fields.length > 0) {
            return `${classLine.replace('{', '').trim()} { ${fields.join(', ')}${fields.length >= 3 ? ', ...' : ''} }`;
          }
          return classLine.replace('{', '').trim();
        }
      }
    } else if (ext === '.cs') {
      // Find class/record/struct definition
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.match(new RegExp(`(class|record|struct|interface)\\s+${cleanName}\\s*`))) {
          const classLine = line.trim();
          const fields: string[] = [];
          // For records with primary constructor
          const recordMatch = line.match(/record\s+\w+\s*\(([^)]+)\)/);
          if (recordMatch) {
            const params = recordMatch[1].split(',').slice(0, 3).map(p => p.trim());
            return `record ${cleanName}(${params.join(', ')}${params.length >= 3 ? ', ...' : ''})`;
          }
          // For classes, look for properties
          for (let j = i + 1; j < Math.min(i + 12, lines.length); j++) {
            const propMatch = lines[j].match(/^\s+(?:public|protected|internal)\s+(?:required\s+)?([\w<>\[\]?]+)\s+(\w+)\s*{/);
            if (propMatch) {
              fields.push(`${propMatch[2]}: ${propMatch[1]}`);
              if (fields.length >= 3) break;
            }
            if (lines[j].match(/^\s*}/) || lines[j].match(/^\s*(?:public|private|protected).*\(/)) break;
          }
          if (fields.length > 0) {
            return `${classLine.replace('{', '').trim()} { ${fields.join('; ')}${fields.length >= 3 ? '; ...' : ''} }`;
          }
          return classLine.replace('{', '').trim();
        }
      }
    } else if (ext === '.prisma') {
      // Prisma schema files
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        if (line.match(new RegExp(`model\\s+${cleanName}\\s*{`))) {
          const fields: string[] = [];
          for (let j = i + 1; j < Math.min(i + 15, lines.length); j++) {
            const fieldMatch = lines[j].match(/^\s+(\w+)\s+(String|Int|Float|Boolean|DateTime|Json|Bytes|BigInt|\w+)(\?)?(\[\])?/);
            if (fieldMatch) {
              const nullable = fieldMatch[3] ? '?' : '';
              const array = fieldMatch[4] ? '[]' : '';
              fields.push(`${fieldMatch[1]}: ${fieldMatch[2]}${nullable}${array}`);
              if (fields.length >= 4) break;
            }
            if (lines[j].trim() === '}') break;
          }
          if (fields.length > 0) {
            return `model ${cleanName} { ${fields.join(', ')}${fields.length >= 4 ? ', ...' : ''} }`;
          }
          return `model ${cleanName}`;
        }
      }
    }
  } catch {
    // Ignore errors
  }
  return null;
}

/**
 * Extract file symbols with enhanced signature information.
 * Uses tree-sitter AST parsing when grammars are available for accurate multi-line support.
 * Falls back to regex for backwards compatibility.
 */
function extractFileSymbolsWithSignatures(
  filePath: string,
  allLinks: DependencyLink[],
  workspaceRoot: string,
  grammars: LoadedGrammars | null | undefined,
  fileContentCache: Map<string, string>
): Array<{ name: string; kind: string; signature: string | null; calledBy: string[] }> {
  const symbols: Array<{ name: string; kind: string; signature: string | null; calledBy: string[] }> = [];
  
  try {
    const text = fileContentCache.get(filePath);
    if (!text) return symbols;
    const ext = path.extname(filePath).toLowerCase();
    
    // Try tree-sitter extraction if grammars available
    let extracted: ExtractedSymbol[] | null = null;
    
    if (grammars) {
      try {
        if (ext === '.py' && grammars.python) {
          extracted = extractPythonSymbols(grammars.python, text);
        } else if (ext === '.ts' && grammars.typescript) {
          extracted = extractTSJSSymbols(grammars.typescript, text);
        } else if (ext === '.tsx' && grammars.tsx) {
          extracted = extractTSJSSymbols(grammars.tsx, text);
        } else if ((ext === '.js' || ext === '.jsx') && grammars.javascript) {
          extracted = extractTSJSSymbols(grammars.javascript, text);
        } else if (ext === '.java' && grammars.java) {
          extracted = extractJavaSymbols(grammars.java, text);
        } else if (ext === '.cs' && grammars.csharp) {
          extracted = extractCSharpSymbols(grammars.csharp, text);
        }
      } catch {
        // Tree-sitter parsing failed, fall through to regex
        extracted = null;
      }
    }
    
    // If tree-sitter succeeded, convert ExtractedSymbol to our format
    if (extracted && extracted.length > 0) {
      for (const sym of extracted) {
        // Only include exported symbols for TS/JS, all for Python/Java/C#
        if (sym.exported || ext === '.py' || ext === '.java' || ext === '.cs') {
          symbols.push({
            name: sym.name,
            kind: sym.kind,
            signature: sym.signature,
            calledBy: getSymbolCallers(sym.name, filePath, allLinks, workspaceRoot)
          });
        }
      }
      return symbols;
    }
    
    // Fallback to regex extraction
    const lines = text.split('\n');
    
    if (ext === '.py') {
      for (const line of lines) {
        // Functions with signature
        const funcMatch = line.match(/^def\s+(\w+)\s*\(([^)]*)\)/);
        if (funcMatch && !funcMatch[1].startsWith('_')) {
          const params = funcMatch[2].split(',').slice(0, 3).map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(p => p && p !== 'self');
          const sig = params.length > 0 ? `(${params.join(', ')})` : '()';
          symbols.push({
            name: funcMatch[1],
            kind: 'function',
            signature: `def ${funcMatch[1]}${sig}`,
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
        
        // Classes
        const classMatch = line.match(/^class\s+(\w+)(?:\(([^)]*)\))?/);
        if (classMatch) {
          const bases = classMatch[2] ? classMatch[2].split(',')[0].trim() : '';
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            signature: bases ? `class ${classMatch[1]}(${bases})` : `class ${classMatch[1]}`,
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
      }
    } else if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i];
        // Functions
        const funcMatch = line.match(/export\s+(?:async\s+)?function\s+(\w+)\s*(?:<[^>]*>)?\s*\(([^)]*)\)/);
        if (funcMatch) {
          const params = funcMatch[2].split(',').slice(0, 3).map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(p => p);
          const sig = params.length > 0 ? `(${params.join(', ')})` : '()';
          symbols.push({
            name: funcMatch[1],
            kind: 'function',
            signature: `function ${funcMatch[1]}${sig}`,
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Classes
        const classMatch = line.match(/export\s+(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?/);
        if (classMatch) {
          const extCls = classMatch[2] ? ` extends ${classMatch[2]}` : '';
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            signature: `class ${classMatch[1]}${extCls}`,
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Interfaces
        const interfaceMatch = line.match(/export\s+interface\s+(\w+)/);
        if (interfaceMatch) {
          symbols.push({
            name: interfaceMatch[1],
            kind: 'interface',
            signature: `interface ${interfaceMatch[1]}`,
            calledBy: getSymbolCallers(interfaceMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Type aliases
        const typeMatch = line.match(/export\s+type\s+(\w+)\s*=/);
        if (typeMatch) {
          symbols.push({
            name: typeMatch[1],
            kind: 'type',
            signature: `type ${typeMatch[1]}`,
            calledBy: getSymbolCallers(typeMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Const arrow functions (common pattern): export const foo = (params) => ...
        // or: export const foo = async (params) => ...
        const arrowFnMatch = line.match(/export\s+const\s+(\w+)\s*=\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*\S+)?\s*=>/);
        if (arrowFnMatch) {
          const params = arrowFnMatch[2].split(',').slice(0, 3).map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(p => p);
          const sig = params.length > 0 ? `(${params.join(', ')})` : '()';
          symbols.push({
            name: arrowFnMatch[1],
            kind: 'const',
            signature: `const ${arrowFnMatch[1]} = ${sig} =>`,
            calledBy: getSymbolCallers(arrowFnMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Const arrow function (single param, no parens): export const foo = x => ...
        const arrowFnSingleMatch = line.match(/export\s+const\s+(\w+)\s*=\s*(?:async\s+)?(\w+)\s*=>/);
        if (arrowFnSingleMatch) {
          symbols.push({
            name: arrowFnSingleMatch[1],
            kind: 'const',
            signature: `const ${arrowFnSingleMatch[1]} = (${arrowFnSingleMatch[2]}) =>`,
            calledBy: getSymbolCallers(arrowFnSingleMatch[1], filePath, allLinks, workspaceRoot)
          });
          continue;
        }
        
        // Other consts (objects, primitives, etc.) - check next line for arrow if multi-line
        const constMatch = line.match(/export\s+const\s+(\w+)\s*[:=]/);
        if (constMatch) {
          // Check if next line has arrow function signature
          let sig: string | null = null;
          if (i + 1 < lines.length) {
            const nextLine = lines[i + 1];
            const nextLineArrow = nextLine.match(/^\s*(?:async\s+)?\(([^)]*)\)\s*(?::\s*\S+)?\s*=>/);
            if (nextLineArrow) {
              const params = nextLineArrow[1].split(',').slice(0, 3).map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(p => p);
              sig = `const ${constMatch[1]} = (${params.join(', ')}) =>`;
            }
          }
          symbols.push({
            name: constMatch[1],
            kind: 'const',
            signature: sig,
            calledBy: getSymbolCallers(constMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
      }
    } else if (ext === '.java') {
      for (const line of lines) {
        // Public/protected methods with signatures
        const methodMatch = line.match(/^\s*(?:public|protected)\s+(?:static\s+)?(?:async\s+)?([\w<>\[\],\s]+)\s+(\w+)\s*\(([^)]*)\)/);
        if (methodMatch && !methodMatch[2].startsWith('_')) {
          const returnType = methodMatch[1].trim();
          const methodName = methodMatch[2];
          const params = methodMatch[3].split(',').slice(0, 3).map(p => p.trim().split(/\s+/).pop() || '').filter(p => p);
          const sig = params.length > 0 ? `(${params.join(', ')})` : '()';
          symbols.push({
            name: methodName,
            kind: 'method',
            signature: `${returnType} ${methodName}${sig}`,
            calledBy: getSymbolCallers(methodName, filePath, allLinks, workspaceRoot)
          });
        }
        
        // Classes and interfaces
        const classMatch = line.match(/^\s*(?:public|protected)?\s*(?:abstract\s+)?(?:class|interface|record)\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w,\s]+))?/);
        if (classMatch) {
          const className = classMatch[1];
          const extendsClause = classMatch[2] ? ` extends ${classMatch[2]}` : '';
          const implementsClause = classMatch[3] ? ` implements ${classMatch[3].split(',')[0].trim()}` : '';
          symbols.push({
            name: className,
            kind: line.includes('interface') ? 'interface' : (line.includes('record') ? 'record' : 'class'),
            signature: `class ${className}${extendsClause}${implementsClause}`,
            calledBy: getSymbolCallers(className, filePath, allLinks, workspaceRoot)
          });
        }
      }
    } else if (ext === '.cs') {
      for (const line of lines) {
        // Public/protected/internal methods with signatures
        const methodMatch = line.match(/^\s*(?:public|protected|internal)\s+(?:static\s+)?(?:async\s+)?(?:virtual\s+)?(?:override\s+)?([\w<>\[\],\s?]+)\s+(\w+)\s*\(([^)]*)\)/);
        if (methodMatch && !methodMatch[2].startsWith('_')) {
          const returnType = methodMatch[1].trim();
          const methodName = methodMatch[2];
          const params = methodMatch[3].split(',').slice(0, 3).map(p => p.trim().split(/\s+/).pop() || '').filter(p => p);
          const sig = params.length > 0 ? `(${params.join(', ')})` : '()';
          symbols.push({
            name: methodName,
            kind: 'method',
            signature: `${returnType} ${methodName}${sig}`,
            calledBy: getSymbolCallers(methodName, filePath, allLinks, workspaceRoot)
          });
        }
        
        // Classes, interfaces, records, structs
        const classMatch = line.match(/^\s*(?:public|protected|internal)?\s*(?:abstract\s+)?(?:partial\s+)?(?:class|interface|record|struct)\s+(\w+)(?:\s*:\s*([\w,\s]+))?/);
        if (classMatch) {
          const className = classMatch[1];
          const baseClause = classMatch[2] ? ` : ${classMatch[2].split(',')[0].trim()}` : '';
          const kind = line.includes('interface') ? 'interface' : (line.includes('record') ? 'record' : (line.includes('struct') ? 'struct' : 'class'));
          symbols.push({
            name: className,
            kind: kind,
            signature: `${kind} ${className}${baseClause}`,
            calledBy: getSymbolCallers(className, filePath, allLinks, workspaceRoot)
          });
        }
        
        // Properties (important in C#)
        const propMatch = line.match(/^\s*(?:public|protected|internal)\s+(?:static\s+)?(?:virtual\s+)?(?:override\s+)?([\w<>\[\],\s?]+)\s+(\w+)\s*{\s*get/);
        if (propMatch) {
          symbols.push({
            name: propMatch[2],
            kind: 'property',
            signature: `${propMatch[1].trim()} ${propMatch[2]}`,
            calledBy: getSymbolCallers(propMatch[2], filePath, allLinks, workspaceRoot)
          });
        }
      }
    }
  } catch {
    // Skip unreadable files
  }
  
  return symbols;
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
// context.md - The Flow (V3)
// ============================================================================

/**
 * Generate .aspect/context.md - The Flow
 * 
 * Purpose: Show how data/requests flow and which files work together.
 * Answers: "What files are edited together?" and "How does data flow?"
 * 
 * Focus on:
 * - Module clusters (co-imported files) - critical for co-location
 * - External integrations
 * - Flow patterns
 * NO LINTING: No patterns to watch, no finding lists
 */
async function generateContextFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  files: string[],
  allLinks: DependencyLink[],
  outputChannel: vscode.OutputChannel,
  fileContentCache: Map<string, string>
): Promise<void> {
  let content = '# Context\n\n';
  content += '_Data flow and co-location context. Use to understand which files work together._\n\n';

  // Filter links to only include app-to-app dependencies
  const appLinks = allLinks.filter(l => 
    classifyFile(l.source, workspaceRoot.fsPath) === 'app' &&
    classifyFile(l.target, workspaceRoot.fsPath) === 'app'
  );
  const appFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'app');

  if (appLinks.length === 0) {
    content += '_No dependency data available. Run examination first._\n';
  } else {
    // ============================================================
    // MODULE CLUSTERS (critical for co-location context)
    // ============================================================
    const clusters = findModuleClusters(appLinks, workspaceRoot.fsPath);
    if (clusters.length > 0) {
      content += '## Module Clusters\n\n';
      content += '_Files commonly imported together. Editing one likely requires editing the others._\n\n';
      
      for (const cluster of clusters.slice(0, 6)) {
        content += `### ${cluster.name}\n\n`;
        content += `_${cluster.reason}_\n\n`;
        for (const file of cluster.files.slice(0, 5)) {
          content += `- \`${file}\`\n`;
        }
        if (cluster.files.length > 5) {
          content += `- _...and ${cluster.files.length - 5} more_\n`;
        }
        content += '\n';
      }
    }

    // ============================================================
    // CRITICAL FLOWS (top central modules)
    // ============================================================
    const centralityScores = calculateCentralityScores(appLinks);
    const topModules = Array.from(centralityScores.entries())
      .filter(([file]) => isStructuralAppFile(file, workspaceRoot.fsPath))
      .sort((a, b) => b[1].score - a[1].score)
      .slice(0, 8);
    
    if (topModules.length > 0) {
      content += '## Critical Flows\n\n';
      content += '_Most central modules by connectivity. Changes here propagate widely._\n\n';
      
      content += '| Module | Callers | Dependencies |\n';
      content += '|--------|---------|--------------|\n';
      for (const [file, stats] of topModules) {
        const relPath = makeRelativePath(file, workspaceRoot.fsPath);
        content += `| \`${relPath}\` | ${stats.inDegree} | ${stats.outDegree} |\n`;
      }
      content += '\n';
    }

    // ============================================================
    // DEPENDENCY CHAINS (top 3-10 chains, prefer starting from entry points)
    // ============================================================
    // Detect entry points for chain prioritization
    const entryPointsForChains = detectEntryPointsWithContent(appFiles, workspaceRoot.fsPath, fileContentCache);
    const runtimeEntryPaths = entryPointsForChains
      .filter(e => e.category === 'runtime')
      .map(e => e.path);
    
    const chains = findDependencyChains(appLinks, workspaceRoot.fsPath, 4, runtimeEntryPaths);
    if (chains.length > 0) {
      // Limit to 3-10 chains, preferring longer chains
      const sortedChains = chains
        .map(c => ({ chain: c, depth: c.split(' → ').length }))
        .sort((a, b) => b.depth - a.depth)
        .slice(0, 8)
        .map(c => c.chain);
      
      content += '## Dependency Chains\n\n';
      content += '_Top data/call flow paths. Shows how changes propagate through the codebase._\n\n';
      
      for (let i = 0; i < sortedChains.length && i < 8; i++) {
        const chain = sortedChains[i];
        const depth = chain.split(' → ').length;
        content += `**Chain ${i + 1}** (${depth} modules):\n`;
        content += `\`\`\`\n${chain}\n\`\`\`\n\n`;
      }
    }

    // ============================================================
    // EXTERNAL INTEGRATIONS
    // ============================================================
    const externalIntegrations = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.EXTERNAL_INTEGRATION)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    
    if (externalIntegrations.length > 0) {
      content += '## External Integrations\n\n';
      content += '_Connections to external services._\n\n';
      
      // Group by type
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

      if (databases.length > 0) {
        content += '**Database:**\n';
        for (const db of databases.slice(0, 3)) {
          const relPath = makeRelativePath(db.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${db.message}\n`;
        }
        content += '\n';
      }
      
      if (httpClients.length > 0) {
        content += '**HTTP/API Clients:**\n';
        for (const http of httpClients.slice(0, 3)) {
          const relPath = makeRelativePath(http.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${http.message}\n`;
        }
        content += '\n';
      }
      
      if (queues.length > 0) {
        content += '**Message Queues:**\n';
        for (const q of queues.slice(0, 3)) {
          const relPath = makeRelativePath(q.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${q.message}\n`;
        }
        content += '\n';
      }
      
      if (other.length > 0) {
        content += '**Other:**\n';
        for (const o of other.slice(0, 3)) {
          const relPath = makeRelativePath(o.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${o.message}\n`;
        }
        content += '\n';
      }
    }

    // ============================================================
    // REQUEST FLOW PATTERN
    // ============================================================
    const layerFlows = detectLayerFlows(appFiles, appLinks, workspaceRoot.fsPath);
    if (layerFlows.length > 0) {
      content += '## Request Flow Pattern\n\n';
      content += '_How a typical request flows through the architecture._\n\n';
      
      for (const layer of layerFlows) {
        content += `**${layer.name}:**\n`;
        content += `\`\`\`\n${layer.flow}\n\`\`\`\n\n`;
      }
    }

    // ============================================================
    // QUICK REFERENCE
    // ============================================================
    content += '---\n\n';
    content += '## Quick Reference\n\n';
    content += '**"What files work together for feature X?"**\n';
    content += '→ Check Module Clusters above.\n\n';
    content += '**"Where does data flow from this endpoint?"**\n';
    content += '→ Check Critical Flows and Dependency Chains.\n\n';
    content += '**"Where are external connections?"**\n';
    content += '→ Check External Integrations.\n';
  }

  content += `\n\n_Generated: ${new Date().toISOString()}_\n`;

  // Enforce size budget before writing
  const finalContent = enforceLineBudget(content, KB_SIZE_LIMITS.context, 'context.md');
  
  const contextFile = vscode.Uri.joinPath(aspectCodeDir, 'context.md');
  await vscode.workspace.fs.writeFile(contextFile, Buffer.from(finalContent, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated context.md (${finalContent.split('\n').length} lines)`);
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
/**
 * Find dependency chains in the codebase.
 * Returns 3-5 chains with deterministic ordering by depth and file path.
 * Chains are 3-6 modules long, showing import flow direction.
 */
function findDependencyChains(
  allLinks: DependencyLink[],
  workspaceRoot: string,
  maxDepth: number = 5,
  preferredStartPaths: string[] = []
): string[] {
  const chains: Array<{ chain: string[]; depth: number; startPath: string; startsFromEntry: boolean }> = [];
  
  // Build adjacency map (sorted for determinism)
  const outgoing = new Map<string, string[]>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    if (!outgoing.has(link.source)) {
      outgoing.set(link.source, []);
    }
    outgoing.get(link.source)!.push(link.target);
  }
  
  // Sort each adjacency list for determinism
  for (const [key, deps] of outgoing.entries()) {
    outgoing.set(key, deps.sort());
  }
  
  // Build a set of preferred start paths for quick lookup
  const preferredSet = new Set(preferredStartPaths.map(p => p.toLowerCase()));
  
  // Find files with high in-degree (good starting points for chains)
  const inDegree = new Map<string, number>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    inDegree.set(link.target, (inDegree.get(link.target) || 0) + 1);
  }
  
  // Prioritize preferred entry points, then fall back to high in-degree files
  // Get start files from preferred paths first
  const entryStartFiles: string[] = [];
  for (const file of outgoing.keys()) {
    const relPath = makeRelativePath(file, workspaceRoot).toLowerCase();
    if (preferredSet.has(relPath)) {
      entryStartFiles.push(file);
    }
  }
  
  // Then add high in-degree files (deterministic tie-breaker by path name)
  const inDegreeStartFiles = Array.from(inDegree.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 8)
    .map(([file]) => file)
    .filter(f => !entryStartFiles.some(e => e === f)); // Avoid duplicates
  
  // Combine: entry points first, then high in-degree
  const startFiles = [...entryStartFiles.sort(), ...inDegreeStartFiles].slice(0, 10);
  
  const seenChains = new Set<string>();
  
  for (const startFile of startFiles) {
    const deps = outgoing.get(startFile) || [];
    if (deps.length === 0) continue;
    
    // Check if this is an entry point start
    const startRelPath = makeRelativePath(startFile, workspaceRoot).toLowerCase();
    const startsFromEntry = preferredSet.has(startRelPath);
    
    // Build chain with BFS-like approach to find longest path
    const chain: string[] = [makeRelativePath(startFile, workspaceRoot)];
    let current = deps[0]; // First dep (deterministic due to sorting)
    let depth = 0;
    
    while (depth < maxDepth && current) {
      const relPath = makeRelativePath(current, workspaceRoot);
      if (chain.includes(relPath)) break; // Avoid cycles
      chain.push(relPath);
      const nextDeps = (outgoing.get(current) || [])
        .filter(d => !chain.includes(makeRelativePath(d, workspaceRoot)));
      current = nextDeps[0] || ''; // First unvisited dep
      depth++;
    }
    
    // Only include chains with 3+ modules
    if (chain.length >= 3) {
      // Truncate to max 6 modules
      const finalChain = chain.slice(0, 6);
      const chainStr = finalChain.join(' → ');
      
      // Avoid duplicate chains (same modules in same order)
      if (!seenChains.has(chainStr)) {
        seenChains.add(chainStr);
        chains.push({
          chain: finalChain,
          depth: finalChain.length,
          startPath: startFile,
          startsFromEntry
        });
      }
    }
  }
  
  // Sort: prefer entry point chains, then by depth, then by path for determinism
  // Also prefer chains that end at "leaf" files (files with low out-degree)
  const outDegree = new Map<string, number>();
  for (const link of allLinks) {
    if (link.source === link.target) continue;
    outDegree.set(link.source, (outDegree.get(link.source) || 0) + 1);
  }
  
  const sortedChains = chains
    .map(c => {
      // Score chains by: entry point bonus + length + bonus if ending at a leaf
      const lastFile = c.chain[c.chain.length - 1];
      const isLeaf = (outDegree.get(lastFile) || 0) <= 1;
      const entryBonus = c.startsFromEntry ? 10 : 0;
      return { ...c, score: entryBonus + c.depth + (isLeaf ? 1 : 0) };
    })
    .sort((a, b) => b.score - a.score || b.depth - a.depth || a.startPath.localeCompare(b.startPath))
    .slice(0, 5); // Max 5 chains
  
  // If we have fewer than 3 chains, try to find more by exploring other starting points
  if (sortedChains.length < 3) {
    // Try files with outgoing edges but not high in-degree
    const additionalStarts = Array.from(outgoing.keys())
      .filter(f => !startFiles.includes(f))
      .sort()
      .slice(0, 5);
    
    for (const startFile of additionalStarts) {
      if (sortedChains.length >= 5) break;
      
      const chain: string[] = [makeRelativePath(startFile, workspaceRoot)];
      let current = (outgoing.get(startFile) || [])[0];
      
      while (chain.length < maxDepth && current) {
        const relPath = makeRelativePath(current, workspaceRoot);
        if (chain.includes(relPath)) break;
        chain.push(relPath);
        const nextDeps = (outgoing.get(current) || [])
          .filter(d => !chain.includes(makeRelativePath(d, workspaceRoot)));
        current = nextDeps[0] || '';
      }
      
      if (chain.length >= 3) {
        const finalChain = chain.slice(0, 6);
        const chainStr = finalChain.join(' → ');
        if (!seenChains.has(chainStr)) {
          seenChains.add(chainStr);
          // Calculate score for fallback chains
          const lastFile = finalChain[finalChain.length - 1];
          const isLeaf = (outDegree.get(lastFile) || 0) <= 1;
          sortedChains.push({
            chain: finalChain,
            depth: finalChain.length,
            startPath: startFile,
            startsFromEntry: false, // Fallback chains don't start from entry points
            score: finalChain.length + (isLeaf ? 1 : 0)
          });
        }
      }
    }
  }
  
  return sortedChains.slice(0, 5).map(c => c.chain.join(' → '));
}

/**
 * Find clusters of files that are commonly imported together.
 * Returns 3-7 clusters with deterministic ordering by co-import score.
 * Each cluster includes a "why" line explaining the grouping.
 */
function findModuleClusters(
  allLinks: DependencyLink[],
  workspaceRoot: string
): Array<{ name: string; files: string[]; reason: string; sharedImporters: string[]; score: number }> {
  const clusters: Array<{ name: string; files: string[]; reason: string; sharedImporters: string[]; score: number }> = [];
  
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
  const fileList = Array.from(importedBy.keys()).sort(); // Sort for determinism
  const coImportScores = new Map<string, Map<string, { score: number; sharedImporters: string[] }>>();
  
  for (let i = 0; i < fileList.length; i++) {
    for (let j = i + 1; j < fileList.length; j++) {
      const fileA = fileList[i];
      const fileB = fileList[j];
      const importersA = importedBy.get(fileA) || new Set();
      const importersB = importedBy.get(fileB) || new Set();
      
      // Find shared importers
      const sharedImporters: string[] = [];
      for (const importer of importersA) {
        if (importersB.has(importer)) {
          sharedImporters.push(importer);
        }
      }
      
      if (sharedImporters.length >= 2) {
        if (!coImportScores.has(fileA)) {
          coImportScores.set(fileA, new Map());
        }
        // Sort shared importers for determinism
        sharedImporters.sort();
        coImportScores.get(fileA)!.set(fileB, { 
          score: sharedImporters.length, 
          sharedImporters 
        });
      }
    }
  }
  
  // Build clusters from high co-import scores
  const processed = new Set<string>();
  
  // Sort entries for deterministic processing
  const sortedEntries = Array.from(coImportScores.entries())
    .sort((a, b) => {
      // Sort by total score of related files
      const scoreA = Array.from(a[1].values()).reduce((sum, d) => sum + d.score, 0);
      const scoreB = Array.from(b[1].values()).reduce((sum, d) => sum + d.score, 0);
      return scoreB - scoreA || a[0].localeCompare(b[0]); // Tie-break by path
    });
  
  for (const [file, relatedMap] of sortedEntries) {
    if (processed.has(file)) continue;
    
    const related = Array.from(relatedMap.entries())
      .filter(([_, data]) => data.score >= 2)
      .sort((a, b) => b[1].score - a[1].score || a[0].localeCompare(b[0])) // Deterministic sort
      .slice(0, 7); // Max 8 files per cluster
    
    if (related.length >= 1) {
      // Filter out config files from clusters - they pollute feature groupings
      const rawFiles = [file, ...related.map(([f]) => f)].map(f => makeRelativePath(f, workspaceRoot));
      const clusterFiles = dedupe(rawFiles.filter(f => !isConfigOrToolingFile(f))).slice(0, 8);
      
      // Skip if all files were configs
      if (clusterFiles.length < 2) {
        processed.add(file);
        related.forEach(([f]) => processed.add(f));
        continue;
      }
      
      // Collect all shared importers across the cluster
      const allSharedImporters = new Set<string>();
      for (const [_, data] of related) {
        for (const imp of data.sharedImporters) {
          allSharedImporters.add(makeRelativePath(imp, workspaceRoot));
        }
      }
      
      // Calculate cluster score for ranking
      const clusterScore = related.reduce((sum, [_, d]) => sum + d.score, 0);
      
      // Determine cluster name from common path components
      const parts = clusterFiles[0].split(/[/\\]/);
      let clusterName = parts.length > 1 ? parts[parts.length - 2] : path.basename(clusterFiles[0]);
      // Capitalize first letter
      clusterName = clusterName.charAt(0).toUpperCase() + clusterName.slice(1);
      
      // Build reason explaining the cluster (top 2-3 co-importing files)
      const topImporters = Array.from(allSharedImporters).sort().slice(0, 3);
      const reason = topImporters.length > 0 
        ? `Co-imported by: ${topImporters.map(i => `\`${i}\``).join(', ')}${allSharedImporters.size > 3 ? ` (+${allSharedImporters.size - 3} more)` : ''}`
        : 'Frequently used together';
      
      clusters.push({
        name: clusterName,
        files: clusterFiles,
        reason,
        sharedImporters: Array.from(allSharedImporters).sort(),
        score: clusterScore
      });
      
      processed.add(file);
      related.forEach(([f]) => processed.add(f));
    }
  }
  
  // Sort clusters by score (highest first) and ensure 3-7 clusters
  const sortedClusters = clusters.sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  
  // If we have fewer than 3 clusters, try to generate more from remaining files
  // by lowering the threshold slightly
  if (sortedClusters.length < 3 && fileList.length > 5) {
    // Add directory-based clusters as fallback
    const dirClusters = buildDirectoryClusters(allLinks, workspaceRoot, processed);
    for (const dc of dirClusters) {
      if (sortedClusters.length >= 7) break;
      if (!sortedClusters.some(c => c.name === dc.name)) {
        sortedClusters.push(dc);
      }
    }
  }
  
  // Disambiguate cluster names using path context or sequential numbering
  disambiguateClusterNames(sortedClusters);
  
  return sortedClusters.slice(0, 7); // Max 7 clusters
}

/**
 * Disambiguate cluster names that would otherwise collide.
 * Uses path segment context first, then falls back to sequential numbering.
 */
function disambiguateClusterNames(clusters: Array<{ name: string; files: string[] }>): void {
  // Group clusters by name to find collisions
  const nameGroups = new Map<string, number[]>();
  for (let i = 0; i < clusters.length; i++) {
    const name = clusters[i].name;
    if (!nameGroups.has(name)) {
      nameGroups.set(name, []);
    }
    nameGroups.get(name)!.push(i);
  }
  
  // Resolve collisions
  for (const [name, indices] of nameGroups.entries()) {
    if (indices.length <= 1) continue; // No collision
    
    // Try to disambiguate using path context from first file
    const pathContexts: string[] = [];
    for (const idx of indices) {
      const firstFile = clusters[idx].files[0] || '';
      const segments = firstFile.split('/');
      // Get distinguishing path segment (prefer parent dir if available)
      if (segments.length >= 2) {
        pathContexts.push(segments[segments.length - 2]); // Parent directory
      } else if (segments.length >= 1) {
        const basename = path.basename(segments[0], path.extname(segments[0]));
        pathContexts.push(basename);
      } else {
        pathContexts.push('');
      }
    }
    
    // Check if path contexts are unique
    const uniqueContexts = new Set(pathContexts);
    if (uniqueContexts.size === pathContexts.length && !pathContexts.some(c => c === '')) {
      // Use path context for disambiguation
      for (let i = 0; i < indices.length; i++) {
        clusters[indices[i]].name = `${name} (${pathContexts[i]})`;
      }
    } else {
      // Fall back to sequential numbering
      for (let i = 0; i < indices.length; i++) {
        clusters[indices[i]].name = `${name} #${i + 1}`;
      }
    }
  }
}

/**
 * Build directory-based clusters as fallback when co-import clusters are sparse.
 */
function buildDirectoryClusters(
  allLinks: DependencyLink[],
  workspaceRoot: string,
  processedFiles: Set<string>
): Array<{ name: string; files: string[]; reason: string; sharedImporters: string[]; score: number }> {
  const dirGroups = new Map<string, string[]>();
  
  const allFiles = new Set(allLinks.flatMap(l => [l.source, l.target]));
  for (const file of allFiles) {
    if (processedFiles.has(file)) continue;
    const relPath = makeRelativePath(file, workspaceRoot);
    // Skip config files in directory clusters too
    if (isConfigOrToolingFile(relPath)) continue;
    const dir = path.dirname(relPath);
    if (!dirGroups.has(dir)) {
      dirGroups.set(dir, []);
    }
    dirGroups.get(dir)!.push(relPath);
  }
  
  return Array.from(dirGroups.entries())
    .filter(([_, files]) => files.length >= 3)
    .sort((a, b) => b[1].length - a[1].length)
    .slice(0, 3)
    .map(([dir, files]) => ({
      name: path.basename(dir) || 'Root',
      files: files.filter(f => !isConfigOrToolingFile(f)).sort().slice(0, 8),
      reason: `Files in \`${dir}/\` directory`,
      sharedImporters: [],
      score: files.length
    }));
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
  
  // Java import patterns
  const javaFiles = files.filter(f => f.endsWith('.java')).slice(0, 3);
  for (const file of javaFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      const lines = text.split('\n').slice(0, 30);
      
      const imports = lines.filter(l => l.trim().startsWith('import '));
      if (imports.length >= 2) {
        patterns.push({
          language: 'Java',
          example: imports.slice(0, 4).join('\n')
        });
        break;
      }
    } catch {}
  }
  
  // C# using patterns
  const csFiles = files.filter(f => f.endsWith('.cs')).slice(0, 3);
  for (const file of csFiles) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      const lines = text.split('\n').slice(0, 30);
      
      const usings = lines.filter(l => l.trim().startsWith('using ') && l.includes(';'));
      if (usings.length >= 2) {
        patterns.push({
          language: 'C#',
          example: usings.slice(0, 4).join('\n')
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
      
      // Java method pattern
      const javaMatches = text.matchAll(/(?:public|protected|private)\s+(?:static\s+)?\w+\s+(\w+)\s*\(/g);
      for (const match of javaMatches) {
        categorizeFunction(match[1], patternCounts);
      }
      
      // C# method pattern
      const csMatches = text.matchAll(/(?:public|protected|private|internal)\s+(?:static\s+)?(?:async\s+)?\w+\s+(\w+)\s*\(/g);
      for (const match of csMatches) {
        categorizeFunction(match[1], patternCounts);
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
  
  // Django detection (conservative - require multiple Django-specific signals)
  const baseNames = new Set(fileNames);
  const hasModelsPy = baseNames.has('models.py');
  const hasViewsPy = baseNames.has('views.py');
  const hasUrlsPy = baseNames.has('urls.py');
  const hasSettingsPy = baseNames.has('settings.py');
  const hasManagePy = baseNames.has('manage.py');

  // Strong project signal: manage.py + (settings.py OR urls.py)
  const strongProjectSignal = hasManagePy && (hasSettingsPy || hasUrlsPy);
  // Strong app signal: models.py + (views.py OR urls.py)
  const strongAppSignal = hasModelsPy && (hasViewsPy || hasUrlsPy);

  if (strongProjectSignal || strongAppSignal) {
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
  
  // Spring Boot detection (Java)
  const javaFiles = fileNames.filter(f => f.endsWith('.java'));
  const hasSpringApp = javaFiles.some(f => f.includes('application'));
  const hasController = dirNames.some(d => d.includes('/controller/') || d.includes('/controllers/'));
  const hasService = dirNames.some(d => d.includes('/service/') || d.includes('/services/'));
  const hasRepository = dirNames.some(d => d.includes('/repository/') || d.includes('/repositories/'));
  
  if (javaFiles.length > 0 && (hasSpringApp || (hasController && hasService))) {
    frameworks.push({
      name: 'Spring Boot',
      patterns: [
        'Use `@RestController` or `@Controller` for HTTP endpoints',
        'Use `@Service` for business logic, `@Repository` for data access',
        'Use `@Autowired` or constructor injection for dependencies',
        'Use `@Entity` with JPA for ORM models',
        'Place controllers in `/controller`, services in `/service`'
      ]
    });
  }
  
  // ASP.NET Core detection (C#)
  const csFiles = fileNames.filter(f => f.endsWith('.cs'));
  const hasProgramCs = csFiles.some(f => f === 'program.cs');
  const hasStartupCs = csFiles.some(f => f === 'startup.cs');
  const hasCsControllers = dirNames.some(d => d.includes('/controllers/'));
  const hasCsServices = dirNames.some(d => d.includes('/services/'));
  
  if (csFiles.length > 0 && (hasProgramCs || hasStartupCs || hasCsControllers)) {
    frameworks.push({
      name: 'ASP.NET Core',
      patterns: [
        'Use `[ApiController]` and `[Route]` attributes for HTTP endpoints',
        'Use `[HttpGet]`, `[HttpPost]` etc. for HTTP methods',
        'Register services in `Program.cs` or `Startup.cs`',
        'Use Entity Framework Core with `DbContext` for data access',
        'Place controllers in `/Controllers`, models in `/Models`'
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

// File classification for project-centric KB generation
type FileKind = 'app' | 'test' | 'third_party';

/**
 * Classify a file as app code, test code, or third-party/environment.
 * Used to focus KB on project code and avoid polluting architectural views
 * with virtualenv, node_modules, build artifacts, or test files.
 */
function classifyFile(absPathOrRel: string, workspaceRoot: string): FileKind {
  const rel = makeRelativePath(absPathOrRel, workspaceRoot).toLowerCase().replace(/\\/g, '/');

  // Third-party / environment / build directories
  const thirdPartyPatterns = [
    '/.venv/', '/venv/', '/env/', '/.tox/', '/site-packages/',
    '/node_modules/', '/__pycache__/', '/.pytest_cache/', '/.mypy_cache/',
    '/dist/', '/build/', '/.next/', '/.turbo/', '/coverage/', '/.cache/',
    '/dist-packages/', '/.git/', '/.hg/',
  ];
  // Also check if path starts with these (for top-level matches)
  const thirdPartyPrefixes = [
    '.venv/', 'venv/', 'env/', '.tox/', 'site-packages/',
    'node_modules/', '__pycache__/', '.pytest_cache/', '.mypy_cache/',
    'dist/', 'build/', '.next/', '.turbo/', 'coverage/', '.cache/',
    'dist-packages/', '.git/', '.hg/',
  ];
  
  if (thirdPartyPatterns.some(p => rel.includes(p)) ||
      thirdPartyPrefixes.some(p => rel.startsWith(p))) {
    return 'third_party';
  }

  // Test files - by directory or filename
  const parts = rel.split('/');
  const filename = parts[parts.length - 1] || '';
  if (
    parts.some(p => p === 'test' || p === 'tests' || p === 'spec' || p === '__tests__') ||
    filename.startsWith('test_') ||
    filename.endsWith('_test.py') ||
    filename.endsWith('.test.ts') ||
    filename.endsWith('.test.tsx') ||
    filename.endsWith('.test.js') ||
    filename.endsWith('.test.jsx') ||
    filename.endsWith('.spec.ts') ||
    filename.endsWith('.spec.tsx') ||
    filename.endsWith('.spec.js') ||
    filename.endsWith('.spec.jsx') ||
    filename.includes('.spec.') ||
    filename.includes('.test.')
  ) {
    return 'test';
  }

  return 'app';
}

/**
 * Check if a file is "structural app code" - runtime/domain modules,
 * not migrations, hooks, or generated tooling.
 */
function isStructuralAppFile(file: string, workspaceRoot: string): boolean {
  if (classifyFile(file, workspaceRoot) !== 'app') return false;

  const rel = makeRelativePath(file, workspaceRoot).toLowerCase().replace(/\\/g, '/');

  // Exclude migrations / Alembic
  if (rel.includes('/alembic/') || rel.includes('/migrations/')) {
    return false;
  }

  // Exclude project generation hooks / scaffolding scripts
  if (rel.includes('/hooks/')) {
    return false;
  }

  // Exclude generated client/config tooling
  const basename = path.basename(rel);
  if (
    basename === 'playwright.config.ts' ||
    basename === 'openapi-ts.config.ts' ||
    basename === 'vite.config.ts' ||
    basename === 'vitest.config.ts' ||
    basename === 'jest.config.ts' ||
    basename === 'jest.config.js' ||
    basename.endsWith('.gen.ts') ||
    basename.endsWith('.gen.js') ||
    basename.endsWith('.gen.tsx') ||
    basename.endsWith('.gen.jsx') ||
    basename.endsWith('sdk.gen.ts') ||
    basename.endsWith('types.gen.ts')
  ) {
    return false;
  }

  return true;
}

/**
 * Check if a file is a config/tooling file (not runtime code).
 * Used to filter configs from feature clusters and categorize entry points.
 */
function isConfigOrToolingFile(filePath: string): boolean {
  const pathLower = filePath.toLowerCase();
  const baseName = path.basename(filePath, path.extname(filePath)).toLowerCase();
  
  return pathLower.includes('config') || pathLower.includes('.config') ||
         baseName.includes('jest') || baseName.includes('webpack') ||
         baseName.includes('vite') || baseName.includes('tailwind') ||
         baseName.includes('eslint') || baseName.includes('prettier') ||
         baseName.includes('tsconfig') || baseName.includes('babel') ||
         baseName.includes('postcss') || baseName.includes('rollup') ||
         baseName.startsWith('next.') || baseName.startsWith('vitest.') ||
         baseName === 'package' || baseName === 'package-lock' ||
         baseName === 'tsconfig' || baseName === 'jsconfig' ||
         pathLower.endsWith('.config.js') || pathLower.endsWith('.config.ts') ||
         pathLower.endsWith('.config.mjs') || pathLower.endsWith('.config.cjs');
}

async function extractFileSymbols(
  filePath: string,
  allLinks: DependencyLink[],
  workspaceRoot?: string
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
            callsInto: getSymbolDependencies(filePath, allLinks, workspaceRoot),
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
        
        const classMatch = line.match(/^class\s+(\w+)/);
        if (classMatch) {
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            callsInto: getSymbolDependencies(filePath, allLinks, workspaceRoot),
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks, workspaceRoot)
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
            callsInto: getSymbolDependencies(filePath, allLinks, workspaceRoot),
            calledBy: getSymbolCallers(funcMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
        
        const classMatch = line.match(/export\s+(?:abstract\s+)?class\s+(\w+)/);
        if (classMatch) {
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            callsInto: getSymbolDependencies(filePath, allLinks, workspaceRoot),
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
        
        const constMatch = line.match(/export\s+const\s+(\w+)\s*[:=]/);
        if (constMatch) {
          symbols.push({
            name: constMatch[1],
            kind: 'const',
            callsInto: getSymbolDependencies(filePath, allLinks, workspaceRoot),
            calledBy: getSymbolCallers(constMatch[1], filePath, allLinks, workspaceRoot)
          });
        }
      }
    }
  } catch {
    // Skip unreadable files
  }
  
  return symbols;
}

/**
 * Get symbols that a file depends on (outgoing symbols from imports)
 */
function getSymbolDependencies(filePath: string, allLinks: DependencyLink[], workspaceRoot?: string): string[] {
  const deps = new Set<string>();
  for (const link of allLinks.filter(l => l.source === filePath)) {
    // Filter out third-party and test files from dependencies
    if (workspaceRoot && classifyFile(link.target, workspaceRoot) !== 'app') continue;
    for (const symbol of link.symbols) {
      deps.add(symbol);
    }
  }
  return Array.from(deps);
}

/**
 * Get files that import/call a specific symbol from a file.
 * Returns shortened relative file paths with extension for unambiguous identification.
 * Format: "handler.ts", "services/auth.ts" (uses shortest unique path)
 * Caps at 5 files with (+N more) if more exist.
 */
function getSymbolCallers(symbolName: string, filePath: string, allLinks: DependencyLink[], workspaceRoot?: string): string[] {
  // Normalize the file path for comparison
  const normalizedFilePath = filePath.replace(/\\/g, '/');
  
  const callers = allLinks
    .filter(l => {
      // Normalize target path for comparison
      const normalizedTarget = l.target.replace(/\\/g, '/');
      if (normalizedTarget !== normalizedFilePath) return false;
      
      // Check if this import could reference the symbol:
      // 1. Explicit symbol import (import { symbolName } from ...)
      // 2. Wildcard import (import * as X from ...) - counts as importing all
      // 3. Default import with matching name
      // 4. Empty symbols = import entire module (could use any export)
      // 5. Type imports often don't track individual symbols
      const hasSymbol = l.symbols.includes(symbolName) || 
                       l.symbols.includes('*') ||
                       l.symbols.length === 0 ||
                       l.type === 'import'; // Any file that imports the target may use the symbol
      if (!hasSymbol) return false;
      
      // Filter out third-party and test files from callers
      if (workspaceRoot && classifyFile(l.source, workspaceRoot) !== 'app') return false;
      return true;
    });
  
  // Dedupe by source file
  const uniqueCallers = dedupe(callers, l => l.source);
  
  // Sort for determinism
  const sorted = uniqueCallers.sort((a, b) => a.source.localeCompare(b.source));
  
  // Map to shortened paths (last 2-3 path segments for readability)
  const maxDisplay = 5;
  const result: string[] = [];
  
  for (let i = 0; i < Math.min(maxDisplay, sorted.length); i++) {
    const caller = sorted[i];
    const relPath = workspaceRoot 
      ? makeRelativePath(caller.source, workspaceRoot)
      : path.basename(caller.source);
    
    // Use shortened path: prefer last 2 segments for brevity
    const segments = relPath.split('/');
    const shortened = segments.length > 2 
      ? segments.slice(-2).join('/')  // e.g., "services/auth.ts"
      : relPath;                       // e.g., "main.ts"
    
    result.push(shortened);
  }
  
  // Add (+N more) indicator if truncated
  if (sorted.length > maxDisplay) {
    result.push(`(+${sorted.length - maxDisplay} more)`);
  }
  
  return result;
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

/**
 * Entry point detection result with category and confidence.
 */
interface DetectedEntryPoint {
  path: string;
  reason: string;
  confidence: 'high' | 'medium' | 'low';
  category: 'runtime' | 'tooling' | 'barrel';
  routeCount?: number; // For ranking runtime entries
}

/**
 * Detect entry points with language-aware content analysis.
 * Categorizes into: Runtime Entry Points, Runnable Scripts/Tooling, Barrel/Index Exports.
 * 
 * Runtime Entry Points (🟢/🟡):
 * - Python: FastAPI/Flask/Django apps, route handlers
 * - TS/JS: Next.js API routes, Express/Nest servers
 * - C#: ASP.NET Program.cs with WebApplication
 * - Java: Spring Boot @SpringBootApplication, @RestController
/**
 * Detect entry points from file content using cache.
 * 
 * Runtime Entry Points (🔴):
 * - FastAPI/Flask/Express route handlers
 * - main() functions, if __name__ == "__main__"
 * - Lambda/cloud function handlers
 * 
 * Runnable Scripts/Tooling (🟡):
 * - Python: if __name__ == "__main__"
 * - JS/TS: bin scripts, require.main === module
 * - Config files: jest.config, next.config, etc.
 * 
 * Barrel/Index Exports (🟡):
 * - index.ts/tsx/js, __init__.py that primarily re-export
 */
function detectEntryPointsWithContent(
  files: string[], 
  workspaceRoot: string,
  fileContentCache: Map<string, string>
): DetectedEntryPoint[] {
  const entryPoints: DetectedEntryPoint[] = [];
  const processedPaths = new Set<string>();
  
  for (const file of files) {
    const relPath = makeRelativePath(file, workspaceRoot);
    if (processedPaths.has(relPath)) continue;
    processedPaths.add(relPath);
    
    const ext = path.extname(file).toLowerCase();
    const basename = path.basename(file, ext).toLowerCase();
    
    // Use cached content
    const content = fileContentCache.get(file) || '';
    if (!content) continue;
    
    const result = analyzeFileForEntryPoint(relPath, basename, ext, content);
    if (result) {
      entryPoints.push(result);
    }
  }
  
  // Sort: runtime first (by route count desc), then tooling, then barrel
  // Within each category: by confidence (high first), then path for determinism
  const categoryOrder = { runtime: 0, tooling: 1, barrel: 2 };
  const confidenceOrder = { high: 0, medium: 1, low: 2 };
  
  entryPoints.sort((a, b) => {
    const catDiff = categoryOrder[a.category] - categoryOrder[b.category];
    if (catDiff !== 0) return catDiff;
    
    // Within runtime, sort by route count desc
    if (a.category === 'runtime' && b.category === 'runtime') {
      const routeDiff = (b.routeCount || 0) - (a.routeCount || 0);
      if (routeDiff !== 0) return routeDiff;
    }
    
    const confDiff = confidenceOrder[a.confidence] - confidenceOrder[b.confidence];
    if (confDiff !== 0) return confDiff;
    
    return a.path.localeCompare(b.path);
  });
  
  return entryPoints;
}

/**
 * Analyze a single file for entry point characteristics.
 */
function analyzeFileForEntryPoint(
  relPath: string,
  basename: string,
  ext: string,
  content: string
): DetectedEntryPoint | null {
  const pathLower = relPath.toLowerCase();
  
  // ============================================================
  // BARREL/INDEX EXPORTS (check first - quick)
  // ============================================================
  if (basename === 'index' || basename === 'mod' || basename === '__init__') {
    // Check if it's primarily re-exports
    const exportLines = (content.match(/^export\s+/gm) || []).length;
    const fromLines = (content.match(/from\s+['"]/gm) || []).length;
    const totalLines = content.split('\n').filter(l => l.trim()).length;
    
    // If more than 50% of non-empty lines are exports/re-exports, it's a barrel
    if (totalLines > 0 && (exportLines + fromLines) / totalLines > 0.4) {
      return {
        path: relPath,
        reason: 'Re-export barrel',
        confidence: 'medium',
        category: 'barrel'
      };
    }
    
    // Python __init__.py with from .X import patterns
    if (ext === '.py') {
      const pyReexports = (content.match(/^from\s+\./gm) || []).length;
      if (pyReexports > 2 && pyReexports / Math.max(1, totalLines) > 0.3) {
        return {
          path: relPath,
          reason: 'Package re-exports',
          confidence: 'medium',
          category: 'barrel'
        };
      }
    }
  }
  
  // ============================================================
  // CONFIG/TOOLING FILES (check early - no content needed)
  // ============================================================
  if (isConfigOrToolingFile(relPath)) {
    // Only include if it has executable content
    if (content.includes('module.exports') || content.includes('export default') || 
        content.includes('defineConfig') || content.includes('createConfig')) {
      return {
        path: relPath,
        reason: 'Config/Build tool',
        confidence: 'high',
        category: 'tooling'
      };
    }
    return null; // Skip plain config files
  }
  
  // ============================================================
  // PYTHON ENTRY POINTS
  // ============================================================
  if (ext === '.py') {
    return analyzePythonEntryPoint(relPath, basename, content);
  }
  
  // ============================================================
  // TYPESCRIPT/JAVASCRIPT ENTRY POINTS
  // ============================================================
  if (['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
    return analyzeTSJSEntryPoint(relPath, basename, pathLower, content);
  }
  
  // ============================================================
  // C# ENTRY POINTS
  // ============================================================
  if (ext === '.cs') {
    return analyzeCSharpEntryPoint(relPath, basename, content);
  }
  
  // ============================================================
  // JAVA ENTRY POINTS
  // ============================================================
  if (ext === '.java') {
    return analyzeJavaEntryPoint(relPath, basename, content);
  }
  
  return null;
}

/**
 * Analyze Python file for entry point patterns.
 */
function analyzePythonEntryPoint(relPath: string, basename: string, content: string): DetectedEntryPoint | null {
  // FastAPI detection (HIGH confidence)
  const hasFastAPI = content.includes('FastAPI(') || content.includes('from fastapi');
  const fastAPIRoutes = (content.match(/@(app|router)\.(get|post|put|delete|patch|options|head)\s*\(/gi) || []).length;
  
  if (hasFastAPI && fastAPIRoutes > 0) {
    return {
      path: relPath,
      reason: `FastAPI (${fastAPIRoutes} routes)`,
      confidence: 'high',
      category: 'runtime',
      routeCount: fastAPIRoutes
    };
  }
  
  // Flask detection (HIGH confidence)
  const hasFlask = content.includes('Flask(__name__)') || content.includes('from flask import Flask');
  const flaskRoutes = (content.match(/@(app|blueprint|bp)\.(route|get|post|put|delete|patch)\s*\(/gi) || []).length;
  
  if (hasFlask && flaskRoutes > 0) {
    return {
      path: relPath,
      reason: `Flask (${flaskRoutes} routes)`,
      confidence: 'high',
      category: 'runtime',
      routeCount: flaskRoutes
    };
  }
  
  // Django detection
  if (basename === 'urls' && content.includes('urlpatterns')) {
    const urlPatterns = (content.match(/path\s*\(|re_path\s*\(|url\s*\(/g) || []).length;
    return {
      path: relPath,
      reason: `Django URLs (${urlPatterns} patterns)`,
      confidence: 'high',
      category: 'runtime',
      routeCount: urlPatterns
    };
  }
  
  if (basename === 'views' && (content.includes('def get(') || content.includes('def post(') || content.includes('@api_view'))) {
    return {
      path: relPath,
      reason: 'Django views',
      confidence: 'medium',
      category: 'runtime',
      routeCount: 1
    };
  }
  
  if ((basename === 'wsgi' || basename === 'asgi') && content.includes('application')) {
    return {
      path: relPath,
      reason: `Django ${basename.toUpperCase()} entry`,
      confidence: 'high',
      category: 'runtime',
      routeCount: 1
    };
  }
  
  // __main__.py is always a runtime entry
  if (basename === '__main__') {
    return {
      path: relPath,
      reason: 'Python main module',
      confidence: 'high',
      category: 'runtime',
      routeCount: 1
    };
  }
  
  // CLI tools with click/typer (TOOLING)
  if (content.includes('@click.command') || content.includes('@click.group') || 
      content.includes('@app.command') && content.includes('import typer')) {
    return {
      path: relPath,
      reason: 'CLI tool (click/typer)',
      confidence: 'high',
      category: 'tooling'
    };
  }
  
  // if __name__ == "__main__" pattern (TOOLING unless it's a web server)
  if (content.includes('if __name__') && content.includes('__main__')) {
    // Check if it starts a server
    if (content.includes('uvicorn.run') || content.includes('app.run(') || content.includes('.serve(')) {
      return {
        path: relPath,
        reason: 'Server entry',
        confidence: 'high',
        category: 'runtime',
        routeCount: 1
      };
    }
    return {
      path: relPath,
      reason: 'Script entry (__main__)',
      confidence: 'medium',
      category: 'tooling'
    };
  }
  
  // main.py, app.py, server.py without specific framework (medium confidence)
  if (['main', 'app', 'server', 'application'].includes(basename)) {
    return {
      path: relPath,
      reason: `Entry point (${basename})`,
      confidence: 'medium',
      category: 'runtime',
      routeCount: 0
    };
  }
  
  return null;
}

/**
 * Analyze TypeScript/JavaScript file for entry point patterns.
 */
function analyzeTSJSEntryPoint(
  relPath: string, 
  basename: string, 
  pathLower: string,
  content: string
): DetectedEntryPoint | null {
  // Next.js API routes (HIGH confidence)
  if (pathLower.includes('pages/api/') || pathLower.includes('app/api/')) {
    const hasHandler = content.includes('export default') || content.includes('export async function');
    if (hasHandler) {
      return {
        path: relPath,
        reason: 'Next.js API route',
        confidence: 'high',
        category: 'runtime',
        routeCount: 1
      };
    }
  }
  
  // Next.js middleware
  if (basename === 'middleware' && (pathLower.endsWith('.ts') || pathLower.endsWith('.js'))) {
    if (content.includes('NextRequest') || content.includes('NextResponse')) {
      return {
        path: relPath,
        reason: 'Next.js middleware',
        confidence: 'high',
        category: 'runtime',
        routeCount: 1
      };
    }
  }
  
  // Express/Fastify/Koa route detection
  const expressRoutes = (content.match(/\.(get|post|put|delete|patch|use)\s*\(\s*['"]/g) || []).length;
  const hasExpressApp = content.includes('express()') || content.includes('fastify(') || content.includes('new Koa(');
  
  if (hasExpressApp || expressRoutes > 2) {
    return {
      path: relPath,
      reason: `Express/HTTP server (${expressRoutes} routes)`,
      confidence: expressRoutes > 0 ? 'high' : 'medium',
      category: 'runtime',
      routeCount: expressRoutes
    };
  }
  
  // NestJS controllers
  if (content.includes('@Controller') || content.includes('@Injectable')) {
    const nestRoutes = (content.match(/@(Get|Post|Put|Delete|Patch|All)\s*\(/g) || []).length;
    if (nestRoutes > 0) {
      return {
        path: relPath,
        reason: `NestJS controller (${nestRoutes} routes)`,
        confidence: 'high',
        category: 'runtime',
        routeCount: nestRoutes
      };
    }
  }
  
  // Hono routes (Cloudflare Workers, etc.)
  if (content.includes('new Hono(') || content.includes('Hono.get') || content.includes('app.get(')) {
    const honoRoutes = (content.match(/\.(get|post|put|delete|patch)\s*\(/g) || []).length;
    if (honoRoutes > 0) {
      return {
        path: relPath,
        reason: `Hono server (${honoRoutes} routes)`,
        confidence: 'high',
        category: 'runtime',
        routeCount: honoRoutes
      };
    }
  }
  
  // require.main === module pattern (TOOLING)
  if (content.includes('require.main === module')) {
    return {
      path: relPath,
      reason: 'Node.js script entry',
      confidence: 'medium',
      category: 'tooling'
    };
  }
  
  // Check for bin/CLI scripts
  if (pathLower.includes('/bin/') || pathLower.includes('/cli/')) {
    if (content.includes('#!/') || content.includes('commander') || content.includes('yargs')) {
      return {
        path: relPath,
        reason: 'CLI script',
        confidence: 'medium',
        category: 'tooling'
      };
    }
  }
  
  // Server files by name
  if (['server', 'main', 'app', 'index'].includes(basename)) {
    // Check if it starts a server
    if (content.includes('.listen(') || content.includes('createServer') || 
        content.includes('http.createServer') || content.includes('https.createServer')) {
      return {
        path: relPath,
        reason: 'Server entry',
        confidence: 'high',
        category: 'runtime',
        routeCount: 1
      };
    }
    
    // Generic entry by name (lower confidence)
    if (basename === 'main' || basename === 'server') {
      return {
        path: relPath,
        reason: `Entry point (${basename})`,
        confidence: 'medium',
        category: 'runtime',
        routeCount: 0
      };
    }
  }
  
  return null;
}

/**
 * Analyze C# file for entry point patterns.
 */
function analyzeCSharpEntryPoint(relPath: string, basename: string, content: string): DetectedEntryPoint | null {
  // ASP.NET Program.cs with WebApplication (HIGH confidence)
  if (basename === 'program') {
    if (content.includes('WebApplication.CreateBuilder') || content.includes('CreateHostBuilder') ||
        content.includes('UseStartup') || content.includes('app.Run()')) {
      const mapRoutes = (content.match(/\.Map(Get|Post|Put|Delete|Patch)\s*\(/g) || []).length;
      return {
        path: relPath,
        reason: `ASP.NET entry${mapRoutes > 0 ? ` (${mapRoutes} routes)` : ''}`,
        confidence: 'high',
        category: 'runtime',
        routeCount: mapRoutes || 1
      };
    }
    
    // Console app Program.cs
    if (content.includes('static void Main') || content.includes('static async Task Main')) {
      return {
        path: relPath,
        reason: 'Console app entry',
        confidence: 'medium',
        category: 'tooling'
      };
    }
  }
  
  // ASP.NET Controllers
  if (content.includes('[ApiController]') || content.includes('[Controller]')) {
    const routes = (content.match(/\[(Http(Get|Post|Put|Delete|Patch)|Route)\]/g) || []).length;
    return {
      path: relPath,
      reason: `ASP.NET controller (${routes} routes)`,
      confidence: routes > 0 ? 'high' : 'medium',
      category: 'runtime',
      routeCount: routes
    };
  }
  
  // Startup.cs
  if (basename === 'startup' && content.includes('ConfigureServices')) {
    return {
      path: relPath,
      reason: 'ASP.NET Startup config',
      confidence: 'high',
      category: 'runtime',
      routeCount: 1
    };
  }
  
  return null;
}

/**
 * Analyze Java file for entry point patterns.
 */
function analyzeJavaEntryPoint(relPath: string, basename: string, content: string): DetectedEntryPoint | null {
  // Spring Boot main class (HIGH confidence)
  if (content.includes('@SpringBootApplication')) {
    return {
      path: relPath,
      reason: 'Spring Boot entry',
      confidence: 'high',
      category: 'runtime',
      routeCount: 1
    };
  }
  
  // Spring controllers
  if (content.includes('@RestController') || content.includes('@Controller')) {
    const mappings = (content.match(/@(Get|Post|Put|Delete|Patch|Request)Mapping/g) || []).length;
    return {
      path: relPath,
      reason: `Spring controller (${mappings} endpoints)`,
      confidence: mappings > 0 ? 'high' : 'medium',
      category: 'runtime',
      routeCount: mappings
    };
  }
  
  // JAX-RS resources
  if (content.includes('@Path(') && (content.includes('@GET') || content.includes('@POST'))) {
    const jaxRoutes = (content.match(/@(GET|POST|PUT|DELETE|PATCH)/g) || []).length;
    return {
      path: relPath,
      reason: `JAX-RS resource (${jaxRoutes} endpoints)`,
      confidence: 'high',
      category: 'runtime',
      routeCount: jaxRoutes
    };
  }
  
  // Public static void main (check if not Spring Boot)
  if (content.includes('public static void main(String')) {
    if (!content.includes('@SpringBootApplication')) {
      return {
        path: relPath,
        reason: 'Java main class',
        confidence: 'medium',
        category: 'tooling'
      };
    }
  }
  
  return null;
}

/**
 * Legacy sync entry point detection (filename-based only).
 * Used as fallback when async detection is not available.
 */
function detectEntryPoints(files: string[], workspaceRoot: string): Array<{ path: string; reason: string; confidence: 'high' | 'medium' | 'low' }> {
  const entryPoints: Array<{ path: string; reason: string; confidence: 'high' | 'medium' | 'low' }> = [];
  
  // High-confidence entry point patterns
  const highConfidence = ['main', '__main__', 'server', 'app'];
  // Medium-confidence entry point patterns
  const mediumConfidence = ['index', 'start', 'cli', 'run'];
  // Low-confidence (could be entry, needs verification)
  const lowConfidence = ['bootstrap', 'init', 'setup'];

  for (const file of files) {
    const basename = path.basename(file, path.extname(file)).toLowerCase();
    const relPath = makeRelativePath(file, workspaceRoot);
    const ext = path.extname(file).toLowerCase();

    // Python __main__.py is always high confidence
    if (basename === '__main__' && ext === '.py') {
      entryPoints.push({ path: relPath, reason: 'Python main module', confidence: 'high' });
    } else if (highConfidence.includes(basename)) {
      entryPoints.push({ path: relPath, reason: `Entry point (${basename})`, confidence: 'high' });
    } else if (mediumConfidence.includes(basename)) {
      entryPoints.push({ path: relPath, reason: `Entry point (${basename})`, confidence: 'medium' });
    } else if (lowConfidence.includes(basename)) {
      entryPoints.push({ path: relPath, reason: `Possible entry (${basename})`, confidence: 'low' });
    }
  }

  // Sort by confidence (high first)
  const confidenceOrder = { high: 0, medium: 1, low: 2 };
  entryPoints.sort((a, b) => confidenceOrder[a.confidence] - confidenceOrder[b.confidence]);

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
  outputChannel: vscode.OutputChannel,
  fileContentCache?: Map<string, string>
): Promise<{
  stats: Map<string, { inDegree: number; outDegree: number }>;
  links: DependencyLink[];
}> {
  const stats = new Map<string, { inDegree: number; outDegree: number }>();
  let links: DependencyLink[] = [];

  try {
    if (files.length === 0) return { stats, links };

    const analyzer = new DependencyAnalyzer();
    // Use cached content if available to avoid reading files again
    if (fileContentCache && fileContentCache.size > 0) {
      analyzer.setFileContentsCache(fileContentCache);
    }
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
  const extensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.java', '.cs', '.cpp', '.c', '.go', '.rs'];

  try {
    const pattern = new vscode.RelativePattern(workspaceRoot, '**/*');
    // Exclude common environment, dependency, and build directories
    const exclude = '{**/node_modules/**,**/.venv/**,**/venv/**,**/env/**,**/site-packages/**,**/__pycache__/**,**/.tox/**,**/.pytest_cache/**,**/.mypy_cache/**,**/dist/**,**/build/**,**/.next/**,**/.turbo/**,**/coverage/**,**/.cache/**,**/dist-packages/**,**/.git/**,**/.hg/**}';
    const uris = await vscode.workspace.findFiles(pattern, exclude, 1000);

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

/**
 * Convert an absolute path to a relative path from the workspace root.
 * Always uses forward slashes for cross-platform consistency.
 */
function makeRelativePath(absPath: string, workspaceRoot: string): string {
  // Normalize both paths to use forward slashes for comparison
  const normalizedAbs = absPath.replace(/\\/g, '/');
  const normalizedRoot = workspaceRoot.replace(/\\/g, '/').replace(/\/$/, '');
  
  if (normalizedAbs.startsWith(normalizedRoot)) {
    return normalizedAbs.substring(normalizedRoot.length).replace(/^\//, '');
  }
  return path.basename(absPath);
}

/**
 * Remove duplicate entries from an array while preserving order.
 */
function dedupe<T>(items: T[], keyFn?: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter(item => {
    const key = keyFn ? keyFn(item) : String(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

// ============================================================================
// File Classification - Project vs Test vs Third-Party
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
