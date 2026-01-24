/**
 * Aspect Code Extension Commands
 * 
 * This module implements the extension commands for local KB generation
 * and code actions.
 */

import * as vscode from 'vscode';
import { AspectCodeState } from './state';

export class AspectCodeCommands {
  private outputChannel: vscode.OutputChannel;
  private statusBarItem: vscode.StatusBarItem;
  private state: AspectCodeState;
  private currentOperationCts: vscode.CancellationTokenSource | null = null;

  constructor(context: vscode.ExtensionContext, state: AspectCodeState) {
    this.outputChannel = vscode.window.createOutputChannel('Aspect Code');
    this.statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    this.statusBarItem.text = '$(beaker) Aspect Code';
    this.statusBarItem.tooltip = 'Aspect Code';
    this.statusBarItem.show();
    this.state = state;

    // Register for cleanup
    context.subscriptions.push(
      this.outputChannel,
      this.statusBarItem
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

    // Ensure panel UI is not left stuck.
    try {
      this.state.update({ busy: false });
    } catch {
      // ignore
    }
  }
}