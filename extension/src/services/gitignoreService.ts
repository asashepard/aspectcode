/**
 * Gitignore Service for Aspect Code
 * 
 * Manages .gitignore entries for Aspect Code generated files.
 * Each target file (e.g., .aspect/, AGENTS.md, CLAUDE.md) is managed separately
 * with user opt-in stored in .aspect/.settings.json
 * 
 * Design principles:
 * - Opt-in per file: user is prompted for each target file separately
 * - Do not silently break existing .gitignore rules
 * - Do not add duplicate entries
 * - Do not reorder or rewrite .gitignore
 * - Prefer additive, minimal changes
 * - Behavior must be deterministic and idempotent
 * - Clear ownership of Aspect Code–managed entries via comment block
 */

import * as vscode from 'vscode';
import { 
  GitignoreTarget, 
  hasGitignorePreference, 
  getGitignorePreference, 
  promptGitignorePreference 
} from './aspectSettings';

// The comment line that marks Aspect Code–owned entries
const ASPECT_CODE_BLOCK_START = '# Aspect Code (local AI context)';

// Global state key for tracking first-time notification (kept for backwards compatibility)
const GITIGNORE_NOTIFICATION_SHOWN_KEY = 'aspectcode.gitignore.notificationShown';

/**
 * Map from target type to the actual gitignore pattern
 * (The GitignoreTarget is already the pattern itself, but we keep this for clarity)
 */
const TARGET_TO_PATTERN: Record<GitignoreTarget, string> = {
  '.aspect/': '.aspect/',
  'AGENTS.md': 'AGENTS.md',
  'CLAUDE.md': 'CLAUDE.md',
  '.github/copilot-instructions.md': '.github/copilot-instructions.md',
  '.cursor/rules/aspectcode.mdc': '.cursor/rules/aspectcode.mdc'
};

// Legacy entries (kept for backwards compatibility with existing blocks)
const ASPECT_DIR_ENTRY = '.aspect/';
const AGENTS_MD_ENTRY = 'AGENTS.md';

export type GitignoreMode = 'auto' | 'off';

/**
 * Gets the current gitignore mode from settings
 */
export function getGitignoreMode(): GitignoreMode {
  const config = vscode.workspace.getConfiguration('aspectcode');
  return config.get<GitignoreMode>('gitignore.mode', 'auto');
}

/**
 * Checks if a .git directory exists in the workspace (i.e., is it a git repo)
 */
async function isGitRepository(workspaceRoot: vscode.Uri): Promise<boolean> {
  try {
    const gitDir = vscode.Uri.joinPath(workspaceRoot, '.git');
    const stat = await vscode.workspace.fs.stat(gitDir);
    return stat.type === vscode.FileType.Directory;
  } catch {
    return false;
  }
}

function detectEol(text: string): string {
  return text.includes('\r\n') ? '\r\n' : '\n';
}

type IgnoreTarget = { kind: 'file' | 'dir'; name: string };

function normalizeRule(rule: string): string {
  return rule.trim().replace(/^\//, '');
}

function matchesRule(ruleRaw: string, target: IgnoreTarget): boolean {
  const rule = normalizeRule(ruleRaw);
  const ruleLower = rule.toLowerCase();
  const nameLower = target.name.toLowerCase();

  // Common "ignore everything" patterns
  if (ruleLower === '*' || ruleLower === '**' || ruleLower === '**/*') return true;

  // Dotfile blanket ignore
  if (ruleLower === '.*' && nameLower.startsWith('.')) return true;

  if (target.kind === 'file') {
    // Exact file
    if (ruleLower === nameLower) return true;

    // Common path globs
    if (ruleLower === `**/${nameLower}`) return true;
    if (ruleLower === `*/${nameLower}`) return true;

    // Extension globs (covers '*.md', '**/*.md')
    if (ruleLower === '*.md' && nameLower.endsWith('.md')) return true;
    if (ruleLower === '**/*.md' && nameLower.endsWith('.md')) return true;

    // Suffix glob (covers '*agents.md')
    if (ruleLower.startsWith('*') && nameLower.endsWith(ruleLower.slice(1))) return true;

    return false;
  }

  // Directory target
  const dirName = nameLower.replace(/\/$/, '');

  if (ruleLower === dirName) return true;
  if (ruleLower === `${dirName}/`) return true;
  if (ruleLower === `${dirName}/*`) return true;
  if (ruleLower === `${dirName}/**`) return true;

  if (ruleLower === `**/${dirName}`) return true;
  if (ruleLower === `**/${dirName}/`) return true;
  if (ruleLower === `**/${dirName}/**`) return true;

  return false;
}

/**
 * Evaluates whether a target is ignored by the given .gitignore lines.
 * Minimal evaluator covering our specific targets and common wildcards.
 * Supports negation via '!pattern' (last match wins).
 */
function isIgnoredByRules(lines: string[], target: IgnoreTarget): boolean {
  let ignored: boolean | undefined;

  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('#')) continue;

    const negated = trimmed.startsWith('!');
    const rule = negated ? trimmed.slice(1).trim() : trimmed;
    if (!rule) continue;

    if (matchesRule(rule, target)) {
      ignored = !negated;
    }
  }

  return ignored ?? false;
}

