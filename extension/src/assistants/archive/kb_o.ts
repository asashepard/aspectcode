import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';

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
    
    outputChannel.appendLine('[KB] Auto-regenerated after validation update');
  } catch (error) {
    outputChannel.appendLine(`[KB] Auto-regeneration failed (non-critical): ${error}`);
  }
}

/**
 * Generates the .aspect/ knowledge base directory with markdown files.
 * Focus: structural analysis (dependencies, hotspots) for AI assistants.
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

  outputChannel.appendLine('[KB] Generating knowledge base files in .aspect/');

  // Generate all KB files
  await Promise.all([
    generateHotspotsFile(aspectCodeDir, state, workspaceRoot, outputChannel),
    generateDepsFile(aspectCodeDir, state, workspaceRoot, outputChannel),
    generateArchitectureFile(aspectCodeDir, state, workspaceRoot, outputChannel),
    generateSymbolsFile(aspectCodeDir, state, workspaceRoot, outputChannel),
    generateFlowsFile(aspectCodeDir, state, workspaceRoot, outputChannel),
    generateFindingsTopFile(aspectCodeDir, state, workspaceRoot, outputChannel)
  ]);

  outputChannel.appendLine('[KB] Knowledge base generation complete');
}



/**
 * Generate .aspect/hotspots.md - files ranked by finding density in canonical LLM-friendly format
 * Format: Top hotspot files (top 10 by findings), Safer files (5-10 low-risk files)
 */
