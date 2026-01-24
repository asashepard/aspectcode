import * as vscode from 'vscode';
import { exec } from 'child_process';
import { parsePatch, applyPatch } from 'diff';
import * as path from 'path';
import { loadGrammarsOnce, getLoadedGrammarsSummary } from './tsParser';
import { extractPythonImports, extractTSJSImports } from './importExtractors';
import { AspectCodeState } from './state';
import Parser from 'web-tree-sitter';
import { activateNewCommands } from './newCommandsIntegration';
import { WorkspaceFingerprint } from './services/WorkspaceFingerprint';
import { computeImpactSummaryForFile } from './assistants/kb';
import { AspectCodePanelProvider } from './panel/PanelProvider';
import { getAssistantsSettings, getAutoRegenerateKbSetting, migrateAspectSettingsFromVSCode, readAspectSettings, setAutoRegenerateKbSetting, getExtensionEnabledSetting, aspectDirExists } from './services/aspectSettings';
import { getEnablementCancellationToken } from './services/enablementCancellation';
import { initFileDiscoveryService, disposeFileDiscoveryService, type FileDiscoveryService } from './services/FileDiscoveryService';

// --- Type Definitions ---

/** Extended vscode.Diagnostic with violation tracking */
interface AspectCodeDiagnostic extends vscode.Diagnostic {
  violationId?: string;
}

let examineOnSave = false;
const diag = vscode.languages.createDiagnosticCollection('aspectcode');

// OUTPUT channel for logging
let outputChannel: vscode.OutputChannel;

// Status bar item
let statusBarItem: vscode.StatusBarItem;

// Workspace fingerprint for KB staleness detection
let workspaceFingerprint: WorkspaceFingerprint | null = null;

// FileDiscoveryService singleton
let fileDiscoveryService: FileDiscoveryService | null = null;

// Extension version from package.json
const EXTENSION_VERSION = '0.0.1';

/**
 * Get the workspace fingerprint service.
 * Returns null if not yet initialized.
 */
export function getWorkspaceFingerprint(): WorkspaceFingerprint | null {
  return workspaceFingerprint;
}

// Dev logging helper
function devLog(message: string, ...args: any[]) {
  const devLogsEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.devLogs', true);
  if (devLogsEnabled && outputChannel) {
    outputChannel.appendLine(`[DEV] ${message}`);
    if (args.length > 0) {
      outputChannel.appendLine(`[DEV] ${JSON.stringify(args, null, 2)}`);
    }
  }
}

// Cached parsers to avoid re-creating
const parserCache = new Map<string, Parser>();

// Parse stats for status
type ParseStats = {
  totalFiles: number;
  treeSitterFiles: number;
  skippedFiles: number;
  skipReasons: { [key: string]: number };
  totalTime: number;
};

let lastParseStats: ParseStats = {
  totalFiles: 0,
  treeSitterFiles: 0,
  skippedFiles: 0,
  skipReasons: {},
  totalTime: 0
};

// Helper to get or create cached parser
function getOrCreateParser(key: string, grammar: Parser.Language): Parser {
  if (!parserCache.has(key)) {
    const parser = new Parser();
    parser.setLanguage(grammar);
    parserCache.set(key, parser);
  }
  return parserCache.get(key)!;
}

async function readTextFile(uri: vscode.Uri): Promise<string | null> {
  try {
    const buf = await vscode.workspace.fs.readFile(uri);
    return buf.toString();
  } catch {
    return null;
  }
}

async function runPyright(workspaceRoot: string, files: vscode.Uri[]): Promise<any[] | null> {
  return new Promise((resolve) => {
    // Only run on Python files
    const pyFiles = files.filter(f => f.fsPath.endsWith('.py')).map(f => f.fsPath);
    if (pyFiles.length === 0) {
      resolve([]);
      return;
    }

    const fileArgs = pyFiles.map(f => `"${f}"`).join(' ');
    const cmd = `pyright --outputjson ${fileArgs}`;

    exec(cmd, { cwd: workspaceRoot }, (err, stdout, stderr) => {
      if (err) {
        // Pyright not installed or failed - fail soft
        resolve(null);
        return;
      }

      try {
        const result = JSON.parse(stdout);
        const diagnostics = result.generalDiagnostics || [];
        resolve(diagnostics);
      } catch (parseErr) {
        resolve(null);
      }
    });
  });
}

function modToPath(root: string, mod: string): string[] {
  // Try module.py and module/__init__.py
  const rel = mod.replace(/\./g, path.sep);
  return [
    path.join(root, rel + ".py"),
    path.join(root, rel, "__init__.py"),
  ];
}

function toModuleName(root: string, filePath: string): string {
  let rel = path.relative(root, filePath).replace(/\\/g, "/");
  if (rel.toLowerCase().endsWith("/__init__.py")) rel = rel.slice(0, -"/__init__.py".length);
  else if (rel.toLowerCase().endsWith(".py")) rel = rel.slice(0, -".py".length);
  return rel.split("/").filter(Boolean).join(".");
}

// Keep the last touched files so we can pin diagnostics if server returns no locations
let lastTouchedFiles: string[] = [];

// Track applied violations to prevent re-showing diagnostics
const appliedViolationIds = new Set<string>();

async function getWorkspaceRoot(): Promise<string | undefined> {
  const folders = vscode.workspace.workspaceFolders;
  return folders && folders.length > 0 ? folders[0].uri.fsPath : undefined;
}

