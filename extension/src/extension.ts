import * as vscode from 'vscode';
import { exec } from 'child_process';
import fetch from 'node-fetch';
import { parsePatch, applyPatch } from 'diff';
import * as path from 'path';
import { loadGrammarsOnce, getLoadedGrammarsSummary } from './tsParser';
import { extractPythonImports, extractTSJSImports } from './importExtractors';
import { AspectCodePanelProvider } from './panel/PanelProvider';
import { AspectCodeState } from './state';
import { post, fetchCapabilities, handleHttpError, hasApiKeyConfigured, isApiKeyBlocked, initHttp, getHeaders, getBaseUrl, resetApiKeyAuthStatus } from './http';
import Parser from 'web-tree-sitter';
import { activateNewCommands } from './newCommandsIntegration';
import { WorkspaceFingerprint } from './services/WorkspaceFingerprint';
import { computeImpactSummaryForFile } from './assistants/kb';
import { getAssistantsSettings, getAutoRegenerateKbSetting, migrateAspectSettingsFromVSCode, readAspectSettings, setAutoRegenerateKbSetting, getExtensionEnabledSetting, aspectDirExists } from './services/aspectSettings';
import { getEnablementCancellationToken } from './services/enablementCancellation';
import { initFileDiscoveryService, disposeFileDiscoveryService, type FileDiscoveryService } from './services/FileDiscoveryService';

// --- Type Definitions for API Responses ---

/** Extended vscode.Diagnostic with violation tracking */
interface AspectCodeDiagnostic extends vscode.Diagnostic {
  violationId?: string;
}

/** Snapshot info from the server */
interface SnapshotInfo {
  snapshot_id: string;
  repo_root: string;
  created_at: string;
  file_count: number;
}