async function generateHotspotsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Aspect Code Hotspot Files\n\n';
  content += 'These files have the highest concentration of issues and dependencies.\n\n';
  
  const findings = state.s.findings;
  
  // Get dependency data
  const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, outputChannel);
  
  if (findings.length === 0) {
    content += '## Top hotspot files (by number of findings)\n\n';
    content += '_No data available. Run analysis first._\n\n';
    
    content += '## Safer files (few deps, mostly style issues)\n\n';
    content += '_No data available. Run analysis first._\n\n';
  } else {
    // Group findings by file
    const fileMap = new Map<string, typeof findings>();
    for (const finding of findings) {
      const file = finding.file;
      if (!fileMap.has(file)) {
        fileMap.set(file, []);
      }
      fileMap.get(file)!.push(finding);
    }

    // Count high/critical findings per file
    const fileMetrics = Array.from(fileMap.entries()).map(([file, fileFindings]) => {
      const highCritical = fileFindings.filter(f => 
        f.severity === 'error' || f.severity === 'critical'
      ).length;
      
      // Count top rules
      const ruleMap = new Map<string, number>();
      for (const finding of fileFindings) {
        ruleMap.set(finding.code, (ruleMap.get(finding.code) || 0) + 1);
      }
      const topRules = Array.from(ruleMap.entries())
        .sort((a, b) => b[1] - a[1])
        .slice(0, 3);
      
      // Get dependency info
      const depInfo = depData.get(file);
      const totalDegree = depInfo ? depInfo.inDegree + depInfo.outDegree : 0;
      
      return {
        file,
        findings: fileFindings,
        totalFindings: fileFindings.length,
        highCritical,
        topRules,
        depInfo,
        totalDegree
      };
    });
    
    // Sort by total findings, break ties with high/critical count
    const hotspots = fileMetrics
      .sort((a, b) => {
        if (b.totalFindings !== a.totalFindings) {
          return b.totalFindings - a.totalFindings;
        }
        return b.highCritical - a.highCritical;
      })
      .slice(0, 10);
    
    content += '## Top hotspot files (by number of findings)\n\n';
    
    for (let i = 0; i < hotspots.length; i++) {
      const hs = hotspots[i];
      const relPath = makeRelativePath(hs.file, workspaceRoot.fsPath);
      
      content += `${i + 1}. \`${relPath}\`\n`;
      content += `   - Total findings: ${hs.totalFindings}\n`;
      content += `   - High/critical findings: ${hs.highCritical}\n`;
      
      if (hs.topRules.length > 0) {
        content += '   - Top rules:\n';
        for (const [ruleId, count] of hs.topRules) {
          content += `     - \`${ruleId}\` (${count})\n`;
        }
      }
      
      // Dependency summary
      if (hs.depInfo) {
        if (hs.depInfo.outDegree > 0) {
          const dependsOn = allLinks
            .filter(l => l.source === hs.file)
            .slice(0, 3)
            .map(l => path.basename(l.target, path.extname(l.target)));
          if (dependsOn.length > 0) {
            content += `   - Depends on: ${dependsOn.join(', ')}${hs.depInfo.outDegree > 3 ? ', ...' : ''}\n`;
          }
        }
        if (hs.depInfo.inDegree > 0) {
          const dependedBy = allLinks
            .filter(l => l.target === hs.file)
            .slice(0, 3)
            .map(l => path.basename(l.source, path.extname(l.source)));
          if (dependedBy.length > 0) {
            content += `   - Depended on by: ${dependedBy.join(', ')}${hs.depInfo.inDegree > 3 ? ', ...' : ''}\n`;
          }
        }
      }
      
      content += '\n';
    }
    
    // Safer files: low severity + low dependency degree (good refactor targets)
    const saferFiles = fileMetrics
      .filter(m => m.highCritical === 0 && m.totalDegree < 5)
      .sort((a, b) => a.totalFindings - b.totalFindings)
      .slice(0, 10);
    
    content += '## Safer files (few deps, mostly style issues)\n\n';
    
    if (saferFiles.length === 0) {
      content += '_No safer files identified._\n\n';
    } else {
      for (const sf of saferFiles) {
        const relPath = makeRelativePath(sf.file, workspaceRoot.fsPath);
        content += `- \`${relPath}\`\n`;
        content += `  - Total findings: ${sf.totalFindings}\n`;
        content += `  - High/critical findings: ${sf.highCritical}\n`;
        
        if (sf.topRules.length > 0) {
          const ruleIds = sf.topRules.map(([id]) => `\`${id}\``).join(', ');
          content += `  - Mostly: ${ruleIds}\n`;
        }
        content += '\n';
      }
    }
  }
  
  content += `\n_Last updated: ${new Date().toISOString()}_\n`;
  
  const hotspotsFile = vscode.Uri.joinPath(aspectCodeDir, 'hotspots.md');
  await vscode.workspace.fs.writeFile(hotspotsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated hotspots.md (${findings.length} findings in ${fileMap.size} files)`);
}



/**
 * Generate .aspect/deps.md - dependency overview in canonical LLM-friendly format
 * Format: Summary stats, Hub modules (top 10), Circular dependencies (top 10)
 */
async function generateDepsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Aspect Code Dependency Overview\n\n';

  const { stats: depData, links: allLinks } = await getDetailedDependencyData(workspaceRoot, outputChannel);
  const totalFiles = depData.size;
  const totalEdges = allLinks.length;
  
  // Count project vs external modules (heuristic: external if in node_modules or site-packages)
  const projectModules = Array.from(depData.keys()).filter(f => 
    !f.includes('node_modules') && !f.includes('site-packages')
  );
  const externalModules = totalFiles - projectModules.length;
  
  // Count strongly connected components (cycles)
  const circularLinks = allLinks.filter(l => l.type === 'circular');
  const cycleCount = Math.ceil(circularLinks.length / 2); // Each cycle creates 2 circular links

  content += '## Summary\n';
  content += `- Total project modules: ${totalFiles}\n`;
  content += `- Project modules: ${projectModules.length}\n`;
  content += `- External modules: ${externalModules}\n`;
  content += `- Import edges: ${totalEdges}\n`;
  content += `- Strongly connected components (cycles): ${cycleCount}\n\n`;

  // Hub modules - top 10 by combined in-degree + out-degree
  // Ranking: High fan-in or fan-out indicates structural importance
  const hubs = Array.from(depData.entries())
    .map(([file, info]) => ({
      file,
      inDegree: info.inDegree,
      outDegree: info.outDegree,
      totalDegree: info.inDegree + info.outDegree
    }))
    .filter(h => h.totalDegree > 0)
    .sort((a, b) => b.totalDegree - a.totalDegree)
    .slice(0, 10);

  content += '## Hub modules (high fan-in or fan-out)\n\n';
  
  if (hubs.length === 0) {
    content += '_No data available. Run analysis first._\n\n';
  } else {
    for (let i = 0; i < hubs.length; i++) {
      const hub = hubs[i];
      const relPath = makeRelativePath(hub.file, workspaceRoot.fsPath);
      content += `${i + 1}. \`${relPath}\`\n`;
      content += `   - Imports: ${hub.outDegree} modules\n`;
      content += `   - Imported by: ${hub.inDegree} modules\n`;
      
      // Add brief note if this is heavily imported or heavily importing
      if (hub.inDegree > 10) {
        content += `   - Notes: Widely used (${hub.inDegree} importers)\n`;
      } else if (hub.outDegree > 15) {
        content += `   - Notes: High coupling (${hub.outDegree} dependencies)\n`;
      }
      content += '\n';
    }
  }

  // Circular dependencies - top 10 cycles by module count
  content += '## Circular dependencies\n\n';
  
  const circularLinksList = allLinks.filter(l => l.type === 'circular');
  
  if (circularLinksList.length === 0) {
    content += '_No data available. Run analysis first._\n\n';
  } else {
    // Group into unique cycles (each cycle has 2 circular links)
    const processedPairs = new Set<string>();
    const cycles: Array<{
      modules: string[];
      edges: Array<{ source: string; target: string; line?: number }>
    }> = [];
    
    for (const link of circularLinksList) {
      const pairKey = [link.source, link.target].sort().join('::');
      if (processedPairs.has(pairKey)) continue;
      processedPairs.add(pairKey);
      
      // Find both directions
      const forward = allLinks.find(l => l.source === link.source && l.target === link.target);
      const backward = allLinks.find(l => l.source === link.target && l.target === link.source);
      
      const edges: Array<{ source: string; target: string; line?: number }> = [];
      if (forward) {
        edges.push({
          source: link.source,
          target: link.target,
          line: forward.lines.length > 0 ? forward.lines[0] : undefined
        });
      }
      if (backward) {
        edges.push({
          source: link.target,
          target: link.source,
          line: backward.lines.length > 0 ? backward.lines[0] : undefined
        });
      }
      
      cycles.push({
        modules: [link.source, link.target],
        edges
      });
    }
    
    // Limit to top 10 cycles
    const topCycles = cycles.slice(0, 10);
    
    for (let i = 0; i < topCycles.length; i++) {
      const cycle = topCycles[i];
      content += `${i + 1}. Cycle ${String.fromCharCode(65 + i)}\n`;
      content += '   - Modules:\n';
      for (const module of cycle.modules) {
        const relPath = makeRelativePath(module, workspaceRoot.fsPath);
        content += `     - \`${relPath}\`\n`;
      }
      content += '   - Minimal cycle edges:\n';
      for (const edge of cycle.edges) {
        const sourceRel = makeRelativePath(edge.source, workspaceRoot.fsPath);
        const targetRel = makeRelativePath(edge.target, workspaceRoot.fsPath);
        if (edge.line) {
          content += `     - \`${sourceRel}:${edge.line}\` → \`${targetRel}\`\n`;
        } else {
          content += `     - \`${sourceRel}\` → \`${targetRel}\`\n`;
        }
      }
      content += '\n';
    }
  }

  content += `\n_Last updated: ${new Date().toISOString()}_\n`;

  const depsFile = vscode.Uri.joinPath(aspectCodeDir, 'deps.md');
  await vscode.workspace.fs.writeFile(depsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated deps.md (${totalFiles} modules, ${totalEdges} edges, ${cycleCount} cycles)`);
}

/**
 * Generate .aspect/architecture.md - comprehensive codebase structure mapping
 * Fills gaps in symbolic representation: directory structure, file purposes, module boundaries, entry points
 */
async function generateArchitectureFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Codebase Architecture\n\n';
  content += '_Comprehensive structural mapping of the codebase for AI agents._\n\n';

  // Discover all files
  const files = await discoverWorkspaceFiles(workspaceRoot);
  
  if (files.length === 0) {
    content += '_No source files found._\n';
  } else {
    // Analyze directory structure
    const dirStructure = analyzeDirStructure(files, workspaceRoot.fsPath);
    
    content += `**Total source files:** ${files.length}\n`;
    content += `**Languages detected:** ${detectLanguages(files).join(', ')}\n`;
    content += `**Directory depth:** ${calculateMaxDepth(files, workspaceRoot.fsPath)}\n\n`;

    // Entry points detection
    const entryPoints = detectEntryPoints(files, workspaceRoot.fsPath);
    if (entryPoints.length > 0) {
      content += '## Entry Points\n\n';
      content += '_Main executable files and application entry points._\n\n';
      for (const entry of entryPoints) {
        content += `- \`${entry.path}\` — ${entry.reason}\n`;
      }
      content += '\n';
    }

    // Directory structure with purposes
    content += '## Directory Structure\n\n';
    content += '_Organized view of the codebase with inferred purposes._\n\n';
    
    for (const [dir, info] of dirStructure.entries()) {
      const relDir = makeRelativePath(dir, workspaceRoot.fsPath) || '.';
      content += `### \`${relDir}/\`\n\n`;
      
      if (info.purpose) {
        content += `**Purpose:** ${info.purpose}\n\n`;
      }
      
      content += `**Files:** ${info.files.length}\n`;
      
      if (info.fileTypes.size > 0) {
        const types = Array.from(info.fileTypes.entries())
          .map(([ext, count]) => `${ext} (${count})`)
          .join(', ');
        content += `**Types:** ${types}\n`;
      }
      
      // List significant files in directory
      const significantFiles = info.files
        .filter(f => isSignificantFile(f))
        .slice(0, 10);
      
      if (significantFiles.length > 0) {
        content += '\n**Key files:**\n\n';
        for (const file of significantFiles) {
          const filename = path.basename(file);
          const purpose = inferFilePurpose(file, filename);
          content += `- \`${filename}\``;
          if (purpose) {
            content += ` — ${purpose}`;
          }
          content += '\n';
        }
      }
      
      content += '\n';
    }

    // Module boundaries and layers
    const moduleBoundaries = detectModuleBoundaries(files, workspaceRoot.fsPath);
    if (moduleBoundaries.length > 0) {
      content += '## Module Boundaries\n\n';
      content += '_Logical boundaries and architectural layers in the codebase._\n\n';
      
      for (const module of moduleBoundaries) {
        content += `### ${module.name}\n\n`;
        content += `**Path:** \`${module.path}\`\n`;
        content += `**Files:** ${module.fileCount}\n`;
        
        if (module.submodules.length > 0) {
          content += `**Submodules:** ${module.submodules.join(', ')}\n`;
        }
        
        if (module.purpose) {
          content += `**Purpose:** ${module.purpose}\n`;
        }
        
        content += '\n';
      }
    }

    // Configuration and build files
    const configFiles = detectConfigFiles(files, workspaceRoot.fsPath);
    if (configFiles.length > 0) {
      content += '## Configuration Files\n\n';
      content += '_Build, test, and deployment configuration._\n\n';
      
      for (const config of configFiles) {
        content += `- \`${config.path}\` — ${config.type}\n`;
      }
      content += '\n';
    }

    // Test organization
    const testInfo = analyzeTestOrganization(files, workspaceRoot.fsPath);
    if (testInfo.testFiles.length > 0) {
      content += '## Test Organization\n\n';
      content += `**Test files:** ${testInfo.testFiles.length}\n`;
      content += `**Test directories:** ${testInfo.testDirs.join(', ') || 'none'}\n`;
      
      if (testInfo.testPatterns.length > 0) {
        content += `**Patterns:** ${testInfo.testPatterns.join(', ')}\n`;
      }
      
      content += '\n';
    }

    // File size distribution
    const sizeInfo = await analyzeFileSizes(files);
    content += '## File Size Distribution\n\n';
    content += `**Average file size:** ${sizeInfo.average} lines\n`;
    content += `**Largest files:** ${sizeInfo.largest.slice(0, 5).map(f => {
      const rel = makeRelativePath(f.path, workspaceRoot.fsPath);
      return `\`${rel}\` (${f.lines}L)`;
    }).join(', ')}\n\n`;

    // Naming conventions
    const namingInfo = analyzeNamingConventions(files, workspaceRoot.fsPath);
    content += '## Naming Conventions\n\n';
    
    if (namingInfo.caseStyles.size > 0) {
      content += '**File naming:**\n';
      for (const [style, count] of namingInfo.caseStyles.entries()) {
        content += `- ${style}: ${count} files\n`;
      }
      content += '\n';
    }

    // Guidelines for AI agents
    content += '## Guidelines for AI Agents\n\n';
    content += '- **Entry points** are the starting files for understanding program flow\n';
    content += '- **Module boundaries** define logical separation — respect them when suggesting changes\n';
    content += '- **Directory purposes** guide where new code should be placed\n';
    content += '- **Configuration files** control build and runtime behavior — handle with care\n';
    content += '- **Test organization** shows where to add new tests\n';
    content += '- **Naming conventions** should be preserved for consistency\n';
  }

  content += `\n_Last updated: ${new Date().toISOString()}_\n`;

  const archFile = vscode.Uri.joinPath(aspectCodeDir, 'architecture.md');
  await vscode.workspace.fs.writeFile(archFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated architecture.md (${files.length} files analyzed)`);
}

