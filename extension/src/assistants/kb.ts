import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';

/**
 * Ensures .aspect/ and AGENTS.md are added to .gitignore.
 * If .gitignore doesn't exist, prompts the user to create one.
 */
async function ensureGitignore(workspaceRoot: vscode.Uri, outputChannel: vscode.OutputChannel): Promise<void> {
  const gitignorePath = vscode.Uri.joinPath(workspaceRoot, '.gitignore');
  const aspectEntry = '.aspect/';
  const agentsEntry = 'AGENTS.md';
  
  try {
    // Try to read existing .gitignore
    const content = await vscode.workspace.fs.readFile(gitignorePath);
    let text = Buffer.from(content).toString('utf8');
    const lines = text.split(/\r?\n/);
    let modified = false;
    
    // Check if .aspect/ is already in .gitignore
    const hasAspect = lines.some(line => {
      const trimmed = line.trim();
      return trimmed === '.aspect/' || trimmed === '.aspect' || trimmed === '/.aspect/' || trimmed === '/.aspect';
    });
    
    if (!hasAspect) {
      // Add .aspect/ to .gitignore, preserving existing content
      text = text.endsWith('\n') 
        ? text + aspectEntry + '\n'
        : text + '\n' + aspectEntry + '\n';
      modified = true;
      outputChannel.appendLine('[KB] Added .aspect/ to .gitignore');
    }
    
    // Check if AGENTS.md is already in .gitignore
    const hasAgents = lines.some(line => {
      const trimmed = line.trim();
      return trimmed === 'AGENTS.md' || trimmed === '/AGENTS.md';
    });
    
    if (!hasAgents) {
      // Add AGENTS.md to .gitignore
      text = text.endsWith('\n') 
        ? text + agentsEntry + '\n'
        : text + '\n' + agentsEntry + '\n';
      modified = true;
      outputChannel.appendLine('[KB] Added AGENTS.md to .gitignore');
    }
    
    if (modified) {
      await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(text, 'utf8'));
    }
  } catch (error) {
    // .gitignore doesn't exist - prompt the user
    const action = await vscode.window.showInformationMessage(
      'No .gitignore found. Create one with .aspect/ and AGENTS.md excluded?',
      'Create .gitignore',
      'Dismiss'
    );
    
    if (action === 'Create .gitignore') {
      const defaultContent = `# Aspect Code knowledge base (auto-generated)
${aspectEntry}
${agentsEntry}
`;
      await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(defaultContent, 'utf8'));
      outputChannel.appendLine('[KB] Created .gitignore with .aspect/ and AGENTS.md excluded');
    } else {
      outputChannel.appendLine('[KB] Warning: .aspect/ and AGENTS.md not added to .gitignore');
    }
  }
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
  return state.s.findings
    .filter(f => f.code === ruleId)
    .map(f => ({
      file: f.file,
      message: f.message,
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
 * V3 Files generated:
 * - architecture.md: The Guardrail - layout, hubs, entry points
 * - map.md: The Context - symbols, data models, conventions
 * - context.md: The Flow - clusters, flows, integrations
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

  outputChannel.appendLine('[KB] Generating V3 knowledge base in .aspect/');

  // Pre-fetch shared data
  const files = await discoverWorkspaceFiles(workspaceRoot);
  const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, files, outputChannel);

  // Generate all KB files in parallel (V3: 3 files)
  await Promise.all([
    generateArchitectureFile(aspectCodeDir, state, workspaceRoot, files, depData, allLinks, outputChannel),
    generateMapFile(aspectCodeDir, state, workspaceRoot, files, depData, allLinks, outputChannel),
    generateContextFile(aspectCodeDir, state, workspaceRoot, files, allLinks, outputChannel)
  ]);

  outputChannel.appendLine('[KB] Knowledge base generation complete (3 files)');
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
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Architecture\n\n';
  content += '_Read this first. Describes the project layout and "Do Not Break" zones._\n\n';

  if (files.length === 0) {
    content += '_No source files found._\n';
  } else {
    // Quick stats
    const totalEdges = allLinks.length;
    const circularLinks = allLinks.filter(l => l.type === 'circular');
    const cycleCount = Math.ceil(circularLinks.length / 2);
    
    content += `**Files:** ${files.length} | **Dependencies:** ${totalEdges} | **Cycles:** ${cycleCount}\n\n`;

    // Filter to app files for architectural views
    const appFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'app');
    const testFiles = files.filter(f => classifyFile(f, workspaceRoot.fsPath) === 'test');
    const findings = state.s.findings;

    // Build finding counts per file for Orgalion-style hotspot ranking
    const findingCounts = new Map<string, { total: number; critical: number }>();
    for (const finding of findings) {
      if (classifyFile(finding.file, workspaceRoot.fsPath) !== 'app') continue;
      if (!findingCounts.has(finding.file)) {
        findingCounts.set(finding.file, { total: 0, critical: 0 });
      }
      const counts = findingCounts.get(finding.file)!;
      counts.total++;
      if (finding.severity === 'error') counts.critical++;
    }

    // ============================================================
    // HIGH-RISK ARCHITECTURAL HUBS (Orgalion + V2 merged)
    // ============================================================
    // Ranking: (inDegree + outDegree) * 2 + findingCount
    const hubs = Array.from(depData.entries())
      .filter(([file]) => isStructuralAppFile(file, workspaceRoot.fsPath))
      .map(([file, info]) => {
        const fc = findingCounts.get(file) || { total: 0, critical: 0 };
        const depScore = info.inDegree + info.outDegree;
        const hotspotScore = (depScore * 2) + fc.total;
        return {
          file,
          inDegree: info.inDegree,
          outDegree: info.outDegree,
          totalDegree: depScore,
          findings: fc.total,
          criticalFindings: fc.critical,
          hotspotScore
        };
      })
      .filter(h => h.totalDegree > 2 || h.findings > 0)
      .sort((a, b) => b.hotspotScore - a.hotspotScore)
      .slice(0, 12);

    if (hubs.length > 0) {
      content += '## ⚠️ High-Risk Architectural Hubs\n\n';
      content += '> **These files are architectural load-bearing walls.**\n';
      content += '> Modify with extreme caution. Do not change signatures without checking `map.md`.\n\n';
      
      content += '| Rank | File | Imports | Imported By | Issues | Risk |\n';
      content += '|------|------|---------|-------------|--------|------|\n';
      
      for (let i = 0; i < hubs.length; i++) {
        const hub = hubs[i];
        const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
        const risk = hub.inDegree > 8 || hub.criticalFindings > 0 ? '🔴 High' : 
                     hub.inDegree > 4 || hub.findings > 3 ? '🟡 Medium' : '🟢 Low';
        content += `| ${i + 1} | \`${relPath}\` | ${hub.outDegree} | ${hub.inDegree} | ${hub.findings} | ${risk} |\n`;
      }
      content += '\n';

      // Show top 3 hub details (who imports them)
      content += '### Hub Details\n\n';
      for (let i = 0; i < Math.min(3, hubs.length); i++) {
        const hub = hubs[i];
        const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
        const importers = allLinks
          .filter(l => l.target === hub.file && l.source !== hub.file)
          .filter(l => classifyFile(l.source, workspaceRoot.fsPath) === 'app')
          .slice(0, 5);
        
        content += `**${i + 1}. \`${relPath}\`** (${hub.inDegree} importers)\n`;
        if (importers.length > 0) {
          content += 'Imported by:\n';
          for (const imp of importers) {
            const impRel = makeRelativePath(imp.source, workspaceRoot.fsPath);
            content += `- \`${impRel}\`\n`;
          }
          if (hub.inDegree > 5) {
            content += `- _...and ${hub.inDegree - 5} more_\n`;
          }
        }
        content += '\n';
      }
    }

    // ============================================================
    // ENTRY POINTS
    // ============================================================
    const ruleEntryPoints = extractKBEnrichingFindings(state, KB_ENRICHING_RULES.ENTRY_POINT)
      .filter(f => classifyFile(f.file, workspaceRoot.fsPath) === 'app');
    const fileEntryPoints = detectEntryPoints(appFiles, workspaceRoot.fsPath);
    
    if (ruleEntryPoints.length > 0 || fileEntryPoints.length > 0) {
      content += '## Entry Points\n\n';
      content += '_Where requests enter the system._\n\n';
      
      // Group by type
      const httpHandlers = ruleEntryPoints.filter(f => f.message.includes('HTTP'));
      const cliCommands = ruleEntryPoints.filter(f => f.message.includes('CLI'));
      const mainFunctions = ruleEntryPoints.filter(f => f.message.includes('Main'));
      
      if (httpHandlers.length > 0) {
        content += `**API Routes:** ${httpHandlers.length} endpoints\n`;
        for (const handler of httpHandlers.slice(0, 5)) {
          const relPath = makeRelativePath(handler.file, workspaceRoot.fsPath);
          const info = handler.message.replace('HTTP entry point: ', '');
          content += `- \`${relPath}\`: ${info}\n`;
        }
        if (httpHandlers.length > 5) {
          content += `- _...and ${httpHandlers.length - 5} more_\n`;
        }
        content += '\n';
      }
      
      if (cliCommands.length > 0) {
        content += `**CLI Commands:** ${cliCommands.length}\n`;
        for (const cmd of cliCommands.slice(0, 3)) {
          const relPath = makeRelativePath(cmd.file, workspaceRoot.fsPath);
          content += `- \`${relPath}\`: ${cmd.message}\n`;
        }
        content += '\n';
      }
      
      if (mainFunctions.length > 0 || fileEntryPoints.length > 0) {
        content += '**Application Entry:**\n';
        for (const entry of [...mainFunctions.slice(0, 2), ...fileEntryPoints.slice(0, 3)].slice(0, 4)) {
          if ('message' in entry) {
            const relPath = makeRelativePath(entry.file, workspaceRoot.fsPath);
            content += `- \`${relPath}\`: ${entry.message}\n`;
          } else {
            content += `- \`${entry.path}\`: ${entry.reason}\n`;
          }
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
      isStructuralAppFile(l.target, workspaceRoot.fsPath)
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

  const architectureFile = vscode.Uri.joinPath(aspectCodeDir, 'architecture.md');
  await vscode.workspace.fs.writeFile(architectureFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated architecture.md`);
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
  outputChannel: vscode.OutputChannel
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

    // Show models with enhanced signatures
    if (ormModels.length > 0) {
      content += '### ORM / Database Models\n\n';
      for (const model of ormModels.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const modelInfo = model.message.replace('Data model: ', '').replace('ORM model: ', '');
        // Try to extract signature from file
        const signature = await extractModelSignature(model.file, modelInfo);
        if (signature) {
          content += `**\`${relPath}\`**: \`${signature}\`\n\n`;
        } else {
          content += `**\`${relPath}\`**: ${modelInfo}\n\n`;
        }
      }
    }

    if (dataClasses.length > 0) {
      content += '### Pydantic / Data Classes\n\n';
      for (const model of dataClasses.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const modelInfo = model.message.replace('Data model: ', '');
        const signature = await extractModelSignature(model.file, modelInfo);
        if (signature) {
          content += `**\`${relPath}\`**: \`${signature}\`\n\n`;
        } else {
          content += `**\`${relPath}\`**: ${modelInfo}\n\n`;
        }
      }
    }

    if (interfaces.length > 0) {
      content += '### TypeScript Interfaces & Types\n\n';
      for (const model of interfaces.slice(0, 15)) {
        const relPath = makeRelativePath(model.file, workspaceRoot.fsPath);
        const modelInfo = model.message.replace('Data model: ', '');
        const signature = await extractModelSignature(model.file, modelInfo);
        if (signature) {
          content += `**\`${relPath}\`**: \`${signature}\`\n\n`;
        } else {
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

    for (const file of sortedFiles) {
      const relPath = makeRelativePath(file, workspaceRoot.fsPath);
      const symbols = await extractFileSymbolsWithSignatures(file, allLinks, workspaceRoot.fsPath);

      if (symbols.length === 0) continue;

      content += `### \`${relPath}\`\n\n`;
      content += '| Symbol | Kind | Signature | Called By |\n';
      content += '|--------|------|-----------|----------|\n';

      for (const symbol of symbols.slice(0, 12)) {
        const sig = symbol.signature ? `\`${symbol.signature}\`` : '—';
        const calledBy = symbol.calledBy.slice(0, 2).map(c => `\`${c}\``).join(', ') || '—';
        content += `| \`${symbol.name}\` | ${symbol.kind} | ${sig} | ${calledBy} |\n`;
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

  const mapFile = vscode.Uri.joinPath(aspectCodeDir, 'map.md');
  await vscode.workspace.fs.writeFile(mapFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated map.md`);
}

/**
 * Extract model signature (first line/fields) from a file
 */
async function extractModelSignature(filePath: string, modelName: string): Promise<string | null> {
  try {
    const uri = vscode.Uri.file(filePath);
    const content = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(content).toString('utf-8');
    const lines = text.split('\n');
    const ext = path.extname(filePath).toLowerCase();
    
    // Extract just the class/model name without extra details
    const cleanName = modelName.split(':')[0].split('(')[0].trim();
    
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
    }
  } catch {
    // Ignore errors
  }
  return null;
}

/**
 * Extract file symbols with enhanced signature information
 */
async function extractFileSymbolsWithSignatures(
  filePath: string,
  allLinks: DependencyLink[],
  workspaceRoot: string
): Promise<Array<{ name: string; kind: string; signature: string | null; calledBy: string[] }>> {
  const symbols: Array<{ name: string; kind: string; signature: string | null; calledBy: string[] }> = [];
  
  try {
    const uri = vscode.Uri.file(filePath);
    const content = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(content).toString('utf-8');
    const lines = text.split('\n');
    const ext = path.extname(filePath).toLowerCase();
    
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
      for (const line of lines) {
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
        }
        
        // Classes
        const classMatch = line.match(/export\s+(?:abstract\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?/);
        if (classMatch) {
          const ext = classMatch[2] ? ` extends ${classMatch[2]}` : '';
          symbols.push({
            name: classMatch[1],
            kind: 'class',
            signature: `class ${classMatch[1]}${ext}`,
            calledBy: getSymbolCallers(classMatch[1], filePath, allLinks, workspaceRoot)
          });
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
        }
        
        // Consts
        const constMatch = line.match(/export\s+const\s+(\w+)\s*[:=]/);
        if (constMatch) {
          symbols.push({
            name: constMatch[1],
            kind: 'const',
            signature: null,
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
  outputChannel: vscode.OutputChannel
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
      content += '_Files commonly edited/imported together. Use for feature co-location._\n\n';
      
      for (const cluster of clusters.slice(0, 8)) {
        content += `### ${cluster.name}\n\n`;
        for (const file of cluster.files.slice(0, 6)) {
          content += `- \`${file}\`\n`;
        }
        if (cluster.files.length > 6) {
          content += `- _...and ${cluster.files.length - 6} more_\n`;
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
      content += '|--------|---------|--------------|n';
      for (const [file, stats] of topModules) {
        const relPath = makeRelativePath(file, workspaceRoot.fsPath);
        content += `| \`${relPath}\` | ${stats.inDegree} | ${stats.outDegree} |\n`;
      }
      content += '\n';
    }

    // ============================================================
    // DEPENDENCY CHAINS
    // ============================================================
    const chains = findDependencyChains(appLinks, workspaceRoot.fsPath, 3);
    if (chains.length > 0) {
      content += '## Dependency Chains\n\n';
      content += '_How modules chain together. Useful for tracing data flow._\n\n';
      
      for (const chain of chains.slice(0, 4)) {
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

  const contextFile = vscode.Uri.joinPath(aspectCodeDir, 'context.md');
  await vscode.workspace.fs.writeFile(contextFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated context.md`);
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

function getSymbolCallers(symbolName: string, filePath: string, allLinks: DependencyLink[], workspaceRoot?: string): string[] {
  return allLinks
    .filter(l => {
      if (l.target !== filePath || !l.symbols.includes(symbolName)) return false;
      // Filter out third-party and test files from callers
      if (workspaceRoot && classifyFile(l.source, workspaceRoot) !== 'app') return false;
      return true;
    })
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

function makeRelativePath(absPath: string, workspaceRoot: string): string {
  if (absPath.startsWith(workspaceRoot)) {
    return absPath.substring(workspaceRoot.length).replace(/^[\\\/]/, '');
  }
  return path.basename(absPath);
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