function runGitDiff(cwd: string): Promise<string> {
  return new Promise((resolve) => {
    exec('git diff -U0', { cwd }, (err, stdout) => {
      resolve(stdout || '');
    });
  });
}

/**
 * Discover all source files in the workspace for incremental indexing
 */
async function discoverWorkspaceSourceFiles(): Promise<string[]> {
  const workspaceFolders = vscode.workspace.workspaceFolders;
  if (!workspaceFolders || workspaceFolders.length === 0) {
    return [];
  }
  
  const allFiles: string[] = [];
  const seenPaths = new Set<string>();
  
  // Use single combined pattern for much faster discovery
  const combinedPattern = '**/*.{py,ts,tsx,js,jsx,mjs,cjs,java,cpp,c,hpp,h,cs,go,rs}';
  // VS Code findFiles uses GlobPattern - use curly braces for alternatives
  const excludePattern = '**/{node_modules,.git,__pycache__,build,dist,target,e2e,playwright,cypress,.venv,venv,.next,coverage,site-packages,.pytest_cache,.mypy_cache,.tox,htmlcov,eggs,*.egg-info,.eggs}/**';
  
  try {
    const files = await vscode.workspace.findFiles(
      combinedPattern,
      excludePattern,
      5000 // Higher limit for large repos
    );
    
    for (const file of files) {
      const filePath = file.fsPath;
      if (!seenPaths.has(filePath)) {
        seenPaths.add(filePath);
        allFiles.push(filePath);
      }
    }
  } catch (error) {
    outputChannel?.appendLine(`Error finding files: ${error}`);
  }
  
  outputChannel?.appendLine(`[DiscoverFiles] Found ${allFiles.length} source files in workspace`);
  
  // Sanity check: warn if too many files (likely missing exclusions)
  if (allFiles.length > 2000) {
    outputChannel?.appendLine(`[DiscoverFiles] WARNING: Large file count (${allFiles.length}) may indicate missing exclusion patterns`);
  }
  
  return allFiles;
}

