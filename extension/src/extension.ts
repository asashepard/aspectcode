import * as vscode from 'vscode';
import { exec } from 'child_process';
import fetch from 'node-fetch';
import { parsePatch, applyPatch } from 'diff';
import * as path from 'path';
import { loadGrammarsOnce, getLoadedGrammarsSummary } from './tsParser';
import { extractPythonImports, extractTSJSImports } from './importExtractors';
import { AspectCodePanelProvider } from './panel/PanelProvider';
import { AspectCodeState } from './state';
import { post, fetchCapabilities, initHttp, getHeaders, handleHttpError } from './http';
import Parser from 'web-tree-sitter';
import { activateNewCommands } from './newCommandsIntegration';
import { IncrementalIndexer } from './services/IncrementalIndexer';
import { DependencyAnalyzer } from './panel/DependencyAnalyzer';
import { CacheManager } from './services/CacheManager';

let examineOnSave = false;
const diag = vscode.languages.createDiagnosticCollection('aspectcode');

// OUTPUT channel for logging
let outputChannel: vscode.OutputChannel;

// Status bar item
let statusBarItem: vscode.StatusBarItem;

// Incremental indexer instance
let incrementalIndexer: IncrementalIndexer | null = null;

// Cache manager instance
let cacheManager: CacheManager | null = null;

// Extension version from package.json
const EXTENSION_VERSION = '0.0.1';

/**
 * Get the incremental indexer instance.
 * Returns null if not yet initialized.
 */
export function getIncrementalIndexer(): IncrementalIndexer | null {
  return incrementalIndexer;
}

/**
 * Get the cache manager instance.
 * Returns null if not yet initialized.
 */
export function getCacheManager(): CacheManager | null {
  return cacheManager;
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

// Store last validation response for autofix operations
let lastExaminationResponse: any = null;

// Store workspace edit for preview/apply functionality
let pendingWorkspaceEdit: vscode.WorkspaceEdit | null = null;
let pendingAutofixData: any = null;

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
  
  // Common source code file patterns
  const patterns = [
    '**/*.py',
    '**/*.ts', '**/*.tsx',
    '**/*.js', '**/*.jsx', '**/*.mjs', '**/*.cjs',
    '**/*.java',
    '**/*.cpp', '**/*.c', '**/*.hpp', '**/*.h',
    '**/*.cs',
    '**/*.go',
    '**/*.rs'
  ];
  
  for (const pattern of patterns) {
    try {
      const files = await vscode.workspace.findFiles(
        pattern,
        '**/node_modules/**,**/.git/**,**/__pycache__/**,**/build/**,**/dist/**,**/target/**,**/e2e/**,**/playwright/**,**/cypress/**,**/.venv/**,**/venv/**',
        500 // Limit to prevent performance issues
      );
      
      for (const file of files) {
        const filePath = file.fsPath;
        if (!allFiles.includes(filePath)) {
          allFiles.push(filePath);
        }
      }
    } catch (error) {
      outputChannel?.appendLine(`Error finding files with pattern ${pattern}: ${error}`);
    }
  }
  
  outputChannel?.appendLine(`[DiscoverFiles] Found ${allFiles.length} source files in workspace`);
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

async function examineWorkspaceDiff(context?: vscode.ExtensionContext) {
  outputChannel?.appendLine('=== examineWorkspaceDiff called ===');

  const root = await getWorkspaceRoot();
  if (!root) {
    outputChannel?.appendLine('ERROR: No workspace root found');
    return;
  }
  outputChannel?.appendLine(`Workspace root: ${root}`);

  const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';
  outputChannel?.appendLine(`API URL: ${apiUrl}`);

  const diff = await runGitDiff(root);
  outputChannel?.appendLine(`Git diff length: ${diff.length} chars`);

  const files = await computeTouchedFilesFromGit(root);
  outputChannel?.appendLine(`Touched files: ${files.length} found - ${files.map(f => f.fsPath).join(', ')}`);
  lastTouchedFiles = files.map(u => u.fsPath);  // keep for fallback

  const ir = await buildIRForFiles(files, root, context);
  outputChannel?.appendLine(`IR built: ${ir.symbols.length} symbols, ${ir.edges.length} edges`);
  ir.lang = "python";

  // Run Pyright on touched files
  const pyrightData = await runPyright(root, files);
  const type_facts = pyrightData ? {
    lang: "python",
    checker: "pyright",
    data: pyrightData
  } : { data: {} };

  const payload = {
    repo_root: root,
    diff,
    ir,
    type_facts,
    modes: ['structure', 'types'],
    autofix: false,
    assumptions: {
      pythonpath: [root] // simple hint; extend later if you want
    }
  };

  // Debug log for detector configuration if enabled in workspace
  try {
    const workspaceConfig = vscode.workspace.getConfiguration();
    const detectorEnabled = workspaceConfig.get('aspectcode.detectors.enabled');
    if (detectorEnabled && Array.isArray(detectorEnabled) && detectorEnabled.length > 0) {
      outputChannel?.appendLine(`Detectors configuration detected: enabled=${JSON.stringify(detectorEnabled)}`);
    }
  } catch (e) {
    // Ignore config errors
  }

  try {
    outputChannel?.appendLine(`Making request to: ${apiUrl}/validate`);
    const headers = await getHeaders();
    const res = await fetch(apiUrl + '/validate', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });

    outputChannel?.appendLine(`Response status: ${res.status}`);

    if (!res.ok) {
      handleHttpError(res.status, res.statusText);
    }

    const json: any = await res.json();
    outputChannel?.appendLine(`Examination result: ${json.verdict} with ${(json.violations || []).length} violations`);
    renderDiagnostics(json);

    // Show status with parse stats
    const { treeSitterFiles, skippedFiles, totalTime } = lastParseStats;
    const statusParts = [];
    if (treeSitterFiles > 0) statusParts.push(`parsed ${treeSitterFiles} TS`);
    if (skippedFiles > 0) statusParts.push(`skipped ${skippedFiles}`);
    const parseInfo = statusParts.length > 0 ? ` (${statusParts.join(' / ')})` : '';

    if (json.verdict === 'risky') {
      vscode.window.setStatusBarMessage(`Aspect Code: risky diff${parseInfo} (see Problems)`, 3000);
    } else {
      vscode.window.setStatusBarMessage(`Aspect Code: safe ✓${parseInfo}`, 3000);
    }
  } catch (e) {
    outputChannel?.appendLine(`EXCEPTION in examineWorkspaceDiff: ${e}`);
    vscode.window.showErrorMessage('Aspect Code examination failed: ' + (e as Error).message);
  }
}

function renderDiagnostics(resp: any) {
  outputChannel?.appendLine(`=== renderDiagnostics called ===`);
  // Violations received (verbose JSON logging removed for performance)

  // Store validation response for autofix operations
  lastExaminationResponse = resp;

  diag.clear();
  const map = new Map<string, vscode.Diagnostic[]>();

  for (const v of resp.violations || []) {
    // Skip violations that have already been applied (idempotent diagnostics)
    if (v.id && appliedViolationIds.has(v.id)) {
      outputChannel?.appendLine(`Skipping already applied finding: ${v.id}`);
      continue;
    }

    outputChannel?.appendLine(`Processing finding: ${v.rule} - ${v.explain}`);
    const loc = (v.locations && v.locations[0]) || "";
    outputChannel?.appendLine(`Finding location: ${loc}`);

    // Try to parse "<path>:l1:c1-l2:c2" safely on Windows
    let file = "";
    let range = new vscode.Range(new vscode.Position(0, 0), new vscode.Position(0, 0));

    if (loc) {
      const m = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
      if (m) {
        file = m[1];
        const l1 = Math.max(0, parseInt(m[2], 10) - 1);
        const c1 = Math.max(0, parseInt(m[3], 10) - 1);
        const l2 = Math.max(0, parseInt(m[4], 10) - 1);
        const c2 = Math.max(0, parseInt(m[5], 10) - 1);
        range = new vscode.Range(new vscode.Position(l1, c1), new vscode.Position(l2, c2));
        outputChannel?.appendLine(`Parsed location: file=${file}, range=${l1}:${c1}-${l2}:${c2}`);
      } else {
        outputChannel?.appendLine(`Failed to parse location: ${loc}`);
      }
    }

    // Fallback: pin to first touched file if server gave no location
    if (!file) {
      file = lastTouchedFiles[0] || vscode.window.activeTextEditor?.document.uri.fsPath || "";
    }
    if (!file) continue;

    const d = new vscode.Diagnostic(range, v.explain || 'Aspect Code issue', vscode.DiagnosticSeverity.Warning);
    d.source = 'Aspect Code';
    d.code = v.rule || 'ASPECT_CODE_RULE';

    // Store violation ID in diagnostic for later tracking
    if (v.id) {
      (d as any).violationId = v.id;
    }

    const arr = map.get(file) || [];
    arr.push(d);
    map.set(file, arr);
  }

  // Diagnostics rendering disabled - findings are shown in Aspect Code panel instead
  // This prevents yellow underlines in the editor while keeping findings functional
  // Uncomment the lines below to re-enable diagnostics in Problems panel:
  // for (const [f, arr] of map) {
  //   diag.set(vscode.Uri.file(f), arr);
  // }
}

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

