/**
 * WorkspaceFingerprint - Simple KB staleness detection
 * 
 * Computes a cheap fingerprint from workspace files (paths + mtime + size).
 * Stores fingerprint in .aspect/.fingerprint.json alongside KB files.
 * Provides simple isKbStale() / markKbFresh() API.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as crypto from 'crypto';
import { AutoRegenerateKbMode } from './aspectSettings';

// ============================================================================
// Types
// ============================================================================

interface FingerprintData {
  /** Hash of all file metadata */
  fingerprint: string;
  /** Timestamp when KB was last regenerated */
  kbGeneratedAt: number;
  /** Number of files in workspace at generation time */
  fileCount: number;
  /** Extension version that generated KB */
  version: string;
}

interface FileMetadata {
  path: string;
  mtime: number;
  size: number;
}

// ============================================================================
// WorkspaceFingerprint Service
// ============================================================================

export class WorkspaceFingerprint implements vscode.Disposable {
  private readonly FINGERPRINT_FILE = '.fingerprint.json';
  private readonly SOURCE_EXTENSIONS = [
    '.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
    '.java', '.cs', '.go', '.cpp', '.c', '.h', '.rs'
  ];
  
  // Idle detection
  private idleTimer: NodeJS.Timeout | null = null;
  private lastEditTime: number = 0;
  private readonly IDLE_DEBOUNCE_MS = 30000; // 30 seconds
  private readonly STALE_THRESHOLD_PERCENT = 5; // 5% of files changed = stale

  // onSave debounce (shorter than idle)
  private saveTimer: NodeJS.Timeout | null = null;
  private readonly SAVE_DEBOUNCE_MS = 2000; // 2 seconds after last save

  private autoRegenMode: AutoRegenerateKbMode = 'onSave';
  
  // Cached fingerprint
  private cachedFingerprint: string | null = null;
  private cachedFileCount: number = 0;

  // Track whether we've already notified the UI that KB is stale.
  private staleNotified: boolean = false;
  private lastStaleLogAt: number = 0;
  private readonly STALE_LOG_DEBOUNCE_MS = 5000;

  // Track if regeneration is in progress to avoid overlapping runs
  private regenerationInProgress: boolean = false;
  
  // Event emitter for stale state changes
  private readonly _onStaleStateChanged = new vscode.EventEmitter<boolean>();
  readonly onStaleStateChanged = this._onStaleStateChanged.event;

  /**
   * Set the auto-regeneration mode (driven by .aspect/.settings.json).
   */
  setAutoRegenerateKbMode(mode: AutoRegenerateKbMode): void {
    this.autoRegenMode = mode;

    // If we moved away from idle mode, cancel any pending idle regeneration.
    if (mode !== 'idle' && this.idleTimer) {
      clearTimeout(this.idleTimer);
      this.idleTimer = null;
    }
  }
  
  // KB regeneration callback
  private kbRegenerateCallback: (() => Promise<void>) | null = null;
  
  constructor(
    private workspaceRoot: string,
    private extensionVersion: string,
    private outputChannel: vscode.OutputChannel
  ) {}