function hasExplicitLine(lines: string[], exactCandidates: string[]): boolean {
  const candidates = new Set(exactCandidates.map((c) => c.toLowerCase()));
  for (const rawLine of lines) {
    const trimmed = rawLine.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('#')) continue;
    if (trimmed.startsWith('!')) continue;
    if (candidates.has(trimmed.toLowerCase())) return true;
  }
  return false;
}

function findAspectCodeBlockStart(lines: string[]): number {
  for (let i = 0; i < lines.length; i++) {
    if (lines[i].trim() === ASPECT_CODE_BLOCK_START) return i;
  }
  return -1;
}

function isManagedEntryLine(line: string): boolean {
  const trimmed = line.trim();
  if (!trimmed) return true; // allow blank lines within the block
  const lower = trimmed.toLowerCase();
  // All entries we manage (includes new entries for opt-in system)
  return (
    lower === '.aspect/' ||
    lower === '.aspect' ||
    lower === '/.aspect/' ||
    lower === '/.aspect' ||
    lower === 'agents.md' ||
    lower === '/agents.md' ||
    lower === 'claude.md' ||
    lower === '/claude.md' ||
    lower === '.github/copilot-instructions.md' ||
    lower === '/.github/copilot-instructions.md' ||
    lower === '.cursor/rules/aspectcode.mdc' ||
    lower === '/.cursor/rules/aspectcode.mdc'
  );
}

function findAspectCodeBlockEnd(lines: string[], startIndex: number): number {
  let end = startIndex;
  for (let i = startIndex + 1; i < lines.length; i++) {
    if (!isManagedEntryLine(lines[i])) {
      break;
    }
    end = i;
  }
  return end;
}

/**
 * Creates the Aspect Code block content
 */
function createAspectCodeBlock(): string {
  return `${ASPECT_CODE_BLOCK_START}
${ASPECT_DIR_ENTRY}
${AGENTS_MD_ENTRY}
`;
}

/**
 * Result of ensureGitignore operation
 */
export interface EnsureGitignoreResult {
  /** Whether any changes were made */
  modified: boolean;
  /** Whether this is a first-time modification (should show notification) */
  isFirstModification: boolean;
  /** What entries were added */
  entriesAdded: string[];
  /** Any warning or info message */
  message?: string;
}

/**
 * Ensures .aspect/ and AGENTS.md are added to .gitignore if mode is 'auto'.
 * 
 * Safety guarantees:
 * - Never removes or modifies existing ignore rules
 * - Adds entries under a clearly labeled comment block
 * - Detects if entries are already ignored (explicitly or via wildcard)
 * - Idempotent - safe to call multiple times
 */