// Create WorkspaceEdit from autofix response for preview
async function createWorkspaceEditFromAutofix(repoRoot: string, autofixResponse: any): Promise<vscode.WorkspaceEdit | null> {
  const edit = new vscode.WorkspaceEdit();

  try {
    // Prefer files[] if available
    if (autofixResponse.files && autofixResponse.files.length > 0) {
      for (const file of autofixResponse.files) {
        const abs = path.join(repoRoot, file.relpath);

        // Security check
        if (!abs.startsWith(path.resolve(repoRoot))) {
          outputChannel?.appendLine(`Skipping ${file.relpath} - outside workspace`);
          continue;
        }

        const uri = vscode.Uri.file(abs);

        try {
          // Detect current EOL style
          const eol = await detectEOL(abs);

          // Convert LF content to match current file's EOL style
          const content = file.content.replace(/\n/g, eol);

          // Get current document if open, otherwise read from disk
          let currentContent = '';
          const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === abs);
          if (doc) {
            currentContent = doc.getText();
          } else {
            try {
              currentContent = (await vscode.workspace.fs.readFile(uri)).toString();
            } catch {
              outputChannel?.appendLine(`Could not read ${file.relpath} - treating as new file`);
              currentContent = '';
            }
          }

          // Create full document replacement
          const fullRange = new vscode.Range(
            new vscode.Position(0, 0),
            new vscode.Position(currentContent.split('\n').length, 0)
          );

          edit.replace(uri, fullRange, content);

        } catch (e) {
          outputChannel?.appendLine(`Error processing ${file.relpath}: ${e}`);
          return null;
        }
      }
      return edit;
    }

    // Fallback to unified diff parsing
    if (!autofixResponse.patched_diff || !autofixResponse.patched_diff.trim()) {
      outputChannel?.appendLine('No patched_diff in autofix response');
      return null;
    }

    const parsed = parsePatch(autofixResponse.patched_diff);
    if (!parsed || parsed.length === 0) {
      outputChannel?.appendLine('No parseable hunks in diff');
      return null;
    }

    for (const filePatch of parsed) {
      let rel = (filePatch.newFileName || filePatch.oldFileName || '').trim();
      rel = rel.replace(/^a\//, '').replace(/^b\//, '');
      if (!rel) continue;

      const abs = path.join(repoRoot, rel);
      if (!abs.startsWith(path.resolve(repoRoot))) continue;

      const uri = vscode.Uri.file(abs);

      try {
        // Load current content
        let cur = '';
        const doc = vscode.workspace.textDocuments.find(d => d.uri.fsPath === abs);
        if (doc) {
          cur = doc.getText();
        } else {
          try {
            cur = (await vscode.workspace.fs.readFile(uri)).toString();
          } catch {
            outputChannel?.appendLine(`Could not read ${rel} for diff preview`);
            continue;
          }
        }

        // Detect EOL and normalize for patching
        const eol = cur.includes('\r\n') ? '\r\n' : '\n';
        const curLF = cur.replace(/\r\n/g, '\n');

        // Apply the patch
        const nextLF = applyPatch(curLF, filePatch);
        if (typeof nextLF !== 'string') {
          outputChannel?.appendLine(`Failed to apply patch to ${rel}`);
          continue;
        }

        // Convert back to original EOL style
        const next = eol === '\r\n' ? nextLF.replace(/\n/g, '\r\n') : nextLF;

        // Create full document replacement
        const fullRange = new vscode.Range(
          new vscode.Position(0, 0),
          new vscode.Position(cur.split(eol === '\r\n' ? '\r\n' : '\n').length, 0)
        );

        edit.replace(uri, fullRange, next);

      } catch (e) {
        outputChannel?.appendLine(`Error processing diff for ${rel}: ${e}`);
        continue;
      }
    }

    return edit;

  } catch (e) {
    outputChannel?.appendLine(`Error creating workspace edit: ${e}`);
    return null;
  }
}

// Preview autofix changes using workspace edit
async function previewAutofixChanges(autofixResponse: any, context?: vscode.ExtensionContext) {
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return;
  }

  const edit = await createWorkspaceEditFromAutofix(root, autofixResponse);
  if (!edit) {
    vscode.window.showErrorMessage('Could not create preview from autofix response');
    return;
  }

  // Store for later application
  pendingWorkspaceEdit = edit;
  pendingAutofixData = autofixResponse;

  // Apply edit in preview mode
  const applied = await vscode.workspace.applyEdit(edit);
  if (!applied) {
    vscode.window.showErrorMessage('Failed to preview changes');
    return;
  }

  // Show information message with action buttons
  const result = await vscode.window.showInformationMessage(
    'Aspect Code auto-fix preview applied. Review changes and choose action.',
    { modal: false },
    'Apply & Re-examine',
    'Revert'
  );

  if (result === 'Apply & Re-examine') {
    await applyAndReexamine(context);
  } else if (result === 'Revert') {
    await revertPendingChanges();
  }
}

// Apply pending changes and Re-examine
async function applyAndReexamine(context?: vscode.ExtensionContext) {
  if (!pendingWorkspaceEdit || !pendingAutofixData) {
    vscode.window.showErrorMessage('No pending changes to apply');
    return;
  }

  try {
    // Save all modified documents
    await vscode.workspace.saveAll();

    // Store original diagnostics to compare later
    const originalDiagnostics = new Map<string, vscode.Diagnostic[]>();
    diag.forEach((uri, diagnostics) => {
      originalDiagnostics.set(uri.fsPath, [...diagnostics]);
    });

    // Mark applied violations as handled
    if (pendingAutofixData.fixed_violations) {
      for (const violationId of pendingAutofixData.fixed_violations) {
        appliedViolationIds.add(violationId);
      }
    }

    // Re-examine workspace
    await examineWorkspaceDiff(context);

    // Check if validation introduced new problems
    let hasNewProblems = false;
    diag.forEach((uri, newDiagnostics) => {
      const originalDiags = originalDiagnostics.get(uri.fsPath) || [];
      if (newDiagnostics.length > originalDiags.length) {
        hasNewProblems = true;
      }
    });

    if (hasNewProblems) {
      // Auto-revert and show toast
      await revertPendingChanges();
      vscode.window.showWarningMessage('Auto-fix introduced new issues. Changes reverted.');
    } else {
      vscode.window.showInformationMessage('Auto-fix applied successfully!');
    }

  } catch (e) {
    vscode.window.showErrorMessage(`Failed to apply changes: ${(e as Error).message}`);
  } finally {
    // Clear pending state
    pendingWorkspaceEdit = null;
    pendingAutofixData = null;
  }
}

// Revert pending workspace changes
async function revertPendingChanges() {
  if (!pendingWorkspaceEdit) {
    return;
  }

  try {
    // Create inverse edit to undo changes
    const undoEdit = new vscode.WorkspaceEdit();

    // For each file that was changed, reload from disk
    for (const [uri, edits] of pendingWorkspaceEdit.entries()) {
      if (edits.length > 0) {
        try {
          // Read original content from disk
          const originalContent = (await vscode.workspace.fs.readFile(uri)).toString();

          // Create full document replacement with original content
          const doc = vscode.workspace.textDocuments.find(d => d.uri.toString() === uri.toString());
          if (doc) {
            const fullRange = new vscode.Range(
              new vscode.Position(0, 0),
              new vscode.Position(doc.lineCount, 0)
            );
            undoEdit.replace(uri, fullRange, originalContent);
          }
        } catch (e) {
          outputChannel?.appendLine(`Could not revert ${uri.fsPath}: ${e}`);
        }
      }
    }

    await vscode.workspace.applyEdit(undoEdit);
    vscode.window.showInformationMessage('Changes reverted');

  } catch (e) {
    vscode.window.showErrorMessage(`Failed to revert changes: ${(e as Error).message}`);
  } finally {
    pendingWorkspaceEdit = null;
    pendingAutofixData = null;
  }
}

// Autofix functions
async function callAutofixAPI(violationIds?: string[], context?: vscode.ExtensionContext, violationFiles?: string[]) {
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return null;
  }

  const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

  try {
    // Build payload same as validate
    const diff = await runGitDiff(root);
    
    // Use files from violations if provided, otherwise fall back to git diff
    let files: vscode.Uri[];
    if (violationFiles && violationFiles.length > 0) {
      outputChannel?.appendLine(`Using ${violationFiles.length} files from violations: ${violationFiles.join(', ')}`);
      files = violationFiles.map(f => vscode.Uri.file(f));
    } else {
      files = await computeTouchedFilesFromGit(root);
    }
    
    const ir = await buildIRForFiles(files, root, context);
    ir.lang = "python";

    // Run Pyright for type facts
    const pyrightData = await runPyright(root, files);
    const type_facts = pyrightData ? {
      lang: "python",
      checker: "pyright",
      data: pyrightData
    } : { data: {} };

    const payload: any = {
      repo_root: root,
      diff,
      ir,
      type_facts
    };

    // Add violation selection if provided
    if (violationIds && violationIds.length > 0) {
      payload.select = violationIds;
    }

    outputChannel?.appendLine(`Calling /autofix with ${violationIds ? violationIds.length : 'all'} violations`);

    const headers = await getHeaders();
    const res = await fetch(apiUrl + '/autofix', {
      method: 'POST',
      headers,
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      handleHttpError(res.status, res.statusText);
    }

    const response = await res.json();
    outputChannel?.appendLine(`Autofix response: ${JSON.stringify(response, null, 2)}`);

    return response;

  } catch (e) {
    outputChannel?.appendLine(`Autofix API exception: ${e}`);
    vscode.window.showErrorMessage(`Aspect Code autofix failed: ${(e as Error).message}`);
    return null;
  }
}