/**
 * Generate .aspect/symbols.md - per-file symbol index with call relationships
 * 
 * This KB file provides function/class-level detail about what's defined where and how symbols connect.
 * It helps AI agents understand the codebase structure at a finer granularity than file-level dependencies.
 * 
 * Design decisions:
 * - Focus on files that have findings or appear in dependency graph (relevant files only)
 * - List key symbols: exported functions, classes, public methods
 * - For each symbol, show what it calls and what calls it (using dependency analyzer data)
 * - Limit to ~100 most relevant symbols to keep file size manageable
 */
async function generateSymbolsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Aspect Code Symbol Index\n\n';
  content += '_Function and class-level structure with call relationships. Use this to understand what each file exports and how symbols connect._\n\n';

  const findings = state.s.findings;
  
  // Get files from findings and dependency graph
  const relevantFiles = new Set<string>();
  
  // Add files with findings
  for (const finding of findings) {
    relevantFiles.add(finding.file);
  }
  
  // Get dependency data
  const { links: allLinks } = await getDetailedDependencyData(workspaceRoot, outputChannel);
  
  // Add files involved in dependencies
  for (const link of allLinks) {
    relevantFiles.add(link.source);
    relevantFiles.add(link.target);
  }
  
  if (relevantFiles.size === 0) {
    content += '_No files with findings or dependencies found. Run validation first._\n';
  } else {
    content += `**Files indexed:** ${relevantFiles.size}\n`;
    content += `**Total dependency relationships:** ${allLinks.length}\n\n`;
    
    // Sort files by number of findings + dependency activity
    const fileScores = new Map<string, number>();
    for (const file of relevantFiles) {
      const findingCount = findings.filter(f => f.file === file).length;
      const outLinks = allLinks.filter(l => l.source === file).length;
      const inLinks = allLinks.filter(l => l.target === file).length;
      fileScores.set(file, findingCount * 10 + outLinks + inLinks);
    }
    
    const sortedFiles = Array.from(relevantFiles)
      .sort((a, b) => (fileScores.get(b) || 0) - (fileScores.get(a) || 0))
      .slice(0, 100); // Limit to top 100 files to keep manageable
    
    outputChannel.appendLine(`[KB] Indexing symbols for ${sortedFiles.length} files (out of ${relevantFiles.size} relevant)`);
    
    for (const file of sortedFiles) {
      const relPath = makeRelativePath(file, workspaceRoot.fsPath);
      
      content += `## \`${relPath}\`\n\n`;
      
      // Extract symbols from this file
      const symbols = await extractFileSymbols(file, allLinks);
      
      if (symbols.length === 0) {
        content += '_No exported symbols detected._\n\n';
        continue;
      }
      
      content += '| Symbol | Kind | Role / Notes | Calls into | Called by (examples) |\n';
      content += '|--------|------|--------------|------------|---------------------|\n';
      
      for (const symbol of symbols.slice(0, 20)) { // Limit to 20 symbols per file
        // Escape pipe characters in symbol names/descriptions
        const escapePipe = (s: string) => s.replace(/\|/g, '\\|');
        
        const symbolCell = escapePipe(`\`${symbol.name}\``);
        const kindCell = escapePipe(symbol.kind);
        const roleCell = escapePipe(symbol.role || '—');
        
        // Build "Calls into" cell
        let callsCell = '—';
        if (symbol.callsInto.length > 0) {
          const callTargets = symbol.callsInto
            .slice(0, 5)
            .map(c => `\`${escapePipe(c)}\``)
            .join(', ');
          callsCell = callTargets;
          if (symbol.callsInto.length > 5) {
            callsCell += `, _+${symbol.callsInto.length - 5} more_`;
          }
        }
        
        // Build "Called by" cell
        let calledByCell = '—';
        if (symbol.calledBy.length > 0) {
          const callers = symbol.calledBy
            .slice(0, 3)
            .map(c => `\`${escapePipe(c)}\``)
            .join(', ');
          calledByCell = callers;
          if (symbol.calledBy.length > 3) {
            calledByCell += `, _+${symbol.calledBy.length - 3} more_`;
          }
        }
        
        content += `| ${symbolCell} | ${kindCell} | ${roleCell} | ${callsCell} | ${calledByCell} |\n`;
      }
      
      if (symbols.length > 20) {
        content += `\n_...and ${symbols.length - 20} more symbols in this file._\n`;
      }
      
      content += '\n';
    }
    
    // Add guidelines for AI agents
    content += '## How to Use This Index\n\n';
    content += '**Finding symbol definitions:**\n';
    content += '- Search for the symbol name in the "Symbol" column\n';
    content += '- The "## `<file>`" heading shows which file it\'s in\n\n';
    
    content += '**Understanding call chains:**\n';
    content += '- "Calls into" shows what this symbol depends on\n';
    content += '- "Called by" shows what depends on this symbol\n';
    content += '- Follow the chain to understand data/control flow\n\n';
    
    content += '**Refactoring safely:**\n';
    content += '- Before changing a symbol, check "Called by" to see impact\n';
    content += '- If many callers exist, the change is high-risk\n';
    content += '- Consider deprecation path for widely-used symbols\n\n';
    
    content += '**Adding new code:**\n';
    content += '- Check what symbols are already in target file\n';
    content += '- Follow existing naming patterns and organization\n';
    content += '- Avoid creating new symbols that duplicate existing ones\n';
  }
  
  content += `\n_Last updated: ${new Date().toISOString()}_\n`;
  
  const symbolsFile = vscode.Uri.joinPath(aspectCodeDir, 'symbols.md');
  await vscode.workspace.fs.writeFile(symbolsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated symbols.md (${relevantFiles.size} files indexed)`);
}

/**
 * Extract symbols from a file using import/call data from dependency analyzer
 * Returns list of {name, kind, role, callsInto, calledBy}
 */
async function extractFileSymbols(
  filePath: string,
  allLinks: DependencyLink[]
): Promise<Array<{
  name: string;
  kind: string;
  role?: string;
  callsInto: string[];
  calledBy: string[];
}>> {
  const symbols: Array<{
    name: string;
    kind: string;
    role?: string;
    callsInto: string[];
    calledBy: string[];
  }> = [];
  
  try {
    // Read file content
    const uri = vscode.Uri.file(filePath);
    const fileContent = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(fileContent).toString('utf-8');
    const lines = text.split('\n');
    
    const extension = path.extname(filePath).toLowerCase();
    
    // Extract symbols based on language
    if (extension === '.py') {
      symbols.push(...extractPythonSymbols(text, lines, filePath, allLinks));
    } else if (['.ts', '.tsx', '.js', '.jsx'].includes(extension)) {
      symbols.push(...extractTypeScriptSymbols(text, lines, filePath, allLinks));
    } else if (extension === '.java') {
      symbols.push(...extractJavaSymbols(text, lines, filePath, allLinks));
    }
    
  } catch (error) {
    // File might not be readable, skip it
  }
  
  return symbols;
}

/**
 * Extract Python symbols (functions, classes, methods)
 */
function extractPythonSymbols(
  text: string,
  lines: string[],
  filePath: string,
  allLinks: DependencyLink[]
): Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> {
  const symbols: Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> = [];
  
  // Match: def function_name( or class ClassName:
  const functionPattern = /^def\s+(\w+)\s*\(/;
  const classPattern = /^class\s+(\w+)(\(.*?\))?:/;
  const methodPattern = /^\s+def\s+(\w+)\s*\(/;
  
  let currentClass: string | null = null;
  
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    
    // Class definition
    const classMatch = line.match(classPattern);
    if (classMatch) {
      currentClass = classMatch[1];
      
      // Determine role
      let role: string | undefined;
      if (classMatch[1].includes('Test')) {
        role = 'Test class';
      } else if (classMatch[1].includes('Service')) {
        role = 'Service layer';
      } else if (classMatch[1].includes('Controller')) {
        role = 'Controller';
      } else if (classMatch[1].includes('Model')) {
        role = 'Data model';
      }
      
      symbols.push({
        name: classMatch[1],
        kind: 'class',
        role,
        callsInto: getSymbolDependencies(classMatch[1], filePath, allLinks),
        calledBy: getSymbolCallers(classMatch[1], filePath, allLinks)
      });
      continue;
    }
    
    // Method definition (indented def)
    const methodMatch = line.match(methodPattern);
    if (methodMatch && currentClass) {
      const methodName = methodMatch[1];
      
      // Skip private methods (starting with _) unless they're special methods
      if (methodName.startsWith('_') && !methodName.startsWith('__')) {
        continue;
      }
      
      symbols.push({
        name: `${currentClass}.${methodName}`,
        kind: 'method',
        role: inferMethodRole(methodName),
        callsInto: getSymbolDependencies(methodName, filePath, allLinks),
        calledBy: getSymbolCallers(methodName, filePath, allLinks)
      });
      continue;
    }
    
    // Function definition (top-level, not indented)
    const functionMatch = line.match(functionPattern);
    if (functionMatch) {
      const funcName = functionMatch[1];
      
      // Skip private functions (starting with _)
      if (funcName.startsWith('_')) {
        continue;
      }
      
      // Reset current class since we're at top level
      currentClass = null;
      
      symbols.push({
        name: funcName,
        kind: 'function',
        role: inferFunctionRole(funcName),
        callsInto: getSymbolDependencies(funcName, filePath, allLinks),
        calledBy: getSymbolCallers(funcName, filePath, allLinks)
      });
    }
  }
  
  return symbols;
}

/**
 * Extract TypeScript/JavaScript symbols (functions, classes, exported items)
 */
function extractTypeScriptSymbols(
  text: string,
  lines: string[],
  filePath: string,
  allLinks: DependencyLink[]
): Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> {
  const symbols: Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> = [];
  
  // Match: export function name, export class Name, export const name =
  const exportFunctionPattern = /export\s+(async\s+)?function\s+(\w+)/;
  const exportClassPattern = /export\s+(abstract\s+)?class\s+(\w+)/;
  const exportConstPattern = /export\s+const\s+(\w+)\s*[:=]/;
  const exportInterfacePattern = /export\s+interface\s+(\w+)/;
  const exportTypePattern = /export\s+type\s+(\w+)/;
  
  for (const line of lines) {
    // Function
    const funcMatch = line.match(exportFunctionPattern);
    if (funcMatch) {
      symbols.push({
        name: funcMatch[2],
        kind: funcMatch[1] ? 'async function' : 'function',
        role: inferFunctionRole(funcMatch[2]),
        callsInto: getSymbolDependencies(funcMatch[2], filePath, allLinks),
        calledBy: getSymbolCallers(funcMatch[2], filePath, allLinks)
      });
      continue;
    }
    
    // Class
    const classMatch = line.match(exportClassPattern);
    if (classMatch) {
      symbols.push({
        name: classMatch[2],
        kind: classMatch[1] ? 'abstract class' : 'class',
        role: inferClassRole(classMatch[2]),
        callsInto: getSymbolDependencies(classMatch[2], filePath, allLinks),
        calledBy: getSymbolCallers(classMatch[2], filePath, allLinks)
      });
      continue;
    }
    
    // Const (could be function, object, etc.)
    const constMatch = line.match(exportConstPattern);
    if (constMatch) {
      let kind = 'const';
      if (line.includes('=>') || line.includes('function')) {
        kind = 'const function';
      }
      
      symbols.push({
        name: constMatch[1],
        kind,
        callsInto: getSymbolDependencies(constMatch[1], filePath, allLinks),
        calledBy: getSymbolCallers(constMatch[1], filePath, allLinks)
      });
      continue;
    }
    
    // Interface
    const interfaceMatch = line.match(exportInterfacePattern);
    if (interfaceMatch) {
      symbols.push({
        name: interfaceMatch[1],
        kind: 'interface',
        callsInto: [],
        calledBy: []
      });
      continue;
    }
    
    // Type
    const typeMatch = line.match(exportTypePattern);
    if (typeMatch) {
      symbols.push({
        name: typeMatch[1],
        kind: 'type',
        callsInto: [],
        calledBy: []
      });
    }
  }
  
  return symbols;
}

/**
 * Extract Java symbols (public classes, methods)
 */
function extractJavaSymbols(
  text: string,
  lines: string[],
  filePath: string,
  allLinks: DependencyLink[]
): Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> {
  const symbols: Array<{ name: string; kind: string; role?: string; callsInto: string[]; calledBy: string[] }> = [];
  
  const publicClassPattern = /public\s+(abstract\s+)?(class|interface)\s+(\w+)/;
  const publicMethodPattern = /public\s+(\w+)\s+(\w+)\s*\(/;
  
  for (const line of lines) {
    // Public class/interface
    const classMatch = line.match(publicClassPattern);
    if (classMatch) {
      symbols.push({
        name: classMatch[3],
        kind: classMatch[2],
        callsInto: getSymbolDependencies(classMatch[3], filePath, allLinks),
        calledBy: getSymbolCallers(classMatch[3], filePath, allLinks)
      });
      continue;
    }
    
    // Public method
    const methodMatch = line.match(publicMethodPattern);
    if (methodMatch) {
      symbols.push({
        name: methodMatch[2],
        kind: 'method',
        callsInto: getSymbolDependencies(methodMatch[2], filePath, allLinks),
        calledBy: getSymbolCallers(methodMatch[2], filePath, allLinks)
      });
    }
  }
  
  return symbols;
}

/**
 * Get symbols that this symbol calls into (dependencies)
 * Uses the symbols field from DependencyLink data
 */
function getSymbolDependencies(symbolName: string, filePath: string, allLinks: DependencyLink[]): string[] {
  const deps = new Set<string>();
  
  // Find links where this file is the source
  const outgoingLinks = allLinks.filter(l => l.source === filePath);
  
  for (const link of outgoingLinks) {
    // Add all symbols imported/called from this link
    for (const symbol of link.symbols) {
      deps.add(symbol);
    }
  }
  
  return Array.from(deps);
}

/**
 * Get files/symbols that call this symbol (reverse dependencies)
 */
function getSymbolCallers(symbolName: string, filePath: string, allLinks: DependencyLink[]): string[] {
  const callers = new Set<string>();
  
  // Find links where this file is the target and the symbol is listed
  const incomingLinks = allLinks.filter(l => 
    l.target === filePath && l.symbols.includes(symbolName)
  );
  
  for (const link of incomingLinks) {
    const sourceName = path.basename(link.source, path.extname(link.source));
    callers.add(sourceName);
  }
  
  return Array.from(callers).slice(0, 10); // Limit to 10 callers
}

/**
 * Infer function role from name
 */
function inferFunctionRole(funcName: string): string | undefined {
  const lower = funcName.toLowerCase();
  
  if (lower.startsWith('test_') || lower.startsWith('test')) {
    return 'Test function';
  } else if (lower.startsWith('get_') || lower.startsWith('get')) {
    return 'Getter';
  } else if (lower.startsWith('set_') || lower.startsWith('set')) {
    return 'Setter';
  } else if (lower.startsWith('create_') || lower.startsWith('create')) {
    return 'Creator';
  } else if (lower.startsWith('delete_') || lower.startsWith('delete')) {
    return 'Deletion';
  } else if (lower.startsWith('update_') || lower.startsWith('update')) {
    return 'Update';
  } else if (lower.startsWith('validate_') || lower.startsWith('validate')) {
    return 'Validator';
  } else if (lower.startsWith('process_') || lower.startsWith('process')) {
    return 'Processor';
  } else if (lower.startsWith('handle_') || lower.startsWith('handle')) {
    return 'Handler';
  } else if (lower.includes('main')) {
    return 'Entry point';
  }
  
  return undefined;
}

/**
 * Infer method role from name
 */
function inferMethodRole(methodName: string): string | undefined {
  if (methodName === '__init__') {
    return 'Constructor';
  } else if (methodName === '__str__' || methodName === '__repr__') {
    return 'String representation';
  } else if (methodName.startsWith('__') && methodName.endsWith('__')) {
    return 'Special method';
  }
  
  return inferFunctionRole(methodName);
}

/**
 * Infer class role from name
 */
function inferClassRole(className: string): string | undefined {
  const lower = className.toLowerCase();
  
  if (lower.includes('test')) {
    return 'Test suite';
  } else if (lower.includes('service')) {
    return 'Service';
  } else if (lower.includes('controller')) {
    return 'Controller';
  } else if (lower.includes('model')) {
    return 'Data model';
  } else if (lower.includes('view')) {
    return 'View';
  } else if (lower.includes('repository')) {
    return 'Data repository';
  } else if (lower.includes('provider')) {
    return 'Provider';
  } else if (lower.includes('manager')) {
    return 'Manager';
  } else if (lower.includes('handler')) {
    return 'Handler';
  }
  
  return undefined;
}

/**
 * Generate .aspect/flows.md - call/data flows around high-impact findings
 * 
 * This KB file shows end-to-end execution paths through critical code.
 * It helps AI agents understand the consequences of changes by showing how requests/data move.
 * 
 * Design decisions:
 * - Focus on top 10-20 findings by severity and impact
 * - Walk the call graph 2 levels up and 2 levels down from each finding
 * - Present as linear call chains (top-down) with arrows
 * - Include notes about what enters/exits the flow (user input, DB, etc.)
 * - Keep each flow to ~10 lines max for readability
 */
async function generateFlowsFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Aspect Code High-Impact Flows\n\n';
  content += '_These show how requests or data move through key functions. Use them to understand consequences of changes._\n\n';

  const findings = state.s.findings;
  
  if (findings.length === 0) {
    content += '_No findings available. Run validation first._\n';
  } else {
    // Score findings by impact (severity + count)
    // Design decision: Use severity as primary factor, with file frequency as tiebreaker
    const scoredFindings = findings.map(f => {
      let severityScore = 0;
      if (f.severity === 'error') {
        severityScore = 100;
      } else if (f.severity === 'warn') {
        severityScore = 50;
      } else {
        severityScore = 10;
      }
      
      // Count findings in same file (indicates problematic area)
      const sameFileCount = findings.filter(other => other.file === f.file).length;
      
      return {
        finding: f,
        score: severityScore + sameFileCount
      };
    });
    
    // Sort by score and take top 20
    // Design decision: 20 flows is enough for comprehensive coverage without overwhelming
    const topFindings = scoredFindings
      .sort((a, b) => b.score - a.score)
      .slice(0, 20)
      .map(sf => sf.finding);
    
    outputChannel.appendLine(`[KB] Generating flows for ${topFindings.length} high-impact findings (out of ${findings.length} total)`);
    
    content += `**Flows generated:** ${topFindings.length} (from ${findings.length} total findings)\n`;
    content += `**Selection criteria:** Top severity findings with consideration for file frequency\n\n`;
    
    // Get dependency data for call graph walking
    const { links: allLinks } = await getDetailedDependencyData(workspaceRoot, outputChannel);
    
    let flowIndex = 1;
    for (const finding of topFindings) {
      const flow = await buildFlowForFinding(finding, allLinks, workspaceRoot, outputChannel);
      
      if (flow) {
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const location = finding.span?.start ? `:${finding.span.start.line}` : '';
        
        content += `## Flow ${flowIndex} – ${flow.title}\n\n`;
        content += `**Related finding:** \`${finding.code}\` in \`${relPath}${location}\`\n\n`;
        content += `**Severity:** ${finding.severity}\n\n`;
        content += `**Call chain (top-down):**\n\n`;
        content += '```\n';
        content += flow.chain.join('\n');
        content += '\n```\n\n';
        
        if (flow.notes.length > 0) {
          content += '**Notes:**\n\n';
          for (const note of flow.notes) {
            content += `- ${note}\n`;
          }
          content += '\n';
        }
        
        content += '---\n\n';
        flowIndex++;
      }
    }
    
    // Add guidelines for AI agents
    content += '## How to Use These Flows\n\n';
    content += '**Understanding impact:**\n';
    content += '- Each flow shows the call path to and from a critical issue\n';
    content += '- Changes anywhere in the chain can affect the entire flow\n';
    content += '- Pay special attention to entry points (where user data enters)\n\n';
    
    content += '**Planning fixes:**\n';
    content += '- Review the full flow before fixing an issue in the middle\n';
    content += '- Check if upstream callers need changes too\n';
    content += '- Verify downstream code can handle your changes\n\n';
    
    content += '**Testing strategy:**\n';
    content += '- Test entry points (top of chain) with realistic inputs\n';
    content += '- Verify exit points (bottom of chain) produce correct outputs\n';
    content += '- Check error handling at each step in the flow\n\n';
    
    content += '**Refactoring:**\n';
    content += '- Breaking a flow into smaller functions can improve testability\n';
    content += '- Keep data transformations explicit at each step\n';
    content += '- Document assumptions about data shape/state\n';
  }
  
  content += `\n_Last updated: ${new Date().toISOString()}_\n`;
  
  const flowsFile = vscode.Uri.joinPath(aspectCodeDir, 'flows.md');
  await vscode.workspace.fs.writeFile(flowsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated flows.md (${topFindings.length} flows)`);
}

/**
 * Generate .aspect/findings_top.md - top 20-30 findings with stable IDs in canonical LLM-friendly format
 * Format: High-impact findings (critical/high severity), Architectural findings (Tier 2), Medium-impact findings
 * Each finding has a stable ID (F-001, F-002, etc.) for cross-referencing
 */
async function generateFindingsTopFile(
  aspectCodeDir: vscode.Uri,
  state: AspectCodeState,
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  let content = '# Aspect Code Top Findings\n\n';
  content += '_Top priority issues with stable IDs for cross-referencing. Use these IDs when discussing or fixing findings._\n\n';

  // Tier 2 architectural rule IDs
  const tier2RuleIds = new Set([
    'analysis.change_impact',
    'architecture.dependency_cycle_impact', 
    'architecture.critical_dependency',
    'deadcode.unused_public'
  ]);

  const findings = state.s.findings;

  if (findings.length === 0) {
    content += '_No findings available. Run validation first._\n\n';
  } else {
    // Separate findings by type
    const tier2Findings = findings.filter(f => tier2RuleIds.has(f.code));
    const highImpactFindings = findings.filter(f => 
      (f.severity === 'error' || f.severity === 'warn') && !tier2RuleIds.has(f.code)
    );
    const mediumImpactFindings = findings.filter(f => 
      (f.severity === 'info' || f.severity === 'hint') && !tier2RuleIds.has(f.code)
    );

    // Sort by severity, then by file, then by line
    const sortFindings = (a: any, b: any) => {
      const severityOrder: Record<string, number> = { error: 0, warn: 1, info: 2, hint: 3 };
      const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (severityDiff !== 0) return severityDiff;
      
      const fileDiff = a.file.localeCompare(b.file);
      if (fileDiff !== 0) return fileDiff;
      
      return (a.span?.start?.line || 0) - (b.span?.start?.line || 0);
    };

    tier2Findings.sort(sortFindings);
    highImpactFindings.sort(sortFindings);
    mediumImpactFindings.sort(sortFindings);

    // Limit counts
    const topTier2 = tier2Findings.slice(0, 15);
    const topHighImpact = highImpactFindings.slice(0, 20);
    const topMediumImpact = mediumImpactFindings.slice(0, 10);

    let findingId = 1;

    // Tier 2 Architectural findings section (NEW)
    content += '## Architectural findings (Tier 2)\n\n';
    content += '_Cross-file dependency analysis: change impact, unused exports, critical dependencies._\n\n';
    
    if (topTier2.length === 0) {
      content += '_No Tier 2 architectural findings. Tier 2 analysis requires project-wide indexing._\n\n';
    } else {
      for (const finding of topTier2) {
        const fId = `F-${String(findingId).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const location = finding.span?.start ? `:${finding.span.start.line}` : '';
        
        // Tier 2 rule descriptions
        let ruleDesc = '';
        if (finding.code === 'analysis.change_impact') {
          ruleDesc = 'High blast radius - changes here affect many dependents';
        } else if (finding.code === 'deadcode.unused_public') {
          ruleDesc = 'Unused export - potential dead code candidate';
        } else if (finding.code === 'architecture.critical_dependency') {
          ruleDesc = 'Critical dependency - many modules rely on this';
        } else if (finding.code === 'architecture.dependency_cycle_impact') {
          ruleDesc = 'Circular dependency with high impact';
        }
        
        content += `### ${fId}\n\n`;
        content += `- **Rule:** \`${finding.code}\`\n`;
        content += `- **Type:** Architectural (Tier 2)\n`;
        content += `- **Location:** \`${relPath}${location}\`\n`;
        content += `- **Summary:** ${finding.message}\n`;
        if (ruleDesc) {
          content += `- **Context:** ${ruleDesc}\n`;
        }
        content += `- **Action:** Review dependencies before changes\n`;
        
        content += '\n';
        findingId++;
      }
    }

    // High-impact findings section
    content += '## High-impact findings\n\n';
    
    if (topHighImpact.length === 0) {
      content += '_No high-impact findings._\n\n';
    } else {
      for (const finding of topHighImpact) {
        const fId = `F-${String(findingId).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const location = finding.span?.start ? `:${finding.span.start.line}` : '';
        const severityLabel = finding.severity === 'error' ? 'Critical' : 'High';
        
        content += `### ${fId}\n\n`;
        content += `- **Rule:** \`${finding.code}\`\n`;
        content += `- **Severity:** ${severityLabel}\n`;
        content += `- **Location:** \`${relPath}${location}\`\n`;
        content += `- **Summary:** ${finding.message}\n`;
        
        if (finding.fixable) {
          content += `- **Suggested fix:** Auto-fixable (use Aspect Code autofix command)\n`;
        } else {
          content += `- **Suggested fix:** Manual review required\n`;
        }
        
        content += '\n';
        findingId++;
      }
    }

    // Medium-impact findings section
    content += '## Medium-impact findings\n\n';
    
    if (topMediumImpact.length === 0) {
      content += '_No medium-impact findings._\n\n';
    } else {
      for (const finding of topMediumImpact) {
        const fId = `F-${String(findingId).padStart(3, '0')}`;
        const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
        const location = finding.span?.start ? `:${finding.span.start.line}` : '';
        
        content += `### ${fId}\n\n`;
        content += `- **Rule:** \`${finding.code}\`\n`;
        content += `- **Severity:** Medium\n`;
        content += `- **Location:** \`${relPath}${location}\`\n`;
        content += `- **Summary:** ${finding.message}\n`;
        
        if (finding.fixable) {
          content += `- **Suggested fix:** Auto-fixable (use Aspect Code autofix command)\n`;
        } else {
          content += `- **Suggested fix:** Manual review required\n`;
        }
        
        content += '\n';
        findingId++;
      }
    }
  }

  content += `\n_Last updated: ${new Date().toISOString()}_\n`;

  const findingsFile = vscode.Uri.joinPath(aspectCodeDir, 'findings_top.md');
  await vscode.workspace.fs.writeFile(findingsFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine(`[KB] Generated findings_top.md (${findings.length} findings)`);
}

