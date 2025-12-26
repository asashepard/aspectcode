/**
 * New Command Integration
 * 
 * This module integrates the new engine-based commands with the existing extension.
 * It can be imported and activated alongside the existing functionality.
 */

import * as vscode from 'vscode';
import { AspectCodeCommands, AspectCodeCodeActionProvider } from './commands';
import { SmartValidationService } from './services/SmartValidationService';
import { PromptGenerationService } from './services/PromptGenerationService';
import { AspectCodeState } from './state';
import { detectAssistants, AssistantId } from './assistants/detection';
import { generateInstructionFiles } from './assistants/instructions';
import { addAlignmentEntry } from './assistants/kb';
import type { ScoreResult } from './scoring/scoreEngine';

/**
 * Activate the new engine-based commands.
 * Call this from the main extension activate function.
 */
export function activateNewCommands(context: vscode.ExtensionContext, state: AspectCodeState): void {
  const outputChannel = vscode.window.createOutputChannel('Aspect Code Engine');
  const commands = new AspectCodeCommands(context, state);
  const codeActionProvider = new AspectCodeCodeActionProvider(commands);
  const smartValidationService = new SmartValidationService(outputChannel);
  const promptGenerationService = new PromptGenerationService(outputChannel);

  // Register commands
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.scanWorkspace', () => commands.scanWorkspace()),
    vscode.commands.registerCommand('aspectcode.scanActiveFile', () => commands.scanActiveFile()),
    // Auto-Fix commands temporarily disabled
    // vscode.commands.registerCommand('aspectcode.applyAutofix', (findings?: any) => commands.applyAutofix(findings)),
    vscode.commands.registerCommand('aspectcode.openFinding', (finding: any) => commands.openFinding(finding)),
    vscode.commands.registerCommand('aspectcode.insertSuppression', (finding: any) => commands.insertSuppression(finding)),
    vscode.commands.registerCommand('aspectcode.configureRules', () => commands.configureRules()),
    vscode.commands.registerCommand('aspectcode.explainFile', async () => {
      return await handleExplainFile(promptGenerationService);
    }),
    vscode.commands.registerCommand('aspectcode.proposeFixes', async () => {
      return await handleProposeFixes(promptGenerationService, state);
    }),
    vscode.commands.registerCommand('aspectcode.alignIssue', async () => {
      return await handleAlignIssue(promptGenerationService, state, outputChannel);
    }),
    vscode.commands.registerCommand('aspectcode.configureAssistants', async () => {
      return await handleConfigureAssistants(context, state, commands, outputChannel);
    }),
    vscode.commands.registerCommand('aspectcode.generateInstructionFiles', async () => {
      return await handleGenerateInstructionFiles(state, commands, outputChannel, context);
    })
  );

  // Register code action provider for all supported languages
  context.subscriptions.push(
    vscode.languages.registerCodeActionsProvider(
      [
        { language: 'python', scheme: 'file' },
        { language: 'typescript', scheme: 'file' },
        { language: 'javascript', scheme: 'file' },
        { language: 'typescriptreact', scheme: 'file' },
        { language: 'javascriptreact', scheme: 'file' }
      ],
      codeActionProvider,
      {
        providedCodeActionKinds: [
          vscode.CodeActionKind.QuickFix,
          vscode.CodeActionKind.SourceFixAll
        ]
      }
    )
  );

  // Register file watcher for debounced scanning
  const fileWatcher = vscode.workspace.createFileSystemWatcher('**/*.{py,ts,tsx,js,jsx,mjs,cjs}');
  let debounceTimer: NodeJS.Timeout | undefined;

  const debouncedScan = () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
    }
    
    const config = vscode.workspace.getConfiguration('aspectcode');
    const debounceMs = config.get<number>('validation.debounceMs', 400);
    const validateOnSave = config.get<boolean>('validation.onSave', true);
    const enableLegacyPreflight = config.get<boolean>('enableLegacyPreflight', false);
    
    if (!validateOnSave || !enableLegacyPreflight) {
      return;
    }
    
    debounceTimer = setTimeout(() => {
      // Only scan active file on save for performance
      const activeEditor = vscode.window.activeTextEditor;
      if (activeEditor) {
        commands.scanActiveFile();
      }
    }, debounceMs);
  };

  fileWatcher.onDidChange(debouncedScan);
  fileWatcher.onDidCreate(debouncedScan);
  
  // Also scan on document save
  const saveListener = vscode.workspace.onDidSaveTextDocument((document) => {
    const config = vscode.workspace.getConfiguration('aspectcode');
    const validateOnSave = config.get<boolean>('validation.onSave', true);
    // Auto-Fix on save disabled - feature temporarily disabled
    // const autofixOnSave = config.get<boolean>('autofix.onSave', false);
    const enableLegacyPreflight = config.get<boolean>('enableLegacyPreflight', false);
    
    if (validateOnSave && enableLegacyPreflight) {
      debouncedScan();
    }
    
    // Optional: Apply safe autofixes on save - feature temporarily disabled
    // if (autofixOnSave) {
    //   setTimeout(() => {
    //     commands.applyAutofix();
    //   }, 1000); // Wait for scan to complete
    // }
  });

  context.subscriptions.push(fileWatcher, saveListener);

  // Watch for ALIGNMENTS.json changes to update the align button visibility
  const alignmentsWatcher = vscode.workspace.createFileSystemWatcher('**/ALIGNMENTS.json');
  const updateAlignmentsButton = async () => {
    const panelProvider = (state as any)._panelProvider;
    if (panelProvider && typeof panelProvider.post === 'function') {
      const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (workspaceRoot) {
        const { alignmentsFileExists } = await import('./assistants/kb');
        const hasFile = await alignmentsFileExists(workspaceRoot);
        panelProvider.post({ type: 'ALIGNMENTS_FILE_STATUS', hasFile });
      }
    }
  };
  alignmentsWatcher.onDidCreate(updateAlignmentsButton);
  alignmentsWatcher.onDidDelete(updateAlignmentsButton);
  context.subscriptions.push(alignmentsWatcher);

  // Watch for .aspect/ folder and instruction file changes to update the '+' button visibility
  // Track if we've recently shown the notification to avoid spamming
  let lastNotificationTime = 0;
  const NOTIFICATION_DEBOUNCE_MS = 5000;

  const updateInstructionFilesStatus = async (showNotificationOnMissing: boolean = false) => {
    const panelProvider = (state as any)._panelProvider;
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!workspaceRoot) {return;}

    const detected = await detectAssistants(workspaceRoot);
    const hasAspectKB = detected.has('aspectKB');
    
    // Check for instruction files (exclude aspectKB and alignments from count)
    const instructionAssistants = new Set(detected);
    instructionAssistants.delete('aspectKB');
    instructionAssistants.delete('alignments');
    const hasInstructionFiles = instructionAssistants.size > 0;
    
    // Show + button if either is missing
    const setupComplete = hasAspectKB && hasInstructionFiles;
    
    // Update panel if available
    if (panelProvider && typeof panelProvider.post === 'function') {
      panelProvider.post({ type: 'INSTRUCTION_FILES_STATUS', hasFiles: setupComplete });
    }

    // Show notification if setup is incomplete and we should notify
    if (showNotificationOnMissing && !setupComplete) {
      const now = Date.now();
      if (now - lastNotificationTime > NOTIFICATION_DEBOUNCE_MS) {
        lastNotificationTime = now;
        outputChannel.appendLine(`[Watcher] Detected missing files: aspectKB=${hasAspectKB}, instructionFiles=${hasInstructionFiles}`);
        const message = !hasAspectKB 
          ? 'Aspect Code: Knowledge base (.aspect/) was deleted.'
          : 'Aspect Code: AI instruction files were deleted.';
        const action = await vscode.window.showWarningMessage(
          message + ' Regenerate to restore AI assistant context.',
          'Regenerate'
        );
        if (action === 'Regenerate') {
          vscode.commands.executeCommand('aspectcode.configureAssistants');
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

  // Watch for .aspect/ folder changes (including files within it)
  const aspectWatcher = vscode.workspace.createFileSystemWatcher('**/.aspect/**');
  aspectWatcher.onDidCreate((uri) => {
    outputChannel.appendLine(`[Watcher] .aspect file created: ${uri.fsPath}`);
    debouncedInstructionUpdate(false);
  });
  aspectWatcher.onDidDelete((uri) => {
    outputChannel.appendLine(`[Watcher] .aspect file deleted: ${uri.fsPath}`);
    debouncedInstructionUpdate(true);
  });
  context.subscriptions.push(aspectWatcher);

  // Also watch for the .aspect folder itself being deleted
  const aspectFolderWatcher = vscode.workspace.createFileSystemWatcher('**/.aspect');
  aspectFolderWatcher.onDidCreate((uri) => {
    outputChannel.appendLine(`[Watcher] .aspect folder created: ${uri.fsPath}`);
    debouncedInstructionUpdate(false);
  });
  aspectFolderWatcher.onDidDelete((uri) => {
    outputChannel.appendLine(`[Watcher] .aspect folder deleted: ${uri.fsPath}`);
    debouncedInstructionUpdate(true);
  });
  context.subscriptions.push(aspectFolderWatcher);

  // Watch for instruction files: AGENTS.md, CLAUDE.md
  const rootInstructionWatcher = vscode.workspace.createFileSystemWatcher('**/{AGENTS,CLAUDE}.md');
  rootInstructionWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  rootInstructionWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  context.subscriptions.push(rootInstructionWatcher);

  // Watch for Copilot instructions
  const copilotWatcher = vscode.workspace.createFileSystemWatcher('**/.github/copilot-instructions.md');
  copilotWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  copilotWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  context.subscriptions.push(copilotWatcher);

  // Watch for Cursor files
  const cursorWatcher = vscode.workspace.createFileSystemWatcher('**/{.cursor,.cursorrules}');
  cursorWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  cursorWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  const cursorFolderWatcher = vscode.workspace.createFileSystemWatcher('**/.cursor/**');
  cursorFolderWatcher.onDidCreate(() => debouncedInstructionUpdate(false));
  cursorFolderWatcher.onDidDelete(() => debouncedInstructionUpdate(true));
  context.subscriptions.push(cursorWatcher, cursorFolderWatcher);

  // Run initial check on startup (after a short delay to let panel initialize)
  // This ensures notification shows even if panel is never opened
  setTimeout(async () => {
    const workspaceRoot = vscode.workspace.workspaceFolders?.[0]?.uri;
    if (!workspaceRoot) {return;}

    const detected = await detectAssistants(workspaceRoot);
    const hasAspectKB = detected.has('aspectKB');
    
    const instructionAssistants = new Set(detected);
    instructionAssistants.delete('aspectKB');
    instructionAssistants.delete('alignments');
    const hasInstructionFiles = instructionAssistants.size > 0;
    
    const setupComplete = hasAspectKB && hasInstructionFiles;
    
    outputChannel.appendLine(`[Startup] Instruction files check: aspectKB=${hasAspectKB}, instructionFiles=${hasInstructionFiles}, setupComplete=${setupComplete}`);
    
    if (!setupComplete) {
      // Update panel if available
      const panelProvider = (state as any)._panelProvider;
      if (panelProvider && typeof panelProvider.post === 'function') {
        panelProvider.post({ type: 'INSTRUCTION_FILES_STATUS', hasFiles: false });
      }
      
      // Show warning notification (more persistent than info)
      const message = !hasAspectKB 
        ? 'Aspect Code: Knowledge base (.aspect/) not found.'
        : 'Aspect Code: No AI instruction files found.';
      const action = await vscode.window.showWarningMessage(
        message + ' Generate them to provide AI assistants with project context.',
        'Generate Now'
      );
      if (action === 'Generate Now') {
        vscode.commands.executeCommand('aspectcode.configureAssistants');
      }
    }
  }, 2000);

  // Add legacy CLI scan status bar items (only if enabled)
  const config = vscode.workspace.getConfiguration('aspectcode');
  const enableLegacyPreflight = config.get<boolean>('enableLegacyPreflight', false);
  
  if (enableLegacyPreflight) {
    // Add to status bar for easy access
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    statusBarItem.text = '$(search) Scan Workspace';
    statusBarItem.command = 'aspectcode.scanWorkspace';
    statusBarItem.tooltip = 'Scan workspace with Aspect Code (Legacy CLI)';
    statusBarItem.show();
    
    // Add rule configuration button to status bar
    const configStatusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 99);
    configStatusBarItem.text = '$(settings-gear)';
    configStatusBarItem.command = 'aspectcode.configureRules';
    configStatusBarItem.tooltip = 'Configure Aspect Code rule categories (Legacy)';
    configStatusBarItem.show();
    
    context.subscriptions.push(statusBarItem, configStatusBarItem);
  }
}

/**
 * Handle Explain File command - immediately copies to clipboard
 */
async function handleExplainFile(promptService: PromptGenerationService): Promise<void> {
  try {
    const activeEditor = vscode.window.activeTextEditor;
    if (!activeEditor) {
      vscode.window.showWarningMessage('No active file to explain');
      return;
    }

    const fileName = activeEditor.document.fileName.split(/[\\/]/).pop();

    const prompt = await promptService.buildExplainCurrentFilePrompt({
      activeFileUri: activeEditor.document.uri,
      fileContent: activeEditor.document.getText()
    });

    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage(`Explanation for ${fileName} copied to clipboard`);

  } catch (error) {
    vscode.window.showErrorMessage(`Failed to generate explanation: ${error}`);
  }
}

/**
 * Handle Propose Fixes command - immediately copies to clipboard
 */
async function handleProposeFixes(promptService: PromptGenerationService, state: AspectCodeState): Promise<void> {
  const MAX_CONTEXT_LENGTH = 500; // Character limit for optional context
  
  try {
    const currentState = state.s;
    const findings = currentState.findings || [];

    if (findings.length === 0) {
      vscode.window.showWarningMessage('No findings available. Run examination first to get structural context.');
      return;
    }

    // Ask for optional context (not required)
    const userContext = await vscode.window.showInputBox({
      prompt: 'What would you like the AI to help with? (optional)',
      placeHolder: 'e.g., "Refactor the auth module" or "Fix the API timeout issue" (leave blank for general guidance)',
      ignoreFocusOut: true,
      validateInput: (value) => {
        if (value && value.length > MAX_CONTEXT_LENGTH) {
          return `Context too long (${value.length}/${MAX_CONTEXT_LENGTH} characters)`;
        }
        return null;
      }
    });

    // User cancelled the input box (pressed Escape)
    if (userContext === undefined) {
      return;
    }

    // Convert findings to the expected format
    const formattedFindings = findings.map((f: any) => ({
      id: f.id || f.violation_id || `finding-${Math.random()}`,
      code: f.rule || f.code || f.ruleId || 'unknown',
      severity: (f.severity === 'critical' ? 'error' : f.severity) as 'info' | 'warn' | 'error',
      file: f.file || '',
      message: f.explain || f.message || f.title || '',
      fixable: !!f.fixable,
      span: f.span,
      _raw: f
    }));

    const prompt = await promptService.buildProposeFixesPrompt({
      findings: formattedFindings,
      userContext: userContext.trim() || undefined // Pass context if provided
    });

    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage('Structural plan copied to clipboard');

  } catch (error) {
    vscode.window.showErrorMessage(`Failed to generate plan: ${error}`);
  }
}

/**
 * Handle Align Issue command - asks user to describe the AI issue,
 * generates a prompt to help fix it, and logs to ALIGNMENTS.json
 */
async function handleAlignIssue(
  promptService: PromptGenerationService, 
  state: AspectCodeState,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  try {
    // Prompt user to describe the issue they experienced
    const issueDescription = await vscode.window.showInputBox({
      prompt: 'Describe the issue you experienced',
      placeHolder: 'e.g., "Kept trying to use deprecated API" or "Deleted important code"',
      ignoreFocusOut: true
    });

    if (!issueDescription) {
      return; // User cancelled
    }

    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    // Add entry to ALIGNMENTS.json (files left blank for user to fill in)
    await addAlignmentEntry(workspaceRoot, {
      issue: issueDescription,
      files: [], // Empty - user can add relevant files later
      resolution: '' // Empty - to be filled in later by user after verification
    }, outputChannel);

    // Generate the alignment prompt
    const prompt = await promptService.buildAlignmentPrompt({
      issueDescription,
      findings: state.s.findings || []
    });

    await vscode.env.clipboard.writeText(prompt);
    vscode.window.showInformationMessage(
      'Alignment prompt copied to clipboard. Issue logged to ALIGNMENTS.json'
    );

  } catch (error) {
    vscode.window.showErrorMessage(`Failed to generate alignment prompt: ${error}`);
  }
}

async function handleAutoFixSafe(commands: AspectCodeCommands): Promise<void> {
  try {
    // Get all findings currently in state (primary) and diagnostics (fallback)
    const allFindings = commands.getCurrentFindings();

    if (allFindings.length === 0) {
      vscode.window.showInformationMessage('No findings available. Please run analysis first.');
      return;
    }

    // Apply Auto-Fix v1 to existing findings (this will filter for compatible rules)
    // The applyAutofix method will handle all state management including busy state
    await commands.applyAutofix(allFindings);
    
  } catch (error) {
    vscode.window.showErrorMessage(`Auto-Fix v1 failed: ${error}`);
  }
}

/**
 * Handle aspectcode.configureAssistants command.
 * Detects assistants, shows QuickPick, updates settings, offers immediate generation.
 */
async function handleConfigureAssistants(
  context: vscode.ExtensionContext,
  state: AspectCodeState,
  commands: AspectCodeCommands,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  try {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    // Detect existing assistants
    const detected = await detectAssistants(workspaceRoot);
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
      // TEMPORARILY DISABLED: ALIGNMENTS.json feature
      // {
      //   id: 'alignments',
      //   label: '$(question) Issue Alignments (ALIGNMENTS.json)',
      //   description: detected.has('alignments') ? '(detected)' : '',
      //   picked: detected.has('alignments')
      // }
    ];

    const selected = await vscode.window.showQuickPick(items, {
      canPickMany: true,
      placeHolder: 'Select AI assistants to configure Aspect Code for'
    });

    if (!selected) {
      return; // User cancelled
    }

    const selectedIds = new Set(selected.map(item => item.id));

    // Update workspace settings in parallel
    const config = vscode.workspace.getConfiguration('aspectcode.assistants');
    await Promise.all([
      config.update('copilot', selectedIds.has('copilot'), vscode.ConfigurationTarget.Workspace),
      config.update('cursor', selectedIds.has('cursor'), vscode.ConfigurationTarget.Workspace),
      config.update('claude', selectedIds.has('claude'), vscode.ConfigurationTarget.Workspace),
      config.update('other', selectedIds.has('other'), vscode.ConfigurationTarget.Workspace)
    ]);
    // TEMPORARILY DISABLED: ALIGNMENTS.json feature
    // await config.update('alignments', selectedIds.has('alignments'), vscode.ConfigurationTarget.Workspace);

    outputChannel.appendLine(`[Assistants] Configuration updated: ${Array.from(selectedIds).join(', ')}`);

    // Generate files if any assistants were selected
    if (selectedIds.size > 0) {
      // Mark as configured
      const hasBeenConfigured = context.globalState.get<boolean>('aspectcode.assistants.configured', false);
      
      if (!hasBeenConfigured) {
        await context.globalState.update('aspectcode.assistants.configured', true);
      }

      // Generate files directly without extra confirmation
      await vscode.commands.executeCommand('aspectcode.generateInstructionFiles');
    }
  } catch (error) {
    outputChannel.appendLine(`[Assistants] Error: ${error}`);
    vscode.window.showErrorMessage(`Failed to configure assistants: ${error}`);
  }
}

