// WebView bootstrap for Aspect Code Panel
declare const acquireVsCodeApi: any;
// src/panel/webview/main.ts
const vscode = acquireVsCodeApi();

type RunFlowMsg = { type: 'RUN_FLOW'; steps: string[] };
type RequestStateMsg = { type: 'REQUEST_STATE' };
type CaptureSnapshotMsg = { type: 'CAPTURE_SNAPSHOT' };
type PanelReadyMsg = { type: 'PANEL_READY' };
type AutofixOneMsg = { type: 'AUTOFIX_ONE'; id: string };
type OpenFindingMsg = { type: 'OPEN_FINDING'; file: string; line?: number; column?: number };
type FixSafeMsg = { type: 'FIX_SAFE' };
type RegenerateKbMsg = { type: 'REGENERATE_KB' };

type FromExt =
  | { type: 'STATE_UPDATE'; state: StateSnapshot }
  | { type: 'FLOW_PROGRESS'; phase: string; detail?: any }
  | { type: 'SNAPSHOT_RESULT'; snapshot: Snapshot }
  | { type: 'DEPENDENCY_GRAPH'; graph: DependencyGraphData }
  | { type: 'ACTIVE_FILE_CHANGED'; file: string };

export type Finding = {
  id?: string;
  file: string;
  rule: string;
  message: string;
  fixable: boolean;
  span?: { start:{ line:number; column:number }, end:{ line:number; column:number } };
  severity?: 'info'|'warn'|'error';
  priority?: 'P0'|'P1'|'P2'|'P3';
};

// Auto-Fix v1 compatible rules (mirrors backend constant)
const AUTO_FIX_V1_RULE_IDS = [
  'imports.unused',
  'deadcode.unused_variable', 
  'lang.ts_loose_equality',
  'memory.return_address_check',
  'style.trailing_whitespace',
  'style.consecutive_blank_lines',
  'style.missing_final_newline',
  'style.tab_vs_space_mixed',
  'style.line_length_exceeded',
  'types.ts_any_overuse'
] as const;

// Helper function to check if a finding is Auto-Fix v1 compatible
function isAutoFixV1Compatible(finding: Finding): boolean {
  return AUTO_FIX_V1_RULE_IDS.includes(finding.rule as any);
}

export type StateSnapshot = {
  busy: boolean;
  findings: Finding[];
  byRule: Record<string, number>;
  history: Array<{ ts: string; filesChanged: number; diffBytes: number }>;
  lastDiffMeta?: { files: number; hunks: number };
  fixableRulesCount?: number;
  lastAction?: string;
  totalFiles?: number;
  processingPhase?: string;
  progress?: number;
  kbStale?: boolean;
  score?: {
    overall: number;
    breakdown: {
      totalFindings: number;
      severityBreakdown: { [key: string]: number };
      categoryBreakdown: { [key: string]: number };
      fileTypeBreakdown: { [key: string]: number };
      concentrationPenalty: number;
      volumePenalty: number;
      totalDeductions: number;
      categoryImpacts: { [key: string]: number };
    };
    subScores: {
      complexity: number | null;
      coverage: number | null;
      documentation: number | null;
    };
    insights: string[];
    potentialImprovement?: number;
  };
};

export type Snapshot = { renderedFindings: number; filters: any; history: StateSnapshot['history']; lastDiffMeta?: StateSnapshot['lastDiffMeta'] };

export type DependencyGraphData = {
  nodes: Array<{ id: string; label: string; type: 'hub' | 'file'; importance: number; file?: string }>;
  links: Array<{ source: string; target: string; strength: number }>;
};

// DOM elements
let processingIndicator: HTMLElement;
let processingText: HTMLElement;
let progressFill: HTMLElement;
let repoScore: HTMLElement;
let graphStats: HTMLElement;
let totalFilesEl: HTMLElement;
let activeIssuesEl: HTMLElement;
let fixableCountEl: HTMLElement;
let criticalCountEl: HTMLElement;
let findingsToggle: HTMLElement;
let findingsContent: HTMLElement;
let findingsList: HTMLElement;
let btnAnalyze: HTMLElement;
let btnAutoFix: HTMLElement;
let btnRefresh: HTMLElement;

// Graph visualization
let svgGraph: any; // Will be D3 selection
let graphData: DependencyGraphData = { nodes: [], links: [] };
let activeFile: string = '';

// State
let currentState: StateSnapshot = {
  busy: false,
  findings: [],
  byRule: {},
  history: [],
  totalFiles: 0
};
let findingsExpanded = true;
let currentFilters = {
  search: '',
  severity: 'all',
  rule: 'all'
};

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  initializeElements();
  initializeDependencyGraph();
  setupEventListeners();
  
  // Start auto-analysis
  startAutoAnalysis();
});

