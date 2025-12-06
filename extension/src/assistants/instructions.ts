import * as vscode from 'vscode';
import { AspectCodeState } from '../state';
import { ScoreResult } from '../scoring/scoreEngine';
import { generateKnowledgeBase } from './kb';

const ASPECT_CODE_START = '<!-- ASPECT_CODE_START -->';
const ASPECT_CODE_END = '<!-- ASPECT_CODE_END -->';

// ─────────────────────────────────────────────────────────────────────────────
// Shared content blocks for standardized instruction structure
// ─────────────────────────────────────────────────────────────────────────────

const INTRO_BLOCK = `
**Aspect Code** is a static-analysis extension that generates a Knowledge Base (KB) for your codebase. The KB lives in \`.aspect/\` and contains these files:

| File | Purpose |
|------|---------|  
| \`structure.md\` | Directory layout, hub modules, circular dependencies |
| \`awareness.md\` | Supplementary context on high-impact files and patterns to watch |
| \`code.md\` | Data models + function/class index with call relationships |
| \`flows.md\` | Entry points, external integrations, and data flow paths |
| \`conventions.md\` | Naming patterns, import styles, framework idioms |

**Key architectural intelligence:**
- **Entry Points** in \`flows.md\`: HTTP handlers, CLI commands, event listeners
- **External Integrations** in \`flows.md\`: API clients, database connections, message queues
- **Data Models** in \`code.md\`: ORM models, dataclasses, TypeScript interfaces

Read the relevant KB files **before** making multi-file changes.
`.trim();

const GOLDEN_RULES = `
## Golden Rules

1. **Read before you write.** Open the relevant \`.aspect/*.md\` files before multi-file edits.
2. **Check structure first.** Understand the codebase architecture before coding.
3. **Think step-by-step.** Break complex tasks into smaller steps; reason through each before coding.
4. **Prefer minimal, local changes.** Small patches are safer than large refactors, especially in hub files.
5. **Never truncate code.** Don't use placeholders like \`// ...rest\` or \`# existing code...\`. Provide complete implementations.
6. **Don't touch tests** unless the task explicitly says to or the tests are clearly wrong.
7. **Never remove referenced logic.** If a symbol appears in \`code.md\` or \`flows.md\`, check all callers before deleting.
8. **Understand blast radius.** Use \`flows.md\` and \`code.md\` to trace call chains before refactors.
9. **Follow conventions.md.** Match the project's existing naming patterns and import styles.
10. **When unsure, go small.** Propose a minimal, reversible change instead of a sweeping refactor.
`.trim();

const WORKFLOW_STEPS = `
## Recommended Workflow

1. **Understand the task.** Parse requirements; note which files or endpoints are involved.
2. **Check structure.** Open \`structure.md\` → locate the correct module/layer and check hub modules.
3. **Follow conventions.** Open \`conventions.md\` → match naming patterns and import styles.
4. **Trace symbols.** Open \`code.md\` → find the function/class; review "Called by" to gauge impact.
5. **Trace flows.** Open \`flows.md\` → see if the symbol is on a critical path.
6. **Review awareness.** Open \`awareness.md\` → note high-impact areas and patterns to watch.
7. **Gather evidence.** If behavior is unclear, add targeted logging or traces to confirm assumptions.
8. **Make minimal edits.** Implement the smallest change that solves the task; run tests.
`.trim();

const CHANGE_RULES = `
## When Changing Code

- **Read the COMPLETE file** before modifying it. Preserve all existing exports/functions.
- **Add, don't reorganize.** Unless the task says "refactor", avoid moving code around.
- **Check hub modules** (\`structure.md\`) before editing widely-imported files.
- **Avoid renaming** widely-used symbols listed in \`code.md\` without updating all callers.
- **No new cycles.** Before adding an import, verify it won't create a circular dependency (\`structure.md\`).
- **Match conventions.** Follow patterns in \`conventions.md\` (naming, imports, frameworks).
- **Watch high-impact areas.** Note patterns flagged in \`awareness.md\` when editing related code.
`.trim();

const KB_USAGE = `
## How to Use the KB Files

| File | When to Open | What to Look For |
|------|--------------|------------------|
| \`structure.md\` | **First, always** | Directory layout, hub modules, circular dependencies |
| \`code.md\` | Before modifying a function | "Called by" examples, data models, impact radius |
| \`flows.md\` | Before architectural changes | Entry points, external integrations, data flow paths |
| \`conventions.md\` | When writing new code | Naming patterns, import styles, framework idioms |
| \`awareness.md\` | For supplementary context | High-impact files, security notes, patterns to watch |

### Quick Reference

- **Entry points** → HTTP handlers, CLI commands, event listeners in \`flows.md\`
- **External integrations** → HTTP clients, DB connections, message queues in \`flows.md\`
- **Data models** → ORM models, dataclasses, interfaces in \`code.md\`
- **Hub module** → listed in \`structure.md\` or \`flows.md\` with high traffic
- **High-impact symbol** → 5+ callers in \`code.md\` "Called by" column
- **High-impact file** → listed in \`awareness.md\` with notes on what to watch
`.trim();

