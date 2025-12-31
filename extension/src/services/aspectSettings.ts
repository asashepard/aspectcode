/**
 * Aspect Settings Service
 * 
 * Manages user preferences stored in .aspect/.settings.json.
 * This keeps Aspect Code settings local to the project (not in .vscode/settings.json)
 * and allows per-file gitignore opt-in decisions.
 */

import * as vscode from 'vscode';

export type InstructionsMode = 'safe' | 'permissive';
export type AutoRegenerateKbMode = 'off' | 'onSave' | 'idle';

export interface AssistantsSettings {
  copilot?: boolean;
  cursor?: boolean;
  claude?: boolean;
  other?: boolean;
  alignments?: boolean;
  autoGenerate?: boolean;
}

// File paths that can be individually configured for gitignore
export type GitignoreTarget =
  | '.aspect/'
  | 'AGENTS.md'
  | 'CLAUDE.md'
  | '.github/copilot-instructions.md'
  | '.cursor/rules/aspectcode.mdc';

export const ALL_GITIGNORE_TARGETS: GitignoreTarget[] = [
  '.aspect/',
  'AGENTS.md',
  'CLAUDE.md',
  '.github/copilot-instructions.md',
  '.cursor/rules/aspectcode.mdc'
];

/**
 * Schema for .aspect/.settings.json
 */
export interface AspectSettings {
  /**
   * Per-target gitignore preferences.
   * true = add to .gitignore (keep local)
   * false = do not add to .gitignore (allow commit)
   * undefined = not yet asked
   */
  gitignore?: {
    [target in GitignoreTarget]?: boolean;
  };
  
  /**
   * Assistant enablement (mirrors aspectcode.assistants.* but stored locally)
   */
  assistants?: AssistantsSettings;

  /**
   * Auto-regenerate KB files.
   * Mirrors aspectcode.autoRegenerateKb.
   */
  autoRegenerateKb?: AutoRegenerateKbMode;
  
  /**
   * Instructions mode: 'safe' or 'permissive'
   */
  instructionsMode?: InstructionsMode;
}

const SETTINGS_FILENAME = '.settings.json';

const SETTINGS_CACHE_TTL_MS = 250;
const SETTINGS_CACHE = new Map<string, { loadedAtMs: number; settings: AspectSettings }>();

function cacheKey(workspaceRoot: vscode.Uri): string {
  return workspaceRoot.toString();
}

function normalizeInstructionsMode(value: unknown): InstructionsMode | undefined {
  return value === 'permissive' ? 'permissive' : value === 'safe' ? 'safe' : undefined;
}

function normalizeAutoRegenerateKbMode(value: unknown): AutoRegenerateKbMode | undefined {
  return value === 'off' || value === 'onSave' || value === 'idle' ? value : undefined;
}

/**
 * Get the path to the .aspect/.settings.json file for a workspace
 */
function getSettingsPath(workspaceRoot: vscode.Uri): vscode.Uri {
  return vscode.Uri.joinPath(workspaceRoot, '.aspect', SETTINGS_FILENAME);
}

/**
 * Read settings from .aspect/.settings.json
 * Returns empty object if file doesn't exist or is invalid
 */
export async function readAspectSettings(workspaceRoot: vscode.Uri): Promise<AspectSettings> {
  const settingsPath = getSettingsPath(workspaceRoot);

  const cached = SETTINGS_CACHE.get(cacheKey(workspaceRoot));
  if (cached && Date.now() - cached.loadedAtMs < SETTINGS_CACHE_TTL_MS) {
    return cached.settings;
  }
  
  try {
    const content = await vscode.workspace.fs.readFile(settingsPath);
    const text = Buffer.from(content).toString('utf8');
    const parsed = JSON.parse(text) as AspectSettings;
    SETTINGS_CACHE.set(cacheKey(workspaceRoot), { loadedAtMs: Date.now(), settings: parsed });
    return parsed;
  } catch {
    // File doesn't exist or is invalid - return empty settings
    const empty: AspectSettings = {};
    SETTINGS_CACHE.set(cacheKey(workspaceRoot), { loadedAtMs: Date.now(), settings: empty });
    return empty;
  }
}

/**
 * Write settings to .aspect/.settings.json
 * Creates .aspect/ directory if it doesn't exist
 */