function initializeElements() {
  processingIndicator = document.getElementById('processing-indicator')!;
  processingText = document.getElementById('processing-text')!;
  progressFill = document.getElementById('progress-fill')!;
  repoScore = document.getElementById('repo-score')!;
  graphStats = document.getElementById('graph-stats')!;
  totalFilesEl = document.getElementById('total-files')!;
  activeIssuesEl = document.getElementById('active-issues')!;
  fixableCountEl = document.getElementById('fixable-count')!;
  criticalCountEl = document.getElementById('critical-count')!;
  findingsToggle = document.getElementById('findings-toggle')!;
  findingsContent = document.getElementById('findings-content')!;
  findingsList = document.getElementById('findings-list')!;
  btnAnalyze = document.getElementById('btn-analyze')!;
  btnAutoFix = document.getElementById('auto-fix-safe-button')!;
  btnRefresh = document.getElementById('btn-refresh')!;
}

function setupEventListeners() {
  // Findings toggle
  const findingsHeader = document.getElementById('findings-header')!;
  findingsHeader.addEventListener('click', () => {
    findingsExpanded = !findingsExpanded;
    updateFindingsVisibility();
  });

  // Button actions
  btnAnalyze.addEventListener('click', () => {
    if (!currentState.busy) {
      startAutoAnalysis();
    }
  });

  btnAutoFix.addEventListener('click', () => {
    vscode.postMessage({ type: 'FIX_SAFE' });
  });

  btnRefresh.addEventListener('click', () => {
    startAutoAnalysis();
  });

  // Filters
  const searchInput = document.getElementById('findings-search') as HTMLInputElement;
  const severityFilter = document.getElementById('severity-filter') as HTMLSelectElement;
  const ruleFilter = document.getElementById('rule-filter') as HTMLSelectElement;

  searchInput?.addEventListener('input', (e) => {
    currentFilters.search = (e.target as HTMLInputElement).value;
    updateFindingsDisplay();
  });

  severityFilter?.addEventListener('change', (e) => {
    currentFilters.severity = (e.target as HTMLSelectElement).value;
    updateFindingsDisplay();
  });

  ruleFilter?.addEventListener('change', (e) => {
    currentFilters.rule = (e.target as HTMLSelectElement).value;
    updateFindingsDisplay();
  });
}

function startAutoAnalysis() {
  showProcessing('Indexing repository...', 0);
  vscode.postMessage({ type: 'RUN_FLOW', steps: ['index', 'validate'] });
}

function showProcessing(text: string, progress: number) {
  processingIndicator.style.display = 'flex';
  processingText.textContent = text;
  progressFill.style.width = `${progress}%`;
  
  btnAnalyze.innerHTML = '<span class="btn-icon">⏳</span>Analyzing...';
  (btnAnalyze as HTMLButtonElement).disabled = true;
}

function hideProcessing() {
  processingIndicator.style.display = 'none';
  btnAnalyze.innerHTML = '<span class="btn-icon">🔍</span>Run Analysis';
  (btnAnalyze as HTMLButtonElement).disabled = false;
}

function updateFindingsVisibility() {
  if (findingsExpanded) {
    findingsContent.classList.remove('collapsed');
    findingsToggle.textContent = '▼';
    findingsToggle.classList.remove('collapsed');
  } else {
    findingsContent.classList.add('collapsed');
    findingsToggle.textContent = '►';
    findingsToggle.classList.add('collapsed');
  }
}

function updateStats(state: StateSnapshot) {
  totalFilesEl.textContent = state.totalFiles?.toString() || '0';
  activeIssuesEl.textContent = state.findings.length.toString();
  
  const fixableCount = state.findings.filter(f => f.fixable).length;
  fixableCountEl.textContent = fixableCount.toString();
  
  const criticalCount = state.findings.filter(f => f.severity === 'error').length;
  criticalCountEl.textContent = criticalCount.toString();
  
  // Update Auto-Fix v1 compatible count
  const autofixV1Count = state.findings.filter(isAutoFixV1Compatible).length;
  const autofixV1El = document.getElementById('autofix-v1-count');
  if (autofixV1El) {
    autofixV1El.textContent = autofixV1Count.toString();
  }
  
  // Update repository score based on findings
  updateRepositoryScore(state);
}

