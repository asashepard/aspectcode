// src/panel/PanelProvider.ts
import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
// NOTE: ScoreEngine imports kept but not used - score calculation disabled for performance
// import { ScoreEngine, ScoreResult } from '../scoring/scoreEngine';
// import { defaultScoreConfig } from '../scoring/scoreConfig';
import { DependencyAnalyzer, DependencyLink } from './DependencyAnalyzer';
import { detectAssistants } from '../assistants/detection';

type Finding = { 
  id?: string;
  file: string; 
  rule: string; 
  message: string; 
  fixable: boolean;
  severity?: 'critical' | 'high' | 'medium' | 'low' | 'info';
  priority?: 'P0' | 'P1' | 'P2' | 'P3';
  locations?: any[];
};

type DevFinding = Finding & {
  id: string;
  severity: 'critical' | 'high' | 'medium' | 'low' | 'info';
  locations: any[];
};

type StateSnapshot = {
  busy: boolean;
  findings: Finding[];
  byRule: Record<string, number>;
  history: Array<{ ts: string; filesChanged: number; diffBytes: number }>;
  lastDiffMeta?: { files: number; hunks: number };
  totalFiles?: number;
  processingPhase?: string;
  progress?: number;
  score?: any;  // Score calculation disabled
};

type DependencyGraphData = {
  nodes: Array<{ id: string; label: string; type: 'hub' | 'file'; importance: number; file?: string }>;
  links: Array<{ source: string; target: string; strength: number }>;
};

export class AspectCodePanelProvider implements vscode.WebviewViewProvider {
  public static readonly viewId = 'aspectcode.panel';
  private _view?: vscode.WebviewView;
  private _autoProcessingStarted = false;
  private _cacheLoadedSuccessfully = false; // Skip auto-processing when cache was loaded
  // NOTE: ScoreEngine disabled for performance
  // private _scoreEngine: ScoreEngine;
  private _dependencyAnalyzer: DependencyAnalyzer;
  
  // Performance caching for fast file switching
  private _workspaceFilesCache: string[] | null = null;
  private _dependencyCache = new Map<string, any[]>();
  private _graphCache = new Map<string, DependencyGraphData>();
  private _cacheTimestamp = 0;
  private readonly _cacheTimeout = 30000; // 30 seconds
  private _fileChangeDebounceTimer: NodeJS.Timeout | null = null;
  private readonly _debounceDelay = 10; // Very fast response - 10ms to batch rapid switches only
  private _lastProcessedFile: string | null = null; // Track last processed file to avoid duplicates
  private _lastProcessedTime: number = 0; // Timestamp of last processing
  private _currentGraphCenterFile: string | null = null; // Track current center of focused graph
  private _centerFileUpdatedTime: number = 0; // Track when center was last updated by user action
  private _isProcessingNodeClick: boolean = false; // Flag to indicate node click is being processed
  private _cacheCleanupInterval: NodeJS.Timeout | null = null; // Periodic cache cleanup

  constructor(
    private readonly _context: vscode.ExtensionContext,
    private readonly _state: AspectCodeState,
    private readonly _outputChannel?: vscode.OutputChannel
  ) {
    // NOTE: ScoreEngine disabled for performance - score calculation removed
    this._dependencyAnalyzer = new DependencyAnalyzer();
    
    // When AspectCodeState changes, push a compact snapshot to the webview
    // NOTE: Score calculation removed for performance
    this._state.onDidChange((s) => {
      const byRule: Record<string, number> = {};
      (s.findings ?? []).forEach((f: any) => {
        const rule = f.code ?? f.ruleId ?? f.rule ?? 'unknown';
        byRule[rule] = (byRule[rule] || 0) + 1;
      });

      const totalFiles = this.estimateTotalFiles();

      // Map findings without score calculation for fast updates
      const findings = (s.findings ?? []).map((f: any) => ({
        id: f.id ?? f.violation_id ?? `finding-${Math.random()}`,
        file: this.parseFileFromFinding(f),
        rule: f.rule ?? f.code ?? f.ruleId ?? 'unknown',
        message: f.explain ?? f.message ?? f.title ?? '',
        fixable: !!f.fixable,
        severity: this.mapSeverity((f.severity as any) ?? 'warn'),
        priority: f.priority ?? 'P1',
        locations: f.span ? [f.span] : (f.locations || []),
      }));

      this._bridgeState = {
        busy: !!s.busy,
        findings: findings.map(f => ({
          ...f,
          span: this.parseSpanFromFinding(s.findings?.find((sf: any) => 
            (sf.id ?? sf.violation_id) === f.id))
        })),
        byRule,
        history: this._bridgeState.history,
        lastDiffMeta: this._bridgeState.lastDiffMeta,
        fixableRulesCount: this._state.getCapabilities()?.fixable_rules?.length ?? 0,
        lastAction: this._bridgeState.lastAction,
        totalFiles: totalFiles,
        processingPhase: this._bridgeState.processingPhase,
        progress: this._bridgeState.progress,
      };
      
      this.pushState();
      
      // Detect incremental updates and show toast notification
      const hasFilesChanged = s.lastValidate && (s.lastValidate as any).filesChanged;
      
      if (hasFilesChanged && (s.lastValidate as any).filesChanged >= 0) {
        // This was an incremental validation - show subtle notification
        this._outputChannel?.appendLine(`[IncrementalUpdate] Sending INCREMENTAL_UPDATE message: ${(s.lastValidate as any).filesChanged} files, ${s.lastValidate?.tookMs}ms`);
        this.post({
          type: 'INCREMENTAL_UPDATE',
          filesChanged: (s.lastValidate as any).filesChanged,
          duration: s.lastValidate?.tookMs || 0
        });
      }
      
      // Send dependency graph after state update (async)
      (async () => {
        try {
          await this.sendDependencyGraph();
        } catch (error) {
          console.error('[Aspect Code:panel] Error sending dependency graph:', error);
        }
      })();
    });

    // Set up periodic cache cleanup (every 60 seconds)
    this._cacheCleanupInterval = setInterval(() => {
      const now = Date.now();
      const cacheAge = now - this._cacheTimestamp;
      
      if (cacheAge > this._cacheTimeout) {
        const cacheSize = this._graphCache.size;
        if (cacheSize > 0) {
          this._graphCache.clear();
          this._dependencyCache.clear();
          this._workspaceFilesCache = null;
          this._cacheTimestamp = 0;
        }
      }
    }, 60000); // Every 60 seconds

    // Listen for active file changes to refresh dependency graph
    vscode.window.onDidChangeActiveTextEditor(async (editor) => {
      // Clear any pending debounce timer
      if (this._fileChangeDebounceTimer) {
        clearTimeout(this._fileChangeDebounceTimer);
      }
      
      // Only handle real files (not output channels, etc.)
      const activeFile = editor?.document.uri.scheme === 'file' 
        ? editor.document.fileName 
        : undefined;
      const now = Date.now();
      
      // Skip if currently processing a node click (let it finish first)
      if (this._isProcessingNodeClick) {
        return;
      }
      
      // Skip ONLY if it's the same file AND was processed very recently (within 100ms)
      if (activeFile && activeFile === this._lastProcessedFile && (now - this._lastProcessedTime) < 100) {
        return;
      }
      
      // Minimal debounce to batch rapid switches only
      this._fileChangeDebounceTimer = setTimeout(async () => {
        try {
          // Check if view is ready
          if (!this._view) {
            console.warn('[Dependency Graph] ⚠️ View not ready, skipping update');
            return;
          }
          
          // Notify webview of active file change for findings sorting
          if (activeFile) {
            this.post({
              type: 'ACTIVE_FILE_CHANGED',
              file: activeFile
            });
          }
          
          // Update the graph
          if (activeFile) {
            this._lastProcessedFile = activeFile;
            this._lastProcessedTime = Date.now();
            // Update center file tracking immediately to prevent race conditions
            this._currentGraphCenterFile = path.normalize(activeFile);
            this._centerFileUpdatedTime = Date.now();
            await this.sendFocusedDependencyGraph(activeFile);
          } else {
            this._lastProcessedFile = null;
            this._lastProcessedTime = Date.now();
            // No active file - prefer current center over best file
            if (this._currentGraphCenterFile && await this.isFileValid(this._currentGraphCenterFile)) {
              await this.sendFocusedDependencyGraph(this._currentGraphCenterFile);
            } else {
              // Invalid or no current center - clear it and pick a file to focus on
              this._currentGraphCenterFile = null;
              await this.sendFocusedOnBestFile();
            }
          }
        } catch (error) {
          console.error('[Dependency Graph] ✗ Error refreshing on editor change:', error);
          this._lastProcessedFile = null; // Reset on error to allow retry
          this._lastProcessedTime = 0;
          // Fallback to default behavior
          try {
            await this.sendDependencyGraph();
          } catch (fallbackError) {
            console.error('[Dependency Graph] ✗ Fallback also failed:', fallbackError);
          }
        }
      }, this._debounceDelay);
    });
  }

  // Keep using your existing state. If you don't have a compact snapshot, track one here:
  private _bridgeState: {
    busy: boolean;
    findings: DevFinding[];
    byRule: Record<string, number>;
    history: Array<{ ts: string; filesChanged: number; diffBytes: number }>;
    lastDiffMeta?: { files: number; hunks: number };
    fixableRulesCount?: number;
    lastAction?: string;
    totalFiles?: number;
    processingPhase?: string;
    progress?: number;
  } = { busy: false, findings: [], byRule: {}, history: [] };

  // (optional) helper to show the view from activate()
  reveal() { this._view?.show?.(true); }

  private mapSeverity(severity: string): 'critical' | 'high' | 'medium' | 'low' | 'info' {
    const severityMap: { [key: string]: 'critical' | 'high' | 'medium' | 'low' | 'info' } = {
      'error': 'critical',
      'warn': 'medium', 
      'warning': 'medium',
      'info': 'info',
      'high': 'high',
      'medium': 'medium',
      'low': 'low',
      'critical': 'critical'
    };
    return severityMap[severity?.toLowerCase()] || 'medium';
  }

  private estimateTotalFiles(): number {
    // Simple heuristic - count unique files from findings
    const uniqueFiles = new Set(this._bridgeState.findings.map(f => f.file));
    return Math.max(uniqueFiles.size, 1);
  }

  /**
   * Centralized view mode management
   * @param mode - 'focused' | 'overview' | 'auto'
   * @param trigger - 'user' | 'navigation' | 'node-click'
   * @param targetFile - file to focus on (if mode is 'focused')
   */
  private async sendDependencyGraph(forceOverview: boolean = false) {
    if (!this._view) return;
    
    // ALWAYS send focused graph - never show all nodes at once
    // Only use activeTextEditor if it's a real file (not output channel, etc.)
    const activeEditor = vscode.window.activeTextEditor;
    const activeFile = activeEditor?.document.uri.scheme === 'file' 
      ? activeEditor.document.fileName 
      : undefined;
    
    if (activeFile) {
      await this.sendFocusedDependencyGraph(activeFile);
    } else {
      // No active file - prefer current center over best file
      if (this._currentGraphCenterFile && await this.isFileValid(this._currentGraphCenterFile)) {
        await this.sendFocusedDependencyGraph(this._currentGraphCenterFile);
      } else {
        // Invalid or no current center - clear it and pick a file to focus on
        this._currentGraphCenterFile = null;
        await this.sendFocusedOnBestFile();
      }
    }
  }

  private async sendFocusedDependencyGraph(activeFile: string) {
    // Ensure view is ready
    if (!this._view) {
      console.error('[Dependency Graph] View not initialized, cannot send graph');
      return;
    }
    
    // Normalize file path to avoid mismatches
    const normalizedFile = path.normalize(activeFile);
    
    // Check cache first
    const now = Date.now();
    const cacheKey = `focused_${normalizedFile}`;
    
    if (this._graphCache.has(cacheKey) && (now - this._cacheTimestamp) < this._cacheTimeout) {
      const cachedGraph = this._graphCache.get(cacheKey)!;
      
      // Use consistent message type (UPPERCASE)
      try {
        this._view?.webview.postMessage({
          type: 'DEPENDENCY_GRAPH',
          graph: { ...cachedGraph, focusMode: true, centerFile: normalizedFile }
        });
        return;
      } catch (error) {
        console.warn(`[Dependency Graph] Failed to send cached graph, fetching fresh data:`, error);
        // Fall through to fetch fresh data
        this._graphCache.delete(cacheKey); // Clear bad cache
      }
    }
    
    // Send loading indicator to webview
    this._view?.webview.postMessage({
      type: 'graphLoading',
      file: normalizedFile
    });
    
    // Get all files in workspace (cached)
    let allFiles = this._workspaceFilesCache;
    if (!allFiles || (now - this._cacheTimestamp) > this._cacheTimeout) {
      allFiles = await this.discoverAllWorkspaceFiles();
      this._workspaceFilesCache = allFiles;
      this._cacheTimestamp = now;
    }
    
    // Ensure the active file is valid (with normalized path comparison)
    const normalizedAllFiles = allFiles.map(f => path.normalize(f));
    const fileIndex = normalizedAllFiles.findIndex(f => f === normalizedFile);
    
    if (fileIndex === -1) {
      console.warn(`[Dependency Graph] Active file not found in workspace: ${normalizedFile}`);
      console.warn(`[Dependency Graph] Workspace has ${allFiles.length} files. Rescanning...`);
      
      // Force rescan and try once more
      this._workspaceFilesCache = null;
      allFiles = await this.discoverAllWorkspaceFiles();
      this._workspaceFilesCache = allFiles;
      
      if (!allFiles.includes(normalizedFile)) {
        console.error(`[Dependency Graph] File still not found after rescan. Showing empty graph.`);
        // Send empty graph centered on this file anyway
        this._view?.webview.postMessage({
          type: 'dependencyGraph',
          data: {
            nodes: [{
              id: normalizedFile,
              label: path.basename(normalizedFile),
              type: 'hub',
              importance: 0,
              file: normalizedFile,
              violations: 0,
              highSeverity: 0,
              errors: 0,
              isActiveFile: true
            }],
            links: [],
            focusMode: true,
            centerFile: normalizedFile
          }
        });
        return;
      }
    }
    
    const actualFile = allFiles[fileIndex] || normalizedFile;

    // Get dependencies (cached)
    let allDependencies = this._dependencyCache.get('all');
    if (!allDependencies || (now - this._cacheTimestamp) > this._cacheTimeout) {
      allDependencies = await this._dependencyAnalyzer.analyzeDependencies(allFiles);
      this._dependencyCache.set('all', allDependencies);
    }
    
    // Filter to get only dependencies involving the active file (using actual file path)
    const relevantDependencies = allDependencies.filter(dep => 
      path.normalize(dep.source) === normalizedFile || path.normalize(dep.target) === normalizedFile
    );
    
    // Get all files involved in these dependencies
    const involvedFiles = new Set<string>([actualFile]);
    relevantDependencies.forEach(dep => {
      involvedFiles.add(dep.source);
      involvedFiles.add(dep.target);
    });
    
    const filesToAnalyze = Array.from(involvedFiles);
    
    // Create nodes
    const nodes = filesToAnalyze.map(file => {
      const fileFindings = this._bridgeState.findings.filter(f => f.file === file);
      const violationCount = fileFindings.length;
      const highSeverityCount = fileFindings.filter(f => f.severity === 'critical' || f.severity === 'high').length;
      const errorCount = fileFindings.filter(f => f.severity === 'critical').length;
      
      // Active file is always a hub, others based on findings
      const isActive = path.normalize(file) === normalizedFile;
      let nodeType: 'hub' | 'file' = isActive ? 'hub' : 'file';
      if (!isActive && (violationCount > 5 || highSeverityCount > 2)) {
        nodeType = 'hub';
      }
      
      return {
        id: file,
        label: file.split(/[/\\]/).pop() || file,
        type: nodeType,
        importance: violationCount,
        file,
        violations: violationCount,
        highSeverity: highSeverityCount,
        errors: errorCount,
        importanceScore: violationCount + (highSeverityCount * 2) + (errorCount * 3),
        ruleCategories: this.categorizeFindings(fileFindings),
        isActiveFile: isActive,
        // Add dependency metadata
        dependencyInfo: {
          imports: relevantDependencies.filter(d => d.source === file && d.type === 'import').length,
          exports: relevantDependencies.filter(d => d.target === file && d.type === 'import').length,
          calls: relevantDependencies.filter(d => d.source === file && d.type === 'call').length,
          isCircular: relevantDependencies.some(d => (d.source === file || d.target === file) && d.type === 'circular')
        }
      };
    });
    
    // Convert dependency links to graph links
    const links = relevantDependencies.map(dep => ({
      source: dep.source,
      target: dep.target,
      strength: dep.strength,
      type: dep.type,
      metadata: {
        symbols: dep.symbols,
        lines: dep.lines,
        bidirectional: dep.bidirectional
      }
    }));
    
    // Create the graph data
    const graphData = { 
      nodes, 
      links, 
      focusMode: true, 
      centerFile: actualFile,
      metadata: {
        totalDependencies: relevantDependencies.length,
        circularDependencies: relevantDependencies.filter(d => d.type === 'circular').length,
        analysisTimestamp: new Date().toISOString()
      }
    };
    
    // Cache the result for fast future access
    this._graphCache.set(cacheKey, graphData);
    
    // Ensure view is still ready before posting
    if (!this._view) {
      console.error('[Dependency Graph] View disappeared before sending');
      return;
    }
    
    // Send with retry logic
    const maxRetries = 2;
    let retries = 0;
    let sent = false;
    
    while (retries <= maxRetries && !sent) {
      const result = this.post({ 
        type: 'DEPENDENCY_GRAPH', 
        graph: graphData
      });
      
      sent = result !== false; // post returns false on error, otherwise Thenable or true
      
      if (!sent) {
        retries++;
        if (retries <= maxRetries) {
          console.warn(`[Dependency Graph] ⚠️ Send failed, retry ${retries}/${maxRetries}`);
          await new Promise(resolve => setTimeout(resolve, 50 * retries)); // Exponential backoff
        }
      }
    }
    
    if (sent) {
      // Track the current center file (only if not already updated by user action recently)
      const timeSinceUserUpdate = Date.now() - this._centerFileUpdatedTime;
      if (timeSinceUserUpdate > 1000) { // Only auto-update if no recent user action
        this._currentGraphCenterFile = path.normalize(actualFile);
      }
    } else {
      console.error(`[Dependency Graph] ✗ Failed to send graph after ${maxRetries} retries`);
      // Clear cache on failure to force fresh fetch next time
      this._graphCache.delete(cacheKey);
    }
  }

