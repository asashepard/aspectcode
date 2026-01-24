/**
 * Command Handlers
 * 
 * This module registers and handles all extension commands.
 */

import * as vscode from 'vscode';
import { AspectCodeState } from './state';
import { detectAssistants, AssistantId } from './assistants/detection';
import { generateInstructionFiles, regenerateInstructionFilesOnly, AssistantsOverride } from './assistants/instructions';
import { generateKnowledgeBase } from './assistants/kb';
import { stopIgnoringGeneratedFilesCommand } from './services/gitignoreService';
import { InstructionsMode, getAssistantsSettings, getInstructionsModeSetting, setInstructionsModeSetting, updateAspectSettings, getExtensionEnabledSetting, setExtensionEnabledSetting, aspectDirExists } from './services/aspectSettings';
import { cancelAndResetAllInFlightWork } from './services/enablementCancellation';

/**
 * Activate the new engine-based commands.
 * Call this from the main extension activate function.
 */
export function activateCommands(
  context: vscode.ExtensionContext,
  state: AspectCodeState,
  outputChannel?: vscode.OutputChannel
): void {
  // Reuse the main extension output channel so users only need to watch one.
  const channel = outputChannel ?? vscode.window.createOutputChannel('Aspect Code');

  const getWorkspaceRoot = (): vscode.Uri | undefined => vscode.workspace.workspaceFolders?.[0]?.uri;

  const isExtensionEnabled = async (): Promise<boolean> => {
    const root = getWorkspaceRoot();
    if (!root) return true;
    try {
      return await getExtensionEnabledSetting(root);
    } catch {
      return true;
    }
  };

  const requireExtensionEnabled = async (): Promise<boolean> => {
    if (await isExtensionEnabled()) return true;
    void vscode.window
      .showInformationMessage('Aspect Code is disabled.', 'Enable')
      .then((sel) => {
        if (sel === 'Enable') void vscode.commands.executeCommand('aspectcode.toggleExtensionEnabled');
      });
    return false;
  };

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.toggleExtensionEnabled', async () => {
      const root = getWorkspaceRoot();
      if (!root) {
        vscode.window.showErrorMessage('No workspace folder open');
        return;
      }

      const enabled = await getExtensionEnabledSetting(root);
      const nextEnabled = !enabled;

      // Only persist to .aspect/.settings.json if .aspect/ already exists
      // Don't create .aspect/ just for the enable/disable toggle
      await setExtensionEnabledSetting(root, nextEnabled, { createIfMissing: false });

      if (!nextEnabled) {
        // Stop any in-flight work immediately.
        cancelAndResetAllInFlightWork();
        // Clear any stuck busy indicators.
        state.update({ busy: false, error: undefined });
      }

      vscode.window.showInformationMessage(
        nextEnabled ? 'Aspect Code enabled' : 'Aspect Code disabled'
      );
    }),
    vscode.commands.registerCommand('aspectcode.configureAssistants', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleConfigureAssistants(context, state, channel);
    }),
    vscode.commands.registerCommand('aspectcode.generateInstructionFiles', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleGenerateInstructionFiles(state, channel, context);
    }),
    vscode.commands.registerCommand('aspectcode.enableSafeMode', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleSetInstructionMode('safe', channel);
    }),
    vscode.commands.registerCommand('aspectcode.enablePermissiveMode', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleSetInstructionMode('permissive', channel);
    }),
    vscode.commands.registerCommand('aspectcode.enableCustomMode', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleSetInstructionMode('custom', channel);
    }),
    vscode.commands.registerCommand('aspectcode.enableOffMode', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleSetInstructionMode('off', channel);
    }),
    vscode.commands.registerCommand('aspectcode.editCustomInstructions', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleEditCustomInstructions(channel);
    }),
    vscode.commands.registerCommand('aspectcode.copyKbReceiptPrompt', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await handleCopyKbReceiptPrompt(channel);
    }),
    vscode.commands.registerCommand('aspectcode.stopIgnoringGeneratedFiles', async () => {
      if (!(await requireExtensionEnabled())) return;
      return await stopIgnoringGeneratedFilesCommand(channel);
    })
  );

  // Watch for .aspect/ folder and instruction file changes to update the '+' button visibility
  // Track if we've recently shown the notification to avoid spamming
  let lastNotificationTime = 0;
  const NOTIFICATION_DEBOUNCE_MS = 5000;
  const SUPPRESS_DELETED_NOTIFICATION_KEY = 'aspectcode.suppressDeletedNotification';

  const updateInstructionFilesStatus = async (showNotificationOnMissing: boolean = false) => {
    const panelProvider = (state as any)._panelProvider;
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!workspaceRoot) {return;}

    const detected = await detectAssistants(workspaceRoot);
    const hasAspectKB = detected.has('aspectKB');
    
    // Check for instruction files (exclude aspectKB from count)
    const instructionAssistants = new Set(detected);
    instructionAssistants.delete('aspectKB');
    const hasInstructionFiles = instructionAssistants.size > 0;
    
    // Show + button if either is missing
    const setupComplete = hasAspectKB && hasInstructionFiles;
    
    // Update panel if available
    if (panelProvider && typeof panelProvider.post === 'function') {
      panelProvider.post({ type: 'INSTRUCTION_FILES_STATUS', hasFiles: setupComplete });
    }

    // Show notification if setup is incomplete and we should notify
    if (showNotificationOnMissing && !setupComplete) {
      // Check if user has suppressed this notification for this workspace
      const isSuppressed = context.workspaceState.get<boolean>(SUPPRESS_DELETED_NOTIFICATION_KEY, false);
      if (isSuppressed) {
        channel.appendLine(`[Watcher] Deleted notification suppressed for this workspace`);
        return;
      }
      
      const now = Date.now();
      if (now - lastNotificationTime > NOTIFICATION_DEBOUNCE_MS) {
        lastNotificationTime = now;
        channel.appendLine(`[Watcher] Detected missing files: aspectKB=${hasAspectKB}, instructionFiles=${hasInstructionFiles}`);
        const message = !hasAspectKB
          ? 'Aspect Code: Knowledge base (.aspect/) was deleted.'
          : 'Aspect Code: AI instruction files were deleted.';
        const action = await vscode.window.showWarningMessage(
          message + ' Regenerate to restore AI assistant context.',
          'Regenerate',
          "Don't Show Again"
        );
        if (action === 'Regenerate') {
          vscode.commands.executeCommand('aspectcode.configureAssistants');
        } else if (action === "Don't Show Again") {
          await context.workspaceState.update(SUPPRESS_DELETED_NOTIFICATION_KEY, true);
          channel.appendLine(`[Watcher] User suppressed deleted notification for this workspace`);
        }
      }
    }
  };

  // Debounce the update to avoid rapid-fire during git operations
  let instructionUpdateTimeout: NodeJS.Timeout | undefined;
  const debouncedInstructionUpdate = (showNotification: boolean = false) => {
    if (instructionUpdateTimeout) {
      clearTimeout(instructionUpdateTimeout);
    }
    instructionUpdateTimeout = setTimeout(() => {
      updateInstructionFilesStatus(showNotification);
    }, 500);
  };

  // ============================================================
  // Consolidated File Watchers
  // ============================================================
  // Watch for .aspect/ folder and all contents (KB files, settings, instructions)
  const aspectWatcher = vscode.workspace.createFileSystemWatcher('**/.aspect{,/**}');
  aspectWatcher.onDidCreate((uri) => {
    channel.appendLine(`[Watcher] .aspect created: ${uri.fsPath}`);
    debouncedInstructionUpdate(false);
  });
  aspectWatcher.onDidChange(async (uri) => {
    // Handle custom instructions deletion check
    if (uri.fsPath.endsWith('instructions.md')) {
      try {
        await vscode.workspace.fs.stat(uri);
      } catch {
        // File was deleted
        const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
        if (!workspaceRoot) return;
        const mode = await getInstructionsModeSetting(workspaceRoot, channel);
        if (mode === 'custom') {
          await setInstructionsModeSetting(workspaceRoot, 'off');
          channel.appendLine('[Instructions] Custom instructions missing; auto-switched instructions.mode=off');
          const assistants = await getAssistantsSettings(workspaceRoot, channel);
          if (assistants.copilot || assistants.cursor || assistants.claude || assistants.other) {
            await regenerateInstructionFilesOnly(workspaceRoot, channel);
          }
        }
      }
    }
  });
  aspectWatcher.onDidDelete((uri) => {
    channel.appendLine(`[Watcher] .aspect deleted: ${uri.fsPath}`);
    // Handle custom instructions auto-switch to off
    if (uri.fsPath.endsWith('instructions.md')) {
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (workspaceRoot) {
        getInstructionsModeSetting(workspaceRoot, channel).then(async (mode) => {
          if (mode === 'custom') {
            await setInstructionsModeSetting(workspaceRoot, 'off');
            channel.appendLine('[Instructions] Custom instructions missing; auto-switched instructions.mode=off');
            const assistants = await getAssistantsSettings(workspaceRoot, channel);
            if (assistants.copilot || assistants.cursor || assistants.claude || assistants.other) {
              await regenerateInstructionFilesOnly(workspaceRoot, channel);
            }
          }
        }).catch((e) => channel.appendLine(`[Watcher] Failed to auto-switch: ${e}`));
      }
    }
    debouncedInstructionUpdate(true);
  });
  context.subscriptions.push(aspectWatcher);

  // Watch for all AI assistant instruction files (root and config folders)
  const instructionFilesWatcher = vscode.workspace.createFileSystemWatcher(
    '**/{AGENTS,CLAUDE}.md'
  );
  instructionFilesWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  instructionFilesWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  context.subscriptions.push(instructionFilesWatcher);

  // Watch for Copilot and Cursor config locations
  const assistantConfigWatcher = vscode.workspace.createFileSystemWatcher(
    '**/{.github/copilot-instructions.md,.cursor/**,.cursorrules}'
  );
  assistantConfigWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  assistantConfigWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  context.subscriptions.push(assistantConfigWatcher);

  // Startup check intentionally disabled: panel UI handles setup prompts.
}