function updateRepositoryScore(state: StateSnapshot) {
  // Use the asymptotic score from the scoring engine if available
  let score = 0;
  let grade = 'F';
  let potentialImprovement = 0;
  
  if (state.score && state.score.overall !== undefined) {
    // Use asymptotic scoring engine result
    score = state.score.overall;
    potentialImprovement = state.score.potentialImprovement || 0;
  } else {
    // Fallback: simple scoring algorithm (legacy)
    const totalIssues = state.findings.length;
    const criticalIssues = state.findings.filter(f => f.severity === 'error').length;
    score = 100;
    score -= criticalIssues * 10;
    score -= (totalIssues - criticalIssues) * 2;
    score = Math.max(0, Math.min(100, score));
  }
  
  // Determine letter grade based on score
  if (score >= 90) grade = 'A+';
  else if (score >= 85) grade = 'A';
  else if (score >= 80) grade = 'A-';
  else if (score >= 75) grade = 'B+';
  else if (score >= 70) grade = 'B';
  else if (score >= 65) grade = 'B-';
  else if (score >= 60) grade = 'C+';
  else if (score >= 55) grade = 'C';
  else if (score >= 50) grade = 'C-';
  else if (score >= 45) grade = 'D+';
  else if (score >= 40) grade = 'D';
  
  repoScore.textContent = grade;
  const scoreSubtext = repoScore.nextElementSibling as HTMLElement;
  if (scoreSubtext) {
    scoreSubtext.textContent = `${score.toFixed(1)}/100`;
  }
  
  // Update score color
  repoScore.style.color = 
    score >= 80 ? 'var(--vscode-charts-green)' :
    score >= 60 ? 'var(--vscode-charts-yellow)' :
    'var(--vscode-charts-red)';
  
  // Update Auto-Fix button with potential improvement badge
  updateAutoFixBadge(potentialImprovement);
}

function updateAutoFixBadge(improvement: number) {
  const button = document.getElementById('auto-fix-safe-button');
  if (!button) {
    return;
  }
  
  // Remove existing badge if present
  const existingBadge = button.querySelector('.improvement-badge');
  if (existingBadge) {
    existingBadge.remove();
  }
  
  // Add badge if there's potential improvement
  if (improvement > 0) {
    const badge = document.createElement('span');
    badge.className = 'improvement-badge';
    badge.textContent = `+${improvement.toFixed(1)}`;
    badge.title = `Auto-fixing could improve score by ${improvement.toFixed(1)} points`;
    badge.style.cssText = 'position: absolute; top: -6px; right: -6px; background: #4CAF50; color: white; font-size: 9px; font-weight: 700; padding: 2px 5px; border-radius: 8px; z-index: 1000;';
    button.appendChild(badge);
  }
}

function updateFindingsDisplay() {
  const filtered = filterFindings(currentState.findings);
  
  // Update rule filter options
  updateRuleFilterOptions(currentState.findings);
  
  // Clear and populate findings
  findingsList.innerHTML = '';
  
  if (filtered.length === 0) {
    findingsList.innerHTML = `
      <div class="empty-state">
        <div class="empty-state-icon">🎉</div>
        <div>No issues found matching current filters</div>
      </div>
    `;
    return;
  }
  
  filtered.forEach(finding => {
    const element = createFindingElement(finding);
    findingsList.appendChild(element);
  });
}

function filterFindings(findings: Finding[]): Finding[] {
  return findings.filter(finding => {
    // Search filter
    if (currentFilters.search) {
      const searchLower = currentFilters.search.toLowerCase();
      const matchesSearch = 
        finding.message.toLowerCase().includes(searchLower) ||
        finding.rule.toLowerCase().includes(searchLower) ||
        finding.file.toLowerCase().includes(searchLower);
      if (!matchesSearch) return false;
    }
    
    // Severity filter
    if (currentFilters.severity !== 'all' && finding.severity !== currentFilters.severity) {
      return false;
    }
    
    // Rule filter
    if (currentFilters.rule !== 'all' && finding.rule !== currentFilters.rule) {
      return false;
    }
    
    return true;
  });
}

function updateRuleFilterOptions(findings: Finding[]) {
  const ruleFilter = document.getElementById('rule-filter') as HTMLSelectElement;
  if (!ruleFilter) return;
  
  const rules = [...new Set(findings.map(f => f.rule))].sort();
  const currentValue = ruleFilter.value;
  
  ruleFilter.innerHTML = '<option value="all">All Rules</option>';
  rules.forEach(rule => {
    const option = document.createElement('option');
    option.value = rule;
    option.textContent = rule;
    ruleFilter.appendChild(option);
  });
  
  // Restore selection if still valid
  if (rules.includes(currentValue) || currentValue === 'all') {
    ruleFilter.value = currentValue;
  }
}