// IR builder with Tree-sitter only import extraction
async function buildIRForFiles(files: vscode.Uri[], workspaceRoot: string, context?: vscode.ExtensionContext): Promise<any> {
  outputChannel?.appendLine(`=== buildIRForFiles called with ${files.length} files ===`);

  const symbols: any[] = [];
  const edges: any[] = [];
  const types: any[] = [];

  // Track which modules/files we've scanned to avoid loops
  const scannedFiles = new Set<string>();
  const scannedModules = new Set<string>();

  // Queue of files to scan: start with touched files
  const q: vscode.Uri[] = [];

  // Config flags
  const treeSitterEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.treeSitter.enabled', true);
  const maxFileSizeKB = vscode.workspace.getConfiguration().get<number>('aspectcode.treeSitter.maxFileSizeKB', 256);

  outputChannel?.appendLine(`Config: treeSitterEnabled=${treeSitterEnabled}, maxFileSizeKB=${maxFileSizeKB}`);

  // Parse stats
  const stats: ParseStats = {
    totalFiles: 0,
    treeSitterFiles: 0,
    skippedFiles: 0,
    skipReasons: {},
    totalTime: 0
  };

  // Early exit if Tree-sitter is disabled
  if (!treeSitterEnabled) {
    outputChannel?.appendLine('Tree-sitter disabled by config; all files skipped');
    lastParseStats = stats;
    return { symbols, types, edges };
  }

  // Load Tree-sitter grammars once (fail-soft)
  let grammars: any = {};
  if (context) {
    try {
      outputChannel?.appendLine('Loading Tree-sitter grammars...');
      grammars = await loadGrammarsOnce(context, outputChannel);
      outputChannel?.appendLine('Tree-sitter grammars loaded successfully');
    } catch (error) {
      outputChannel?.appendLine(`Tree-sitter init failed: ${error}. All files skipped.`);
      lastParseStats = stats;
      return { symbols, types, edges };
    }
  } else {
    outputChannel?.appendLine('No context provided for Tree-sitter initialization');
  }

  outputChannel?.appendLine(`Processing ${files.length} files...`);

  // Add all source files to queue
  for (const u of files) {
    const ext = path.extname(u.fsPath);
    outputChannel?.appendLine(`Processing file: ${u.fsPath} (${ext})`);

    if (!['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
      outputChannel?.appendLine(`Skipping ${u.fsPath} - not a supported file type`);
      continue;
    }
    if (['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
      q.push(u);
    }
  }

  const startTime = Date.now();

  while (q.length > 0) {
    const uri = q.shift()!;
    const filePath = uri.fsPath;
    if (scannedFiles.has(filePath)) continue;
    scannedFiles.add(filePath);

    const text = await readTextFile(uri);
    if (text == null) continue;

    stats.totalFiles++;

    const modName = toModuleName(workspaceRoot, filePath);
    if (!scannedModules.has(modName)) {
      scannedModules.add(modName);
      symbols.push({ id: modName, kind: 'module', name: modName.split('.').pop() || modName, file: filePath, span: null });
    }

    // Extract defs (functions/classes) - simple regex for this is OK
    const defRe = /^\s*(def|class)\s+(\w+)/gm;
    let m: RegExpExecArray | null;
    while ((m = defRe.exec(text)) !== null) {
      const kind = m[1] === 'def' ? 'func' : 'class';
      const name = m[2];
      symbols.push({ id: `${modName}:${name}`, kind, name, file: filePath, span: null });
    }

    // Extract imports using Tree-sitter only
    let importModules: string[] = [];
    const ext = path.extname(filePath);
    const fileSizeKB = Buffer.byteLength(text, 'utf8') / 1024;

    // Check file size limit
    if (fileSizeKB > maxFileSizeKB) {
      const reason = 'size_limit';
      stats.skippedFiles++;
      stats.skipReasons[reason] = (stats.skipReasons[reason] || 0) + 1;
      const relativePath = path.relative(workspaceRoot, filePath);
      outputChannel?.appendLine(`TS skip: ${relativePath} — reason=${reason} (limit=${maxFileSizeKB}KB)`);
      continue;
    }

    // Determine required grammar and extract imports
    const fileStartTime = Date.now();
    let grammarUsed = false;

    try {
      if (ext === '.py' && grammars.python) {
        const parser = getOrCreateParser('python', grammars.python);
        importModules = extractPythonImports(grammars.python, text);
        grammarUsed = true;
      } else if (ext === '.ts' && grammars.typescript) {
        const parser = getOrCreateParser('typescript', grammars.typescript);
        importModules = extractTSJSImports(grammars.typescript, text);
        grammarUsed = true;
      } else if (ext === '.tsx' && grammars.tsx) {
        const parser = getOrCreateParser('tsx', grammars.tsx);
        importModules = extractTSJSImports(grammars.tsx, text);
        grammarUsed = true;
      } else if (['.js', '.jsx', '.mjs', '.cjs'].includes(ext) && grammars.javascript) {
        const parser = getOrCreateParser('javascript', grammars.javascript);
        importModules = extractTSJSImports(grammars.javascript, text);
        grammarUsed = true;
      } else {
        // Missing grammar - skip this file
        const reason = 'missing_grammar';
        stats.skippedFiles++;
        stats.skipReasons[reason] = (stats.skipReasons[reason] || 0) + 1;
        const relativePath = path.relative(workspaceRoot, filePath);
        outputChannel?.appendLine(`TS skip: ${relativePath} — reason=${reason}`);
        continue;
      }
    } catch (error) {
      // Parse error - skip this file
      const reason = 'parse_error';
      stats.skippedFiles++;
      stats.skipReasons[reason] = (stats.skipReasons[reason] || 0) + 1;
      const relativePath = path.relative(workspaceRoot, filePath);
      outputChannel?.appendLine(`TS skip: ${relativePath} — reason=${reason} (${error})`);
      continue;
    }

    if (grammarUsed) {
      stats.treeSitterFiles++;
      const parseTime = Date.now() - fileStartTime;
      const relativePath = path.relative(workspaceRoot, filePath);
      outputChannel?.appendLine(`TS(${ext.slice(1)}) parsed ${relativePath} in ${parseTime}ms`);
    }

    // Create edges and enqueue workspace modules (one-hop enrichment)
    for (const dst of importModules) {
      if (!dst) continue;
      edges.push({ kind: 'imports', src: modName, dst });

      // One-hop enrichment: if dst maps to a file in this workspace, scan it too
      for (const candidate of modToPath(workspaceRoot, dst)) {
        const uriCandidate = vscode.Uri.file(candidate);
        try {
          const stat = await vscode.workspace.fs.stat(uriCandidate);
          if (stat && stat.type === vscode.FileType.File) {
            // Add a symbol for dst module to help server anchor locations
            const dstMod = toModuleName(workspaceRoot, candidate);
            if (!scannedModules.has(dstMod)) {
              symbols.push({ id: dstMod, kind: 'module', name: dstMod.split('.').pop() || dstMod, file: candidate, span: null });
            }
            // Enqueue the file for scan (one hop)
            q.push(uriCandidate);
            break;
          }
        } catch {
          // not found; ignore
        }
      }
    }
  }

  // Calculate total time and store stats
  stats.totalTime = Date.now() - startTime;
  lastParseStats = stats;

  // Log summary
  const reasonStrings = Object.entries(stats.skipReasons).map(([reason, count]) => `${reason}=${count}`);
  const reasonSummary = reasonStrings.length > 0 ? ` (${reasonStrings.join(', ')})` : '';
  outputChannel?.appendLine(`Parse summary: TS: ${stats.treeSitterFiles} files, Skipped: ${stats.skippedFiles}${reasonSummary}, Duration: ${stats.totalTime}ms`);

  return { symbols, types, edges };
}

async function computeTouchedFilesFromGit(cwd: string): Promise<vscode.Uri[]> {
  return new Promise((resolve) => {
    exec('git diff --name-only', { cwd }, async (err, stdout) => {
      const allFiles = stdout.split('\n').filter(Boolean).map(f => vscode.Uri.file(path.join(cwd, f)));

      // Get focus path configuration
      const focusPath = vscode.workspace.getConfiguration().get<string>('aspectcode.focusPath', 'samples');

      if (!focusPath) {
        // No filtering - analyze all files
        outputChannel?.appendLine(`No focus path set - analyzing all ${allFiles.length} files`);
        resolve(allFiles);
        return;
      }

      // Filter to only include files in the focus directory
      const focusedFiles = allFiles.filter(uri => {
        const relativePath = path.relative(cwd, uri.fsPath);
        return relativePath.startsWith(focusPath + path.sep) || relativePath.startsWith(focusPath + '/');
      });

      outputChannel?.appendLine(`Focus path '${focusPath}': ${allFiles.length} total → ${focusedFiles.length} focused files`);
      if (focusedFiles.length !== allFiles.length) {
        const excludedFiles = allFiles.filter(uri => !focusedFiles.includes(uri)).map(uri => path.relative(cwd, uri.fsPath));
        outputChannel?.appendLine(`Excluded files: ${excludedFiles.join(', ')}`);
      }

      resolve(focusedFiles);
    });
  });
}

// Server-dependent functions (examineWorkspaceDiff, renderDiagnostics) removed.

async function detectEOL(filePath: string): Promise<string> {
  try {
    const content = await vscode.workspace.fs.readFile(vscode.Uri.file(filePath));
    const text = content.toString();
    return text.includes('\r\n') ? '\r\n' : '\n';
  } catch {
    return '\n'; // default to LF
  }
}

async function applyUnifiedDiffToWorkspace(repoRoot: string, patchedDiff: string, files?: any[]) {
  try {
    // Prefer files[] if available
    if (files && files.length > 0) {
      outputChannel?.appendLine(`Applying ${files.length} file(s) via files[] method`);

      for (const file of files) {
        outputChannel?.appendLine(`Processing file: ${file.relpath}`);
        const abs = path.join(repoRoot, file.relpath);
        outputChannel?.appendLine(`Absolute path: ${abs}`);

        // Security check
        if (!abs.startsWith(path.resolve(repoRoot))) {
          const errorMsg = `Aspect Code: patch tries to touch ${file.relpath} outside workspace — skipped`;
          outputChannel?.appendLine(errorMsg);
          vscode.window.showErrorMessage(errorMsg);
          continue;
        }

        try {
          // Detect current EOL style
          const eol = await detectEOL(abs);

          // Convert LF content to match current file's EOL style
          const content = file.content.replace(/\n/g, eol);

          // Write the file
          await vscode.workspace.fs.writeFile(vscode.Uri.file(abs), Buffer.from(content, 'utf8'));

        } catch (e) {
          const errorMsg = `Failed to write ${file.relpath}: ${(e as Error).message}`;
          const previewContent = file.content.substring(0, 120) + (file.content.length > 120 ? '...' : '');
          outputChannel?.appendLine(`ERROR applying patch to ${file.relpath}: ${errorMsg}`);
          outputChannel?.appendLine(`Content preview: ${previewContent}`);
          vscode.window.showErrorMessage(`${errorMsg}\nContent preview: ${previewContent}`);
        }
      }
      return;
    }

    // Fallback to unified diff parsing
    const parsed = parsePatch(patchedDiff);
    if (!parsed || parsed.length === 0) {
      vscode.window.showErrorMessage('Aspect Code: no patch hunks to apply.');
      return;
    }

    for (const filePatch of parsed) {
      // Prefer newFileName (b/...), else fall back to oldFileName (a/...)
      let rel = (filePatch.newFileName || filePatch.oldFileName || '').trim();
      // Strip leading a/ or b/
      rel = rel.replace(/^a\//, '').replace(/^b\//, '');
      if (!rel) {
        vscode.window.showErrorMessage('Aspect Code: patch missing target filename.');
        continue;
      }

      const abs = path.join(repoRoot, rel);
      if (!abs.startsWith(path.resolve(repoRoot))) {
        vscode.window.showErrorMessage(`Aspect Code: patch tries to touch ${rel} outside workspace — skipped`);
        continue;
      }
      const uri = vscode.Uri.file(abs);

      try {
        // Load current content
        let cur = '';
        try {
          cur = (await vscode.workspace.fs.readFile(uri)).toString();
        } catch (e) {
          vscode.window.showErrorMessage(`Aspect Code: cannot read ${rel} — ${(e as Error).message}`);
          continue;
        }

        // Detect EOL and normalize for patching
        const eol = cur.includes('\r\n') ? '\r\n' : '\n';
        const curLF = cur.replace(/\r\n/g, '\n');

        // Apply the structured patch (single-file) to the normalized content
        const nextLF = applyPatch(curLF, filePatch);
        if (typeof nextLF !== 'string') {
          const patchPreview = JSON.stringify(filePatch).substring(0, 120) + '...';
          vscode.window.showErrorMessage(`Aspect Code: failed to apply patch to ${rel}\nPatch preview: ${patchPreview}`);
          continue;
        }

        // Convert back to original EOL style
        const next = eol === '\r\n' ? nextLF.replace(/\n/g, '\r\n') : nextLF;

        // Write back
        await vscode.workspace.fs.writeFile(uri, Buffer.from(next, 'utf8'));

      } catch (e) {
        const errorMsg = `Aspect Code: error processing ${rel} — ${(e as Error).message}`;
        vscode.window.showErrorMessage(errorMsg);
      }
    }
  } catch (e) {
    vscode.window.showErrorMessage(`Aspect Code: patch application failed — ${(e as Error).message}`);
  }
}

// Server-dependent functions removed:
// - sendProgressToPanel (panel UI)
// - examineFullRepository (server validation)
// - showRepositoryStatus (server snapshots API)

// Command implementations
async function showParserStatus() {
  const treeSitterEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.treeSitter.enabled', true);
  const maxFileSizeKB = vscode.workspace.getConfiguration().get<number>('aspectcode.treeSitter.maxFileSizeKB', 256);
  const treeSitterOnly = vscode.workspace.getConfiguration().get<boolean>('aspectcode.treeSitter.only', true);
  const summary = getLoadedGrammarsSummary();

  const grammars = [];
  if (summary.python) grammars.push('Python');
  if (summary.typescript) grammars.push('TypeScript');
  if (summary.tsx) grammars.push('TSX');
  if (summary.javascript) grammars.push('JavaScript');

  const grammarText = grammars.length > 0 ? grammars.join(', ') : 'None';
  const enabledText = treeSitterEnabled ? 'Enabled' : 'Disabled';
  const { treeSitterFiles, skippedFiles, totalFiles, totalTime, skipReasons } = lastParseStats;

  const reasonText = Object.entries(skipReasons).map(([reason, count]) => `${reason}: ${count}`).join(', ');

  const message = [
    `Tree-sitter Status:`,
    `• Grammars loaded: ${grammarText}`,
    `• Parsing: ${enabledText} (max ${maxFileSizeKB}KB, TS-only: ${treeSitterOnly})`,
    `• Last examination: ${totalFiles} files (${treeSitterFiles} TS, ${skippedFiles} skipped) in ${totalTime}ms`,
    skippedFiles > 0 ? `• Skip reasons: ${reasonText}` : ''
  ].filter(Boolean).join('\n');

  vscode.window.showInformationMessage(message, { modal: true });
}

async function debugParseCurrentFile(context: vscode.ExtensionContext) {
  const editor = vscode.window.activeTextEditor;
  if (!editor) {
    vscode.window.showErrorMessage('No active file to parse');
    return;
  }

  const filePath = editor.document.uri.fsPath;
  const ext = path.extname(filePath);
  const text = editor.document.getText();

  if (!['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'].includes(ext)) {
    vscode.window.showErrorMessage('File type not supported for parsing');
    return;
  }

  outputChannel.show();
  outputChannel.appendLine(`\n=== Debug Parse: ${path.basename(filePath)} ===`);

  // Check configuration
  const treeSitterEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.treeSitter.enabled', true);
  const maxFileSizeKB = vscode.workspace.getConfiguration().get<number>('aspectcode.treeSitter.maxFileSizeKB', 256);
  const fileSizeKB = Buffer.byteLength(text, 'utf8') / 1024;

  outputChannel.appendLine(`Config: enabled=${treeSitterEnabled}, maxSizeKB=${maxFileSizeKB}`);
  outputChannel.appendLine(`File: ${fileSizeKB.toFixed(2)}KB`);

  if (!treeSitterEnabled) {
    outputChannel.appendLine('Result: Tree-sitter disabled - no imports extracted');
    outputChannel.appendLine('=== End Debug Parse ===\n');
    return;
  }

  if (fileSizeKB > maxFileSizeKB) {
    outputChannel.appendLine(`Result: File too large (${fileSizeKB.toFixed(2)}KB > ${maxFileSizeKB}KB) - no imports extracted`);
    outputChannel.appendLine('=== End Debug Parse ===\n');
    return;
  }

  // Try Tree-sitter parsing
  try {
    const grammars = await loadGrammarsOnce(context);
    const startTime = Date.now();
    let imports: string[] = [];
    let grammarUsed = false;

    if (ext === '.py' && grammars.python) {
      imports = extractPythonImports(grammars.python, text);
      grammarUsed = true;
      outputChannel.appendLine(`Tree-sitter (Python): ${imports.join(', ')} [${Date.now() - startTime}ms]`);
    } else if (ext === '.ts' && grammars.typescript) {
      imports = extractTSJSImports(grammars.typescript, text);
      grammarUsed = true;
      outputChannel.appendLine(`Tree-sitter (TypeScript): ${imports.join(', ')} [${Date.now() - startTime}ms]`);
    } else if (ext === '.tsx' && grammars.tsx) {
      imports = extractTSJSImports(grammars.tsx, text);
      grammarUsed = true;
      outputChannel.appendLine(`Tree-sitter (TSX): ${imports.join(', ')} [${Date.now() - startTime}ms]`);
    } else if (['.js', '.jsx', '.mjs', '.cjs'].includes(ext) && grammars.javascript) {
      imports = extractTSJSImports(grammars.javascript, text);
      grammarUsed = true;
      outputChannel.appendLine(`Tree-sitter (JavaScript): ${imports.join(', ')} [${Date.now() - startTime}ms]`);
    } else {
      outputChannel.appendLine(`Result: No grammar available for ${ext} - no imports extracted`);
    }

    if (grammarUsed) {
      outputChannel.appendLine(`Result: Extracted ${imports.length} imports using Tree-sitter`);
    }

  } catch (error) {
    outputChannel.appendLine(`Tree-sitter error: ${error} - no imports extracted`);
  }

  outputChannel.appendLine('=== End Debug Parse ===\n');
}

function parseLocationToSpan(loc: string | undefined) {
  if (!loc) return undefined;
  const m = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
  if (!m) return undefined;
  const l1 = Math.max(1, parseInt(m[2], 10));
  const c1 = Math.max(1, parseInt(m[3], 10));
  const l2 = Math.max(1, parseInt(m[4], 10));
  const c2 = Math.max(1, parseInt(m[5], 10));
  return {
    start: { line: l1, column: c1 },
    end: { line: l2, column: c2 }
  };
}

function parseLocationToFileAndSpan(loc?: string): { file: string; span?: { start: { line: number; column: number }; end: { line: number; column: number } } } | null {
  if (!loc) return null;
  // Greedy path capture, then 4 numbers. Works on "C:\x\y.py:10:1-12:2" and "/x/y.py:10:1-12:2"
  const m = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
  if (!m) return null;
  const file = m[1];
  const l1 = Math.max(1, parseInt(m[2], 10));
  const c1 = Math.max(1, parseInt(m[3], 10));
  const l2 = Math.max(1, parseInt(m[4], 10));
  const c2 = Math.max(1, parseInt(m[5], 10));
  return {
    file,
    span: { start: { line: l1, column: c1 }, end: { line: l2, column: c2 } }
  };
}

// Server-dependent function fetchCapabilitiesIfNeeded removed.

/**
 * Extract file paths from a unified diff.
 */
function extractFilesFromDiff(diff: string): string[] {
  const files = new Set<string>();
  const lines = diff.split('\n');
  
  for (const line of lines) {
    if (line.startsWith('+++') || line.startsWith('---')) {
      // Extract file path from "--- a/path/to/file" or "+++ b/path/to/file"
      const match = line.match(/^[+-]{3}\s+[ab]\/(.+)$/);
      if (match) {
        files.add(match[1]);
      }
    }
  }
  
  return Array.from(files);
}

/**
 * Count the number of changed lines in a unified diff.
 */
function countLinesInDiff(diff: string): number {
  const lines = diff.split('\n');
  let count = 0;
  
  for (const line of lines) {
    if (line.startsWith('+') || line.startsWith('-')) {
      // Don't count header lines like +++ or ---
      if (!line.startsWith('+++') && !line.startsWith('---')) {
        count++;
      }
    }
  }
  
  return count;
}

export async function activate(context: vscode.ExtensionContext) {
  // Initialize output channel
  outputChannel = vscode.window.createOutputChannel('Aspect Code');

  // Create status bar item immediately on activation (icon only)
  statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, -100);
  statusBarItem.command = "aspectcode.generateKB";
  statusBarItem.tooltip = "Regenerate Aspect Code Knowledge Base";
  statusBarItem.text = "$(beaker)";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Initialize state
  const state = new AspectCodeState(context);
  state.load();

  // Register panel provider
  const panelProvider = new AspectCodePanelProvider(context, state, outputChannel);
  (state as AspectCodeState & { _panelProvider?: AspectCodePanelProvider })._panelProvider = panelProvider;
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('aspectcode.panel', panelProvider, {
      webviewOptions: { retainContextWhenHidden: true }
    })
  );

  // Migrate project-scoped Aspect Code settings from .vscode/settings.json (if present)
  // into .aspect/.settings.json, and ensure reasonable defaults exist there.
  // IMPORTANT: Only write to .aspect/.settings.json if .aspect/ already exists.
  // We don't want to auto-create .aspect/ on extension startup - that should only
  // happen when user explicitly generates KB via '+' button.
  try {
    const root = await getWorkspaceRoot();
    if (root) {
      const rootUri = vscode.Uri.file(root);
      
      // Only migrate/set defaults if .aspect/ already exists
      const dirExists = await aspectDirExists(rootUri);
      if (dirExists) {
        await migrateAspectSettingsFromVSCode(rootUri, outputChannel);

        // Ensure a default autoRegenerateKb is present in .aspect/.settings.json.
        const settings = await readAspectSettings(rootUri);
        if (settings.autoRegenerateKb === undefined) {
          await setAutoRegenerateKbSetting(rootUri, 'onSave');
        }
      }
    }
  } catch (e) {
    outputChannel.appendLine(`[Settings] Failed to migrate project settings: ${e}`);
  }

  // Initialize workspace fingerprint for KB staleness detection
  const workspaceRoot = await getWorkspaceRoot();
  if (workspaceRoot) {
    // Initialize FileDiscoveryService singleton FIRST (used by other services)
    const workspaceRootUri = vscode.Uri.file(workspaceRoot);
    fileDiscoveryService = initFileDiscoveryService(workspaceRootUri, outputChannel);
    context.subscriptions.push({ dispose: () => disposeFileDiscoveryService() });
    outputChannel.appendLine('[Startup] FileDiscoveryService initialized');
    
    workspaceFingerprint = new WorkspaceFingerprint(workspaceRoot, EXTENSION_VERSION, outputChannel);
    context.subscriptions.push(workspaceFingerprint);

    // Initialize fingerprint service with project-local mode and keep it updated.
    try {
      const mode = await getAutoRegenerateKbSetting(vscode.Uri.file(workspaceRoot), outputChannel);
      workspaceFingerprint.setAutoRegenerateKbMode(mode);
    } catch {}

    // Use **/ glob pattern to match the settings file from the workspace root.
    const aspectSettingsWatcher = vscode.workspace.createFileSystemWatcher('**/.aspect/.settings.json');
    const refreshKbMode = () => {
      void (async () => {
        try {
          const mode = await getAutoRegenerateKbSetting(vscode.Uri.file(workspaceRoot), outputChannel);
          workspaceFingerprint?.setAutoRegenerateKbMode(mode);
        } catch {
          // Ignore
        }
      })();
    };
    aspectSettingsWatcher.onDidChange(refreshKbMode);
    aspectSettingsWatcher.onDidCreate(refreshKbMode);
    aspectSettingsWatcher.onDidDelete(() => {
      workspaceFingerprint?.setAutoRegenerateKbMode('onSave');
    });
    context.subscriptions.push(aspectSettingsWatcher);
    
    // Update panel when KB staleness changes
    workspaceFingerprint.onStaleStateChanged(stale => {
      panelProvider.setKbStale(stale);
    });
    
    // Set up KB regeneration callback for idle/onSave auto-regeneration
    workspaceFingerprint.setKbRegenerateCallback(async () => {
      try {
        const regenStart = Date.now();
        outputChannel.appendLine('[KB] Auto-regenerating KB...');

        // KB generation works offline (uses local dependency analysis)
        const { regenerateEverything } = await import('./assistants/kb');
        const result = await regenerateEverything(state, outputChannel, context);
        
        if (result.regenerated) {
          // Pass the discovered files to markKbFresh to avoid rediscovery
          await workspaceFingerprint?.markKbFresh(result.files);
          
          // Refresh dependency graph in panel
          panelProvider.refreshDependencyGraph();

          outputChannel.appendLine(`[KB] Auto-regeneration complete in ${Date.now() - regenStart}ms`);
        }
      } catch (e) {
        outputChannel.appendLine(`[KB] Auto-regeneration failed: ${e}`);
      }
    });
    
    // Check KB staleness on startup
    const isStale = await workspaceFingerprint.isKbStale();
    if (isStale) {
      outputChannel.appendLine('[Startup] KB may be stale - will auto-regenerate if configured');
    } else {
      outputChannel.appendLine('[Startup] KB is up to date');
    }
  }

  // ===== CORE Aspect Code COMMANDS =====
  // Note: Server-dependent commands removed.

  // Generate/refresh KB files (.aspect/*.md) based on current state.
  // Used by the panel “Regenerate KB” button.
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.generateKB', async () => {
      const rootUri = vscode.workspace.workspaceFolders?.[0]?.uri;
      if (!rootUri) {
        vscode.window.showWarningMessage('No workspace folder open.');
        return;
      }
      
      const enabled = await getExtensionEnabledSetting(rootUri);
      if (!enabled) {
        vscode.window.showInformationMessage('Aspect Code is disabled.', 'Enable').then((sel) => {
          if (sel === 'Enable') void vscode.commands.executeCommand('aspectcode.toggleExtensionEnabled');
        });
        return;
      }
      // Note: KB generation works offline

      try {
        const regenStart = Date.now();
        outputChannel?.appendLine('=== REGENERATE KB: Using regenerateEverything() ===');

        // Use the consolidated regenerateEverything function
        const { regenerateEverything } = await import('./assistants/kb');
        const result = await regenerateEverything(state, outputChannel!, context);
        
        if (result.regenerated) {
          // Mark KB as fresh after successful regeneration, reusing discovered files
          await workspaceFingerprint?.markKbFresh(result.files);

          outputChannel?.appendLine(`=== REGENERATE KB: Complete (${Date.now() - regenStart}ms) ===`);
          vscode.window.showInformationMessage('Knowledge base regenerated successfully.');
        } else {
          outputChannel?.appendLine('=== REGENERATE KB: Skipped (.aspect/ not yet created) ===');
          vscode.window.showInformationMessage('Knowledge base not yet initialized. Use the + button to create it.');
        }
      } catch (e) {
        outputChannel?.appendLine(`REGENERATE KB ERROR: ${e}`);
        vscode.window.showErrorMessage(`KB regeneration failed: ${e}`);
      }
    })
  );

  // Refresh dependency analysis caches and re-render the panel graph.
  // This is a purely local operation (no KB generation, no network).
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.forceReindex', async () => {
      try {
        panelProvider.invalidateDependencyCache();
        panelProvider.refreshDependencyGraph();
        vscode.window.showInformationMessage('Aspect Code: dependency graph refreshed.');
      } catch (e) {
        vscode.window.showErrorMessage(`Aspect Code: failed to refresh dependency graph: ${e}`);
      }
    })
  );

  // Copy a short impact summary for the current file to clipboard.
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.copyImpactAnalysisCurrentFile', async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage('No active file.');
        return;
      }

      const workspaceFolders = vscode.workspace.workspaceFolders;
      if (!workspaceFolders || workspaceFolders.length === 0) {
        vscode.window.showWarningMessage('No workspace folder open.');
        return;
      }

      const workspaceRoot = workspaceFolders[0].uri;
      const absPath = editor.document.uri.fsPath;

      const channel = outputChannel ?? vscode.window.createOutputChannel('Aspect Code');
      channel.appendLine(`[Impact] Computing impact for: ${absPath}`);

      const summary = await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: 'Aspect Code: Computing impact analysis...',
          cancellable: false
        },
        async () => computeImpactSummaryForFile(workspaceRoot, absPath, channel)
      );


      if (!summary) {
        vscode.window.showWarningMessage('Impact analysis unavailable. Try running “Aspect Code: Examine” first.');
        return;
      }

      const lines: string[] = [];
      lines.push('Aspect Code — Impact Analysis');
      lines.push(`File: ${summary.file}`);
      lines.push(`Dependents: ${summary.dependents_count}`);
      lines.push(`Hub risk: ${summary.hub_risk}`);
      if (summary.top_dependents.length > 0) {
        lines.push('Top dependents:');
        for (const dep of summary.top_dependents) {
          lines.push(`- ${dep.file} (${dep.dependent_count} dependents)`);
        }
      } else {
        lines.push('Top dependents: (none found)');
      }
      lines.push(`Generated: ${summary.generated_at}`);

      await vscode.env.clipboard.writeText(lines.join('\n'));
      vscode.window.showInformationMessage('Impact analysis copied to clipboard.');
    })
  );
  
  // Note: Server-dependent commands (showPanel, copyDebugInfo, forceReindex) removed.
  // Note: Aspect Code.openFinding command is now registered in newCommandsIntegration.ts

  // ===== EXTENSION SETUP =====
  outputChannel.appendLine('Aspect Code extension activated');
  
  // Load tree-sitter grammars for local parsing
  
  loadGrammarsOnce(context, outputChannel).then(() => {
    const summary = getLoadedGrammarsSummary();
    const statusParts = [];
    statusParts.push(`python=${summary.python ? 'OK' : 'MISSING'}`);
    statusParts.push(`typescript=${summary.typescript ? 'OK' : 'MISSING'}`);
    statusParts.push(`tsx=${summary.tsx ? 'OK' : 'MISSING'}`);
    statusParts.push(`javascript=${summary.javascript ? 'OK' : 'MISSING'}`);
    outputChannel.appendLine(`Tree-sitter loaded: ${statusParts.join(' ')}`);
  }).catch((error) => {
    outputChannel.appendLine(`Tree-sitter initialization failed: ${error}`);
  });

  const shouldTrackFileForKb = (filePath: string): boolean => {
    const ext = path.extname(filePath).toLowerCase();
    const sourceExtensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.java', '.cpp', '.c', '.cs', '.go', '.rs'];
    if (!sourceExtensions.includes(ext)) {
      return false;
    }

    const normalized = filePath.replace(/\\/g, '/').toLowerCase();
    // Avoid churn from common generated/vendor directories.
    const excludedSegments = [
      '/node_modules/', '/.git/', '/__pycache__/', '/.venv/', '/venv/',
      '/build/', '/dist/', '/target/', '/coverage/', '/.next/',
      '/.pytest_cache/', '/.mypy_cache/', '/.tox/', '/htmlcov/',
      '/.aspect/'
    ];
    return !excludedSegments.some(seg => normalized.includes(seg));
  };

  const isBulkEdit = (changes: readonly vscode.TextDocumentContentChangeEvent[]): boolean => {
    // Heuristic: LLM/apply-edit flows tend to apply large/compound edits.
    if (!changes || changes.length === 0) return false;
    if (changes.length >= 2) return true;

    const c = changes[0];
    const insertedLen = (c.text || '').length;
    const insertedLines = (c.text || '').split(/\r?\n/).length - 1;
    const replacedLen = c.rangeLength ?? 0;
    return insertedLen >= 200 || insertedLines >= 8 || replacedLen >= 400;
  };

  // Hook into file change events for KB staleness detection
  // Only track edits to mark KB as potentially stale (no server calls)
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument(async (event) => {
      const filePath = event.document.fileName;
      if (!shouldTrackFileForKb(filePath)) {
        return;
      }
      
      // Notify fingerprint service that a file was edited (for idle detection)
      if (event.contentChanges.length > 0) {
        workspaceFingerprint?.onFileEdited();

        // If autoRegenerateKb === 'onSave', also trigger regeneration for bulk edits
        // (common when an LLM applies a change), even if the editor isn't explicitly saved.
        const autoRegen = workspaceRoot ? await getAutoRegenerateKbSetting(vscode.Uri.file(workspaceRoot)) : 'onSave';
        if (autoRegen === 'onSave' && isBulkEdit(event.contentChanges)) {
          workspaceFingerprint?.onFileSaved(filePath);
        }
      }
    })
  );

  // Also mark stale on save (users expect this signal on save).
  // If autoRegenerateKb === 'onSave', this will trigger debounced KB regeneration.
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument((doc) => {
      const filePath = doc.fileName;
      if (!shouldTrackFileForKb(filePath)) {
        return;
      }
      workspaceFingerprint?.onFileSaved(filePath);
    })
  );

  // Also watch for on-disk changes (e.g., git revert/checkout, bulk updates) so
  // autoRegenerateKb='onSave' works even when files change outside normal saves.
  const kbFsWatcher = vscode.workspace.createFileSystemWatcher(
    '**/*.{py,ts,tsx,js,jsx,mjs,cjs,java,cpp,c,cs,go,rs}'
  );
  kbFsWatcher.onDidChange((uri) => {
    if (!shouldTrackFileForKb(uri.fsPath)) return;
    workspaceFingerprint?.onFileSaved(uri.fsPath);
  });
  kbFsWatcher.onDidCreate((uri) => {
    if (!shouldTrackFileForKb(uri.fsPath)) return;
    workspaceFingerprint?.onFileSaved(uri.fsPath);
  });
  kbFsWatcher.onDidDelete((uri) => {
    if (!shouldTrackFileForKb(uri.fsPath)) return;
    workspaceFingerprint?.onFileSaved(uri.fsPath);
  });
  context.subscriptions.push(kbFsWatcher);

  context.subscriptions.push(
    diag,
    outputChannel
  );
  const codeActionProvider: vscode.CodeActionProvider = {
    provideCodeActions(doc, range, ctx) {
      const actions: vscode.CodeAction[] = [];
      return actions;
    }
  };
  context.subscriptions.push(vscode.languages.registerCodeActionsProvider({ scheme: 'file', language: 'python' }, codeActionProvider));

  // Activate new JSON Protocol v1 commands
  activateNewCommands(context, state, outputChannel);
}

export function deactivate() {
  diag.dispose();
}