/**
 * Handle aspectcode.configureAssistants command.
 * Detects assistants, shows QuickPick, updates settings, offers immediate generation.
 */
async function handleConfigureAssistants(
  context: vscode.ExtensionContext,
  state: AspectCodeState,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  try {
    const perfEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.devLogs', true);
    const tStart = Date.now();
    if (perfEnabled) {
      outputChannel.appendLine('[Perf][Assistants][configure] start');
    }

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    // Detect existing assistants
    const tDetect = Date.now();
    const detected = await detectAssistants(workspaceRoot);
    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Assistants][configure] detectAssistants tookMs=${Date.now() - tDetect}`);
    }
    outputChannel.appendLine(`[Assistants] Detected: ${Array.from(detected).join(', ') || 'none'}`);

    // Show QuickPick for selection
    interface AssistantPickItem extends vscode.QuickPickItem {
      id: AssistantId;
    }

    const items: AssistantPickItem[] = [
      {
        id: 'copilot',
        label: '$(github) GitHub Copilot',
        description: detected.has('copilot') ? '(detected)' : '',
        picked: detected.has('copilot')
      },
      {
        id: 'cursor',
        label: '$(edit) Cursor',
        description: detected.has('cursor') ? '(detected)' : '',
        picked: detected.has('cursor')
      },
      {
        id: 'claude',
        label: '$(comment) Claude Code',
        description: detected.has('claude') ? '(detected)' : '',
        picked: detected.has('claude')
      },
      {
        id: 'other',
        label: '$(file) Other (AGENTS.md)',
        description: detected.has('other') ? '(detected)' : '',
        picked: detected.has('other')
      }
    ];

    if (perfEnabled) {
      outputChannel.appendLine('[Perf][Assistants][configure] showing QuickPick');
    }
    const tPick = Date.now();
    const selected = await vscode.window.showQuickPick(items, {
      canPickMany: true,
      placeHolder: 'Select AI assistants to configure Aspect Code for'
    });

    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Assistants][configure] QuickPick resolved tookMs=${Date.now() - tPick} pickedCount=${selected?.length ?? 0}`);
    }

    if (!selected) {
      // User cancelled - re-check instruction files status so '+' button reappears if needed
      const panelProvider = (state as any)._panelProvider;
      const detected = await detectAssistants(workspaceRoot);
      const hasAspectKB = detected.has('aspectKB');
      const instructionAssistants = new Set(detected);
      instructionAssistants.delete('aspectKB');
      const hasInstructionFiles = instructionAssistants.size > 0;
      const setupComplete = hasAspectKB && hasInstructionFiles;
      if (panelProvider && typeof panelProvider.post === 'function') {
        panelProvider.post({ type: 'INSTRUCTION_FILES_STATUS', hasFiles: setupComplete });
      }
      return;
    }

    const selectedIds = new Set(selected.map(item => item.id));

    // Generate files if any assistants were selected
    if (selectedIds.size > 0) {
      // Mark as configured
      const hasBeenConfigured = context.globalState.get<boolean>('aspectcode.assistants.configured', false);
      
      if (!hasBeenConfigured) {
        await context.globalState.update('aspectcode.assistants.configured', true);
      }

      // Build assistants override to pass to generateInstructionFiles.
      // This ensures KB files are created BEFORE settings are written to disk,
      // preventing orphan .settings.json files if generation is interrupted.
      const assistantsOverride: AssistantsOverride = {
        copilot: selectedIds.has('copilot'),
        cursor: selectedIds.has('cursor'),
        claude: selectedIds.has('claude'),
        other: selectedIds.has('other')
      };

      // Generate files directly without extra confirmation
      if (perfEnabled) {
        outputChannel.appendLine('[Perf][Assistants][configure] executing generateInstructionFiles');
      }
      // IMPORTANT: Call handleGenerateInstructionFiles directly with the assistants override.
      // This ensures KB is generated first (creating .aspect/ with KB files),
      // then instruction files are generated based on the passed-in selection.
      try {
        await handleGenerateInstructionFiles(state, outputChannel, context, assistantsOverride);
        if (perfEnabled) {
          outputChannel.appendLine('[Perf][Assistants][configure] generateInstructionFiles resolved');
        }
      } catch (err) {
        outputChannel.appendLine(`[Assistants] generateInstructionFiles failed: ${err}`);
        // Don't write settings if KB generation failed
        throw err;
      }
      
      // NOW write settings after KB files are successfully created.
      // This ensures .aspect/ is created with KB files first, then settings are added.
      const tCfg = Date.now();
      await updateAspectSettings(workspaceRoot, {
          assistants: assistantsOverride,
          // Initialize default exclusion settings so users can see/edit them
          excludeDirectories: {
            always: [],
            never: []
          }
      });
      if (perfEnabled) {
        outputChannel.appendLine(`[Perf][Assistants][configure] .aspect settings update tookMs=${Date.now() - tCfg}`);
      }
      
      outputChannel.appendLine(`[Assistants] Configuration updated: ${Array.from(selectedIds).join(', ')}`);
    }

    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Assistants][configure] end tookMs=${Date.now() - tStart}`);
    }
  } catch (error) {
    outputChannel.appendLine(`[Assistants] Error: ${error}`);
    vscode.window.showErrorMessage(`Failed to configure assistants: ${error}`);
  }
}

/**
 * Handle aspectcode.generateInstructionFiles command.
 * Generates KB files and instruction files based on settings.
 * Uses fully local analysis (tree-sitter + dependency analysis) - no server required.
 * 
 * @param assistantsOverride Optional assistants selection. If provided, uses these
 *   values instead of reading from .aspect/.settings.json. This enables
 *   generating instruction files before settings are written to disk.
 */
async function handleGenerateInstructionFiles(
  state: AspectCodeState,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext,
  assistantsOverride?: AssistantsOverride
): Promise<void> {
  try {
    const perfEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.devLogs', true);
    const tStart = Date.now();
    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Instructions][cmd] start`);
    }

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    // Generate instruction files directly using local analysis (no server needed)
    // The generateInstructionFiles function handles KB generation internally
    const tGen = Date.now();
    await generateInstructionFiles(workspaceRoot, state, outputChannel, context, assistantsOverride);
    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Instructions][cmd] generateInstructionFiles tookMs=${Date.now() - tGen}`);
    }

    // Mark KB as fresh after generation
    try {
      const { getWorkspaceFingerprint } = await import('./extension');
      const fingerprint = getWorkspaceFingerprint();
      if (fingerprint) {
        await fingerprint.markKbFresh();
        outputChannel.appendLine('[KB] Marked KB as fresh');
      }
    } catch (e) {
      outputChannel.appendLine(`[KB] Failed to mark KB fresh (non-critical): ${e}`);
    }

    vscode.window.showInformationMessage('Aspect Code knowledge base and assistant instruction files have been updated.');

    if (perfEnabled) {
      outputChannel.appendLine(`[Perf][Instructions][cmd] end tookMs=${Date.now() - tStart}`);
    }
  } catch (error) {
    outputChannel.appendLine(`[Instructions] Error: ${error}`);
    vscode.window.showErrorMessage(`Failed to generate instruction files: ${error}`);
  }
}

async function handleSetInstructionMode(mode: InstructionsMode, outputChannel: vscode.OutputChannel): Promise<void> {
  try {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    if (mode === 'off') {
      const confirmed = await vscode.window.showWarningMessage(
        'Aspect Code: Turn off instructions? This will remove only the Aspect Code block (between the ASPECT_CODE_START/END markers) from any existing instruction files.',
        { modal: true },
        'Turn Off'
      );
      if (confirmed !== 'Turn Off') {
        return;
      }
    }

    if (mode === 'custom') {
      const customFile = vscode.Uri.joinPath(workspaceRoot, '.aspect', 'instructions.md');
      try {
        await vscode.workspace.fs.stat(customFile);
      } catch {
        vscode.window.showErrorMessage('Aspect Code: Custom mode requires .aspect/instructions.md to exist.');
        return;
      }
    }

    await setInstructionsModeSetting(workspaceRoot, mode);
    outputChannel.appendLine(`[Instructions] Set instructions.mode=${mode} in .aspect/.settings.json`);

    // Check if any assistants are enabled before regenerating
    const { getAssistantsSettings } = await import('./services/aspectSettings');
    const assistants = await getAssistantsSettings(workspaceRoot, outputChannel);
    const hasEnabledAssistants = assistants.copilot || assistants.cursor || assistants.claude || assistants.other;

    if (hasEnabledAssistants) {
      // Regenerate instruction files only; do not run EXAMINE or KB generation.
      await regenerateInstructionFilesOnly(workspaceRoot, outputChannel);
    } else {
      // No assistants configured - nothing to regenerate.
      outputChannel.appendLine('[Instructions] No assistants enabled; skipped instruction file regeneration');
    }
  } catch (error) {
    outputChannel.appendLine(`[Instructions] Failed to set instruction mode: ${error}`);
    vscode.window.showErrorMessage(`Failed to set instruction mode: ${error}`);
  }
}

async function handleEditCustomInstructions(outputChannel: vscode.OutputChannel): Promise<void> {
  try {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!workspaceRoot) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const aspectDir = vscode.Uri.joinPath(workspaceRoot, '.aspect');
    const customFile = vscode.Uri.joinPath(aspectDir, 'instructions.md');

    let exists = true;
    try {
      await vscode.workspace.fs.stat(customFile);
    } catch {
      exists = false;
    }

    if (!exists) {
      const confirmed = await vscode.window.showWarningMessage(
        'Aspect Code: Create .aspect/instructions.md and switch to Custom mode? This file will be used as the content inserted into AI instruction files.',
        { modal: true },
        'Create & Edit'
      );
      if (confirmed !== 'Create & Edit') {
        return;
      }

      try {
        await vscode.workspace.fs.createDirectory(aspectDir);
      } catch {
        // ignore
      }

      const template =
        `## Aspect Code Custom Instructions\n\n` +
        `Edit this file to control the instructions inserted into your AI assistant instruction files.\n` +
        `This content will be placed inside the Aspect Code markers (ASPECT_CODE_START/END).\n`;
      await vscode.workspace.fs.writeFile(customFile, Buffer.from(template, 'utf-8'));
      outputChannel.appendLine('[Instructions] Created .aspect/instructions.md');
    }

    // Activate custom mode (no prompt when already exists).
    await setInstructionsModeSetting(workspaceRoot, 'custom');
    outputChannel.appendLine('[Instructions] Set instructions.mode=custom in .aspect/.settings.json');

    const assistants = await getAssistantsSettings(workspaceRoot, outputChannel);
    const hasEnabledAssistants = assistants.copilot || assistants.cursor || assistants.claude || assistants.other;
    if (hasEnabledAssistants) {
      await regenerateInstructionFilesOnly(workspaceRoot, outputChannel);
    }

    const doc = await vscode.workspace.openTextDocument(customFile);
    await vscode.window.showTextDocument(doc, { preview: false });
  } catch (error) {
    outputChannel.appendLine(`[Instructions] Failed to edit custom instructions: ${error}`);
    vscode.window.showErrorMessage(`Failed to edit custom instructions: ${error}`);
  }
}

async function handleCopyKbReceiptPrompt(outputChannel: vscode.OutputChannel): Promise<void> {
  try {
    const text =
`Using the Aspect Code knowledge base available in this repository, return a KB Receipt in this exact format:

Architecture hubs: <file1> (Imported By: <n1>), <file2> (Imported By: <n2>)

One entry point file + its category (runtime / script / barrel)

One module cluster name + 3 files in it

One symbol (name + kind + defining file)

KB generated timestamp

If you can’t access the KB, output exactly: KB_NOT_AVAILABLE.`;

    await vscode.env.clipboard.writeText(text);
    vscode.window.showInformationMessage('Aspect Code: KB receipt prompt copied to clipboard.');
  } catch (error) {
    outputChannel.appendLine(`[KB Receipt] Failed to copy prompt: ${error}`);
    vscode.window.showErrorMessage(`Failed to copy KB receipt prompt: ${error}`);
  }
}