export async function ensureGitignore(
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
): Promise<EnsureGitignoreResult> {
  const result: EnsureGitignoreResult = {
    modified: false,
    isFirstModification: false,
    entriesAdded: []
  };
  
  // Check if gitignore management is disabled
  const mode = getGitignoreMode();
  if (mode === 'off') {
    outputChannel.appendLine('[Gitignore] Mode is "off", skipping .gitignore management');
    return result;
  }
  
  // Check if this is a git repository
  const isGitRepo = await isGitRepository(workspaceRoot);
  if (!isGitRepo) {
    outputChannel.appendLine('[Gitignore] Not a git repository, skipping .gitignore management');
    result.message = 'Not a git repository';
    return result;
  }
  
  const gitignorePath = vscode.Uri.joinPath(workspaceRoot, '.gitignore');
  
  try {
    // Try to read existing .gitignore
    const content = await vscode.workspace.fs.readFile(gitignorePath);
    const text = Buffer.from(content).toString('utf8');
    const eol = detectEol(text);
    const lines = text.split(/\r?\n/);

    const aspectTarget: IgnoreTarget = { kind: 'dir', name: '.aspect' };
    const agentsTarget: IgnoreTarget = { kind: 'file', name: 'AGENTS.md' };

    // Check if entries are already ignored (explicitly or via wildcards). Also avoid duplicates.
    const aspectIgnored = isIgnoredByRules(lines, aspectTarget);
    const agentsIgnored = isIgnoredByRules(lines, agentsTarget);

    const aspectExplicit = hasExplicitLine(lines, ['.aspect/', '.aspect', '/.aspect/', '/.aspect']);
    const agentsExplicit = hasExplicitLine(lines, ['AGENTS.md', '/AGENTS.md']);
    
    if (aspectIgnored && agentsIgnored) {
      outputChannel.appendLine('[Gitignore] Both .aspect/ and AGENTS.md are already ignored');
      return result;
    }
    
    // Check if we already have an Aspect Code block
    const blockStart = findAspectCodeBlockStart(lines);
    
    let newContent: string;
    
    if (blockStart !== -1) {
      const blockEnd = findAspectCodeBlockEnd(lines, blockStart);
      const blockLines = lines.slice(blockStart, blockEnd + 1);

      const blockHasAspect = blockLines.some((l) => {
        const t = l.trim().toLowerCase();
        return t === '.aspect/' || t === '.aspect' || t === '/.aspect/' || t === '/.aspect';
      });
      const blockHasAgents = blockLines.some((l) => {
        const t = l.trim().toLowerCase();
        return t === 'agents.md' || t === '/agents.md';
      });

      const entriesToAdd: string[] = [];

      if (!aspectIgnored && !aspectExplicit && !blockHasAspect) {
        entriesToAdd.push(ASPECT_DIR_ENTRY);
        result.entriesAdded.push(ASPECT_DIR_ENTRY);
      }
      if (!agentsIgnored && !agentsExplicit && !blockHasAgents) {
        entriesToAdd.push(AGENTS_MD_ENTRY);
        result.entriesAdded.push(AGENTS_MD_ENTRY);
      }

      if (entriesToAdd.length === 0) {
        outputChannel.appendLine('[Gitignore] Aspect Code block already covers required entries');
        return result;
      }

      // Insert new entries directly under the header line (minimal diff)
      const insertIndex = blockStart + 1;
      const newLines = [...lines];
      newLines.splice(insertIndex, 0, ...entriesToAdd);
      newContent = newLines.join(eol);
    } else {
      // No existing block - append a new one at the end
      const entriesToAdd: string[] = [];
      if (!aspectIgnored && !aspectExplicit) {
        entriesToAdd.push(ASPECT_DIR_ENTRY);
        result.entriesAdded.push(ASPECT_DIR_ENTRY);
      }
      if (!agentsIgnored && !agentsExplicit) {
        entriesToAdd.push(AGENTS_MD_ENTRY);
        result.entriesAdded.push(AGENTS_MD_ENTRY);
      }
      
      if (entriesToAdd.length === 0) {
        outputChannel.appendLine('[Gitignore] All entries already ignored by existing rules');
        return result;
      }
      
      // Build the block with only the entries we need to add
      const blockContent = `${ASPECT_CODE_BLOCK_START}${eol}${entriesToAdd.join(eol)}${eol}`;

      // Append to end, ensuring proper newline separation without rewriting existing content
      const endsWithNewline = text.endsWith('\n');
      newContent = endsWithNewline
        ? text + eol + blockContent
        : text + eol + eol + blockContent;
    }
    
    // Write the updated content
    await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
    result.modified = true;
    
    // Check if this is the first time we've modified .gitignore
    const notificationShown = context?.globalState.get<boolean>(GITIGNORE_NOTIFICATION_SHOWN_KEY, false);
    if (!notificationShown && context) result.isFirstModification = true;
    
    outputChannel.appendLine(`[Gitignore] Added ${result.entriesAdded.join(', ')} to .gitignore`);
    
  } catch (error) {
    // .gitignore doesn't exist - create it with the Aspect Code block
    if ((error as vscode.FileSystemError).code === 'FileNotFound') {
      const eol = '\n';
      const newContent = `${ASPECT_CODE_BLOCK_START}${eol}${ASPECT_DIR_ENTRY}${eol}${AGENTS_MD_ENTRY}${eol}`;
      
      try {
        await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
        result.modified = true;
        result.entriesAdded = [ASPECT_DIR_ENTRY, AGENTS_MD_ENTRY];
        
        // Check if this is the first time we've modified .gitignore
        const notificationShown = context?.globalState.get<boolean>(GITIGNORE_NOTIFICATION_SHOWN_KEY, false);
        if (!notificationShown && context) result.isFirstModification = true;
        
        outputChannel.appendLine('[Gitignore] Created .gitignore with Aspect Code entries');
      } catch (writeError) {
        outputChannel.appendLine(`[Gitignore] Failed to create .gitignore: ${writeError}`);
        result.message = 'Failed to create .gitignore (filesystem may be read-only)';
      }
    } else {
      outputChannel.appendLine(`[Gitignore] Error reading .gitignore: ${error}`);
      result.message = 'Failed to read .gitignore';
    }
  }
  
  return result;
}