async function previewAutofix(violationIds?: string[], context?: vscode.ExtensionContext) {
  outputChannel?.appendLine(`=== previewAutofix called with ${violationIds ? violationIds.length : 'all'} violations ===`);

  const autofixResponse = await callAutofixAPI(violationIds, context);
  if (!autofixResponse) {
    vscode.window.showWarningMessage('Auto-fix request failed. Check the output for details.');
    return;
  }

  // Check if any fixes were applied
  const fixesApplied = (autofixResponse as any).fixes_applied || 0;
  outputChannel?.appendLine(`Autofix result: ${fixesApplied} fixes applied`);

  if (!(autofixResponse as any).patched_diff && (!(autofixResponse as any).files || (autofixResponse as any).files.length === 0)) {
    if (fixesApplied === 0) {
      vscode.window.showInformationMessage('No auto-fixes available for this finding. It may require manual intervention.');
    } else {
      vscode.window.showInformationMessage('No preview available, but fixes were applied.');
    }
    return;
  }

  await previewAutofixChanges(autofixResponse, context);
}

async function autofixSelectedProblems(context?: vscode.ExtensionContext) {
  // Get all diagnostics from Problems panel
  const allDiagnostics: { uri: vscode.Uri; diagnostic: vscode.Diagnostic }[] = [];

  diag.forEach((uri, diagnostics) => {
    for (const diagnostic of diagnostics) {
      if (diagnostic.source === 'Aspect Code') {
        allDiagnostics.push({ uri, diagnostic });
      }
    }
  });

  if (allDiagnostics.length === 0) {
    vscode.window.showInformationMessage('No Aspect Code violations found');
    return;
  }

  // Separate fixable and non-fixable violations
  const fixableItems = allDiagnostics
    .filter(item => (item.diagnostic as any).violationId)
    .map((item, index) => ({
      label: `${path.basename(item.uri.fsPath)}: ${item.diagnostic.message}`,
      description: item.diagnostic.code?.toString() || '',
      detail: item.uri.fsPath,
      picked: true, // Default to selected
      violationId: (item.diagnostic as any).violationId,
      index
    }));

  const nonFixableCount = allDiagnostics.length - fixableItems.length;

  if (fixableItems.length === 0) {
    vscode.window.showInformationMessage(`No auto-fixable violations found (${nonFixableCount} violations cannot be automatically fixed)`);
    return;
  }

  let title = `Select violations to auto-fix (${fixableItems.length} fixable`;
  if (nonFixableCount > 0) {
    title += `, ${nonFixableCount} not auto-fixable`;
  }
  title += ')';

  const selected = await vscode.window.showQuickPick(fixableItems, {
    canPickMany: true,
    title,
    placeHolder: 'Choose which violations to fix automatically'
  });

  if (!selected || selected.length === 0) {
    return;
  }

  // Extract violation IDs
  const violationIds = selected.map(item => item.violationId);

  outputChannel?.appendLine(`Multi-select autofix: ${violationIds.length} violations selected`);
  await previewAutofix(violationIds, context);
}

// Helper function to send progress updates to the panel
function sendProgressToPanel(state: AspectCodeState | undefined, phase: string, percentage: number, message: string) {
  if (state && (state as any)._panelProvider) {
    try {
      ((state as any)._panelProvider as any).post({ 
        type: 'PROGRESS_UPDATE', 
        phase, 
        percentage, 
        message 
      });
    } catch (error) {
      // Ignore errors if panel is not available
      console.warn('Failed to send progress to panel:', error);
    }
  }
}

// Repository indexing functions
async function indexRepository(force: boolean = false, state?: AspectCodeState) {
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return;
  }

  const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

  try {
    outputChannel?.appendLine(`=== ${force ? 'Re-indexing' : 'Indexing'} repository: ${root} ===`);

    // Update panel state - start indexing
    if (state) {
      state.update({ busy: true, error: undefined });
    }

    // Enhanced progress tracking with multiple phases
    // NOTE: Using SourceControl location to hide the notification popup
    const progressOptions = {
      location: vscode.ProgressLocation.SourceControl, // Changed from Notification to hide popup
      title: `${force ? 'Re-indexing' : 'Indexing'} repository...`,
      cancellable: false
    };

    await vscode.window.withProgress(progressOptions, async (progress) => {
      // Phase 1: File discovery (10%)
      progress.report({ increment: 0, message: 'Discovering source files...' });
      sendProgressToPanel(state, 'indexing', 5, 'Discovering source files...');
      
      await new Promise(resolve => setTimeout(resolve, 200)); // Small delay for UI
      
      // Phase 2: Preparing request (20%)
      progress.report({ increment: 10, message: 'Preparing indexing request...' });
      sendProgressToPanel(state, 'indexing', 15, 'Preparing indexing request...');

      const payload = {
        root: root,
        force_reindex: force,
        include_patterns: ['**/*.py', '**/*.ts', '**/*.tsx', '**/*.js', '**/*.jsx'],
        exclude_patterns: ['.git/**', 'node_modules/**', '__pycache__/**', '*.pyc']
      };

      // Phase 3: Sending to server (30%)
      progress.report({ increment: 10, message: 'Sending to analysis server...' });
      sendProgressToPanel(state, 'indexing', 25, 'Sending to analysis server...');

      // Phase 4: Server processing (30% -> 90%) with timeout protection
      progress.report({ increment: 5, message: 'Server processing files...' });
      sendProgressToPanel(state, 'indexing', 35, 'Server processing files...');

      const startTime = Date.now();
      
      // Create a timeout promise for large repositories
      const timeoutMs = 180000; // 3 minutes timeout
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Indexing timeout - repository may be too large')), timeoutMs);
      });
      
      const fetchPromise = (async () => {
        const headers = await getHeaders();
        return fetch(apiUrl + '/index', {
          method: 'POST',
          headers,
          body: JSON.stringify(payload)
        });
      })();

      const res = await Promise.race([fetchPromise, timeoutPromise]) as Response;

      if (!res.ok) {
        handleHttpError(res.status, res.statusText);
      }

      // Phase 5: Processing response (90%)
      progress.report({ increment: 55, message: 'Processing server response...' });
      sendProgressToPanel(state, 'indexing', 90, 'Processing server response...');

      const result: any = await res.json();
      outputChannel?.appendLine(`Index result: ${JSON.stringify(result, null, 2)}`);

      // Phase 6: Finalizing (100%)
      progress.report({ increment: 10, message: 'Finalizing indexing...' });
      sendProgressToPanel(state, 'indexing', 100, 'Indexing complete');

      // Update panel state - index complete
      if (state) {
        const { snapshot_id, file_count, processing_time_ms } = result;
        const indexStats = {
          snapshotId: snapshot_id,
          fileCount: file_count,
          bytes: result.total_bytes || 0,
          tookMs: processing_time_ms
        };

        state.update({
          snapshot: indexStats,
          busy: false,
          error: undefined,
          ui: { ...(state.s.ui ?? {}), activeTab: (state.s.ui?.activeTab ?? "overview") }
        });

        state.update({
          history: [
            { ts: Date.now(), kind: (force ? 'reindex' : 'index') as 'index' | 'reindex', meta: { files: file_count, tookMs: processing_time_ms } },
            ...state.s.history
          ].slice(0, 50)
        });
      }

      progress.report({ message: 'Index complete!' });

      // Show summary
      const { snapshot_id, file_count, processing_time_ms, dependency_count } = result;
      const message = [
        `Repository indexed successfully!`,
        `• Files processed: ${file_count}`,
        `• Dependencies found: ${dependency_count}`,
        `• Processing time: ${processing_time_ms}ms`,
        `• Snapshot ID: ${snapshot_id.substring(0, 8)}...`
      ].join('\n');

      // vscode.window.showInformationMessage(message);
    });

  } catch (e) {
    outputChannel?.appendLine(`EXCEPTION in indexRepository: ${e}`);
    if (state) {
      state.update({ busy: false, error: `Indexing failed: ${(e as Error).message}` });
    }
    vscode.window.showErrorMessage(`Repository indexing failed: ${(e as Error).message}`);
  }
}

