import * as vscode from 'vscode';

export type AssistantId = 'copilot' | 'cursor' | 'claude' | 'other' | 'alignments' | 'aspectKB';

/**
 * Detects which AI assistants are likely in use by checking for their config files.
 * Also detects if Aspect Code KB (.aspect/) exists, indicating prior configuration.
 * Uses parallel file stat operations for speed.
 */
export async function detectAssistants(workspaceRoot: vscode.Uri): Promise<Set<AssistantId>> {
  const detected = new Set<AssistantId>();

  // Check all paths in parallel for maximum speed
  const checks: Array<{ id: AssistantId; paths: string[] }> = [
    { id: 'aspectKB', paths: ['.aspect'] },
    { id: 'copilot', paths: ['.github/copilot-instructions.md'] },
    { id: 'cursor', paths: ['.cursor', '.cursorrules'] },
    { id: 'claude', paths: ['CLAUDE.md'] },
    { id: 'other', paths: ['AGENTS.md'] },
    { id: 'alignments', paths: ['ALIGNMENTS.json'] }
  ];

  const allPromises = checks.flatMap(check => 
    check.paths.map(async p => {
      try {
        await vscode.workspace.fs.stat(vscode.Uri.joinPath(workspaceRoot, p));
        return check.id;
      } catch {
        return null;
      }
    })
  );

  const results = await Promise.allSettled(allPromises);
  
  for (const result of results) {
    if (result.status === 'fulfilled' && result.value) {
      detected.add(result.value);
    }
  }

  return detected;
}
