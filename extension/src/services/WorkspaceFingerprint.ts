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
  
  // Cached fingerprint
  private cachedFingerprint: string | null = null;
  private cachedFileCount: number = 0;
  
  // Event emitter for stale state changes
  private readonly _onStaleStateChanged = new vscode.EventEmitter<boolean>();
  readonly onStaleStateChanged = this._onStaleStateChanged.event;
  
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
   */
  async isKbStale(): Promise<boolean> {
    try {
      const stored = await this.loadFingerprint();
      if (!stored) {
        // No fingerprint = no KB generated yet
        return true;
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
      return true; // Assume stale on error
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
      return { isStale: true, fileCount: 0, lastGenerated: null };
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

    // Check if auto-regenerate is enabled
    const config = vscode.workspace.getConfiguration('aspectcode');
    const autoRegen = config.get<string>('autoRegenerateKb', 'off');
    
    if (autoRegen === 'idle' && this.kbRegenerateCallback) {
      this.idleTimer = setTimeout(async () => {
        this.idleTimer = null;
        await this.onIdleTimeout();
      }, this.IDLE_DEBOUNCE_MS);
    }

    // Notify that KB may be stale (debounced)
    this._onStaleStateChanged.fire(true);
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
      const isStale = await this.isKbStale();
      
      if (isStale && this.kbRegenerateCallback) {
        this.outputChannel.appendLine(`[WorkspaceFingerprint] Idle timeout + KB stale, auto-regenerating...`);
        await this.kbRegenerateCallback();
      }
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Idle regeneration failed: ${e}`);
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
      // Ensure .aspect directory exists
      const aspectDir = vscode.Uri.file(path.join(this.workspaceRoot, '.aspect'));
      try {
        await vscode.workspace.fs.stat(aspectDir);
      } catch {
        await vscode.workspace.fs.createDirectory(aspectDir);
      }

      const uri = vscode.Uri.file(this.getFingerprintPath());
      const content = JSON.stringify(data, null, 2);
      await vscode.workspace.fs.writeFile(uri, new TextEncoder().encode(content));
    } catch (e) {
      this.outputChannel.appendLine(`[WorkspaceFingerprint] Error saving fingerprint: ${e}`);
    }
  }
}