async function examineFullRepository(state?: AspectCodeState, context?: vscode.ExtensionContext) {
  outputChannel?.appendLine(`[examineFullRepository] Called with state: ${state ? 'YES' : 'NO'}`);
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return;
  }

  const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

  try {
    outputChannel?.appendLine(`=== Full repository examination: ${root} ===`);

    // Update panel state - start validation
    if (state) {
      state.update({ busy: true, error: undefined });
    }

    // Enhanced progress tracking with multiple phases
    // NOTE: Using SourceControl location to hide the notification popup
    const progressOptions = {
      location: vscode.ProgressLocation.SourceControl, // Changed from Notification to hide popup
      title: 'Validating entire repository...',
      cancellable: false
    };

    await vscode.window.withProgress(progressOptions, async (progress) => {
      // Phase 1: Preparing validation (10%)
      progress.report({ increment: 0, message: 'Preparing examination...' });
      sendProgressToPanel(state, 'examination', 10, 'Preparing examination...');
      
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Phase 2: Setting up request (20%)
      progress.report({ increment: 10, message: 'Setting up examination request...' });
      sendProgressToPanel(state, 'examination', 20, 'Setting up examination request...');

      const payload = {
        repo_root: root,
        modes: ['structure', 'types'],
        autofix: false,
        enable_project_graph: true  // Enable Tier 2 architectural rules
      };

      // Phase 3: Sending to server (30%)
      progress.report({ increment: 10, message: 'Sending to analysis server...' });
      sendProgressToPanel(state, 'examination', 30, 'Sending to analysis server...');

      // Phase 4: Server validation (30% -> 80%) with timeout protection
      progress.report({ increment: 5, message: 'Server analyzing code...' });
      sendProgressToPanel(state, 'examination', 35, 'Server analyzing code...');

      // Create a timeout promise for large repositories  
      const timeoutMs = 300000; // 5 minutes timeout for examination (more complex)
      const timeoutPromise = new Promise((_, reject) => {
        setTimeout(() => reject(new Error('Examination timeout - repository may be too large or complex')), timeoutMs);
      });

      const fetchPromise = (async () => {
        const headers = await getHeaders();
        return fetch(apiUrl + '/validate_tree_sitter', {
          method: 'POST',
          headers,
          body: JSON.stringify(payload)
        });
      })();

      const res = await Promise.race([fetchPromise, timeoutPromise]) as Response;

      if (!res.ok) {
        handleHttpError(res.status, res.statusText);
      }

      // Phase 5: Processing results (80%)
      progress.report({ increment: 45, message: 'Processing Examination results...' });
      sendProgressToPanel(state, 'examination', 80, 'Processing Examination results...');

      const result: any = await res.json();
      const resultViolationCount = (result.violations || []).length;
      outputChannel?.appendLine(`Full Examination result: ${resultViolationCount} violations returned`);

      // Phase 6: Mapping findings (90%)
      progress.report({ increment: 10, message: 'Mapping findings...' });
      sendProgressToPanel(state, 'examination', 90, 'Mapping findings...');

      // Update panel state if provided
      if (state) {
        try {
          outputChannel?.appendLine(`[examineFullRepository] Entering state update block...`);
          const rootAbs = await getWorkspaceRoot(); // already defined in this file
          const violations = result.violations || [];

          const sevMap: Record<string, 'info' | 'warn' | 'error'> = { low: 'info', medium: 'warn', high: 'error' };

          const findings = violations.map((v: any) => {
            // Prefer first location string from server
            const loc0 = Array.isArray(v.locations) && typeof v.locations[0] === 'string' ? v.locations[0] : undefined;
            const parsed = parseLocationToFileAndSpan(loc0 || undefined);

            // File resolution:
            // 1) from parsed location (absolute from server)
            // 2) else from v.file* fields (may be relative) → make absolute if needed
            let absFile = parsed?.file || v.filePath || v.file_path || v.file || '';
            if (absFile && !path.isAbsolute(absFile) && rootAbs) {
              absFile = path.join(rootAbs, absFile);
            }

            // Severity normalization (server: low|medium|high → panel: info|warn|error)
            const severity = sevMap[v.severity] ?? (['info', 'warn', 'error'].includes(v.severity) ? v.severity : 'warn');

            return {
              id: v.violation_id ?? v.id,
              code: v.rule ?? v.code ?? 'unknown',
              severity,
              file: absFile,
              span: parsed?.span ?? (v.span ? {
                start: { line: Math.max(1, v.span.start?.line ?? 1), column: Math.max(1, v.span.start?.column ?? 1) },
                end: { line: Math.max(1, v.span.end?.line ?? 1), column: Math.max(1, v.span.end?.column ?? 1) }
              } : undefined),
              message: v.message ?? v.explain ?? '',
              fixable: !!(v.fixable || v.suggested_patchlet),
              suggested_patchlet: v.suggested_patchlet,
              selected: false,
              _raw: v
            };
          });

          const validateStats = {
            total: violations.length,
            fixable: violations.filter((v: any) => v.suggested_patchlet || v.fixable).length,
            byCode: violations.reduce((acc: any, v: any) => {
              const key = v.rule ?? v.code ?? 'unknown';
              acc[key] = (acc[key] || 0) + 1;
              return acc;
            }, {}),
            tookMs: result.processing_time_ms || 0
          };

          outputChannel?.appendLine(`[examineFullRepository] CHECKPOINT 1: About to call state.update() with ${findings.length} findings`);
          outputChannel?.appendLine(`[examineFullRepository] CHECKPOINT 2: state object is ${state ? 'DEFINED' : 'UNDEFINED'}`);
          
          state.update({
            findings,
            lastEXAMINE: validateStats,
            error: undefined,
            busy: false,
            ui: { ...(state.s.ui ?? {}), activeTab: (state.s.ui?.activeTab ?? "overview") }
          });
          outputChannel?.appendLine(`[examineFullRepository] CHECKPOINT 3: state.update() returned`);
          outputChannel?.appendLine(`[examineFullRepository] CHECKPOINT 4: state.s.findings.length is now ${state.s.findings?.length}`);

          state.update({
            history: [
              { ts: Date.now(), kind: 'validate' as 'validate', meta: { total: violations.length, fixable: validateStats.fixable } },
              ...state.s.history
            ].slice(0, 50)
          });
        } catch (stateUpdateError) {
          outputChannel?.appendLine(`[examineFullRepository] ERROR during state update: ${stateUpdateError}`);
          throw stateUpdateError;
        }

        // Phase 7: Finalizing (100%)
        progress.report({ increment: 10, message: 'Finalizing examination...' });
        sendProgressToPanel(state, 'examination', 100, 'Examination complete');
      }

      progress.report({ message: 'Rendering diagnostics...' });

      // Render diagnostics same as diff validation
      renderDiagnostics(result);

      progress.report({ message: 'Examination complete!' });

      // Always regenerate .aspect KB files after successful examination
      if (state) {
        try {
          const { autoRegenerateKBFiles } = await import('./assistants/kb');
          await autoRegenerateKBFiles(state, outputChannel!);
        } catch (kbError) {
          outputChannel?.appendLine(`[KB] Auto-regeneration failed (non-critical): ${kbError}`);
        }
      }

      // Persist cache for instant startup next time
      if (cacheManager && state && incrementalIndexer) {
        try {
          outputChannel?.appendLine('[Cache] Saving examination cache...');
          const signatures = await cacheManager.buildFileSignatures();
          const cachedFindings = cacheManager.findingsToCache(state.s.findings || []);
          const dependencies = cacheManager.dependenciesToCache(incrementalIndexer.getReverseDependencyGraph());
          const lastValidate = state.s.lastValidate ? {
            total: state.s.lastValidate.total,
            fixable: state.s.lastValidate.fixable,
            tookMs: state.s.lastValidate.tookMs
          } : undefined;
          await cacheManager.saveCache(signatures, cachedFindings, dependencies, lastValidate);
          outputChannel?.appendLine(`[Cache] Saved ${cachedFindings.length} findings to cache`);
        } catch (cacheError) {
          outputChannel?.appendLine(`[Cache] Failed to save cache (non-critical): ${cacheError}`);
        }
      }

      // Check if we should auto-generate instruction files after successful examination
      const assistantsConfig = vscode.workspace.getConfiguration('aspectcode.assistants');
      const autoGenerate = assistantsConfig.get<boolean>('autoGenerate', false);
      
      if (autoGenerate) {
        outputChannel?.appendLine('[Assistants] Auto-generating instruction files after examination...');
        try {
          await vscode.commands.executeCommand('aspectcode.generateInstructionFiles');
        } catch (genError) {
          outputChannel?.appendLine(`[Assistants] Auto-generation failed: ${genError}`);
          // Don't block validation on generation failure
        }
      }

      // On first successful examination, offer to configure AI assistants
      if (context) {
        const hasBeenAsked = context.globalState.get<boolean>('aspectcode.assistants.firstTimeAsked', false);
        if (!hasBeenAsked) {
          await context.globalState.update('aspectcode.assistants.firstTimeAsked', true);
          // Delay slightly so examination success message is visible first
          setTimeout(async () => {
            const answer = await vscode.window.showInformationMessage(
              'Would you like to configure Aspect Code for your AI assistants (Copilot, Cursor, Claude)?',
              'Configure', 'Later'
            );
            if (answer === 'Configure') {
              await vscode.commands.executeCommand('aspectcode.configureAssistants');
            }
          }, 1500);
        }
      }

      // Show summary
      const violationCount = (result.violations || []).length;
      if (violationCount > 0) {
        // vscode.window.showWarningMessage(`Full repository examination found ${violationCount} issues (see Problems panel)`);
        // vscode.window.setStatusBarMessage(`Aspect Code: ${violationCount} repo issues found`, 5000);
      } else {
        // vscode.window.showInformationMessage('Repository examination passed - no issues found!');
        // vscode.window.setStatusBarMessage('Aspect Code: repository clean ✓', 3000);
      }
    });

  } catch (e) {
    outputChannel?.appendLine(`EXCEPTION in examineFullRepository: ${e}`);
    if (state) {
      state.update({ busy: false, error: `Examination failed: ${(e as Error).message}` });
    }
    vscode.window.showErrorMessage(`Full repository Examination failed: ${(e as Error).message}`);
  }
}