/**
 * Handle aspectcode.generateInstructionFiles command.
 * Generates KB files and instruction files based on settings.
 * If no findings exist yet, runs INDEX and EXAMINE first.
 */
async function handleGenerateInstructionFiles(
  state: AspectCodeState,
  commands: AspectCodeCommands,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
): Promise<void> {
  try {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) {
      vscode.window.showErrorMessage('No workspace folder open');
      return;
    }

    const workspaceRoot = workspaceFolders[0].uri;

    // If no findings exist, run INDEX and EXAMINE first
    let findings = state.s.findings;
    if (!findings || findings.length === 0) {
      outputChannel.appendLine('[Instructions] No findings exist, running INDEX and EXAMINE first...');
      
      // Show progress notification
      await vscode.window.withProgress({
        location: vscode.ProgressLocation.Notification,
        title: 'Aspect Code',
        cancellable: false
      }, async (progress) => {
        progress.report({ message: 'Indexing repository...' });
        await vscode.commands.executeCommand('aspectcode.index');
        
        progress.report({ message: 'Running examination...' });
        await vscode.commands.executeCommand('aspectcode.examine');
      });
      
      // Re-fetch findings after examination
      findings = state.s.findings;
      outputChannel.appendLine(`[Instructions] Examination complete, ${findings.length} findings`);
    }

    // Calculate score from current findings
    let scoreResult: ScoreResult | null = null;

    if (findings.length > 0) {
      // Import score engine dynamically to avoid circular deps
      const { AsymptoticScoreEngine } = await import('./scoring/scoreEngine');
      const scoreEngine = new AsymptoticScoreEngine();
      
      // Convert state findings to scoreEngine format
      const scoringFindings = findings.map(f => {
        // Map severity from state format to scoring format
        let severity: 'critical' | 'high' | 'medium' | 'low' | 'info' = 'info';
        if (f.severity === 'error') {
          severity = 'critical';
        } else if (f.severity === 'warn') {
          severity = 'medium';
        } else {
          severity = 'info';
        }

        return {
          id: f.id || '',
          rule: f.code,
          severity,
          message: f.message,
          file: f.file,
          locations: [],
          fixable: f.fixable
        };
      });

      scoreResult = scoreEngine.calculateScore(scoringFindings);
    }

    // Generate instruction files
    await generateInstructionFiles(workspaceRoot, state, scoreResult, outputChannel, context);

    // Save cache after generating files (ensures cache is in sync with KB)
    try {
      const { getCacheManager, getIncrementalIndexer } = await import('./extension');
      const cacheManager = getCacheManager();
      const incrementalIndexer = getIncrementalIndexer();
      
      if (cacheManager && incrementalIndexer) {
        outputChannel.appendLine('[Cache] Saving cache after KB generation...');
        const signatures = await cacheManager.buildFileSignatures();
        const cachedFindings = cacheManager.findingsToCache(state.s.findings || []);
        const dependencies = cacheManager.dependenciesToCache(incrementalIndexer.getReverseDependencyGraph());
        const lastValidate = state.s.lastValidate ? {
          total: state.s.lastValidate.total,
          fixable: state.s.lastValidate.fixable,
          tookMs: state.s.lastValidate.tookMs
        } : undefined;
        await cacheManager.saveCache(signatures, cachedFindings, dependencies, lastValidate);
        outputChannel.appendLine(`[Cache] Saved ${cachedFindings.length} findings to cache`);
      } else {
        outputChannel.appendLine('[Cache] Cache manager or indexer not available, skipping cache save');
      }
    } catch (cacheError) {
      outputChannel.appendLine(`[Cache] Failed to save cache (non-critical): ${cacheError}`);
    }

    // DISABLED: ALIGNMENTS.json feature - never generate this file
    // const assistantsConfig = vscode.workspace.getConfiguration('aspectcode.assistants');
    // if (assistantsConfig.get<boolean>('alignments', false)) {
    //   await initializeAlignmentsFile(workspaceRoot, outputChannel);
    //   
    //   // Notify the panel to show the align button
    //   const panelProvider = (state as any)._panelProvider;
    //   if (panelProvider && typeof panelProvider.post === 'function') {
    //     panelProvider.post({ type: 'ALIGNMENTS_FILE_STATUS', hasFile: true });
    //   }
    // }

    vscode.window.showInformationMessage('Aspect Code knowledge base and assistant instruction files have been updated.');
  } catch (error) {
    outputChannel.appendLine(`[Instructions] Error: ${error}`);
    vscode.window.showErrorMessage(`Failed to generate instruction files: ${error}`);
  }
}