export async function writeAspectSettings(
  workspaceRoot: vscode.Uri,
  settings: AspectSettings
): Promise<void> {
  const aspectDir = vscode.Uri.joinPath(workspaceRoot, '.aspect');
  const settingsPath = getSettingsPath(workspaceRoot);
  
  // Ensure .aspect/ directory exists
  try {
    await vscode.workspace.fs.createDirectory(aspectDir);
  } catch {
    // Directory may already exist
  }
  
  const content = JSON.stringify(settings, null, 2) + '\n';
  await vscode.workspace.fs.writeFile(settingsPath, Buffer.from(content, 'utf8'));

  SETTINGS_CACHE.set(cacheKey(workspaceRoot), { loadedAtMs: Date.now(), settings });
}

/**
 * Update a specific setting in .aspect/.settings.json
 * Merges with existing settings
 */
export async function updateAspectSettings(
  workspaceRoot: vscode.Uri,
  update: Partial<AspectSettings>
): Promise<AspectSettings> {
  const existing = await readAspectSettings(workspaceRoot);
  
  // Deep merge for nested objects
  const merged: AspectSettings = {
    ...existing,
    ...update,
    gitignore: {
      ...existing.gitignore,
      ...update.gitignore
    },
    assistants: {
      ...existing.assistants,
      ...update.assistants
    },
    autoRegenerateKb: update.autoRegenerateKb ?? existing.autoRegenerateKb,
    instructionsMode: update.instructionsMode ?? existing.instructionsMode
  };
  
  await writeAspectSettings(workspaceRoot, merged);
  return merged;
}