/**
 * Result of ensureGitignoreForTarget operation
 */
export interface EnsureGitignoreForTargetResult {
  /** Whether any changes were made */
  modified: boolean;
  /** What entry was added (if any) */
  entryAdded?: string;
  /** Whether user declined to add this entry */
  declined: boolean;
  /** Any warning or info message */
  message?: string;
}

/**
 * Ensures a specific target is added to .gitignore, with opt-in prompt.
 * 
 * This function checks the user's preference stored in .aspect/.settings.json.
 * If no preference exists, it prompts the user.
 * If user agrees, it adds the entry to .gitignore.
 * 
 * @param workspaceRoot - The workspace root URI
 * @param target - The target to potentially add to .gitignore
 * @param outputChannel - Output channel for logging
 * @returns Result indicating what happened
 */
export async function ensureGitignoreForTarget(
  workspaceRoot: vscode.Uri,
  target: GitignoreTarget,
  outputChannel: vscode.OutputChannel
): Promise<EnsureGitignoreForTargetResult> {
  const result: EnsureGitignoreForTargetResult = {
    modified: false,
    declined: false
  };
  
  // Check if this is a git repository
  const isGitRepo = await isGitRepository(workspaceRoot);
  if (!isGitRepo) {
    outputChannel.appendLine(`[Gitignore] Not a git repository, skipping .gitignore management for ${target}`);
    result.message = 'Not a git repository';
    return result;
  }
  
  // Get the gitignore pattern for this target
  const pattern = TARGET_TO_PATTERN[target];
  
  // Check if user already has a preference for this target
  const hasPref = await hasGitignorePreference(workspaceRoot, target);
  
  let shouldAdd: boolean;
  
  if (hasPref) {
    // User already made a choice - respect it
    const pref = await getGitignorePreference(workspaceRoot, target);
    shouldAdd = pref ?? false; // Default to false if somehow undefined
    outputChannel.appendLine(`[Gitignore] Using saved preference for ${target}: ${shouldAdd ? 'add' : 'skip'}`);
  } else {
    // Prompt user for this target
    const preference = await promptGitignorePreference(workspaceRoot, target);
    
    if (preference === undefined) {
      // User dismissed without choosing - skip for now but don't save preference
      outputChannel.appendLine(`[Gitignore] User dismissed prompt for ${target}, skipping`);
      result.message = 'User dismissed prompt';
      return result;
    }
    
    shouldAdd = preference;
    outputChannel.appendLine(`[Gitignore] User chose ${shouldAdd ? 'add' : 'skip'} for ${target}`);
  }
  
  if (!shouldAdd) {
    result.declined = true;
    return result;
  }
  
  // User wants to add this entry - proceed with gitignore modification
  const gitignorePath = vscode.Uri.joinPath(workspaceRoot, '.gitignore');
  
  try {
    // Try to read existing .gitignore
    const content = await vscode.workspace.fs.readFile(gitignorePath);
    const text = Buffer.from(content).toString('utf8');
    const eol = detectEol(text);
    const lines = text.split(/\r?\n/);
    
    // Check if already ignored
    const targetInfo = getTargetInfo(target);
    const isIgnored = isIgnoredByRules(lines, targetInfo);
    
    if (isIgnored) {
      outputChannel.appendLine(`[Gitignore] ${pattern} is already ignored`);
      return result;
    }
    
    // Check for explicit line
    const hasExplicit = hasExplicitLine(lines, getExplicitCandidates(pattern));
    if (hasExplicit) {
      outputChannel.appendLine(`[Gitignore] ${pattern} already has explicit line`);
      return result;
    }
    
    // Check if we already have an Aspect Code block
    const blockStart = findAspectCodeBlockStart(lines);
    
    let newContent: string;
    
    if (blockStart !== -1) {
      // Block exists - add entry to it
      const blockEnd = findAspectCodeBlockEnd(lines, blockStart);
      const blockLines = lines.slice(blockStart, blockEnd + 1);
      
      // Check if entry already in block
      const alreadyInBlock = blockLines.some(l => 
        l.trim().toLowerCase() === pattern.toLowerCase()
      );
      
      if (alreadyInBlock) {
        outputChannel.appendLine(`[Gitignore] ${pattern} already in Aspect Code block`);
        return result;
      }
      
      // Insert entry after header
      const insertIndex = blockStart + 1;
      const newLines = [...lines];
      newLines.splice(insertIndex, 0, pattern);
      newContent = newLines.join(eol);
    } else {
      // No block - create one at the end
      const blockContent = `${ASPECT_CODE_BLOCK_START}${eol}${pattern}${eol}`;
      
      const endsWithNewline = text.endsWith('\n');
      newContent = endsWithNewline
        ? text + eol + blockContent
        : text + eol + eol + blockContent;
    }
    
    // Write the updated content
    await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
    result.modified = true;
    result.entryAdded = pattern;
    
    outputChannel.appendLine(`[Gitignore] Added ${pattern} to .gitignore`);
    
  } catch (error) {
    // .gitignore doesn't exist - create it
    if ((error as vscode.FileSystemError).code === 'FileNotFound') {
      const eol = '\n';
      const newContent = `${ASPECT_CODE_BLOCK_START}${eol}${pattern}${eol}`;
      
      try {
        await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
        result.modified = true;
        result.entryAdded = pattern;
        
        outputChannel.appendLine(`[Gitignore] Created .gitignore with ${pattern}`);
      } catch (writeError) {
        outputChannel.appendLine(`[Gitignore] Failed to create .gitignore: ${writeError}`);
        result.message = 'Failed to create .gitignore (filesystem may be read-only)';
      }
    } else {
      outputChannel.appendLine(`[Gitignore] Error reading .gitignore: ${error}`);
      result.message = 'Failed to read .gitignore';
    }
  }
  
  return result;
}

