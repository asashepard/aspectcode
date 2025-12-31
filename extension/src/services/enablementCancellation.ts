import * as vscode from 'vscode';

let currentCts = new vscode.CancellationTokenSource();

export function getEnablementCancellationToken(): vscode.CancellationToken {
  return currentCts.token;
}

export function cancelAllInFlightWork(): void {
  try {
    currentCts.cancel();
  } catch {
    // ignore
  }
}

export function resetEnablementCancellationToken(): void {
  try {
    currentCts.dispose();
  } catch {
    // ignore
  }
  currentCts = new vscode.CancellationTokenSource();
}

export function cancelAndResetAllInFlightWork(): void {
  cancelAllInFlightWork();
  resetEnablementCancellationToken();
}