async function readVSCodeWorkspaceSettingsJson(workspaceRoot: vscode.Uri): Promise<Record<string, unknown> | null> {
  const settingsPath = vscode.Uri.joinPath(workspaceRoot, '.vscode', 'settings.json');
  try {
    const bytes = await vscode.workspace.fs.readFile(settingsPath);
    const text = Buffer.from(bytes).toString('utf8');
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === 'object') {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

/**
 * One-time-ish migration: copy selected aspectcode.* settings from .vscode/settings.json
 * into .aspect/.settings.json (only when the .aspect setting is not already set).
 */
export async function migrateAspectSettingsFromVSCode(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel
): Promise<boolean> {
  const vsSettings = await readVSCodeWorkspaceSettingsJson(workspaceRoot);
  if (!vsSettings) return false;

  const current = await readAspectSettings(workspaceRoot);

  const update: Partial<AspectSettings> = {};
  let changed = false;

  // instructions mode
  if (current.instructionsMode === undefined) {
    const migrated = normalizeInstructionsMode(vsSettings['aspectcode.instructions.mode']);
    if (migrated) {
      update.instructionsMode = migrated;
      changed = true;
    }
  }

  // autoRegenerateKb mode
  if (current.autoRegenerateKb === undefined) {
    const migrated = normalizeAutoRegenerateKbMode(vsSettings['aspectcode.autoRegenerateKb']);
    if (migrated) {
      update.autoRegenerateKb = migrated;
      changed = true;
    }
  }

  // assistants flags
  const assistantKeys: Array<keyof AssistantsSettings> = [
    'copilot',
    'cursor',
    'claude',
    'other',
    'alignments',
    'autoGenerate'
  ];

  const currentAssistants = current.assistants ?? {};
  const assistantUpdate: AssistantsSettings = {};
  for (const key of assistantKeys) {
    if (currentAssistants[key] !== undefined) continue;
    const raw = vsSettings[`aspectcode.assistants.${String(key)}`];
    if (typeof raw === 'boolean') {
      assistantUpdate[key] = raw;
      changed = true;
    }
  }
  if (Object.keys(assistantUpdate).length > 0) {
    update.assistants = assistantUpdate;
  }

  if (!changed) return false;

  await updateAspectSettings(workspaceRoot, update);
  outputChannel?.appendLine('[Settings] Migrated Aspect Code settings from .vscode/settings.json to .aspect/.settings.json');
  return true;
}

export async function getInstructionsModeSetting(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel
): Promise<InstructionsMode> {
  await migrateAspectSettingsFromVSCode(workspaceRoot, outputChannel);
  const settings = await readAspectSettings(workspaceRoot);
  return normalizeInstructionsMode(settings.instructionsMode) ?? 'safe';
}

export async function setInstructionsModeSetting(
  workspaceRoot: vscode.Uri,
  mode: InstructionsMode
): Promise<void> {
  await updateAspectSettings(workspaceRoot, { instructionsMode: mode });
}

export async function getAutoRegenerateKbSetting(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel
): Promise<AutoRegenerateKbMode> {
  await migrateAspectSettingsFromVSCode(workspaceRoot, outputChannel);
  const settings = await readAspectSettings(workspaceRoot);
  return normalizeAutoRegenerateKbMode(settings.autoRegenerateKb) ?? 'onSave';
}

export async function setAutoRegenerateKbSetting(
  workspaceRoot: vscode.Uri,
  mode: AutoRegenerateKbMode
): Promise<void> {
  await updateAspectSettings(workspaceRoot, { autoRegenerateKb: mode });
}

export async function getAssistantsSettings(
  workspaceRoot: vscode.Uri,
  outputChannel?: vscode.OutputChannel
): Promise<Required<AssistantsSettings>> {
  await migrateAspectSettingsFromVSCode(workspaceRoot, outputChannel);
  const settings = await readAspectSettings(workspaceRoot);
  const a = settings.assistants ?? {};
  return {
    copilot: a.copilot ?? false,
    cursor: a.cursor ?? false,
    claude: a.claude ?? false,
    other: a.other ?? false,
    alignments: a.alignments ?? false,
    autoGenerate: a.autoGenerate ?? false
  };
}

/**
 * Get the gitignore preference for a specific target
 * Returns undefined if not yet set (user hasn't been asked)
 */
export async function getGitignorePreference(
  workspaceRoot: vscode.Uri,
  target: GitignoreTarget
): Promise<boolean | undefined> {
  const settings = await readAspectSettings(workspaceRoot);
  return settings.gitignore?.[target];
}

/**
 * Set the gitignore preference for a specific target
 */
export async function setGitignorePreference(
  workspaceRoot: vscode.Uri,
  target: GitignoreTarget,
  addToGitignore: boolean
): Promise<void> {
  await updateAspectSettings(workspaceRoot, {
    gitignore: {
      [target]: addToGitignore
    }
  });
}

/**
 * User-friendly descriptions for each gitignore target
 */
export function getTargetDescription(target: GitignoreTarget): string {
  switch (target) {
    case '.aspect/':
      return 'the Aspect Code knowledge base (.aspect/)';
    case 'AGENTS.md':
      return 'AGENTS.md (general AI instructions)';
    case 'CLAUDE.md':
      return 'CLAUDE.md (Claude Code instructions)';
    case '.github/copilot-instructions.md':
      return 'GitHub Copilot instructions (.github/copilot-instructions.md)';
    case '.cursor/rules/aspectcode.mdc':
      return 'Cursor rules (.cursor/rules/aspectcode.mdc)';
  }
}

/**
 * Prompt the user about adding a target to .gitignore
 * Returns their choice (true = add, false = don't add)
 * Returns undefined if user dismissed without choosing (don't persist)
 * Also persists the choice to .aspect/.settings.json
 */
export async function promptGitignorePreference(
  workspaceRoot: vscode.Uri,
  target: GitignoreTarget,
  outputChannel?: vscode.OutputChannel
): Promise<boolean | undefined> {
  const description = getTargetDescription(target);
  
  const result = await vscode.window.showInformationMessage(
    `Keep ${description} local? Adding to .gitignore prevents it from being committed to git.`,
    { modal: false },
    'Keep Local (add to .gitignore)',
    'Allow Commit (don\'t add)'
  );
  
  // If user dismissed without choosing, don't persist and return undefined
  if (result === undefined) {
    outputChannel?.appendLine(
      `[Settings] User dismissed gitignore prompt for ${target}`
    );
    return undefined;
  }
  
  const addToGitignore = result === 'Keep Local (add to .gitignore)';
  
  // Persist the decision
  await setGitignorePreference(workspaceRoot, target, addToGitignore);
  
  outputChannel?.appendLine(
    `[Settings] User chose to ${addToGitignore ? 'add' : 'not add'} ${target} to .gitignore`
  );
  
  return addToGitignore;
}

/**
 * Check if a gitignore preference has been set (user has been asked)
 */
export async function hasGitignorePreference(
  workspaceRoot: vscode.Uri,
  target: GitignoreTarget
): Promise<boolean> {
  const pref = await getGitignorePreference(workspaceRoot, target);
  return pref !== undefined;
}
