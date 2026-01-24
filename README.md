<div align="center">

# Aspect Code

**Knowledge Base Generator for AI Coding Assistants**

</div>

---

## Overview

This repo contains the VS Code extension.

Development happens in the open on GitHub, and contributions are welcome.
See CONTRIBUTING.md for how to propose changes.

- Marketplace/end-user README: see extension/README.md
- Docs: https://aspectcode.com/docs

## Install

- VS Code Marketplace: https://marketplace.visualstudio.com/items?itemName=aspectcode.aspectcode
- Or download the `.vsix` from the GitHub Release for a tag (see below) and install via "Extensions: Install from VSIX…"

## Features

- **Knowledge Base generation** — Writes `.aspect/architecture.md`, `.aspect/map.md`, and `.aspect/context.md`
- **AI instruction files** — Generates assistant-friendly instruction files for Copilot, Cursor, Claude, AGENTS.md
- **Dependency visualization** — Interactive graph in the sidebar panel
- **Incremental updates** — Regenerates on save/idle (configurable via `.aspect/.settings.json`)

## Supported Languages

Primary support: Python, TypeScript, JavaScript, Java, C#

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        VS Code Extension                        │
├─────────────────────────────────────────────────────────────────┤
│  extension.ts                                                   │
│  ├── Activation & lifecycle                                     │
│  ├── File watchers (KB staleness, settings refresh)             │
│  └── Tree-sitter grammar initialization                         │
├─────────────────────────────────────────────────────────────────┤
│  commandHandlers.ts                                             │
│  ├── Command registration (configureAssistants, modes, etc.)   │
│  └── File watchers (instruction files, assistant configs)       │
├─────────────────────────────────────────────────────────────────┤
│  panel/PanelProvider.ts                                         │
│  ├── Sidebar webview UI (inline HTML/JS)                        │
│  ├── Dependency graph visualization                             │
│  └── Settings controls                                          │
├─────────────────────────────────────────────────────────────────┤
│  assistants/                                                    │
│  ├── kb.ts           → KB file generation (architecture/map/    │
│  │                     context.md with strict line budgets)     │
│  ├── instructions.ts → Instruction file generation              │
│  │                     (safe/permissive/custom modes)           │
│  └── detection.ts    → Auto-detect installed AI assistants      │
├─────────────────────────────────────────────────────────────────┤
│  services/                                                      │
│  ├── DependencyAnalyzer.ts   → Import/export/call graph         │
│  ├── FileDiscoveryService.ts → Cached workspace file discovery  │
│  ├── WorkspaceFingerprint.ts → KB staleness detection           │
│  ├── aspectSettings.ts       → .aspect/.settings.json I/O       │
│  ├── DirectoryExclusion.ts   → Glob exclusion patterns          │
│  └── gitignoreService.ts     → .gitignore management            │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
extension/
├── src/
│   ├── extension.ts           # Entry point, activation, file watchers
│   ├── commandHandlers.ts     # Command registration and handlers
│   ├── state.ts               # Panel state management
│   ├── tsParser.ts            # Tree-sitter grammar loading
│   ├── importExtractors.ts    # Tree-sitter import/symbol extraction
│   │
│   ├── assistants/
│   │   ├── kb.ts              # KB generation (4k+ lines)
│   │   │                      # Generates architecture.md, map.md, context.md
│   │   │                      # Strict line budgets (200/300/200) for AI context
│   │   ├── instructions.ts    # Instruction file generation
│   │   │                      # Modes: safe, permissive, custom, off
│   │   │                      # Inserts between <!-- ASPECT:BEGIN/END --> markers
│   │   └── detection.ts       # Auto-detect AI assistants by config files
│   │
│   ├── panel/
│   │   └── PanelProvider.ts   # Sidebar webview (5k+ lines)
│   │                          # Inline HTML/JS, dependency graph, settings UI
│   │
│   ├── services/
│   │   ├── DependencyAnalyzer.ts    # Import/export/call graph (1.2k lines)
│   │   │                            # Pre-built indexes for O(1) lookups
│   │   ├── FileDiscoveryService.ts  # Cached file discovery (700 lines)
│   │   │                            # Single source of truth for workspace files
│   │   ├── WorkspaceFingerprint.ts  # KB staleness detection (450 lines)
│   │   │                            # Stores .aspect/.fingerprint.json
│   │   ├── aspectSettings.ts        # .aspect/.settings.json read/write
│   │   ├── DirectoryExclusion.ts    # Exclusion glob patterns
│   │   ├── gitignoreService.ts      # .gitignore management
│   │   └── enablementCancellation.ts # Cancellation token utilities
│   │
│   └── test/
│       └── kb.test.ts         # KB generation tests
│
├── parsers/                   # Tree-sitter WASM grammars
├── media/                     # Icons and assets
├── scripts/                   # Build scripts
├── package.json               # Extension manifest
└── tsconfig.json
```

---

## Key Components

### KB Generation (`assistants/kb.ts`)

Generates three markdown files with strict line budgets to fit within AI context windows:

| File | Budget | Content |
|------|--------|--------|
| `architecture.md` | 200 lines | High-risk hubs, directory tree, entry points |
| `map.md` | 300 lines | Data models, symbol index, naming conventions |
| `context.md` | 200 lines | Module clusters, external integrations, data flows |

### Instruction Generation (`assistants/instructions.ts`)

Generates instruction files with content between `<!-- ASPECT:BEGIN -->` and `<!-- ASPECT:END -->` markers. User content outside markers is preserved on regeneration.

| Mode | Behavior |
|------|----------|
| Safe | Full guardrails — testing, imports, error handling rules |
| Permissive | Minimal rules — trusts AI to follow KB context |
| Custom | User-provided `.aspect/instructions.md` content |
| Off | No instruction files |

### Dependency Analysis (`services/DependencyAnalyzer.ts`)

Analyzes imports, exports, calls, and inheritance relationships. Builds pre-indexed maps for:
- Files importing a given file
- Files imported by a given file
- Circular dependency detection
- Hub file identification (high in-degree)

### Workspace Fingerprint (`services/WorkspaceFingerprint.ts`)

Tracks KB staleness using a cheap fingerprint (file paths + mtime + size). Supports auto-regeneration on save or after idle period.

---

## Extension Flows

### Activation (when VS Code opens workspace)

```
activate()
├── Create output channel + status bar
├── Initialize AspectCodeState, load persisted state
├── Register PanelProvider webview
├── Migrate settings (.vscode/settings.json → .aspect/.settings.json)
├── Initialize FileDiscoveryService singleton
├── Initialize WorkspaceFingerprint
│   └── Set up KB regeneration callback
├── Set up file watchers:
│   ├── .aspect/.settings.json → refresh KB mode
│   ├── Source files (*.ts, *.py, etc.) → staleness detection
│   └── Instruction files → UI updates
├── Check if KB is stale on startup
└── activateCommands() → register all commands
```

### File Change Detection

File watchers monitor workspace changes:

| Watcher | Pattern | Purpose |
|---------|---------|---------|
| Source files | `*.{ts,tsx,js,py,...}` | KB staleness via WorkspaceFingerprint |
| .aspect/ | `**/.aspect{,/**}` | UI updates, instruction file detection |
| Instruction files | `**/{AGENTS,CLAUDE}.md` | Assistant detection |
| Config folders | `.github/`, `.cursor/` | Assistant config detection |

On source file change:
1. `onDidSave` → `WorkspaceFingerprint.checkStaleAndRegenerateIfNeeded()`
2. If stale + autoRegenerate enabled → debounced `regenerateEverything()`
3. Panel receives staleness state update

### KB Generation Flow

```
User clicks "+" or "Regenerate" (or auto-save triggers)
         ↓
regenerateEverything() [kb.ts]
├── Check if .aspect/ exists (skip if not)
├── Load tree-sitter grammars (cached)
├── discoverWorkspaceFiles() via FileDiscoveryService
├── preloadFileContents() → Map<string, string>
├── getDetailedDependencyData() via DependencyAnalyzer
└── PARALLEL generation:
    ├── generateArchitectureFile() → .aspect/architecture.md
    ├── generateMapFile() → .aspect/map.md
    └── generateContextFile() → .aspect/context.md
         ↓
workspaceFingerprint.markKbFresh()
         ↓
panelProvider.refreshDependencyGraph()
```

### Data Storage

| Storage | Location | Data |
|---------|----------|------|
| VS Code globalState | Extension storage | Panel state, first-run flag |
| VS Code workspaceState | Workspace storage | Notification suppressions |
| `.aspect/.settings.json` | Workspace | autoRegenerateKb, instructions.mode, enabled, assistants |
| `.aspect/.fingerprint.json` | Workspace | KB staleness (hash, timestamp, file count) |
| In-memory caches | Runtime | File contents, parsers, dependency graph, discovered files |

---

## Development

Build the extension:

```bash
cd extension
npm install
npm run build
```

Package a VSIX locally:

```bash
cd extension
npx --yes @vscode/vsce package --pre-release
```

## Releases

Pushing a tag like `v0.1.1` creates a GitHub Release with the `.vsix` attached (via .github/workflows/release.yml).

If you prefer installing from a file, open the GitHub Release for the tag and download the `.vsix` from the **Assets** section.

## License

See LICENSE.md.


