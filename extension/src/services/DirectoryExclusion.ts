/**
 * DirectoryExclusion - Types and legacy compatibility layer
 * 
 * The actual exclusion logic has moved to FileDiscoveryService.
 * This module now provides:
 * - Type definitions (ExclusionSettings)
 * - Legacy compatibility wrapper (discoverSourceFiles)
 * - Static helper functions
 * 
 * All new code should use FileDiscoveryService directly.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { getFileDiscoveryService } from './FileDiscoveryService';

// ============================================================================
// Types
// ============================================================================

export interface ExclusionSettings {
  /** Always exclude these directories (relative paths from workspace root) */
  always?: string[];
  /** Never exclude these directories, even if auto-detected (relative paths) */
  never?: string[];
  /** Computed exclusions (stored by FileDiscoveryService) */
  _computed?: {
    excludeGlob: string;
    excludedDirs: string[];
    computedAt: number;
  };
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
// Default Exclusion Patterns (kept for static access)
// ============================================================================

/** Package manager directories */
const PACKAGE_MANAGER_DIRS = [
  'node_modules', 'bower_components', 'jspm_packages', 'vendor',
  'packages', 'site-packages', 'dist-packages', 'eggs', '.eggs',
];

/** Build output directories */
const BUILD_OUTPUT_DIRS = [
  'dist', 'build', 'out', 'output', 'target', 'bin', 'obj', 'lib',
  '.next', '.nuxt', '.output', '.turbo', '.parcel-cache', '.webpack', '.rollup.cache',
];

/** Virtual environment directories */
const VENV_DIRS = [
  'venv', '.venv', 'env', '.env', 'virtualenv', '.virtualenv',
  '.tox', '.nox', '.conda',
];

/** Cache directories */
const CACHE_DIRS = [
  '__pycache__', '.cache', '.pytest_cache', '.mypy_cache', '.ruff_cache',
  '.hypothesis', 'coverage', 'htmlcov', '.nyc_output', '.coverage',
];

/** VCS and IDE directories */
const VCS_IDE_DIRS = ['.git', '.hg', '.svn', '.idea', '.vs', '.vscode'];

/** Test framework output directories */
const TEST_OUTPUT_DIRS = ['e2e', 'playwright-report', 'test-results', 'cypress', '.playwright'];

/** Generated/framework directories */
const GENERATED_DIRS = ['.aspect', 'generated', '__generated__', '.serverless', '.terraform', '.pulumi'];

// ============================================================================
// DirectoryExclusionService (Legacy Compatibility)
// ============================================================================

/**
 * @deprecated Use FileDiscoveryService instead.
 * This class is kept for backwards compatibility during transition.
 */
export class DirectoryExclusionService {
  constructor(
    private workspaceRoot: string,
    private outputChannel?: vscode.OutputChannel
  ) {}

  /**
   * Get exclusions using FileDiscoveryService if available, otherwise compute locally.
   */
  async computeExclusions(settings?: ExclusionSettings): Promise<ExclusionResult> {
    const service = getFileDiscoveryService();
    if (service) {
      const exclusions = await service.getExclusions();
      return {
        excludeGlob: exclusions.excludeGlob,
        excludedDirs: exclusions.excludedDirs,
        overriddenDirs: []
      };
    }
    
    // Fallback: compute locally (shouldn't happen in normal operation)
    const allDirs = DirectoryExclusionService.getDefaultExclusionNames();
    const neverSet = new Set((settings?.never ?? []).map(p => p.replace(/\\/g, '/')));
    const excludedDirs = allDirs.filter(d => !neverSet.has(d));
    const overriddenDirs = allDirs.filter(d => neverSet.has(d));
    
    this.outputChannel?.appendLine(
      `[DirectoryExclusion] Computed exclusions: ${excludedDirs.length} dirs, ${overriddenDirs.length} overridden`
    );
    
    return {
      excludeGlob: this.buildExcludeGlob(excludedDirs),
      excludedDirs,
      overriddenDirs
    };
  }

  invalidateCache(): void {
    const service = getFileDiscoveryService();
    service?.invalidate();
  }

  static getDefaultExcludeGlob(): string {
    const allDirs = DirectoryExclusionService.getDefaultExclusionNames();
    const unique = [...new Set(allDirs)];
    return `**/{${unique.join(',')}}/**`;
  }

  static getDefaultExclusionNames(): string[] {
    return [
      ...PACKAGE_MANAGER_DIRS, ...BUILD_OUTPUT_DIRS, ...VENV_DIRS,
      ...CACHE_DIRS, ...VCS_IDE_DIRS, ...TEST_OUTPUT_DIRS, ...GENERATED_DIRS,
    ];
  }

  private buildExcludeGlob(dirs: string[]): string {
    if (dirs.length === 0) return '';
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
 * @deprecated Use FileDiscoveryService instead.
 */
export function createExclusionService(
  workspaceRoot: string,
  outputChannel?: vscode.OutputChannel
): DirectoryExclusionService {
  return new DirectoryExclusionService(workspaceRoot, outputChannel);
}

/**
 * Discover all source files in the workspace with proper exclusions.
 * Uses FileDiscoveryService if available (singleton), otherwise falls back
 * to direct discovery.
 * 
 * @param workspaceRoot The workspace root URI
 * @param outputChannel Optional output channel for logging (only used in fallback)
 * @param onProgress Optional progress callback
 * @returns Sorted list of absolute file paths
 */
export async function discoverSourceFiles(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel,
  onProgress?: (phase: string) => void
): Promise<string[]> {
  // Use FileDiscoveryService singleton if available
  const service = getFileDiscoveryService();
  if (service) {
    return service.getFiles();
  }
  
  // Fallback: direct discovery (should only happen during early initialization)
  outputChannel?.appendLine('[FileDiscovery] Warning: FileDiscoveryService not initialized, using fallback');
  return discoverSourceFilesFallback(workspaceRoot, outputChannel, onProgress);
}

/**
 * Fallback file discovery when FileDiscoveryService is not yet initialized.
 * This mirrors the logic in FileDiscoveryService.
 */
async function discoverSourceFilesFallback(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel,
  onProgress?: (phase: string) => void
): Promise<string[]> {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    return [];
  }

  const allFiles = new Set<string>();

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

  const explicitExclude = DirectoryExclusionService.getDefaultExcludeGlob();
  outputChannel?.appendLine(`[FileDiscovery] Using default exclusion glob (fallback)`);

  const maxResultsPerPattern = 10000;
  let completedPatterns = 0;

  const patternPromises = patterns.map(async (pattern) => {
    try {
      const files = await vscode.workspace.findFiles(
        new vscode.RelativePattern(workspaceRoot, pattern),
        explicitExclude,
        maxResultsPerPattern
      );
      completedPatterns++;
      onProgress?.(`Discovering files (${Math.round((completedPatterns / patterns.length) * 100)}%)...`);
      return files;
    } catch {
      completedPatterns++;
      return [] as readonly vscode.Uri[];
    }
  });

  const results = await Promise.all(patternPromises);

  for (const fileList of results) {
    for (const file of fileList) {
      allFiles.add(file.fsPath);
    }
  }

  const sorted = Array.from(allFiles).sort();
  outputChannel?.appendLine(`[FileDiscovery] Found ${sorted.length} source files (fallback)`);
  return sorted;
}