function createFindingElement(finding: Finding): HTMLElement {
  const div = document.createElement('div');
  div.className = 'finding-item';
  
  const locationText = finding.file + 
    (finding.span ? `:${finding.span.start.line}:${finding.span.start.column}` : '');
  
  // Check if finding is Auto-Fix v1 compatible
  const isV1Compatible = isAutoFixV1Compatible(finding);
  
  div.innerHTML = `
    <div class="finding-header">
      <span class="finding-rule">${finding.rule}</span>
      <span class="finding-severity severity-${finding.severity || 'warn'}">${finding.severity || 'warn'}</span>
      ${finding.fixable ? '<span class="finding-fixable">Auto-fixable</span>' : ''}
      ${isV1Compatible ? '<span class="finding-autofix-v1" title="Compatible with Auto-Fix v1 pipeline">⚡ Auto-Fix v1</span>' : ''}
    </div>
    <div class="finding-message">${escapeHtml(finding.message)}</div>
    <div class="finding-location">${escapeHtml(locationText)}</div>
  `;
  
  div.addEventListener('click', () => {
    const line = finding.span?.start?.line;
    const column = finding.span?.start?.column;
    vscode.postMessage({
      type: 'OPEN_FINDING',
      file: finding.file,
      line,
      column
    });
  });
  
  return div;
}

function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Dependency graph visualization
function initializeDependencyGraph() {
  // Simple SVG-based visualization without D3 for now
  const svg = document.getElementById('dependency-graph') as unknown as SVGElement;
  if (!svg) return;
  
  // Create a simple placeholder visualization
  updateDependencyGraph({ nodes: [], links: [] });
}

function updateDependencyGraph(data: DependencyGraphData) {
  graphData = data;
  const svg = document.getElementById('dependency-graph') as unknown as SVGElement;
  if (!svg) return;
  
  // Clear existing content
  svg.innerHTML = '';
  
  if (data.nodes.length === 0) {
    // Show placeholder
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', '50%');
    text.setAttribute('y', '50%');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('fill', 'var(--vscode-descriptionForeground)');
    text.setAttribute('font-size', '14');
    text.textContent = 'Analyzing dependencies...';
    svg.appendChild(text);
    return;
  }
  
  // Update graph stats
  graphStats.textContent = `${data.nodes.length} files, ${data.links.length} connections`;
  
  // Simple circular layout
  const width = svg.clientWidth || 300;
  const height = svg.clientHeight || 300;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(width, height) / 3;
  
  // Position nodes in a circle
  data.nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / data.nodes.length;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    
    // Draw connections first (behind nodes)
    data.links.forEach(link => {
      if (link.source === node.id) {
        const targetIndex = data.nodes.findIndex(n => n.id === link.target);
        if (targetIndex >= 0) {
          const targetAngle = (2 * Math.PI * targetIndex) / data.nodes.length;
          const targetX = centerX + radius * Math.cos(targetAngle);
          const targetY = centerY + radius * Math.sin(targetAngle);
          
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', x.toString());
          line.setAttribute('y1', y.toString());
          line.setAttribute('x2', targetX.toString());
          line.setAttribute('y2', targetY.toString());
          line.setAttribute('class', 'connection');
          svg.appendChild(line);
        }
      }
    });
  });
  
  // Draw nodes
  data.nodes.forEach((node, i) => {
    const angle = (2 * Math.PI * i) / data.nodes.length;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    
    // Node circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', x.toString());
    circle.setAttribute('cy', y.toString());
    circle.setAttribute('r', node.type === 'hub' ? '8' : '5');
    circle.setAttribute('class', `${node.type}-node`);
    circle.style.cursor = 'pointer';
    
    // Add click handler to focus on file
    circle.addEventListener('click', () => {
      if (node.file) {
        highlightFile(node.file);
        vscode.postMessage({ type: 'OPEN_FINDING', file: node.file });
      }
    });
    
    svg.appendChild(circle);
    
    // Node label
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x.toString());
    text.setAttribute('y', (y + 15).toString());
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('class', 'file-label');
    text.textContent = node.label.length > 10 ? node.label.substring(0, 10) + '...' : node.label;
    text.style.cursor = 'pointer';
    
    text.addEventListener('click', () => {
      if (node.file) {
        highlightFile(node.file);
        vscode.postMessage({ type: 'OPEN_FINDING', file: node.file });
      }
    });
    
    svg.appendChild(text);
  });
}

