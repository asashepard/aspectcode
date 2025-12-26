/**
 * Incremental Indexer Service
 * 
 * Provides fast, dependency-aware re-indexing and examination on file saves.
 * Uses cached dependency graph to determine which files need re-examination.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';
import { AspectCodeState } from '../state';
import { getHeaders, handleHttpError, getBaseUrl } from '../http';
import type { CacheManager } from './CacheManager';

interface FileSnapshot {
  filePath: string;
  lastModified: number;
  symbolsHash: string; // Quick diff check for symbols (imports, exports, functions, classes)
  contentHash: string; // Hash of normalized content (ignoring whitespace) for code changes
  imports: string[];
  exports: string[];
  functions: string[];
  classes: string[];
}

interface ValidationScope {
  changedFile: string;
  affectedFiles: Set<string>;
  reason: 'import_change' | 'dependency_change' | 'direct_change' | 'style_change';
  estimatedTimeMs: number;
}

type ChangeType = 
  | 'no_change' 
  | 'content_changed' 
  | 'imports_changed' 
  | 'exports_changed' 
  | 'symbols_changed' 
  | 'new_file';

export class IncrementalIndexer {
  // In-memory caches for fast lookups
  private fileSnapshots = new Map<string, FileSnapshot>();
  private dependencyGraph = new Map<string, Set<string>>(); // file -> dependents (who imports this)
  private reverseDependencyGraph = new Map<string, Set<string>>(); // file -> dependencies (what this imports)
  private pendingSaves = new Map<string, NodeJS.Timeout>();
  
  private readonly DEBOUNCE_MS: number;
  private readonly MAX_AFFECTED_FILES: number;
  private readonly MAX_TRANSITIVE_DEPTH: number;
  
  private _initialized = false;
  
  // Cache manager reference (set externally after construction)
  private _cacheManager: CacheManager | null = null;
  
  constructor(
    private state: AspectCodeState,
    private dependencyAnalyzer: DependencyAnalyzer,
    private outputChannel: vscode.OutputChannel
  ) {
    // Load configuration
    const config = vscode.workspace.getConfiguration('Aspect Code');
    this.DEBOUNCE_MS = config.get<number>('incremental.debounceMs', 300);
    this.MAX_AFFECTED_FILES = config.get<number>('incremental.maxAffectedFiles', 50);
    this.MAX_TRANSITIVE_DEPTH = config.get<number>('incremental.maxTransitiveDepth', 3);
  }

  /**
   * Set the cache manager reference
   */
  setCacheManager(cacheManager: CacheManager): void {
    this._cacheManager = cacheManager;
  }

  /**
   * Persist current state to cache file
   */
  private async persistCache(): Promise<void> {
    if (!this._cacheManager) {
      return;
    }
    
    try {
      // Build file signatures
      const signatures = await this._cacheManager.buildFileSignatures();
      
      // Convert findings to cache format
      const findings = this._cacheManager.findingsToCache(this.state.s.findings || []);
      
      // Convert dependency graph to cache format
      const dependencies = this._cacheManager.dependenciesToCache(this.reverseDependencyGraph);
      
      // Get last examine stats
      const lastValidate = this.state.s.lastValidate ? {
        total: this.state.s.lastValidate.total,
        fixable: this.state.s.lastValidate.fixable,
        tookMs: this.state.s.lastValidate.tookMs
      } : undefined;
      
      await this._cacheManager.saveCache(signatures, findings, dependencies, lastValidate);
    } catch (error) {
      this.outputChannel.appendLine(`[IncrementalIndexer] Failed to persist cache: ${error}`);
    }
  }

  /**
   * Send progress update to panel for spinner visibility
   */
  private sendProgressToPanel(phase: string, percentage: number, message: string): void {
    try {
      const panelProvider = (this.state as any)._panelProvider;
      if (panelProvider && typeof panelProvider.post === 'function') {
        panelProvider.post({
          type: 'PROGRESS_UPDATE',
          phase,
          percentage,
          message
        });
      }
    } catch (error) {
      // Silently ignore - panel might not be ready
    }
  }

  /**
   * Initialize by building full dependency graph and snapshots
   */
  async initialize(workspaceFiles: string[]): Promise<void> {
    if (this._initialized) {
      this.outputChannel.appendLine('[IncrementalIndexer] Already initialized, skipping');
      return;
    }
    
    this.outputChannel.appendLine('[IncrementalIndexer] Initializing...');
    const startTime = Date.now();
    
    try {
      // 1. Analyze all dependencies
      this.outputChannel.appendLine(`[IncrementalIndexer] Analyzing dependencies for ${workspaceFiles.length} files...`);
      const links = await this.dependencyAnalyzer.analyzeDependencies(workspaceFiles);
      this.buildDependencyMaps(links);
      
      // 2. Create snapshots for all files in parallel batches (much faster than sequential)
      this.outputChannel.appendLine('[IncrementalIndexer] Creating file snapshots...');
      const snapshotStartTime = Date.now();
      let snapshotCount = 0;
      const BATCH_SIZE = 100;
      
      for (let i = 0; i < workspaceFiles.length; i += BATCH_SIZE) {
        const batch = workspaceFiles.slice(i, i + BATCH_SIZE);
        const results = await Promise.allSettled(
          batch.map(file => this.createFileSnapshot(file))
        );
        
        for (const result of results) {
          if (result.status === 'fulfilled') {
            snapshotCount++;
          }
        }
      }
      
      const snapshotDuration = Date.now() - snapshotStartTime;
      this.outputChannel.appendLine(`[IncrementalIndexer] Snapshots: ${snapshotCount}/${workspaceFiles.length} in ${snapshotDuration}ms`);
      
      const duration = Date.now() - startTime;
      this.outputChannel.appendLine(
        `[IncrementalIndexer] ✓ Initialized ${snapshotCount}/${workspaceFiles.length} files in ${duration}ms`
      );
      
      this._initialized = true;
    } catch (error) {
      this.outputChannel.appendLine(`[IncrementalIndexer] Initialization failed: ${error}`);
      throw error;
    }
  }

  /**
   * Check if indexer is initialized
   */
  isInitialized(): boolean {
    return this._initialized;
  }

  /**
   * Restore dependency graph from cached data (for startup)
   * This allows incremental examination before full INDEX is run
   */
  restoreDependencyGraph(reverseDeps: Map<string, Set<string>>): void {
    this.reverseDependencyGraph = reverseDeps;
    
    // Build forward graph from reverse graph
    this.dependencyGraph.clear();
    for (const [file, deps] of reverseDeps) {
      for (const dep of deps) {
        if (!this.dependencyGraph.has(dep)) {
          this.dependencyGraph.set(dep, new Set());
        }
        this.dependencyGraph.get(dep)!.add(file);
      }
    }
    
    // Mark as initialized since we have a valid dependency graph
    this._initialized = true;
    
    this.outputChannel.appendLine(
      `[IncrementalIndexer] Restored dependency graph: ${reverseDeps.size} files, ready for incremental updates`
    );
  }

  /**
   * Get the reverse dependency graph (file -> what it imports)
   * Used by CacheManager to persist the graph
   */
  getReverseDependencyGraph(): Map<string, Set<string>> {
    return this.reverseDependencyGraph;
  }

  /**
   * Handle bulk file changes (e.g., git undo/discard, multiple file rollback)
   * Uses incremental examination instead of full repository scan
   */
  async handleBulkChange(changedFiles: string[]): Promise<void> {
    if (!this._initialized) {
      this.outputChannel.appendLine('[IncrementalIndexer] Not initialized, cannot do incremental bulk examination');
      return;
    }
    
    const startTime = Date.now();
    this.outputChannel.appendLine(`\n[IncrementalIndexer] Processing bulk change: ${changedFiles.length} files`);
    
    // Set busy state to show loading indicators
    this.state.update({ busy: true });
    
    // Show inline spinner
    this.sendProgressToPanel('examination', 10, `Validating ${changedFiles.length} files...`);
    
    try {
      // Collect all affected files (union of all changed files + their dependents)
      const affectedFiles = new Set<string>();
      
      for (const filePath of changedFiles) {
        // Add the file itself
        affectedFiles.add(filePath);
        
        // Update snapshot and detect change type
        const changeType = await this.updateFileSnapshot(filePath);
        
        // If imports/exports changed, update dependency graph
        if (changeType === 'imports_changed' || changeType === 'exports_changed') {
          await this.updateDependencyGraph(filePath);
        }
        
        // Add dependents based on change type
        if (changeType === 'imports_changed' || changeType === 'exports_changed') {
          this.addTransitiveDependents(filePath, affectedFiles, 2);
          const deps = this.reverseDependencyGraph.get(filePath);
          if (deps) {
            deps.forEach(dep => affectedFiles.add(dep));
          }
        } else if (changeType === 'symbols_changed') {
          this.addTransitiveDependents(filePath, affectedFiles, 1);
        }
      }
      
      this.outputChannel.appendLine(
        `[IncrementalIndexer] Bulk scope: ${affectedFiles.size} total affected files`
      );
      
      // Build examination scope
      const scope: ValidationScope = {
        changedFile: changedFiles[0], // Primary file for logging
        affectedFiles,
        reason: 'direct_change',
        estimatedTimeMs: this.estimateValidationTime(affectedFiles.size)
      };
      
      // Re-examine with timeout
      const timeoutMs = 60000; // 60 second timeout for bulk operations
      const validationPromise = this.revalidateFiles(scope);
      const timeoutPromise = new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error('Bulk examination timeout')), timeoutMs)
      );
      
      await Promise.race([validationPromise, timeoutPromise]);
      
      const duration = Date.now() - startTime;
      this.outputChannel.appendLine(
        `[IncrementalIndexer] ✓ Bulk examination complete in ${duration}ms (${affectedFiles.size} files)`
      );

      // Hide inline spinner
      this.sendProgressToPanel('examination', 100, 'Complete');

      // Note: KB files (.aspect/) are regenerated on-demand when user clicks '+' button
      // This avoids redundant regeneration on every examination
      
      // Update last examine info with bulk change marker
      const fixableCount = this.state.s.findings?.filter(f => f.fixable)?.length ?? 0;
      this.state.update({
        lastValidate: {
          total: this.state.s.findings?.length ?? 0,
          fixable: fixableCount,
          byCode: {},
          tookMs: duration
        }
      });

      // Persist cache for instant startup next time
      await this.persistCache();
      
    } catch (error) {
      // Hide inline spinner on error
      this.sendProgressToPanel('examination', 0, 'Error');
      
      this.outputChannel.appendLine(`[IncrementalIndexer] Bulk examination error: ${error}`);
      throw error;
    } finally {
      this.state.update({ busy: false });
    }
  }

  /**
   * Handle file save with debouncing and smart scoping
   */
  async handleFileSave(document: vscode.TextDocument): Promise<void> {
    if (!this._initialized) {
      this.outputChannel.appendLine('[IncrementalIndexer] Not initialized, skipping incremental examination');
      return;
    }
    
    const filePath = document.fileName;
    
    // Check if incremental examination is enabled
    const config = vscode.workspace.getConfiguration('Aspect Code');
    const enabled = config.get<boolean>('incremental.enabled', true);
    if (!enabled) {
      return;
    }
    
    // Clear any pending save for this file
    const existingTimeout = this.pendingSaves.get(filePath);
    if (existingTimeout) {
      clearTimeout(existingTimeout);
    }
    
    // Debounce to batch rapid saves (user typing, auto-format, etc.)
    const timeout = setTimeout(async () => {
      this.pendingSaves.delete(filePath);
      await this.processFileSave(filePath);
    }, this.DEBOUNCE_MS);
    
    this.pendingSaves.set(filePath, timeout);
  }

  /**
   * Core incremental examination logic
   */
  private async processFileSave(filePath: string): Promise<void> {
    const startTime = Date.now();
    this.outputChannel.appendLine(`\n[IncrementalIndexer] Processing save: ${path.basename(filePath)}`);
    
    // Set busy state to show loading indicators
    this.state.update({ busy: true });
    
    // Show inline spinner
    this.sendProgressToPanel('examination', 10, 'Validating...');
    
    try {
      // 1. Update snapshot and detect what changed
      const changeType = await this.updateFileSnapshot(filePath);
      
      // IMPORTANT: Even if symbols didn't change, we still need to examine the file itself
      // for style rules (trailing whitespace, missing newlines, etc.) and content-based rules
      // (unused variables, duplicate code, etc.). We only skip examination of DEPENDENT files.
      if (changeType === 'no_change') {
        this.outputChannel.appendLine(
          `[IncrementalIndexer] No symbol changes (whitespace/content only) - validating file only, skipping dependents`
        );
        // Continue to examine this file, but with minimal scope
      }
      
      // 2. If imports changed, update dependency graph
      if (changeType === 'imports_changed' || changeType === 'exports_changed') {
        await this.updateDependencyGraph(filePath);
      }
      
      // 3. Determine examination scope
      const scope = this.determineValidationScope(filePath, changeType);
      
      this.outputChannel.appendLine(
        `[IncrementalIndexer] Scope: ${scope.affectedFiles.size} files (${scope.reason})`
      );
      
      // 4. Re-examine affected files with timeout
      const timeoutMs = 30000; // 30 second timeout
      const validationPromise = this.revalidateFiles(scope);
      const timeoutPromise = new Promise<never>((_, reject) => 
        setTimeout(() => reject(new Error('examination timeout')), timeoutMs)
      );
      
      await Promise.race([validationPromise, timeoutPromise]);
      
      const duration = Date.now() - startTime;
      this.outputChannel.appendLine(
        `[IncrementalIndexer] ✓ Complete in ${duration}ms`
      );

      // Hide inline spinner
      this.sendProgressToPanel('examination', 100, 'Complete');

      // Note: KB files (.aspect/) are regenerated on-demand when user clicks '+' button
      // This avoids redundant regeneration on every file save

      // Persist cache for instant startup next time
      await this.persistCache();
      
    } catch (error) {
      // Hide inline spinner on error
      this.sendProgressToPanel('examination', 0, 'Error');
      
      this.outputChannel.appendLine(`[IncrementalIndexer] Error: ${error}`);
      this.outputChannel.appendLine(`[IncrementalIndexer] Falling back to manual examination`);
      
      // Show warning to user
      vscode.window.showWarningMessage(
        `Incremental examination failed: ${error}. Run "Aspect Code: examine" to re-examine.`,
        'examine Now'
      ).then(choice => {
        if (choice === 'examine Now') {
          vscode.commands.executeCommand('aspectcode.examine');
        }
      });
    } finally {
      // ALWAYS clear busy state, even on error or timeout
      this.state.update({ busy: false });
    }
  }

  /**
   * Update snapshot and detect change type
   */
  private async updateFileSnapshot(filePath: string): Promise<ChangeType> {
    const oldSnapshot = this.fileSnapshots.get(filePath);
    const newSnapshot = await this.createFileSnapshot(filePath);
    
    if (!oldSnapshot) {
      return 'new_file';
    }
    
    // Check if symbols changed
    const symbolsChanged = oldSnapshot.symbolsHash !== newSnapshot.symbolsHash;
    
    // Check if content changed (ignoring whitespace)
    const contentChanged = oldSnapshot.contentHash !== newSnapshot.contentHash;
    
    if (!symbolsChanged && !contentChanged) {
      return 'no_change'; // Only whitespace/formatting changed
    }
    
    // Detailed comparison
    const importsChanged = !this.arraysEqual(oldSnapshot.imports, newSnapshot.imports);
    const exportsChanged = !this.arraysEqual(oldSnapshot.exports, newSnapshot.exports);
    const symbolDefsChanged = 
      !this.arraysEqual(oldSnapshot.functions, newSnapshot.functions) ||
      !this.arraysEqual(oldSnapshot.classes, newSnapshot.classes);
    
    if (importsChanged) {
      return 'imports_changed';
    } else if (exportsChanged) {
      return 'exports_changed';
    } else if (symbolDefsChanged) {
      return 'symbols_changed';
    }
    
    return 'content_changed';
  }

  /**
   * Determine which files need re-examination based on change type
   */
  private determineValidationScope(
    changedFile: string,
    changeType: ChangeType
  ): ValidationScope {
    const affectedFiles = new Set<string>([changedFile]);
    let reason: ValidationScope['reason'] = 'direct_change';
    
    // ALWAYS include immediate dependents (files that import the changed file)
    // This ensures rules like "unused export" and "missing import" are properly updated
    const immediateDependents = this.dependencyGraph.get(changedFile);
    if (immediateDependents) {
      for (const dep of immediateDependents) {
        affectedFiles.add(dep);
      }
      if (immediateDependents.size > 0) {
        this.outputChannel.appendLine(
          `[IncrementalIndexer] Including ${immediateDependents.size} immediate dependents`
        );
      }
    }
    
    // ALWAYS include immediate dependencies (files this file imports)
    // This ensures "unused import" rules are updated when imported file changes
    const immediateDependencies = this.reverseDependencyGraph.get(changedFile);
    if (immediateDependencies) {
      for (const dep of immediateDependencies) {
        affectedFiles.add(dep);
      }
      if (immediateDependencies.size > 0) {
        this.outputChannel.appendLine(
          `[IncrementalIndexer] Including ${immediateDependencies.size} immediate dependencies`
        );
      }
    }
    
    switch (changeType) {
      case 'imports_changed':
      case 'exports_changed':
        // Import/export changes affect transitive dependents too
        reason = 'import_change';
        this.addTransitiveDependents(changedFile, affectedFiles, 2);
        break;
        
      case 'symbols_changed':
        // Symbol changes affect immediate dependents (already added above)
        reason = 'dependency_change';
        break;
        
      case 'no_change':
        // Only whitespace/style changes - examine just this file for style rules
        // Don't include dependents for pure whitespace changes
        reason = 'style_change';
        affectedFiles.clear();
        affectedFiles.add(changedFile);
        break;
        
      case 'content_changed':
      case 'new_file':
        // Content changes - immediate dependents already added above
        reason = 'direct_change';
        break;
    }
    
    // Safety limit
    if (affectedFiles.size > this.MAX_AFFECTED_FILES) {
      this.outputChannel.appendLine(
        `[IncrementalIndexer] Scope too large (${affectedFiles.size}), limiting to ${this.MAX_AFFECTED_FILES}`
      );
      const limited = Array.from(affectedFiles).slice(0, this.MAX_AFFECTED_FILES);
      affectedFiles.clear();
      limited.forEach(f => affectedFiles.add(f));
    }
    
    return {
      changedFile,
      affectedFiles,
      reason,
      estimatedTimeMs: this.estimateValidationTime(affectedFiles.size)
    };
  }

  /**
   * Add transitive dependents up to maxDepth
   */
  private addTransitiveDependents(
    file: string,
    result: Set<string>,
    maxDepth: number,
    currentDepth: number = 0,
    visited: Set<string> = new Set()
  ): void {
    // Prevent infinite recursion
    if (currentDepth >= maxDepth) return;
    if (visited.has(file)) return; // Already processed this file
    if (result.size > this.MAX_AFFECTED_FILES) return; // Safety limit
    
    visited.add(file);
    
    const dependents = this.dependencyGraph.get(file);
    if (!dependents) return;
    
    for (const dependent of dependents) {
      if (!result.has(dependent)) {
        result.add(dependent);
        this.addTransitiveDependents(dependent, result, maxDepth, currentDepth + 1, visited);
      }
    }
  }

  /**
   * Re-examine specific files and merge results
   */
  private async revalidateFiles(scope: ValidationScope): Promise<void> {
    const apiUrl = getBaseUrl();
    
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    if (!workspaceRoot) return;
    
    // Call examination API with affected files only
    const relativePaths = Array.from(scope.affectedFiles).map(f => 
      path.relative(workspaceRoot, f).replace(/\\/g, '/')
    );
    
    const payload = {
      repo_root: workspaceRoot,
      paths: relativePaths,  // Use 'paths' field for path-based filtering, not 'files' (which expects FileContent objects)
      incremental: true,
      modes: ['structure', 'types']
    };
    
    this.outputChannel.appendLine(`[IncrementalIndexer] Validating files: ${relativePaths.join(', ')}`);
    
    try {
      // Add timeout to API call
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 25000); // 25 second timeout
      
      const headers = await getHeaders();
      const response = await fetch(apiUrl + '/validate', {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: controller.signal
      });
      
      clearTimeout(timeoutId);
      
      if (!response.ok) {
        handleHttpError(response.status, response.statusText);
      }
      
      const result = await response.json();
      
      // Merge findings with existing state
      await this.mergeFindingsIntoState(result, scope);
      
    } catch (error) {
      this.outputChannel.appendLine(`[IncrementalIndexer] validate API error: ${error}`);
      throw error;
    }
  }

  /**
   * Smart merge: Remove old findings for affected files, add new ones
   */
  private async mergeFindingsIntoState(
    examinationResult: any,
    scope: ValidationScope
  ): Promise<void> {
    const currentFindings = this.state.s.findings || [];
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    
    if (!workspaceRoot) return;
    
    this.outputChannel.appendLine(`[IncrementalIndexer] Merging: ${currentFindings.length} current findings, ${scope.affectedFiles.size} affected files`);
    
    // Helper function for consistent path normalization
    const normalizePath = (filePath: string): string => {
      const abs = path.isAbsolute(filePath) ? filePath : path.join(workspaceRoot!, filePath);
      // Normalize and lowercase for case-insensitive Windows comparison
      return path.normalize(abs).toLowerCase().replace(/\\/g, '/');
    };
    
    // Pre-normalize affected files once (not per finding!)
    const affectedFilesSet = new Set<string>();
    for (const f of scope.affectedFiles) {
      const normalized = normalizePath(f);
      affectedFilesSet.add(normalized);
      this.outputChannel.appendLine(`[IncrementalIndexer] Affected file: ${normalized}`);
    }
    
    // Filter out findings from affected files - optimized version
    const preservedFindings = currentFindings.filter(finding => {
      // Handle findings that might have empty or missing file paths
      if (!finding.file) {
        this.outputChannel.appendLine(`[IncrementalIndexer] Dropping finding with no file path: ${finding.id || finding.code}`);
        return false;
      }
      const normalized = normalizePath(finding.file);
      const shouldKeep = !affectedFilesSet.has(normalized);
      if (!shouldKeep) {
        this.outputChannel.appendLine(`[IncrementalIndexer] Removing old finding from: ${path.basename(finding.file)} (${finding.code})`);
      }
      return shouldKeep;
    });
    
    // Add new findings - but ONLY for affected files (backend may return all findings)
    const newFindings = (examinationResult.violations || [])
      .map((v: any) => {
        // Server may use 'file', 'file_path', or embedded in locations
        const vFile = v.file || v.file_path || this.parseFileFromLocation(v.locations?.[0]);
        if (!vFile) {
          this.outputChannel.appendLine(`[IncrementalIndexer] Warning: finding without file path: ${JSON.stringify(v).slice(0, 200)}`);
          return null;
        }
        const filePath = path.isAbsolute(vFile) ? vFile : path.join(workspaceRoot, vFile);
        
        return {
          id: v.id || v.violation_id,
          code: v.rule || v.code,
          severity: this.mapSeverity(v.severity),
          file: filePath,
          message: v.explain || v.message,
          fixable: !!v.fixable,
          selected: false,
          span: this.parseSpan(v),
          _raw: v
        };
      })
      .filter((finding: any) => {
        if (!finding) return false; // Skip nulls from missing file paths
        // CRITICAL: Only include findings from affected files
        const normalized = normalizePath(finding.file);
        const isAffected = affectedFilesSet.has(normalized);
        if (!isAffected) {
          this.outputChannel.appendLine(`[IncrementalIndexer] Skipping finding from non-affected file: ${normalized}`);
        }
        return isAffected;
      });
    
    const mergedFindings = [...preservedFindings, ...newFindings];
    
    this.outputChannel.appendLine(`[IncrementalIndexer] Result: ${preservedFindings.length} kept + ${newFindings.length} new = ${mergedFindings.length} total`);
    
    // Update state
    const validateStats = {
      total: mergedFindings.length,
      fixable: mergedFindings.filter(f => f.fixable).length,
      byCode: this.groupByCode(mergedFindings),
      tookMs: examinationResult.processing_time_ms || 0,
      filesChanged: scope.affectedFiles.size
    };
    
    this.state.update({
      findings: mergedFindings,
      lastValidate: validateStats
    });
  }

  /**
   * Create snapshot with lightweight symbol extraction
   */
  private async createFileSnapshot(filePath: string): Promise<FileSnapshot> {
    try {
      const uri = vscode.Uri.file(filePath);
      // Use fs.readFile instead of openTextDocument - 10-50x faster for bulk reads
      const rawContent = await vscode.workspace.fs.readFile(uri);
      const content = Buffer.from(rawContent).toString('utf-8');
      const ext = path.extname(filePath);
      
      // Extract symbols via simple regex (lightweight, fast)
      let imports: string[] = [];
      let exports: string[] = [];
      let functions: string[] = [];
      let classes: string[] = [];
      
      if (ext === '.py') {
        // Python imports
        const importRegex = /^(?:from\s+([\w.]+)\s+)?import\s+([\w\s,*]+)/gm;
        let match;
        while ((match = importRegex.exec(content)) !== null) {
          const module = match[1] || match[2].split(',')[0].trim();
          imports.push(module);
        }
        
        // Python functions/classes
        const defRegex = /^(?:async\s+)?def\s+(\w+)/gm;
        while ((match = defRegex.exec(content)) !== null) {
          functions.push(match[1]);
        }
        
        const classRegex = /^class\s+(\w+)/gm;
        while ((match = classRegex.exec(content)) !== null) {
          classes.push(match[1]);
        }
      } else if (['.ts', '.tsx', '.js', '.jsx'].includes(ext)) {
        // TypeScript/JavaScript imports
        const importRegex = /^import\s+(?:{[^}]+}|[\w]+|\*\s+as\s+\w+)\s+from\s+['"]([^'"]+)['"]/gm;
        let match;
        while ((match = importRegex.exec(content)) !== null) {
          imports.push(match[1]);
        }
        
        const requireRegex = /require\(['"]([^'"]+)['"]\)/g;
        while ((match = requireRegex.exec(content)) !== null) {
          imports.push(match[1]);
        }
        
        // TypeScript/JavaScript exports
        const exportRegex = /^export\s+(?:default\s+)?(?:class|function|const|let|var|interface|type)\s+(\w+)/gm;
        while ((match = exportRegex.exec(content)) !== null) {
          exports.push(match[1]);
        }
        
        // Functions/classes
        const funcRegex = /^(?:export\s+)?(?:async\s+)?function\s+(\w+)/gm;
        while ((match = funcRegex.exec(content)) !== null) {
          functions.push(match[1]);
        }
        
        const classRegexTS = /^(?:export\s+)?(?:abstract\s+)?class\s+(\w+)/gm;
        while ((match = classRegexTS.exec(content)) !== null) {
          classes.push(match[1]);
        }
      }
      
      // Create hashes for quick comparison
      const symbolsHash = this.hashSymbols({ imports, exports, functions, classes });
      
      // Content hash: normalize content by removing all whitespace and comments
      // This helps distinguish between pure whitespace changes vs actual code changes
      const normalizedContent = content
        .replace(/\/\/.*$/gm, '')  // Remove single-line comments
        .replace(/\/\*[\s\S]*?\*\//g, '')  // Remove multi-line comments
        .replace(/#.*$/gm, '')  // Remove Python comments
        .replace(/\s+/g, ' ')  // Normalize all whitespace to single spaces
        .trim();
      const contentHash = this.hashString(normalizedContent);
      
      const snapshot: FileSnapshot = {
        filePath,
        lastModified: Date.now(),
        symbolsHash,
        contentHash,
        imports: [...new Set(imports)].sort(), // Dedupe and sort for consistent comparison
        exports: [...new Set(exports)].sort(),
        functions: [...new Set(functions)].sort(),
        classes: [...new Set(classes)].sort()
      };
      
      this.fileSnapshots.set(filePath, snapshot);
      return snapshot;
      
    } catch (error) {
      this.outputChannel.appendLine(`[IncrementalIndexer] Snapshot error for ${filePath}: ${error}`);
      throw error;
    }
  }

  /**
   * Build dependency maps for O(1) lookups
   */
  private buildDependencyMaps(links: DependencyLink[]): void {
    this.dependencyGraph.clear();
    this.reverseDependencyGraph.clear();
    
    for (const link of links) {
      // Forward: file -> who depends on it (who imports it)
      if (!this.dependencyGraph.has(link.target)) {
        this.dependencyGraph.set(link.target, new Set());
      }
      this.dependencyGraph.get(link.target)!.add(link.source);
      
      // Reverse: file -> what it depends on (what it imports)
      if (!this.reverseDependencyGraph.has(link.source)) {
        this.reverseDependencyGraph.set(link.source, new Set());
      }
      this.reverseDependencyGraph.get(link.source)!.add(link.target);
    }
    
    this.outputChannel.appendLine(
      `[IncrementalIndexer] Built dependency maps: ${this.dependencyGraph.size} files with dependencies`
    );
  }

  /**
   * Rebuild dependency graph for changed file
   */
  private async updateDependencyGraph(changedFile: string): Promise<void> {
    try {
      this.outputChannel.appendLine(`[IncrementalIndexer] Updating dependency graph for ${path.basename(changedFile)}`);
      
      // Re-analyze just this file's dependencies
      const newLinks = await this.dependencyAnalyzer.analyzeDependencies([changedFile]);
      
      // Remove old links for this file
      for (const [target, sources] of this.dependencyGraph) {
        sources.delete(changedFile);
      }
      
      for (const [source, targets] of this.reverseDependencyGraph) {
        if (source === changedFile) {
          targets.clear();
        }
      }
      
      // Add new links
      for (const link of newLinks) {
        if (!this.dependencyGraph.has(link.target)) {
          this.dependencyGraph.set(link.target, new Set());
        }
        this.dependencyGraph.get(link.target)!.add(link.source);
        
        if (!this.reverseDependencyGraph.has(link.source)) {
          this.reverseDependencyGraph.set(link.source, new Set());
        }
        this.reverseDependencyGraph.get(link.source)!.add(link.target);
      }
      
      this.outputChannel.appendLine(`[IncrementalIndexer] Updated ${newLinks.length} dependencies for ${path.basename(changedFile)}`);
    } catch (error) {
      this.outputChannel.appendLine(`[IncrementalIndexer] Failed to update dependency graph: ${error}`);
      // Continue anyway - graph might be stale but not critical
    }
  }

  // Helper methods
  private hashSymbols(symbols: any): string {
    const str = JSON.stringify(symbols);
    return this.hashString(str);
  }

  private hashString(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return hash.toString(36);
  }

  private arraysEqual(a: string[], b: string[]): boolean {
    if (a.length !== b.length) return false;
    // Already sorted in createFileSnapshot
    return a.every((val, idx) => val === b[idx]);
  }

  private estimateValidationTime(fileCount: number): number {
    // Rough estimate: 50ms per file
    return fileCount * 50;
  }

  private mapSeverity(severity: string): 'info' | 'warn' | 'error' {
    const map: any = { 
      error: 'error', 
      critical: 'error',
      high: 'error',
      warn: 'warn', 
      warning: 'warn',
      medium: 'warn',
      low: 'warn',
      info: 'info' 
    };
    return map[severity?.toLowerCase()] || 'warn';
  }

  private parseFileFromLocation(loc?: string): string {
    if (!loc) return '';
    const match = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
    return match ? match[1] : '';
  }

  private parseSpan(v: any): any {
    if (v.span) return v.span;
    if (v.locations?.[0]) {
      const match = v.locations[0].match(/:(\d+):(\d+)-(\d+):(\d+)$/);
      if (match) {
        return {
          start: { line: parseInt(match[1]), column: parseInt(match[2]) },
          end: { line: parseInt(match[3]), column: parseInt(match[4]) }
        };
      }
    }
    return undefined;
  }

  private groupByCode(findings: any[]): Record<string, number> {
    const result: Record<string, number> = {};
    for (const f of findings) {
      result[f.code] = (result[f.code] || 0) + 1;
    }
    return result;
  }

  /**
   * Clean up on disposal
   */
  dispose(): void {
    // Clear all pending saves
    for (const timeout of this.pendingSaves.values()) {
      clearTimeout(timeout);
    }
    this.pendingSaves.clear();
    
    // Clear caches
    this.fileSnapshots.clear();
    this.dependencyGraph.clear();
    this.reverseDependencyGraph.clear();
    
    this._initialized = false;
  }
}