/**
 * Build a call flow for a specific finding
 * Returns {title, chain, notes} or null if flow can't be constructed
 */
async function buildFlowForFinding(
  finding: any,
  allLinks: DependencyLink[],
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<{ title: string; chain: string[]; notes: string[] } | null> {
  try {
    const chain: string[] = [];
    const notes: string[] = [];
    
    // Extract function name from finding if available
    const functionName = await extractFunctionAtLocation(finding.file, finding.span?.start?.line);
    
    if (!functionName) {
      // Can't build flow without knowing the function
      return null;
    }
    
    // Build title from rule and function
    const title = `${simplifyRuleName(finding.code)} in ${functionName}`;
    
    // Walk call graph upward (who calls this function?)
    const upstreamCalls = findUpstreamCallers(finding.file, functionName, allLinks, 2);
    
    // Add upstream calls to chain (reverse order so entry point is first)
    for (let i = upstreamCalls.length - 1; i >= 0; i--) {
      chain.push(upstreamCalls[i]);
    }
    
    // Add the current function (where the finding is)
    const relPath = makeRelativePath(finding.file, workspaceRoot.fsPath);
    const location = finding.span?.start ? `:${finding.span.start.line}` : '';
    chain.push(`${relPath}:${functionName}${location}  ← ⚠️ Finding here`);
    
    // Walk call graph downward (what does this function call?)
    const downstreamCalls = findDownstreamCallees(finding.file, functionName, allLinks, 2);
    
    // Add downstream calls to chain
    for (const call of downstreamCalls) {
      chain.push(call);
    }
    
    // Format chain with arrows
    const formattedChain: string[] = [];
    for (let i = 0; i < chain.length; i++) {
      if (i === 0) {
        formattedChain.push(chain[i]);
      } else {
        formattedChain.push(`  → ${chain[i]}`);
      }
    }
    
    // Add contextual notes based on finding type
    addContextualNotes(finding, functionName, notes);
    
    return {
      title,
      chain: formattedChain,
      notes
    };
    
  } catch (error) {
    outputChannel.appendLine(`[KB] Failed to build flow for finding: ${error}`);
    return null;
  }
}

/**
 * Extract function/method name at a specific line in a file
 */
async function extractFunctionAtLocation(filePath: string, line?: number): Promise<string | null> {
  if (!line) return null;
  
  try {
    const uri = vscode.Uri.file(filePath);
    const content = await vscode.workspace.fs.readFile(uri);
    const text = Buffer.from(content).toString('utf-8');
    const lines = text.split('\n');
    
    // Look backward from the line to find the nearest function/method definition
    for (let i = line - 1; i >= 0 && i >= line - 50; i--) {
      const currentLine = lines[i];
      
      // Python: def function_name(
      const pyMatch = currentLine.match(/def\s+(\w+)\s*\(/);
      if (pyMatch) {
        return pyMatch[1];
      }
      
      // TypeScript/JavaScript: function name( or name = function( or name: function(
      const tsMatch = currentLine.match(/(?:function\s+(\w+)|(\w+)\s*[:=]\s*(?:async\s+)?function)/);
      if (tsMatch) {
        return tsMatch[1] || tsMatch[2];
      }
      
      // Java: public/private type methodName(
      const javaMatch = currentLine.match(/(?:public|private|protected)\s+\w+\s+(\w+)\s*\(/);
      if (javaMatch) {
        return javaMatch[1];
      }
    }
    
    // Fallback: use the file basename
    return path.basename(filePath, path.extname(filePath));
    
  } catch (error) {
    return null;
  }
}

/**
 * Find functions that call the given function (walk up the call graph)
 */
function findUpstreamCallers(
  filePath: string,
  functionName: string,
  allLinks: DependencyLink[],
  maxDepth: number
): string[] {
  const callers: string[] = [];
  
  // Find links where this file is the target
  const incomingLinks = allLinks.filter(l => l.target === filePath);
  
  for (const link of incomingLinks.slice(0, 3)) { // Limit to 3 callers to keep flow readable
    const sourceFile = path.basename(link.source, path.extname(link.source));
    
    if (link.symbols.length > 0) {
      // We have symbol information
      callers.push(`${sourceFile}:${link.symbols[0]}()`);
    } else {
      // Just file-level dependency
      callers.push(`${sourceFile}:<unknown>()`);
    }
  }
  
  return callers;
}

/**
 * Find functions that this function calls (walk down the call graph)
 */
function findDownstreamCallees(
  filePath: string,
  functionName: string,
  allLinks: DependencyLink[],
  maxDepth: number
): string[] {
  const callees: string[] = [];
  
  // Find links where this file is the source
  const outgoingLinks = allLinks.filter(l => l.source === filePath);
  
  for (const link of outgoingLinks.slice(0, 3)) { // Limit to 3 callees to keep flow readable
    const targetFile = path.basename(link.target, path.extname(link.target));
    
    if (link.symbols.length > 0) {
      // We have symbol information
      callees.push(`${targetFile}:${link.symbols[0]}()`);
    } else {
      // Just file-level dependency
      callees.push(`${targetFile}:<unknown>()`);
    }
  }
  
  return callees;
}

/**
 * Simplify rule name for display
 */
function simplifyRuleName(ruleCode: string): string {
  // Remove namespace prefixes like "security." or "performance."
  const parts = ruleCode.split('.');
  return parts[parts.length - 1].replace(/-/g, ' ');
}

/**
 * Add contextual notes based on finding type
 */
function addContextualNotes(finding: any, functionName: string, notes: string[]): void {
  const ruleCode = finding.code.toLowerCase();
  
  // Security-related notes
  if (ruleCode.includes('security') || ruleCode.includes('sql') || ruleCode.includes('injection')) {
    notes.push('🔒 Security issue: Verify user input is sanitized before entering this flow');
  }
  
  if (ruleCode.includes('auth')) {
    notes.push('🔑 Authentication required: Check that all entry points validate credentials');
  }
  
  // Performance-related notes
  if (ruleCode.includes('performance') || ruleCode.includes('n+1') || ruleCode.includes('loop')) {
    notes.push('⚡ Performance issue: Consider caching or batch operations to reduce overhead');
  }
  
  // Database-related notes
  if (ruleCode.includes('db') || ruleCode.includes('query') || ruleCode.includes('sql')) {
    notes.push('💾 Database operation: Ensure transactions are handled properly');
  }
  
  // Memory-related notes
  if (ruleCode.includes('memory') || ruleCode.includes('leak')) {
    notes.push('🧠 Memory management: Verify resources are properly released');
  }
  
  // Type-related notes
  if (ruleCode.includes('type') || ruleCode.includes('any')) {
    notes.push('📝 Type safety: Add proper type annotations to catch errors at compile time');
  }
  
  // Generic note about the function
  if (functionName.toLowerCase().includes('handle') || functionName.toLowerCase().includes('process')) {
    notes.push(`Function "${functionName}" appears to be a handler/processor - main logic is here`);
  }
}

/**
 * Analyze directory structure and infer purposes
 */
function analyzeDirStructure(
  files: string[],
  workspaceRoot: string
): Map<string, { files: string[]; fileTypes: Map<string, number>; purpose?: string }> {
  const structure = new Map<string, { files: string[]; fileTypes: Map<string, number>; purpose?: string }>();

  for (const file of files) {
    const dir = path.dirname(file);
    
    if (!structure.has(dir)) {
      structure.set(dir, { files: [], fileTypes: new Map(), purpose: undefined });
    }
    
    const info = structure.get(dir)!;
    info.files.push(file);
    
    const ext = path.extname(file);
    info.fileTypes.set(ext, (info.fileTypes.get(ext) || 0) + 1);
  }

  // Infer purposes based on directory names and contents
  for (const [dir, info] of structure.entries()) {
    const dirName = path.basename(dir).toLowerCase();
    
    if (dirName.includes('test') || dirName.includes('spec')) {
      info.purpose = 'Testing';
    } else if (dirName.includes('doc') || dirName === 'docs') {
      info.purpose = 'Documentation';
    } else if (dirName === 'src' || dirName === 'source') {
      info.purpose = 'Source code';
    } else if (dirName === 'lib' || dirName === 'libs') {
      info.purpose = 'Libraries';
    } else if (dirName === 'util' || dirName === 'utils' || dirName === 'helpers') {
      info.purpose = 'Utilities';
    } else if (dirName === 'config' || dirName === 'configuration') {
      info.purpose = 'Configuration';
    } else if (dirName === 'api' || dirName === 'server') {
      info.purpose = 'API/Server';
    } else if (dirName === 'client' || dirName === 'frontend') {
      info.purpose = 'Client/Frontend';
    } else if (dirName === 'model' || dirName === 'models') {
      info.purpose = 'Data models';
    } else if (dirName === 'view' || dirName === 'views') {
      info.purpose = 'Views/UI';
    } else if (dirName === 'controller' || dirName === 'controllers') {
      info.purpose = 'Controllers';
    } else if (dirName === 'service' || dirName === 'services') {
      info.purpose = 'Services';
    } else if (dirName === 'component' || dirName === 'components') {
      info.purpose = 'Components';
    }
  }

  return structure;
}

/**
 * Detect programming languages in use
 */
function detectLanguages(files: string[]): string[] {
  const langMap: Map<string, string> = new Map([
    ['.py', 'Python'],
    ['.ts', 'TypeScript'],
    ['.tsx', 'TypeScript/React'],
    ['.js', 'JavaScript'],
    ['.jsx', 'JavaScript/React'],
    ['.java', 'Java'],
    ['.cs', 'C#'],
    ['.cpp', 'C++'],
    ['.c', 'C'],
    ['.go', 'Go'],
    ['.rs', 'Rust'],
    ['.rb', 'Ruby']
  ]);

  const languages = new Set<string>();
  for (const file of files) {
    const ext = path.extname(file).toLowerCase();
    const lang = langMap.get(ext);
    if (lang) {
      languages.add(lang);
    }
  }

  return Array.from(languages).sort();
}

/**
 * Calculate maximum directory depth
 */
function calculateMaxDepth(files: string[], workspaceRoot: string): number {
  let maxDepth = 0;
  
  for (const file of files) {
    const relPath = makeRelativePath(file, workspaceRoot);
    const depth = relPath.split(/[/\\]/).length;
    maxDepth = Math.max(maxDepth, depth);
  }
  
  return maxDepth;
}

/**
 * Detect entry point files
 */
function detectEntryPoints(files: string[], workspaceRoot: string): Array<{ path: string; reason: string }> {
  const entryPoints: Array<{ path: string; reason: string }> = [];
  const commonEntryNames = [
    'main', 'index', 'app', '__main__', 'server', 'start', 'init',
    'bootstrap', 'launcher', 'program', 'run'
  ];

  for (const file of files) {
    const basename = path.basename(file, path.extname(file)).toLowerCase();
    const filename = path.basename(file);
    const relPath = makeRelativePath(file, workspaceRoot);

    if (commonEntryNames.includes(basename)) {
      entryPoints.push({
        path: relPath,
        reason: `Common entry point name "${basename}"`
      });
    } else if (filename === 'package.json') {
      entryPoints.push({
        path: relPath,
        reason: 'NPM package configuration (check "main" field)'
      });
    } else if (filename === 'setup.py') {
      entryPoints.push({
        path: relPath,
        reason: 'Python package setup'
      });
    } else if (filename.endsWith('.csproj') || filename.endsWith('.sln')) {
      entryPoints.push({
        path: relPath,
        reason: 'C# project/solution file'
      });
    }
  }

  return entryPoints;
}

/**
 * Check if file is significant (not auto-generated, not trivial)
 */
function isSignificantFile(file: string): boolean {
  const basename = path.basename(file).toLowerCase();
  const insignificantPatterns = [
    '__pycache__', '.pyc', '.pyo',
    'node_modules', '.min.js', '.bundle.js',
    '.generated.', 'auto_generated'
  ];

  for (const pattern of insignificantPatterns) {
    if (basename.includes(pattern)) {
      return false;
    }
  }

  return true;
}

/**
 * Infer file purpose from name
 */
function inferFilePurpose(filepath: string, filename: string): string | undefined {
  const lower = filename.toLowerCase();
  
  if (lower.includes('test') || lower.includes('spec')) {
    return 'Tests';
  } else if (lower.includes('config')) {
    return 'Configuration';
  } else if (lower === 'readme.md' || lower === 'readme.txt') {
    return 'Documentation';
  } else if (lower.includes('util') || lower.includes('helper')) {
    return 'Utilities';
  } else if (lower.includes('type') || lower.includes('interface')) {
    return 'Type definitions';
  } else if (lower.includes('const') || lower === 'constants.ts' || lower === 'constants.py') {
    return 'Constants';
  } else if (lower.includes('model')) {
    return 'Data model';
  } else if (lower.includes('service')) {
    return 'Service layer';
  } else if (lower.includes('controller')) {
    return 'Controller';
  } else if (lower.includes('component')) {
    return 'UI Component';
  }
  
  return undefined;
}

/**
 * Detect module boundaries (major subsystems)
 */
function detectModuleBoundaries(files: string[], workspaceRoot: string): Array<{
  name: string;
  path: string;
  fileCount: number;
  submodules: string[];
  purpose?: string;
}> {
  const modules: Array<{
    name: string;
    path: string;
    fileCount: number;
    submodules: string[];
    purpose?: string;
  }> = [];

  // Group by top-level directories
  const topLevelDirs = new Map<string, string[]>();
  
  for (const file of files) {
    const relPath = makeRelativePath(file, workspaceRoot);
    const parts = relPath.split(/[/\\]/);
    
    if (parts.length > 1) {
      const topDir = parts[0];
      if (!topLevelDirs.has(topDir)) {
        topLevelDirs.set(topDir, []);
      }
      topLevelDirs.get(topDir)!.push(file);
    }
  }

  // Analyze each top-level directory as a potential module
  for (const [dirName, dirFiles] of topLevelDirs.entries()) {
    if (dirFiles.length < 2) continue; // Skip trivial directories

    // Detect submodules
    const subdirs = new Set<string>();
    for (const file of dirFiles) {
      const relPath = makeRelativePath(file, workspaceRoot);
      const parts = relPath.split(/[/\\]/);
      if (parts.length > 2) {
        subdirs.add(parts[1]);
      }
    }

    modules.push({
      name: dirName,
      path: dirName,
      fileCount: dirFiles.length,
      submodules: Array.from(subdirs).slice(0, 10),
      purpose: inferModulePurpose(dirName)
    });
  }

  return modules.sort((a, b) => b.fileCount - a.fileCount);
}

/**
 * Infer module purpose from name
 */
function inferModulePurpose(moduleName: string): string | undefined {
  const lower = moduleName.toLowerCase();
  
  if (lower === 'src' || lower === 'source') {
    return 'Main source code';
  } else if (lower === 'server' || lower === 'backend') {
    return 'Backend/Server logic';
  } else if (lower === 'client' || lower === 'frontend') {
    return 'Frontend/Client code';
  } else if (lower.includes('test')) {
    return 'Test suite';
  } else if (lower === 'docs' || lower === 'documentation') {
    return 'Project documentation';
  } else if (lower === 'extension' || lower === 'extensions') {
    return 'Extensions/Plugins';
  } else if (lower === 'playground') {
    return 'Experimental/Demo code';
  }
  
  return undefined;
}

/**
 * Detect configuration files
 */
function detectConfigFiles(files: string[], workspaceRoot: string): Array<{ path: string; type: string }> {
  const configs: Array<{ path: string; type: string }> = [];
  const configPatterns: Map<string, string> = new Map([
    ['package.json', 'NPM configuration'],
    ['tsconfig.json', 'TypeScript configuration'],
    ['webpack.config.js', 'Webpack build config'],
    ['babel.config.js', 'Babel transpiler config'],
    ['jest.config.js', 'Jest test config'],
    ['.eslintrc', 'ESLint linter config'],
    ['pyproject.toml', 'Python project config'],
    ['setup.py', 'Python setup script'],
    ['requirements.txt', 'Python dependencies'],
    ['Dockerfile', 'Docker container config'],
    ['docker-compose.yml', 'Docker Compose config'],
    ['.gitignore', 'Git ignore rules'],
    ['Makefile', 'Build automation'],
    ['pom.xml', 'Maven build config'],
    ['build.gradle', 'Gradle build config']
  ]);

  for (const file of files) {
    const filename = path.basename(file);
    const relPath = makeRelativePath(file, workspaceRoot);
    
    for (const [pattern, type] of configPatterns.entries()) {
      if (filename === pattern || filename.endsWith(pattern)) {
        configs.push({ path: relPath, type });
        break;
      }
    }
  }

  return configs;
}

/**
 * Analyze test organization
 */
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
      
      if (dir.includes('test')) {
        testDirs.add(dir);
      }

      if (basename.startsWith('test_')) {
        testPatterns.add('test_*.py');
      } else if (basename.endsWith('.test.ts')) {
        testPatterns.add('*.test.ts');
      } else if (basename.endsWith('.spec.ts')) {
        testPatterns.add('*.spec.ts');
      }
    }
  }

  return {
    testFiles,
    testDirs: Array.from(testDirs),
    testPatterns: Array.from(testPatterns)
  };
}