function highlightFile(filePath: string) {
  activeFile = filePath;
  const svg = document.getElementById('dependency-graph') as unknown as SVGElement;
  if (!svg) return;
  
  // Remove existing highlights
  svg.querySelectorAll('.active').forEach(el => el.classList.remove('active'));
  
  // Find and highlight the node for this file
  const nodeIndex = graphData.nodes.findIndex(n => n.file === filePath);
  if (nodeIndex >= 0) {
    const circles = svg.querySelectorAll('circle');
    const texts = svg.querySelectorAll('text');
    
    if (circles[nodeIndex]) circles[nodeIndex].classList.add('active');
    if (texts[nodeIndex]) texts[nodeIndex].classList.add('active');
    
    // Highlight connected edges
    graphData.links.forEach(link => {
      if (link.source === graphData.nodes[nodeIndex].id || link.target === graphData.nodes[nodeIndex].id) {
        // Find corresponding line element and highlight
        // This is simplified - in a full implementation you'd track elements
      }
    });
  }
}

// Message handling from extension
window.addEventListener('message', (event: MessageEvent<FromExt>) => {
  const msg = event.data;
  switch (msg.type) {
    case 'STATE_UPDATE':
      handleStateUpdate(msg.state);
      break;
    case 'FLOW_PROGRESS':
      handleFlowProgress(msg.phase, msg.detail);
      break;
    case 'SNAPSHOT_RESULT':
      // Snapshot result received
      break;
    case 'DEPENDENCY_GRAPH':
      updateDependencyGraph(msg.graph);
      break;
    case 'ACTIVE_FILE_CHANGED':
      highlightFile(msg.file);
      break;
  }
});

function handleStateUpdate(state: StateSnapshot) {
  currentState = { ...state };
  
  if (!state.busy) {
    hideProcessing();
  }
  
  updateStats(state);
  updateFindingsDisplay();
  updateKbStaleIndicator(state.kbStale ?? false);
  
  // Generate mock dependency graph for demonstration
  if (state.findings.length > 0) {
    generateMockDependencyGraph(state);
  }
}

function handleFlowProgress(phase: string, detail?: any) {
  const phaseMessages = {
    'index': 'Indexing repository...',
    'validate': 'Running analysis...',
    'preview_fixes': 'Preparing fixes...',
    'apply': 'Applying changes...'
  };
  
  const phaseProgress = {
    'index': 25,
    'validate': 75,
    'preview_fixes': 90,
    'apply': 100
  };
  
  const message = phaseMessages[phase as keyof typeof phaseMessages] || `Processing ${phase}...`;
  const progress = phaseProgress[phase as keyof typeof phaseProgress] || 50;
  
  showProcessing(message, progress);
}

function generateMockDependencyGraph(state: StateSnapshot) {
  // Generate a mock dependency graph based on findings
  // In real implementation, this would come from the actual dependency analysis
  const fileSet = new Set(state.findings.map(f => f.file));
  const files = Array.from(fileSet).slice(0, 10); // Limit for demo
  
  const nodes = files.map((file, i) => ({
    id: file,
    label: file.split('/').pop() || file,
    type: (i < 3 ? 'hub' : 'file') as 'hub' | 'file',
    importance: state.findings.filter(f => f.file === file).length,
    file
  }));
  
  const links = [];
  for (let i = 0; i < Math.min(files.length - 1, 8); i++) {
    links.push({
      source: files[i],
      target: files[i + 1],
      strength: Math.random()
    });
  }
  
  updateDependencyGraph({ nodes, links });
}

/**
 * Update KB stale indicator in the UI.
 */
function updateKbStaleIndicator(isStale: boolean) {
  const indicator = document.getElementById('kb-stale-indicator');
  if (!indicator) return;
  
  if (isStale) {
    indicator.style.display = 'flex';
  } else {
    indicator.style.display = 'none';
  }
}

/**
 * Handle regenerate KB button click.
 */
function handleRegenerateKb() {
  vscode.postMessage({ type: 'REGENERATE_KB' } as RegenerateKbMsg);
}

// Initialize on script load
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    // Wire up regenerate button
    const regenBtn = document.getElementById('btn-regenerate-kb');
    if (regenBtn) {
      regenBtn.addEventListener('click', handleRegenerateKb);
    }
    vscode.postMessage({ type: 'PANEL_READY' });
  });
} else {
  // Wire up regenerate button
  const regenBtn = document.getElementById('btn-regenerate-kb');
  if (regenBtn) {
    regenBtn.addEventListener('click', handleRegenerateKb);
  }
  vscode.postMessage({ type: 'PANEL_READY' });
}



