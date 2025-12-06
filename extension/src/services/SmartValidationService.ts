/**
 * Smart Validation Service
 * 
 * Provides dependency-aware validation that only validates files affected by changes.
 * Uses the dependency graph to traverse and validate dependent files intelligently.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import * as fs from 'fs';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';
import { AspectCodeEngineService } from '../engineService';

export interface ValidationResult {
  success: boolean;
  filesValidated: string[];
  findings: any[];
  error?: string;
}

export interface SmartValidationOptions {
  maxDepth?: number;
  skipUnchanged?: boolean;
  skipCleanFiles?: boolean;
}

export class SmartValidationService {
  private dependencyAnalyzer: DependencyAnalyzer;
  private engineService: AspectCodeEngineService;
  private lastValidationTimestamps: Map<string, number> = new Map();
  private lastFileModificationTimes: Map<string, number> = new Map();
  private cachedFindings: Map<string, any[]> = new Map();
  
  constructor(
    private outputChannel: vscode.OutputChannel
  ) {
    this.dependencyAnalyzer = new DependencyAnalyzer();
    this.engineService = new AspectCodeEngineService(outputChannel);
  }

  /**
   * Validate a file and its dependents based on the dependency graph
   */
  async validateWithDependencies(
    changedFile: string,
    options: SmartValidationOptions = {}
  ): Promise<ValidationResult> {
    const {
      maxDepth = undefined,
      skipUnchanged = true,
      skipCleanFiles = true
    } = options;

    this.outputChannel.appendLine(`[SmartValidation] Starting validation for: ${changedFile}`);
    
    try {
      // Normalize the file path
      const normalizedFile = path.normalize(changedFile);
      
      // Get all workspace files
      const workspaceFiles = await this.discoverWorkspaceFiles();
      
      // Build dependency graph
      this.outputChannel.appendLine(`[SmartValidation] Analyzing dependencies for ${workspaceFiles.length} files...`);
      const dependencies = await this.dependencyAnalyzer.analyzeDependencies(workspaceFiles);
      
      // Find files affected by this change
      const filesToValidate = this.findAffectedFiles(
        normalizedFile,
        dependencies,
        workspaceFiles,
        maxDepth,
        skipUnchanged,
        skipCleanFiles
      );
      
      this.outputChannel.appendLine(`[SmartValidation] Will validate ${filesToValidate.length} files`);
      
      if (filesToValidate.length === 0) {
        this.outputChannel.appendLine(`[SmartValidation] No files to validate`);
        return {
          success: true,
          filesValidated: [],
          findings: []
        };
      }
      
      // Validate the affected files
      const allFindings: any[] = [];
      
      for (const file of filesToValidate) {
        this.outputChannel.appendLine(`[SmartValidation] Validating: ${path.basename(file)}`);
        
        const result = await this.engineService.scanFile(file);
        
        if (result.success && result.data) {
          const fileFindings = result.data.findings || [];
          allFindings.push(...fileFindings);
          
          // Cache findings for this file
          this.cachedFindings.set(file, fileFindings);
          
          // Update validation timestamp
          this.lastValidationTimestamps.set(file, Date.now());
        }
      }
      
      this.outputChannel.appendLine(`[SmartValidation] Validation complete: ${allFindings.length} findings`);
      
      return {
        success: true,
        filesValidated: filesToValidate,
        findings: allFindings
      };
      
    } catch (error) {
      this.outputChannel.appendLine(`[SmartValidation] Error: ${error}`);
      return {
        success: false,
        filesValidated: [],
        findings: [],
        error: String(error)
      };
    }
  }

  /**
   * Find all files affected by a change using dependency graph traversal
   */
  private findAffectedFiles(
    changedFile: string,
    dependencies: DependencyLink[],
    allFiles: string[],
    maxDepth: number | undefined,
    skipUnchanged: boolean,
    skipCleanFiles: boolean
  ): string[] {
    const affected = new Set<string>();
    const visited = new Set<string>();
    const queue: Array<{ file: string; depth: number }> = [{ file: changedFile, depth: 0 }];
    
    // Build reverse dependency map (file -> files that depend on it)
    const reverseDeps = new Map<string, string[]>();
    for (const dep of dependencies) {
      if (!reverseDeps.has(dep.target)) {
        reverseDeps.set(dep.target, []);
      }
      reverseDeps.get(dep.target)!.push(dep.source);
    }
    
    this.outputChannel.appendLine(`[SmartValidation] Built reverse dependency map with ${reverseDeps.size} targets`);
    
    // BFS traversal
    while (queue.length > 0) {
      const { file, depth } = queue.shift()!;
      
      // Skip if already visited
      if (visited.has(file)) {
        continue;
      }
      visited.add(file);
      
      // Check if we should stop at this file
      if (this.shouldStopTraversal(file, depth, maxDepth, skipUnchanged, skipCleanFiles)) {
        this.outputChannel.appendLine(`[SmartValidation] Stopping traversal at ${path.basename(file)} (depth: ${depth})`);
        continue;
      }
      
      // Add file to affected list
      affected.add(file);
      
      // Add dependents to queue
      const dependents = reverseDeps.get(file) || [];
      for (const dependent of dependents) {
        if (!visited.has(dependent)) {
          queue.push({ file: dependent, depth: depth + 1 });
        }
      }
    }
    
    return Array.from(affected);
  }

  /**
   * Determine if we should stop traversal at this file
   */
  private shouldStopTraversal(
    file: string,
    depth: number,
    maxDepth: number | undefined,
    skipUnchanged: boolean,
    skipCleanFiles: boolean
  ): boolean {
    // Stop if max depth reached
    if (maxDepth !== undefined && depth > maxDepth) {
      this.outputChannel.appendLine(`[SmartValidation] Stop: max depth ${maxDepth} reached`);
      return true;
    }
    
    // Stop if file hasn't changed since last validation
    if (skipUnchanged && depth > 0) {
      const lastValidation = this.lastValidationTimestamps.get(file);
      if (lastValidation) {
        try {
          const stats = fs.statSync(file);
          const lastModified = stats.mtimeMs;
          
          // Cache the modification time
          this.lastFileModificationTimes.set(file, lastModified);
          
          if (lastValidation > lastModified) {
            this.outputChannel.appendLine(`[SmartValidation] Stop: ${path.basename(file)} unchanged since last validation`);
            return true;
          }
        } catch (error) {
          // File doesn't exist or can't be read - don't stop, let validation handle it
        }
      }
    }
    
    // Stop if file has no findings from last validation
    if (skipCleanFiles && depth > 0) {
      const cachedFindings = this.cachedFindings.get(file);
      if (cachedFindings !== undefined && cachedFindings.length === 0) {
        this.outputChannel.appendLine(`[SmartValidation] Stop: ${path.basename(file)} has no findings`);
        return true;
      }
    }
    
    return false;
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
   * Clear all caches
   */
  clearCache(): void {
    this.lastValidationTimestamps.clear();
    this.lastFileModificationTimes.clear();
    this.cachedFindings.clear();
  }

  /**
   * Get validation statistics
   */
  getStats(): {
    cachedFiles: number;
    totalValidations: number;
  } {
    return {
      cachedFiles: this.cachedFindings.size,
      totalValidations: this.lastValidationTimestamps.size
    };
  }
}