/**
 * Analyze file sizes
 */
async function analyzeFileSizes(files: string[]): Promise<{
  average: number;
  largest: Array<{ path: string; lines: number }>;
}> {
  const fileSizes: Array<{ path: string; lines: number }> = [];
  let totalLines = 0;
  let analyzedCount = 0;

  // Sample up to 100 files for performance
  const sampled = files.slice(0, 100);
  
  for (const file of sampled) {
    try {
      const uri = vscode.Uri.file(file);
      const content = await vscode.workspace.fs.readFile(uri);
      const text = Buffer.from(content).toString('utf-8');
      const lines = text.split('\n').length;
      
      fileSizes.push({ path: file, lines });
      totalLines += lines;
      analyzedCount++;
    } catch (error) {
      // Skip files that can't be read
    }
  }

  return {
    average: analyzedCount > 0 ? Math.round(totalLines / analyzedCount) : 0,
    largest: fileSizes.sort((a, b) => b.lines - a.lines).slice(0, 10)
  };
}

/**
 * Analyze naming conventions
 */
function analyzeNamingConventions(files: string[], workspaceRoot: string): {
  caseStyles: Map<string, number>;
} {
  const caseStyles = new Map<string, number>();

  for (const file of files) {
    const basename = path.basename(file, path.extname(file));
    
    if (/^[a-z][a-z0-9]*(_[a-z0-9]+)*$/.test(basename)) {
      caseStyles.set('snake_case', (caseStyles.get('snake_case') || 0) + 1);
    } else if (/^[a-z][a-zA-Z0-9]*$/.test(basename)) {
      caseStyles.set('camelCase', (caseStyles.get('camelCase') || 0) + 1);
    } else if (/^[A-Z][a-zA-Z0-9]*$/.test(basename)) {
      caseStyles.set('PascalCase', (caseStyles.get('PascalCase') || 0) + 1);
    } else if (/^[a-z][a-z0-9]*(-[a-z0-9]+)+$/.test(basename)) {
      caseStyles.set('kebab-case', (caseStyles.get('kebab-case') || 0) + 1);
    } else {
      caseStyles.set('mixed/other', (caseStyles.get('mixed/other') || 0) + 1);
    }
  }

  return { caseStyles };
}

