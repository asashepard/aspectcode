/**
 * DirectoryExclusion - Centralized, deterministic directory exclusion system
 * 
 * Auto-detects directories that shouldn't be indexed based on:
 * - Directory name patterns (node_modules, dist, etc.)
 * - Marker files (pyvenv.cfg for venvs, package-lock.json, etc.)
 * - User settings in .aspect/.settings.json
 * 
 * All detection is strictly deterministic and local (no network calls).
 */

import * as vscode from 'vscode';
import * as path from 'path';

// ============================================================================
// Types
// ============================================================================

export interface ExclusionSettings {
  /** Enable auto-detection of excludable directories (default: true) */
  auto?: boolean;
  /** Always exclude these directories (relative paths from workspace root) */
  always?: string[];
  /** Never exclude these directories, even if auto-detected (relative paths) */
  never?: string[];
}

export interface ExclusionResult {
  /** Glob pattern for vscode.workspace.findFiles exclude parameter */
  excludeGlob: string;
  /** List of excluded directory paths (relative to workspace) */
  excludedDirs: string[];
  /** Directories that would be excluded but are in 'never' list */
  overriddenDirs: string[];
}

// ============================================================================
// Default Exclusion Patterns (by category)
// ============================================================================

/** Package manager directories - always exclude by name */
const PACKAGE_MANAGER_DIRS = [
  'node_modules',
  'bower_components',
  'jspm_packages',
  'vendor',           // PHP Composer, Go modules
  'packages',         // Some monorepo structures (check for marker)
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
  'target',           // Rust, Java/Maven
  'bin',
  'obj',              // C#/.NET
  'lib',              // When it's build output (check for marker)
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
  '.env',             // Note: may conflict with dotenv, check for marker
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
  '.vscode',          // Usually config, not code
];

/** Test framework output directories */
const TEST_OUTPUT_DIRS = [
  'e2e',              // Often test outputs
  'playwright-report',
  'test-results',
  'cypress',          // Cypress downloads/screenshots
  '.playwright',
];

/** Generated/framework directories */
const GENERATED_DIRS = [
  '.aspect',          // Our own output
  'generated',
  '__generated__',
  '.serverless',
  '.terraform',
  '.pulumi',
];

// ============================================================================
// Marker Files for Intelligent Detection
// ============================================================================

/** Marker files that definitively identify a directory type */
const VENV_MARKERS = ['pyvenv.cfg', 'pip-selfcheck.json'];
const NODE_MODULES_MARKERS = ['.package-lock.json', '.yarn-integrity'];
const BUILD_OUTPUT_MARKERS = ['.tsbuildinfo', '.buildinfo'];

// ============================================================================
// Directory Exclusion Service
// ============================================================================

export class DirectoryExclusionService {
  private cachedResult: ExclusionResult | null = null;
  private cacheTimestamp = 0;
  private readonly CACHE_TTL_MS = 60000; // 1 minute cache
  
  constructor(
    private workspaceRoot: string,
    private outputChannel?: vscode.OutputChannel
  ) {}

  /**
   * Compute excluded directories based on auto-detection and user settings.
   * Results are cached for performance.
   */
  async computeExclusions(settings?: ExclusionSettings): Promise<ExclusionResult> {
    const now = Date.now();
    if (this.cachedResult && (now - this.cacheTimestamp) < this.CACHE_TTL_MS) {
      return this.cachedResult;
    }

    const effectiveSettings: ExclusionSettings = {
      auto: true,
      always: [],
      never: [],
      ...settings
    };

    const excludedDirs: string[] = [];
    const overriddenDirs: string[] = [];
    const neverSet = new Set((effectiveSettings.never ?? []).map(p => p.replace(/\\/g, '/')));

    // Add user's always-exclude list
    for (const dir of effectiveSettings.always ?? []) {
      const normalized = dir.replace(/\\/g, '/');
      if (!neverSet.has(normalized)) {
        excludedDirs.push(normalized);
      }
    }

    // Auto-detect if enabled
    if (effectiveSettings.auto !== false) {
      const autoDetected = await this.autoDetectExclusions();
      
      for (const dir of autoDetected) {
        if (neverSet.has(dir)) {
          overriddenDirs.push(dir);
        } else if (!excludedDirs.includes(dir)) {
          excludedDirs.push(dir);
        }
      }
    }

    // Build glob pattern
    const excludeGlob = this.buildExcludeGlob(excludedDirs);

    this.cachedResult = { excludeGlob, excludedDirs, overriddenDirs };
    this.cacheTimestamp = now;

    this.outputChannel?.appendLine(
      `[DirectoryExclusion] Computed exclusions: ${excludedDirs.length} dirs, ${overriddenDirs.length} overridden`
    );

    return this.cachedResult;
  }

  /**
   * Invalidate the cache (call when files change or settings update).
   */
  invalidateCache(): void {
    this.cachedResult = null;
    this.cacheTimestamp = 0;
  }

