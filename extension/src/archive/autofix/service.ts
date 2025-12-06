/**
 * Auto-Fix v1 Service
 * 
 * Service for applying Auto-Fix v1 rules via the backend API.
 */

import * as vscode from 'vscode';
import * as path from 'path';
import { AUTO_FIX_V1_RULE_IDS, isAutoFixV1Rule, AutofixRequest, AutofixResponse } from './config';
import { Finding } from '../../types/protocol';
import * as http from '../../http';

export class AutofixV1Service {
    private outputChannel: vscode.OutputChannel;

    constructor(outputChannel: vscode.OutputChannel) {
        this.outputChannel = outputChannel;
    }

    /**
     * Check if a finding can be auto-fixed with v1 pipeline.
     */
    canAutoFix(finding: Finding): boolean {
        // For Auto-Fix v1, we only need the rule ID to be in the safe set
        // The backend generates fixes dynamically, so we don't require autofix data
        return isAutoFixV1Rule(finding.rule_id);
    }

    /**
     * Filter findings to only those that can be auto-fixed.
     */
    filterAutoFixableFindings(findings: Finding[]): Finding[] {
        const autofixable: Finding[] = [];
        
        for (const finding of findings) {
            if (this.canAutoFix(finding)) {
                autofixable.push(finding);
            }
        }
        
        return autofixable;
    }

    /**
     * Apply auto-fix for a single finding.
     */
    async applyFindingAutofix(finding: Finding, workspaceRoot: string): Promise<boolean> {
        if (!this.canAutoFix(finding)) {
            this.outputChannel.appendLine(`Cannot auto-fix rule ${finding.rule_id} - not in AUTO_FIX_V1_RULE_IDS`);
            return false;
        }

        const request: AutofixRequest = {
            repo_root: workspaceRoot,
            rule_id: finding.rule_id,
            file_path: finding.file_path,
            start_byte: finding.start_byte,
            end_byte: finding.end_byte,
            max_fixes: 1
        };

        try {
            const response = await this.callAutofixAPI(request);
            
            if (response.fixes_applied > 0) {
                await this.applyFixesToWorkspace(response);
                this.outputChannel.appendLine(`Applied ${response.fixes_applied} fixes for ${finding.rule_id}`);
                return true;
            } else {
                this.outputChannel.appendLine(`No fixes applied for ${finding.rule_id}`);
                if (response.skipped && response.skipped.length > 0) {
                    for (const skip of response.skipped) {
                        this.outputChannel.appendLine(`  Skipped: ${skip.reason}`);
                    }
                }
                return false;
            }

        } catch (error) {
            this.outputChannel.appendLine(`Auto-fix failed for ${finding.rule_id}: ${error}`);
            return false;
        }
    }

    /**
     * Apply auto-fixes for multiple findings.
     * Returns applied/failed counts and list of modified file paths (absolute).
     */
    async applyBatchAutofix(findings: Finding[], workspaceRoot: string): Promise<{ applied: number; failed: number; modifiedFiles: string[] }> {
        const autofixableFindings = this.filterAutoFixableFindings(findings);
        
        if (autofixableFindings.length === 0) {
            this.outputChannel.appendLine('No auto-fixable findings found');
            return { applied: 0, failed: 0, modifiedFiles: [] };
        }

        this.outputChannel.appendLine(`Applying auto-fixes for ${autofixableFindings.length} findings...`);

        const request: AutofixRequest = {
            repo_root: workspaceRoot,
            max_fixes: autofixableFindings.length
        };

        try {
            const response = await this.callAutofixAPI(request);
            
            if (response.fixes_applied > 0) {
                await this.applyFixesToWorkspace(response);
                this.outputChannel.appendLine(`Successfully applied ${response.fixes_applied} fixes across ${response.files_changed} files`);
                
                // Collect absolute paths of modified files
                const modifiedFiles: string[] = [];
                if (response.files) {
                    for (const file of response.files) {
                        const absPath = path.isAbsolute(file.relpath) 
                            ? file.relpath 
                            : path.join(workspaceRoot, file.relpath);
                        modifiedFiles.push(absPath);
                    }
                }
                
                return { applied: response.fixes_applied, failed: 0, modifiedFiles };
            } else {
                this.outputChannel.appendLine('No fixes were applied');
                if (response.skipped && response.skipped.length > 0) {
                    for (const skip of response.skipped) {
                        this.outputChannel.appendLine(`  Skipped: ${skip.reason}`);
                    }
                }
                return { applied: 0, failed: autofixableFindings.length, modifiedFiles: [] };
            }

        } catch (error) {
            this.outputChannel.appendLine(`Batch auto-fix failed: ${error}`);
            return { applied: 0, failed: autofixableFindings.length, modifiedFiles: [] };
        }
    }

