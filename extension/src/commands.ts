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
import { AspectCodeState } from './state';

export class AspectCodeCommands {
  private engineService: AspectCodeEngineService;
  private outputChannel: vscode.OutputChannel;
  private diagnostics: vscode.DiagnosticCollection;
  private statusBarItem: vscode.StatusBarItem;
  private state: AspectCodeState;
  private currentOperationCts: vscode.CancellationTokenSource | null = null;

  constructor(context: vscode.ExtensionContext, state: AspectCodeState) {
    this.outputChannel = vscode.window.createOutputChannel('Aspect Code');
    this.engineService = new AspectCodeEngineService({}, this.outputChannel);
    this.diagnostics = vscode.languages.createDiagnosticCollection('aspectcode');
    this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.statusBarItem.text = '$(beaker) Aspect Code';
    this.statusBarItem.tooltip = 'Aspect Code';
    this.statusBarItem.show();
    this.state = state;

    // Register for cleanup
    context.subscriptions.push(
      this.outputChannel,
      this.diagnostics,
      this.statusBarItem,
      this.engineService
    );
  }

  /**
   * Cancel any in-flight work started by this command set.
   * Used by the global enable/disable switch.
   */
  cancelAllRunningWork(): void {
    try {
      this.currentOperationCts?.cancel();
      this.currentOperationCts?.dispose();
    } catch {
      // ignore
    } finally {
      this.currentOperationCts = null;
    }

    try {
      this.engineService.stopAllRunningProcesses();
    } catch {
      // ignore
    }

    // Ensure panel UI is not left stuck.
    try {
      this.state.update({ busy: false });
    } catch {
      // ignore
    }
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
   * Scan commands removed (OSS-only): Aspect Code uses dependency graph + KB.
   */

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