/**
 * Gets the IgnoreTarget info for a GitignoreTarget
 */
function getTargetInfo(target: GitignoreTarget): IgnoreTarget {
  switch (target) {
    case '.aspect/':
      return { kind: 'dir', name: '.aspect' };
    case 'AGENTS.md':
      return { kind: 'file', name: 'AGENTS.md' };
    case 'CLAUDE.md':
      return { kind: 'file', name: 'CLAUDE.md' };
    case '.github/copilot-instructions.md':
      return { kind: 'file', name: '.github/copilot-instructions.md' };
    case '.cursor/rules/aspectcode.mdc':
      return { kind: 'file', name: '.cursor/rules/aspectcode.mdc' };
    default:
      // Exhaustive check - should never reach here
      const _exhaustive: never = target;
      throw new Error(`Unknown target: ${_exhaustive}`);
  }
}

/**
 * Gets explicit line candidates for checking duplicates
 */
function getExplicitCandidates(pattern: string): string[] {
  return [pattern, `/${pattern}`];
}

/**
 * Shows the one-time notification explaining the gitignore modification
 */
export async function showGitignoreNotification(context: vscode.ExtensionContext): Promise<void> {
  const result = await vscode.window.showInformationMessage(
    'Aspect Code added .aspect/ and AGENTS.md to .gitignore so AI context stays local. You can change this later in settings.',
    'Open Settings',
    'Dismiss'
  );
  
  // Mark notification as shown
  await context.globalState.update(GITIGNORE_NOTIFICATION_SHOWN_KEY, true);
  
  if (result === 'Open Settings') {
    await vscode.commands.executeCommand('workbench.action.openSettings', 'aspectcode.gitignore.mode');
  }
}