    /**
     * Apply auto-fixes for a specific file.
     */
    async applyFileAutofix(filePath: string, workspaceRoot: string): Promise<boolean> {
        const request: AutofixRequest = {
            repo_root: workspaceRoot,
            file_path: filePath,
            max_fixes: 50  // Reasonable limit for single file
        };

        try {
            const response = await this.callAutofixAPI(request);
            
            if (response.fixes_applied > 0) {
                await this.applyFixesToWorkspace(response);
                this.outputChannel.appendLine(`Applied ${response.fixes_applied} fixes to ${filePath}`);
                return true;
            } else {
                this.outputChannel.appendLine(`No fixes applied to ${filePath}`);
                return false;
            }

        } catch (error) {
            this.outputChannel.appendLine(`Auto-fix failed for ${filePath}: ${error}`);
            return false;
        }
    }

    /**
     * Call the backend auto-fix API.
     */
    private async callAutofixAPI(request: AutofixRequest): Promise<AutofixResponse> {
        const response = await http.post<AutofixResponse>('/autofix', request);
        return response;
    }

    /**
     * Apply fixes returned by the API to the workspace.
     */
    private async applyFixesToWorkspace(response: AutofixResponse): Promise<void> {
        if (!response.files || response.files.length === 0) {
            return;
        }

        // Get workspace root for resolving relative paths
        const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
        if (!workspaceFolder) {
            this.outputChannel.appendLine('No workspace folder found for applying fixes');
            return;
        }

        this.outputChannel.appendLine(`Workspace root: ${workspaceFolder.uri.fsPath}`);
        this.outputChannel.appendLine(`Response has ${response.files.length} files to fix:`);
        for (const file of response.files) {
            this.outputChannel.appendLine(`  - ${file.relpath}`);
        }

        const edit = new vscode.WorkspaceEdit();

        for (const file of response.files) {
            try {
                // Resolve path relative to workspace root, not VS Code's cwd
                let uri: vscode.Uri;
                if (path.isAbsolute(file.relpath)) {
                    // If already absolute, use as-is
                    uri = vscode.Uri.file(file.relpath);
                } else {
                    // Resolve relative to workspace root
                    const absolutePath = path.join(workspaceFolder.uri.fsPath, file.relpath);
                    uri = vscode.Uri.file(absolutePath);
                }

                this.outputChannel.appendLine(`Applying fixes to: ${uri.fsPath}`);
                
                // Read current file content
                const document = await vscode.workspace.openTextDocument(uri);
                const fullRange = new vscode.Range(
                    document.positionAt(0),
                    document.positionAt(document.getText().length)
                );

                // Replace entire file content with fixed version
                edit.replace(uri, fullRange, file.content);

            } catch (error) {
                this.outputChannel.appendLine(`Failed to apply fixes to ${file.relpath}: ${error}`);
            }
        }

        // Apply all edits as a single operation (for undo)
        const success = await vscode.workspace.applyEdit(edit);
        
        if (success) {
            // Show notification
            if (response.files_changed === 1) {
                vscode.window.showInformationMessage(
                    `Applied ${response.fixes_applied} auto-fixes to ${response.files_changed} file. Undo available.`
                );
            } else {
                vscode.window.showInformationMessage(
                    `Applied ${response.fixes_applied} auto-fixes across ${response.files_changed} files. Undo available.`
                );
            }
        } else {
            vscode.window.showErrorMessage('Failed to apply auto-fixes to workspace');
        }
    }

    /**
     * Get list of auto-fixable rule IDs for UI filtering.
     */
    getAutoFixableRuleIds(): ReadonlySet<string> {
        return AUTO_FIX_V1_RULE_IDS;
    }
}