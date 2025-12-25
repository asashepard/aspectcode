import * as vscode from 'vscode';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { generateKnowledgeBase } from './kb';

const ASPECT_CODE_START = '<!-- ASPECT_CODE_START -->';
const ASPECT_CODE_END = '<!-- ASPECT_CODE_END -->';

// ─────────────────────────────────────────────────────────────────────────────
// Canonical instruction content - all exports derive from this
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Generates the canonical instruction content.
 * All assistant-specific exports are derived from this single source.
 */
function generateCanonicalContent(): string {
  return `## Aspect Code Knowledge Base

Before multi-file edits, read the KB files in \`.aspect/\`:

| File | Contains | When to Read |
|------|----------|--------------|
| \`architecture.md\` | High-risk hubs, entry points, circular deps | **Always first** |
| \`map.md\` | Data models, symbol index, naming conventions | Before modifying functions |
| \`context.md\` | Module clusters, external integrations, data flows | Before architectural changes |

---

## Workflow Checklist

1. **Parse the task** → Identify which files/endpoints are involved
2. **Read \`architecture.md\`** → Find high-risk hubs (3+ dependents) and entry points
3. **Read \`map.md\`** → Locate relevant symbols; check "Called by" for blast radius
4. **Read \`context.md\`** → See which files are commonly co-edited (module clusters)
5. **Plan minimal change** → Target the smallest, safest location
6. **Implement** → Preserve all existing exports; match naming conventions
7. **Verify** → Run tests; check you didn't break callers

---

## Core Rules

**Do:**
- Read the complete file before modifying it
- Add code; don't reorganize unless explicitly asked
- Match naming patterns shown in \`map.md\`
- Check "Called by" in \`map.md\` before renaming/deleting symbols

**Don't:**
- Edit files with 5+ dependents without acknowledging the risk
- Create circular dependencies (check \`architecture.md\`)
- Use placeholders like \`// ...rest\` — provide complete code
- Touch tests, migrations, or third-party code unless asked

---

## Editing Hub Files

Hub files have many dependents — changes ripple widely. Before editing:

1. Confirm the file is in \`architecture.md\` → \`## High-Risk Architectural Hubs\`
2. Check dependent count (e.g., "8 dependents" = high risk)
3. Prefer **additive changes** (new functions) over modifying existing signatures
4. If you must change a signature, update all callers listed in "Called by"

**Example:** If \`models.py\` has 8 dependents, adding a new field is safer than renaming an existing one.

---

## MCP Tools

If MCP is configured, query the dependency graph programmatically:

| Tool | Use Case |
|------|----------|
| \`get_file_dependents\` | What files import this file? (blast radius) |
| \`get_file_dependencies\` | What does this file import? |
| \`get_architectural_hubs\` | Find files with N+ dependents |
| \`get_circular_dependencies\` | Detect import cycles |
| \`get_impact_analysis\` | Cascading impact of changes |

**Example:**
\`\`\`json
{ "tool": "get_file_dependents", "arguments": { "file_path": "src/utils/helpers.ts" } }
\`\`\`
→ Returns files affected by changes to \`helpers.ts\`
`.trim();
}

/**
 * Generates or updates instruction files for configured AI assistants.
 */
export async function generateInstructionFiles(
  workspaceRoot: vscode.Uri,
  state: AspectCodeState,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel,
  context?: vscode.ExtensionContext
): Promise<void> {
  // Always generate KB files first
  await generateKnowledgeBase(workspaceRoot, state, scoreResult, outputChannel, context);

  // Read assistant settings
  const config = vscode.workspace.getConfiguration('aspectcode.assistants');
  const wantCopilot = config.get<boolean>('copilot', false);
  const wantCursor = config.get<boolean>('cursor', false);
  const wantClaude = config.get<boolean>('claude', false);
  const wantOther = config.get<boolean>('other', false);

  outputChannel.appendLine(`[Instructions] Generating instruction files (Copilot: ${wantCopilot}, Cursor: ${wantCursor}, Claude: ${wantClaude}, Other: ${wantOther})`);

  const promises: Promise<void>[] = [];

  if (wantCopilot) {
    promises.push(generateCopilotInstructions(workspaceRoot, scoreResult, outputChannel));
  }

  if (wantCursor) {
    promises.push(generateCursorRules(workspaceRoot, outputChannel));
  }

  if (wantClaude) {
    promises.push(generateClaudeInstructions(workspaceRoot, scoreResult, outputChannel));
  }

  if (wantOther) {
    promises.push(generateOtherInstructions(workspaceRoot, scoreResult, outputChannel));
  }

  await Promise.all(promises);

  outputChannel.appendLine('[Instructions] Instruction file generation complete');
}

/**
 * Generate/update .github/copilot-instructions.md
 */