  dispose(): void {
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }
    this._onStaleStateChanged.dispose();
  }

  // ==========================================================================
  // Public API
  // ==========================================================================

  /**
   * Set callback for KB regeneration (used by idle auto-regenerate).
   */
  setKbRegenerateCallback(callback: () => Promise<void>): void {
    this.kbRegenerateCallback = callback;
  }

  /**
   * Check if KB is stale (fingerprint changed significantly since last generation).
   * Returns false if no KB exists (no fingerprint file) - can't be stale if it doesn't exist.
   */
  async isKbStale(): Promise<boolean> {
    try {
      const stored = await this.loadFingerprint();
      if (!stored) {
        // No fingerprint = no KB generated yet = NOT stale (it doesn't exist)
        return false;
      }

      const current = await this.computeFingerprint();
      
      // Check if fingerprint changed
      if (current.fingerprint !== stored.fingerprint) {
        // Estimate change magnitude
        const changePercent = Math.abs(current.fileCount - stored.fileCount) / Math.max(stored.fileCount, 1) * 100;
        
        this.outputChannel.appendLine(
          `[WorkspaceFingerprint] Fingerprint changed: ${stored.fileCount} -> ${current.fileCount} files (${changePercent.toFixed(1)}% change)`
        );
        
        return true; // Any fingerprint change = stale
      }

      return false;
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Error checking staleness: ${e}`);
      return false; // On error, don't show stale indicator
    }
  }

  /**
   * Get staleness info for UI display.
   */
  async getStalenessInfo(): Promise<{ isStale: boolean; fileCount: number; lastGenerated: number | null }> {
    try {
      const stored = await this.loadFingerprint();
      const isStale = await this.isKbStale();
      const current = await this.computeFingerprint();
      
      return {
        isStale,
        fileCount: current.fileCount,
        lastGenerated: stored?.kbGeneratedAt || null
      };
    } catch {
      return { isStale: false, fileCount: 0, lastGenerated: null };
    }
  }

  /**
   * Mark KB as fresh (call after successful KB regeneration).
   */
  async markKbFresh(): Promise<void> {
    try {
      const fingerprint = await this.computeFingerprint();
      
      const data: FingerprintData = {
        fingerprint: fingerprint.fingerprint,
        kbGeneratedAt: Date.now(),
        fileCount: fingerprint.fileCount,
        version: this.extensionVersion
      };

      await this.saveFingerprint(data);
      this.cachedFingerprint = fingerprint.fingerprint;
      this.cachedFileCount = fingerprint.fileCount;
      
      this.outputChannel.appendLine(
        `[WorkspaceFingerprint] Marked KB fresh: ${fingerprint.fileCount} files`
      );

      // Notify listeners that KB is no longer stale
      this.staleNotified = false;
      this._onStaleStateChanged.fire(false);
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Error marking KB fresh: ${e}`);
    }
  }

  /**
   * Notify that a file was edited (for idle detection).
   */
  onFileEdited(): void {
    this.lastEditTime = Date.now();
    
    // Reset idle timer
    if (this.idleTimer) {
      clearTimeout(this.idleTimer);
    }

    if (this.autoRegenMode === 'idle' && this.kbRegenerateCallback) {
      this.idleTimer = setTimeout(async () => {
        this.idleTimer = null;
        await this.onIdleTimeout();
      }, this.IDLE_DEBOUNCE_MS);
    }

    // Notify that KB may be stale (only on transition to avoid spam)
    if (!this.staleNotified) {
      this.staleNotified = true;

      const now = Date.now();
      if (now - this.lastStaleLogAt > this.STALE_LOG_DEBOUNCE_MS) {
        this.lastStaleLogAt = now;
        this.outputChannel.appendLine('[WorkspaceFingerprint] Workspace changed; KB may be stale');
      }

      this._onStaleStateChanged.fire(true);
    }
  }

  /**
   * Notify that a file was saved.
   * This triggers debounced KB regeneration if autoRegenerateKb === 'onSave'.
   */
  onFileSaved(filePath: string): void {
    this.lastEditTime = Date.now();

    if (this.autoRegenMode !== 'onSave' || !this.kbRegenerateCallback) {
      // Still mark stale if not auto-regenerating
      this.onFileEdited();
      return;
    }

    // Mark stale immediately
    if (!this.staleNotified) {
      this.staleNotified = true;
      this._onStaleStateChanged.fire(true);
    }

    // Reset save debounce timer
    if (this.saveTimer) {
      clearTimeout(this.saveTimer);
    }

    this.saveTimer = setTimeout(async () => {
      this.saveTimer = null;
      await this.onSaveTimeout(filePath);
    }, this.SAVE_DEBOUNCE_MS);
  }

  /**
   * Called after save debounce expires - triggers KB regeneration.
   */
  private async onSaveTimeout(lastSavedFile: string): Promise<void> {
    if (this.regenerationInProgress) {
      this.outputChannel.appendLine('[WorkspaceFingerprint] Skipping onSave regen (already in progress)');
      return;
    }

    try {
      this.regenerationInProgress = true;
      const startTime = Date.now();
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Auto-regenerating KB (onSave trigger, file: ${path.basename(lastSavedFile)})...`);
      
      await this.kbRegenerateCallback!();
      
      const duration = Date.now() - startTime;
      this.outputChannel.appendLine(`[WorkspaceFingerprint] KB regenerated in ${duration}ms`);
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] onSave regeneration failed: ${e}`);
    } finally {
      this.regenerationInProgress = false;
    }
  }

  /**
   * Get current fingerprint without comparing to stored.
   */
  async computeFingerprint(): Promise<{ fingerprint: string; fileCount: number }> {
    const files = await this.discoverSourceFiles();
    const metadata = await this.getFilesMetadata(files);
    
    // Sort for deterministic hash
    metadata.sort((a, b) => a.path.localeCompare(b.path));
    
    // Create fingerprint from metadata
    const hashInput = metadata.map(m => `${m.path}:${m.mtime}:${m.size}`).join('\n');
    const hash = crypto.createHash('sha256').update(hashInput).digest('hex').slice(0, 16);
    
    return { fingerprint: hash, fileCount: metadata.length };
  }

  // ==========================================================================
  // Internal: Idle Detection
  // ==========================================================================

  private async onIdleTimeout(): Promise<void> {
    try {
      if (this.regenerationInProgress) {
        this.outputChannel.appendLine('[WorkspaceFingerprint] Skipping idle regen (already in progress)');
        return;
      }

      const isStale = await this.isKbStale();
      
      if (isStale && this.kbRegenerateCallback) {
        this.regenerationInProgress = true;
        const startTime = Date.now();
        this.outputChannel.appendLine(`[WorkspaceFingerprint] Idle timeout + KB stale, auto-regenerating...`);
        await this.kbRegenerateCallback();
        const duration = Date.now() - startTime;
        this.outputChannel.appendLine(`[WorkspaceFingerprint] KB regenerated in ${duration}ms`);
      }
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Idle regeneration failed: ${e}`);
    } finally {
      this.regenerationInProgress = false;
    }
  }

  // ==========================================================================
  // Internal: File Discovery
  // ==========================================================================

  private async discoverSourceFiles(): Promise<string[]> {
    const files: string[] = [];
    
    // Build glob pattern for source files
    const pattern = `**/*{${this.SOURCE_EXTENSIONS.join(',')}}`;
    
    // Exclusions
    const excludePatterns = [
      '**/node_modules/**',
      '**/venv/**',
      '**/.venv/**',
      '**/dist/**',
      '**/build/**',
      '**/.git/**',
      '**/.*/**'
    ];
    
    const excludeGlob = `{${excludePatterns.join(',')}}`;
    
    try {
      const uris = await vscode.workspace.findFiles(pattern, excludeGlob, 10000);
      for (const uri of uris) {
        files.push(uri.fsPath);
      }
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] File discovery error: ${e}`);
    }
    
    return files;
  }

  private async getFilesMetadata(files: string[]): Promise<FileMetadata[]> {
    const metadata: FileMetadata[] = [];
    
    for (const filePath of files) {
      try {
        const uri = vscode.Uri.file(filePath);
        const stat = await vscode.workspace.fs.stat(uri);
        
        // Use relative path for consistency across machines
        const relativePath = path.relative(this.workspaceRoot, filePath).replace(/\\/g, '/');
        
        metadata.push({
          path: relativePath,
          mtime: stat.mtime,
          size: stat.size
        });
      } catch {
        // File may have been deleted between discovery and stat
      }
    }
    
    return metadata;
  }

  // ==========================================================================
  // Internal: Fingerprint Persistence
  // ==========================================================================

  private getFingerprintPath(): string {
    return path.join(this.workspaceRoot, '.aspect', this.FINGERPRINT_FILE);
  }

  private async loadFingerprint(): Promise<FingerprintData | null> {
    try {
      const uri = vscode.Uri.file(this.getFingerprintPath());
      const content = await vscode.workspace.fs.readFile(uri);
      const data = JSON.parse(new TextDecoder().decode(content)) as FingerprintData;
      return data;
    } catch {
      // File doesn't exist or is invalid
      return null;
    }
  }

  private async saveFingerprint(data: FingerprintData): Promise<void> {
    try {
      // IMPORTANT: Never create .aspect/ implicitly.
      // The first time we write anything into the workspace must be user-initiated
      // (e.g., via the '+' setup button / explicit KB generation).
      const aspectDir = vscode.Uri.file(path.join(this.workspaceRoot, '.aspect'));
      try {
        await vscode.workspace.fs.stat(aspectDir);
      } catch {
        // No KB directory yet; skip writing fingerprint.
        return;
      }

      const uri = vscode.Uri.file(this.getFingerprintPath());
      const content = JSON.stringify(data, null, 2);
      await vscode.workspace.fs.writeFile(uri, new TextEncoder().encode(content));
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Error saving fingerprint: ${e}`);
    }
  }
}
