import * as vscode from 'vscode';

export type AssistantId = 'copilot' | 'cursor' | 'claude' | 'other' | 'alignments' | 'aspectKB';

/**
 * Detects which AI assistants are likely in use by checking for their config files.
 * Also detects if Aspect Code KB (.aspect/) exists, indicating prior configuration.
 */
export async function detectAssistants(workspaceRoot: vscode.Uri): Promise<Set<AssistantId>> {
  const detected = new Set<AssistantId>();

  // Aspect Code KB: .aspect/ directory (indicates extension was previously configured)
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, '.aspect'));
    detected.add('aspectKB');
  } catch {}

  // Copilot: .github/copilot-instructions.md
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, '.github', 'copilot-instructions.md'));
    detected.add('copilot');
  } catch {}

  // Cursor: .cursor/ or .cursorrules
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, '.cursor'));
    detected.add('cursor');
  } catch {
    try {
      await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, '.cursorrules'));
      detected.add('cursor');
    } catch {}
  }

  // Claude: CLAUDE.md
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, 'CLAUDE.md'));
    detected.add('claude');
  } catch {}

  // Other: AGENTS.md
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, 'AGENTS.md'));
    detected.add('other');
  } catch {}

  // Alignments: ALIGNMENTS.json
  try {
    await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, 'ALIGNMENTS.json'));
    detected.add('alignments');
  } catch {}

  return detected;
}
