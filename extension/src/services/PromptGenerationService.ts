/**
 * Prompt Generation Service
 * 
 * Generates high-level, project-manager-style prompts for AI coding agents
 * using codebase context, findings, and dependency information.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';
import * as fs from 'fs';

export interface Finding {
  id: string;
  code: string;
  severity: 'info' | 'warn' | 'error';
  file: string;
  message: string;
  fixable: boolean;
  span?: {
    start: { line: number; column: number };
    end: { line: number; column: number };
  };
  _raw?: any;
}

export interface PromptGenerationContext {
  findings: Finding[];
  userGoal?: string;
  includeFiles?: string[];
  maxFiles?: number;
}

export interface GeneratedPrompt {
  prompt: string;
  metadata: {
    filesIncluded: number;
    findingsIncluded: number;
    severity: { error: number; warn: number; info: number };
    timestamp: string;
  };
}

export interface ImpactAnalysis {
  finding: Finding;
  impactScore: number;
  reasons: string[];
  affectedFiles: string[];
  category: 'quick-win' | 'critical-error' | 'systematic-pattern' | 'architectural' | 'low-priority';
  effort: 'low' | 'medium' | 'high';
  risk: 'low' | 'medium' | 'high';
}

export interface FindingsSummary {
  timestamp: string;
  totalFindings: number;
  byFile: { file: string; count: number; errorCount: number }[];
  byRule: { rule: string; count: number; severity: string }[];
  impactRanked: ImpactAnalysis[];
  hubFiles: string[];
  hotspotFiles: string[];
  circularDeps: string[][];
}

const SYSTEM_PROMPT = `You are an expert project manager creating a concise, actionable task description for an AI coding agent (like Cursor or GitHub Copilot).

Given:
- A codebase summary with file paths and structure
- A list of code issues/findings
- Dependency relationships between files
- User's goal or objective (if provided)

Generate a high-level prompt (500-1000 words) that:
1. Summarizes the problem clearly
2. Lists affected files by path (NOT full contents)
3. Describes key issues by priority
4. Suggests a high-level approach
5. Defines success criteria

The agent will read the actual files themselves, so focus on WHAT needs to be fixed and WHERE, not HOW at the code level.

Format in markdown with clear sections:
- ## Objective
- ## Affected Files
- ## Key Issues
- ## Suggested Approach
- ## Success Criteria

Be concise but comprehensive. Use bullet points for clarity.`;

export class PromptGenerationService {
  private dependencyAnalyzer: DependencyAnalyzer;
  
  constructor(
    private outputChannel: vscode.OutputChannel
  ) {
    this.dependencyAnalyzer = new DependencyAnalyzer();
  }

  /**
   * Generate a custom prompt based on user's goal and current findings
   */
  async generateCustomPrompt(context: PromptGenerationContext): Promise<GeneratedPrompt> {
    this.outputChannel.appendLine('[PromptGeneration] Generating custom prompt...');
    
    try {
      // Gather context
      const contextData = await this.gatherContext(context);
      
      // Build the prompt
      const prompt = await this.buildPrompt(contextData, context.userGoal);
      
      // Calculate metadata
      const metadata = this.calculateMetadata(context.findings, contextData.files);
      
      return {
        prompt,
        metadata
      };
      
    } catch (error) {
      this.outputChannel.appendLine(`[PromptGeneration] Error: ${error}`);
      throw error;
    }
  }

  /**
   * Generate an automatic fix prompt for non-safe findings
   */
  async generateAutoFixPrompt(findings: Finding[]): Promise<GeneratedPrompt> {
    this.outputChannel.appendLine('[PromptGeneration] Generating auto-fix prompt...');
    
    try {
      // Filter to non-safe, high-priority findings
      const priorityFindings = this.prioritizeFindings(findings);
      
      // Gather context
      const contextData = await this.gatherContext({ findings: priorityFindings });
      
      // Build fix-specific prompt
      const prompt = await this.buildFixPrompt(contextData);
      
      // Calculate metadata
      const metadata = this.calculateMetadata(priorityFindings, contextData.files);
      
      return {
        prompt,
        metadata
      };
      
    } catch (error) {
      this.outputChannel.appendLine(`[PromptGeneration] Error: ${error}`);
      throw error;
    }
  }

  /**
   * Gather all necessary context for prompt generation
   */
  private async gatherContext(context: PromptGenerationContext): Promise<{
    findings: Finding[];
    files: string[];
    dependencies: DependencyLink[];
    filesByPath: Map<string, { relativePath: string; findings: Finding[] }>;
  }> {
    // Get unique files from findings
    const files = Array.from(new Set(
      context.findings.map(f => f.file).filter(f => f)
    ));
    
    // Get workspace root for relative paths
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    
    // Build file map with relative paths
    const filesByPath = new Map<string, { relativePath: string; findings: Finding[] }>();
    for (const file of files) {
      const relativePath = workspaceRoot 
        ? path.relative(workspaceRoot, file)
        : path.basename(file);
      
      const fileFindings = context.findings.filter(f => f.file === file);
      
      filesByPath.set(file, {
        relativePath,
        findings: fileFindings
      });
    }
    
    // Analyze dependencies if we have multiple files
    let dependencies: DependencyLink[] = [];
    if (files.length > 1) {
      try {
        // Get all workspace files for dependency analysis
        const allFiles = await this.discoverWorkspaceFiles();
        dependencies = await this.dependencyAnalyzer.analyzeDependencies(allFiles);
        
        // Filter to only dependencies involving our files
        dependencies = dependencies.filter(dep => 
          files.includes(dep.source) || files.includes(dep.target)
        );
      } catch (error) {
        this.outputChannel.appendLine(`[PromptGeneration] Warning: Could not analyze dependencies: ${error}`);
      }
    }
    
    return {
      findings: context.findings,
      files,
      dependencies,
      filesByPath
    };
  }

  /**
   * Build the actual prompt using LLM or template
   */
  private async buildPrompt(
    contextData: Awaited<ReturnType<typeof this.gatherContext>>,
    userGoal?: string
  ): Promise<string> {
    const config = vscode.workspace.getConfiguration('aspectcode.promptGeneration');
    const useLLM = config.get<boolean>('useLLM', false);
    const endpoint = config.get<string>('llmEndpoint', 'http://localhost:11434/api/generate');
    const model = config.get<string>('llmModel', 'llama3.2:3b');
    
    if (useLLM) {
      try {
        return await this.buildPromptWithLLM(contextData, userGoal, endpoint, model);
      } catch (error) {
        this.outputChannel.appendLine(`[PromptGeneration] LLM generation failed, falling back to template: ${error}`);
        // Fall through to template
      }
    }
    
    // Template-based generation (always available as fallback)
    return this.buildPromptWithTemplate(contextData, userGoal);
  }

  /**
   * Build prompt using LLM
   */
  private async buildPromptWithLLM(
    contextData: Awaited<ReturnType<typeof this.gatherContext>>,
    userGoal: string | undefined,
    endpoint: string,
    model: string
  ): Promise<string> {
    // Prepare context summary for LLM
    const contextSummary = this.buildContextSummary(contextData, userGoal);
    
    // Call LLM
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model,
        prompt: contextSummary,
        system: SYSTEM_PROMPT,
        stream: false,
        options: {
          temperature: 0.7,
          num_predict: 1000
        }
      })
    });
    
    if (!response.ok) {
      throw new Error(`LLM request failed: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json() as any;
    return data.response || '';
  }

  /**
   * Build prompt using template (deterministic, no LLM required)
   */
  private buildPromptWithTemplate(
    contextData: Awaited<ReturnType<typeof this.gatherContext>>,
    userGoal?: string
  ): string {
    const { findings, filesByPath, dependencies } = contextData;
    
    // Group findings by severity
    const bySeversity = {
      error: findings.filter(f => f.severity === 'error'),
      warn: findings.filter(f => f.severity === 'warn'),
      info: findings.filter(f => f.severity === 'info')
    };
    
    let prompt = '# Code Quality Task\n\n';
    
    // Objective section
    prompt += '## Objective\n\n';
    if (userGoal) {
      prompt += `${userGoal}\n\n`;
    } else {
      prompt += `Fix ${findings.length} code quality issues across ${filesByPath.size} files.\n\n`;
    }
    
    // Summary
    prompt += `**Summary**: `;
    prompt += `${bySeversity.error.length} errors, ${bySeversity.warn.length} warnings, ${bySeversity.info.length} info issues.\n\n`;
    
    // Affected Files section
    prompt += '## Affected Files\n\n';
    for (const [file, info] of filesByPath) {
      prompt += `- \`${info.relativePath}\` (${info.findings.length} issues)\n`;
    }
    prompt += '\n';
    
    // Key Issues section
    prompt += '## Key Issues\n\n';
    
    if (bySeversity.error.length > 0) {
      prompt += '### Errors (High Priority)\n\n';
      for (const finding of bySeversity.error.slice(0, 10)) {
        const fileInfo = filesByPath.get(finding.file);
        const location = finding.span 
          ? `:${finding.span.start.line}:${finding.span.start.column}`
          : '';
        prompt += `- **${finding.code}** in \`${fileInfo?.relativePath || path.basename(finding.file)}${location}\`\n`;
        prompt += `  ${finding.message}\n`;
      }
      prompt += '\n';
    }
    
    if (bySeversity.warn.length > 0) {
      prompt += '### Warnings (Medium Priority)\n\n';
      for (const finding of bySeversity.warn.slice(0, 5)) {
        const fileInfo = filesByPath.get(finding.file);
        prompt += `- **${finding.code}** in \`${fileInfo?.relativePath || path.basename(finding.file)}\`: ${finding.message}\n`;
      }
      prompt += '\n';
    }
    
    // Dependency context if available
    if (dependencies.length > 0) {
      prompt += '## File Relationships\n\n';
      prompt += 'Key dependencies to consider:\n\n';
      for (const dep of dependencies.slice(0, 5)) {
        const sourceFile = filesByPath.get(dep.source);
        const targetFile = filesByPath.get(dep.target);
        if (sourceFile && targetFile) {
          prompt += `- \`${sourceFile.relativePath}\` depends on \`${targetFile.relativePath}\`\n`;
        }
      }
      prompt += '\n';
    }
    
    // Suggested Approach
    prompt += '## Suggested Approach\n\n';
    prompt += '1. Start with error-level issues in the most critical files\n';
    prompt += '2. Consider file dependencies when making changes\n';
    prompt += '3. Run examination after each fix to ensure no new issues\n';
    prompt += '4. Address warnings and info issues after errors are resolved\n';
    
    if (findings.some(f => f.fixable)) {
      prompt += '5. Some issues have automated fixes available - apply these first\n';
    }
    
    prompt += '\n';
    
    // Success Criteria
    prompt += '## Success Criteria\n\n';
    prompt += `- [ ] All ${bySeversity.error.length} error-level issues resolved\n`;
    prompt += `- [ ] All ${bySeversity.warn.length} warning-level issues addressed\n`;
    prompt += '- [ ] Code passes validation checks\n';
    prompt += '- [ ] No new issues introduced\n';
    prompt += '- [ ] All changes properly tested\n\n';
    
    // Footer
    prompt += '---\n\n';
    prompt += '*Note: This is a high-level overview. Read the actual files for implementation details.*\n';
    
    return prompt;
  }

  /**
   * Build prompt specifically for auto-fixing issues
   */
  private async buildFixPrompt(
    contextData: Awaited<ReturnType<typeof this.gatherContext>>
  ): Promise<string> {
    const { findings, filesByPath } = contextData;
    
    let prompt = '# Automated Fix Task\n\n';
    
    prompt += '## Objective\n\n';
    prompt += `Automatically fix ${findings.length} code quality issues that require manual intervention.\n\n`;
    
    // Affected Files
    prompt += '## Files to Fix\n\n';
    for (const [file, info] of filesByPath) {
      prompt += `- \`${info.relativePath}\` (${info.findings.length} issues)\n`;
    }
    prompt += '\n';
    
    // Issues by file
    prompt += '## Issues to Fix\n\n';
    for (const [file, info] of filesByPath) {
      prompt += `### ${info.relativePath}\n\n`;
      for (const finding of info.findings) {
        const location = finding.span 
          ? `Line ${finding.span.start.line}, Col ${finding.span.start.column}`
          : 'Unknown location';
        prompt += `**${finding.code}** (${location})\n`;
        prompt += `- ${finding.message}\n`;
        prompt += `- Severity: ${finding.severity}\n`;
        if (finding._raw?.suggested_patchlet) {
          prompt += `- Suggested fix available\n`;
        }
        prompt += '\n';
      }
    }
    
    // Approach
    prompt += '## Approach\n\n';
    prompt += '1. Review each issue carefully\n';
    prompt += '2. Apply minimal, targeted fixes\n';
    prompt += '3. Preserve existing code style and formatting\n';
    prompt += '4. Test changes to ensure no regressions\n\n';
    
    prompt += '## Important\n\n';
    prompt += '- Make minimal changes that directly address each issue\n';
    prompt += '- Do not refactor unrelated code\n';
    prompt += '- Maintain backward compatibility\n';
    prompt += '- Follow existing patterns in the codebase\n';
    
    return prompt;
  }

  /**
   * Build context summary for LLM
   */
  private buildContextSummary(
    contextData: Awaited<ReturnType<typeof this.gatherContext>>,
    userGoal?: string
  ): string {
    const { findings, filesByPath, dependencies } = contextData;
    
    let summary = '';
    
    if (userGoal) {
      summary += `User Goal: ${userGoal}\n\n`;
    }
    
    summary += `Codebase Context:\n`;
    summary += `- Files affected: ${filesByPath.size}\n`;
    summary += `- Total issues: ${findings.length}\n`;
    summary += `- Dependencies: ${dependencies.length} relationships\n\n`;
    
    summary += `Files:\n`;
    for (const [file, info] of filesByPath) {
      summary += `- ${info.relativePath} (${info.findings.length} issues)\n`;
    }
    
    summary += `\nTop Issues:\n`;
    for (const finding of findings.slice(0, 10)) {
      summary += `- ${finding.code}: ${finding.message}\n`;
    }
    
    return summary;
  }

  /**
   * Prioritize findings for auto-fix
   */
  private prioritizeFindings(findings: Finding[]): Finding[] {
    // Sort by severity, then by file
    return findings.sort((a, b) => {
      const severityOrder = { error: 0, warn: 1, info: 2 };
      const severityDiff = severityOrder[a.severity] - severityOrder[b.severity];
      if (severityDiff !== 0) return severityDiff;
      return a.file.localeCompare(b.file);
    });
  }

  /**
   * Calculate metadata for the generated prompt
   */
  private calculateMetadata(
    findings: Finding[],
    files: string[]
  ): GeneratedPrompt['metadata'] {
    const severity = {
      error: findings.filter(f => f.severity === 'error').length,
      warn: findings.filter(f => f.severity === 'warn').length,
      info: findings.filter(f => f.severity === 'info').length
    };
    
    return {
      filesIncluded: files.length,
      findingsIncluded: findings.length,
      severity,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Discover all workspace files
   */
  private async discoverWorkspaceFiles(): Promise<string[]> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      return [];
    }
    
    const files: string[] = [];
    const patterns = ['**/*.{ts,tsx,js,jsx,py,java,cs,go,rs}'];
    
    for (const folder of workspaceFolders) {
      for (const pattern of patterns) {
        const found = await vscode.workspace.findFiles(
          new vscode.RelativePattern(folder, pattern),
          '**/node_modules/**'
        );
        files.push(...found.map(uri => uri.fsPath));
      }
    }
    
    return files;
  }

  /**
   * Read knowledge base files (.aspect/*.md)
   */
  private async readKBFiles(): Promise<{
    structure?: string;
    awareness?: string;
    code?: string;
    flows?: string;
    conventions?: string;
  }> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      return {};
    }

    const kbFiles: { 
      structure?: string;
      awareness?: string;
      code?: string;
      flows?: string;
      conventions?: string;
    } = {};

    try {
      const structureUri = vscode.Uri.joinPath(workspaceFolder.uri, '.aspect', 'structure.md');
      const structureBytes = await vscode.workspace.fs.readFile(structureUri);
      kbFiles.structure = Buffer.from(structureBytes).toString('utf8');
    } catch (error) {
      // File doesn't exist, skip
    }

    try {
      const awarenessUri = vscode.Uri.joinPath(workspaceFolder.uri, '.aspect', 'awareness.md');
      const awarenessBytes = await vscode.workspace.fs.readFile(awarenessUri);
      kbFiles.awareness = Buffer.from(awarenessBytes).toString('utf8');
    } catch (error) {
      // File doesn't exist, skip
    }

    try {
      const codeUri = vscode.Uri.joinPath(workspaceFolder.uri, '.aspect', 'code.md');
      const codeBytes = await vscode.workspace.fs.readFile(codeUri);
      kbFiles.code = Buffer.from(codeBytes).toString('utf8');
    } catch (error) {
      // File doesn't exist, skip
    }

    try {
      const flowsUri = vscode.Uri.joinPath(workspaceFolder.uri, '.aspect', 'flows.md');
      const flowsBytes = await vscode.workspace.fs.readFile(flowsUri);
      kbFiles.flows = Buffer.from(flowsBytes).toString('utf8');
    } catch (error) {
      // File doesn't exist, skip
    }

    try {
      const conventionsUri = vscode.Uri.joinPath(workspaceFolder.uri, '.aspect', 'conventions.md');
      const conventionsBytes = await vscode.workspace.fs.readFile(conventionsUri);
      kbFiles.conventions = Buffer.from(conventionsBytes).toString('utf8');
    } catch (error) {
      // File doesn't exist, skip
    }

    return kbFiles;
  }

  /**
   * Performs sophisticated impact analysis on findings using:
   * - Dependency graph analysis (hub files get higher impact)
   * - Hotspot detection (problematic files need careful fixes)
   * - Pattern detection (systematic issues across multiple files)
   * - Severity and fixability weighting
   * - Effort vs value ratio
   */
  private async analyzeImpact(findings: Finding[]): Promise<ImpactAnalysis[]> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    const kbFiles = await this.readKBFiles();
    
    // Extract structural context from KB files
    const hubFiles = this.extractHubFiles(kbFiles.structure);
    const hotspotFiles = this.extractHotspotFiles(kbFiles.awareness);
    const circularDeps = this.extractCircularDeps(kbFiles.structure);
    
    // Group findings by rule to detect patterns
    const ruleGroups = new Map<string, Finding[]>();
    for (const finding of findings) {
      if (!ruleGroups.has(finding.code)) {
        ruleGroups.set(finding.code, []);
      }
      ruleGroups.get(finding.code)!.push(finding);
    }
    
    // Analyze each finding
    const analyses: ImpactAnalysis[] = [];
    
    for (const finding of findings) {
      const relativePath = workspaceRoot 
        ? path.relative(workspaceRoot, finding.file)
        : path.basename(finding.file);
      
      let score = 0;
      const reasons: string[] = [];
      const affectedFiles: string[] = [relativePath];
      
      // Base score from severity
      if (finding.severity === 'error') {
        score += 100;
        reasons.push('Critical severity (error)');
      } else if (finding.severity === 'warn') {
        score += 50;
        reasons.push('Warning severity');
      } else {
        score += 10;
        reasons.push('Info severity');
      }
      
      // Security/correctness rules get massive boost
      const securityRules = [
        'memory-buffer-overflow',
        'memory-malloc-null-check-missing',
        'memory-return-address',
        'security-',
        'auth-',
        'sql-injection',
        'xss-',
        'csrf-'
      ];
      if (securityRules.some(prefix => finding.code.toLowerCase().includes(prefix))) {
        score += 200;
        reasons.push('Security/correctness critical');
      }
      
      // Hub file amplification (affects many dependents)
      if (hubFiles.some(hub => relativePath.includes(hub))) {
        score += 80;
        reasons.push('Hub file (high fanout - affects many files)');
        // Add dependent files to affected
        affectedFiles.push('...and multiple dependents');
      }
      
      // Hotspot penalty (risky to change)
      const isHotspot = hotspotFiles.some(hot => relativePath.includes(hot));
      if (isHotspot) {
        score -= 20; // Reduce slightly due to risk
        reasons.push('Hotspot file (already problematic - needs care)');
      }
      
      // Pattern detection (same rule across multiple files)
      const ruleOccurrences = ruleGroups.get(finding.code)?.length || 1;
      if (ruleOccurrences >= 5) {
        score += 60;
        reasons.push(`Systematic pattern (${ruleOccurrences} occurrences - fix once, apply broadly)`);
      } else if (ruleOccurrences >= 3) {
        score += 30;
        reasons.push(`Repeated issue (${ruleOccurrences} occurrences)`);
      }
      
      // Fixable boost
      if (finding.fixable) {
        score += 40;
        reasons.push('Auto-fixable (low effort)');
      }
      
      // Circular dependency involvement
      const inCircularDep = circularDeps.some(cycle => 
        cycle.some(file => relativePath.includes(file))
      );
      if (inCircularDep) {
        if (finding.code.includes('import') || finding.code.includes('circular')) {
          score += 90;
          reasons.push('Circular dependency issue (architectural improvement)');
        } else {
          score -= 10;
          reasons.push('In circular dependency (extra caution needed)');
        }
      }
      
      // Categorize
      let category: ImpactAnalysis['category'];
      let effort: ImpactAnalysis['effort'];
      let risk: ImpactAnalysis['risk'];
      
      if (finding.fixable && !isHotspot && score < 150) {
        category = 'quick-win';
        effort = 'low';
        risk = 'low';
      } else if (securityRules.some(p => finding.code.toLowerCase().includes(p))) {
        category = 'critical-error';
        effort = 'medium';
        risk = 'medium';
      } else if (ruleOccurrences >= 5) {
        category = 'systematic-pattern';
        effort = 'medium';
        risk = 'low';
      } else if (inCircularDep && finding.code.includes('circular')) {
        category = 'architectural';
        effort = 'high';
        risk = 'high';
      } else {
        category = 'low-priority';
        effort = 'medium';
        risk = isHotspot ? 'high' : 'medium';
      }
      
      analyses.push({
        finding,
        impactScore: score,
        reasons,
        affectedFiles,
        category,
        effort,
        risk
      });
    }
    
    // Sort by impact score descending
    return analyses.sort((a, b) => b.impactScore - a.impactScore);
  }
  
  /**
   * Extract hub files from structure.md (files with high import fanout)
   */
  private extractHubFiles(structure?: string): string[] {
    if (!structure) return [];
    
    const hubs: string[] = [];
    const lines = structure.split('\n');
    
    for (const line of lines) {
      // Look for patterns like "hub" or "widely imported" or specific metrics
      if (line.toLowerCase().includes('hub') || 
          line.toLowerCase().includes('widely imported') ||
          /imported by \d{2,}/.test(line)) {
        // Extract file path
        const match = line.match(/`([^`]+)`/);
        if (match) {
          hubs.push(match[1]);
        }
      }
    }
    
    return hubs;
  }
  
  /**
   * Extract hotspot files from awareness.md (high-impact files)
   */
  private extractHotspotFiles(hotspots?: string): string[] {
    if (!hotspots) return [];
    
    const files: string[] = [];
    const lines = hotspots.split('\n');
    
    for (const line of lines) {
      // Look for file paths in markdown
      const match = line.match(/`([^`]+\.[a-z]{2,4})`/);
      if (match) {
        files.push(match[1]);
      }
    }
    
    return files;
  }
  
  /**
   * Extract circular dependency cycles from structure.md
   */
  private extractCircularDeps(structure?: string): string[][] {
    if (!structure) return [];
    
    const cycles: string[][] = [];
    const lines = structure.split('\n');
    
    for (const line of lines) {
      // Look for cycle patterns: A -> B -> C -> A
      if (line.includes('->') && line.includes('cycle')) {
        const files = line.match(/`([^`]+)`/g);
        if (files && files.length > 1) {
          cycles.push(files.map(f => f.replace(/`/g, '')));
        }
      }
    }
    
    return cycles;
  }
  
  /**
   * Generate a comprehensive findings.md file in .aspect/
   * This file is continuously updated and provides rich context for AI agents.
   */
  async generateFindingsSummary(findings: Finding[]): Promise<FindingsSummary> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceRoot) {
      throw new Error('No workspace folder open');
    }
    
    this.outputChannel.appendLine('[PromptGeneration] Generating findings summary...');
    
    // Perform sophisticated impact analysis
    const impactRanked = await this.analyzeImpact(findings);
    
    // Group by file
    const byFile = new Map<string, Finding[]>();
    for (const finding of findings) {
      const relativePath = path.relative(workspaceRoot, finding.file);
      if (!byFile.has(relativePath)) {
        byFile.set(relativePath, []);
      }
      byFile.get(relativePath)!.push(finding);
    }
    
    const byFileArray = Array.from(byFile.entries())
      .map(([file, findings]) => ({
        file,
        count: findings.length,
        errorCount: findings.filter(f => f.severity === 'error').length
      }))
      .sort((a, b) => b.count - a.count);
    
    // Group by rule
    const byRule = new Map<string, Finding[]>();
    for (const finding of findings) {
      if (!byRule.has(finding.code)) {
        byRule.set(finding.code, []);
      }
      byRule.get(finding.code)!.push(finding);
    }
    
    const byRuleArray = Array.from(byRule.entries())
      .map(([rule, findings]) => ({
        rule,
        count: findings.length,
        severity: findings[0].severity
      }))
      .sort((a, b) => b.count - a.count);
    
    // Extract structural context
    const kbFiles = await this.readKBFiles();
    const hubFiles = this.extractHubFiles(kbFiles.structure);
    const hotspotFiles = this.extractHotspotFiles(kbFiles.awareness);
    const circularDeps = this.extractCircularDeps(kbFiles.structure);
    
    const summary: FindingsSummary = {
      timestamp: new Date().toISOString(),
      totalFindings: findings.length,
      byFile: byFileArray,
      byRule: byRuleArray,
      impactRanked,
      hubFiles,
      hotspotFiles,
      circularDeps
    };
    
    // Write to .aspect/findings.md
    await this.writeFindingsSummaryFile(summary);
    
    return summary;
  }
  
  /**
   * Write the findings summary to .aspect/findings.md
   */
  private async writeFindingsSummaryFile(summary: FindingsSummary): Promise<void> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceRoot) return;
    
    const kbPath = path.join(workspaceRoot, '.aspect');
    const findingsPath = path.join(kbPath, 'findings.md');
    
    // Ensure .aspect directory exists
    if (!fs.existsSync(kbPath)) {
      fs.mkdirSync(kbPath, { recursive: true });
    }
    
    let content = '# Findings Summary\n\n';
    content += `**Last Updated:** ${new Date(summary.timestamp).toLocaleString()}\n\n`;
    content += `**Total Findings:** ${summary.totalFindings}\n\n`;
    
    // Top impact findings
    content += '## Highest Impact Fixes\n\n';
    content += 'These fixes provide the best value based on algorithmic analysis of severity, scope, patterns, and architectural context.\n\n';
    
    for (const analysis of summary.impactRanked.slice(0, 15)) {
      const finding = analysis.finding;
      const relativePath = path.relative(workspaceRoot!, finding.file);
      const location = finding.span 
        ? `${finding.span.start.line}:${finding.span.start.column}`
        : 'unknown';
      
      content += `### ${analysis.category.toUpperCase()} | ${finding.severity.toUpperCase()}

`;
      content += `- **File:** \`${relativePath}\` (${location})
`;
      content += `- **Rule:** \`${finding.code}\`
`;
      content += `- **Effort:** ${analysis.effort} | **Risk:** ${analysis.risk}
`;
      content += `- **Message:** ${finding.message}
`;
      content += `- **Why High Priority:**
`;
      for (const reason of analysis.reasons) {
        content += `  - ${reason}\n`;
      }
      if (analysis.affectedFiles.length > 1) {
        content += `- **Affected Files:** ${analysis.affectedFiles.join(', ')}\n`;
      }
      content += '\n';
    }
    
    // Findings by file
    content += '## Findings by File\n\n';
    for (const { file, count, errorCount } of summary.byFile.slice(0, 20)) {
      content += `- \`${file}\`: ${count} issues (${errorCount} errors)\n`;
    }
    if (summary.byFile.length > 20) {
      content += `\n*...and ${summary.byFile.length - 20} more files*\n`;
    }
    content += '\n';
    
    // Findings by rule
    content += '## Findings by Rule\n\n';
    for (const { rule, count, severity } of summary.byRule.slice(0, 20)) {
      content += `- \`${rule}\`: ${count} occurrences (${severity})\n`;
    }
    if (summary.byRule.length > 20) {
      content += `\n*...and ${summary.byRule.length - 20} more rules*\n`;
    }
    content += '\n';
    
    // Structural context
    if (summary.hubFiles.length > 0) {
      content += '## Hub Files (High Fanout)\n\n';
      content += 'These files are widely imported. Changes affect many dependents.\n\n';
      for (const hub of summary.hubFiles) {
        content += `- \`${hub}\`\n`;
      }
      content += '\n';
    }
    
    if (summary.hotspotFiles.length > 0) {
      content += '## Hotspot Files (Already Problematic)\n\n';
      content += 'These files already have many issues. Changes require extra care.\n\n';
      for (const hotspot of summary.hotspotFiles) {
        content += `- \`${hotspot}\`\n`;
      }
      content += '\n';
    }
    
    if (summary.circularDeps.length > 0) {
      content += '## Circular Dependencies\n\n';
      for (const cycle of summary.circularDeps) {
        content += `- ${cycle.map(f => `\`${f}\``).join(' → ')}\n`;
      }
      content += '\n';
    }
    
    content += '---\n\n';
    content += '*This file is automatically generated and continuously updated by Aspect Code.*\n';
    
    fs.writeFileSync(findingsPath, content, 'utf8');
    this.outputChannel.appendLine(`[PromptGeneration] Findings summary written to ${findingsPath}`);
  }

  /**
   * Build a prompt to explain the current file using codebase context
   */
  async buildExplainCurrentFilePrompt(args: {
    activeFileUri: vscode.Uri;
    fileContent: string;
  }): Promise<string> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    const relativePath = workspaceRoot 
      ? path.relative(workspaceRoot, args.activeFileUri.fsPath)
      : path.basename(args.activeFileUri.fsPath);

    // Read KB files
    const kbFiles = await this.readKBFiles();
    
    // Get workspace findings and analyze this specific file
    const allFiles = await this.discoverWorkspaceFiles();
    const dependencies = await this.dependencyAnalyzer.analyzeDependencies(allFiles);
    
    // Find dependencies involving this file
    const incomingDeps = dependencies.filter(d => d.target === args.activeFileUri.fsPath);
    const outgoingDeps = dependencies.filter(d => d.source === args.activeFileUri.fsPath);

    let prompt = '# File Explanation - Architectural Context\n\n';
    
    prompt += `You are an AI coding agent with full workspace access. Focus on understanding this file\'s role in the codebase architecture—how it fits structurally and what it does.\n\n`;
    
    prompt += `## Context Files\n\n`;
    
    // Reference all available KB files
    const availableKBFiles = [];
    if (kbFiles.structure) availableKBFiles.push('`.aspect/structure.md`');
    if (kbFiles.code) availableKBFiles.push('`.aspect/code.md`');
    if (kbFiles.flows) availableKBFiles.push('`.aspect/flows.md`');
    if (kbFiles.conventions) availableKBFiles.push('`.aspect/conventions.md`');
    if (kbFiles.awareness) availableKBFiles.push('`.aspect/awareness.md`');
    
    if (availableKBFiles.length > 0) {
      prompt += `**Read these knowledge base files for structural context:**\n\n`;
      availableKBFiles.forEach((file, index) => {
        prompt += `${index + 1}. ${file}\n`;
      });
      prompt += '\n';
      prompt += 'Focus on architectural understanding:\n';
      prompt += '- **structure.md**: Directory layout, hub modules, circular dependencies\n';
      prompt += '- **code.md**: Data models, function/class index with call relationships\n';
      prompt += '- **flows.md**: Entry points, external integrations, data flow paths\n';
      prompt += '- **conventions.md**: Naming patterns, import styles, framework idioms\n';
      prompt += '- **awareness.md**: Supplementary context (high-impact patterns to watch)\n\n';
    }
    
    // Add the file to explain with context
    prompt += `## Target File\n\n`;
    prompt += `**File path:** \`${relativePath}\`\n`;
    prompt += `**Incoming dependencies:** ${incomingDeps.length} files import this\n`;
    prompt += `**Outgoing dependencies:** ${outgoingDeps.length} imports from this file\n\n`;
    
    if (incomingDeps.length > 5) {
      prompt += `**This is a hub module** - widely imported by ${incomingDeps.length} files. Changes here affect many dependents.\n\n`;
    }
    
    prompt += `**Read the complete file** from workspace to understand full implementation.\n\n`;
    
    prompt += `## Analysis Framework\n\n`;
    
    prompt += `Provide a structured explanation covering these dimensions:\n\n`;
    
    prompt += `### 1. Architectural Role\n`;
    prompt += `- What layer/module does this belong to? (check structure.md)\n`;
    prompt += `- What's its primary responsibility?\n`;
    prompt += `- How does it fit in the overall design?\n`;
    prompt += `- Is it an entry point, service layer, data model, utility, or UI component?\n\n`;
    
    prompt += `### 2. Key Components & Exports\n`;
    prompt += `- List main functions, classes, interfaces, types\n`;
    prompt += `- What does each component do?\n`;
    prompt += `- What's exported (public API) vs internal?\n`;
    prompt += `- Cross-reference with code.md for call relationships\n\n`;
    
    prompt += `### 3. Dependency Analysis\n`;
    prompt += `- What does this file import? (check structure.md for dependencies)\n`;
    prompt += `- Who imports this file?\n`;
    prompt += `- Is this file part of any circular dependencies? (check structure.md)\n`;
    prompt += `- Does it depend on hub modules?\n\n`;
    
    prompt += `### 4. Code Patterns & Style\n`;
    prompt += `- Is the code well-structured and idiomatic? (check conventions.md)\n`;
    prompt += `- Error handling approach\n`;
    prompt += `- Any complexity that might need extra care when modifying?\n`;
    prompt += `- Test coverage indicators (test files, mocking, etc.)\n\n`;
    
    prompt += `### 5. Critical Execution Paths\n`;
    prompt += `- Does this file appear in flows.md? If so, which flows?\n`;
    prompt += `- Are there security-sensitive operations?\n`;
    prompt += `- Performance-critical sections?\n`;
    prompt += `- Data transformation points?\n\n`;
    
    prompt += `### 6. Related Files & Context\n`;
    prompt += `- What files are closely related?\n`;
    prompt += `- What would someone modifying this file need to check?\n`;
    prompt += `- Any coupled behavior with other modules?\n\n`;
    
    prompt += `### 7. Recommendations\n`;
    prompt += `- Potential improvements\n`;
    prompt += `- Refactoring opportunities\n`;
    prompt += `- Risks when modifying\n`;
    prompt += `- Best practices for working with this file\n\n`;
    
    prompt += `## Output Format\n\n`;
    prompt += `Organize your response in clear markdown with the 7 sections above. Be specific and reference line numbers, function names, and related files. Use findings from the KB files to provide accurate, evidence-based analysis.`;
    
    return prompt;
  }

  /**
   * Expand a vague user query into a specific, actionable prompt using LLM.
   * This significantly improves prompt quality by:
   * - Clarifying ambiguous requests
   * - Identifying relevant files and functions
   * - Highlighting architectural risks
   * - Providing specific success criteria
   */
  async expandUserQuery(args: {
    userQuestion: string;
    activeFileUri?: vscode.Uri;
    findings: Finding[];
    llmClient: any;
  }): Promise<string> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    
    // Get current file context
    let currentFile = 'unknown';
    let currentFileFindings: Finding[] = [];
    
    if (args.activeFileUri) {
      currentFile = workspaceRoot
        ? path.relative(workspaceRoot, args.activeFileUri.fsPath)
        : path.basename(args.activeFileUri.fsPath);
      
      currentFileFindings = args.findings.filter(f => 
        f.file === args.activeFileUri!.fsPath
      );
    }
    
    // Read KB files for context
    const kbFiles = await this.readKBFiles();
    
    // Extract key information (first 300 lines to stay within token limits)
    const structureSummary = kbFiles.structure?.split('\n').slice(0, 300).join('\n') || 'No structure.md available';
    const codeSummary = kbFiles.code?.split('\n').slice(0, 300).join('\n') || 'No code.md available';
    const flowsSummary = kbFiles.flows?.split('\n').slice(0, 300).join('\n') || 'No flows.md available';
    
    // Get top findings by severity
    const topFindings = args.findings
      .filter(f => f.severity === 'error')
      .slice(0, 20)
      .map(f => {
        const relPath = workspaceRoot ? path.relative(workspaceRoot, f.file) : path.basename(f.file);
        const location = f.span ? `${f.span.start.line}:${f.span.start.column}` : 'unknown';
        return `- ${f.code} in ${relPath}:${location} - ${f.message}`;
      });
    
    // Build expansion prompt for LLM
    const expansionPrompt = `You are an expert at translating vague user requests into specific, actionable prompts for AI coding agents (like Cursor, Copilot, or Claude).

**User's Question:** "${args.userQuestion}"

**Current Context:**
- Current file: \`${currentFile}\`
- Findings in current file: ${currentFileFindings.length} (${currentFileFindings.filter(f => f.severity === 'error').length} errors)
- Total workspace findings: ${args.findings.length} (${args.findings.filter(f => f.severity === 'error').length} errors)

**Codebase Structure (from structure.md):**
\`\`\`
${structureSummary.substring(0, 1500)}
\`\`\`

**Code Index (from code.md):**
\`\`\`
${codeSummary.substring(0, 1500)}
\`\`\`

**Execution Flows (from flows.md):**
\`\`\`
${flowsSummary.substring(0, 1500)}
\`\`\`

**Top Issues (from findings):**
${topFindings.slice(0, 15).join('\n')}

**Your Task:**
Generate a detailed, specific prompt that an AI coding agent can execute. The prompt should:

1. **Clarify Intent**: What does the user really want? Infer from context if the question is vague.
2. **Identify Targets**: Which specific files, functions, or modules need to be modified?
3. **Highlight Risks**: 
   - Hub files (widely imported - changes affect many dependents)
   - Files in circular dependencies (don't make them worse)
   - Entry points and data flows that could be impacted
4. **Reference Context**: Point to relevant KB files (.aspect/structure.md, code.md, flows.md)
5. **Define Success**: What does "done" look like?
6. **Provide Specifics**: Include line numbers, function names, exact issues to address

**Output Format:**
Write the prompt directly (not meta-commentary about it). Use markdown with clear sections:
- ## Objective
- ## Context Files to Read
- ## Target Files/Functions
- ## Specific Changes Required
- ## Risks to Consider
- ## Success Criteria

Be technical, specific, and actionable. The agent will have full file access - reference files, don't embed their contents.`;

    try {
      const response = await args.llmClient.complete({
        systemPrompt: 'You are an expert software architect who translates vague requests into precise technical specifications.',
        userPrompt: expansionPrompt,
        maxTokens: 1500
      });
      
      return response.text;
    } catch (error) {
      this.outputChannel.appendLine(`[PromptGeneration] Query expansion failed: ${error}`);
      // Fallback to template-based approach
      return await this.buildAgentTaskPrompt({
        userQuestion: args.userQuestion,
        activeFileUri: args.activeFileUri
      });
    }
  }

  /**
   * Build a prompt for an agent task (question, bug fix, feature request)
   */
  async buildAgentTaskPrompt(args: {
    userQuestion: string;
    activeFileUri?: vscode.Uri;
  }): Promise<string> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    
    // Read KB files
    const kbFiles = await this.readKBFiles();
    
    // Get dependency context
    const allFiles = await this.discoverWorkspaceFiles();
    const dependencies = await this.dependencyAnalyzer.analyzeDependencies(allFiles);

    let prompt = '# AI Agent Task - Systematic Implementation\n\n';
    
    prompt += `You are an AI coding agent with full workspace access. You will implement this task using sophisticated reasoning and architectural awareness.\n\n`;
    
    prompt += `## Context Files\n\n`;
    
    // Reference all available KB files
    const availableKBFiles = [];
    if (kbFiles.structure) availableKBFiles.push('`.aspect/structure.md`');
    if (kbFiles.code) availableKBFiles.push('`.aspect/code.md`');
    if (kbFiles.flows) availableKBFiles.push('`.aspect/flows.md`');
    if (kbFiles.conventions) availableKBFiles.push('`.aspect/conventions.md`');
    if (kbFiles.awareness) availableKBFiles.push('`.aspect/awareness.md`');
    
    if (availableKBFiles.length > 0) {
      prompt += `**Read these knowledge base files for structural understanding:**\n\n`;
      availableKBFiles.forEach((file, index) => {
        prompt += `${index + 1}. ${file}\n`;
      });
      prompt += '\n';
      prompt += 'These files provide:\n';
      prompt += '- **structure.md**: Directory layout, hub modules, circular dependencies\n';
      prompt += '- **code.md**: Data models, function/class index with call relationships\n';
      prompt += '- **flows.md**: Entry points, external integrations, data flow paths\n';
      prompt += '- **conventions.md**: Naming patterns, import styles, framework idioms\n';
      prompt += '- **awareness.md**: Supplementary context (high-impact patterns to watch)\n\n';
    }
    
    // Add current file context if available
    if (args.activeFileUri) {
      const relativePath = workspaceRoot 
        ? path.relative(workspaceRoot, args.activeFileUri.fsPath)
        : path.basename(args.activeFileUri.fsPath);
      
      const activeFilePath = args.activeFileUri.fsPath;
      const fileIncomingDeps = dependencies.filter(d => d.target === activeFilePath);
      const fileOutgoingDeps = dependencies.filter(d => d.source === activeFilePath);
      
      prompt += `## Current Context\n\n`;
      prompt += `**Active file:** \`${relativePath}\`\n`;
      prompt += `**Incoming dependencies:** ${fileIncomingDeps.length} files import this\n`;
      prompt += `**Outgoing dependencies:** ${fileOutgoingDeps.length} imports\n`;
      
      if (fileIncomingDeps.length > 5) {
        prompt += `**This is a hub module** - changes affect ${fileIncomingDeps.length} dependents\n`;
      }
      prompt += '\n';
    }
    
    // Add user's question/request
    prompt += `## User's Request\n\n`;
    prompt += `${args.userQuestion}\n\n`;
    
    // Add sophisticated implementation framework
    prompt += `## Implementation Framework\n\n`;
    
    prompt += `**DO NOT just start coding.** Follow this systematic approach:\n\n`;
    
    prompt += `### Phase 1: Deep Understanding\n\n`;
    prompt += `1. **Parse the request** - What exactly is being asked?\n`;
    prompt += `2. **Identify scope:**\n`;
    prompt += `   - Which files/modules are involved? (use structure.md)\n`;
    prompt += `   - Are these hub modules? (check structure.md for dependencies)\n`;
    prompt += `   - Do existing flows cover this functionality? (check flows.md)\n`;
    prompt += `3. **Check for existing patterns:**\n`;
    prompt += `   - Search code.md for similar functionality\n`;
    prompt += `   - Review structure.md for where this type of code belongs\n`;
    prompt += `   - Review conventions.md for naming patterns to follow\n\n`;
    
    prompt += `### Phase 2: Impact Analysis\n\n`;
    prompt += `Assess the impact of proposed changes:\n\n`;
    
    prompt += `**Dependency Risk:**\n`;
    prompt += `- Will this modify hub modules (high fanout)?\n`;
    prompt += `- Could this create/worsen circular dependencies? (check structure.md)\n`;
    prompt += `- What's the dependency chain?\n\n`;
    
    prompt += `**Awareness Context:**\n`;
    prompt += `- Check awareness.md for relevant context on affected files\n`;
    prompt += `- What patterns or risks have been noted?\n`;
    prompt += `- Is refactoring needed before adding features?\n\n`;
    
    prompt += `**Flow Impact:**\n`;
    prompt += `- Does this affect critical execution paths? (check flows.md)\n`;
    prompt += `- Could this break existing functionality?\n`;
    prompt += `- What entry points are affected?\n\n`;
    
    prompt += `**Cross-Module Impact:**\n`;
    prompt += `- Use code.md to identify call relationships\n`;
    prompt += `- Check what calls modified functions (reverse dependencies)\n`;
    prompt += `- Verify module boundary compliance (structure.md)\n\n`;
    
    prompt += `### Phase 3: Design & Planning\n\n`;
    prompt += `Create a concrete implementation plan:\n\n`;
    
    prompt += `1. **File-level changes:**\n`;
    prompt += `   - List exact files to create/modify\n`;
    prompt += `   - Specify which functions/classes to add/change\n`;
    prompt += `   - Note required imports and their sources\n\n`;
    
    prompt += `2. **Follow patterns:**\n`;
    prompt += `   - Match naming conventions (conventions.md)\n`;
    prompt += `   - Use existing patterns (code.md)\n`;
    prompt += `   - Maintain module boundaries\n\n`;
    
    prompt += `3. **Risk mitigation:**\n`;
    prompt += `   - Plan for hub module changes (thorough testing)\n`;
    prompt += `   - Avoid worsening circular dependencies\n`;
    prompt += `   - Handle high-impact files carefully (smaller changes)\n\n`;
    
    prompt += `### Phase 4: Implementation\n\n`;
    prompt += `Execute the plan systematically:\n\n`;
    
    prompt += `1. **Read all affected files** completely (no snippets)\n`;
    prompt += `2. **Make targeted changes:**\n`;
    prompt += `   - Implement one logical unit at a time\n`;
    prompt += `   - Preserve existing behavior unless explicitly changing\n`;
    prompt += `   - Add proper error handling and validation\n`;
    prompt += `3. **Verify dependencies:**\n`;
    prompt += `   - Check all imports resolve correctly\n`;
    prompt += `   - No new circular dependencies introduced\n`;
    prompt += `   - No missing or broken imports\n\n`;
    
    prompt += `### Phase 5: Validation\n\n`;
    prompt += `Before considering the task complete:\n\n`;
    
    prompt += `1. **Cross-check against KB:**\n`;
    prompt += `   - Changes follow structure.md layout\n`;
    prompt += `   - Changes follow conventions.md patterns\n`;
    prompt += `   - Dependencies are properly managed\n`;
    prompt += `2. **Test considerations:**\n`;
    prompt += `   - What should be tested?\n`;
    prompt += `   - Are there existing tests to update?\n`;
    prompt += `   - What edge cases exist?\n`;
    prompt += `3. **Document:**\n`;
    prompt += `   - Clear commit messages referencing issue IDs\n`;
    prompt += `   - Comments for complex logic\n`;
    prompt += `   - Update documentation if APIs changed\n\n`;
    
    prompt += `## Execution\n\n`;
    prompt += `Now implement the task using the framework above. Be thorough, systematic, and architectural-aware. Quality over speed.`;
    
    return prompt;
  }

  /**
   * Build a prompt that leverages structural understanding to help the AI plan and execute tasks
   */
  async buildProposeFixesPrompt(args: {
    findings: Finding[];
    userContext?: string;
  }): Promise<string> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    
    // Generate comprehensive findings summary with impact analysis
    await this.generateFindingsSummary(args.findings);
    
    // Read KB files
    const kbFiles = await this.readKBFiles();

    let prompt = '# Structural Planning Guide\n\n';
    
    prompt += `You are an AI coding agent with full workspace access. **Aspect Code** has analyzed this codebase and generated structural intelligence in \`.aspect/\` to help you understand the architecture before making changes.\n\n`;
    
    // Include user context if provided - this shapes the entire plan
    if (args.userContext) {
      prompt += `## Your Task\n\n`;
      prompt += `**${args.userContext}**\n\n`;
      prompt += `Use the structural context below to understand how this task relates to the codebase architecture, then create a plan that accounts for dependencies and impact.\n\n`;
    } else {
      prompt += `## Your Task\n\n`;
      prompt += `Review the codebase structure and identify opportunities for improvement based on the architectural patterns and observations in the KB files.\n\n`;
    }
    
    prompt += `## Structural Context (Read First)\n\n`;
    prompt += `These files contain Aspect Code's analysis of the codebase:\n\n`;
    prompt += `| File | What It Tells You |\n`;
    prompt += `|------|-------------------|\n`;
    prompt += `| \`.aspect/structure.md\` | Directory layout, hub modules (high-traffic files), circular dependencies |\n`;
    prompt += `| \`.aspect/code.md\` | Symbols, call relationships, data models |\n`;
    prompt += `| \`.aspect/flows.md\` | Entry points, external integrations, data flow paths |\n`;
    prompt += `| \`.aspect/awareness.md\` | High-impact areas, patterns to watch, contextual notes |\n`;
    prompt += `| \`.aspect/conventions.md\` | Naming patterns, import styles, framework idioms |\n\n`;
    
    prompt += `## Planning Approach\n\n`;
    prompt += `### 1. Understand the Architecture\n\n`;
    prompt += `Before writing any code:\n`;
    prompt += `- **Read structure.md** → Where does this code live? What are the hub files?\n`;
    prompt += `- **Check code.md** → What functions/classes are involved? Who calls them?\n`;
    prompt += `- **Trace flows.md** → How does data move through the relevant paths?\n`;
    prompt += `- **Review awareness.md** → Are there notes about this area?\n\n`;
    
    prompt += `### 2. Assess Impact\n\n`;
    prompt += `For any change you're considering:\n`;
    prompt += `- **Hub files** (listed in structure.md) → Changes here affect many dependents\n`;
    prompt += `- **Circular dependencies** → Don't worsen existing cycles\n`;
    prompt += `- **Call chains** (in code.md) → Check "Called by" to understand blast radius\n`;
    prompt += `- **Entry points** (in flows.md) → These are user-facing; test carefully\n\n`;
    
    prompt += `### 3. Create Your Plan\n\n`;
    prompt += `Based on structural understanding, outline:\n`;
    prompt += `- What files will be touched and why\n`;
    prompt += `- What dependencies exist between changes\n`;
    prompt += `- What order to make changes (dependency-aware)\n`;
    prompt += `- How to verify each step works\n\n`;
    
    prompt += `### 4. Execute Incrementally\n\n`;
    prompt += `- Make one logical change at a time\n`;
    prompt += `- Follow existing patterns in the codebase\n`;
    prompt += `- Read affected files fully before editing\n`;
    prompt += `- Verify after each change before moving on\n\n`;
    
    prompt += `## What to Watch For\n\n`;
    prompt += `**High-Risk Patterns:**\n`;
    prompt += `- Editing hub files without checking all dependents\n`;
    prompt += `- Breaking circular dependency cycles (valuable but risky)\n`;
    prompt += `- Changing function signatures called from multiple places\n`;
    prompt += `- Modifying entry points (HTTP handlers, CLI commands)\n\n`;
    
    prompt += `**Low-Value Changes (Skip):**\n`;
    prompt += `- Whitespace/formatting (use formatters)\n`;
    prompt += `- Auto-generated code\n`;
    prompt += `- Style preferences without functional benefit\n\n`;
    
    prompt += `## Output Format\n\n`;
    
    if (args.userContext) {
      prompt += `### Understanding\n`;
      prompt += `Summarize what you learned from the KB files relevant to: "${args.userContext}"\n\n`;
      prompt += `### Plan\n`;
      prompt += `1. [First step with file and rationale]\n`;
      prompt += `2. [Second step...]\n`;
      prompt += `...\n\n`;
      prompt += `### Execution\n`;
      prompt += `For each step: what you read, what you changed, how you verified it.\n\n`;
    } else {
      prompt += `### Structural Overview\n`;
      prompt += `What you learned about the codebase architecture.\n\n`;
      prompt += `### Opportunities\n`;
      prompt += `Areas where improvements would have high value based on structural analysis.\n\n`;
      prompt += `### Recommended Actions\n`;
      prompt += `Specific changes with rationale tied to structural understanding.\n\n`;
    }
    
    prompt += `---\n\n`;
    prompt += `**Key Principle:** The KB files exist so you don't have to guess about architecture. Read them first, plan with that knowledge, then execute incrementally.\n`;
    
    return prompt;
  }

  /**
   * Build a prompt to help AI agents recover from issues/mistakes
   * Uses codebase context to provide targeted guidance
   */
  async buildAlignmentPrompt(args: {
    issueDescription: string;
    findings: any[];
  }): Promise<string> {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || '';
    
    // Read KB files for context
    const kbFiles = await this.readKBFiles();
    
    // Read alignments file for previous issues
    let previousAlignments: any[] = [];
    try {
      const alignmentsPath = path.join(workspaceRoot, 'ALIGNMENTS.json');
      if (fs.existsSync(alignmentsPath)) {
        const content = fs.readFileSync(alignmentsPath, 'utf-8');
        const parsed = JSON.parse(content);
        previousAlignments = parsed.alignments || [];
      }
    } catch (e) {
      // Ignore - file may not exist yet
    }

    let prompt = '# Alignment Recovery - Debugging Mode\n\n';
    
    prompt += `You are helping to recover from an issue encountered during coding. The user has reported a problem.\n\n`;
    
    prompt += `## Reported Issue\n\n`;
    prompt += `**Problem:** ${args.issueDescription}\n\n`;
    
    // Show previous similar issues if any have resolutions
    const resolvedAlignments = previousAlignments
      .filter(a => a.resolution && a.resolution.trim().length > 0)
      .slice(0, 5);
    
    if (resolvedAlignments.length > 0) {
      prompt += `## Previous Issues & Resolutions\n\n`;
      prompt += `**Check these first** - similar problems may have been solved before:\n\n`;
      
      for (const alignment of resolvedAlignments) {
        prompt += `### ${new Date(alignment.timestamp).toLocaleDateString()}\n`;
        prompt += `- **Issue:** ${alignment.issue}\n`;
        if (alignment.files && alignment.files.length > 0) {
          prompt += `- **Files:** ${alignment.files.map((f: string) => `\`${f}\``).join(', ')}\n`;
        }
        prompt += `- **Resolution:** ${alignment.resolution}\n\n`;
      }
    }
    
    prompt += `## Diagnostic Approach\n\n`;
    
    prompt += `### Step 1: Understand What Went Wrong\n\n`;
    prompt += `Based on the reported issue, consider:\n`;
    prompt += `- What were you trying to do?\n`;
    prompt += `- What happened instead?\n`;
    prompt += `- What context was missing or misunderstood?\n\n`;
    
    prompt += `### Step 2: Check Codebase Context\n\n`;
    prompt += `**Read the knowledge base files for context:**\n`;
    prompt += `- \`.aspect/structure.md\` - Overall architecture\n`;
    prompt += `- \`.aspect/code.md\` - Symbols and relationships\n`;
    prompt += `- \`.aspect/flows.md\` - Execution paths and data flows\n`;
    prompt += `- \`.aspect/conventions.md\` - Coding patterns to follow\n`;
    prompt += `- \`ALIGNMENTS.json\` - Previous issues and fixes\n\n`;
    
    prompt += `### Step 3: Trace Data Flows\n\n`;
    prompt += `**For debugging, focus on data flow analysis:**\n`;
    prompt += `- Trace the data from input to output\n`;
    prompt += `- Check \`flows.md\` for entry points and integration points\n`;
    prompt += `- Verify data transformations at each step\n`;
    prompt += `- Look for where data might be lost, corrupted, or mishandled\n`;
    prompt += `- Check type conversions and serialization points\n\n`;
    
    prompt += `### Step 4: Run Actual Tests\n\n`;
    prompt += `**Verify your understanding with real tests:**\n`;
    prompt += `- Run existing tests to see what passes/fails\n`;
    prompt += `- Add targeted test cases for the specific issue\n`;
    prompt += `- Use console.log/print statements to trace execution\n`;
    prompt += `- Check actual runtime behavior, not just static analysis\n`;
    prompt += `- Verify fixes work before considering the issue resolved\n\n`;
    
    prompt += `### Step 5: Identify the Root Cause\n\n`;
    prompt += `Common mistakes and fixes:\n\n`;
    
    prompt += `**Pattern: Deleted or lost code**\n`;
    prompt += `- Use git to recover: \`git diff\`, \`git checkout -- <file>\`\n`;
    prompt += `- Check if code was moved elsewhere\n`;
    prompt += `- Restore from the complete implementation\n\n`;
    
    prompt += `**Pattern: Used deprecated/wrong API**\n`;
    prompt += `- Check \`conventions.md\` for correct patterns\n`;
    prompt += `- Look at similar working code in the codebase\n`;
    prompt += `- Verify imports match what's actually exported\n\n`;
    
    prompt += `**Pattern: Broke dependencies**\n`;
    prompt += `- Check \`structure.md\` for hub modules\n`;
    prompt += `- Verify all importers still work\n`;
    prompt += `- Run tests or type-check affected files\n\n`;
    
    prompt += `**Pattern: Data flow issue**\n`;
    prompt += `- Trace data through \`flows.md\` entry points\n`;
    prompt += `- Check transformations at each step\n`;
    prompt += `- Verify types match at integration boundaries\n`;
    prompt += `- Look for async/sync mismatches\n\n`;
    
    prompt += `**Pattern: Incomplete or truncated**\n`;
    prompt += `- You may have cut off mid-implementation\n`;
    prompt += `- Read the original file for complete context\n`;
    prompt += `- Ensure all functions/exports are preserved\n\n`;
    
    prompt += `### Step 6: Apply the Fix\n\n`;
    prompt += `1. **Restore any lost code** using git or backups\n`;
    prompt += `2. **Make minimal, targeted corrections**\n`;
    prompt += `3. **Run tests** to verify the fix works\n`;
    prompt += `4. **Trace data flows** to confirm correct behavior\n\n`;
    
    prompt += `## Output Format\n\n`;
    prompt += `Structure your response as:\n\n`;
    
    prompt += `### 1. Diagnosis\n`;
    prompt += `- What went wrong\n`;
    prompt += `- Root cause analysis\n`;
    prompt += `- Similar past issues (if found in ALIGNMENTS.json)\n\n`;
    
    prompt += `### 2. Recovery Steps\n`;
    prompt += `- Specific commands to run\n`;
    prompt += `- Files to check or restore\n`;
    prompt += `- Code changes needed\n\n`;
    
    prompt += `### 3. Verification\n`;
    prompt += `- Tests to run\n`;
    prompt += `- Expected vs actual behavior\n`;
    prompt += `- Data flow confirmation\n\n`;
    
    prompt += `---\n\n`;
    prompt += `**Remember:** Focus on understanding what went wrong through actual testing and data flow tracing. Use the KB files for context and check ALIGNMENTS.json for similar past issues.\n`;
    
    return prompt;
  }
}