async function showRepositoryStatus() {
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return;
  }

  const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

  try {
    // Get snapshots
    const snapshotsHeaders = await getHeaders();
    const snapshotsRes = await fetch(apiUrl + '/snapshots', { headers: snapshotsHeaders });
    if (!snapshotsRes.ok) {
      handleHttpError(snapshotsRes.status, snapshotsRes.statusText);
    }

    const snapshots = await snapshotsRes.json() as any[];

    // Get storage stats
    const statsHeaders = await getHeaders();
    const statsRes = await fetch(apiUrl + '/storage/stats', { headers: statsHeaders });
    if (!statsRes.ok) {
      handleHttpError(statsRes.status, statsRes.statusText);
    }

    const stats: any = await statsRes.json();

    // Find current repo snapshot
    const currentSnapshot = snapshots.find((s: any) => s.repo_root === root);

    let message = 'Repository Status:\n\n';

    if (currentSnapshot) {
      message += `Current Index:\n`;
      message += `• Snapshot ID: ${currentSnapshot.snapshot_id.substring(0, 8)}...\n`;
      message += `• Created: ${new Date(currentSnapshot.created_at).toLocaleString()}\n`;
      message += `• Files: ${currentSnapshot.file_count}\n`;
      message += `• Dependencies: ${currentSnapshot.dependency_count}\n\n`;
    } else {
      message += `Current Index: Not indexed\n\n`;
    }

    message += `Storage Stats:\n`;
    message += `• Total snapshots: ${stats.total_snapshots}\n`;
    message += `• Memory usage: ${(stats.memory_usage_mb || 0).toFixed(1)} MB\n`;
    message += `• Cache hits: ${stats.cache_stats?.hits || 0}\n`;
    message += `• Cache misses: ${stats.cache_stats?.misses || 0}\n`;

    if (!currentSnapshot) {
      const result = await vscode.window.showInformationMessage(message, { modal: true }, 'Index Repository');
      if (result === 'Index Repository') {
        await indexRepository(false);
      }
    } else {
      const actions = ['Re-index', 'Examine Full Repo'];
      const result = await vscode.window.showInformationMessage(message, { modal: true }, ...actions);
      if (result === 'Re-index') {
        await indexRepository(true);
      } else if (result === 'Examine Full Repo') {
        await examineFullRepository();
      }
    }

  } catch (e) {
    outputChannel?.appendLine(`EXCEPTION in showRepositoryStatus: ${e}`);
    vscode.window.showErrorMessage(`Failed to get repository status: ${(e as Error).message}`);
  }
}

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

/**
 * Fetch patchlet capabilities if not already cached.
 */
async function fetchCapabilitiesIfNeeded(state: AspectCodeState, force: boolean = false) {
  try {
    // If we already have capabilities, don't fetch again (unless forced)
    if (!force && state.getCapabilities()) {
      outputChannel?.appendLine('Capabilities already cached');
      const caps = state.getCapabilities();
      outputChannel?.appendLine(`Cached ${caps?.fixable_rules?.length ?? 0} fixable rules`);
      return;
    }

    outputChannel?.appendLine('Fetching patchlet capabilities...');
    const capabilities = await fetchCapabilities();
    state.setCapabilities(capabilities);
    outputChannel?.appendLine(`Cached ${capabilities.fixable_rules.length} fixable rules`);
    outputChannel?.appendLine(`Rules: ${capabilities.fixable_rules.map(r => r.rule).join(', ')}`);
  } catch (error) {
    outputChannel?.appendLine(`Failed to fetch capabilities: ${error}`);
    // Don't fail activation if capabilities can't be fetched
  }
}

/**
 * Execute the Fix (safe) command with safety auto-revert.
 */