async function generateCopilotInstructions(
  workspaceRoot: vscode.Uri,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const githubDir = vscode.Uri.joinPath(workspaceRoot, '.github');
  const instructionsFile = vscode.Uri.joinPath(githubDir, 'copilot-instructions.md');

  // Ensure .github directory exists
  try {
    await vscode.workspace.fs.createDirectory(githubDir);
  } catch {}

  const aspectCodeContent = generateCopilotContent();

  let existingContent = '';
  try {
    const bytes = await vscode.workspace.fs.readFile(instructionsFile);
    existingContent = Buffer.from(bytes).toString('utf-8');
  } catch {
    // File doesn't exist yet
  }

  const newContent = mergeAspectCodeSection(existingContent, aspectCodeContent);

  await vscode.workspace.fs.writeFile(instructionsFile, Buffer.from(newContent, 'utf-8'));
  outputChannel.appendLine('[Instructions] Generated .github/copilot-instructions.md');
}

function generateCopilotContent(): string {
  return `${generateCanonicalContent()}

---

## Copilot Tips

- Use \`@.aspect/architecture.md\` to include KB context in chat
- Ask "Show me only the lines to change" to keep edits minimal
- Reference \`@.aspect/map.md\` when asking about naming conventions
`.trim();
}

/**
 * Generate/update .cursor/rules/aspectcode.mdc
 */
async function generateCursorRules(
  workspaceRoot: vscode.Uri,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const cursorDir = vscode.Uri.joinPath(workspaceRoot, '.cursor', 'rules');
  const rulesFile = vscode.Uri.joinPath(cursorDir, 'aspectcode.mdc');

  // Ensure .cursor/rules directory exists
  try {
    await vscode.workspace.fs.createDirectory(cursorDir);
  } catch {}

  const content = generateCursorContent();

  await vscode.workspace.fs.writeFile(rulesFile, Buffer.from(content, 'utf-8'));
  outputChannel.appendLine('[Instructions] Generated .cursor/rules/aspectcode.mdc');
}

function generateCursorContent(): string {
  return `---
description: Aspect Code KB integration - read before multi-file edits
globs: 
alwaysApply: true
---

${generateCanonicalContent()}

---

## Cursor Tips

- Read KB files before using Composer for multi-file edits
- Check \`architecture.md\` for hub files before agent-mode refactors
- Use "Called by" in \`map.md\` to find all usages before renaming
`.trim();
}

/**
 * Generate/update CLAUDE.md with Aspect Code section
 */
async function generateClaudeInstructions(
  workspaceRoot: vscode.Uri,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const claudeFile = vscode.Uri.joinPath(workspaceRoot, 'CLAUDE.md');

  const aspectCodeContent = generateClaudeContent();

  let existingContent = '';
  try {
    const bytes = await vscode.workspace.fs.readFile(claudeFile);
    existingContent = Buffer.from(bytes).toString('utf-8');
  } catch {
    // File doesn't exist, create new one
    existingContent = '# Claude Code Instructions\n\n';
  }

  const newContent = mergeAspectCodeSection(existingContent, aspectCodeContent);

  await vscode.workspace.fs.writeFile(claudeFile, Buffer.from(newContent, 'utf-8'));
  outputChannel.appendLine('[Instructions] Generated CLAUDE.md');
}

function generateClaudeContent(): string {
  return `${generateCanonicalContent()}

---

## Claude Tips

- Summarize what you found in KB files before proposing changes
- State "This file has N dependents" when editing hubs
- Use \`@.aspect/architecture.md\` to reference KB in chat
`.trim();
}

/**
 * Generate/update AGENTS.md with Aspect Code section for other AI coding assistants
 */
async function generateOtherInstructions(
  workspaceRoot: vscode.Uri,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  const agentsFile = vscode.Uri.joinPath(workspaceRoot, 'AGENTS.md');

  const aspectCodeContent = generateCanonicalContent();

  let existingContent = '';
  try {
    const bytes = await vscode.workspace.fs.readFile(agentsFile);
    existingContent = Buffer.from(bytes).toString('utf-8');
  } catch {
    // File doesn't exist, create new one
    existingContent = '# AI Coding Agent Instructions\n\n';
  }

  const newContent = mergeAspectCodeSection(existingContent, aspectCodeContent);

  await vscode.workspace.fs.writeFile(agentsFile, Buffer.from(newContent, 'utf-8'));
  outputChannel.appendLine('[Instructions] Generated AGENTS.md');
}

/**
 * Merges Aspect Code content into existing file using markers.
 * If markers exist, replaces content between them.
 * If not, appends new section with markers.
 */
function mergeAspectCodeSection(existingContent: string, aspectCodeContent: string): string {
  const startIndex = existingContent.indexOf(ASPECT_CODE_START);
  const endIndex = existingContent.indexOf(ASPECT_CODE_END);

  if (startIndex !== -1 && endIndex !== -1 && endIndex > startIndex) {
    // Markers exist, replace content between them
    const before = existingContent.substring(0, startIndex + ASPECT_CODE_START.length);
    const after = existingContent.substring(endIndex);
    return `${before}\n${aspectCodeContent}\n${after}`;
  } else {
    // No markers, append new section
    const separator = existingContent.trim().length > 0 ? '\n\n' : '';
    return `${existingContent}${separator}${ASPECT_CODE_START}\n${aspectCodeContent}\n${ASPECT_CODE_END}\n`;
  }
}

