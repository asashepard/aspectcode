import * as vscode from 'vscode';
import * as path from 'path';
import { AspectCodeState } from '../state';
import { DependencyAnalyzer, DependencyLink } from '../panel/DependencyAnalyzer';

type ProgressFn = (message: string) => void;
type KbStatus = { path: string; ok: boolean };

type RankedFile = {
  relPath: string;
  score: number;
  importedBy: number;
  tags: string[];
};

const STOPWORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'but', 'if', 'then', 'else', 'when', 'while', 'for', 'to', 'of', 'in', 'on',
  'by', 'with', 'from', 'into', 'as', 'at', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'this', 'that',
  'these', 'those', 'it', 'its', 'we', 'you', 'they', 'them', 'our', 'your', 'their', 'can', 'could', 'should',
  'would', 'may', 'might', 'must', 'do', 'does', 'did', 'done', 'not', 'no', 'yes', 'all', 'any', 'some',
  'fix', 'bug', 'issue', 'error', 'warn', 'warning', 'refactor', 'improve', 'update', 'change', 'add', 'remove',
  'make', 'use', 'using', 'work', 'works', 'working', 'implement', 'plan', 'project', 'repo', 'workspace'
]);

const SYNONYMS: Record<string, string[]> = {
  auth: ['authentication', 'authorization', 'authorize', 'login', 'jwt', 'token', 'session', 'oauth'],
  api: ['http', 'endpoint', 'handler', 'route', 'request', 'response', 'server'],
  db: ['database', 'sql', 'query', 'orm', 'model', 'storage', 'persistence'],
  cache: ['caching', 'memo', 'memoize', 'redis'],
  config: ['settings', 'env', 'environment', 'configuration'],
  build: ['compile', 'bundle', 'tsc', 'webpack', 'vite'],
  test: ['tests', 'testing', 'pytest', 'jest', 'unit', 'integration'],
  ui: ['webview', 'panel', 'frontend', 'view'],
  kb: ['knowledge', 'architecture', 'context', 'map', 'fingerprint'],
  graph: ['dependency', 'deps', 'imports', 'edges', 'cycles']
};

function normalizeFsPath(p: string): string {
  return path.normalize(p);
}

function relPath(absPath: string, workspaceRoot: string): string {
  try {
    return workspaceRoot ? path.relative(workspaceRoot, absPath).replace(/\\/g, '/') : absPath.replace(/\\/g, '/');
  } catch {
    return absPath.replace(/\\/g, '/');
  }
}

function tokenize(text: string): string[] {
  const raw = (text || '')
    .toLowerCase()
    .replace(/\\/g, '/')
    .replace(/[^a-z0-9_./-]+/g, ' ');

  const base = raw
    .split(/\s+/)
    .map(t => t.trim())
    .filter(Boolean)
    .filter(t => t.length >= 2)
    .filter(t => !STOPWORDS.has(t))
    .filter(t => !/^[0-9]+$/.test(t));

  const expanded = new Set<string>(base);
  for (const t of base) {
    const key = t.replace(/[^a-z0-9_]+/g, '');
    const syns = SYNONYMS[key];
    if (syns) {
      for (const s of syns) expanded.add(s);
    }
  }
  return Array.from(expanded).sort();
}

function buildAdjacency(links: DependencyLink[]): {
  out: Map<string, Set<string>>;
  inbound: Map<string, Set<string>>;
  indegree: Map<string, number>;
  outdegree: Map<string, number>;
  circularEdgeCount: number;
} {
  const out = new Map<string, Set<string>>();
  const inbound = new Map<string, Set<string>>();
  const indegree = new Map<string, number>();
  const outdegree = new Map<string, number>();
  let circularEdgeCount = 0;

  const addEdge = (s: string, t: string) => {
    if (!out.has(s)) out.set(s, new Set());
    out.get(s)!.add(t);
    if (!inbound.has(t)) inbound.set(t, new Set());
    inbound.get(t)!.add(s);
  };

  for (const l of links) {
    addEdge(l.source, l.target);
    if (l.bidirectional) addEdge(l.target, l.source);
    if (l.type === 'circular') circularEdgeCount += 1;
  }

  for (const [s, ts] of out) outdegree.set(s, ts.size);
  for (const [t, ss] of inbound) indegree.set(t, ss.size);

  return { out, inbound, indegree, outdegree, circularEdgeCount };
}

function neighborhoodDistances(
  seed: string,
  out: Map<string, Set<string>>,
  inbound: Map<string, Set<string>>,
  maxDepth: number
): Map<string, number> {
  const dist = new Map<string, number>();
  const queue: Array<{ node: string; d: number }> = [{ node: seed, d: 0 }];
  dist.set(seed, 0);

  while (queue.length) {
    const { node, d } = queue.shift()!;
    if (d >= maxDepth) continue;
    const neighbors = new Set<string>([...(out.get(node) || []), ...(inbound.get(node) || [])]);
    for (const n of neighbors) {
      const nd = d + 1;
      const existing = dist.get(n);
      if (existing === undefined || nd < existing) {
        dist.set(n, nd);
        queue.push({ node: n, d: nd });
      }
    }
  }

  return dist;
}

