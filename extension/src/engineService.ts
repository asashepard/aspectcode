/**
 * Aspect Code Engine Service
 * 
 * This module provides a service layer for communicating with the Aspect Code engine
 * using the new JSON protocol v1.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { spawn, ChildProcess } from 'child_process';
import { ScanResult, Finding, ValidationResult, decodeScanResult, groupFindingsByFile } from './types/protocol';

export interface EngineConfig {
  pythonPath?: string;
  serverPath?: string;
  timeout?: number;
  maxJobs?: number;
}

export interface ScanOptions {
  paths: string[];
  language?: string;
  rules?: string;
  discover?: string;
  jobs?: number;
  validate?: boolean;
  debugResolver?: boolean;
  debugScopes?: boolean;
  graphDump?: string;
  // Enhanced options for new rule system
  categories?: string[];  // Filter by rule categories like 'imports', 'security', 'memory'
  tier?: number;         // Filter by rule tier (1, 2, 3)
  priority?: string;     // Filter by priority (P0, P1, P2, P3)
  excludeRules?: string; // Exclude specific rules or patterns
}

export class AspectCodeEngineService {
  private config: EngineConfig;
  private outputChannel: vscode.OutputChannel;
  private runningProcesses = new Set<ChildProcess>();

  constructor(config: EngineConfig = {}, outputChannel?: vscode.OutputChannel) {
    this.config = {
      timeout: 30000, // 30 seconds default
      maxJobs: 4,
      ...config
    };
    this.outputChannel = outputChannel || vscode.window.createOutputChannel('Aspect Code Engine');
  }

  /**
   * Best-effort: immediately stop any currently running engine processes.
   * attach to the engine are cancelled.
   */
  stopAllRunningProcesses(): void {
    for (const proc of Array.from(this.runningProcesses)) {
      try {
        proc.kill();
      } catch {
        // ignore
      } finally {
        this.runningProcesses.delete(proc);
      }
    }
  }

  /**
   * Get the Python interpreter path, preferring Python extension if available.
   */
  private async getPythonPath(): Promise<string> {
    if (this.config.pythonPath) {
      return this.config.pythonPath;
    }

    // Try to use the Python extension's interpreter
    try {
      const pythonExtension = vscode.extensions.getExtension('ms-python.python');
      if (pythonExtension && pythonExtension.isActive) {
        const api = pythonExtension.exports;
        
        // Try the modern API first
        if (api?.environments?.getActiveEnvironmentPath) {
          const activeEnvPath = api.environments.getActiveEnvironmentPath();
          if (activeEnvPath?.path) {
            this.outputChannel.appendLine(`Using Python from active environment: ${activeEnvPath.path}`);
            return activeEnvPath.path;
          }
        }
        
        // Try the legacy API
        if (api?.settings?.getExecutionDetails) {
          const details = api.settings.getExecutionDetails();
          if (details?.execCommand) {
            const pythonPath = Array.isArray(details.execCommand) ? details.execCommand[0] : details.execCommand;
            this.outputChannel.appendLine(`Using Python from execution details: ${pythonPath}`);
            return pythonPath;
          }
        }
      }
    } catch (error) {
      this.outputChannel.appendLine(`Warning: Could not get Python path from extension: ${error}`);
    }

    // Try VS Code Python settings
    const config = vscode.workspace.getConfiguration('python');
    const defaultInterpreterPath = config.get<string>('defaultInterpreterPath');
    if (defaultInterpreterPath) {
      this.outputChannel.appendLine(`Using Python from VS Code settings: ${defaultInterpreterPath}`);
      return defaultInterpreterPath;
    }

    // Try platform-specific defaults
    const isWindows = process.platform === 'win32';
    const fallbackPath = isWindows ? 'python.exe' : 'python3';
    this.outputChannel.appendLine(`Using fallback Python path: ${fallbackPath}`);
    
    return fallbackPath;
  }

  /**
   * Get the server module path.
   */
  private getServerPath(): string {
    if (this.config.serverPath) {
      return this.config.serverPath;
    }

    // Use the updated engine runner path
    return 'engine.runner';
  }

  /**
   * Build command line arguments for the engine runner.
   */
  private buildRunnerArgs(options: ScanOptions): string[] {
    const args = ['-m', this.getServerPath()];

    // Required arguments
    args.push('--paths', ...options.paths);
    args.push('--format', 'json');

    // Language detection and support
    if (options.language) {
      args.push('--lang', options.language);
    }

    // Use the updated rule discovery system
    if (options.discover) {
      args.push('--discover', options.discover);
    } else {
      // Default to the new rules package structure
      args.push('--discover', 'rules');
    }

    // Rule filtering - support both patterns and specific rules
    if (options.rules) {
      args.push('--rules', options.rules);
    } else if (options.categories && options.categories.length > 0) {
      // Convert categories to rule patterns (e.g., 'imports' -> 'imports.*')
      const categoryPatterns = options.categories.map(cat => `${cat}.*`).join(',');
      args.push('--rules', categoryPatterns);
    } else {
      // Default to all rules
      args.push('--rules', '*');
    }

    // Rule exclusions
    if (options.excludeRules) {
      // Note: The current engine doesn't support --exclude-rules yet, but we can document this
      this.outputChannel.appendLine(`Note: Rule exclusions not yet supported in engine: ${options.excludeRules}`);
    }

    if (options.jobs && options.jobs > 0) {
      args.push('--jobs', options.jobs.toString());
    }

    if (options.validate) {
      args.push('--validate');
    }

    if (options.debugResolver) {
      args.push('--debug-resolver');
    }

    if (options.debugScopes) {
      args.push('--debug-scopes');
    }

    if (options.graphDump) {
      args.push('--graph-dump', options.graphDump);
    }

    return args;
  }

  /**
   * Execute the engine runner and return the parsed result.
   */
  private async runEngine(options: ScanOptions, workspaceRoot?: string, cancellationToken?: vscode.CancellationToken): Promise<ValidationResult> {
    const pythonPath = await this.getPythonPath();
    const args = this.buildRunnerArgs(options);

    this.outputChannel.appendLine(`Running: ${pythonPath} ${args.join(' ')}`);
    
    // The working directory should be the server directory where the engine module is located
    // Not the workspace being scanned - that's passed as --paths argument
    const extensionPath = vscode.extensions.getExtension('aspectcode.aspect')?.extensionPath;
    const serverPath = extensionPath ? path.join(extensionPath, '..', 'server') : path.join(__dirname, '..', '..', 'server');
    
    this.outputChannel.appendLine(`Working directory: ${serverPath}`);

    return new Promise((resolve) => {
      let process: ChildProcess;
      
      try {
        this.outputChannel.appendLine(`Attempting to spawn: ${pythonPath}`);
        this.outputChannel.appendLine(`Arguments: ${args.join(' ')}`);
        this.outputChannel.appendLine(`Working directory: ${serverPath}`);
        
        process = spawn(pythonPath, args, {
          cwd: serverPath,  // Use server directory as working directory
          stdio: ['ignore', 'pipe', 'pipe']
        });
        
        this.outputChannel.appendLine(`Process spawned with PID: ${process.pid}`);
      } catch (error) {
        this.outputChannel.appendLine(`Failed to spawn process: ${error}`);
        resolve({
          success: false,
          error: { type: "validation_error", message: `Failed to start engine process: ${error}` }
        });
        return;
      }

      this.runningProcesses.add(process);
      let stdout = '';
      let stderr = '';
      let resolved = false;

      // Set up timeout
      const timeout = setTimeout(() => {
        if (!resolved) {
          resolved = true;
          process.kill();
          this.runningProcesses.delete(process);
          resolve({
            success: false,
            error: {
              type: "validation_error",
              message: `Engine process timed out after ${this.config.timeout}ms`
            }
          });
        }
      }, this.config.timeout);

      // Handle cancellation
      const cancellationListener = cancellationToken?.onCancellationRequested(() => {
        if (!resolved) {
          resolved = true;
          process.kill();
          this.runningProcesses.delete(process);
          clearTimeout(timeout);
          resolve({
            success: false,
            error: {
              type: "validation_error",
              message: "Engine process was cancelled"
            }
          });
        }
      });

      // Collect output with null checks
      if (process.stdout) {
        process.stdout.on('data', (data) => {
          stdout += data.toString();
        });
      }

      if (process.stderr) {
        process.stderr.on('data', (data) => {
          const text = data.toString();
          stderr += text;
          // Log stderr to output channel in real-time for debugging
          this.outputChannel.append(text);
        });
      }

      process.on('close', (code) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          cancellationListener?.dispose();
          this.runningProcesses.delete(process);

          if (code === 0) {
            // Success - parse JSON output
            const result = decodeScanResult(stdout);
            if (result.success) {
              this.outputChannel.appendLine(`Engine completed successfully: ${result.data?.findings.length || 0} findings`);
            } else {
              this.outputChannel.appendLine(`Engine output parsing failed: ${result.error?.message}`);
            }
            resolve(result);
          } else {
            // Error exit code
            this.outputChannel.appendLine(`Engine process exited with code ${code}`);
            this.outputChannel.appendLine(`Stderr: ${stderr}`);
            resolve({
              success: false,
              error: {
                type: "validation_error",
                message: `Engine process failed with exit code ${code}`,
                details: { stderr, stdout }
              }
            });
          }
        }
      });

      process.on('error', (error) => {
        if (!resolved) {
          resolved = true;
          clearTimeout(timeout);
          cancellationListener?.dispose();
          this.runningProcesses.delete(process);
          
          this.outputChannel.appendLine(`Engine process error: ${error.message}`);
          resolve({
            success: false,
            error: {
              type: "validation_error",
              message: `Failed to start engine process: ${error.message}`,
              details: error
            }
          });
        }
      });
    });
  }

  /**
   * Auto-detect languages in the workspace based on file extensions.
   */
  private async detectLanguages(workspaceRoot: string): Promise<string[]> {
    const languages: Set<string> = new Set();

    // Look for common file patterns
    const patterns = [
      { pattern: '**/*.py', language: 'python' },
      { pattern: '**/*.ts', language: 'typescript' },
      { pattern: '**/*.tsx', language: 'typescript' },
      { pattern: '**/*.js', language: 'javascript' },
      { pattern: '**/*.jsx', language: 'javascript' },
      { pattern: '**/*.mjs', language: 'javascript' },
      { pattern: '**/*.cjs', language: 'javascript' }
    ];

    for (const { pattern, language } of patterns) {
      try {
        const files = await vscode.workspace.findFiles(pattern, '**/node_modules/**', 1);
        if (files.length > 0) {
          languages.add(language);
        }
      } catch (error) {
        // Ignore errors in file searching
      }
    }

    return Array.from(languages);
  }

  /**
   * Scan the entire workspace for issues.
   */
  async scanWorkspace(cancellationToken?: vscode.CancellationToken): Promise<ValidationResult> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: "No workspace folder found"
        }
      };
    }

    const workspaceRoot = workspaceFolders[0].uri.fsPath;
    const languages = await this.detectLanguages(workspaceRoot);

    if (languages.length === 0) {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: "No supported languages detected in workspace"
        }
      };
    }

    this.outputChannel.appendLine(`Detected languages: ${languages.join(', ')}`);

    // For now, scan each language separately and combine results
    // In the future, the engine might support multiple languages in one call
    const allFindings: Finding[] = [];
    let totalFilesScanned = 0;
    let totalRulesRun = 0;
    let totalMetrics = { parse_ms: 0, rules_ms: 0, total_ms: 0 };

    for (const language of languages) {
      const options: ScanOptions = {
        paths: [workspaceRoot],
        language: language,
        discover: 'server.rules',
        jobs: this.config.maxJobs,
        validate: true
      };

      const result = await this.runEngine(options, workspaceRoot, cancellationToken);
      if (!result.success) {
        return result; // Return first error
      }

      if (result.data) {
        allFindings.push(...result.data.findings);
        totalFilesScanned += result.data.files_scanned;
        totalRulesRun += result.data.rules_run;
        totalMetrics.parse_ms += result.data.metrics.parse_ms;
        totalMetrics.rules_ms += result.data.metrics.rules_ms;
        totalMetrics.total_ms += result.data.metrics.total_ms;
      }
    }

    // Combine results
    const combinedResult: ScanResult = {
      "aspect-code.protocol": "1",
      engine_version: "0.1.0", // This should come from the actual engine response
      files_scanned: totalFilesScanned,
      rules_run: totalRulesRun,
      findings: allFindings,
      metrics: totalMetrics
    };

    return {
      success: true,
      data: combinedResult
    };
  }

  /**
   * Scan single file.
   */
  async scanActiveFile(cancellationToken?: vscode.CancellationToken): Promise<ValidationResult> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: "No active file to scan"
        }
      };
    }

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: "No workspace folder found"
        }
      };
    }

    const workspaceRoot = workspaceFolders[0].uri.fsPath;
    const filePath = activeEditor.document.uri.fsPath;

    // Auto-detect language from file extension
    const ext = path.extname(filePath).toLowerCase();
    let language = 'python'; // default

    if (['.ts', '.tsx'].includes(ext)) {
      language = 'typescript';
    } else if (['.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
      language = 'javascript';
    } else if (['.py'].includes(ext)) {
      language = 'python';
    } else {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: `Unsupported file type: ${ext}`
        }
      };
    }

    const options: ScanOptions = {
      paths: [filePath],
      language: language,
      discover: 'rules',
      jobs: 1, // Single file, single job
      validate: true
    };

    return await this.runEngine(options, workspaceRoot, cancellationToken);
  }

  /**
   * Dispose of the engine service.
   */
  dispose(): void {
    // Kill any running processes
    for (const process of this.runningProcesses) {
      process.kill();
    }
    this.runningProcesses.clear();
  }
}
