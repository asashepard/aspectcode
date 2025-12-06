/**
 * CacheManager - Persistent Validation Cache System
 * 
 * Stores file signatures, findings, and dependency graphs in .aspect/cache.json
 * to enable instant startup and incremental-only validation.
 * 
 * Key features:
 * - Content-based hashing (SHA-256) for robust cross-machine change detection
 * - Workspace-relative paths for portability
 * - Version stamping for cache invalidation on extension updates
 * - Atomic writes to prevent corruption
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as crypto from 'crypto';

// ============================================================================
// Types
// ============================================================================

/** File signature for change detection */
export interface FileSignature {
  /** SHA-256 hash of (relativePath + fileContent) */
  hash: string;
  /** File size in bytes - quick check before hashing */
  size: number;
}

/** Cached finding - matches state.ts Finding but with relative paths */
export interface CachedFinding {
  id: string;
  code: string;
  severity: 'info' | 'warn' | 'error';
  /** Workspace-relative file path */
  file: string;
  message: string;
  fixable: boolean;
  span?: {
    start: { line: number; column: number };
    end: { line: number; column: number };
  };
  /** Rule priority if available */
  priority?: number;
}

/** Simplified dependency map (file -> files it imports) */
export interface DependencyMap {
  [relativePath: string]: string[];
}

/** The complete cache schema stored in .aspect/cache.json */
export interface CacheSchema {
  /** Schema version - bump when structure changes */
  cacheVersion: string;
  /** Extension version from package.json */
  extensionVersion: string;
  /** Timestamp when cache was last saved */
  timestamp: string;
  /** Workspace root used when cache was created (for validation) */
  workspaceRoot: string;
  /** Map of relative file path -> signature */
  files: { [relativePath: string]: FileSignature };
  /** Cached findings with relative paths */
  findings: CachedFinding[];
  /** Simplified dependency graph (file -> imports) */
  dependencies: DependencyMap;
  /** Last validation stats */
  lastValidate?: {
    total: number;
    fixable: number;
    tookMs: number;
  };
}

/** Result of comparing cache against current workspace */
export interface ChangeDetectionResult {
  /** Files that exist now but not in cache */
  added: Set<string>;
  /** Files that exist in both but content changed */
  modified: Set<string>;
  /** Files in cache but no longer exist */
  deleted: Set<string>;
  /** True if cache was valid and comparison succeeded */
  valid: boolean;
  /** If invalid, the reason why */
  invalidReason?: string;
}

/** Result of loading cache */
export interface CacheLoadResult {
  /** The loaded cache, or null if invalid */
  cache: CacheSchema | null;
  /** Why the cache was invalidated (if cache is null) */
  invalidReason?: 'not_found' | 'cache_version' | 'extension_version' | 'workspace_changed' | 'parse_error';
  /** Details about the invalidation */
  invalidDetails?: string;
}

// ============================================================================
// Constants
// ============================================================================

const CACHE_VERSION = '1.0';
const CACHE_FILENAME = 'cache.json';
const ASPECT_CODE_DIR = '.aspect';

// Source file extensions to track
const SOURCE_EXTENSIONS = new Set([
  '.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs',
  '.java', '.cpp', '.c', '.h', '.hpp', '.cs', '.go', '.rs'
]);

// ============================================================================
// CacheManager Class
// ============================================================================

export class CacheManager {
  private workspaceRoot: string;
  private extensionVersion: string;
  private outputChannel: vscode.OutputChannel;
  private cache: CacheSchema | null = null;

  constructor(
    workspaceRoot: string,
    extensionVersion: string,
    outputChannel: vscode.OutputChannel
  ) {
    this.workspaceRoot = workspaceRoot;
    this.extensionVersion = extensionVersion;
    this.outputChannel = outputChannel;
  }

  // --------------------------------------------------------------------------
  // Public API
  // --------------------------------------------------------------------------