function confidenceIcon(norm: number): { icon: string; word: string } {
  if (norm >= 0.66) return { icon: '🟢', word: 'likely' };
  if (norm >= 0.33) return { icon: '🟡', word: 'candidate' };
  return { icon: '🔴', word: 'weak-candidate' };
}

function rankFiles(args: {
  userText: string;
  files: string[];
  links: DependencyLink[];
  workspaceRoot: string;
  seedFileAbs?: string;
}): { ranked: RankedFile[]; circularEdgeCount: number } {
  const queryTokens = tokenize(args.userText);
  const { out, inbound, indegree, outdegree, circularEdgeCount } = buildAdjacency(args.links);

  const seedAbs = args.seedFileAbs ? normalizeFsPath(args.seedFileAbs) : undefined;
  const dist = seedAbs ? neighborhoodDistances(seedAbs, out, inbound, 2) : new Map<string, number>();

  const candidates = new Set<string>();
  if (seedAbs) candidates.add(seedAbs);
  for (const f of dist.keys()) candidates.add(f);

  for (const abs of args.files) {
    const p = relPath(abs, args.workspaceRoot).toLowerCase();
    if (queryTokens.some(t => p.includes(t))) candidates.add(abs);
  }

  const ranked: RankedFile[] = [];
  for (const abs of candidates) {
    const rp = relPath(abs, args.workspaceRoot);
    const rpLower = rp.toLowerCase();
    const importedBy = indegree.get(abs) || 0;
    const imports = outdegree.get(abs) || 0;

    let score = 0;
    const tags: string[] = [];

    if (seedAbs && abs === seedAbs) {
      score += 8;
      tags.push('active');
    }

    const d = dist.get(abs);
    if (d === 1) {
      score += 6;
      tags.push('neighbor1');
    } else if (d === 2) {
      score += 3;
      tags.push('neighbor2');
    }

    const tokenHits: string[] = [];
    for (const t of queryTokens) {
      if (rpLower.includes(t)) tokenHits.push(t);
    }
    if (tokenHits.length) {
      score += Math.min(10, tokenHits.length * 2);
      tags.push(`token:${tokenHits.slice(0, 2).join('+')}`);
    }

    score += Math.min(6, Math.floor((importedBy + imports) / 5));
    if (importedBy + imports >= 10) tags.push('hub');

    if (score <= 0) continue;
    ranked.push({ relPath: rp, score, importedBy, tags });
  }

  ranked.sort((a, b) =>
    b.score - a.score ||
    b.importedBy - a.importedBy ||
    a.relPath.localeCompare(b.relPath)
  );

  return { ranked, circularEdgeCount };
}

function renderPrompt(args: {
  task: string;
  kbStatus: KbStatus[];
  ranked: RankedFile[];
  circularEdgeCount: number;
}): string {
  const topFiles = args.ranked.slice(0, 10);
  const maxScore = args.ranked.length ? args.ranked[0].score : 1;

  const lines: string[] = [];
  lines.push('# You are a software engineer AI assistant with full workspace access.');
  lines.push('');
  lines.push('## Task');
  lines.push(args.task);
  lines.push('');
  lines.push('## Read First (KB v3)');
  for (const s of args.kbStatus) {
    lines.push(`- ${s.ok ? '[x]' : '[ ]'} ${s.path}`);
  }
  lines.push('');
  lines.push('## Relevant Context (confidence-scored)');
  lines.push('Deterministic ranking: score desc, importedBy desc, path asc.');
  lines.push('');
  lines.push('### Files (ranked)');
  if (topFiles.length === 0) {
    lines.push('- (No ranked files available)');
  } else {
    for (const f of topFiles) {
      const norm = Math.max(0, Math.min(1, f.score / maxScore));
      const c = confidenceIcon(norm);
      const tagStr = f.tags.length ? ` [${f.tags.join(',')}]` : '';
      lines.push(`- ${c.icon} ${f.relPath} (${c.word}; score=${f.score}, importedBy=${f.importedBy})${tagStr}`);
    }
    const remaining = Math.max(0, args.ranked.length - topFiles.length);
    if (remaining > 0) lines.push(`- (+${remaining} more)`);
  }
  lines.push('');
  lines.push(`Notes: circularEdges=${args.circularEdgeCount}. Tags: active/neighbor*/hub/token:*.`);
  lines.push('');
  lines.push('## Output Format (respond in markdown)');
  lines.push('### Understanding');
  lines.push('- Summarize relevant architecture from KB v3 and how it connects to the ranked files.');
  lines.push('### Plan');
  lines.push('1. Read: [files] → confirm responsibilities + dependencies');
  lines.push('2. Change: [smallest safe steps]');
  lines.push('3. Verify: tests/build + import graph sanity');
  lines.push('### Execution');
  lines.push('- For each step: what you read, what you changed, how you verified.');
  lines.push('### Validation');
  lines.push('- Ensure no new circular dependencies; be careful with hubs and entry points.');
  return lines.join('\n');
}

