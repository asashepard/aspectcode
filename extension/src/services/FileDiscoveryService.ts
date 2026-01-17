/**
 * FileDiscoveryService - Centralized, coordinated file discovery
 * 
 * This service provides THE SINGLE SOURCE OF TRUTH for discovered workspace files.
 * All components (KB generation, fingerprinting, dependency graph, etc.) should
 * use this service instead of calling discoverSourceFiles directly.
 * 
 * Key features:
 * - Singleton instance per workspace (created once at activation)
 * - Caches discovered files and invalidates based on fingerprint changes
 * - Stores computed exclusions in .aspect/.settings.json (not auto field)
 * - Provides coordinated access to file lists across all components
 * 
 * This eliminates the redundant file discovery that was running 2-3x per operation.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as crypto from 'crypto';
import type { ExclusionSettings } from './DirectoryExclusion';
import { readAspectSettings, updateAspectSettings } from './aspectSettings';

// ============================================================================
// Types
// ============================================================================

export interface FileDiscoveryResult {
  /** List of absolute file paths discovered */
  files: string[];
  /** Fingerprint hash of the discovery (for staleness detection) */
  fingerprint: string;
  /** Number of files */
  fileCount: number;
  /** Timestamp when discovery was performed */
  timestamp: number;
}

export interface ComputedExclusions {
  /** Glob pattern for vscode.workspace.findFiles exclude parameter */
  excludeGlob: string;
  /** List of excluded directory names (from auto-detection) */
  excludedDirs: string[];
  /** Timestamp when exclusions were computed */
  computedAt: number;
}

// ============================================================================
// Default Exclusion Patterns (by category)
// ============================================================================

/** Package manager directories - always exclude by name */
const PACKAGE_MANAGER_DIRS = [
  'node_modules',
  'bower_components',
  'jspm_packages',
  'vendor',
  'packages',
  'site-packages',
  'dist-packages',
  'eggs',
  '.eggs',
];

/** Build output directories - exclude by name */
const BUILD_OUTPUT_DIRS = [
  'dist',
  'build',
  'out',
  'output',
  'target',
  'bin',
  'obj',
  'lib',
  '.next',
  '.nuxt',
  '.output',
  '.turbo',
  '.parcel-cache',
  '.webpack',
  '.rollup.cache',
];

/** Virtual environment directories - exclude by name or marker */
const VENV_DIRS = [
  'venv',
  '.venv',
  'env',
  '.env',
  'virtualenv',
  '.virtualenv',
  '.tox',
  '.nox',
  '.conda',
];

/** Cache directories - always exclude */
const CACHE_DIRS = [
  '__pycache__',
  '.cache',
  '.pytest_cache',
  '.mypy_cache',
  '.ruff_cache',
  '.hypothesis',
  'coverage',
  'htmlcov',
  '.nyc_output',
  '.coverage',
];

/** VCS and IDE directories - always exclude */
const VCS_IDE_DIRS = [
  '.git',
  '.hg',
  '.svn',
  '.idea',
  '.vs',
  '.vscode',
];

/** Test framework output directories */
const TEST_OUTPUT_DIRS = [
  'e2e',
  'playwright-report',
  'test-results',
  'cypress',
  '.playwright',
];

/** Generated/framework directories */
const GENERATED_DIRS = [
  '.aspect',
  'generated',
  '__generated__',
  '.serverless',
  '.terraform',
  '.pulumi',
];

/** Marker files for venv detection */
const VENV_MARKERS = ['pyvenv.cfg', 'pip-selfcheck.json'];

/** Marker files for build output detection */
const BUILD_OUTPUT_MARKERS = ['.tsbuildinfo', '.buildinfo'];

// ============================================================================
// FileDiscoveryService
// ============================================================================

export class FileDiscoveryService implements vscode.Disposable {
  private workspaceRoot: vscode.Uri;
  private outputChannel?: vscode.OutputChannel;
  