  /**
   * Load cache from .aspect/cache.json
   * Returns the cache if valid, or null with reason if missing/invalid/version mismatch
   */
  async loadCache(): Promise<CacheLoadResult> {
    const cacheUri = this.getCacheUri();
    
    try {
      const content = await vscode.workspace.fs.readFile(cacheUri);
      const json = JSON.parse(Buffer.from(content).toString('utf-8'));
      
      // Validate schema version
      if (json.cacheVersion !== CACHE_VERSION) {
        const details = `Cache version mismatch: ${json.cacheVersion} vs ${CACHE_VERSION}`;
        this.outputChannel.appendLine(`[CacheManager] ${details} - will regenerate`);
        return { cache: null, invalidReason: 'cache_version', invalidDetails: details };
      }
      
      // Validate extension version (invalidate on extension update)
      if (json.extensionVersion !== this.extensionVersion) {
        const details = `Extension version changed: ${json.extensionVersion} -> ${this.extensionVersion}`;
        this.outputChannel.appendLine(`[CacheManager] ${details} - will regenerate`);
        return { cache: null, invalidReason: 'extension_version', invalidDetails: details };
      }
      
      // Validate workspace root matches
      if (json.workspaceRoot !== this.workspaceRoot) {
        const details = `Workspace root changed: ${json.workspaceRoot} -> ${this.workspaceRoot}`;
        this.outputChannel.appendLine(`[CacheManager] ${details}`);
        return { cache: null, invalidReason: 'workspace_changed', invalidDetails: details };
      }
      
      this.cache = json as CacheSchema;
      this.outputChannel.appendLine(
        `[CacheManager] Loaded cache: ${Object.keys(this.cache.files).length} files, ${this.cache.findings.length} findings`
      );
      
      return { cache: this.cache };
      
    } catch (error) {
      if ((error as any).code === 'FileNotFound' || (error as any).code === 'ENOENT') {
        return { cache: null, invalidReason: 'not_found' };
      }
      this.outputChannel.appendLine(`[CacheManager] Failed to load cache: ${error}`);
      return { cache: null, invalidReason: 'parse_error', invalidDetails: String(error) };
    }
  }

  /**
   * Save current state to .aspect/cache.json
   */
  async saveCache(
    files: Map<string, FileSignature>,
    findings: CachedFinding[],
    dependencies: DependencyMap,
    lastValidate?: { total: number; fixable: number; tookMs: number }
  ): Promise<void> {
    const cacheUri = this.getCacheUri();
    const aspectCodeDir = vscode.Uri.file(path.join(this.workspaceRoot, ASPECT_CODE_DIR));
    
    // Ensure .aspect directory exists
    try {
      await vscode.workspace.fs.createDirectory(aspectCodeDir);
    } catch {
      // Directory may already exist
    }
    
    const cache: CacheSchema = {
      cacheVersion: CACHE_VERSION,
      extensionVersion: this.extensionVersion,
      timestamp: new Date().toISOString(),
      workspaceRoot: this.workspaceRoot,
      files: Object.fromEntries(files),
      findings,
      dependencies,
      lastValidate
    };
    
    const content = JSON.stringify(cache, null, 2);
    
    // Write atomically by writing to temp file first
    const tempUri = vscode.Uri.file(path.join(this.workspaceRoot, ASPECT_CODE_DIR, 'cache.json.tmp'));
    await vscode.workspace.fs.writeFile(tempUri, Buffer.from(content, 'utf-8'));
    
    // Rename to final location (atomic on most filesystems)
    try {
      await vscode.workspace.fs.rename(tempUri, cacheUri, { overwrite: true });
    } catch {
      // Fallback: direct write if rename fails
      await vscode.workspace.fs.writeFile(cacheUri, Buffer.from(content, 'utf-8'));
      try {
        await vscode.workspace.fs.delete(tempUri);
      } catch { /* ignore */ }
    }
    
    this.cache = cache;
    this.outputChannel.appendLine(
      `[CacheManager] Saved cache: ${files.size} files, ${findings.length} findings`
    );
  }

  /**
   * Detect which files changed since cache was created
   */
  async detectChanges(): Promise<ChangeDetectionResult> {
    if (!this.cache) {
      return {
        added: new Set(),
        modified: new Set(),
        deleted: new Set(),
        valid: false,
        invalidReason: 'No cache loaded'
      };
    }
    
    const startTime = Date.now();
    const added = new Set<string>();
    const modified = new Set<string>();
    const deleted = new Set<string>();
    
    // Get all current source files
    const currentFiles = await this.discoverSourceFiles();
    const cachedPaths = new Set(Object.keys(this.cache.files));
    
    // Check each current file against cache
    for (const relativePath of currentFiles) {
      const absolutePath = path.join(this.workspaceRoot, relativePath);
      
      if (!cachedPaths.has(relativePath)) {
        // New file
        added.add(absolutePath);
      } else {
        // Check if content changed
        const cachedSig = this.cache.files[relativePath];
        const currentSig = await this.computeFileSignature(absolutePath, relativePath);
        
        if (currentSig && currentSig.hash !== cachedSig.hash) {
          modified.add(absolutePath);
        }
        cachedPaths.delete(relativePath);
      }
    }
    
    // Remaining cached paths are deleted files
    for (const relativePath of cachedPaths) {
      deleted.add(path.join(this.workspaceRoot, relativePath));
    }
    
    const duration = Date.now() - startTime;
    this.outputChannel.appendLine(
      `[CacheManager] Change detection: +${added.size} ~${modified.size} -${deleted.size} (${duration}ms)`
    );
    
    return { added, modified, deleted, valid: true };
  }