export class PromptGenerationService {
  private readonly dependencyAnalyzer = new DependencyAnalyzer();
  private workspaceFilesCache: string[] | null = null;
  private dependencyLinksCache: DependencyLink[] | null = null;
  private cacheAt = 0;
  private readonly cacheTtlMs = 30_000;

  constructor(private readonly deps: { outputChannel: vscode.OutputChannel; state: AspectCodeState }) {}

  async buildUserPrompt(args: {
    userText: string;
    activeFileUri?: vscode.Uri;
    onProgress?: ProgressFn;
  }): Promise<string> {
    const workspaceFolder = vscode.workspace.workspaceFolders?.[0];
    if (!workspaceFolder) throw new Error('No workspace folder open');

    const workspaceRoot = workspaceFolder.uri.fsPath;
    const task = (args.userText ?? '').trim();
    if (!task) throw new Error('Task text is empty');

    const report: ProgressFn = (message: string) => {
      try { args.onProgress?.(message); } catch { /* best-effort */ }
    };

    report('Preparing...');
    const kbStatus = await this.kbFileStatus(workspaceFolder);

    report('Loading dependency context...');
    const { files, links, source } = await this.getDependencyContext(report);
    this.deps.outputChannel.appendLine(`[Prompt] dependencyContext source=${source} files=${files.length} links=${links.length}`);

    report('Scoring files...');
    const seedFileAbs = args.activeFileUri?.scheme === 'file' ? normalizeFsPath(args.activeFileUri.fsPath) : undefined;
    const { ranked, circularEdgeCount } = rankFiles({ userText: task, files, links, workspaceRoot, seedFileAbs });

    report('Building prompt...');
    return renderPrompt({ task, kbStatus, ranked, circularEdgeCount });
  }

  private async kbFileStatus(workspaceFolder: vscode.WorkspaceFolder): Promise<KbStatus[]> {
    const kbRel = ['.aspect/architecture.md', '.aspect/map.md', '.aspect/context.md'];
    const out: KbStatus[] = [];
    for (const p of kbRel) {
      try {
        const uri = vscode.Uri.joinPath(workspaceFolder.uri, ...p.split('/'));
        await vscode.workspace.fs.stat(uri);
        out.push({ path: p, ok: true });
      } catch {
        out.push({ path: p, ok: false });
      }
    }
    return out;
  }

  private filesFromLinks(links: DependencyLink[]): string[] {
    const s = new Set<string>();
    for (const l of links) { s.add(l.source); s.add(l.target); }
    return Array.from(s);
  }

  private async getDependencyContext(report: ProgressFn): Promise<{
    files: string[];
    links: DependencyLink[];
    source: 'panel-cache' | 'service-cache' | 'fresh-analysis' | 'none';
  }> {
    const panelProvider: any = (this.deps.state as any)._panelProvider;
    const panelLinks: DependencyLink[] | null | undefined = panelProvider?.getCachedDependencyLinksForPrompt?.();
    const panelFiles: string[] | null | undefined = panelProvider?.getCachedWorkspaceFilesForPrompt?.();
    if (panelLinks && panelLinks.length > 0) {
      return {
        links: panelLinks,
        files: panelFiles && panelFiles.length > 0 ? panelFiles : this.filesFromLinks(panelLinks),
        source: 'panel-cache'
      };
    }

    const now = Date.now();
    if (this.dependencyLinksCache && this.workspaceFilesCache && (now - this.cacheAt) < this.cacheTtlMs) {
      return { files: this.workspaceFilesCache, links: this.dependencyLinksCache, source: 'service-cache' };
    }

    report('Discovering workspace files...');
    const files = await this.discoverWorkspaceFiles();
    if (files.length === 0) {
      this.workspaceFilesCache = [];
      this.dependencyLinksCache = [];
      this.cacheAt = now;
      return { files: [], links: [], source: 'none' };
    }

    report(`Analyzing dependencies (${files.length} files)...`);
    const links = await this.dependencyAnalyzer.analyzeDependencies(files, (_cur, _tot, phase) => report(phase));

    this.workspaceFilesCache = files;
    this.dependencyLinksCache = links;
    this.cacheAt = Date.now();

    return { files, links, source: 'fresh-analysis' };
  }

  private async discoverWorkspaceFiles(): Promise<string[]> {
    const workspaceFolders = vscode.workspace.workspaceFolders;
    if (!workspaceFolders || workspaceFolders.length === 0) return [];

    const include = '**/*.{ts,tsx,js,jsx,mjs,cjs,py}';
    const exclude = '**/{node_modules,dist,out,build,.git,.aspect}/**';

    const all: string[] = [];
    for (const folder of workspaceFolders) {
      const found = await vscode.workspace.findFiles(new vscode.RelativePattern(folder, include), exclude);
      for (const uri of found) all.push(normalizeFsPath(uri.fsPath));
    }
    all.sort((a, b) => a.localeCompare(b));
    return all;
  }
}