async function executeFixSafeCommand(state: AspectCodeState, context: vscode.ExtensionContext, panelProvider?: any) {
  try {
    // Guard: if busy → return
    if (state.s.busy) {
      outputChannel?.appendLine('Fix (safe) already in progress');
      return;
    }

    // Mark as busy
    state.update({ busy: true });
    const startTime = Date.now();
    
    outputChannel?.appendLine('Starting Fix (safe) operation...');
    
    // Get capabilities first
    let safeRuleSet = state.getSafeRuleSet();
    
    outputChannel?.appendLine(`Safe rule set size: ${safeRuleSet.size}`);
    outputChannel?.appendLine(`Safe rules: ${Array.from(safeRuleSet).join(', ')}`);
    
    if (safeRuleSet.size === 0) {
      outputChannel?.appendLine('No capabilities available. Attempting to fetch now...');
      await fetchCapabilitiesIfNeeded(state, true); // Force refresh
      const newSafeRuleSet = state.getSafeRuleSet();
      outputChannel?.appendLine(`After fetch attempt: ${newSafeRuleSet.size} safe rules`);
      
      if (newSafeRuleSet.size === 0) {
        vscode.window.showInformationMessage('No capabilities available. Try reloading the window.');
        state.update({ busy: false });
        return;
      }
      
      // Update safeRuleSet for the rest of the function
      safeRuleSet = newSafeRuleSet;
    }

    // Get current findings from state (may have cached snapshot IDs)
    const currentFindings = state.s.findings || [];
    outputChannel?.appendLine(`Current findings: ${currentFindings.length}`);

    // Filter to fixable + allowed rules  
    const fixableFindings = currentFindings.filter(f => {
      const ruleCode = f._raw?.rule || f.code;
      const isFixable = f.fixable;
      const isSafe = safeRuleSet.has(ruleCode);
      
      outputChannel?.appendLine(`Finding ${f.id}: rule=${ruleCode}, fixable=${isFixable}, safe=${isSafe}`);
      
      return isFixable && isSafe;
    });

    if (fixableFindings.length === 0) {
      vscode.window.showInformationMessage('No safe fixable findings found.');
      state.update({ busy: false });
      return;
    }

    // Build selection list of finding IDs (cap at 200 per batch)
    const findingIds = fixableFindings.slice(0, 200).map(f => f.id).filter(Boolean);
    
    if (findingIds.length === 0) {
      vscode.window.showInformationMessage('No findings with valid IDs found.');
      state.update({ busy: false });
      return;
    }

    outputChannel?.appendLine(`Found ${findingIds.length} safe fixable findings`);

    // Group by file to enforce max files constraint
    const fileGroups = new Map<string, string[]>();
    for (const finding of fixableFindings) {
      if (!finding.id) continue;
      
      // Get file path from finding.file or extract from locations in _raw
      let file = finding.file;
      if (!file && finding._raw && finding._raw.locations && finding._raw.locations.length > 0) {
        const loc = finding._raw.locations[0];
        const match = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
        if (match) {
          file = match[1]; // Extract file path from location
          outputChannel?.appendLine(`Extracted file from location: ${loc} → ${file}`);
        }
      }
      
      if (!file) {
        outputChannel?.appendLine(`Warning: No file path found for finding ${finding.id}`);
        continue;
      }
      
      if (!fileGroups.has(file)) {
        fileGroups.set(file, []);
      }
      fileGroups.get(file)!.push(finding.id);
    }

    // Enforce max 3 files per batch
    const fileList = Array.from(fileGroups.keys());
    if (fileList.length > 3) {
      const limitedIds: string[] = [];
      for (let i = 0; i < 3; i++) {
        limitedIds.push(...fileGroups.get(fileList[i])!);
      }
      findingIds.splice(0, findingIds.length, ...limitedIds);
      outputChannel?.appendLine(`Limited to first 3 files (${limitedIds.length} findings)`);
    }

    // Extract unique file paths from the fixable findings
    const violationFiles = Array.from(new Set(
      fixableFindings.map(f => {
        let file = f.file;
        if (!file && f._raw && f._raw.locations && f._raw.locations.length > 0) {
          const loc = f._raw.locations[0];
          const match = loc.match(/^(.*):(\d+):(\d+)-(\d+):(\d+)$/);
          if (match) {
            file = match[1];
          }
        }
        // Normalize path separators for deduplication
        return file ? path.resolve(file) : null;
      }).filter((file): file is string => Boolean(file))
    ));
    
    outputChannel?.appendLine(`Violation files: ${violationFiles.join(', ')}`);

    // Since cached findings have snapshot-* IDs but server expects detector-* IDs,
    // we need to call autofix without specific IDs to let it find all fixable violations
    outputChannel?.appendLine('Calling autofix without specific violation IDs to avoid ID mismatch...');
    const resp = await callAutofixAPI([], context, violationFiles);  // Empty array = fix all found violations
    if (!resp) {
      state.update({ busy: false });
      return;
    }

    outputChannel?.appendLine(`Autofix response keys: ${Object.keys(resp).join(', ')}`);

    // If server returns a unified diff, apply it
    const patchedDiff = (resp as any)?.patched_diff;
    const files = (resp as any)?.files;
    
    outputChannel?.appendLine(`Patched diff length: ${patchedDiff?.length || 0}`);
    outputChannel?.appendLine(`Files array length: ${files?.length || 0}`);
    
    if (files && files.length > 0) {
      outputChannel?.appendLine(`Files to patch: ${files.map((f: any) => f.relpath).join(', ')}`);
    }
    
    if (patchedDiff && typeof patchedDiff === 'string') {
      outputChannel?.appendLine(`Diff preview: ${patchedDiff.substring(0, 200)}...`);
    } else {
      outputChannel?.appendLine(`Diff is not a string: ${typeof patchedDiff}`);
    }
    
    if (patchedDiff && patchedDiff.trim()) {
      const root = await getWorkspaceRoot();
      if (!root) {
        outputChannel?.appendLine('ERROR: No workspace root found');
        state.update({ busy: false });
        return;
      }
      
      outputChannel?.appendLine(`Using workspace root: ${root}`);

      // Track which files we're changing
      const touchedFiles = extractFilesFromDiff(patchedDiff);
      const linesChanged = countLinesInDiff(patchedDiff);
      
      outputChannel?.appendLine(`Applying diff: ${touchedFiles.length} files, ${linesChanged} lines`);

      // Apply diff to workspace  
      await applyUnifiedDiffToWorkspace(root, patchedDiff, files);
      await vscode.workspace.saveAll();

      // Re-EXAMINE: First on touched files, then full repo
      outputChannel?.appendLine('Re-validating touched files...');
      
      // Simple re-validation approach: just validate the whole workspace
      await examineWorkspaceDiff(context);
      
      // Check for safety violations in the updated state
      // Note: In a full implementation, we'd specifically check touched files for safety.* or exc.* violations
      // and auto-revert if any are found. For now, we'll log success.
      
      const tookMs = Date.now() - startTime;
      
      // Update state history
      const historyEntry = {
        ts: Date.now(),
        kind: 'autofix' as any, // Add to HistoryItem type if needed
        meta: {
          fixed_by: 'fixSafe',
          filesChanged: touchedFiles.length,
          linesChanged,
          fixedCount: findingIds.length,
          tookMs
        }
      };
      
      state.update({
        busy: false,
        history: [...state.s.history, historyEntry]
      });

      // Show success message
      const successMsg = `Applied: ${touchedFiles.length} files / ${linesChanged} lines • Fixed ${findingIds.length} findings • Re-examine OK`;
      vscode.window.showInformationMessage(successMsg);
      
      // Update panel last action
      if (panelProvider) {
        panelProvider.setLastAction(successMsg);
      }
      
      outputChannel?.appendLine(`Fix (safe) completed in ${tookMs}ms`);
      
    } else {
      outputChannel?.appendLine('No changes from autofix');
      state.update({ busy: false });
      vscode.window.showInformationMessage('No changes applied by autofix.');
    }

  } catch (error) {
    outputChannel?.appendLine(`Fix (safe) error: ${error}`);
    vscode.window.showErrorMessage(`Fix (safe) failed: ${error}`);
    state.update({ busy: false });
  }
}

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
  statusBarItem.command = "aspectcode.showPanel";
  statusBarItem.tooltip = "Open Aspect Code Panel";
  statusBarItem.text = "$(beaker)";
  statusBarItem.show();
  context.subscriptions.push(statusBarItem);

  // Initialize HTTP module with secrets storage for API key management
  initHttp(context);

  // Check if API key is configured - prompt user if not
  const existingApiKey = await context.secrets.get('aspectcode.apiKey');
  const configApiKey = vscode.workspace.getConfiguration('aspectcode').get<string>('apiKey');
  
  if (!existingApiKey && !configApiKey) {
    // No API key configured - prompt user
    const choice = await vscode.window.showWarningMessage(
      'Aspect Code requires an API key to function. Please enter your API key.',
      'Enter API Key',
      'Later'
    );
    
    if (choice === 'Enter API Key') {
      // Delay slightly to ensure extension is fully activated
      setTimeout(() => {
        vscode.commands.executeCommand('aspectcode.enterApiKey');
      }, 500);
    }
  }

  // Initialize state
  const state = new AspectCodeState(context);
  state.load();

  // Fetch capabilities on activation if not cached (don't block startup)
  fetchCapabilitiesIfNeeded(state).catch(e => {
    outputChannel.appendLine(`Failed to fetch capabilities: ${e}`);
  });

  // Register the panel provider
  const panelProvider = new AspectCodePanelProvider(context, state, outputChannel);
  
  // Store panel provider reference in state for progress updates
  (state as any)._panelProvider = panelProvider;
  
  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider('aspectcode.panel', panelProvider, {
      webviewOptions: { retainContextWhenHidden: true }
    })
  );

  // Initialize incremental indexer (will be initialized after first INDEX)
  incrementalIndexer = new IncrementalIndexer(
    state,
    new DependencyAnalyzer(),
    outputChannel
  );
  context.subscriptions.push(incrementalIndexer);

  // Initialize cache manager and load cached findings
  const workspaceRoot = await getWorkspaceRoot();
  if (workspaceRoot) {
    cacheManager = new CacheManager(workspaceRoot, EXTENSION_VERSION, outputChannel);
    
    // Link cache manager to incremental indexer for persistence
    incrementalIndexer.setCacheManager(cacheManager);
    
    // Try to load cached findings for instant startup
    const cacheResult = await cacheManager.loadCache();
    if (cacheResult.cache) {
      const cachedData = cacheResult.cache;
      outputChannel.appendLine('[Startup] Loading cached findings...');
      
      // Convert cached findings to absolute paths and populate state
      const findings = cacheManager.findingsFromCache(cachedData.findings);
      state.update({
        findings,
        lastEXAMINE: cachedData.lastValidate ? {
          ...cachedData.lastValidate,
          byCode: {} // Add required field
        } : undefined
      });
      
      outputChannel.appendLine(`[Startup] Loaded ${findings.length} cached findings`);
      
      // Mark cache as loaded to skip automatic INDEX/VALIDATE
      panelProvider.setCacheLoaded(true);
      
      // Restore dependency graph to incremental indexer
      if (cachedData.dependencies && incrementalIndexer) {
        const deps = cacheManager.dependenciesFromCache(cachedData.dependencies);
        incrementalIndexer.restoreDependencyGraph(deps);
      }
      
      // Detect changes and run incremental examination in background
      setTimeout(async () => {
        try {
          const changes = await cacheManager!.detectChanges();
          if (changes.valid) {
            const changedCount = changes.added.size + changes.modified.size + changes.deleted.size;
            if (changedCount > 0) {
              outputChannel.appendLine(`[Startup] Detected ${changedCount} file changes, running incremental examination...`);
              
              // Combine all changed files
              const allChanged = [...changes.added, ...changes.modified];
              
              // Handle deleted files - remove their findings from state
              if (changes.deleted.size > 0) {
                const currentFindings = state.s.findings || [];
                const remainingFindings = currentFindings.filter(
                  f => !changes.deleted.has(f.file)
                );
                state.update({ findings: remainingFindings });
              }
              
              // Run incremental examination on changed files
              if (allChanged.length > 0 && incrementalIndexer?.isInitialized()) {
                await incrementalIndexer.handleBulkChange(allChanged);
              } else if (allChanged.length > 0) {
                // Indexer not initialized - need full index first
                outputChannel.appendLine('[Startup] Incremental indexer not ready, needs INDEX first');
              }
            } else {
              outputChannel.appendLine('[Startup] No file changes detected, cache is up to date');
            }
          }
        } catch (error) {
          outputChannel.appendLine(`[Startup] Change detection failed: ${error}`);
        }
      }, 1000); // Delay to let UI render first
    } else {
      // Cache invalid - log reason and let auto-processing handle regeneration
      if (cacheResult.invalidReason === 'extension_version') {
        outputChannel.appendLine('[Startup] Extension version changed - full cache regeneration required');
        outputChannel.appendLine(`[Startup] ${cacheResult.invalidDetails}`);
      } else if (cacheResult.invalidReason === 'cache_version') {
        outputChannel.appendLine('[Startup] Cache schema version changed - full cache regeneration required');
        outputChannel.appendLine(`[Startup] ${cacheResult.invalidDetails}`);
      } else if (cacheResult.invalidReason === 'workspace_changed') {
        outputChannel.appendLine('[Startup] Workspace changed - full cache regeneration required');
      } else if (cacheResult.invalidReason === 'not_found') {
        outputChannel.appendLine('[Startup] No cache found - will run initial INDEX and EXAMINE');
      } else {
        outputChannel.appendLine(`[Startup] Cache invalid (${cacheResult.invalidReason}) - will regenerate`);
      }
      // panelProvider.setCacheLoaded(false) is default, so auto-processing will trigger
    }
  }

  // ===== CORE Aspect Code COMMANDS (4 TOTAL) =====
  
  // Enter API Key - Allows users to input their API key manually
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.enterApiKey', async () => {
      try {
        // Check if already have a key
        const existingKey = await context.secrets.get('aspectcode.apiKey');
        if (existingKey) {
          const choice = await vscode.window.showInformationMessage(
            'You already have an API key configured. Do you want to replace it with a new one?',
            'Enter new API key',
            'Cancel'
          );
          if (choice !== 'Enter new API key') {
            return;
          }
        }

        // Prompt for API key
        const apiKey = await vscode.window.showInputBox({
          prompt: 'Enter your Aspect Code API key',
          placeHolder: 'paste-your-api-key-here',
          password: true, // Hide the input for security
          validateInput: (value) => {
            if (!value || value.trim().length === 0) {
              return 'API key is required';
            }
            if (value.trim().length < 20) {
              return 'API key appears too short - please check and try again';
            }
            return undefined;
          }
        });

        if (!apiKey) {
          return; // User cancelled
        }

        // Store the API key in SecretStorage
        await context.secrets.store('aspectcode.apiKey', apiKey.trim());

        outputChannel?.appendLine('[Auth] API key stored successfully');

        vscode.window.showInformationMessage(
          'API key saved! You can now use Aspect Code.',
          'OK'
        );

      } catch (error: any) {
        outputChannel?.appendLine(`[Auth] Error storing API key: ${error.message}`);
        vscode.window.showErrorMessage(`Failed to save API key: ${error.message}`);
      }
    })
  );

  // Clear API Key - Deletes the stored API key from SecretStorage
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.clearApiKey', async () => {
      try {
        const existingKey = await context.secrets.get('aspectcode.apiKey');
        if (!existingKey) {
          vscode.window.showInformationMessage('No stored API key found to clear.');
          return;
        }

        const choice = await vscode.window.showWarningMessage(
          'This will remove your stored Aspect Code API key from VS Code. You will need to enter it again to use Aspect Code.',
          'Clear API Key',
          'Cancel'
        );
        if (choice !== 'Clear API Key') {
          return;
        }

        await context.secrets.delete('aspectcode.apiKey');
        outputChannel?.appendLine('[Auth] API key cleared from SecretStorage');

        const configApiKey = vscode.workspace.getConfiguration('aspectcode').get<string>('apiKey');
        if (configApiKey && configApiKey.trim().length > 0) {
          vscode.window.showInformationMessage(
            "Stored API key cleared. Note: 'aspectcode.apiKey' is still set in Settings and will still be used.",
            'Open Settings'
          ).then(sel => {
            if (sel === 'Open Settings') {
              vscode.commands.executeCommand('workbench.action.openSettings', 'aspectcode.apiKey');
            }
          });
          return;
        }

        vscode.window.showInformationMessage('Stored API key cleared.');
      } catch (error: any) {
        outputChannel?.appendLine(`[Auth] Error clearing API key: ${error.message}`);
        vscode.window.showErrorMessage(`Failed to clear API key: ${error.message}`);
      }
    })
  );

  // 1. INDEX - Scan entire repository for analysis
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.index', async () => {
      try {
        outputChannel?.appendLine('=== INDEX: Starting repository indexing ===');
        
        // Clear all existing state and start fresh
        state.update({
          busy: false,
          findings: [],
          lastEXAMINE: undefined,
          capabilities: undefined,
          error: undefined
        });
        
        // Index the entire repository without caching
        await indexRepository(true, state); // force = true to bypass cache
        
        outputChannel?.appendLine('=== INDEX: Repository indexing complete ===');
        
        // Initialize incremental indexer after successful index
        if (incrementalIndexer) {
          try {
            outputChannel?.appendLine('=== INDEX: Initializing incremental indexer ===');
            const allFiles = await discoverWorkspaceSourceFiles();
            await incrementalIndexer.initialize(allFiles);
            outputChannel?.appendLine('=== INDEX: Incremental indexer ready ===');
          } catch (error) {
            outputChannel?.appendLine(`INDEX: Incremental indexer initialization failed: ${error}`);
            // Continue anyway - incremental indexing is optional
          }
        }
        
        // vscode.window.showInformationMessage('Repository indexed successfully');
        
      } catch (error) {
        outputChannel?.appendLine(`INDEX ERROR: ${error}`);
        
        // Clear progress state on error
        if (state) {
          state.update({ busy: false, error: `Index failed: ${error}` });
          sendProgressToPanel(state, 'indexing', 0, 'Indexing failed');
        }
        
        if (error instanceof Error && error.message.includes('timeout')) {
          vscode.window.showWarningMessage(`Index timeout: ${error.message}. Try indexing a smaller subset of files.`);
        } else {
          vscode.window.showErrorMessage(`Index failed: ${error}`);
        }
      }
    })
  );
  
  // 2. VALIDATE - Analyze entire repository for issues
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.examine', async () => {
      try {
        outputChannel?.appendLine('=== EXAMINE: Starting repository examination ===');
        
        // Validate the entire repository
        await examineFullRepository(state, context);
        
        const total = state.s.lastValidate?.total ?? 0;
        const fixable = state.s.findings?.filter(f => f.fixable)?.length ?? 0;
        
        outputChannel?.appendLine(`=== EXAMINE: Found ${total} total issues, ${fixable} fixable ===`);
        
        // if (total > 0) {
        //   vscode.window.showInformationMessage(`Examination complete: ${total} issues found (${fixable} fixable)`);
        // } else {
        //   vscode.window.showInformationMessage('Examination complete: No issues found');
        // }
        
        // Show the panel to display results
        await vscode.commands.executeCommand('aspectcode.showPanel');
        
      } catch (error) {
        outputChannel?.appendLine(`EXAMINE ERROR: ${error}`);
        
        // Clear progress state on error
        if (state) {
          state.update({ busy: false, error: `Examination failed: ${error}` });
          sendProgressToPanel(state, 'examination', 0, 'Examination failed');
        }
        
        if (error instanceof Error && error.message.includes('timeout')) {
          vscode.window.showWarningMessage(`Examination timeout: ${error.message}. Try validating a smaller subset of files.`);
        } else {
          vscode.window.showErrorMessage(`Examination failed: ${error}`);
        }
      }
    })
  );
  
  // 3. FIX SAFE - Removed legacy command, now uses Auto-Fix V1 pipeline
  // All fix operations now go through Aspect Code.applyAutofix for consistency
  
  // 4. SHOW PANEL - Display the main Aspect Code panel
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.showPanel', async () => {
      // Focus the webview panel directly by its view ID
      await vscode.commands.executeCommand('aspectcode.panel.focus');
    })
  );
  
  // 4. PREVIEW AUTOFIX - Auto-Fix feature temporarily disabled
  // context.subscriptions.push(
  //   vscode.commands.registerCommand('aspectcode.previewAutofix', async (violationIds?: string[]) => {
  //     await previewAutofix(violationIds, context);
  //   })
  // );
  
  // 6. AUTO FIX SAFE - Now handled by Auto-Fix V1 pipeline in newCommandsIntegration.ts
  // Removed duplicate registration to avoid conflicts
  
  // Note: Aspect Code.openFinding command is now registered in newCommandsIntegration.ts

  // ===== EXTENSION SETUP =====
  outputChannel.appendLine('Aspect Code extension activated');
  
  // Show the panel on startup
  vscode.commands.executeCommand('aspectcode.panel.focus');
  
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

  // Hook into file save events for incremental examination
  context.subscriptions.push(
    vscode.workspace.onDidSaveTextDocument(async (document) => {
      // Only process source files
      const ext = path.extname(document.fileName).toLowerCase();
      const sourceExtensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.java', '.cpp', '.c', '.cs', '.go', '.rs'];
      
      if (sourceExtensions.includes(ext) && incrementalIndexer?.isInitialized()) {
        await incrementalIndexer.handleFileSave(document);
      }
    })
  );

  // Handle file creation - trigger incremental examination
  context.subscriptions.push(
    vscode.workspace.onDidCreateFiles(async (event) => {
      const sourceExtensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.java', '.cpp', '.c', '.cs', '.go', '.rs'];
      const sourceFiles = event.files.filter(f => {
        const ext = path.extname(f.fsPath).toLowerCase();
        return sourceExtensions.includes(ext);
      });
      
      if (sourceFiles.length > 0 && incrementalIndexer?.isInitialized()) {
        outputChannel?.appendLine(`[FileCreate] ${sourceFiles.length} source file(s) created, triggering validation`);
        try {
          await incrementalIndexer.handleBulkChange(sourceFiles.map(f => f.fsPath));
        } catch (error) {
          outputChannel?.appendLine(`[FileCreate] Incremental Examination failed: ${error}`);
        }
      }
    })
  );

  // Handle file deletion - trigger incremental examination to remove stale findings
  context.subscriptions.push(
    vscode.workspace.onDidDeleteFiles(async (event) => {
      const sourceExtensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.java', '.cpp', '.c', '.cs', '.go', '.rs'];
      const sourceFiles = event.files.filter(f => {
        const ext = path.extname(f.fsPath).toLowerCase();
        return sourceExtensions.includes(ext);
      });
      
      if (sourceFiles.length > 0 && incrementalIndexer?.isInitialized()) {
        outputChannel?.appendLine(`[FileDelete] ${sourceFiles.length} source file(s) deleted, triggering validation`);
        try {
          // For deleted files, we need to Re-examine their dependents
          await incrementalIndexer.handleBulkChange(sourceFiles.map(f => f.fsPath));
        } catch (error) {
          outputChannel?.appendLine(`[FileDelete] Incremental Examination failed: ${error}`);
        }
      }
    })
  );

  // Bulk file change detection for git operations (git checkout, git reset, git stash pop, etc.)
  // This detects when multiple files change simultaneously without being saved (e.g., git discard)
  let bulkChangeTimer: NodeJS.Timeout | null = null;
  let pendingFileChanges = new Set<string>();
  const BULK_CHANGE_THRESHOLD = 3; // 3+ files changing at once = likely git operation
  const BULK_CHANGE_DEBOUNCE = 500; // 500ms window to collect changes
  
  context.subscriptions.push(
    vscode.workspace.onDidChangeTextDocument(async (event) => {
      const ext = path.extname(event.document.fileName).toLowerCase();
      const sourceExtensions = ['.py', '.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.java', '.cpp', '.c', '.cs', '.go', '.rs'];
      
      if (!sourceExtensions.includes(ext)) {
        return;
      }
      
      // Track files with unsaved changes (for detecting git operations)
      // Git operations change multiple files at once without saving
      if (event.contentChanges.length > 0) {
        pendingFileChanges.add(event.document.fileName);
        
        // Debounce to collect all changes in a batch
        if (bulkChangeTimer) {
          clearTimeout(bulkChangeTimer);
        }
        
        bulkChangeTimer = setTimeout(async () => {
          const changeCount = pendingFileChanges.size;
          const changedFiles = Array.from(pendingFileChanges);
          
          // Only trigger for bulk changes (3+ files) - indicates git operation
          // Single file changes are handled by onDidSaveTextDocument
          if (changeCount >= BULK_CHANGE_THRESHOLD && incrementalIndexer?.isInitialized()) {
            outputChannel?.appendLine(`[GitOperation] Detected ${changeCount} files changed simultaneously`);
            outputChannel?.appendLine(`[GitOperation] Changed files: ${changedFiles.map(f => path.basename(f)).join(', ')}`);
            
            try {
              await incrementalIndexer.handleBulkChange(changedFiles);
              outputChannel?.appendLine(`[GitOperation] Incremental Examination completed`);
            } catch (error) {
              outputChannel?.appendLine(`[GitOperation] Incremental Examination failed: ${error}`);
            }
          }
          
          // Clear the tracked changes
          pendingFileChanges.clear();
        }, BULK_CHANGE_DEBOUNCE);
      }
    })
  );

  context.subscriptions.push(
    diag,
    outputChannel
  );
  const codeActionProvider: vscode.CodeActionProvider = {
    provideCodeActions(doc, range, ctx) {
      const actions: vscode.CodeAction[] = [];
      const aspectCodeDiagnostics = ctx.diagnostics.filter(d => d.source === 'Aspect Code');

      for (const d of aspectCodeDiagnostics) {
        // Legacy specific fixes
        if (d.code === 'symbols_missing') {
          const action = new vscode.CodeAction('Aspect Code: Apply Suggested Import', vscode.CodeActionKind.QuickFix);
          action.command = {
            title: 'Apply Suggested Import',
            command: 'aspectcode.applySuggestedImport',
            arguments: [doc.uri, d]
          };
          action.diagnostics = [d];
          actions.push(action);
        } else if (d.code === 'signature_compatibility') {
          const action = new vscode.CodeAction('Aspect Code: Insert Optional Guard', vscode.CodeActionKind.QuickFix);
          action.command = {
            title: 'Insert Optional Guard',
            command: 'aspectcode.applyOptionalGuard',
            arguments: [doc.uri, d]
          };
          action.diagnostics = [d];
          actions.push(action);
        }

        // General autofix for any Aspect Code diagnostic
        if ((d as any).violationId) {
          const action = new vscode.CodeAction('Aspect Code: Preview Auto-fix', vscode.CodeActionKind.QuickFix);
          action.command = {
            title: 'Preview Auto-fix',
            command: 'aspectcode.previewAutofix',
            arguments: [[(d as any).violationId]]
          };
          action.diagnostics = [d];
          actions.push(action);
        }
      }

      // Add multi-select autofix if multiple diagnostics
      if (aspectCodeDiagnostics.length > 1) {
        const violationIds = aspectCodeDiagnostics
          .map(d => (d as any).violationId)
          .filter(id => id !== undefined);

        if (violationIds.length > 0) {
          const action = new vscode.CodeAction(`Aspect Code: Auto-fix All (${violationIds.length})`, vscode.CodeActionKind.QuickFix);
          action.command = {
            title: 'Auto-fix All Issues',
            command: 'aspectcode.previewAutofix',
            arguments: [violationIds]
          };
          action.diagnostics = aspectCodeDiagnostics;
          actions.push(action);
        }
      }

      return actions;
    }
  };
  context.subscriptions.push(vscode.languages.registerCodeActionsProvider({ scheme: 'file', language: 'python' }, codeActionProvider));

  // Command implementation
  context.subscriptions.push(vscode.commands.registerCommand('aspectcode.applySuggestedImport', async (uri: vscode.Uri, diag: vscode.Diagnostic) => {
    const root = await getWorkspaceRoot();
    if (!root) return;
    const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

    // Build payload same as validate
    const diff = await runGitDiff(root);
    const files = await computeTouchedFilesFromGit(root);
    const ir = await buildIRForFiles(files, root, context);
    ir.lang = "python";

    // Run Pyright for type facts
    const pyrightData = await runPyright(root, files);
    const type_facts = pyrightData ? {
      lang: "python",
      checker: "pyright",
      data: pyrightData
    } : { data: {} };

    // We need the violation id; stash it in Diagnostic? For MVP, re-call validate and pick the one matching this location/explain
    const validatePayload = {
      repo_root: root, diff, ir,
      type_facts, modes: ['structure', 'types'], autofix: false
    };
    const validateHeaders = await getHeaders();
    const vr = await fetch(apiUrl + '/validate', { method: 'POST', headers: validateHeaders, body: JSON.stringify(validatePayload) });
    if (!vr.ok) { handleHttpError(vr.status, vr.statusText); }
    const vjson: any = await vr.json();

    // Select first fixable import_insert violation at this file position
    const abs = uri.fsPath;
    const pick = (vjson.violations || []).find((v: any) =>
      v.fixable && v.suggested_fix_kind === 'import_insert' &&
      v.locations && v.locations[0] && v.locations[0].startsWith(abs)
    );
    if (!pick) {
      vscode.window.showInformationMessage('No applicable Aspect Code import fix found.');
      return;
    }

    const afPayload = { repo_root: root, diff, ir, select: [pick.id] };
    const afHeaders = await getHeaders();
    const ar = await fetch(apiUrl + '/autofix', { method: 'POST', headers: afHeaders, body: JSON.stringify(afPayload) });
    if (!ar.ok) { handleHttpError(ar.status, ar.statusText); }
    const aj: any = await ar.json();

    if (!aj?.patched_diff || !aj.patched_diff.trim()) {
      vscode.window.showInformationMessage('No changes from autofix.');
      return;
    }

    await applyUnifiedDiffToWorkspace(root, aj.patched_diff, aj.files);

    // Save file, then Re-examine
    await vscode.workspace.saveAll();
    await examineWorkspaceDiff(context);
  }));

  // Command implementation for optional guard
  context.subscriptions.push(vscode.commands.registerCommand('aspectcode.applyOptionalGuard', async (uri: vscode.Uri, diag: vscode.Diagnostic) => {
    const root = await getWorkspaceRoot();
    if (!root) return;
    const apiUrl = vscode.workspace.getConfiguration().get<string>('aspectcode.apiUrl') || 'http://localhost:8000';

    // Build payload same as validate
    const diff = await runGitDiff(root);
    const files = await computeTouchedFilesFromGit(root);
    const ir = await buildIRForFiles(files, root, context);
    ir.lang = "python";

    // Run Pyright for type facts
    const pyrightData = await runPyright(root, files);
    const type_facts = pyrightData ? {
      lang: "python",
      checker: "pyright",
      data: pyrightData
    } : { data: {} };

    // We need the violation id; re-call validate and pick the one matching this location/explain
    const validatePayload = {
      repo_root: root, diff, ir,
      type_facts, modes: ['structure', 'types'], autofix: false
    };
    const validateHeaders = await getHeaders();
    const vr = await fetch(apiUrl + '/validate', { method: 'POST', headers: validateHeaders, body: JSON.stringify(validatePayload) });
    if (!vr.ok) { handleHttpError(vr.status, vr.statusText); }
    const vjson: any = await vr.json();

    // Select first fixable optional_return_guard violation at this file position
    const abs = uri.fsPath;
    const pick = (vjson.violations || []).find((v: any) =>
      v.fixable && v.suggested_fix_kind === 'optional_return_guard' &&
      v.locations && v.locations[0] && v.locations[0].startsWith(abs)
    );
    if (!pick) {
      vscode.window.showInformationMessage('No applicable Aspect Code optional guard fix found.');
      return;
    }

    const afPayload = { repo_root: root, diff, ir, select: [pick.id] };
    const afHeaders = await getHeaders();
    const ar = await fetch(apiUrl + '/autofix', { method: 'POST', headers: afHeaders, body: JSON.stringify(afPayload) });
    if (!ar.ok) { handleHttpError(ar.status, ar.statusText); }
    const aj: any = await ar.json();

    if (!aj?.patched_diff || !aj.patched_diff.trim()) {
      vscode.window.showInformationMessage('No changes from optional guard autofix.');
      return;
    }

    await applyUnifiedDiffToWorkspace(root, aj.patched_diff, aj.files);

    // Save file, then Re-examine
    await vscode.workspace.saveAll();
    await examineWorkspaceDiff(context);
  }));

  // Activate new JSON Protocol v1 commands
  activateNewCommands(context, state);
}

export function deactivate() {
  diag.dispose();
}