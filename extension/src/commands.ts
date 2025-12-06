/**
 * Aspect Code Extension Commands
 * 
 * This module implements the new extension commands using the engine service
 * and JSON protocol v1.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeEngineService } from './engineService';
import { Finding, ScanResult, createSuppressionComment } from './types/protocol';
import { AutofixV1Service } from './archive/autofix/service';
import { isAutoFixV1Finding } from './archive/autofix/config';
import { AspectCodeState } from './state';
import { getIncrementalIndexer } from './extension';

export class AspectCodeCommands {
  private engineService: AspectCodeEngineService;
  private autofixService: AutofixV1Service;
  private outputChannel: vscode.OutputChannel;
  private diagnostics: vscode.DiagnosticCollection;
  private state: AspectCodeState;

  constructor(context: vscode.ExtensionContext, state: AspectCodeState) {
    this.outputChannel = vscode.window.createOutputChannel('Aspect Code');
    this.engineService = new AspectCodeEngineService({}, this.outputChannel);
    this.autofixService = new AutofixV1Service(this.outputChannel);
    this.diagnostics = vscode.languages.createDiagnosticCollection('aspectcode');
    this.state = state;

    // Register for cleanup
    context.subscriptions.push(
      this.outputChannel,
      this.diagnostics,
      this.engineService
    );
  }

  /**
   * Convert findings to VS Code diagnostics.
   */
  private findingsToDiagnostics(findings: Finding[]): Map<string, vscode.Diagnostic[]> {
    const diagnosticsMap = new Map<string, vscode.Diagnostic[]>();

    for (const finding of findings) {
      // Use finding.uri with fallback to file path
      let uri: vscode.Uri;
      try {
        uri = vscode.Uri.parse(finding.uri);
      } catch {
        uri = vscode.Uri.file(finding.file_path);
      }

      // Convert severity
      let severity: vscode.DiagnosticSeverity;
      switch (finding.severity) {
        case 'error':
          severity = vscode.DiagnosticSeverity.Error;
          break;
        case 'warning':
          severity = vscode.DiagnosticSeverity.Warning;
          break;
        case 'info':
          severity = vscode.DiagnosticSeverity.Information;
          break;
        default:
          severity = vscode.DiagnosticSeverity.Warning;
      }

      // Create VS Code range from protocol range
      const range = new vscode.Range(
        new vscode.Position(finding.range.startLine - 1, finding.range.startCol),
        new vscode.Position(finding.range.endLine - 1, finding.range.endCol)
      );

      // Create diagnostic
      const diagnostic = new vscode.Diagnostic(range, finding.message, severity);
      diagnostic.source = 'aspectcode';
      diagnostic.code = finding.rule_id;

      // Store finding data for code actions
      (diagnostic as any).aspectcodeFinding = finding;

      // Add to map
      const fileKey = uri.toString();
      if (!diagnosticsMap.has(fileKey)) {
        diagnosticsMap.set(fileKey, []);
      }
      diagnosticsMap.get(fileKey)!.push(diagnostic);
    }

    return diagnosticsMap;
  }

  /**
   * Update diagnostics from scan results.
   */
  private updateDiagnostics(result: ScanResult): void {
    // Clear existing diagnostics
    this.diagnostics.clear();

    // Convert findings to diagnostics
    const diagnosticsMap = this.findingsToDiagnostics(result.findings);

    // Diagnostics rendering disabled - findings are shown in Aspect Code panel instead
    // This prevents yellow underlines in the editor while keeping findings functional
    // Uncomment the lines below to re-enable diagnostics in Problems panel:
    // for (const [uriString, fileDiagnostics] of diagnosticsMap) {
    //   const uri = vscode.Uri.parse(uriString);
    //   this.diagnostics.set(uri, fileDiagnostics);
    // }

    // Update status bar
    const errorCount = result.findings.filter(f => f.severity === 'error').length;
    const warningCount = result.findings.filter(f => f.severity === 'warning').length;
    const totalCount = result.findings.length;

    if (totalCount > 0) {
      this.statusBarItem.text = `$(beaker) Aspect Code: ${errorCount + warningCount} issues`;
      this.statusBarItem.tooltip = `${errorCount} errors, ${warningCount} warnings`;
    } else {
      this.statusBarItem.text = '$(beaker) Aspect Code ✓';
      this.statusBarItem.tooltip = 'No issues found';
    }

    // Show summary message
    this.outputChannel.appendLine(`Scan complete: ${totalCount} findings (${errorCount} errors, ${warningCount} warnings)`);
    this.outputChannel.appendLine(`Processed ${result.files_scanned} files with ${result.rules_run} rules in ${result.metrics.total_ms}ms`);
  }

  /**
   * Get all current findings from state (primary) with fallback to diagnostics
   */
  getCurrentFindings(): Finding[] {
    // Try to get findings from the main state first (panel's source of truth)
    const fromState = this.state.s.findings || [];
    
    if (fromState.length > 0) {
      // Map state findings to protocol Finding format if needed
      const findings = fromState.map((f: any) => {
        // If already in correct format, return as is
        if (f.rule_id && f.file_path && f.range && f.start_byte !== undefined && f.end_byte !== undefined) {
          return f as Finding;
        }
        
        // Otherwise try to map from state format to protocol format
        return {
          rule_id: f.code || f.rule_id || 'unknown',
          message: f.message || 'No message',
          severity: f.severity === 'critical' ? 'error' : (f.severity || 'warning'),
          file_path: f.file || f.file_path || '',
          uri: f.uri || `file://${f.file || f.file_path}`,
          start_byte: f.start_byte || 0,
          end_byte: f.end_byte || 0,
          range: f.span ? {
            startLine: f.span.start.line + 1,
            startCol: f.span.start.column,
            endLine: f.span.end.line + 1,
            endCol: f.span.end.column
          } : (f.range || { startLine: 1, startCol: 0, endLine: 1, endCol: 0 }),
          autofix: f.autofix || [],
          meta: f.meta || {}
        } as Finding;
      });
      
      return findings;
    }

    // Fallback to diagnostics if state is empty
    const findings: Finding[] = [];
    this.diagnostics.forEach((uri, diagnostics) => {
      for (const diagnostic of diagnostics) {
        const finding = (diagnostic as any).aspectcodeFinding as Finding;
        if (finding) {
          findings.push(finding);
        }
      }
    });
    
    return findings;
  }

  /**
   * Scan workspace command with category filtering.
   */
  async scanWorkspace(): Promise<void> {
    this.outputChannel.show();
    this.outputChannel.appendLine('=== Scanning workspace ===');
    this.statusBarItem.text = '$(loading~spin) Aspect Code: Scanning...';

    try {
      // Get configuration for rule filtering
      const config = vscode.workspace.getConfiguration('aspectcode');
      const enabledRules = config.get<string[]>('rules.enabled', ['*']);
      const categories = config.get<string[]>('rules.categories', []);
      const maxJobs = config.get<number>('engine.maxJobs', 4);

      const result = await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Aspect Code: Scanning workspace...',
        cancellable: true
      }, async (progress, token) => {
        const scanOptions = {
          categories: categories.length > 0 ? categories : undefined,
          rules: enabledRules.length > 0 && enabledRules[0] !== '*' ? enabledRules.join(',') : undefined,
          jobs: maxJobs
        };
        
        // Combine scanOptions with the engine service call
        return await this.engineService.scanWorkspace(token);
      });

      if (result.success && result.data) {
        this.updateDiagnostics(result.data);
        
        // Enhanced reporting with category breakdown
        const findings = result.data.findings;
        const categories = new Map<string, number>();
        
        findings.forEach(f => {
          const category = f.rule_id.split('.')[0];
          categories.set(category, (categories.get(category) || 0) + 1);
        });
        
        const categoryReport = Array.from(categories.entries())
          .map(([cat, count]) => `${cat}: ${count}`)
          .join(', ');
        
        this.outputChannel.appendLine(`Category breakdown: ${categoryReport}`);
        
        vscode.window.showInformationMessage(
          `Aspect Code: Found ${result.data.findings.length} issues in ${result.data.files_scanned} files`
        );
      } else {
        this.statusBarItem.text = '$(beaker) Aspect Code: Error';
        this.statusBarItem.tooltip = result.error?.message || 'Unknown error';
        vscode.window.showErrorMessage(`Aspect Code scan failed: ${result.error?.message || 'Unknown error'}`);
        this.outputChannel.appendLine(`Scan failed: ${result.error?.message}`);
      }
    } catch (error) {
      this.statusBarItem.text = '$(beaker) Aspect Code: Error';
      vscode.window.showErrorMessage(`Aspect Code scan failed: ${error}`);
      this.outputChannel.appendLine(`Scan error: ${error}`);
    }
  }

  /**
   * Scan active file command.
   */
  async scanActiveFile(): Promise<void> {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage('No active file to scan');
      return;
    }

    this.outputChannel.appendLine(`=== Scanning active file: ${path.basename(activeEditor.document.fileName)} ===`);

    try {
      const result = await vscode.window.withProgress({
        location: vscode.ProgressLocation.Window,
        title: 'Aspect Code: Scanning file...',
        cancellable: true
      }, async (progress, token) => {
        return await this.engineService.scanActiveFile(token);
      });

      if (result.success && result.data) {
        // Only update diagnostics for the active file
        const diagnosticsMap = this.findingsToDiagnostics(result.data.findings);
        const activeUri = activeEditor.document.uri;
        
        // Clear diagnostics for active file and set new ones
        const fileDiagnostics = diagnosticsMap.get(activeUri.toString()) || [];
        this.diagnostics.set(activeUri, fileDiagnostics);

        vscode.window.showInformationMessage(
          `Aspect Code: Found ${result.data.findings.length} issues in ${path.basename(activeEditor.document.fileName)}`
        );
        this.outputChannel.appendLine(`File scan complete: ${result.data.findings.length} findings`);
      } else {
        vscode.window.showErrorMessage(`Aspect Code file scan failed: ${result.error?.message || 'Unknown error'}`);
        this.outputChannel.appendLine(`File scan failed: ${result.error?.message}`);
      }
    } catch (error) {
      vscode.window.showErrorMessage(`Aspect Code file scan failed: ${error}`);
      this.outputChannel.appendLine(`File scan error: ${error}`);
    }
  }

  /**
   * Apply autofix command using Auto-Fix v1 pipeline.
   */
  async applyAutofix(findings?: Finding[]): Promise<void> {
    let targetFindings = findings;

    if (!targetFindings) {
      // Get all findings from state/diagnostics
      targetFindings = this.getCurrentFindings();

      if (targetFindings.length === 0) {
        vscode.window.showInformationMessage('No findings available to fix');
        return;
      }
    }

    // Filter for Auto-Fix v1 compatible findings
    const autofixableFindings = this.autofixService.filterAutoFixableFindings(targetFindings);
    
    if (autofixableFindings.length === 0) {
      vscode.window.showInformationMessage('No Auto-Fix v1 compatible findings available');
      return;
    }

    // Auto-apply fixes without confirmation dialog
    const result = 'Apply'; // Skip modal and proceed directly

    if (result !== 'Apply') {
      // Clear busy state on cancel
      this.state.update({ busy: false });
      return;
    }

    // Get workspace root
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) {
      vscode.window.showErrorMessage('No workspace folder found');
      return;
    }

    this.outputChannel.appendLine(`=== Applying ${autofixableFindings.length} Auto-Fix v1 fixes ===`);

    try {
      // Set busy state for panel integration
      this.state.update({ busy: true });
      
      const result = await this.autofixService.applyBatchAutofix(
        autofixableFindings, 
        workspaceFolder.uri.fsPath
      );
      
      this.outputChannel.appendLine(`Auto-Fix applied: ${result.applied} fixes, ${result.failed} failed`);
      
      if (result.applied > 0) {
        this.outputChannel.appendLine(`[Auto-Fix v1] Applied ${result.applied} fixes`);
        this.outputChannel.appendLine(`[Auto-Fix v1] Modified files: ${result.modifiedFiles.map(f => path.basename(f)).join(', ')}`);
        
        // Explicitly save all modified documents
        this.outputChannel.appendLine(`[Auto-Fix v1] Saving all modified files...`);
        const saveSuccess = await vscode.workspace.saveAll();
        
        if (saveSuccess) {
          this.outputChannel.appendLine(`[Auto-Fix v1] Successfully saved all files`);
        } else {
          this.outputChannel.appendLine(`[Auto-Fix v1] Warning: Some files may not have been saved`);
        }
        
        // Re-run analysis to refresh panel state - use incremental if available
        this.outputChannel.appendLine(`[Auto-Fix v1] Re-running validation to update findings...`);
        await this.rerunAnalysis(result.modifiedFiles);
        
        // Clear loading state after re-validation completes
        this.state.update({ busy: false });
        
        vscode.window.showInformationMessage(
          `Auto-Fix v1: Applied ${result.applied} fixes successfully! Analysis refreshed.`
        );
        this.outputChannel.appendLine(`[Auto-Fix v1] SUCCESS: Applied ${result.applied} fixes and refreshed analysis`);
      } else if (result.failed > 0) {
        // Clear loading state on no fixes applied
        this.state.update({ busy: false });
        
        vscode.window.showWarningMessage(
          `Auto-Fix v1: No fixes could be applied. Check output for details.`
        );
        this.outputChannel.appendLine(`[Auto-Fix v1] WARNING: No fixes applied, ${result.failed} failed`);
      }

    } catch (error) {
      // Clear loading state on error
      this.state.update({ busy: false });
      
      this.outputChannel.appendLine(`[Auto-Fix v1] ERROR: ${error}`);
      vscode.window.showErrorMessage(`Auto-Fix v1 failed: ${error}`);
    }
  }

  /**
   * Open finding command.
   */
  async openFinding(finding: Finding): Promise<void> {
    try {
      // Use finding.uri with fallback to file path
      let uri: vscode.Uri;
      try {
        uri = vscode.Uri.parse(finding.uri);
      } catch {
        uri = vscode.Uri.file(finding.file_path);
      }

      // Open the document
      const document = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(document);

      // Navigate to the finding location
      const position = new vscode.Position(
        finding.range.startLine - 1,
        finding.range.startCol
      );
      const range = new vscode.Range(position, position);

      editor.selection = new vscode.Selection(position, position);
      editor.revealRange(range, vscode.TextEditorRevealType.InCenter);

      this.outputChannel.appendLine(`Opened finding: ${finding.rule_id} in ${path.basename(finding.file_path)}`);
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to open finding: ${error}`);
      this.outputChannel.appendLine(`Open finding error: ${error}`);
    }
  }

  /**
   * Insert suppression comment for a finding.
   */
  async insertSuppression(finding: Finding): Promise<void> {
    try {
      // Use finding.uri with fallback to file path
      let uri: vscode.Uri;
      try {
        uri = vscode.Uri.parse(finding.uri);
      } catch {
        uri = vscode.Uri.file(finding.file_path);
      }

      const document = await vscode.workspace.openTextDocument(uri);
      const editor = await vscode.window.showTextDocument(document);

      // Create suppression comment
      const suppressionComment = createSuppressionComment(finding);
      
      // Insert at the line before the finding
      const insertLine = Math.max(0, finding.range.startLine - 2); // Convert to 0-based and go one line before
      const insertPosition = new vscode.Position(insertLine, 0);
      
      // Get the indentation of the finding line
      const findingLine = document.lineAt(Math.max(0, finding.range.startLine - 1));
      const indentMatch = findingLine.text.match(/^\\s*/);
      const indent = indentMatch ? indentMatch[0] : '';
      
      const edit = new vscode.WorkspaceEdit();
      edit.insert(uri, insertPosition, `${indent}${suppressionComment}\\n`);
      
      await vscode.workspace.applyEdit(edit);
      
      vscode.window.showInformationMessage(`Inserted suppression comment for ${finding.rule_id}`);
      this.outputChannel.appendLine(`Inserted suppression: ${suppressionComment}`);
    } catch (error) {
      vscode.window.showErrorMessage(`Failed to insert suppression: ${error}`);
      this.outputChannel.appendLine(`Suppression error: ${error}`);
    }
  }

  /**
   * Re-run full repository analysis (same as "Analyze workspace" command)
   */
  async rerunAnalysis(modifiedFiles?: string[]): Promise<void> {
    // Try to use incremental validation for better performance
    const incrementalIndexer = getIncrementalIndexer();
    
    if (modifiedFiles && modifiedFiles.length > 0 && incrementalIndexer?.isInitialized()) {
      this.outputChannel.appendLine(`[Auto-Fix v1] Using incremental validation for ${modifiedFiles.length} modified files`);
      
      try {
        await incrementalIndexer.handleBulkChange(modifiedFiles);
        this.outputChannel.appendLine('[Auto-Fix v1] Incremental validation complete');
        return;
      } catch (error) {
        this.outputChannel.appendLine(`[Auto-Fix v1] Incremental validation failed: ${error}, falling back to full validation`);
        // Fall through to full validation
      }
    }
    
    // Fall back to full validation
    this.outputChannel.appendLine('[Auto-Fix v1] Running full validation...');
    
    try {
      // Trigger the validate command which calls validateFullRepository
      await vscode.commands.executeCommand('aspectcode.examine');
      
    } catch (error) {
      this.outputChannel.appendLine(`[Auto-Fix v1] Analysis failed: ${error}`);
    }
  }

  async configureRules(): Promise<void> {
    const availableCategories = [
      { label: 'imports.*', description: 'Import analysis (unused, cycles, side effects)', value: 'imports' },
      { label: 'security.*', description: 'Security vulnerabilities (XSS, SQL injection, etc.)', value: 'security' },
      { label: 'memory.*', description: 'Memory management issues (leaks, use-after-free)', value: 'memory' },
      { label: 'deadcode.*', description: 'Dead code detection (unused variables, functions)', value: 'deadcode' },
      { label: 'style.*', description: 'Code style issues (formatting, conventions)', value: 'style' },
      { label: 'complexity.*', description: 'Code complexity metrics', value: 'complexity' },
      { label: 'concurrency.*', description: 'Concurrency issues (race conditions, locks)', value: 'concurrency' },
      { label: 'types.*', description: 'Type-related issues (TypeScript)', value: 'types' },
      { label: 'errors.*', description: 'Error handling patterns', value: 'errors' },
      { label: 'naming.*', description: 'Naming conventions and consistency', value: 'naming' },
      { label: 'performance.*', description: 'Performance anti-patterns', value: 'performance' }
    ];

    const config = vscode.workspace.getConfiguration('aspectcode');
    const currentCategories = config.get<string[]>('rules.categories', []);

    const selectedItems = await vscode.window.showQuickPick(availableCategories, {
      canPickMany: true,
      title: 'Select Rule Categories to Enable',
      placeHolder: 'Choose which categories of rules to run',
      ignoreFocusOut: true
    });

    if (selectedItems && selectedItems.length > 0) {
      const selectedCategories = selectedItems.map(item => item.value);
      
      // Update configuration
      await config.update('rules.categories', selectedCategories, vscode.ConfigurationTarget.Workspace);
      
      // Show confirmation
      vscode.window.showInformationMessage(
        `Enabled rule categories: ${selectedCategories.join(', ')}`
      );
      
      this.outputChannel.appendLine(`Updated rule categories: ${selectedCategories.join(', ')}`);
      
      // Offer to re-scan with new settings
      const rescan = await vscode.window.showInformationMessage(
        'Re-scan workspace with new rule categories?',
        'Yes', 'No'
      );
      
      if (rescan === 'Yes') {
        this.scanWorkspace();
      }
    }
  }
}

/**
 * Code Action Provider for Aspect Code diagnostics.
 */
export class AspectCodeCodeActionProvider implements vscode.CodeActionProvider {
  private commands: AspectCodeCommands;

  constructor(commands: AspectCodeCommands) {
    this.commands = commands;
  }

  provideCodeActions(
    document: vscode.TextDocument,
    range: vscode.Range | vscode.Selection,
    context: vscode.CodeActionContext,
    token: vscode.CancellationToken
  ): vscode.CodeAction[] {
    const actions: vscode.CodeAction[] = [];

    // Filter for Aspect Code diagnostics in the range
    const aspectcodeDiagnostics = context.diagnostics.filter(
      d => d.source === 'aspectcode' && (d as any).aspectcodeFinding
    );

    for (const diagnostic of aspectcodeDiagnostics) {
      const finding = (diagnostic as any).aspectcodeFinding as Finding;
      
      // Auto-fix action disabled - feature temporarily disabled
      /*
      // Add autofix action if available
      if (finding.autofix && finding.autofix.length > 0 && finding.meta?.autofix_safety === 'safe') {
        const autofixAction = new vscode.CodeAction(
          `Aspect Code: Apply autofix for ${finding.rule_id}`,
          vscode.CodeActionKind.QuickFix
        );
        autofixAction.command = {
          title: 'Apply autofix',
          command: 'aspectcode.applyAutofix',
          arguments: [[finding]]
        };
        autofixAction.diagnostics = [diagnostic];
        actions.push(autofixAction);
      }
      */

      // Add suppression action
      const suppressAction = new vscode.CodeAction(
        `Aspect Code: Insert suppression comment`,
        vscode.CodeActionKind.QuickFix
      );
      suppressAction.command = {
        title: 'Insert suppression comment',
        command: 'aspectcode.insertSuppression',
        arguments: [finding]
      };
      suppressAction.diagnostics = [diagnostic];
      actions.push(suppressAction);

      // Add "open finding" action for context
      const openAction = new vscode.CodeAction(
        `Aspect Code: Show details for ${finding.rule_id}`,
        vscode.CodeActionKind.Empty
      );
      openAction.command = {
        title: 'Show details',
        command: 'aspectcode.openFinding',
        arguments: [finding]
      };
      openAction.diagnostics = [diagnostic];
      actions.push(openAction);
    }

    return actions;
  }
}