const TROUBLESHOOTING = `
## When Things Go Wrong

If you encounter repeated errors or unexpected behavior:

1. **Use git** to see what changed: \`git diff\`, \`git status\`
2. **Restore lost code** with \`git checkout -- <file>\` if needed
3. **Re-read the complete file** before making more changes
4. **Trace data flows** using \`flows.md\` to understand execution paths
5. **Run actual tests** to verify behavior before assuming something works
6. **Check awareness.md** for notes on high-impact areas and patterns to watch
`.trim();

/**
 * Generates or updates instruction files for configured AI assistants.
 */
export async function generateInstructionFiles(
  workspaceRoot: vscode.Uri,
  state: AspectCodeState,
  scoreResult: ScoreResult | null,
  outputChannel: vscode.OutputChannel
): Promise<void> {
  // Always generate KB files first
  await generateKnowledgeBase(workspaceRoot, state, scoreResult, outputChannel);

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

  const aspectCodeContent = generateCopilotContent(scoreResult);

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

function generateCopilotContent(scoreResult: ScoreResult | null): string {
  // Copilot-specific: emphasize file-local context and @-references
  return `
## Aspect Code Knowledge Base

${INTRO_BLOCK}

Use \`@.aspect/<file>.md\` syntax to reference KB files in Copilot Chat.

${GOLDEN_RULES}

${WORKFLOW_STEPS}

${CHANGE_RULES}

${KB_USAGE}

${TROUBLESHOOTING}

## Copilot-Specific Tips

- **Use @-references.** Type \`@.aspect/structure.md\` to include KB context in chat.
- **Check structure first.** Understand codebase architecture before coding.
- **Ask for small patches.** "Show me only the lines to change" keeps edits minimal.
- **One file at a time.** When editing, work on a single file before moving on.
- **Match conventions.** Ask "What naming pattern should I use?" and reference \`conventions.md\`.

## Section Headers (Pattern-Matching)

**\`structure.md\`:** \`## Directory Layout\`, \`## Hub Modules\`, \`## Circular Dependencies\`
**\`awareness.md\`:** \`## High-Impact Files\`, \`## Security & Correctness Notes\`, \`## Patterns to Watch\`
**\`code.md\`:** \`## Data Models\` (ORM, dataclasses, interfaces), \`## <file path>\` with Symbol | Kind | Calls | Called By
**\`flows.md\`:** \`## Entry Points\` (HTTP handlers, CLI, events), \`## External Integrations\` (API clients, DB, queues), \`## Hub Module Flows\`
**\`conventions.md\`:** \`## File Naming\`, \`## Function Naming\`, \`## Framework Patterns\`
`.trim();
}

/**
 * Generate/update .cursor/rules/Aspect Code.mdc
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
  outputChannel.appendLine('[Instructions] Generated .cursor/rules/Aspect Code.mdc');
}

function generateCursorContent(): string {
  // Cursor-specific: lean into multi-file edits but enforce KB-driven plans
  return `---
title: Aspect Code Knowledge Base
tags: [architecture, dependencies, Aspect Code]
priority: always
---

# Aspect Code Knowledge Base

${INTRO_BLOCK}

${GOLDEN_RULES}

${WORKFLOW_STEPS}

${CHANGE_RULES}

${KB_USAGE}

${TROUBLESHOOTING}

## Cursor-Specific Tips

- **Check structure first.** Know the codebase layout and hub files before writing code.
- **Plan before multi-file edits.** Even with Cursor's agent mode, read KB files first.
- **Follow conventions.md.** Match naming patterns and import styles consistently.
- **Check callers before renaming.** Use \`code.md\` to find all usages.
- **Avoid wide-scope refactors** unless the task explicitly calls for them.

## Section Headers (Pattern-Matching)

**\`structure.md\`:** \`## Directory Layout\`, \`## Hub Modules\`, \`## Circular Dependencies\`
**\`awareness.md\`:** \`## High-Impact Files\`, \`## Security & Correctness Notes\`, \`## Patterns to Watch\`
**\`code.md\`:** \`## Data Models\` (ORM, dataclasses, interfaces), \`## <file path>\` with Symbol | Kind | Calls | Called By
**\`flows.md\`:** \`## Entry Points\` (HTTP handlers, CLI, events), \`## External Integrations\` (API clients, DB, queues), \`## Hub Module Flows\`
**\`conventions.md\`:** \`## File Naming\`, \`## Function Naming\`, \`## Framework Patterns\`
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

  const aspectCodeContent = generateClaudeContent(scoreResult);

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

function generateClaudeContent(scoreResult: ScoreResult | null): string {
  // Claude-specific: encourage plan + patch style with explicit KB summarization
  return `
## Aspect Code Knowledge Base

${INTRO_BLOCK}

Reference KB files using: \`@.aspect/<file>.md\`

${GOLDEN_RULES}

${WORKFLOW_STEPS}

${CHANGE_RULES}

${KB_USAGE}

${TROUBLESHOOTING}

## Claude-Specific Tips

- **Check structure first.** Understand codebase layout and hub files before proposing solutions.
- **OBSERVATIONS → REASONING → PLAN.** State what you observed, why it's the issue, then your approach.
- **Summarize KB findings.** Before writing code, state what you learned from each KB file.
- **Plan, then patch.** Outline your approach (which files, what changes) before providing code.
- **Follow conventions.md.** Match naming patterns and styles exactly.
- **Cite risk levels.** If touching a hub module or high-impact file, acknowledge it explicitly.

## Example Workflow

1. **"OBSERVATIONS: I see X in the code…"** → Describe what you found.
2. **"REASONING: This causes Y because…"** → Explain why it's the issue.
3. **"PLAN: I'll fix by changing Z in file A…"** → State your approach.
4. **"Based on \`structure.md\`, \`models.py\` is a hub (8 importers)…"** → Acknowledge risk.
5. **"Awareness.md notes this area needs care…"** → Note contextual considerations.
6. **"Here's the patch:"** → Provide minimal, complete code changes.

## Section Headers (Pattern-Matching)

**\`structure.md\`:** \`## Directory Layout\`, \`## Hub Modules\`, \`## Circular Dependencies\`
**\`awareness.md\`:** \`## High-Impact Files\`, \`## Security & Correctness Notes\`, \`## Patterns to Watch\`
**\`code.md\`:** \`## Data Models\` (ORM, dataclasses, interfaces), \`## <file path>\` with Symbol | Kind | Calls | Called By
**\`flows.md\`:** \`## Entry Points\` (HTTP handlers, CLI, events), \`## External Integrations\` (API clients, DB, queues), \`## Hub Module Flows\`
**\`conventions.md\`:** \`## File Naming\`, \`## Function Naming\`, \`## Framework Patterns\`
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

  const aspectCodeContent = generateOtherContent(scoreResult);

  let existingContent = '';
  try {
    const bytes = await vscode.workspace.fs.readFile(agentsFile);
    existingContent = Buffer.from(bytes).toString('utf-8');
  } catch {
    // File doesn't exist, create new one
    existingContent = '# AI Coding Agent Instructions\n\nThis file provides instructions for AI coding assistants working on this codebase.\n\n';
  }

  const newContent = mergeAspectCodeSection(existingContent, aspectCodeContent);

  await vscode.workspace.fs.writeFile(agentsFile, Buffer.from(newContent, 'utf-8'));
  outputChannel.appendLine('[Instructions] Generated AGENTS.md');
}

function generateOtherContent(scoreResult: ScoreResult | null): string {
  // Generic instructions for any AI coding assistant
  return `
## Aspect Code Knowledge Base

${INTRO_BLOCK}

Reference KB files at: \`.aspect/<file>.md\`

${GOLDEN_RULES}

${WORKFLOW_STEPS}

${CHANGE_RULES}

${KB_USAGE}

${TROUBLESHOOTING}

## General Guidelines

- **Read KB files first.** Before making changes, consult the relevant knowledge base files.
- **Start with structure.md.** Understand the codebase layout and architecture.
- **Check hub modules.** Know which files have many dependents before editing.
- **Follow conventions.md.** Match existing naming patterns and coding styles exactly.
- **Minimal changes.** Make the smallest change that solves the problem correctly.
- **Acknowledge risk.** If editing a hub module or high-impact file, note the elevated risk.

## KB File Reference

| File | Purpose |
|------|---------||
| \`structure.md\` | Project layout, hub modules, dependency info |
| \`awareness.md\` | Supplementary context on high-impact areas |
| \`code.md\` | Symbol tables with call relationships, data models |
| \`flows.md\` | Entry points, external integrations, data flow patterns |
| \`conventions.md\` | Naming conventions and framework patterns |

## Section Headers (Pattern-Matching)

**\`structure.md\`:** \`## Directory Layout\`, \`## Hub Modules\`, \`## Circular Dependencies\`
**\`awareness.md\`:** \`## High-Impact Files\`, \`## Security & Correctness Notes\`, \`## Patterns to Watch\`
**\`code.md\`:** \`## Data Models\` (ORM, dataclasses, interfaces), \`## <file path>\` with Symbol | Kind | Calls | Called By
**\`flows.md\`:** \`## Entry Points\` (HTTP handlers, CLI, events), \`## External Integrations\` (API clients, DB, queues), \`## Hub Module Flows\`
**\`conventions.md\`:** \`## File Naming\`, \`## Function Naming\`, \`## Framework Patterns\`
`.trim();
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