/**
 * Removes the Aspect Code block from .gitignore.
 * Only removes entries that are within the Aspect Code–owned block.
 */
export async function removeAspectCodeBlock(
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<{ success: boolean; message: string }> {
  const gitignorePath = vscode.Uri.joinPath(workspaceRoot, '.gitignore');
  
  try {
    const content = await vscode.workspace.fs.readFile(gitignorePath);
    const text = Buffer.from(content).toString('utf8');
    const eol = detectEol(text);
    const lines = text.split(/\r?\n/);

    const startIndex = findAspectCodeBlockStart(lines);
    if (startIndex === -1) {
      return {
        success: false,
        message: 'No Aspect Code block found in .gitignore'
      };
    }

    const endIndex = findAspectCodeBlockEnd(lines, startIndex);

    // Remove header + subsequent managed lines (and only those)
    const newLines = [...lines.slice(0, startIndex), ...lines.slice(endIndex + 1)];
    
    // Clean up any trailing empty lines that might have been left
    while (newLines.length > 0 && newLines[newLines.length - 1].trim() === '') {
      newLines.pop();
    }
    
    // Ensure file ends with newline
    const newContent = newLines.join(eol) + eol;
    
    // If the file would be empty or only whitespace, delete it instead
    if (newContent.trim() === '') {
      await vscode.workspace.fs.delete(gitignorePath);
      outputChannel.appendLine('[Gitignore] Deleted empty .gitignore after removing Aspect Code block');
      return {
        success: true,
        message: 'Removed Aspect Code block and deleted empty .gitignore'
      };
    }
    
    await vscode.workspace.fs.writeFile(gitignorePath, Buffer.from(newContent, 'utf8'));
    outputChannel.appendLine('[Gitignore] Removed Aspect Code block from .gitignore');
    
    return {
      success: true,
      message: 'Removed Aspect Code block from .gitignore'
    };
    
  } catch (error) {
    if ((error as vscode.FileSystemError).code === 'FileNotFound') {
      return {
        success: false,
        message: 'No .gitignore file exists'
      };
    }
    
    outputChannel.appendLine(`[Gitignore] Error removing block: ${error}`);
    return {
      success: false,
      message: `Failed to modify .gitignore: ${error}`
    };
  }
}

/**
 * Command handler for "Aspect Code: Stop ignoring generated files"
 */
export async function stopIgnoringGeneratedFilesCommand(
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
  
  if (!workspaceRoot) {
    vscode.window.showErrorMessage('No workspace folder open');
    return;
  }
  
  const result = await removeAspectCodeBlock(workspaceRoot, outputChannel);
  
  if (result.success) {
    vscode.window.showInformationMessage(
      'Removed Aspect Code entries from .gitignore. Generated files will now be tracked by git.'
    );
  } else {
    vscode.window.showWarningMessage(result.message);
  }
}