/** Storage stats from the server */
interface StorageStats {
  total_bytes?: number;
  snapshot_count?: number;
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

async function examineWorkspaceDiff(context?: vscode.ExtensionContext) {
  outputChannel?.appendLine('=== examineWorkspaceDiff called ===');

  const root = await getWorkspaceRoot();
  if (!root) {
    outputChannel?.appendLine('ERROR: No workspace root found');
    return;
  }
  outputChannel?.appendLine(`Workspace root: ${root}`);

  const apiUrl = getBaseUrl();
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

    const d: AspectCodeDiagnostic = new vscode.Diagnostic(range, v.explain || 'Aspect Code issue', vscode.DiagnosticSeverity.Warning);
    d.source = 'Aspect Code';
    d.code = v.rule || 'ASPECT_CODE_RULE';

    // Store violation ID in diagnostic for later tracking
    if (v.id) {
      d.violationId = v.id;
    }

    const arr = map.get(file) || [];
    arr.push(d);
    map.set(file, arr);
  }
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

// Helper function to send progress updates to the panel
function sendProgressToPanel(state: AspectCodeState | undefined, phase: string, percentage: number, message: string) {
  const panelProvider = (state as AspectCodeState & { _panelProvider?: AspectCodePanelProvider })?._panelProvider;
  if (panelProvider) {
    try {
      panelProvider.post({ 
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

async function examineFullRepository(
  state?: AspectCodeState,
  context?: vscode.ExtensionContext,
  modesOverride?: string[]
) {
  outputChannel?.appendLine(`[examineFullRepository] Called with state: ${state ? 'YES' : 'NO'}`);
  
  // Check if API key is available - if not, skip server validation but still regenerate KB
  const hasKey = await hasApiKeyConfigured();
  if (!hasKey || isApiKeyBlocked()) {
    outputChannel?.appendLine('[examineFullRepository] No API key configured - skipping server validation, regenerating KB only');
    
    // Still regenerate KB (works offline)
    if (state) {
      try {
        const { regenerateEverything } = await import('./assistants/kb');
        const result = await regenerateEverything(state, outputChannel!, context);
        if (workspaceFingerprint && result.regenerated) {
          // Pass discovered files to avoid rediscovery
          await workspaceFingerprint.markKbFresh(result.files);
        }
      } catch (kbError) {
        outputChannel?.appendLine(`[KB] Regeneration failed: ${kbError}`);
      }
      state.update({ busy: false });
    }
    return;
  }
  
  const perfEnabled = vscode.workspace.getConfiguration().get<boolean>('aspectcode.devLogs', true);
  const root = await getWorkspaceRoot();
  if (!root) {
    vscode.window.showErrorMessage('No workspace root found');
    return;
  }

  // Respect the project-local enable/disable switch.
  try {
    const enabled = await getExtensionEnabledSetting(vscode.Uri.file(root));
    if (!enabled) {
      if (state) state.update({ busy: false });
      return;
    }
  } catch {
    // If settings read fails, default to enabled.
  }

  const enablementToken = getEnablementCancellationToken();

  const apiUrl = getBaseUrl();

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
      if (enablementToken.isCancellationRequested) {
        throw new Error('Aspect Code disabled');
      }
      // Phase 1: Preparing validation (10%)
      progress.report({ increment: 0, message: 'Preparing examination...' });
      sendProgressToPanel(state, 'examination', 10, 'Preparing examination...');
      
      await new Promise(resolve => setTimeout(resolve, 200));
      
      // Phase 2: Collecting files (20%)
      progress.report({ increment: 10, message: 'Collecting source files...' });
      sendProgressToPanel(state, 'examination', 20, 'Collecting source files...');

      // Collect all source files and read their contents for remote validation
      const tDiscover = Date.now();
      const sourceFiles = await discoverWorkspaceSourceFiles();
      outputChannel?.appendLine(`[examineFullRepository] Discovered ${sourceFiles.length} source files`);
      outputChannel?.appendLine(`[Perf][EXAMINE] discoverWorkspaceSourceFiles tookMs=${Date.now() - tDiscover}`);
      
      // Read file contents (with size limit to prevent memory issues)
      // Use parallel batching to avoid antivirus slowdowns
      const maxFileSize = 100 * 1024; // 100KB per file
      const maxTotalSize = 10 * 1024 * 1024; // 10MB total
      const filesData: { path: string; content: string; language?: string }[] = [];
      let totalSize = 0;

      const tReadLoopStart = Date.now();
      
      // Helper to detect language from extension
      const detectLanguage = (filePath: string): string | undefined => {
        if (filePath.endsWith('.py')) return 'python';
        if (filePath.endsWith('.ts') || filePath.endsWith('.tsx')) return 'typescript';
        if (filePath.endsWith('.js') || filePath.endsWith('.jsx') || filePath.endsWith('.mjs') || filePath.endsWith('.cjs')) return 'javascript';
        if (filePath.endsWith('.java')) return 'java';
        if (filePath.endsWith('.cs')) return 'csharp';
        return undefined;
      };

      // Process files in parallel batches for better performance
      const BATCH_SIZE = 20;
      let processedCount = 0;
      let skippedLarge = 0;
      
      for (let i = 0; i < sourceFiles.length && totalSize < maxTotalSize; i += BATCH_SIZE) {
        if (enablementToken.isCancellationRequested) {
          throw new Error('Aspect Code disabled');
        }
        const batch = sourceFiles.slice(i, i + BATCH_SIZE);
        
        const batchResults = await Promise.allSettled(
          batch.map(async (filePath) => {
            if (enablementToken.isCancellationRequested) {
              return { skipped: true, size: 0, path: filePath };
            }
            const uri = vscode.Uri.file(filePath);
            const stat = await vscode.workspace.fs.stat(uri);
            
            // Skip files that are too large
            if (stat.size > maxFileSize) {
              return { skipped: true, size: stat.size, path: filePath };
            }
            
            const content = await vscode.workspace.fs.readFile(uri);
            const text = new TextDecoder().decode(content);
            const relativePath = path.relative(root, filePath);
            
            return {
              skipped: false,
              size: stat.size,
              data: {
                path: relativePath,
                content: text,
                language: detectLanguage(filePath)
              }
            };
          })
        );

        if (enablementToken.isCancellationRequested) {
          throw new Error('Aspect Code disabled');
        }
        
        // Collect results
        for (const result of batchResults) {
          if (result.status === 'fulfilled') {
            const value = result.value;
            if (value.skipped) {
              skippedLarge++;
            } else if (totalSize + value.size <= maxTotalSize) {
              filesData.push(value.data!);
              totalSize += value.size;
            }
          }
          // Skip failed files silently
        }
        
        processedCount += batch.length;
        
        // Log progress every 50 files
        if (processedCount % 50 === 0 || i + BATCH_SIZE >= sourceFiles.length) {
          const elapsed = Date.now() - tReadLoopStart;
          outputChannel?.appendLine(`[Perf][EXAMINE] readLoop progress filesAdded=${filesData.length} examined=${processedCount}/${sourceFiles.length} totalKB=${(totalSize / 1024).toFixed(1)} elapsedMs=${elapsed}`);
        }
      }

      if (skippedLarge > 0) {
        outputChannel?.appendLine(`[examineFullRepository] Skipped ${skippedLarge} files exceeding ${maxFileSize / 1024}KB limit`);
      }

      outputChannel?.appendLine(`[Perf][EXAMINE] readLoop end filesAdded=${filesData.length} examined=${processedCount}/${sourceFiles.length} totalKB=${(totalSize / 1024).toFixed(1)} tookMs=${Date.now() - tReadLoopStart}`);
      
      outputChannel?.appendLine(`[examineFullRepository] Prepared ${filesData.length} files (${(totalSize / 1024).toFixed(1)} KB) for remote validation`);

      // Build payload with file contents for remote validation
      const payload = {
        repo_root: root,
        modes: (Array.isArray(modesOverride) && modesOverride.length > 0)
          ? modesOverride
          : ['structure', 'types'],
        enable_project_graph: false, // Disabled for remote validation (no cross-file analysis yet)
        files: filesData  // Send file contents for remote validation
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

      const examFetchStart = Date.now();
      
      const fetchPromise = (async () => {
        const headers = await getHeaders();
        const response = await fetch(apiUrl + '/validate_tree_sitter', {
          method: 'POST',
          headers,
          body: JSON.stringify(payload)
        });
        return response;
      })();

      const res = await Promise.race([fetchPromise, timeoutPromise]) as Response;
      outputChannel?.appendLine(`[examineFullRepository] Server responded in ${Date.now() - examFetchStart}ms (${filesData.length} files)`);

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
            lastValidate: validateStats,
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
          const { regenerateEverything } = await import('./assistants/kb');
          const kbResult = await regenerateEverything(state, outputChannel!, context);
          
          // Mark KB as fresh after successful regeneration, reusing discovered files
          if (workspaceFingerprint && kbResult.regenerated) {
            await workspaceFingerprint.markKbFresh(kbResult.files);
          }
        } catch (kbError) {
          outputChannel?.appendLine(`[KB] Auto-regeneration failed (non-critical): ${kbError}`);
        }
      }

      // Check if we should auto-generate instruction files after successful examination
      const assistantsSettings = await getAssistantsSettings(vscode.Uri.file(root));
      const autoGenerate = assistantsSettings.autoGenerate;

      if (autoGenerate) {
        outputChannel?.appendLine('[Assistants] Auto-generating instruction files after examination...');
        try {
          await vscode.commands.executeCommand('aspectcode.generateInstructionFiles');
        } catch (genError) {
          outputChannel?.appendLine(`[Assistants] Auto-generation failed (non-critical): ${genError}`);
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

  const apiUrl = getBaseUrl();

  try {
    // Get snapshots
    const snapshotsHeaders = await getHeaders();
    const snapshotsRes = await fetch(apiUrl + '/snapshots', { headers: snapshotsHeaders });
    if (!snapshotsRes.ok) {
      handleHttpError(snapshotsRes.status, snapshotsRes.statusText);
    }

    const snapshots = await snapshotsRes.json() as SnapshotInfo[];

    // Get storage stats
    const statsHeaders = await getHeaders();
    const statsRes = await fetch(apiUrl + '/storage/stats', { headers: statsHeaders });
    if (!statsRes.ok) {
      handleHttpError(statsRes.status, statsRes.statusText);
    }

    const stats = await statsRes.json() as StorageStats;

    // Find current repo snapshot
    const currentSnapshot = snapshots.find((s) => s.repo_root === root);

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
      const result = await vscode.window.showInformationMessage(message, { modal: true }, 'Regenerate KB');
      if (result === 'Regenerate KB') {
        await vscode.commands.executeCommand('aspectcode.generateKB');
      }
    } else {
      const actions = ['Regenerate KB', 'Examine Full Repo'];
      const result = await vscode.window.showInformationMessage(message, { modal: true }, ...actions);
      if (result === 'Regenerate KB') {
        await vscode.commands.executeCommand('aspectcode.generateKB');
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
 * Fetch capabilities if not already cached.
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

    outputChannel?.appendLine('Fetching capabilities...');
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

  // Initialize state
  const state = new AspectCodeState(context);
  state.load();

  // Register the panel provider
  const panelProvider = new AspectCodePanelProvider(context, state, outputChannel);
  
  // Store panel provider reference in state for progress updates
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
    
    // Connect fingerprint staleness to panel indicator
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
          
          // Trigger a dependency graph refresh if panel is visible
          // FileDiscoveryService will use cached files from KB generation
          panelProvider.refreshDependencyGraph();

          outputChannel.appendLine(`[KB] Auto-regeneration complete in ${Date.now() - regenStart}ms`);
        }
      } catch (e) {
        outputChannel.appendLine(`[KB] Auto-regeneration failed: ${e}`);
      }
    });
    
    // Check KB staleness on startup and update panel
    const isStale = await workspaceFingerprint.isKbStale();
    panelProvider.setKbStale(isStale);
    if (isStale) {
      outputChannel.appendLine('[Startup] KB may be stale - will show indicator');
    } else {
      outputChannel.appendLine('[Startup] KB is up to date');
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

        // Key changed: clear any previous invalid/revoked banner until we validate again.
        resetApiKeyAuthStatus();

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

        // Key changed: clear any previous invalid/revoked banner.
        resetApiKeyAuthStatus();

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

  // 1. EXAMINE - Analyze entire repository for issues
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.examine', async (opts?: { modes?: string[] }) => {
      try {
        const rootUri = vscode.workspace.workspaceFolders?.[0]?.uri;
        if (rootUri) {
          const enabled = await getExtensionEnabledSetting(rootUri);
          if (!enabled) {
            vscode.window.showInformationMessage('Aspect Code is disabled.', 'Enable').then((sel) => {
              if (sel === 'Enable') void vscode.commands.executeCommand('aspectcode.toggleExtensionEnabled');
            });
            return;
          }
        }
        // Note: examineFullRepository will skip server validation if no API key (works offline)
        outputChannel?.appendLine('=== EXAMINE: Starting repository examination ===');
        
        // Validate the entire repository
        await examineFullRepository(state, context, opts?.modes);
        
        const total = state.s.lastValidate?.total ?? 0;
        const fixable = state.s.findings?.filter(f => f.fixable)?.length ?? 0;
        
        outputChannel?.appendLine(`=== EXAMINE: Found ${total} total issues, ${fixable} fixable ===`);
        
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
      // Note: KB generation works offline - no API key required

      try {
        const regenStart = Date.now();
        outputChannel?.appendLine('=== REGENERATE KB: Using regenerateEverything() ===');

        // Use the consolidated regenerateEverything function
        const { regenerateEverything } = await import('./assistants/kb');
        const result = await regenerateEverything(state, outputChannel!, context);
        
        if (result.regenerated) {
          // Mark KB as fresh after successful regeneration, reusing discovered files
          await workspaceFingerprint?.markKbFresh(result.files);
          
          // Notify panel that KB is no longer stale
          panelProvider.setKbStale(false);

          // Refresh dependency graph - FileDiscoveryService will use cached files
          panelProvider.refreshDependencyGraph();

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
        async () => computeImpactSummaryForFile(workspaceRoot, absPath, channel, context)
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
  
  // 3. FIX SAFE - Removed legacy auto-fix command
  
  // 2. SHOW PANEL - Display the main Aspect Code panel
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.showPanel', async () => {
      // Focus the webview panel directly by its view ID
      await vscode.commands.executeCommand('aspectcode.panel.focus');
    })
  );

  // 5. COPY DEBUG INFO - Collect debug information for support
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.copyDebugInfo', async () => {
      try {
        const { getExtensionVersion, getNetworkEvents, getBaseUrl } = await import('./http');
        
        // Collect debug info
        const debugInfo: Record<string, any> = {
          timestamp: new Date().toISOString(),
          extension_version: getExtensionVersion(),
          server_url: getBaseUrl(),
        };
        
        // Workspace fingerprint (hashed, no real path)
        if (workspaceFingerprint) {
          const stats = await workspaceFingerprint.getStats();
          debugInfo.workspace = {
            fingerprint_hash: stats.fingerprint?.substring(0, 12),
            file_count: stats.fileCount,
            kb_stale: stats.isStale,
            last_kb_update: stats.lastKbUpdate,
          };
        }
        
        // KB mode from project-local settings
        const root = await getWorkspaceRoot();
        if (root) {
          debugInfo.kb_mode = await getAutoRegenerateKbSetting(vscode.Uri.file(root));
        } else {
          debugInfo.kb_mode = 'unknown';
        }
        
        // State summary
        const panelState = state.get();
        debugInfo.state = {
          busy: panelState.busy,
          findings_count: panelState.findings.length,
          has_snapshot: !!panelState.snapshot,
          last_validate_took_ms: panelState.lastValidate?.tookMs,
          error: panelState.error?.substring(0, 100),
        };
        
        // Last 20 network events
        const events = getNetworkEvents();
        debugInfo.network_events = events.map(e => ({
          time: new Date(e.timestamp).toISOString(),
          endpoint: e.endpoint,
          status: e.status,
          duration_ms: e.durationMs,
          request_id: e.requestId?.substring(0, 8),
          error: e.error?.substring(0, 50),
        }));
        
        // Format and copy
        const text = JSON.stringify(debugInfo, null, 2);
        await vscode.env.clipboard.writeText(text);
        
        vscode.window.showInformationMessage(
          'Aspect Code debug info copied to clipboard.',
          'Show in Output'
        ).then(choice => {
          if (choice === 'Show in Output') {
            outputChannel.appendLine('=== DEBUG INFO ===');
            outputChannel.appendLine(text);
            outputChannel.show();
          }
        });
      } catch (e) {
        vscode.window.showErrorMessage(`Failed to collect debug info: ${e}`);
      }
    })
  );

  // 6. FORCE REINDEX - Run full examination (same as startup) and regenerate KB
  // This is a manual button - always runs regardless of staleness
  context.subscriptions.push(
    vscode.commands.registerCommand('aspectcode.forceReindex', async () => {
      try {
        outputChannel?.appendLine('=== FORCE REINDEX: Running full examination ===');
        
        // Invalidate FileDiscoveryService cache to force fresh file discovery
        const { getFileDiscoveryService } = await import('./services/FileDiscoveryService');
        const fileDiscovery = getFileDiscoveryService();
        fileDiscovery?.invalidate();
        
        // Run full examination - this shows the "Validating..." toast,
        // discovers files, validates, and regenerates KB at the end
        // examineFullRepository already calls markKbFresh with discovered files
        await examineFullRepository(state, context);
        
        // Refresh UI after examination completes
        // No need to call markKbFresh again - examineFullRepository does it
        panelProvider.setKbStale(false);
        panelProvider.refreshDependencyGraph();
        
        outputChannel?.appendLine('=== FORCE REINDEX: Complete ===');
      } catch (error) {
        outputChannel?.appendLine(`FORCE REINDEX ERROR: ${error}`);
        vscode.window.showErrorMessage(`Examination failed: ${error}`);
      }
    })
  );
  
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
      // NOTE: Autofix actions removed - feature disabled
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