  // Cached state
  private cachedResult: FileDiscoveryResult | null = null;
  private cachedExclusions: ComputedExclusions | null = null;
  private discoveryInFlight: Promise<FileDiscoveryResult> | null = null;
  
  // Change tracking
  private fileWatcherDisposable: vscode.Disposable | null = null;
  private isDirty: boolean = true;
  
  // Event emitter for when files change
  private readonly _onFilesChanged = new vscode.EventEmitter<void>();
  readonly onFilesChanged = this._onFilesChanged.event;

  constructor(
    workspaceRoot: vscode.Uri,
    outputChannel?: vscode.OutputChannel
  ) {
    this.workspaceRoot = workspaceRoot;
    this.outputChannel = outputChannel;
    
    // Set up file watchers to mark cache as dirty
    this.setupFileWatchers();
  }

  dispose(): void {
    this.fileWatcherDisposable?.dispose();
    this._onFilesChanged.dispose();
  }

  // ==========================================================================
  // Public API
  // ==========================================================================

  /**
   * Get discovered files. Uses cache if available and not dirty.
   * This is the main entry point - all components should use this.
   */
  async getFiles(): Promise<string[]> {
    const result = await this.discover();
    return result.files;
  }

  /**
   * Get the full discovery result including fingerprint.
   */
  async discover(): Promise<FileDiscoveryResult> {
    // Return cached result if not dirty
    if (this.cachedResult && !this.isDirty) {
      return this.cachedResult;
    }
    
    // If discovery is already in flight, wait for it
    if (this.discoveryInFlight) {
      return this.discoveryInFlight;
    }
    
    // Start new discovery
    this.discoveryInFlight = this.performDiscovery();
    
    try {
      const result = await this.discoveryInFlight;
      this.cachedResult = result;
      this.isDirty = false;
      return result;
    } finally {
      this.discoveryInFlight = null;
    }
  }

  /**
   * Force rediscovery on next access.
   */
  invalidate(): void {
    this.isDirty = true;
    this.cachedResult = null;
    this.cachedExclusions = null;
  }

  /**
   * Get cached files if available (no discovery if cache is empty).
   * Useful for best-effort access without triggering expensive operations.
   */
  getCachedFiles(): string[] | null {
    return this.cachedResult?.files ?? null;
  }

  /**
   * Get cached fingerprint if available.
   */
  getCachedFingerprint(): string | null {
    return this.cachedResult?.fingerprint ?? null;
  }

  /**
   * Get computed exclusions. Computes once and caches, stores in settings.
   */
  async getExclusions(): Promise<ComputedExclusions> {
    if (this.cachedExclusions) {
      return this.cachedExclusions;
    }
    
    // Try to load from settings first
    const fromSettings = await this.loadExclusionsFromSettings();
    if (fromSettings) {
      this.cachedExclusions = fromSettings;
      return fromSettings;
    }
    
    // Compute fresh exclusions
    const exclusions = await this.computeExclusions();
    this.cachedExclusions = exclusions;
    
    // Save to settings (async, non-blocking)
    void this.saveExclusionsToSettings(exclusions);
    
    return exclusions;
  }

  /**
   * Force recomputation of exclusions (e.g., when user changes settings).
   */
  async recomputeExclusions(): Promise<ComputedExclusions> {
    this.cachedExclusions = null;
    const exclusions = await this.computeExclusions();
    this.cachedExclusions = exclusions;
    
    // Save to settings
    await this.saveExclusionsToSettings(exclusions);
    
    // Mark files as dirty since exclusions changed
    this.invalidate();
    
    return exclusions;
  }

  // ==========================================================================
  // Private: File Discovery
  // ==========================================================================