  private async isFileValid(filePath: string): Promise<boolean> {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.file(filePath));
      return true;
    } catch {
      return false;
    }
  }

  private async sendFocusedOnBestFile() {
    // Get all files in workspace
    const allFiles = await this.discoverAllWorkspaceFiles();
    
    if (allFiles.length === 0) {
      // No files at all - send empty graph
      this.post({ 
        type: 'DEPENDENCY_GRAPH', 
        graph: { nodes: [], links: [], focusMode: true, centerFile: null } 
      });
      return;
    }
    
    // Pick the best file to focus on (prioritize files with findings)
    const filesWithFindings = this._bridgeState.findings.map(f => f.file);
    const fileToFocus = filesWithFindings.length > 0 
      ? filesWithFindings[0]  // First file with findings
      : allFiles[0];           // Or just the first file
    
    await this.sendFocusedDependencyGraph(fileToFocus);
  }

  private async sendRandomDependencyGraph() {
    // Get ALL files in workspace
    const allFiles = await this.discoverAllWorkspaceFiles();
    const findingsFiles = new Set(this._bridgeState.findings.map(f => f.file));
    
    // Select files more inclusively
    let selectedFiles: string[] = [];
    
    // Include files with findings (up to 15)
    const filesWithFindings = Array.from(findingsFiles).slice(0, 15);
    selectedFiles.push(...filesWithFindings);
    
    // Fill remaining slots with any other files (to ensure we show files even without findings)
    const remainingSlots = 25 - selectedFiles.length;
    if (remainingSlots > 0) {
      const otherFiles = allFiles
        .filter(f => !selectedFiles.includes(f))
        .sort(() => Math.random() - 0.5)
        .slice(0, remainingSlots);
      selectedFiles.push(...otherFiles);
    }
    
    if (selectedFiles.length === 0) {
      this.post({ type: 'DEPENDENCY_GRAPH', graph: { nodes: [], links: [] } });
      return;
    }
    
    // Analyze real dependencies among selected files
    const allDependencies = await this._dependencyAnalyzer.analyzeDependencies(selectedFiles);
    
    // Create nodes for ALL selected files (even those without dependencies)
    const nodes = selectedFiles.map(file => {
      const fileFindings = this._bridgeState.findings.filter(f => f.file === file);
      const violationCount = fileFindings.length;
      const highSeverityCount = fileFindings.filter(f => f.severity === 'critical' || f.severity === 'high').length;
      const errorCount = fileFindings.filter(f => f.severity === 'critical').length;
      
      // Calculate dependency metrics for this file
      const incomingDeps = allDependencies.filter(d => d.target === file);
      const outgoingDeps = allDependencies.filter(d => d.source === file);
      const totalDeps = incomingDeps.length + outgoingDeps.length;
      
      let nodeType: 'hub' | 'file' = 'file';
      if (violationCount > 8 || highSeverityCount > 3 || this.isKeyArchitecturalFile(file) || totalDeps > 4) {
        nodeType = 'hub';
      }
      
      return {
        id: file,
        label: file.split(/[/\\]/).pop() || file,
        type: nodeType,
        importance: violationCount,
        file,
        violations: violationCount,
        highSeverity: highSeverityCount,
        errors: errorCount,
        importanceScore: violationCount + (highSeverityCount * 2) + (errorCount * 3) + (totalDeps * 0.5),
        ruleCategories: this.categorizeFindings(fileFindings),
        isActiveFile: false,
        dependencyInfo: {
          imports: outgoingDeps.filter(d => d.type === 'import').length,
          exports: incomingDeps.filter(d => d.type === 'import').length,
          calls: outgoingDeps.filter(d => d.type === 'call').length,
          isCircular: [...incomingDeps, ...outgoingDeps].some(d => d.type === 'circular')
        }
      };
    });
    
    // Convert dependency links to graph links
    const links = allDependencies.map(dep => ({
      source: dep.source,
      target: dep.target,
      strength: dep.strength,
      type: dep.type,
      metadata: {
        symbols: dep.symbols,
        lines: dep.lines,
        bidirectional: dep.bidirectional
      }
    }));
    
    this.post({ 
      type: 'DEPENDENCY_GRAPH', 
      graph: { 
        nodes, 
        links, 
        focusMode: false, 
        centerFile: null,
        metadata: {
          totalDependencies: allDependencies.length,
          circularDependencies: allDependencies.filter(d => d.type === 'circular').length,
          analysisTimestamp: new Date().toISOString()
        }
      } 
    });
  }
  
  private categorizeFindings(findings: Finding[]): Record<string, number> {
    const categories: Record<string, number> = {};
    findings.forEach(finding => {
      const category = finding.rule.split('.')[0] || 'other';
      categories[category] = (categories[category] || 0) + 1;
    });
    return categories;
  }
  
  private extractReferencedFile(finding: Finding, files: string[]): string | null {
    // Enhanced pattern matching for different import styles
    const patterns = [
      /import.+?['"]([^'"]+)['"]/i,
      /from\s+['"]([^'"]+)['"]/i,
      /requires?\s*\(\s*['"]([^'"]+)['"]\s*\)/i,
      /includes?\s*['"]([^'"]+)['"]/i
    ];
    
    for (const pattern of patterns) {
      const match = finding.message.match(pattern);
      if (match) {
        const moduleName = match[1];
        const targetFile = files.find(f => 
          f.includes(moduleName) || 
          f.endsWith(moduleName + '.py') || 
          f.endsWith(moduleName + '.ts') ||
          f.endsWith(moduleName + '.js') ||
          f.split(/[/\\]/).pop()?.startsWith(moduleName)
        );
        if (targetFile) return targetFile;
      }
    }
    return null;
  }
  
  private addOrUpdateLink(links: any[], source: string, target: string, strength: number, type: string) {
    const existing = links.find(l => 
      (l.source === source && l.target === target) || 
      (l.source === target && l.target === source)
    );
    
    if (existing) {
      existing.strength = Math.min(1.0, existing.strength + strength * 0.5);
    } else {
      links.push({ source, target, strength: Math.max(0.1, Math.min(1.0, strength)), type });
    }
  }
  
  private calculateFileSimilarity(file1: string, file2: string): number {
    const findings1 = this._bridgeState.findings.filter(f => f.file === file1);
    const findings2 = this._bridgeState.findings.filter(f => f.file === file2);
    
    const rules1 = new Set(findings1.map(f => f.rule));
    const rules2 = new Set(findings2.map(f => f.rule));
    
    const intersection = new Set([...rules1].filter(x => rules2.has(x)));
    const union = new Set([...rules1, ...rules2]);
    
    return union.size > 0 ? intersection.size / union.size : 0;
  }
  
  private calculateDirectorySimilarity(file1: string, file2: string): number {
    const dir1 = file1.split(/[/\\]/).slice(0, -1);
    const dir2 = file2.split(/[/\\]/).slice(0, -1);
    
    let commonDepth = 0;
    for (let i = 0; i < Math.min(dir1.length, dir2.length); i++) {
      if (dir1[i] === dir2[i]) commonDepth++;
      else break;
    }
    
    const maxDepth = Math.max(dir1.length, dir2.length);
    return maxDepth > 0 ? commonDepth / maxDepth : 0;
  }
  
  private async discoverAllWorkspaceFiles(): Promise<string[]> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      return [];
    }
    
    const allFiles: string[] = [];
    
    // Common source code file patterns
    const patterns = [
      '**/*.py',
      '**/*.ts', '**/*.tsx',
      '**/*.js', '**/*.jsx', '**/*.mjs', '**/*.cjs',
      '**/*.java',
      '**/*.cpp', '**/*.c', '**/*.hpp', '**/*.h',
      '**/*.cs',
      '**/*.go',
      '**/*.rs',
      '**/*.rb',
      '**/*.php'
    ];
    
    for (const pattern of patterns) {
      try {
        const files = await vscode.workspace.findFiles(
          pattern,
          '**/node_modules/**,**/.git/**,**/__pycache__/**,**/build/**,**/dist/**,**/target/**,**/e2e/**,**/playwright/**,**/cypress/**,**/.venv/**,**/venv/**',
          300 // Increased from 100 to discover more files
        );
        
        for (const file of files) {
          const filePath = file.fsPath;
          if (!allFiles.includes(filePath)) {
            allFiles.push(filePath);
          }
        }
      } catch (error) {
        console.warn('Error finding files with pattern:', pattern, error);
      }
    }
    
    return allFiles;
  }
  
  private isKeyArchitecturalFile(filePath: string): boolean {
    const fileName = filePath.split(/[/\\]/).pop()?.toLowerCase() || '';
    const directoryPath = filePath.toLowerCase();
    
    // Check for key architectural files
    const keyFiles = [
      'main.py', 'app.py', '__init__.py',
      'index.ts', 'main.ts', 'app.ts',
      'index.js', 'main.js', 'app.js',
      'package.json', 'tsconfig.json', 'pyproject.toml',
      'requirements.txt', 'cargo.toml', 'pom.xml',
      'dockerfile', 'readme.md'
    ];
    
    // Check for important directories
    const keyDirectoryParts = [
      'src', 'lib', 'core', 'api', 'server', 'client',
      'components', 'services', 'utils', 'common'
    ];
    
    return keyFiles.includes(fileName) || 
           keyDirectoryParts.some(part => directoryPath.includes('/' + part + '/') || directoryPath.includes('\\' + part + '\\'));
  }
  
  private calculateArchitecturalImportance(filePath: string): number {
    let score = 0;
    const fileName = filePath.split(/[/\\]/).pop()?.toLowerCase() || '';
    const directoryPath = filePath.toLowerCase();
    
    // Main/entry files
    if (['main.py', 'app.py', 'index.ts', 'main.ts', 'index.js', 'main.js'].includes(fileName)) {
      score += 5;
    }
    
    // Configuration files
    if (['package.json', 'tsconfig.json', 'pyproject.toml', 'requirements.txt'].includes(fileName)) {
      score += 3;
    }
    
    // Core directories
    if (directoryPath.includes('/src/') || directoryPath.includes('\\src\\')) {
      score += 2;
    }
    
    // Init files (often architectural)
    if (fileName === '__init__.py') {
      score += 1;
    }
    
    return score;
  }

  resolveWebviewView(view: vscode.WebviewView) {
    this._view = view;
    view.webview.options = { enableScripts: true };
    view.webview.html = this.getHtml();
    
    // Reset auto-processing flag when webview is resolved/recreated
    this._autoProcessingStarted = false;
    
    // Send initial graph after view is ready
    setTimeout(async () => {
      await this.sendDependencyGraph();
    }, 100);

    // Enhanced message handlers for new UI
    view.webview.onDidReceiveMessage(async (msg: any) => {
      switch (msg?.type) {
        case 'PANEL_READY':
          // Auto-start processing when panel first loads, unless cache was already loaded
          if (!this._autoProcessingStarted && !this._cacheLoadedSuccessfully) {
            this._autoProcessingStarted = true;
            // Send message to frontend to start automatic processing with UI
            this.post({ type: 'START_AUTOMATIC_PROCESSING' });
          } else if (this._cacheLoadedSuccessfully) {
            // Cache was loaded - just update the score display without running INDEX/VALIDATE
            this._outputChannel?.appendLine('[PanelProvider] Cache already loaded, skipping automatic processing');
          }
          // Send state with workspace root without modifying the original state
          const webviewState = {
            ...this._bridgeState,
            workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ''
          };
          this.post({ type: 'STATE_UPDATE', state: webviewState });
          
          // Send current active file for findings sorting (only real files)
          const activeEditor = vscode.window.activeTextEditor;
          const activeFile = activeEditor?.document.uri.scheme === 'file' 
            ? activeEditor.document.fileName 
            : undefined;
          if (activeFile) {
            this.post({ type: 'ACTIVE_FILE_CHANGED', file: activeFile });
          }
          
          // Check if any instruction files exist
          const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
          if (workspaceRoot) {
            const detected = await detectAssistants(workspaceRoot);
            const hasInstructionFiles = detected.size > 0;
            this.post({ type: 'INSTRUCTION_FILES_STATUS', hasFiles: hasInstructionFiles });
            
            // TEMPORARILY DISABLED: Check if ALIGNMENTS.json exists to show align button
            // const hasAlignmentsFile = await alignmentsFileExists(workspaceRoot);
            // this.post({ type: 'ALIGNMENTS_FILE_STATUS', hasFile: hasAlignmentsFile });
          }
          break;

        case 'REQUEST_DEPENDENCY_GRAPH':
          // Legacy handler - default to focused mode for compatibility
          const currentActiveEditor = vscode.window.activeTextEditor;
          const currentActiveFile = currentActiveEditor?.document.uri.scheme === 'file'
            ? currentActiveEditor.document.fileName
            : undefined;
          if (currentActiveFile) {
            await this.sendFocusedDependencyGraph(currentActiveFile);
          } else {
            // No active file - prefer current center over best file
            if (this._currentGraphCenterFile && await this.isFileValid(this._currentGraphCenterFile)) {
              await this.sendFocusedDependencyGraph(this._currentGraphCenterFile);
            } else {
              // Invalid or no current center - clear it and pick a file to focus on
              this._currentGraphCenterFile = null;
              await this.sendFocusedOnBestFile();
            }
          }
          break;

        case 'REQUEST_STATE':
          this.post({ type: 'STATE_UPDATE', state: this._bridgeState });
          break;

        case 'RUN_FLOW':
          await this.runFlow(Array.isArray(msg.steps) ? msg.steps : []);
          break;

        case 'CAPTURE_SNAPSHOT':
          this.post({ type: 'SNAPSHOT_RESULT', snapshot: this.captureSnapshot() });
          break;

        case 'OPEN_FINDING': {
          const file = String(msg.file || '');
          const line = Number.isFinite(msg.line) ? Number(msg.line) : 1;
          const column = Number.isFinite(msg.column) ? Number(msg.column) : 1;

          // Create proper URI using VS Code's URI utilities
          const uri = vscode.Uri.file(file);
          
          // Create a Finding object that matches the command signature
          const finding = {
            file_path: file,
            uri: uri.toString(),
            range: {
              startLine: line,
              startCol: column,
              endLine: line,
              endCol: column
            },
            rule_id: 'panel-click'
          };

          // Delegate to the command
          await vscode.commands.executeCommand('aspectcode.openFinding', finding);
          break;
        }

        case 'NODE_CLICK_FOCUS': {
          const file = String(msg.file || '');
          if (file) {
            // Set flag to prevent editor change handler interference
            this._isProcessingNodeClick = true;
            
            try {
              // Clear any pending editor change debounce to avoid duplicate updates
              if (this._fileChangeDebounceTimer) {
                clearTimeout(this._fileChangeDebounceTimer);
                this._fileChangeDebounceTimer = null;
              }
              
              const normalizedFile = path.normalize(file);
              
              // Clear cache for this file to force fresh data
              const cacheKey = `focused_${normalizedFile}`;
              if (this._graphCache.has(cacheKey)) {
                this._graphCache.delete(cacheKey);
              }
              
              // Update tracking
              this._lastProcessedFile = normalizedFile;
              this._lastProcessedTime = Date.now();
              // Update center file tracking for node clicks
              this._currentGraphCenterFile = normalizedFile;
              this._centerFileUpdatedTime = Date.now();
              
              // Node clicks always focus on the specific file (good UX) - force fresh data
              await this.sendFocusedDependencyGraph(file);
            } catch (error) {
              console.error(`[NODE_CLICK_FOCUS] Error processing click:`, error);
              // Reset tracking on error to allow retry
              this._lastProcessedFile = null;
              this._lastProcessedTime = 0;
            } finally {
              // Always clear the flag after a short delay
              setTimeout(() => {
                this._isProcessingNodeClick = false;
              }, 200); // 200ms grace period
            }
          }
          break;
        }

        case 'FIX_FINDING': {
          // Auto-Fix feature temporarily disabled
          // Support both single ID and array of IDs
          // const id = msg?.id as string | undefined;
          // const ids = msg?.ids as string[] | undefined;
          // 
          // if (ids && ids.length > 0) {
          //   await vscode.commands.executeCommand('aspectcode.previewAutofix', ids);
          // } else if (id) {
          //   await vscode.commands.executeCommand('aspectcode.previewAutofix', [id]);
          // }
          break;
        }

        case 'FIX_SAFE':
          // Auto-Fix feature temporarily disabled
          // await vscode.commands.executeCommand('aspectcode.applyAutofix');
          break;

        case 'COMMAND':
          if (msg?.command) {
            await vscode.commands.executeCommand(msg.command);
          }
          break;

        case 'REQUEST_OVERVIEW_GRAPH':
          // 3D graph disabled - code kept for future use
          // await this.sendRandomDependencyGraph();
          break;

        case 'REQUEST_FOCUSED_GRAPH':
          // Always send focused data for 2D graph
          const activeEditorFocused = vscode.window.activeTextEditor;
          const activeFileFocused = activeEditorFocused?.document.uri.scheme === 'file'
            ? activeEditorFocused.document.fileName
            : undefined;
          
          if (activeFileFocused) {
            // Use the actual active file
            await this.sendFocusedDependencyGraph(activeFileFocused);
          } else {
            // No active file - check if we recently updated center due to user action
            const timeSinceLastUpdate = Date.now() - this._centerFileUpdatedTime;
            const recentUserUpdate = timeSinceLastUpdate < 500; // 500ms grace period
            
            if (this._currentGraphCenterFile && await this.isFileValid(this._currentGraphCenterFile) && recentUserUpdate) {
              // Keep the current center file - user recently selected it
              await this.sendFocusedDependencyGraph(this._currentGraphCenterFile);
            } else if (this._currentGraphCenterFile && await this.isFileValid(this._currentGraphCenterFile)) {
              // Keep the current center file - older but still valid
              await this.sendFocusedDependencyGraph(this._currentGraphCenterFile);
            } else {
              // Invalid or no current center - clear it and fall back to best file
              this._currentGraphCenterFile = null;
              await this.sendFocusedOnBestFile();
            }
          }
          break;

        case 'AUTO_FIX_SAFE':
          // Auto-Fix feature temporarily disabled
          // try {
          //   await vscode.commands.executeCommand('aspectcode.autoFixSafe');
          // } finally {
          //   // Send message back to webview to re-enable the button regardless of outcome
          //   this._view?.webview.postMessage({
          //     type: 'AUTO_FIX_SAFE_COMPLETE',
          //     payload: {}
          //   });
          // }
          break;

        case 'EXPLAIN_FILE': {
          await vscode.commands.executeCommand('aspectcode.explainFile');
          break;
        }

        case 'PROPOSE_FIXES': {
          await vscode.commands.executeCommand('aspectcode.proposeFixes');
          break;
        }

        case 'ALIGN_ISSUE': {
          await vscode.commands.executeCommand('aspectcode.alignIssue');
          break;
        }

        case 'GENERATE_AUTO_FIX_PROMPT': {
          // Auto-Fix feature temporarily disabled
          // const findings = msg.payload?.findings || [];
          // await vscode.commands.executeCommand('aspectcode.generateAutoFixPrompt', findings);
          break;
        }
        
        case 'DEBUG_MESSAGE': {
          // Log webview debug messages to extension output channel
          this._outputChannel?.appendLine(`🌐 [WEBVIEW DEBUG] ${msg.message}`);
          break;
        }
      }
    });
  }

  // === Called by dev commands (from activate) ===
  public simulateFindings() {
    this._bridgeState.findings = [
      { id: 'demo-1', file: 'samples/foo.py', rule: 'imports/no-cycles', message: 'Demo finding', fixable: true, severity: 'high', locations: [] },
      { id: 'demo-2', file: 'samples/bar.py', rule: 'style/docstring-missing', message: 'Add docstring', fixable: false, severity: 'medium', locations: [] },
    ];
    this._bridgeState.byRule = { 'imports/no-cycles': 1, 'style/docstring-missing': 1 };
    this.pushState();
  }

  public resetBridgeState() {
    this._bridgeState = { busy: false, findings: [], byRule: {}, history: [], lastDiffMeta: undefined };
    this.pushState();
  }

  /**
   * Mark that cache was successfully loaded on startup.
   * When set, the panel will skip automatic INDEX/VALIDATE processing.
   */
  public setCacheLoaded(loaded: boolean) {
    this._cacheLoadedSuccessfully = loaded;
    if (loaded) {
      // Also mark auto-processing as done so we don't run it later
      this._autoProcessingStarted = true;
    }
  }

  public __setBridgeStateFromSnapshot(snap: any) {
    this._bridgeState.findings = new Array(snap.renderedFindings || 0)
      .fill(0)
      .map((_, i) => ({
        id: `restored-${i}`,
        file: `(restored-${i})`,
        rule: 'restored',
        message: 'restored',
        fixable: false,
        severity: 'medium' as const,
        locations: []
      }));
    this._bridgeState.history = snap.history || [];
    this._bridgeState.lastDiffMeta = snap.lastDiffMeta;
    this.pushState();
  }

  public captureSnapshot() {
    return {
      renderedFindings: this._bridgeState.findings.length,
      filters: {}, // fill with your real filter UI state if you have it
      history: this._bridgeState.history,
      lastDiffMeta: this._bridgeState.lastDiffMeta
    };
  }

  public async runFlow(steps: string[]) {
    try {
      this._bridgeState.busy = true;
      this._bridgeState.progress = 0;
      this.pushState();
      
      for (let i = 0; i < steps.length; i++) {
        const step = steps[i];
        const progress = Math.round((i / steps.length) * 100);
        
        this._bridgeState.processingPhase = step;
        this._bridgeState.progress = progress;
        this.post({ type: 'FLOW_PROGRESS', phase: step });

        if (step === 'index') {
          try {
            await vscode.commands.executeCommand('aspectcode.index');
          } catch (error) {
            console.error('[Aspect Code] index step failed:', error);
            throw error;
          }
        }

        else if (step === 'validate') {
          try {
            await vscode.commands.executeCommand('aspectcode.examine');
          } catch (error) {
            console.error('[Aspect Code] validate step failed:', error);
            throw error;
          }
        }

      else if (step === 'preview_fixes') {
        this._bridgeState.lastDiffMeta = { files: 1, hunks: 2 };
        this.pushState();
      }

      else if (step === 'apply') {
        await vscode.commands.executeCommand('aspectcode.autofixSelected');
      }

      else if (step === 'revalidate') {
        await vscode.commands.executeCommand('aspectcode.validateWorkspaceDiff');
      }
    }
    
    this._bridgeState.history.push({
      ts: new Date().toISOString(),
      filesChanged: 1,
      diffBytes: 120
    });
    
    } catch (error) {
      console.error('[Aspect Code:panel] Flow execution failed:', error);
      // Don't re-throw, just log the error
    } finally {
      // Always ensure clean state on completion or error
      this._bridgeState.busy = false;
      this._bridgeState.processingPhase = undefined;
      this._bridgeState.progress = 100;
      this.pushState();
    }
    
    return this.captureSnapshot();
  }

  // === helpers ===
  private post(message: any): boolean | Thenable<boolean> {
    if (!this._view) {
      // STATE_UPDATE is routine - silently skip when view not ready (next update will sync)
      // Only log unexpected message types that might indicate a problem
      if (message.type !== 'STATE_UPDATE') {
        console.warn('[Post] View not ready, skipping message:', message.type);
      }
      return false;
    }
    try {
      return this._view.webview.postMessage(message);
    } catch (error) {
      console.error('[Post] Error posting message:', error);
      return false;
    }
  }
  private pushState() { 
    const webviewState = {
      ...this._bridgeState,
      workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ''
    };
    this.post({ type: 'STATE_UPDATE', state: webviewState }); 
  }

  /**
   * Parse file path from either structured format or location strings.
   */
   private parseFileFromFinding(f: any): string {
    const directFile = f.file ?? f.filePath ?? f.file_path;
    if (directFile) {
      return directFile;
    }

    if (f.locations && Array.isArray(f.locations) && f.locations.length > 0) {
      const location = f.locations[0];
      if (typeof location === 'string') {
        const match = location.match(/^(.+):(\d+):(\d+)-(\d+):(\d+)$/);
        if (match) {
          return match[1];
        }
      }
    }

    return '';
  }

  /**
   * Parse span information from either structured span or location strings.
   */
  private parseSpanFromFinding(f: any): any {
    if (f.span && f.span.start && f.span.end) {
      return {
        start: { line: f.span.start.line, column: f.span.start.column },
        end: { line: f.span.end.line, column: f.span.end.column }
      };
    }

    if (f.locations && Array.isArray(f.locations) && f.locations.length > 0) {
      const location = f.locations[0];
      if (typeof location === 'string') {
        const match = location.match(/:(\d+):(\d+)-(\d+):(\d+)$/);
        if (match) {
          const [, startLine, startCol, endLine, endCol] = match;
          return {
            start: { line: parseInt(startLine, 10), column: parseInt(startCol, 10) },
            end: { line: parseInt(endLine, 10), column: parseInt(endCol, 10) }
          };
        }
      }
    }

    return undefined;
  }

  getHtml() {
    // Compact, one-line UI with dropdown findings
    const timestamp = Date.now(); // Cache busting for webview refresh
    return `<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="cache-control" content="no-cache, no-store, must-revalidate">
    <meta name="pragma" content="no-cache">
    <meta name="expires" content="0">
    <title>Aspect Code - ${timestamp}</title>
    <style>
        body {
            margin: 0;
            padding: 0;
            font-family: var(--vscode-font-family);
            color: var(--vscode-foreground);
            background: var(--vscode-editor-background);
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        
        .main-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        /* Compact header bar */
        .header-bar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 11px 12px 3px 12px;
            background: var(--vscode-sideBar-background);
            border-bottom: none;
            flex-shrink: 0;
        }
        
        .header-bar.score-hidden {
            padding-top: 0px;
        }
        
        .controls-container {
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        /* Score display */
        .score-container {
            position: relative;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
            min-width: 80px;
        }
        
        .score-number {
            font-size: 28px;
            font-weight: 700;
            color: var(--vscode-charts-orange);
            min-width: 60px;
            text-align: center;
            font-family: 'Segoe UI', monospace;
            line-height: 1;
        }
        
        .score-label {
            font-size: 9px;
            font-weight: 500;
            color: var(--vscode-descriptionForeground);
            text-align: center;
            margin-top: -2px;
            letter-spacing: 0.5px;
        }
        
        .score-details {
            font-size: 9px;
            opacity: 0.6;
            text-align: center;
            line-height: 1.2;
        }
        
        /* Loading spinner */
        .loading-spinner {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            display: none;
            align-items: center;
            justify-content: center;
        }
        
        .loading-spinner svg {
            animation: rotate 2s linear infinite;
        }
        
        @keyframes rotate {
            from { transform: rotate(0deg); }
            to { transform: rotate(360deg); }
        }
        
        /* Action buttons */
        .action-buttons {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            align-items: center;
        }
        
        .action-button {
            background: none;
            border: 1px solid transparent;
            border-radius: 4px;
            color: var(--vscode-input-foreground);
            cursor: pointer;
            padding: 6px 10px;
            height: 28px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 500;
            flex: 1;
            min-width: 80px;
        }
        
        .action-button:hover:not(:disabled) {
            background: var(--vscode-list-hoverBackground);
            border-color: transparent;
        }
        
        .action-button:active:not(:disabled) {
            background: var(--vscode-button-background);
            opacity: 0.8;
        }
        
        .action-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        
        .action-icon {
            fill: none;
            stroke: currentColor;
            width: 14px;
            height: 14px;
            flex-shrink: 0;
        }
        
        .action-text {
            font-size: 11px;
            font-weight: 500;
            white-space: nowrap;
        }
        
        .action-button:disabled .action-icon {
            opacity: 0.7;
        }
        
        .action-button:disabled .action-text {
            opacity: 0.7;
        }

        .action-button.icon-only {
            flex: 0;
            min-width: auto;
            padding: 6px 8px;
        }
        
        /* Score improvement badge on Auto-Fix button */
        .improvement-badge {
            position: absolute;
            top: -6px;
            right: -6px;
            background: var(--vscode-charts-green);
            color: var(--vscode-editor-background);
            font-size: 9px;
            font-weight: 700;
            padding: 2px 5px;
            border-radius: 8px;
            min-width: 20px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.3);
        }
        
        #auto-fix-safe-button {
            position: relative;
        }
        
        /* View container */
        .view-container {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .view-toggle {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 4px 12px 6px 12px;
            background: var(--vscode-sideBar-background);
            flex-shrink: 0;
        }
        
        .view-toggle-btn {
            background: none;
            border: none;
            color: var(--vscode-charts-orange);
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 4px;
            font-size: 13px;
            font-weight: 500;
            padding: 4px 8px;
            border-radius: 4px;
            transition: all 0.2s ease;
            font-family: var(--vscode-font-family);
        }

        .view-toggle-btn:hover {
            background: var(--vscode-toolbar-hoverBackground);
        }

        .view-toggle-count {
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
            font-weight: 400;
        }

        /* Settings menu styles (now in view toggle) */
        .graph-settings-container {
            position: relative;
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 2px;
        }
        
        /* Generate AI Instructions button - attention-grabbing */
        .generate-instructions-btn {
            background: var(--vscode-charts-orange);
            border: none;
            border-radius: 4px;
            color: #000;
            cursor: pointer;
            padding: 3px 6px;
            height: 22px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
            font-weight: 600;
            animation: pulse-attention 1.5s ease-in-out infinite;
            box-shadow: 0 0 8px var(--vscode-charts-orange);
        }
        
        .generate-instructions-btn:hover {
            animation: none;
            background: var(--vscode-charts-yellow);
            box-shadow: 0 0 12px var(--vscode-charts-yellow);
        }
        
        .generate-instructions-btn .action-icon {
            width: 12px;
            height: 12px;
            stroke: #000;
        }
        
        @keyframes pulse-attention {
            0%, 100% {
                transform: scale(1);
                box-shadow: 0 0 8px var(--vscode-charts-orange);
            }
            50% {
                transform: scale(1.08);
                box-shadow: 0 0 16px var(--vscode-charts-orange), 0 0 24px rgba(255, 140, 0, 0.4);
            }
        }
        
        .graph-type-select {
            background: var(--vscode-dropdown-background);
            border: 1px solid var(--vscode-dropdown-border);
            border-radius: 4px;
            color: var(--vscode-dropdown-foreground);
            font-size: 12px;
            padding: 4px 6px;
            cursor: pointer;
            min-width: 90px;
        }
        
        .graph-type-select:hover {
            background: var(--vscode-dropdown-background);
            border-color: var(--vscode-focusBorder);
        }
        
        .settings-toggle {
            background: none;
            border: 1px solid transparent;
            border-radius: 4px;
            color: var(--vscode-input-foreground);
            cursor: pointer;
            padding: 4px 8px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 6px;
            font-size: 11px;
            font-weight: 500;
            min-width: 24px;
        }
        
        .settings-toggle:hover {
            background: var(--vscode-list-hoverBackground);
            border-color: transparent;
        }
        
        .validation-spinner {
            display: none;
            align-items: center;
            justify-content: center;
            padding: 4px;
            opacity: 0.8;
        }
        
        .validation-spinner.active {
            display: flex;
        }
        
        .settings-menu {
            position: absolute;
            top: 100%;
            right: 0;
            background: var(--vscode-menu-background);
            border: 1px solid var(--vscode-menu-border);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 1000;
            min-width: 200px;
            padding: 8px;
            margin-top: 4px;
        }
        
        .settings-menu.hidden {
            display: none;
        }
        
        .settings-section {
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px solid var(--vscode-panel-border);
        }
        
        .settings-section:last-child {
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }
        
        .settings-section-title {
            display: block;
            color: var(--vscode-foreground);
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .settings-group {
            margin-bottom: 12px;
        }
        
        .settings-group:last-child {
            margin-bottom: 0;
        }
        
        .settings-label {
            display: block;
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .settings-select {
            width: 100%;
            background: var(--vscode-dropdown-background);
            border: 1px solid var(--vscode-dropdown-border);
            border-radius: 3px;
            color: var(--vscode-dropdown-foreground);
            font-size: 12px;
            padding: 4px 8px;
        }
        
        .settings-checkbox {
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--vscode-foreground);
            font-size: 12px;
            margin: 4px 0;
            cursor: pointer;
        }
        
        .settings-checkbox input[type="checkbox"] {
            margin: 0;
        }
        
        .view-content {
            flex: 1;
            display: none;
            flex-direction: column;
            overflow: hidden;
            background: var(--vscode-editor-background);
        }
        
        .view-content.active {
            display: flex;
        }

        /* Graph view content */
        .graph-view-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding: 0;
            margin: 0;
            position: relative; /* For absolute positioning of tooltips */
        }

        /* Findings view content */
        .findings-view-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        /* Filter controls */
        .filter-bar {
            padding: 8px 12px;
            background: var(--vscode-editor-background);
            border-bottom: 1px solid var(--vscode-panel-border);
            display: flex;
            gap: 8px;
            align-items: center;
        }
        
        .filter-label {
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            min-width: 40px;
        }
        
        .filter-select {
            flex: 1;
            padding: 4px 8px;
            border: 1px solid var(--vscode-input-border);
            border-radius: 3px;
            background: var(--vscode-input-background);
            color: var(--vscode-input-foreground);
            font-family: var(--vscode-font-family);
            font-size: 12px;
        }
        
        .filter-select:focus {
            outline: none;
            border-color: var(--vscode-focusBorder);
        }
        
        /* Findings list */
        .findings-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px 12px;
        }
        
        .finding-item {
            display: flex;
            align-items: flex-start;
            gap: 6px;
            padding: 8px 12px;
            border-radius: 4px;
            margin-bottom: 2px;
            cursor: pointer;
            transition: background-color 0.1s;
            min-height: 36px;
            max-width: 100%;
        }
        
        .finding-item.current-file {
            background: rgba(255, 140, 0, 0.25);
            border-left: 3px solid rgba(255, 140, 0, 0.8);
            padding-left: 9px;
        }
        
        .finding-item.current-file:hover {
            background: rgba(255, 140, 0, 0.35);
        }
        
        .finding-count {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-width: 20px;
            height: 18px;
            padding: 0 6px;
            background: var(--vscode-badge-background);
            color: var(--vscode-badge-foreground);
            border-radius: 9px;
            font-size: 11px;
            font-weight: 600;
            margin-left: 6px;
        }
        
        .finding-item.compact {
            gap: 6px;
            padding: 3px 8px;
            min-height: 24px;
        }
        
        .finding-item:hover {
            background: var(--vscode-list-hoverBackground);
        }
        
        .finding-item.current-file:hover {
            background: rgba(255, 140, 0, 0.35);
        }
        
        .finding-content {
            flex: 1;
            min-width: 0;
        }
        
        .finding-content.with-button {
            max-width: calc(100% - 60px); /* Reserve space for button */
        }
        
        .finding-message {
            color: var(--vscode-foreground);
            font-size: 13px;
            line-height: 1.3;
            margin-bottom: 2px;
            word-wrap: break-word;
            overflow-wrap: break-word;
            white-space: normal;
            width: 100%;
        }
        
        .finding-file {
            color: var(--vscode-descriptionForeground);
            font-size: 11px;
            font-family: var(--vscode-editor-font-family);
            opacity: 0.8;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            width: 100%;
        }
        
        .finding-autofix-btn {
            background: none;
            color: var(--vscode-input-foreground);
            border: 1px solid var(--vscode-input-border);
            border-radius: 3px;
            padding: 4px 8px;
            font-size: 11px;
            font-weight: 500;
            cursor: pointer;
            flex-shrink: 0;
            margin-left: auto;
            min-width: 30px;
            height: 24px;
        }
        
        .finding-autofix-btn:hover {
            background: var(--vscode-list-hoverBackground);
            border-color: var(--vscode-focusBorder);
        }
        
        .finding-autofix-btn:active {
            background: var(--vscode-button-background);
            opacity: 0.8;
        }
        
        /* Compact severity dots instead of pills */
        .severity-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
        }
        
        .severity-dot.error {
            background: var(--vscode-charts-red);
        }
        
        .severity-dot.warn {
            background: var(--vscode-charts-yellow);
        }
        
        .severity-dot.info {
            background: var(--vscode-charts-blue);
        }
        
        .finding-content {
            flex: 1;
            font-size: 11px;
            line-height: 1.2;
            overflow: hidden;
            color: var(--vscode-editor-foreground);
        }
        
        /* Legacy styles for backward compatibility */
        .severity-pill {
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 10px;
            font-weight: 500;
            min-width: 50px;
            text-align: center;
        }
        
        .severity-pill.error {
            background: var(--vscode-charts-red);
            color: white;
        }
        
        .severity-pill.warn {
            background: var(--vscode-charts-yellow);
            color: black;
        }
        
        .severity-pill.info {
            background: var(--vscode-charts-blue);
            color: white;
        }
        
        .rule-name {
            font-family: var(--vscode-editor-font-family);
            font-size: 11px;
            color: var(--vscode-descriptionForeground);
            min-width: 120px;
        }
        
        .finding-message {
            flex: 1;
            font-size: 12px;
            line-height: 1.3;
        }
        
        .finding-location {
            font-family: var(--vscode-editor-font-family);
            font-size: 10px;
            color: var(--vscode-descriptionForeground);
            text-align: right;
            min-width: 100px;
        }
        
        /* Empty state */
        .empty-findings {
            text-align: center;
            padding: 32px;
            color: var(--vscode-descriptionForeground);
            font-size: 13px;
        }
        
        .empty-graph {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            color: var(--vscode-descriptionForeground);
            font-size: 13px;
            gap: 12px;
        }
        
        .empty-graph svg {
            opacity: 0.5;
        }
        
        .empty-graph.hidden {
            display: none;
        }
        
        /* Dependency Graph tab content */
        .graph-tab-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            padding: 12px;
        }
        
        .graph-tab-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* Settings menu styles */
        .graph-header {
            position: relative;
            display: flex;
            justify-content: flex-end;
            padding: 8px 0;
        }
        
        .graph-settings-container {
            position: relative;
        }
        
        .settings-menu {
            position: absolute;
            top: 100%;
            right: 0;
            background: var(--vscode-menu-background);
            border: 1px solid var(--vscode-menu-border);
            border-radius: 6px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.2);
            z-index: 1000;
            min-width: 200px;
            padding: 8px;
            margin-top: 4px;
        }
        
        .settings-menu.hidden {
            display: none;
        }
        
        .settings-group {
            margin-bottom: 12px;
        }
        
        .settings-group:last-child {
            margin-bottom: 0;
        }
        
        .settings-label {
            display: block;
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 4px;
        }
        
        .settings-select {
            width: 100%;
            background: var(--vscode-dropdown-background);
            border: 1px solid var(--vscode-dropdown-border);
            border-radius: 3px;
            color: var(--vscode-dropdown-foreground);
            font-size: 12px;
            padding: 4px 8px;
        }
        
        .settings-checkbox {
            display: flex;
            align-items: center;
            gap: 6px;
            color: var(--vscode-foreground);
            font-size: 12px;
            margin: 4px 0;
            cursor: pointer;
        }
        
        .settings-checkbox input[type="checkbox"] {
            margin: 0;
        }

        .dependency-graph-svg {
            flex: 1;
            width: 100%;
            height: 100%;
            min-height: 100px;
            max-height: 400px;
            background: var(--vscode-editor-background);
            border: none;
            border-radius: 0;
            overflow: visible;
            cursor: default;
            margin: 0;
            padding: 0;
        }
        
        .dependency-graph-3d {
            flex: 1;
            width: 100%;
            height: 100%;
            min-height: 300px;
            background: var(--vscode-editor-background);
            border: none;
            border-radius: 0;
            cursor: pointer;
        }
        
        /* Enhanced graph node styles */
        .graph-node {
            cursor: pointer;
            transition: filter 0.2s ease, stroke-width 0.2s ease;
        }
        
        .graph-node.enhanced:hover {
            filter: url(#glow);
            stroke-width: 3;
        }
        
        .graph-link {
            stroke: var(--vscode-descriptionForeground);
            opacity: 0.6;
            stroke-width: 2.5; /* Base thickness */
            transition: opacity 0.2s ease, stroke-width 0.2s ease;
            cursor: pointer;
        }
        
        .graph-link:hover {
            opacity: 1;
            stroke-width: 4; /* Thicker on hover */
        }
        
        .graph-label.enhanced {
            fill: var(--vscode-foreground);
            font-family: var(--vscode-editor-font-family);
            font-size: 13px;
            text-anchor: middle;
            pointer-events: none;
            font-weight: 500;
        }
        
        /* Enhanced tooltip styles */
        .graph-tooltip {
            position: absolute;
            background: rgba(30, 30, 30, 0.9);
            border: none;
            border-radius: 3px;
            padding: 6px 10px;
            max-width: 250px;
            z-index: 10000;
            font-family: var(--vscode-editor-font-family);
            font-size: 11px;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.6);
            pointer-events: none;
            backdrop-filter: blur(10px);
            left: 10px !important;
            top: 10px !important;
        }
        
        .tooltip-header {
            font-weight: 500;
            color: var(--vscode-editor-foreground);
            margin-bottom: 2px;
            font-size: 11px;
        }
        
        .tooltip-content > div {
            margin: 1px 0;
            color: var(--vscode-descriptionForeground);
            font-size: 10px;
        }
        
        .tooltip-value {
            color: var(--vscode-editor-foreground);
            font-weight: 400;
        }
        
        .tooltip-critical {
            color: var(--vscode-errorForeground);
            font-weight: 500;
        }
        
        .tooltip-file {
            font-size: 10px;
            font-style: italic;
            margin-top: 3px;
            padding-top: 3px;
            border-top: none;
            color: var(--vscode-descriptionForeground);
        }

        /* Enhanced link tooltip styles - inherits from graph-tooltip */
        .link-tooltip {
            /* All styles inherited from .graph-tooltip above */
        }

        .link-tooltip .tooltip-header {
            background: transparent;
            color: var(--vscode-editor-foreground);
            padding: 0;
            border-radius: 0;
            font-weight: 500;
            margin-bottom: 2px;
            font-size: 11px;
        }

        .link-tooltip .tooltip-content {
            padding: 0;
        }

        .link-tooltip .tooltip-content > div {
            margin-bottom: 1px;
            line-height: 1.3;
            font-size: 10px;
        }

        .link-tooltip .tooltip-content > div:last-child {
            margin-bottom: 0;
        }

        .link-tooltip .tooltip-value {
            font-weight: 400;
            color: var(--vscode-editor-foreground);
        }

        .link-tooltip .tooltip-value.circular {
            color: var(--vscode-errorForeground);
        }

        .link-tooltip .tooltip-value.import {
            color: var(--vscode-editor-foreground);
        }

        .link-tooltip .tooltip-value.pattern {
            color: var(--vscode-editor-foreground);
        }

        .link-tooltip .tooltip-warning {
            background: transparent;
            color: var(--vscode-errorForeground);
            border: none;
            border-radius: 0;
            padding: 0;
            font-size: 10px;
            margin-top: 2px;
        }

        .link-tooltip .tooltip-action {
            color: var(--vscode-descriptionForeground);
            font-style: italic;
            font-size: 9px;
            margin-top: 3px;
            padding-top: 3px;
            border-top: 1px solid rgba(255, 255, 255, 0.1);
        }

        /* Findings summary bar */
        .findings-summary {
            background: var(--vscode-sideBar-background);
            border-bottom: 1px solid var(--vscode-panel-border);
            padding: 6px 12px;
            font-size: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin: 0;
            width: 100%;
            box-sizing: border-box;
            overflow: hidden;
        }

        .findings-breakdown {
            display: flex;
            align-items: center;
            gap: 16px;
            flex: 1;
            min-width: 0;
            margin-left: 6px;
        }

        .breakdown-item {
            display: flex;
            align-items: center;
            gap: 6px;
            font-weight: 500;
            flex-shrink: 0;
            cursor: pointer;
            transition: opacity 0.2s ease;
        }

        .breakdown-item:hover {
            opacity: 0.8;
        }

        .breakdown-item.filtered-out {
            opacity: 0.3;
        }

        .breakdown-item.filtered-out .breakdown-dot {
            background: var(--vscode-descriptionForeground) !important;
            border-color: var(--vscode-descriptionForeground) !important;
        }

        .breakdown-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            flex-shrink: 0;
        }

        .breakdown-dot.total {
            background: var(--vscode-foreground);
        }

        .breakdown-dot.error {
            background: var(--vscode-charts-orange);
            width: 12px;
            height: 12px;
        }

        .breakdown-dot.warn {
            background: var(--vscode-notificationsWarningIcon-foreground);
        }

        .breakdown-dot.info {
            background: transparent;
            border: 2px solid var(--vscode-charts-orange);
            width: 10px;
            height: 10px;
        }

        .autofix-potential {
            color: #ff9500;
            font-weight: 500;
            flex-shrink: 0;
            margin-left: 8px;
            white-space: nowrap;
            display: none;
        }

        /* Link analysis panel styles */
        .link-analysis {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            width: 100vw;
            height: 100vh;
            background: rgba(20, 20, 20, 0.95);
            border: none;
            border-radius: 0;
            box-shadow: none;
            z-index: 10001;
            overflow-y: auto;
            overflow-x: hidden;
            backdrop-filter: blur(10px);
        }

        .link-analysis .analysis-header {
            background: transparent;
            color: var(--vscode-editor-foreground);
            padding: 12px 16px;
            border-radius: 0;
            border-bottom: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .link-analysis .analysis-header h4 {
            margin: 0;
            font-size: 14px;
            font-weight: 600;
        }

        .link-analysis .close-btn {
            background: none;
            border: none;
            color: var(--vscode-editor-foreground);
            font-size: 18px;
            cursor: pointer;
            padding: 0;
            width: 24px;
            height: 24px;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 0;
        }

        .link-analysis .close-btn:hover {
            background: rgba(255, 255, 255, 0.1);
        }

        .link-analysis .analysis-content {
            padding: 16px;
            max-width: 800px;
            margin: 0 auto;
        }

        .link-analysis .analysis-section {
            margin-bottom: 16px;
        }

        .link-analysis .analysis-section:last-child {
            margin-bottom: 0;
        }

        .link-analysis .analysis-section h5 {
            margin: 0 0 8px 0;
            font-size: 13px;
            font-weight: 600;
            color: var(--vscode-symbolIcon-keywordForeground);
        }

        .link-analysis .detail-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 6px;
            line-height: 1.4;
        }

        .link-analysis .detail-row .label {
            color: var(--vscode-descriptionForeground);
            font-size: 12px;
        }

        .link-analysis .detail-row .value {
            color: var(--vscode-editor-foreground);
            font-size: 12px;
            font-weight: 500;
            max-width: 200px;
            text-align: right;
            word-break: break-word;
        }

        .link-analysis .action-btn {
            background: var(--vscode-button-secondaryBackground);
            color: var(--vscode-button-secondaryForeground);
            border: 1px solid var(--vscode-button-border);
            border-radius: 4px;
            padding: 6px 12px;
            font-size: 12px;
            cursor: pointer;
            margin-right: 8px;
            margin-bottom: 4px;
        }

        .link-analysis .action-btn:hover {
            background: var(--vscode-button-secondaryHoverBackground);
        }

        /* Interactive link styles */
        .graph-link.interactive {
            cursor: pointer;
            transition: all 0.2s ease;
            marker-end: url(#arrow-default);
        }

        .graph-link.interactive:hover {
            stroke-width: 5; /* Increased hover thickness */
            filter: drop-shadow(0 0 6px currentColor);
        }

        .graph-link.highlighted {
            stroke-width: 6; /* Increased highlight thickness */
            marker-end: url(#arrow-highlighted);
        }

        .graph-node.connected {
            stroke: var(--vscode-focusBorder);
            stroke-width: 3;
            filter: drop-shadow(0 0 6px var(--vscode-focusBorder));
        }

        /* Link type specific colors and arrows */
        .graph-link.link-import {
            stroke: var(--vscode-symbolIcon-moduleForeground);
            stroke-width: 4;
            marker-end: url(#arrow-import);
        }

        .graph-link.link-call {
            stroke: var(--vscode-symbolIcon-functionForeground);
            stroke-dasharray: 6,3;
            stroke-width: 3;
            marker-end: url(#arrow-call);
        }

        .graph-link.link-circular {
            stroke: var(--vscode-errorForeground);
            stroke-dasharray: 8,4;
            stroke-width: 4;
            marker-end: url(#arrow-circular);
        }

        .graph-link.link-export {
            stroke: var(--vscode-symbolIcon-keywordForeground);
            stroke-width: 4;
            marker-end: url(#arrow-export);
        }

        .graph-link.link-inherit {
            stroke: var(--vscode-symbolIcon-classForeground);
            stroke-dasharray: 12,4;
            stroke-width: 5;
            marker-end: url(#arrow-inherit);
        }

        /* Enhanced dependency analysis styles */
        .dependency-type-import { color: var(--vscode-symbolIcon-moduleForeground); }
        .dependency-type-call { color: var(--vscode-symbolIcon-functionForeground); }
        .dependency-type-circular { color: var(--vscode-errorForeground); font-weight: bold; }
        .dependency-type-export { color: var(--vscode-symbolIcon-keywordForeground); }
        .dependency-type-inherit { color: var(--vscode-symbolIcon-classForeground); }

        .symbols {
            font-family: monospace;
            background: var(--vscode-textBlockQuote-background);
            padding: 2px 6px;
            border-radius: 3px;
            font-size: 11px;
        }

        .lines {
            font-family: monospace;
            color: var(--vscode-descriptionForeground);
            font-size: 11px;
        }

        .bidirectional {
            color: var(--vscode-notificationsWarningIcon-foreground);
            font-weight: bold;
        }

        .insight {
            margin: 8px 0;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
            line-height: 1.4;
        }

        .insight.warning {
            background: var(--vscode-inputValidation-warningBackground);
            border-left: 3px solid var(--vscode-notificationsWarningIcon-foreground);
        }

        .insight.info {
            background: var(--vscode-inputValidation-infoBackground);
            border-left: 3px solid var(--vscode-notificationsInfoIcon-foreground);
        }

        .analysis-section h5 {
            margin: 12px 0 6px 0;
            color: var(--vscode-foreground);
            font-size: 13px;
            font-weight: 600;
        }

        .graph-link.link-fallback {
            stroke: var(--vscode-descriptionForeground);
            stroke-dasharray: 3,3;
            stroke-width: 3;
            opacity: 0.6;
            marker-end: url(#arrow-default);
        }

        /* Animations */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(-5px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes slideInRight {
            from { 
                opacity: 0; 
                transform: translateX(20px); 
            }
            to { 
                opacity: 1; 
                transform: translateX(0); 
            }
        }

        @keyframes slideInUp {
            from { 
                opacity: 0; 
                transform: translateY(10px); 
            }
            to { 
                opacity: 1; 
                transform: translateY(0); 
            }
        }

        @keyframes fadeOut {
            from { opacity: 1; }
            to { opacity: 0; }
        }

        /* Toast notifications */
        .toast {
            position: fixed;
            bottom: 16px;
            right: 16px;
            background: var(--vscode-notifications-background);
            border: 1px solid var(--vscode-notifications-border);
            border-radius: 4px;
            padding: 8px 12px;
            font-size: 12px;
            color: var(--vscode-notifications-foreground);
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
            z-index: 10000;
            animation: slideInUp 0.3s ease-out;
            max-width: 300px;
        }

        .toast.success {
            border-left: 3px solid var(--vscode-charts-green);
        }

        .toast.info {
            border-left: 3px solid var(--vscode-charts-blue);
        }

        .toast.fade-out {
            animation: fadeOut 0.3s ease-out forwards;
        }

        /* Findings tab content */
        .findings-tab-content {
            flex: 1;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        
        .empty-graph {
            text-align: center;
            padding: 32px;
            color: var(--vscode-descriptionForeground);
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="header-bar score-hidden" id="header-bar">
        <div class="score-container" id="score-container" style="display: none;">
            <div class="score-number" id="score">—</div>
            <div class="score-label">QUALITY SCORE</div>
            <div class="score-details" id="score-details" style="display: none;"></div>
            <div class="loading-spinner" id="loading-spinner" style="display: none;">
                <svg viewBox="0 0 24 24" width="28" height="28">
                    <circle cx="12" cy="12" r="10" stroke="var(--vscode-charts-orange)" stroke-width="2" fill="none" stroke-dasharray="31.416" stroke-dashoffset="31.416">
                        <animate attributeName="stroke-dasharray" dur="2s" values="0 31.416;15.708 15.708;0 31.416;0 31.416" repeatCount="indefinite"/>
                        <animate attributeName="stroke-dashoffset" dur="2s" values="0;-15.708;-31.416;-31.416" repeatCount="indefinite"/>
                    </circle>
                </svg>
            </div>
        </div>
        <div class="controls-container">
            <div class="action-buttons">
                <!-- Auto-Fix button hidden - feature temporarily disabled
                <button id="auto-fix-safe-button" class="action-button" title="Safe Auto-Fix">
                    <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                        <polyline points="9 11 12 14 22 4"></polyline>
                        <path d="m21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9c1.51 0 2.93.37 4.18 1.03"></path>
                    </svg>
                    <span class="action-text">Auto-Fix</span>
                </button>
                -->
                <!-- Agent button moved to view-toggle area -->
            </div>
        </div>
    </div>
    
    <div class="main-content">
        <div class="view-container">
            <!-- View Toggle with Settings -->
            <div class="view-toggle">
                <button class="view-toggle-btn" id="view-toggle-btn">
                    <span id="view-toggle-text">Show graph</span>
                    <span class="view-toggle-count" id="view-toggle-count">(0)</span>
                </button>
                <div class="graph-settings-container">
                    <!-- Graph type selector removed - code kept for future use
                    <select id="graph-type-select" class="graph-type-select" style="display: none;">
                        <option value="2d">2D Focused</option>
                        <option value="3d">3D Overview</option>
                    </select>
                    -->
                    <button id="generate-instructions-btn" class="generate-instructions-btn" title="Generate AI instruction files" style="display: none;">
                        <svg class="action-icon" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2.5">
                            <path d="M12 5v14M5 12h14"/>
                        </svg>
                    </button>
                    <div class="validation-spinner" id="validation-spinner" title="Validating...">
                        <svg viewBox="0 0 16 16" width="14" height="14">
                            <circle cx="8" cy="8" r="6" stroke="var(--vscode-charts-orange)" stroke-width="2" fill="none" stroke-dasharray="18.85" stroke-dashoffset="9.42" stroke-linecap="round">
                                <animateTransform attributeName="transform" type="rotate" from="0 8 8" to="360 8 8" dur="0.8s" repeatCount="indefinite"/>
                            </circle>
                        </svg>
                    </div>
                    <!-- TEMPORARILY DISABLED: Align button (ALIGNMENTS.json feature)
                    <button id="align-button" class="action-button icon-only" title="Align - Report AI issue" style="display: none;">
                        <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path>
                        </svg>
                    </button>
                    -->
                    <!-- TEMPORARILY DISABLED: Explain button (replaced by Propose)
                    <button id="explain-button" class="action-button icon-only" title="Explain Current File">
                        <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
                            <polyline points="14 2 14 8 20 8"></polyline>
                            <line x1="16" y1="13" x2="8" y2="13"></line>
                            <line x1="16" y1="17" x2="8" y2="17"></line>
                            <polyline points="10 9 9 9 8 9"></polyline>
                        </svg>
                    </button>
                    -->
                    <button id="propose-button" class="action-button icon-only" title="Plan with Structure">
                        <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 20h9"></path>
                            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"></path>
                        </svg>
                    </button>
                    <button class="settings-toggle" id="settings-toggle" title="Settings">
                        <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z"></path>
                            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1Z"></path>
                        </svg>
                    </button>
                    <div class="settings-menu hidden" id="settings-menu">
                        <div class="settings-section">
                            <button class="action-button settings-action-button" id="regenerate-assistant-files">
                                <svg class="action-icon" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21.5 2v6h-6M2.5 22v-6h6M2 11.5a10 10 0 0 1 18.8-4.3M22 12.5a10 10 0 0 1-18.8 4.2"/>
                                </svg>
                                <span class="action-text">Regenerate Files</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Dependency Graph View -->
            <div class="view-content" id="graph-view">
                <div class="graph-view-content">
                    <div class="empty-graph" id="empty-graph">
                        <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5">
                            <circle cx="12" cy="12" r="3"></circle>
                            <circle cx="4" cy="8" r="2"></circle>
                            <circle cx="20" cy="8" r="2"></circle>
                            <circle cx="4" cy="16" r="2"></circle>
                            <circle cx="20" cy="16" r="2"></circle>
                            <line x1="9.5" y1="10.5" x2="5.5" y2="8.5"></line>
                            <line x1="14.5" y1="10.5" x2="18.5" y2="8.5"></line>
                            <line x1="9.5" y1="13.5" x2="5.5" y2="15.5"></line>
                            <line x1="14.5" y1="13.5" x2="18.5" y2="15.5"></line>
                        </svg>
                        <div>Open a file to see its dependency graph</div>
                    </div>
                    <svg class="dependency-graph-svg" id="dependency-graph" viewBox="0 0 800 300" preserveAspectRatio="xMidYMid meet">
                        <g id="graph-links"></g>
                        <g id="graph-nodes"></g>
                        <g id="graph-labels"></g>
                    </svg>
                    <!-- 3D canvas removed but code kept for future use
                    <canvas class="dependency-graph-3d hidden" id="dependency-graph-3d" width="800" height="400"></canvas>
                    -->
                </div>
            </div>
            
            <!-- Findings View (default) -->
            <div class="view-content active" id="findings-view">
                <div class="findings-view-content">
                    <div class="findings-list" id="findings-list">
                        <div class="empty-findings">No findings to display</div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        const vscode = acquireVsCodeApi();
        
        let currentFindings = [];
        let currentGraph = { nodes: [], links: [] }; // Legacy - will be replaced
        let focusedGraph = { nodes: [], links: [] }; // 2D focused graph data
        let overviewGraph = { nodes: [], links: [] }; // 3D overview graph data
        let activeTab = 'graph'; // Default to dependency graph tab (kept for compatibility)
        let manualProcessingActive = false; // Track manual processing to prevent score flashing
        let currentActiveFile = ''; // Track currently active file for findings sorting
        let currentState = null; // Track latest state for re-rendering
        let severityFilters = { problems: true, informational: true }; // Track which priority types are shown (P0/P1 = problems, P2/P3 = informational)
        
        // Action button handlers
        // Auto-Fix button handler disabled - feature temporarily disabled
        /*
        document.getElementById('auto-fix-safe-button').addEventListener('click', async () => {
            const btn = document.getElementById('auto-fix-safe-button');
            btn.disabled = true;
            
            try {
                vscode.postMessage({
                    type: 'AUTO_FIX_SAFE',
                    payload: {}
                });
                // Button will be re-enabled by AUTO_FIX_SAFE_COMPLETE message
            } catch (error) {
                console.error('Auto-fix failed:', error);
                btn.disabled = false;
            }
        });
        */
        
        /* TEMPORARILY DISABLED: Explain button (replaced by Propose)
        document.getElementById('explain-button').addEventListener('click', async () => {
            const btn = document.getElementById('explain-button');
            btn.disabled = true;
            
            try {
                vscode.postMessage({ type: 'EXPLAIN_FILE' });
                setTimeout(() => { btn.disabled = false; }, 1000);
            } catch (error) {
                console.error('Explain failed:', error);
                btn.disabled = false;
            }
        });
        */

        document.getElementById('propose-button').addEventListener('click', async () => {
            const btn = document.getElementById('propose-button');
            btn.disabled = true;
            
            try {
                vscode.postMessage({
                    type: 'PROPOSE_FIXES',
                    payload: { findings: currentFindings }
                });
                setTimeout(() => { btn.disabled = false; }, 1000);
            } catch (error) {
                console.error('Propose failed:', error);
                btn.disabled = false;
            }
        });

        /* TEMPORARILY DISABLED: Align button (ALIGNMENTS.json feature)
        document.getElementById('align-button').addEventListener('click', async () => {
            const btn = document.getElementById('align-button');
            btn.disabled = true;
            
            try {
                // Show input box to describe the issue
                vscode.postMessage({
                    type: 'ALIGN_ISSUE',
                    payload: {}
                });
                setTimeout(() => { btn.disabled = false; }, 1000);
            } catch (error) {
                console.error('Align failed:', error);
                btn.disabled = false;
            }
        });
        */
        
        // View toggle functionality
        let currentView = 'findings'; // Default to findings view
        
        // Settings container is always visible now
        // document.querySelector('.graph-settings-container').style.display = currentView === 'graph' ? '' : 'none';
        
        document.getElementById('view-toggle-btn').addEventListener('click', () => {
            toggleView();
        });

        // Generate instructions button (attention-grabbing)
        document.getElementById('generate-instructions-btn').addEventListener('click', async () => {
            const btn = document.getElementById('generate-instructions-btn');
            btn.disabled = true;
            
            vscode.postMessage({
                type: 'COMMAND',
                command: 'aspectcode.configureAssistants'
            });
            
            // Hide the button after clicking (files will be generated)
            setTimeout(() => {
                btn.style.display = 'none';
            }, 500);
        });

        // Regenerate assistant files button
        document.getElementById('regenerate-assistant-files').addEventListener('click', async () => {
            const btn = document.getElementById('regenerate-assistant-files');
            const iconSvg = btn.querySelector('.action-icon');
            const textSpan = btn.querySelector('.action-text');
            const originalText = textSpan.textContent;
            
            // Close the settings menu immediately
            document.getElementById('settings-menu').classList.add('hidden');
            
            btn.disabled = true;
            textSpan.textContent = 'Regenerating...';
            
            try {
                vscode.postMessage({
                    type: 'COMMAND',
                    command: 'aspectcode.configureAssistants'
                });
                
                // Re-enable after a delay and hide the generate button
                setTimeout(() => {
                    btn.disabled = false;
                    textSpan.textContent = originalText;
                    // Also hide the generate-instructions button since files were generated
                    document.getElementById('generate-instructions-btn').style.display = 'none';
                }, 2000);
            } catch (error) {
                console.error('Failed to regenerate assistant files:', error);
                btn.disabled = false;
                textSpan.textContent = originalText;
            }
        });
        
        function toggleView() {
            const isShowingGraph = currentView === 'graph';
            currentView = isShowingGraph ? 'findings' : 'graph';
            
            // Update views
            document.querySelectorAll('.view-content').forEach(content => {
                content.classList.remove('active');
            });
            
            if (currentView === 'graph') {
                document.getElementById('graph-view').classList.add('active');
                updateViewToggleButton('Show findings', currentFindings.length);
                
                // Settings menu is now always visible
                // document.querySelector('.graph-settings-container').style.display = '';
                
                // Re-render graph if switching to graph view
                if (currentGraph && currentGraph.nodes.length > 0) {
                    setTimeout(() => renderDependencyGraph(currentGraph), 100);
                }
            } else {
                document.getElementById('findings-view').classList.add('active');
                updateViewToggleButton('Show graph', currentGraph?.nodes?.length || 0);
                
                // Settings menu is now always visible
                // document.querySelector('.graph-settings-container').style.display = 'none';
            }
        }
        
        function updateViewToggleButton(text, count) {
            document.getElementById('view-toggle-text').textContent = text;
            // Don't show count for "Show graph", only for "Show findings"
            if (text.includes('Show graph')) {
                document.getElementById('view-toggle-count').textContent = '';
            } else {
                document.getElementById('view-toggle-count').textContent = '(' + count + ')';
            }
        }
        
        // Settings menu toggle
        document.getElementById('settings-toggle').addEventListener('click', (e) => {
            e.stopPropagation();
            const menu = document.getElementById('settings-menu');
            menu.classList.toggle('hidden');
        });
        
        // Close settings menu when clicking elsewhere
        document.addEventListener('click', (e) => {
            const menu = document.getElementById('settings-menu');
            const toggle = document.getElementById('settings-toggle');
            if (!menu.contains(e.target) && e.target !== toggle) {
                menu.classList.add('hidden');
            }
        });
        
        function renderDependencyGraph(graph) {
            currentGraph = graph || { nodes: [], links: [] };
            
            // Hide any visible tooltips when graph updates (new file/node focused)
            hideTooltip();
            hideLinkTooltip();
            
            // Handle empty graph state
            const emptyGraph = document.getElementById('empty-graph');
            const svg = document.getElementById('dependency-graph');
            
            if (!currentGraph.nodes || currentGraph.nodes.length === 0) {
                // Show empty state, hide SVG
                if (emptyGraph) emptyGraph.classList.remove('hidden');
                if (svg) svg.style.display = 'none';
                return;
            } else {
                // Hide empty state, show SVG
                if (emptyGraph) emptyGraph.classList.add('hidden');
                if (svg) svg.style.display = '';
            }
            
            // 3D mode disabled - always use 2D
            // const graphTypeSelect = document.getElementById('graph-type-select');
            // const currentGraphType = graphTypeSelect ? graphTypeSelect.value : '2d';
            // 
            // if (currentGraphType === '3d') {
            //     render3DGraph(currentGraph);
            //     return;
            // }
            
            if (!svg) {
                console.warn('SVG elements not found, retrying...');
                setTimeout(() => renderDependencyGraph(graph), 100);
                return;
            }
            
            // Update view toggle button if we're showing graph
            if (currentView === 'graph') {
                updateViewToggleButton('Show findings', currentFindings.length);
            }
            
            // Clear existing content and set up structure
            svg.innerHTML = '';
            
            // Create SVG structure with enhanced arrow markers
            const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
            
            // Create arrow markers for different link types
            const createArrowMarker = (id, color, size = 6) => {
                const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
                marker.setAttribute('id', id);
                marker.setAttribute('viewBox', '0 0 10 10');
                marker.setAttribute('refX', '8');
                marker.setAttribute('refY', '3');
                marker.setAttribute('markerWidth', size);
                marker.setAttribute('markerHeight', size);
                marker.setAttribute('orient', 'auto');
                marker.setAttribute('markerUnits', 'strokeWidth');
                
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', 'M0,0 L0,6 L9,3 z');
                path.setAttribute('fill', color);
                marker.appendChild(path);
                return marker;
            };
            
            // Add various arrow types
            defs.appendChild(createArrowMarker('arrow-default', 'var(--vscode-descriptionForeground)', 5));
            defs.appendChild(createArrowMarker('arrow-import', 'var(--vscode-symbolIcon-moduleForeground)', 6));
            defs.appendChild(createArrowMarker('arrow-call', 'var(--vscode-symbolIcon-functionForeground)', 5));
            defs.appendChild(createArrowMarker('arrow-circular', 'var(--vscode-errorForeground)', 6));
            defs.appendChild(createArrowMarker('arrow-export', 'var(--vscode-symbolIcon-keywordForeground)', 6));
            defs.appendChild(createArrowMarker('arrow-inherit', 'var(--vscode-symbolIcon-classForeground)', 7));
            defs.appendChild(createArrowMarker('arrow-highlighted', 'var(--vscode-focusBorder)', 8));
            
            const filter = document.createElementNS('http://www.w3.org/2000/svg', 'filter');
            filter.setAttribute('id', 'glow');
            
            const blur = document.createElementNS('http://www.w3.org/2000/svg', 'feGaussianBlur');
            blur.setAttribute('stdDeviation', '3');
            blur.setAttribute('result', 'coloredBlur');
            
            const merge = document.createElementNS('http://www.w3.org/2000/svg', 'feMerge');
            const mergeNode1 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
            mergeNode1.setAttribute('in', 'coloredBlur');
            const mergeNode2 = document.createElementNS('http://www.w3.org/2000/svg', 'feMergeNode');
            mergeNode2.setAttribute('in', 'SourceGraphic');
            
            merge.appendChild(mergeNode1);
            merge.appendChild(mergeNode2);
            filter.appendChild(blur);
            filter.appendChild(merge);
            defs.appendChild(filter);
            svg.appendChild(defs);
            
            const container = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            container.setAttribute('id', 'graph-container');
            
            const linksGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            linksGroup.setAttribute('id', 'graph-links');
            const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            nodesGroup.setAttribute('id', 'graph-nodes');
            const labelsGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            labelsGroup.setAttribute('id', 'graph-labels');
            
            container.appendChild(linksGroup);
            container.appendChild(nodesGroup);
            container.appendChild(labelsGroup);
            svg.appendChild(container);
            
            // Get container size for responsive graph - USE ACTUAL SIZE
            const containerRect = svg.getBoundingClientRect();
            const width = containerRect.width || 800; // Use actual width, fallback only if 0
            const height = containerRect.height || 300; // Use actual height, fallback only if 0
            const centerX = width / 2;
            const centerY = height * 0.50; // Position circle higher - 50% from top
            
            // Update SVG viewBox to match container
            svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);
            
            if (currentGraph.nodes.length === 0) {
                const emptyMessage = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                emptyMessage.setAttribute('x', centerX);
                emptyMessage.setAttribute('y', centerY);
                emptyMessage.setAttribute('text-anchor', 'middle');
                emptyMessage.setAttribute('class', 'empty-graph');
                emptyMessage.textContent = 'No dependency data available';
                nodesGroup.appendChild(emptyMessage);
                return;
            }

            // Enhanced node data with physics properties
            const nodes = currentGraph.nodes.map((node, i) => {
                let x, y;
                
                // First, try to preserve position from previous render to prevent bouncing
                const existingCircle = document.querySelector('circle[data-node-id="' + node.id.replace(/[\\\/]/g, '_') + '"]');
                if (existingCircle) {
                    const prevX = parseFloat(existingCircle.getAttribute('cx'));
                    const prevY = parseFloat(existingCircle.getAttribute('cy'));
                    if (!isNaN(prevX) && !isNaN(prevY)) {
                        x = prevX;
                        y = prevY;
                    }
                }
                
                // If no previous position found, calculate new position using circular layout
                if (x === undefined || y === undefined) {
                    // Use most of space but leave margin for labels
                    const radius = Math.min(width, height) * 0.40; // Use 80% of diameter
                    
                    // Smart angle offset based on number of nodes for better aesthetics
                    const nodeCount = currentGraph.nodes.length;
                    let angleOffset = -Math.PI / 2; // Default: start from top (12 o'clock)
                    if (nodeCount === 1) {
                        angleOffset = -Math.PI / 2; // 1 node: top (12 o'clock)
                    } else if (nodeCount === 2) {
                        angleOffset = 0; // 2 nodes: left and right (9 and 3 o'clock)
                    } else if (nodeCount % 2 === 0) {
                        // Even number: offset by half step for symmetry
                        angleOffset = -Math.PI / 2 + (Math.PI / nodeCount);
                    }
                    
                    const angle = (2 * Math.PI * i) / nodeCount + angleOffset;
                    
                    x = centerX + radius * Math.cos(angle);
                    y = centerY + radius * Math.sin(angle);
                }
                
                return {
                    ...node,
                    x: x,
                    y: y,
                    vx: 0,
                    vy: 0,
                    // All nodes same size - smaller and uniform
                    radius: 8,
                    color: getNodeColor(node),
                    strokeColor: getNodeStrokeColor(node)
                };
            });

            // Create node lookup map
            const nodeMap = new Map();
            nodes.forEach(node => nodeMap.set(node.id, node));

            // Enhanced links with validation
            const links = currentGraph.links.filter(link => {
                const source = nodeMap.get(link.source);
                const target = nodeMap.get(link.target);
                return source && target && source !== target;
            }).map(link => ({
                ...link,
                source: nodeMap.get(link.source),
                target: nodeMap.get(link.target),
                strength: Math.max(0.1, Math.min(1, link.strength || 0.5))
            }));

            // Force simulation parameters
            let alpha = 1.0;
            const alphaDecay = 0.02;
            const velocityDecay = 0.6;
            
            // Run physics simulation
            function tick() {
                // Apply forces
                applyForces(nodes, links, width, height);
                
                // Update positions with improved boundary handling
                nodes.forEach(node => {
                    // ABSOLUTELY pin the center file in focus mode - STRONGEST enforcement
                    if (currentGraph.focusMode && currentGraph.centerFile && node.id === currentGraph.centerFile) {
                        // Force position to higher center position
                        node.x = centerX;
                        node.y = height * 0.3; // Higher positioning
                        node.vx = 0;
                        node.vy = 0;
                        return; // Skip all other processing for this node
                    }
                    
                    node.vx *= velocityDecay;
                    node.vy *= velocityDecay;
                    node.x += node.vx;
                    node.y += node.vy;
                    
                    // Better boundary constraints with padding
                    const padding = node.radius + 25;
                    node.x = Math.max(padding, Math.min(width - padding, node.x));
                    node.y = Math.max(padding, Math.min(height - padding, node.y));
                });
                
                // ADDITIONAL collision resolution pass to prevent any remaining overlaps
                for (let i = 0; i < nodes.length; i++) {
                    // Skip the pinned center node
                    if (currentGraph.focusMode && currentGraph.centerFile && nodes[i].id === currentGraph.centerFile) {
                        continue;
                    }
                    
                    for (let j = i + 1; j < nodes.length; j++) {
                        // Skip if the other node is pinned center
                        if (currentGraph.focusMode && currentGraph.centerFile && nodes[j].id === currentGraph.centerFile) {
                            continue;
                        }
                        
                        const dx = nodes[j].x - nodes[i].x;
                        const dy = nodes[j].y - nodes[i].y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        const minSeparation = (nodes[i].radius + nodes[j].radius) * 2.2;
                        
                        if (distance < minSeparation && distance > 0) {
                            // Push nodes apart to prevent overlap
                            const pushDistance = (minSeparation - distance) / 2;
                            const pushX = (dx / distance) * pushDistance;
                            const pushY = (dy / distance) * pushDistance;
                            
                            nodes[i].x -= pushX;
                            nodes[i].y -= pushY;
                            nodes[j].x += pushX;
                            nodes[j].y += pushY;
                        }
                    }
                }
                
                // Render current state
                render();
                
                alpha -= alphaDecay;
                if (alpha > 0.01) {
                    requestAnimationFrame(tick);
                }
            }

            function applyForces(nodes, links, width, height) {
                const k = Math.sqrt((width * height) / nodes.length) * 1.2; // Increased spacing factor
                const centerForce = 0.03;
                const boundaryPadding = 60;
                
                // STRONG collision detection and separation - prevent all overlaps
                for (let i = 0; i < nodes.length; i++) {
                    // Skip force application if this is the pinned center node
                    if (currentGraph.focusMode && currentGraph.centerFile && nodes[i].id === currentGraph.centerFile) {
                        continue;
                    }
                    
                    for (let j = i + 1; j < nodes.length; j++) {
                        // Skip if the other node is the pinned center node
                        if (currentGraph.focusMode && currentGraph.centerFile && nodes[j].id === currentGraph.centerFile) {
                            continue;
                        }
                        
                        const dx = nodes[j].x - nodes[i].x;
                        const dy = nodes[j].y - nodes[i].y;
                        const distance = Math.sqrt(dx * dx + dy * dy);
                        const minSeparation = (nodes[i].radius + nodes[j].radius) * 2.5; // Increased separation
                        
                        if (distance < minSeparation && distance > 0) {
                            // STRONG separation force to prevent overlap
                            const separationForce = (minSeparation - distance) * 0.5;
                            const fx = (dx / distance) * separationForce;
                            const fy = (dy / distance) * separationForce;
                            
                            // Apply separation forces
                            nodes[i].vx -= fx;
                            nodes[i].vy -= fy;
                            nodes[j].vx += fx;
                            nodes[j].vy += fy;
                        }
                        
                        // General repulsion for better spacing
                        if (distance > 0 && distance < k * 3) {
                            const repulsionForce = k * k / (distance * distance + 100);
                            const fx = (dx / distance) * repulsionForce;
                            const fy = (dy / distance) * repulsionForce;
                            
                            nodes[i].vx -= fx * alpha;
                            nodes[i].vy -= fy * alpha;
                            nodes[j].vx += fx * alpha;
                            nodes[j].vy += fy * alpha;
                        }
                    }
                }
                
                // Link forces - but don't apply to pinned center node
                links.forEach(link => {
                    const dx = link.target.x - link.source.x;
                    const dy = link.target.y - link.source.y;
                    const distance = Math.sqrt(dx * dx + dy * dy);
                    const targetDistance = k * (1.0 + link.strength * 0.3);
                    
                    if (distance > 0) {
                        const force = (distance - targetDistance) * link.strength * 0.03;
                        const fx = (dx / distance) * force;
                        const fy = (dy / distance) * force;
                        
                        // Only apply link forces to non-pinned nodes
                        if (!(currentGraph.focusMode && currentGraph.centerFile && link.source.id === currentGraph.centerFile)) {
                            link.source.vx += fx * alpha;
                            link.source.vy += fy * alpha;
                        }
                        if (!(currentGraph.focusMode && currentGraph.centerFile && link.target.id === currentGraph.centerFile)) {
                            link.target.vx -= fx * alpha;
                            link.target.vy -= fy * alpha;
                        }
                    }
                });
                
                // Center attraction and boundary forces - skip pinned node
                nodes.forEach(node => {
                    // Skip the pinned center node completely
                    if (currentGraph.focusMode && currentGraph.centerFile && node.id === currentGraph.centerFile) {
                        return;
                    }
                    
                    // Center attraction for non-center nodes
                    node.vx += (centerX - node.x) * centerForce * alpha;
                    node.vy += (centerY - node.y) * centerForce * alpha;
                    
                    // Strong boundary repulsion
                    if (node.x < boundaryPadding) {
                        node.vx += (boundaryPadding - node.x) * 0.2;
                    }
                    if (node.x > width - boundaryPadding) {
                        node.vx -= (node.x - (width - boundaryPadding)) * 0.2;
                    }
                    if (node.y < boundaryPadding) {
                        node.vy += (boundaryPadding - node.y) * 0.2;
                    }
                    if (node.y > height - boundaryPadding) {
                        node.vy -= (node.y - (height - boundaryPadding)) * 0.2;
                    }
                });
            }

            function renderEnhancedLinks(links, linksGroup) {
                // Group links by node pairs to detect overlaps
                const linkGroups = new Map();
                
                links.forEach(link => {
                    const sourceId = link.source.id;
                    const targetId = link.target.id;
                    const pairKey = [sourceId, targetId].sort().join('->');
                    
                    if (!linkGroups.has(pairKey)) {
                        linkGroups.set(pairKey, []);
                    }
                    linkGroups.get(pairKey).push(link);
                });
                
                linkGroups.forEach((groupLinks, pairKey) => {
                    if (groupLinks.length === 1) {
                        // Single link - render as straight line
                        renderSingleLink(groupLinks[0], linksGroup);
                    } else {
                        // Multiple links - render with offsets/curves
                        renderBundledLinks(groupLinks, linksGroup);
                    }
                });
            }

            function renderSingleLink(link, container) {
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                const x1 = link.source.x, y1 = link.source.y;
                const x2 = link.target.x, y2 = link.target.y;
                
                // Calculate arrow offset to end at node edge, not center
                const dx = x2 - x1, dy = y2 - y1;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const offset = (link.target.radius || 15) + 5; // Arrow ends outside node
                
                const endX = x2 - (dx / distance) * offset;
                const endY = y2 - (dy / distance) * offset;
                
                path.setAttribute('d', 'M ' + x1 + ' ' + y1 + ' L ' + endX + ' ' + endY);
                path.setAttribute('class', 'graph-link interactive');
                path.setAttribute('stroke-opacity', link.strength * 0.8 + 0.2);
                path.setAttribute('stroke-width', Math.max(3, link.strength * 4)); // Thicker base
                path.setAttribute('fill', 'none');
                
                // Add link type class for different styling and arrows
                if (link.type) {
                    path.classList.add('link-' + link.type);
                }
                
                // Enhanced hover effects for links
                path.addEventListener('mouseenter', (e) => showLinkTooltip(e, link));
                path.addEventListener('mouseleave', hideLinkTooltip);
                path.addEventListener('click', (e) => handleLinkClick(link, e));
                
                container.appendChild(path);
            }

            function renderBundledLinks(groupLinks, container) {
                const baseLink = groupLinks[0];
                const x1 = baseLink.source.x, y1 = baseLink.source.y;
                const x2 = baseLink.target.x, y2 = baseLink.target.y;
                
                // Calculate perpendicular offset for bundling
                const dx = x2 - x1, dy = y2 - y1;
                const distance = Math.sqrt(dx * dx + dy * dy);
                const perpX = -dy / distance;
                const perpY = dx / distance;
                
                groupLinks.forEach((link, index) => {
                    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                    
                    // Calculate offset for this link in the bundle
                    const bundleSize = groupLinks.length;
                    const offsetMultiplier = (index - (bundleSize - 1) / 2) * 12; // 12px spacing
                    const offsetX = perpX * offsetMultiplier;
                    const offsetY = perpY * offsetMultiplier;
                    
                    // Control points for curved path
                    const midX = (x1 + x2) / 2 + offsetX;
                    const midY = (y1 + y2) / 2 + offsetY;
                    
                    // Calculate arrow offset to end at node edge
                    const offset = (link.target.radius || 15) + 5;
                    const endX = x2 - (dx / distance) * offset;
                    const endY = y2 - (dy / distance) * offset;
                    
                    // Create smooth quadratic curve
                    path.setAttribute('d', 'M ' + x1 + ' ' + y1 + ' Q ' + midX + ' ' + midY + ' ' + endX + ' ' + endY);
                    path.setAttribute('class', 'graph-link interactive');
                    path.setAttribute('stroke-opacity', link.strength * 0.8 + 0.2);
                    path.setAttribute('stroke-width', Math.max(3, link.strength * 4));
                    path.setAttribute('fill', 'none');
                    
                    // Add link type class
                    if (link.type) {
                        path.classList.add('link-' + link.type);
                    }
                    
                    // Enhanced hover effects
                    path.addEventListener('mouseenter', (e) => showLinkTooltip(e, link));
                    path.addEventListener('mouseleave', hideLinkTooltip);
                    path.addEventListener('click', (e) => handleLinkClick(link, e));
                    
                    container.appendChild(path);
                });
            }

            function render() {
                // FINAL enforcement: Ensure center node is ALWAYS at exact center before rendering
                if (currentGraph.focusMode && currentGraph.centerFile) {
                    const centerNode = nodes.find(node => node.id === currentGraph.centerFile);
                    if (centerNode) {
                        centerNode.x = centerX;
                        centerNode.y = centerY;
                        centerNode.vx = 0;
                        centerNode.vy = 0;
                    }
                }
                
                // Clear and render links with enhanced directional arrows and bundling
                linksGroup.innerHTML = '';
                renderEnhancedLinks(links, linksGroup);

                // Clear and render nodes
                nodesGroup.innerHTML = '';
                labelsGroup.innerHTML = '';
                
                nodes.forEach(node => {
                    // Create node circle
                    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                    circle.setAttribute('cx', node.x);
                    circle.setAttribute('cy', node.y);
                    circle.setAttribute('r', node.radius);
                    circle.setAttribute('class', 'graph-node enhanced');
                    circle.setAttribute('fill', node.color);
                    circle.setAttribute('stroke', node.strokeColor);
                    circle.setAttribute('stroke-width', node.type === 'hub' ? '3' : '1.5');
                    circle.setAttribute('data-node-id', node.id.replace(/[\\\/]/g, '_')); // For position preservation
                    
                    // Enhanced hover effects
                    circle.addEventListener('mouseenter', (e) => showTooltip(e, node));
                    circle.addEventListener('mouseleave', hideTooltip);
                    circle.addEventListener('click', () => {
                        // Hide tooltips immediately on click
                        hideTooltip();
                        hideLinkTooltip();
                        
                        if (node.file) {
                            // Open the file in editor
                            vscode.postMessage({
                                type: 'OPEN_FINDING', 
                                file: node.file,
                                line: 1,
                                column: 1
                            });
                            
                            // Switch to focused mode for this file
                            vscode.postMessage({
                                type: 'NODE_CLICK_FOCUS',
                                file: node.file
                            });
                        }
                    });
                    
                    nodesGroup.appendChild(circle);
                    
                    // Enhanced labels
                    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                    text.setAttribute('x', node.x);
                    text.setAttribute('y', node.y + node.radius + 14);
                    text.setAttribute('class', 'graph-label enhanced');
                    text.textContent = node.label.length > 15 ? node.label.substring(0, 12) + '...' : node.label;
                    labelsGroup.appendChild(text);
                });
            }

            // Enhanced color functions
            function getNodeColor(node) {
                if (node.type === 'hub') return 'var(--vscode-charts-orange)';
                
                const importance = node.importance || 0;
                if (importance > 10) return 'var(--vscode-charts-orange)';
                if (importance > 5) return 'var(--vscode-charts-yellow)';
                if (importance > 2) return 'var(--vscode-charts-blue)';
                return '#282828';
            }
            
            function getNodeStrokeColor(node) {
                if (node.highSeverity > 0) return 'var(--vscode-errorForeground)';
                if ((node.importance || 0) > 3) return 'var(--vscode-notificationsWarningIcon-foreground)';
                return 'var(--vscode-foreground)';
            }

            // Enhanced tooltip system
            function showTooltip(event, node) {
                hideTooltip(); // Clear any existing tooltip
                
                const tooltip = document.createElement('div');
                tooltip.id = 'graph-tooltip';
                tooltip.className = 'graph-tooltip';
                
                // Build compact tooltip content
                const header = document.createElement('div');
                header.className = 'tooltip-header';
                header.textContent = node.label;
                
                const content = document.createElement('div');
                content.className = 'tooltip-content';
                
                // Only show findings if > 0
                if (node.importance > 0) {
                    const findingsDiv = document.createElement('div');
                    findingsDiv.innerHTML = '<span class="tooltip-value">' + (node.importance || 0) + ' finding' + (node.importance !== 1 ? 's' : '') + '</span>';
                    content.appendChild(findingsDiv);
                }
                
                tooltip.appendChild(header);
                tooltip.appendChild(content);
                
                // Position tooltip at top-left of graph container (not document.body)
                const graphView = document.querySelector('.graph-view-content');
                if (graphView) {
                    graphView.appendChild(tooltip);
                } else {
                    svg.parentElement.appendChild(tooltip);
                }
                
                // Tooltip is positioned at top-left via CSS
                // No need for dynamic positioning
            }
            
            function hideTooltip() {
                const existing = document.getElementById('graph-tooltip');
                if (existing) existing.remove();
            }

            // Enhanced link tooltip system
            function showLinkTooltip(event, link) {
                hideLinkTooltip(); // Clear any existing tooltip
                
                const tooltip = document.createElement('div');
                tooltip.id = 'link-tooltip';
                tooltip.className = 'link-tooltip graph-tooltip'; // Reuse graph-tooltip styles
                
                // Build compact tooltip content
                const header = document.createElement('div');
                header.className = 'tooltip-header';
                header.textContent = (link.source.label || '?') + ' → ' + (link.target.label || '?');
                
                const content = document.createElement('div');
                content.className = 'tooltip-content';
                
                // Only show type if interesting
                if (link.type === 'circular') {
                    const warningDiv = document.createElement('div');
                    warningDiv.className = 'tooltip-warning';
                    warningDiv.innerHTML = '⚠️ Circular';
                    content.appendChild(warningDiv);
                }
                
                // Add action hint
                const actionDiv = document.createElement('div');
                actionDiv.className = 'tooltip-action';
                actionDiv.textContent = 'click to inspect';
                content.appendChild(actionDiv);
                
                tooltip.appendChild(header);
                tooltip.appendChild(content);
                
                // Position tooltip at top-left of graph container (not document.body)
                const graphView = document.querySelector('.graph-view-content');
                if (graphView) {
                    graphView.appendChild(tooltip);
                } else {
                    svg.parentElement.appendChild(tooltip);
                }
                
                // Tooltip is positioned at top-left via CSS
                // No need for dynamic positioning
            }
            
            function hideLinkTooltip() {
                const existing = document.getElementById('link-tooltip');
                if (existing) existing.remove();
            }
            
            function getLinkTypeLabel(type) {
                const typeLabels = {
                    'import': 'Import Dependency',
                    'circular': 'Circular Reference',
                    'pattern': 'Similar Issues',
                    'directory': 'Same Directory',
                    'fallback': 'Structural Connection'
                };
                return typeLabels[type] || 'Unknown';
            }
            
            function handleLinkClick(link, event) {
                event.stopPropagation();
                
                // Hide tooltips immediately on link click
                hideTooltip();
                hideLinkTooltip();
                
                // Highlight the link and connected nodes
                highlightLinkAndNodes(link);
                
                // Show detailed link analysis
                showLinkAnalysis(link);
            }
            
            function highlightLinkAndNodes(link) {
                // Remove previous highlights
                document.querySelectorAll('.graph-link, .graph-node').forEach(el => {
                    el.classList.remove('highlighted', 'connected');
                });
                
                // Find and highlight the clicked link
                const allLinks = linksGroup.querySelectorAll('.graph-link');
                const allNodes = nodesGroup.querySelectorAll('.graph-node');
                
                // This is a simplified approach - in a real implementation you'd need better link identification
                allLinks.forEach(linkEl => {
                    linkEl.classList.add('highlighted');
                });
                
                // Highlight connected nodes
                allNodes.forEach(nodeEl => {
                    const cx = parseFloat(nodeEl.getAttribute('cx'));
                    const cy = parseFloat(nodeEl.getAttribute('cy'));
                    
                    // Check if this node is the source or target
                    const isSource = Math.abs(cx - link.source.x) < 5 && Math.abs(cy - link.source.y) < 5;
                    const isTarget = Math.abs(cx - link.target.x) < 5 && Math.abs(cy - link.target.y) < 5;
                    
                    if (isSource || isTarget) {
                        nodeEl.classList.add('connected');
                    }
                });
                
                // Remove highlights after a delay
                setTimeout(() => {
                    document.querySelectorAll('.highlighted, .connected').forEach(el => {
                        el.classList.remove('highlighted', 'connected');
                    });
                }, 3000);
            }
            
            function showLinkAnalysis(link) {
                // Create enhanced analysis panel with rich dependency information
                const analysisPanel = document.createElement('div');
                analysisPanel.id = 'link-analysis';
                analysisPanel.className = 'link-analysis';
                
                const header = document.createElement('div');
                header.className = 'analysis-header';
                header.innerHTML = '<h4>Dependency Analysis</h4><button class="close-btn" onclick="this.parentElement.parentElement.remove()">×</button>';
                
                const content = document.createElement('div');
                content.className = 'analysis-content';
                
                // Enhanced dependency details with metadata
                let details = '<div class="analysis-section">' +
                    '<div class="detail-row"><span class="label">From:</span> <span class="value">' + (link.source.label || 'Unknown') + '</span></div>' +
                    '<div class="detail-row"><span class="label">To:</span> <span class="value">' + (link.target.label || 'Unknown') + '</span></div>' +
                    '<div class="detail-row"><span class="label">Type:</span> <span class="value dependency-type-' + link.type + '">' + getDependencyTypeDescription(link.type) + '</span></div>' +
                    '<div class="detail-row"><span class="label">Strength:</span> <span class="value">' + Math.round(link.strength * 100) + '%</span></div>';
                
                // Add metadata if available
                if (link.metadata) {
                    if (link.metadata.symbols && link.metadata.symbols.length > 0) {
                        const symbolsDisplay = link.metadata.symbols.slice(0, 5).join(', ') + (link.metadata.symbols.length > 5 ? '...' : '');
                        details += '<div class="detail-row"><span class="label">Symbols:</span> <span class="value symbols">' + symbolsDisplay + '</span></div>';
                    }
                    
                    if (link.metadata.lines && link.metadata.lines.length > 0) {
                        const linesDisplay = link.metadata.lines.slice(0, 3).join(', ') + (link.metadata.lines.length > 3 ? '...' : '');
                        details += '<div class="detail-row"><span class="label">Lines:</span> <span class="value lines">' + linesDisplay + '</span></div>';
                    }
                    
                    if (link.metadata.bidirectional) {
                        details += '<div class="detail-row"><span class="label">Direction:</span> <span class="value bidirectional">Bidirectional</span></div>';
                    }
                }
                
                details += '</div>';
                
                // Add dependency insights
                details += '<div class="analysis-section">' +
                    '<h5>Analysis</h5>' +
                    getDependencyInsights(link) +
                    '</div>';
                
                content.innerHTML = details;
                
                analysisPanel.appendChild(header);
                analysisPanel.appendChild(content);
                document.body.appendChild(analysisPanel);
                
                // Fullscreen panel - no additional positioning needed (CSS handles it)
                // Panel fills entire viewport and is scrollable
            }
            
            function getDependencyTypeDescription(type) {
                const types = {
                    'import': '📥 Import/Require',
                    'call': '📞 Function Call',
                    'circular': '🔄 Circular Dependency',
                    'export': '📤 Export',
                    'inherit': '🧬 Inheritance'
                };
                return types[type] || '🔗 ' + type;
            }
            
            function getDependencyInsights(link) {
                let insights = '';
                
                switch (link.type) {
                    case 'circular':
                        insights += '<div class="insight warning">⚠️ Circular dependency detected. Consider refactoring to break the cycle.</div>';
                        break;
                    case 'import':
                        if (link.strength > 0.8) {
                            insights += '<div class="insight info">💡 Strong import relationship. Core dependency.</div>';
                        }
                        break;
                    case 'call':
                        insights += '<div class="insight info">🔍 Function call relationship. Runtime dependency.</div>';
                        break;
                }
                
                if (link.metadata && link.metadata.bidirectional) {
                    insights += '<div class="insight warning">⚠️ Bidirectional dependency may indicate tight coupling.</div>';
                }
                
                return insights || '<div class="insight info">📊 Standard dependency relationship.</div>';
            }

            // Helper function to update link positions after layout change
            function updateLinkPositions() {
                const links = document.querySelectorAll('line[data-source]');
                links.forEach(link => {
                    const sourceId = link.getAttribute('data-source').replace(/[\\\\/]/g, '_');
                    const targetId = link.getAttribute('data-target').replace(/[\\\\/]/g, '_');
                    
                    const sourceCircle = document.querySelector('circle[data-node-id="' + sourceId + '"]');
                    const targetCircle = document.querySelector('circle[data-node-id="' + targetId + '"]');
                    
                    if (sourceCircle && targetCircle) {
                        const sourceX = parseFloat(sourceCircle.getAttribute('cx'));
                        const sourceY = parseFloat(sourceCircle.getAttribute('cy'));
                        const targetX = parseFloat(targetCircle.getAttribute('cx'));
                        const targetY = parseFloat(targetCircle.getAttribute('cy'));
                        
                        link.style.transition = 'x1 0.3s ease, y1 0.3s ease, x2 0.3s ease, y2 0.3s ease';
                        link.setAttribute('x1', sourceX.toString());
                        link.setAttribute('y1', sourceY.toString());
                        link.setAttribute('x2', targetX.toString());
                        link.setAttribute('y2', targetY.toString());
                    }
                });
            }

            // Setup graph controls
            function setupGraphControls() {
                // Labels and links checkboxes removed - graph elements always visible
                const graphTypeSelect = document.getElementById('graph-type-select');
                
                // Graph type switching disabled - code kept for future use
                if (false && graphTypeSelect) {
                    const savedGraphType = localStorage.getItem('Aspect Code-graph-type') || '2d';
                    
                    // Only set the value and switch if not already initialized to prevent infinite loops
                    if (!graphTypeSelect.hasAttribute('data-initialized')) {
                        graphTypeSelect.value = savedGraphType;
                        graphTypeSelect.setAttribute('data-initialized', 'true');
                        
                        // Only call switchGraphType if we actually need to change the display
                        const svg = document.getElementById('dependency-graph');
                        const canvas = document.getElementById('dependency-graph-3d');
                        if (savedGraphType === '3d' && svg.style.display !== 'none') {
                            switchGraphType(savedGraphType);
                        } else if (savedGraphType !== '3d' && canvas.style.display !== 'none') {
                            switchGraphType(savedGraphType);
                        }
                    }
                    
                    // Remove old event listener if exists to prevent duplicate listeners
                    if (graphTypeSelect.onchange) {
                        graphTypeSelect.onchange = null;
                    }
                    
                    graphTypeSelect.addEventListener('change', () => {
                        const selectedType = graphTypeSelect.value;
                        localStorage.setItem('Aspect Code-graph-type', selectedType);
                        switchGraphType(selectedType);
                        
                        // Use the appropriate cached graph data instead of currentGraph
                        if (selectedType === '3d') {
                            // 3D uses overview graph - render with cached data if available
                            if (overviewGraph.nodes.length > 0) {
                                render3DGraph(overviewGraph);
                            } else {
                                // Request fresh overview data if not cached
                                vscode.postMessage({ type: 'REQUEST_OVERVIEW_GRAPH' });
                            }
                        } else {
                            // 2D uses focused graph - render with cached data if available  
                            if (focusedGraph.nodes.length > 0) {
                                renderDependencyGraph(focusedGraph);
                            } else {
                                // Request fresh focused data if not cached
                                vscode.postMessage({ type: 'REQUEST_FOCUSED_GRAPH' });
                            }
                        }
                    });
                }
                
                // Layout selection removed - circular layout is always used
                // Labels and links checkboxes removed - always visible
                // Show score checkbox removed - score always hidden
            }

            // Alternative layout algorithms
            function applyLayoutAlgorithm(nodes, layout) {
                const svg = document.getElementById('dependency-graph');
                const containerRect = svg.getBoundingClientRect();
                const width = containerRect.width || 800; // Use actual width, fallback only if 0
                const height = containerRect.height || 300; // Use actual height, fallback only if 0
                const margin = 5; // Absolute minimal margin
                
                switch (layout) {
                    case 'circular':
                        const centerXCircular = width / 2;
                        // Position circle higher - 40% from top instead of centered
                        const centerYCircular = height * 0.40;
                        // Use most of the space but leave margin for labels
                        const radiusCircular = Math.min(width, height) * 0.40; // Use 80% of diameter (40% radius)
                        
                        // Smart angle offset based on number of nodes for better aesthetics
                        let angleOffset = -Math.PI / 2; // Default: start from top (12 o'clock)
                        if (nodes.length === 1) {
                            angleOffset = -Math.PI / 2; // 1 node: top (12 o'clock)
                        } else if (nodes.length === 2) {
                            angleOffset = 0; // 2 nodes: left and right (9 and 3 o'clock)
                        } else if (nodes.length % 2 === 0) {
                            // Even number: offset by half step for symmetry
                            angleOffset = -Math.PI / 2 + (Math.PI / nodes.length);
                        }
                        
                        // Arrange nodes in circle with even spacing
                        nodes.forEach((node, i) => {
                            const angle = (2 * Math.PI * i) / nodes.length + angleOffset;
                            node.x = centerXCircular + radiusCircular * Math.cos(angle);
                            node.y = centerYCircular + radiusCircular * Math.sin(angle);
                        });
                        break;
                        
                    default:
                        // Only circular layout is supported
                        console.warn('Only circular layout is supported, requested:', layout);
                        break;
                }
            }

            // Graph type switching functions
            function switchGraphType(type) {
                const svg = document.getElementById('dependency-graph');
                const canvas = document.getElementById('dependency-graph-3d');
                
                // Store the preference
                localStorage.setItem('Aspect Code-graph-type', type);
                
                if (type === '3d') {
                    svg.style.display = 'none';
                    canvas.style.display = 'block';
                    
                    // If we have overview data, render it immediately
                    if (overviewGraph.nodes.length > 0) {
                        render3DGraph(overviewGraph);
                    } else {
                        // Show loading state for 3D graph
                        const ctx = canvas.getContext('2d');
                        const rect = canvas.getBoundingClientRect();
                        canvas.width = rect.width;
                        canvas.height = rect.height;
                        ctx.clearRect(0, 0, canvas.width, canvas.height);
                        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-editor-background');
                        ctx.fillRect(0, 0, canvas.width, canvas.height);
                        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-descriptionForeground');
                        ctx.font = '14px var(--vscode-font-family)';
                        ctx.textAlign = 'center';
                        ctx.fillText('Loading overview graph...', canvas.width / 2, canvas.height / 2);
                    }
                    
                    // Request overview data for 3D graph
                    vscode.postMessage({ type: 'REQUEST_OVERVIEW_GRAPH' });
                } else {
                    svg.style.display = 'block';
                    canvas.style.display = 'none';
                    
                    // If we have focused data, render it immediately
                    if (focusedGraph.nodes.length > 0) {
                        renderDependencyGraph(focusedGraph);
                    } else {
                        // Show loading state for 2D graph
                        svg.innerHTML = '';
                        const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                        text.setAttribute('x', '300');
                        text.setAttribute('y', '150');
                        text.setAttribute('text-anchor', 'middle');
                        text.setAttribute('fill', getComputedStyle(document.body).getPropertyValue('--vscode-descriptionForeground'));
                        text.setAttribute('font-family', 'var(--vscode-font-family)');
                        text.setAttribute('font-size', '14px');
                        text.textContent = 'Loading focused graph...';
                        svg.appendChild(text);
                        
                        // Request focused data for 2D graph
                        vscode.postMessage({ type: 'REQUEST_FOCUSED_GRAPH' });
                    }
                }
            }

            // Efficient 3D graph renderer - focused on speed, not beauty
            function render3DGraph(graph) {
                const canvas = document.getElementById('dependency-graph-3d');
                const ctx = canvas.getContext('2d');
                
                // Auto-resize canvas
                const rect = canvas.getBoundingClientRect();
                canvas.width = rect.width;
                canvas.height = rect.height;
                
                // Clear canvas
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-editor-background');
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                
                if (!graph || !graph.nodes || graph.nodes.length === 0) {
                    // Draw empty state
                    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-descriptionForeground');
                    ctx.font = '14px var(--vscode-font-family)';
                    ctx.textAlign = 'center';
                    ctx.fillText('No dependencies to display', canvas.width / 2, canvas.height / 2);
                    return;
                }

                // 3D positioning - spread nodes in 3D space, project to 2D
                const nodes3d = graph.nodes.map((node, i) => {
                    // Distribute nodes in a 3D sphere for better visualization of entire codebase
                    const phi = Math.acos(1 - 2 * (i / graph.nodes.length)); // Polar angle
                    const theta = Math.PI * (3 - Math.sqrt(5)) * i; // Azimuthal angle (golden spiral)
                    const r = 150; // Sphere radius
                    
                    return {
                        ...node,
                        x3d: r * Math.sin(phi) * Math.cos(theta),
                        y3d: r * Math.sin(phi) * Math.sin(theta),
                        z3d: r * Math.cos(phi)
                    };
                });

                // Simple 3D to 2D projection (isometric-like)
                const centerX = canvas.width / 2;
                const centerY = canvas.height / 2;
                const scale = Math.min(canvas.width, canvas.height) / 400;

                nodes3d.forEach(node => {
                    // Project 3D to 2D
                    node.x2d = centerX + (node.x3d + node.z3d * 0.5) * scale;
                    node.y2d = centerY + (node.y3d + node.z3d * 0.3) * scale;
                    node.depth = node.z3d; // For depth sorting
                });

                // Sort by depth for proper rendering order
                nodes3d.sort((a, b) => a.depth - b.depth);

                // Render edges first (straight lines only)
                ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--vscode-descriptionForeground');
                ctx.lineWidth = 1;
                ctx.globalAlpha = 0.4;

                graph.links.forEach(link => {
                    const source = nodes3d.find(n => n.id === link.source);
                    const target = nodes3d.find(n => n.id === link.target);
                    
                    if (source && target) {
                        ctx.beginPath();
                        ctx.moveTo(source.x2d, source.y2d);
                        ctx.lineTo(target.x2d, target.y2d);
                        ctx.stroke();
                    }
                });

                // Render nodes
                ctx.globalAlpha = 1;
                nodes3d.forEach(node => {
                    const nodeSize = 3 + (node.depth / 150) * 2; // Vary size by depth
                    
                    // Node circle
                    ctx.beginPath();
                    ctx.arc(node.x2d, node.y2d, nodeSize, 0, 2 * Math.PI);
                    
                    // Color by type/importance
                    if (node.type === 'hub') {
                        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-focusBorder');
                    } else if (node.importance && node.importance > 2) {
                        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-errorForeground');
                    } else {
                        ctx.fillStyle = getComputedStyle(document.body).getPropertyValue('--vscode-symbolIcon-fileForeground');
                    }
                    
                    ctx.fill();
                    ctx.strokeStyle = getComputedStyle(document.body).getPropertyValue('--vscode-foreground');
                    ctx.lineWidth = 0.5;
                    ctx.stroke();
                });

                // Add interaction for file opening
                canvas.onclick = (e) => {
                    const rect = canvas.getBoundingClientRect();
                    const clickX = e.clientX - rect.left;
                    const clickY = e.clientY - rect.top;
                    
                    // Find clicked node
                    for (const node of nodes3d) {
                        const distance = Math.sqrt((clickX - node.x2d) ** 2 + (clickY - node.y2d) ** 2);
                        if (distance < 8 && node.file) { // 8px click tolerance
                            vscode.postMessage({
                                type: 'OPEN_FINDING',
                                file: node.file,
                                line: 1,
                                column: 1
                            });
                            break;
                        }
                    }
                };
            }

            // Setup controls and start simulation
            setupGraphControls();
            
            // Apply selected layout
            // Always use circular layout
            applyLayoutAlgorithm(nodes, 'circular');
            render(); // Single render for static layout
            
            // Legacy force simulation code (no longer used)
            if (false) {
                // Only use animated force simulation when explicitly selected
                requestAnimationFrame(tick); // Animated force simulation
            }
        }
        
        function renderFindings(findings, filterRule = '', state = null) {
            const findingsList = document.getElementById('findings-list');
            const findingsView = document.getElementById('findings-view');
            
            // Always show all findings (no filtering by rule)
            let sortedFindings = findings || [];
            
            // Update view toggle button if we're showing findings
            if (currentView === 'findings') {
                updateViewToggleButton('Show graph', currentGraph?.nodes?.length || 0);
            }
            
            // Clear list
            findingsList.innerHTML = '';
            
            // Remove any existing summary bar
            const existingSummary = findingsView.querySelector('.findings-summary');
            if (existingSummary) {
                existingSummary.remove();
            }
            
            if (sortedFindings.length === 0) {
                findingsList.innerHTML = '<div class="empty-findings">No findings to display</div>';
                return;
            }

            // KB-enriching rules that are purely informational (not problems)
            // These rules provide insights for knowledge base generation, not issues to fix
            const KB_ENRICHING_RULES = new Set([
                'arch.entry_point',
                'arch.external_integration', 
                'arch.data_model'
            ]);
            
            // Helper to determine if a finding is informational (KB-enriching vs actual problem)
            const isInformational = (f) => {
                return f.rule && KB_ENRICHING_RULES.has(f.rule);
            };

            // Calculate breakdown: problems vs informational (KB-enriching insights)
            const breakdown = {
                total: sortedFindings.length,
                problems: sortedFindings.filter(f => !isInformational(f)).length,
                informational: sortedFindings.filter(f => isInformational(f)).length
            };
            
            // Calculate autofix potential using same value as badge
            let autofixScore = 0;
            if (state && state.score && state.score.potentialImprovement) {
                autofixScore = state.score.potentialImprovement;
            }
            
            // Create summary bar and insert it at the top of findings view
            const summaryBar = document.createElement('div');
            summaryBar.className = 'findings-summary';\n            summaryBar.style.marginTop = '-4px';
            findingsView.insertBefore(summaryBar, findingsView.firstChild);
            
            // Create breakdown section
            const breakdownDiv = document.createElement('div');
            breakdownDiv.className = 'findings-breakdown';
            
            // Show problems and informational counts
            const breakdownItems = [
                { number: breakdown.problems, tooltip: 'problems (P0/P1)', type: 'error', filterType: 'problems', show: breakdown.problems > 0 },
                { number: breakdown.informational, tooltip: 'informational (P2/P3)', type: 'info', filterType: 'informational', show: breakdown.informational > 0 }
            ].filter(item => item.show);
            
            breakdownItems.forEach(item => {
                const itemDiv = document.createElement('div');
                itemDiv.className = 'breakdown-item';
                itemDiv.style.cursor = 'pointer';
                
                const dot = document.createElement('div');
                dot.className = 'breakdown-dot ' + item.type;
                dot.title = item.tooltip;
                
                // Apply grayed-out state if filter is disabled
                if (!severityFilters[item.filterType]) {
                    itemDiv.classList.add('filtered-out');
                }
                
                // Add click handler to toggle filter
                itemDiv.addEventListener('click', () => {
                    severityFilters[item.filterType] = !severityFilters[item.filterType];
                    // Re-render findings with current state
                    if (currentState) {
                        renderFindings(currentFindings, '', currentState);
                    }
                });
                
                const label = document.createElement('span');
                label.textContent = item.number.toString();
                
                itemDiv.appendChild(dot);
                itemDiv.appendChild(label);
                breakdownDiv.appendChild(itemDiv);
            });
            
            // Auto-fix potential section disabled - feature temporarily disabled
            /*
            // Create autofix potential section
            const autofixDiv = document.createElement('div');
            autofixDiv.className = 'autofix-potential';
            if (autofixScore > 0) {
                const displayScore = autofixScore.toFixed(1).replace('.0', '');
                autofixDiv.textContent = '+' + displayScore;
                autofixDiv.title = 'Potential score increase from auto-fixes';
            } else {
                autofixDiv.textContent = '+0';
                autofixDiv.style.color = 'var(--vscode-descriptionForeground)';
                autofixDiv.style.fontWeight = 'normal';
            }
            */
            
            summaryBar.appendChild(breakdownDiv);
            // summaryBar.appendChild(autofixDiv); // Auto-fix feature temporarily disabled
            
            // Get current active file for relevance sorting
            const currentFile = currentActiveFile || '';
            
            // Filter findings based on priority filters (problems vs informational)
            const filteredFindings = sortedFindings.filter(finding => {
                if (isInformational(finding)) {
                    return severityFilters.informational;
                } else {
                    return severityFilters.problems;
                }
            });
            
            // Group findings by file + rule
            const groupedFindings = new Map();
            filteredFindings.forEach(finding => {
                const key = finding.file + '::' + finding.rule;
                if (!groupedFindings.has(key)) {
                    groupedFindings.set(key, {
                        finding: finding,
                        count: 1,
                        instances: [finding]
                    });
                } else {
                    const group = groupedFindings.get(key);
                    group.count++;
                    group.instances.push(finding);
                }
            });
            
            // Convert to array for sorting
            const groupedArray = Array.from(groupedFindings.values());
            
            // Smart sorting: 1. Current file first, 2. Severity, 3. Count
            const severityOrder = { error: 0, critical: 0, warn: 1, warning: 1, info: 2 };
            groupedArray.sort((a, b) => {
                // First: Current file gets priority
                const aFile = a.finding.file || '';
                const bFile = b.finding.file || '';
                const aIsCurrent = currentFile && (aFile === currentFile || currentFile.includes(aFile.split('/').pop() || ''));
                const bIsCurrent = currentFile && (bFile === currentFile || currentFile.includes(bFile.split('/').pop() || ''));
                if (aIsCurrent !== bIsCurrent) return bIsCurrent ? 1 : -1;
                
                // Second: Sort by severity
                const aSev = severityOrder[a.finding.severity] ?? 2;
                const bSev = severityOrder[b.finding.severity] ?? 2;
                if (aSev !== bSev) return aSev - bSev;
                
                // Third: More occurrences first
                return b.count - a.count;
            });
            
            // Render grouped findings with improved formatting
            groupedArray.forEach(group => {
                const finding = group.finding;
                const isCurrentFile = currentFile && (finding.file === currentFile || currentFile.includes((finding.file || '').split('/').pop() || ''));
                const item = document.createElement('div');
                item.className = isCurrentFile ? 'finding-item current-file' : 'finding-item';
                item.onclick = () => {
                    openFinding(group.instances[0]);
                    // Scroll to top of findings list when clicking a finding
                    const findingsContainer = document.querySelector('.findings-list');
                    if (findingsContainer) {
                        findingsContainer.scrollTop = 0;
                    }
                };
                
                // Auto-fix badge disabled - feature temporarily disabled
                /*
                // Auto-fix badge if applicable
                let autofixBadge = null;
                if (finding.fixable) {
                    autofixBadge = document.createElement('span');
                    autofixBadge.className = 'autofix-ready-badge';
                    autofixBadge.textContent = 'Auto-fix ready';
                }
                */
                const autofixBadge = null; // Auto-fix feature temporarily disabled
                
                // Main content container
                const content = document.createElement('div');
                content.className = 'finding-content';
                
                // Message text with count badge
                const messageDiv = document.createElement('div');
                messageDiv.className = 'finding-message';
                messageDiv.textContent = finding.message || 'No message';
                
                // Add count badge if multiple instances
                if (group.count > 1) {
                    const countBadge = document.createElement('span');
                    countBadge.className = 'finding-count';
                    countBadge.textContent = group.count.toString();
                    countBadge.title = group.count + ' instances in this file';
                    messageDiv.appendChild(countBadge);
                }
                
                // Auto-fix badge on its own line if applicable
                let autofixLine = null;
                if (autofixBadge) {
                    autofixLine = document.createElement('div');
                    autofixLine.className = 'autofix-ready-line';
                    autofixLine.appendChild(autofixBadge);
                }
                
                // File info with relative path
                const fileDiv = document.createElement('div');
                fileDiv.className = 'finding-file';
                
                // Calculate relative path if workspace root is available
                let displayPath = finding.file || 'Unknown file';
                try {
                    if (currentState && currentState.workspaceRoot && finding.file) {
                        if (finding.file.startsWith(currentState.workspaceRoot)) {
                            displayPath = finding.file.substring(currentState.workspaceRoot.length).replace(/^[/\\\\]/, '');
                        } else {
                            // If not in workspace, just show filename
                            displayPath = (finding.file || '').split(/[/\\\\]/).pop() || 'Unknown file';
                        }
                    } else {
                        // Fallback to filename only if no workspace root available
                        displayPath = (finding.file || '').split(/[/\\\\]/).pop() || 'Unknown file';
                    }
                } catch (error) {
                    console.error('[Panel] Error calculating relative path:', error);
                    displayPath = (finding.file || '').split(/[/\\\\]/).pop() || 'Unknown file';
                }
                
                const line = finding.span?.start?.line || finding.line || 1;
                fileDiv.textContent = displayPath + ':' + line;
                
                content.appendChild(messageDiv);
                if (autofixLine) {
                    content.appendChild(autofixLine);
                }
                content.appendChild(fileDiv);
                
                item.appendChild(content);
                
                findingsList.appendChild(item);
            });
        }
        
        function openFinding(finding) {
            if (finding.file) {
                const line = finding.span?.start?.line || 1;
                const column = finding.span?.start?.column || 1;
                vscode.postMessage({
                    type: 'OPEN_FINDING',
                    file: finding.file,
                    line: line,
                    column: column
                });
            }
        }
        
        function calculateScore(findings) {
            if (!findings || findings.length === 0) return '—';
            
            // Simple scoring: start at 100, deduct points for findings
            let score = 100;
            findings.forEach(f => {
                switch (f.severity) {
                    case 'error': score -= 5; break;
                    case 'warn': score -= 2; break;
                    case 'info': score -= 1; break;
                    default: score -= 2; break;
                }
            });
            
            return Math.max(0, score);
        }
        
        // Request initial state and dependency graph
        vscode.postMessage({ type: 'PANEL_READY' });
        // Request initial graph based on dropdown preference
        const savedGraphType = localStorage.getItem('Aspect Code-graph-type') || '2d';
        if (savedGraphType === '3d') {
            vscode.postMessage({ type: 'REQUEST_OVERVIEW_GRAPH' });
        } else {
            vscode.postMessage({ type: 'REQUEST_FOCUSED_GRAPH' });
        }
        
        // Handle state updates from extension
        window.addEventListener('message', (event) => {
            const msg = event.data;
            switch (msg.type) {
                case 'STATE_UPDATE':
                    render(msg.state);
                    break;
                case 'DEPENDENCY_GRAPH':
                    // Store graph data based on focus mode
                    if (msg.graph.focusMode) {
                        focusedGraph = msg.graph;
                        
                        // Always render 2D focused graph (3D disabled)
                        renderDependencyGraph(focusedGraph);
                    } else {
                        overviewGraph = msg.graph;
                        
                        // 3D overview disabled - render as 2D
                        renderDependencyGraph(overviewGraph);
                    }
                    break;
                case 'START_AUTOMATIC_PROCESSING':
                    // Start automatic processing with the same UI as manual reload
                    setTimeout(() => startAutomaticProcessing(), 500);
                    break;
                case 'PROGRESS_UPDATE':
                    // Handle real progress updates from backend
                    handleRealProgress(msg.phase, msg.percentage, msg.message);
                    break;
                case 'INCREMENTAL_UPDATE':
                    // Incremental validation complete - no toast notification needed
                    // The spinner already indicates when validation is in progress
                    break;
                case 'ACTIVE_FILE_CHANGED':
                    // Update current file and re-render findings if on findings tab
                    currentActiveFile = msg.file;
                    if (currentView === 'findings' && currentFindings.length > 0) {
                        renderFindings(currentFindings, '', currentState);
                    }
                    break;
                case 'AUTO_FIX_SAFE_COMPLETE':
                    // Re-enable the auto-fix button immediately when command completes
                    const btn = document.getElementById('auto-fix-safe-button');
                    if (btn) {
                        btn.disabled = false;
                    }
                    break;
                case 'INSTRUCTION_FILES_STATUS':
                    // Show/hide the generate instructions button based on whether files exist
                    const generateBtn = document.getElementById('generate-instructions-btn');
                    if (generateBtn) {
                        generateBtn.style.display = msg.hasFiles ? 'none' : 'flex';
                    }
                    break;
                case 'ALIGNMENTS_FILE_STATUS':
                    // Show/hide the align button based on whether ALIGNMENTS.json exists
                    const alignBtn = document.getElementById('align-button');
                    if (alignBtn) {
                        alignBtn.style.display = msg.hasFile ? 'inline-flex' : 'none';
                    }
                    break;
            }
        });
        
        // Handle real progress updates from backend
        function handleRealProgress(phase, percentage, message) {
            const validationSpinner = document.getElementById('validation-spinner');
            
            // Show/hide inline validation spinner for all processing phases
            if (phase === 'validation' || phase === 'indexing' || phase === 'examination') {
                if (percentage > 0 && percentage < 100) {
                    validationSpinner?.classList.add('active');
                } else if (percentage >= 100 || percentage === 0) {
                    validationSpinner?.classList.remove('active');
                }
            }
            
            if (manualProcessingActive) {
                const scoreEl = document.getElementById('score');
                const detailsEl = document.getElementById('score-details');
                
                // Update score display
                scoreEl.textContent = '—';
                scoreEl.style.color = 'var(--vscode-descriptionForeground)';
                detailsEl.textContent = message;
                
                // Update progress bar
                showProgress('', Math.max(5, Math.min(100, percentage)));
            }
        }
        
        // Automatic processing with same UI as manual reload
        async function startAutomaticProcessing() {
            manualProcessingActive = true; // Use same flag for consistency
            
            const scoreEl = document.getElementById('score');
            const detailsEl = document.getElementById('score-details');
            scoreEl.textContent = '—';
            scoreEl.style.color = 'var(--vscode-descriptionForeground)';
            detailsEl.textContent = 'Starting indexing...';
            showProgress('', 5);
            
            try {
                // Send index command and wait
                vscode.postMessage({ type: 'COMMAND', command: 'aspectcode.index' });
                await new Promise(resolve => setTimeout(resolve, 3000));
                
                // Transition to validation
                detailsEl.textContent = 'Running validation...';
                showProgress('', 50);
                
                // Send validate command and wait
                vscode.postMessage({ type: 'COMMAND', command: 'aspectcode.examine' });
                await new Promise(resolve => setTimeout(resolve, 5000));
                
                // Final completion
                showProgress('', 100);
                detailsEl.textContent = 'Complete';
                
            } finally {
                setTimeout(() => {
                    hideProgress();
                    // manualProcessingActive is now cleared in render function
                }, 1000);
            }
        }
        
        function render(state) {
            currentState = state; // Store for later use
            const previousFindingsCount = currentFindings.length;
            currentFindings = (state.findings || []).slice();
            
            // If findings count changed significantly, clear cached graph data
            // But preserve user's current view unless there's a major change
            const findingsDelta = Math.abs(currentFindings.length - previousFindingsCount);
            const shouldClearCache = findingsDelta > 5 || (previousFindingsCount === 0 && currentFindings.length > 0);
            
            if (shouldClearCache) {
                focusedGraph = { nodes: [], links: [] };
                overviewGraph = { nodes: [], links: [] };
            }
            
            // Clear manual processing flag when we detect processing is complete
            // (we have findings and backend is not busy)
            if (manualProcessingActive && !state.busy && currentFindings.length > 0) {
                manualProcessingActive = false;
                // Also ensure action buttons are enabled
                const autoFixBtn = document.getElementById('auto-fix-safe-button');
                const explainBtn = document.getElementById('explain-button');
                const proposeBtn = document.getElementById('propose-button');
                if (autoFixBtn) autoFixBtn.disabled = false;
                if (explainBtn) explainBtn.disabled = false;
                if (proposeBtn) proposeBtn.disabled = false;
                hideProgress();
            }
            
            // Update score display based on state and processing status
            if (manualProcessingActive) {
                // During manual processing, keep score as dash - don't update score
                // But do allow button state updates in case we missed the completion
                if (!state.busy && currentFindings.length > 0) {
                    // Processing seems done, clear the flag and continue to score display
                    manualProcessingActive = false;
                }
            }
            
            if (!manualProcessingActive) {
                if (state.busy) {
                    // Show processing indicator during actual backend processing
                    document.getElementById('score').textContent = '—';
                    document.getElementById('score-details').textContent = 'Processing...';
                    document.getElementById('score').style.color = 'var(--vscode-descriptionForeground)';
                } else if (state.score) {
                    // Show actual score when we have a valid score object
                    document.getElementById('score').textContent = state.score.overall.toFixed(1);
                    
                    // Update score details with actual scoring breakdown
                    const details = document.getElementById('score-details');
                    const totalFindings = state.score.breakdown.totalFindings || 0;
                    const totalDeductions = state.score.breakdown.totalDeductions || 0;
                    details.textContent = \`\${totalFindings} findings | \${totalDeductions.toFixed(1)} deductions\`;
                    
                    // Color code the score
                    const scoreEl = document.getElementById('score');
                    // Always use primary orange color for score
                    scoreEl.style.color = 'var(--vscode-charts-orange)';
                    hideProgress();
                } else if (currentFindings.length === 0 && !state.busy) {
                    // No findings and not processing - show placeholder
                    document.getElementById('score').textContent = '—';
                    document.getElementById('score-details').textContent = 'No findings';
                    document.getElementById('score').style.color = 'var(--vscode-descriptionForeground)';
                    hideProgress();
                } else {
                    // Fallback to old scoring function if needed
                    const score = calculateScore(currentFindings);
                    document.getElementById('score').textContent = score;
                    document.getElementById('score-details').textContent = '';
                    hideProgress();
                }
            }
            
            // Render findings without any filter (since we removed the rule dropdown)
            renderFindings(currentFindings, '', state);
            
            // Request graph data update when state changes with new findings
            // Only request if we don't already have graph data to avoid overriding user's current view
            if (!state.busy && currentFindings.length > 0) {
                const graphTypeSelect = document.getElementById('graph-type-select');
                const currentGraphType = graphTypeSelect ? graphTypeSelect.value : '2d';
                
                // Only request graph data if we don't have any cached yet
                const hasGraphData = (currentGraphType === '3d' && overviewGraph.nodes.length > 0) 
                                  || (currentGraphType === '2d' && focusedGraph.nodes.length > 0);
                
                if (!hasGraphData) {
                    if (currentGraphType === '3d') {
                        vscode.postMessage({ type: 'REQUEST_OVERVIEW_GRAPH' });
                    } else {
                        vscode.postMessage({ type: 'REQUEST_FOCUSED_GRAPH' });
                    }
                }
            }
            
            // Update button state and score improvement badge
            const autoFixBtn = document.getElementById('auto-fix-safe-button');
            const explainBtn = document.getElementById('explain-button');
            const proposeBtn = document.getElementById('propose-button');
            if (autoFixBtn) {
                autoFixBtn.disabled = !!state.busy || manualProcessingActive;
                
                // Update score improvement badge
                // updateAutoFixBadge(autoFixBtn, state); // Removed - score now in summary bar
            }
            if (explainBtn) explainBtn.disabled = !!state.busy || manualProcessingActive;
            if (proposeBtn) proposeBtn.disabled = !!state.busy || manualProcessingActive;
        }
        
        function showProgress(phase, progress) {
            const loadingSpinner = document.getElementById('loading-spinner');
            const scoreNumber = document.getElementById('score');
            const scoreLabel = document.querySelector('.score-label');
            const scoreDetails = document.getElementById('score-details');
            
            if (loadingSpinner) {
                loadingSpinner.style.display = 'flex';
            }
            // Hide the score elements while loading
            if (scoreNumber) {
                scoreNumber.style.visibility = 'hidden';
            }
            if (scoreLabel) {
                scoreLabel.style.visibility = 'hidden';
            }
            if (scoreDetails) {
                scoreDetails.style.visibility = 'hidden';
            }
        }
        
        function hideProgress() {
            const loadingSpinner = document.getElementById('loading-spinner');
            const scoreNumber = document.getElementById('score');
            const scoreLabel = document.querySelector('.score-label');
            const scoreDetails = document.getElementById('score-details');
            
            if (loadingSpinner) {
                loadingSpinner.style.display = 'none';
            }
            // Restore score elements visibility
            if (scoreNumber) {
                scoreNumber.style.visibility = 'visible';
            }
            if (scoreLabel) {
                scoreLabel.style.visibility = 'visible';
            }
            if (scoreDetails) {
                scoreDetails.style.visibility = 'visible';
            }
        }
        
        // Show toast notification
        function showToast(message, type = 'info') {
            const toast = document.createElement('div');
            toast.className = \`toast \${type}\`;
            toast.textContent = message;
            document.body.appendChild(toast);
            
            // Auto-remove after 2 seconds
            setTimeout(() => {
                toast.classList.add('fade-out');
                setTimeout(() => toast.remove(), 300);
            }, 2000);
        }
        
        function updateAutoFixBadge(button, state) {
            // Remove existing badge if present
            const existingBadge = button.querySelector('.improvement-badge');
            if (existingBadge) {
                existingBadge.remove();
            }
            
            // Calculate potential improvement from score
            let potentialImprovement = 0;
            if (state.score && state.score.potentialImprovement) {
                potentialImprovement = state.score.potentialImprovement;
            }
            
            // Add badge if there's potential improvement
            if (potentialImprovement > 0) {
                const badge = document.createElement('span');
                badge.className = 'improvement-badge';
                badge.textContent = '+' + potentialImprovement.toFixed(1);
                badge.title = 'Auto-fixing could improve score by ' + potentialImprovement.toFixed(1) + ' points';
                button.appendChild(badge);
            }
        }
        
        // Initialize default tab (graph tab is already active in HTML)
        
        // Handle window resize - re-render graph with circular layout for responsive sizing
        window.addEventListener('resize', () => {
            if (currentView === 'graph' && currentGraph && currentGraph.nodes.length > 0) {
                setTimeout(() => renderDependencyGraph(currentGraph), 100);
            }
        });
        
        // Handle visibility change to re-render graph if needed
        document.addEventListener('visibilitychange', () => {
            if (!document.hidden && currentGraph && currentGraph.nodes.length > 0 && currentView === 'graph') {
                setTimeout(() => renderDependencyGraph(currentGraph), 100);
            }
        });
    </script>
</body>
</html>`;
  }
}