/**
 * Get detailed dependency data including stats and full link information
 */
async function getDetailedDependencyData(
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<{
  stats: Map<string, { inDegree: number; outDegree: number }>;
  links: DependencyLink[];
}> {
  const stats = new Map<string, { inDegree: number; outDegree: number }>();
  let links: DependencyLink[] = [];

  try {
    // Discover workspace files
    const files = await discoverWorkspaceFiles(workspaceRoot);
    
    if (files.length === 0) {
      return { stats, links };
    }

    // Run dependency analysis
    const analyzer = new DependencyAnalyzer();
    links = await analyzer.analyzeDependencies(files);

    // Calculate in-degree and out-degree for each file
    for (const file of files) {
      stats.set(file, { inDegree: 0, outDegree: 0 });
    }

    for (const link of links) {
      const sourceStats = stats.get(link.source);
      const targetStats = stats.get(link.target);
      
      if (sourceStats) {
        sourceStats.outDegree++;
      }
      if (targetStats) {
        targetStats.inDegree++;
      }
    }

    outputChannel.appendLine(`[KB] Analyzed ${links.length} dependencies across ${files.length} files`);
  } catch (error) {
    outputChannel.appendLine(`[KB] Dependency analysis failed (non-critical): ${error}`);
  }

  return { stats, links };
}

/**
 * Discover source files in workspace (simplified)
 */
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
  } catch (error) {
    // Ignore errors, return empty
  }

  return files;
}

function makeRelativePath(absPath: string, workspaceRoot: string): string {
  if (absPath.startsWith(workspaceRoot)) {
    return absPath.substring(workspaceRoot.length).replace(/^[\\\/]/, '');
  }
  return path.basename(absPath);
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