  private async performDiscovery(): Promise<FileDiscoveryResult> {
    const startTime = Date.now();
    
    // Get exclusions (from cache or compute)
    const exclusions = await this.getExclusions();
    
    this.outputChannel?.appendLine(
      `[FileDiscovery] Using exclusion glob: ${exclusions.excludeGlob.substring(0, 100)}...`
    );

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

    // Also respect VS Code's files.exclude and search.exclude settings
    const config = vscode.workspace.getConfiguration();
    const filesExclude = config.get<Record<string, boolean>>('files.exclude', {});
    const searchExclude = config.get<Record<string, boolean>>('search.exclude', {});

    const settingsExcludes: string[] = [];
    for (const [pattern, enabled] of Object.entries(filesExclude)) {
      if (enabled) settingsExcludes.push(pattern);
    }
    for (const [pattern, enabled] of Object.entries(searchExclude)) {
      if (enabled && !settingsExcludes.includes(pattern)) settingsExcludes.push(pattern);
    }

    // Build directory names to exclude from settings
    const excludeNames = settingsExcludes
      .map(p => {
        const normalized = p.replace(/\*\*\//g, '').replace(/\/\*\*/g, '').replace(/^\*+/, '').replace(/\*+$/, '');
        return normalized.toLowerCase();
      })
      .filter(p => p.length > 2 && !p.includes('*'));

    this.outputChannel?.appendLine(
      `[FileDiscovery] Additional excludeNames from settings: ${excludeNames.join(', ')}`
    );

    const allFiles = new Set<string>();
    const maxResultsPerPattern = 10000;

    // Run all patterns in parallel
    const patternPromises = patterns.map(async (pattern) => {
      try {
        const files = await vscode.workspace.findFiles(
          new vscode.RelativePattern(this.workspaceRoot, pattern),
          exclusions.excludeGlob,
          maxResultsPerPattern
        );
        return files;
      } catch (error) {
        console.warn('Error finding files with pattern:', pattern, error);
        return [] as readonly vscode.Uri[];
      }
    });

    const results = await Promise.all(patternPromises);

    for (const fileList of results) {
      for (const file of fileList) {
        const filePath = file.fsPath.toLowerCase();
        // Filter out files matching settings excludes
        const excluded = excludeNames.length > 0 && excludeNames.some(name => filePath.includes(name));
        if (!excluded) {
          allFiles.add(file.fsPath);
        }
      }
    }

    const files = Array.from(allFiles).sort();
    const fingerprint = this.computeListFingerprint(files);
    
    const elapsed = Date.now() - startTime;
    this.outputChannel?.appendLine(
      `[FileDiscovery] Found ${files.length} source files in ${elapsed}ms`
    );

    return {
      files,
      fingerprint,
      fileCount: files.length,
      timestamp: Date.now()
    };
  }

  /**
   * Compute a fingerprint from just the file paths (fast).
   * For full staleness detection with mtime/size, use WorkspaceFingerprint.
   */
  private computeListFingerprint(files: string[]): string {
    const hashInput = files.join('\n');
    return crypto.createHash('sha256').update(hashInput).digest('hex').slice(0, 16);
  }

  // ==========================================================================
  // Private: Exclusion Computation
  // ==========================================================================

  private async computeExclusions(): Promise<ComputedExclusions> {
    const startTime = Date.now();
    
    // Load user settings for overrides
    const settings = await this.loadExclusionSettingsFromAspect();
    const neverSet = new Set((settings?.never ?? []).map(p => p.replace(/\\/g, '/')));
    const alwaysSet = new Set((settings?.always ?? []).map(p => p.replace(/\\/g, '/')));
    
    const excludedDirs: string[] = [];
    
    // Add user's always-exclude list
    for (const dir of alwaysSet) {
      if (!neverSet.has(dir)) {
        excludedDirs.push(dir);
      }
    }
    
    // Add name-based exclusions (fast)
    const nameBasedDirs = this.getNameBasedExclusions();
    for (const dir of nameBasedDirs) {
      if (!neverSet.has(dir) && !excludedDirs.includes(dir)) {
        excludedDirs.push(dir);
      }
    }
    
    // Add marker-based exclusions (slightly slower, checks filesystem)
    const markerBasedDirs = await this.detectMarkerBasedExclusions();
    for (const dir of markerBasedDirs) {
      if (!neverSet.has(dir) && !excludedDirs.includes(dir)) {
        excludedDirs.push(dir);
      }
    }
    
    const excludeGlob = this.buildExcludeGlob(excludedDirs);
    
    const elapsed = Date.now() - startTime;
    this.outputChannel?.appendLine(
      `[FileDiscovery] Computed exclusions: ${excludedDirs.length} dirs in ${elapsed}ms`
    );

    return {
      excludeGlob,
      excludedDirs,
      computedAt: Date.now()
    };
  }

  private getNameBasedExclusions(): string[] {
    return [
      ...PACKAGE_MANAGER_DIRS,
      ...CACHE_DIRS,
      ...VCS_IDE_DIRS,
      ...GENERATED_DIRS,
      // Only include unambiguous build/venv dirs
      '.next', '.nuxt', '.output', '.turbo', '.parcel-cache',
      '__pycache__', '.pytest_cache', '.mypy_cache',
      'venv', '.venv', '.tox', '.nox',
    ];
  }

  private async detectMarkerBasedExclusions(): Promise<string[]> {
    const detected: string[] = [];

    try {
      // Look for virtual environment markers
      const venvCandidates = ['env', '.env', 'venv', '.venv', 'virtualenv'];
      for (const candidate of venvCandidates) {
        if (await this.hasVenvMarker(candidate)) {
          detected.push(candidate);
        }
      }

      // Look for build output markers
      const buildCandidates = ['dist', 'build', 'out', 'lib'];
      for (const candidate of buildCandidates) {
        if (await this.hasBuildOutputMarker(candidate)) {
          detected.push(candidate);
        }
      }
    } catch (e) {
      this.outputChannel?.appendLine(`[FileDiscovery] Marker detection error: ${e}`);
    }

    return detected;
  }

  private async hasVenvMarker(dirName: string): Promise<boolean> {
    const dirPath = path.join(this.workspaceRoot.fsPath, dirName);
    
    for (const marker of VENV_MARKERS) {
      try {
        const markerPath = vscode.Uri.file(path.join(dirPath, marker));
        await vscode.workspace.fs.stat(markerPath);
        return true;
      } catch {
        // Marker doesn't exist
      }
    }

    // Check for lib/python*/site-packages structure
    try {
      const libPath = vscode.Uri.file(path.join(dirPath, 'lib'));
      const libStat = await vscode.workspace.fs.stat(libPath);
      if (libStat.type === vscode.FileType.Directory) {
        const libContents = await vscode.workspace.fs.readDirectory(libPath);
        for (const [name, type] of libContents) {
          if (type === vscode.FileType.Directory && name.startsWith('python')) {
            return true;
          }
        }
      }
    } catch {
      // Not a venv structure
    }

    return false;
  }

  private async hasBuildOutputMarker(dirName: string): Promise<boolean> {
    const dirPath = path.join(this.workspaceRoot.fsPath, dirName);
    
    for (const marker of BUILD_OUTPUT_MARKERS) {
      try {
        const markerPath = vscode.Uri.file(path.join(dirPath, marker));
        await vscode.workspace.fs.stat(markerPath);
        return true;
      } catch {
        // Marker doesn't exist
      }
    }

    // Heuristic: If there's a package.json or tsconfig.json at root,
    // 'dist' and 'build' are likely build outputs
    if (dirName === 'dist' || dirName === 'build' || dirName === 'out') {
      try {
        const pkgJson = vscode.Uri.file(path.join(this.workspaceRoot.fsPath, 'package.json'));
        await vscode.workspace.fs.stat(pkgJson);
        return true;
      } catch {
        // No package.json
      }
      
      try {
        const tsConfig = vscode.Uri.file(path.join(this.workspaceRoot.fsPath, 'tsconfig.json'));
        await vscode.workspace.fs.stat(tsConfig);
        return true;
      } catch {
        // No tsconfig.json
      }
    }

    return false;
  }

  private buildExcludeGlob(dirs: string[]): string {
    if (dirs.length === 0) {
      return '';
    }
    
    // Escape special glob characters and build pattern
    const escaped = dirs.map(d => d.replace(/[{}[\]()]/g, '\\$&'));
    return `**/{${escaped.join(',')}}/**`;
  }

  // ==========================================================================
  // Private: Settings Persistence
  // ==========================================================================

  private async loadExclusionSettingsFromAspect(): Promise<ExclusionSettings | undefined> {
    try {
      const settings = await readAspectSettings(this.workspaceRoot);
      return settings.excludeDirectories;
    } catch {
      return undefined;
    }
  }

  private async loadExclusionsFromSettings(): Promise<ComputedExclusions | null> {
    try {
      const settings = await readAspectSettings(this.workspaceRoot);
      const computed = settings.excludeDirectories as ExclusionSettings & {
        _computed?: {
          excludeGlob: string;
          excludedDirs: string[];
          computedAt: number;
        }
      };
      
      if (computed?._computed?.excludeGlob) {
        return {
          excludeGlob: computed._computed.excludeGlob,
          excludedDirs: computed._computed.excludedDirs,
          computedAt: computed._computed.computedAt
        };
      }
    } catch {
      // Settings not available
    }
    return null;
  }

  private async saveExclusionsToSettings(exclusions: ComputedExclusions): Promise<void> {
    try {
      const settings = await readAspectSettings(this.workspaceRoot);
      const current = settings.excludeDirectories ?? {};
      
      // Store computed exclusions alongside user settings
      await updateAspectSettings(this.workspaceRoot, {
        excludeDirectories: {
          ...current,
          // Remove the 'auto' field - we no longer use it
          auto: undefined,
          // Store computed result
          _computed: {
            excludeGlob: exclusions.excludeGlob,
            excludedDirs: exclusions.excludedDirs,
            computedAt: exclusions.computedAt
          }
        } as ExclusionSettings & { _computed: any }
      });
    } catch (e) {
      this.outputChannel?.appendLine(`[FileDiscovery] Failed to save exclusions to settings: ${e}`);
    }
  }

  // ==========================================================================
  // Private: File Watchers
  // ==========================================================================

  private setupFileWatchers(): void {
    // Watch for file creates/deletes/renames to invalidate cache
    const watcher = vscode.workspace.createFileSystemWatcher('**/*');
    
    const markDirty = () => {
      this.isDirty = true;
      this._onFilesChanged.fire();
    };
    
    watcher.onDidCreate(markDirty);
    watcher.onDidDelete(markDirty);
    // Note: onDidChange fires for content changes, but we don't need to
    // rediscover files for content changes - only structure changes
    
    this.fileWatcherDisposable = watcher;
  }
}

// ============================================================================
// Singleton Instance Management
// ============================================================================

let _instance: FileDiscoveryService | null = null;

/**
 * Initialize the FileDiscoveryService singleton.
 * Should be called once during extension activation.
 */
export function initFileDiscoveryService(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel
): FileDiscoveryService {
  if (_instance) {
    _instance.dispose();
  }
  _instance = new FileDiscoveryService(workspaceRoot, outputChannel);
  return _instance;
}

/**
 * Get the FileDiscoveryService singleton.
 * Returns null if not yet initialized.
 */
export function getFileDiscoveryService(): FileDiscoveryService | null {
  return _instance;
}

/**
 * Dispose the singleton (for cleanup during deactivation).
 */
export function disposeFileDiscoveryService(): void {
  _instance?.dispose();
  _instance = null;
}