  /**
   * Get a static glob pattern for common exclusions (no auto-detection).
   * Use this for quick operations where full detection isn't needed.
   */
  static getDefaultExcludeGlob(): string {
    const allDirs = [
      ...PACKAGE_MANAGER_DIRS,
      ...BUILD_OUTPUT_DIRS,
      ...VENV_DIRS,
      ...CACHE_DIRS,
      ...VCS_IDE_DIRS,
      ...TEST_OUTPUT_DIRS,
      ...GENERATED_DIRS,
    ];
    // Remove duplicates and build glob
    const unique = [...new Set(allDirs)];
    return `**/{${unique.join(',')}}/**`;
  }

  /**
   * Get list of all default exclusion directory names.
   */
  static getDefaultExclusionNames(): string[] {
    return [
      ...PACKAGE_MANAGER_DIRS,
      ...BUILD_OUTPUT_DIRS,
      ...VENV_DIRS,
      ...CACHE_DIRS,
      ...VCS_IDE_DIRS,
      ...TEST_OUTPUT_DIRS,
      ...GENERATED_DIRS,
    ];
  }

  // ==========================================================================
  // Private: Auto-Detection Logic
  // ==========================================================================

  private async autoDetectExclusions(): Promise<string[]> {
    const excluded: string[] = [];

    // Fast path: Use name-based detection for well-known directories
    const nameBasedExclusions = this.detectByName();
    excluded.push(...nameBasedExclusions);

    // Slower path: Check for marker files in ambiguous cases
    const markerBasedExclusions = await this.detectByMarkers();
    for (const dir of markerBasedExclusions) {
      if (!excluded.includes(dir)) {
        excluded.push(dir);
      }
    }

    return excluded;
  }

  /**
   * Fast name-based detection - just check directory names against patterns.
   */
  private detectByName(): string[] {
    // For name-based detection, we just return the pattern names
    // The actual filtering happens via glob pattern
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

  /**
   * Marker-based detection for ambiguous directories like 'build', 'dist', 'env'.
   * Only runs if we need to disambiguate.
   */
  private async detectByMarkers(): Promise<string[]> {
    const detected: string[] = [];

    try {
      // Look for virtual environment markers at common locations
      const venvCandidates = ['env', '.env', 'venv', '.venv', 'virtualenv'];
      for (const candidate of venvCandidates) {
        if (await this.hasVenvMarker(candidate)) {
          detected.push(candidate);
        }
      }

      // Look for build output markers
      // 'dist' and 'build' are ambiguous - could be source or output
      // Check for common build markers
      const buildCandidates = ['dist', 'build', 'out', 'lib'];
      for (const candidate of buildCandidates) {
        if (await this.hasBuildOutputMarker(candidate)) {
          detected.push(candidate);
        }
      }
    } catch (e) {
      this.outputChannel?.appendLine(`[DirectoryExclusion] Marker detection error: ${e}`);
    }

    return detected;
  }

  /**
   * Check if a directory has virtual environment markers.
   */
  private async hasVenvMarker(dirName: string): Promise<boolean> {
    const dirPath = path.join(this.workspaceRoot, dirName);
    
    for (const marker of VENV_MARKERS) {
      try {
        const markerPath = vscode.Uri.file(path.join(dirPath, marker));
        await vscode.workspace.fs.stat(markerPath);
        return true;
      } catch {
        // Marker doesn't exist
      }
    }

    // Also check for lib/python*/site-packages structure
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

  /**
   * Check if a directory appears to be build output (not source).
   */
  private async hasBuildOutputMarker(dirName: string): Promise<boolean> {
    const dirPath = path.join(this.workspaceRoot, dirName);
    
    // Check for build markers
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
        const pkgJson = vscode.Uri.file(path.join(this.workspaceRoot, 'package.json'));
        await vscode.workspace.fs.stat(pkgJson);
        return true;
      } catch {
        // No package.json
      }
      
      try {
        const tsConfig = vscode.Uri.file(path.join(this.workspaceRoot, 'tsconfig.json'));
        await vscode.workspace.fs.stat(tsConfig);
        return true;
      } catch {
        // No tsconfig.json
      }
    }

    return false;
  }

  /**
   * Build a glob pattern from list of directory names.
   */
  private buildExcludeGlob(dirs: string[]): string {
    if (dirs.length === 0) {
      return '';
    }
    
    // Escape special glob characters and build pattern
    const escaped = dirs.map(d => d.replace(/[{}[\]()]/g, '\\$&'));
    return `**/{${escaped.join(',')}}/**`;
  }
}

// ============================================================================
// Convenience Functions
// ============================================================================

/**
 * Get the default exclusion glob pattern (static, no auto-detection).
 * Use this for quick operations where you don't need settings customization.
 */
export function getDefaultExcludeGlob(): string {
  return DirectoryExclusionService.getDefaultExcludeGlob();
}

/**
 * Create a configured exclusion service for a workspace.
 */
export function createExclusionService(
  workspaceRoot: string,
  outputChannel?: vscode.OutputChannel
): DirectoryExclusionService {
  return new DirectoryExclusionService(workspaceRoot, outputChannel);
}