  /**
   * Compute SHA-256 hash of file content + relative path
   * Including path in hash means renamed files are detected as changed
   */
  async computeFileSignature(absolutePath: string, relativePath: string): Promise<FileSignature | null> {
    try {
      const uri = vscode.Uri.file(absolutePath);
      const content = await vscode.workspace.fs.readFile(uri);
      
      // Hash = SHA-256(relativePath + content)
      const hash = crypto
        .createHash('sha256')
        .update(relativePath)
        .update(content)
        .digest('hex');
      
      return {
        hash,
        size: content.length
      };
    } catch (error) {
      this.outputChannel.appendLine(`[CacheManager] Failed to hash ${relativePath}: ${error}`);
      return null;
    }
  }

  /**
   * Build file signatures map for all source files in workspace
   */
  async buildFileSignatures(): Promise<Map<string, FileSignature>> {
    const signatures = new Map<string, FileSignature>();
    const files = await this.discoverSourceFiles();
    
    for (const relativePath of files) {
      const absolutePath = path.join(this.workspaceRoot, relativePath);
      const sig = await this.computeFileSignature(absolutePath, relativePath);
      if (sig) {
        signatures.set(relativePath, sig);
      }
    }
    
    return signatures;
  }

  /**
   * Convert absolute path findings to cached format with relative paths
   */
  findingsToCache(findings: any[]): CachedFinding[] {
    return findings.map(f => ({
      id: f.id,
      code: f.code || f.rule_id,
      severity: f.severity,
      file: this.toRelativePath(f.file || f.file_path),
      message: f.message,
      fixable: f.fixable ?? false,
      span: f.span,
      priority: f.priority
    }));
  }

  /**
   * Convert cached findings back to absolute path format
   */
  findingsFromCache(cached: CachedFinding[]): any[] {
    return cached.map(f => ({
      id: f.id,
      code: f.code,
      severity: f.severity,
      file: path.join(this.workspaceRoot, f.file),
      message: f.message,
      fixable: f.fixable,
      span: f.span,
      priority: f.priority,
      selected: false,
      _raw: null
    }));
  }

  /**
   * Convert dependency graph to simplified relative-path format for caching
   */
  dependenciesToCache(
    reverseDependencyGraph: Map<string, Set<string>>
  ): DependencyMap {
    const result: DependencyMap = {};
    
    for (const [file, deps] of reverseDependencyGraph) {
      const relFile = this.toRelativePath(file);
      result[relFile] = Array.from(deps).map(d => this.toRelativePath(d));
    }
    
    return result;
  }

  /**
   * Convert cached dependencies back to Map format with absolute paths
   */
  dependenciesFromCache(cached: DependencyMap): Map<string, Set<string>> {
    const result = new Map<string, Set<string>>();
    
    for (const [relFile, deps] of Object.entries(cached)) {
      const absFile = path.join(this.workspaceRoot, relFile);
      result.set(absFile, new Set(deps.map(d => path.join(this.workspaceRoot, d))));
    }
    
    return result;
  }

  /**
   * Get the currently loaded cache (may be null)
   */
  getCache(): CacheSchema | null {
    return this.cache;
  }

  /**
   * Clear the cache file
   */
  async clearCache(): Promise<void> {
    try {
      await vscode.workspace.fs.delete(this.getCacheUri());
      this.cache = null;
      this.outputChannel.appendLine('[CacheManager] Cache cleared');
    } catch {
      // File may not exist
    }
  }

  // --------------------------------------------------------------------------
  // Private Helpers
  // --------------------------------------------------------------------------

  private getCacheUri(): vscode.Uri {
    return vscode.Uri.file(path.join(this.workspaceRoot, ASPECT_CODE_DIR, CACHE_FILENAME));
  }

  private toRelativePath(absolutePath: string): string {
    return path.relative(this.workspaceRoot, absolutePath).replace(/\\/g, '/');
  }

  private async discoverSourceFiles(): Promise<string[]> {
    const files: string[] = [];
    
    // Use VS Code's findFiles with common ignore patterns
    const pattern = new vscode.RelativePattern(
      this.workspaceRoot,
      '**/*.{py,ts,tsx,js,jsx,mjs,cjs,java,cpp,c,h,hpp,cs,go,rs}'
    );
    
    const excludePattern = '{**/node_modules/**,**/.git/**,**/dist/**,**/build/**,**/__pycache__/**,**/.venv/**,**/venv/**,**/e2e/**,**/playwright/**,**/cypress/**,**/target/**}';
    
    const uris = await vscode.workspace.findFiles(pattern, excludePattern, 10000);
    
    for (const uri of uris) {
      files.push(this.toRelativePath(uri.fsPath));
    }
    
    return files;
  }
}

