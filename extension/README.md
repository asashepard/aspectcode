# Aspect Code

**AI-Powered Static Analysis for Modern Development**

![Status](https://img.shields.io/badge/status-alpha-orange)
![Languages](https://img.shields.io/badge/languages-5-blue)
![Rules](https://img.shields.io/badge/rules-27+-green)

*Fewer errors. Better structure. Less time debugging AI responses.*

---

## Features

### 🔍 Smart Analysis
Detects security vulnerabilities, bugs, concurrency issues, complexity problems, and architectural patterns using Tree-sitter-powered parsing.

### 🤖 AI Integration
Generates instruction files for GitHub Copilot, Cursor, Claude, and other AI assistants. Your AI tools will understand your codebase better.

### 📚 Knowledge Base Generation
Creates `.aspect/` directories containing structured documentation:
- Architectural diagrams
- Code conventions
- Data flows
- Dependency graphs
- High-impact areas

### ⚡ Fast & Incremental
Tree-sitter-based parsing with smart incremental indexing for rapid feedback.

---

## Supported Languages

| Language | Status |
|----------|--------|
| Python | ✅ Primary |
| TypeScript | ✅ Primary |
| JavaScript | ✅ Primary |
| Java | ✅ Primary |
| C# | ✅ Primary |
| Go | Experimental |
| C / C++ | Experimental |

---

## Getting Started

1. Install the extension from the VS Code Marketplace
2. Open a workspace with supported source files
3. The extension activates automatically and begins analysis
4. View findings in the Aspect Code panel (activity bar)

---

## Commands

| Command | Description |
|---------|-------------|
| `Aspect Code: Scan Workspace` | Analyze all files in the workspace |
| `Aspect Code: Scan Active File` | Analyze the current file |
| `Aspect Code: Show Panel` | Open the Aspect Code panel |
| `Aspect Code: Configure Rule Categories` | Enable/disable rule categories |
| `Aspect Code: Generate Knowledge Base` | Create AI context files |

---

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| `aspectcode.serverBaseUrl` | Backend server URL | `https://api.aspectcode.dev` |
| `aspectcode.enabledCategories` | Rule categories to enable | All enabled |
| `aspectcode.extensionEnabled` | Enable/disable analysis | `true` |

---

## Rule Categories

The **alpha_default** profile includes curated rules across:

- **Security** — SQL injection, hardcoded secrets, path traversal
- **Bugs** — Float equality, iteration modification, null dereference
- **Concurrency** — Unreleased locks, blocking in async contexts
- **Complexity** — Cyclomatic complexity, deep nesting, long functions
- **Dead Code** — Unused variables, unused imports
- **Errors** — Swallowed exceptions, broad catch blocks
- **Architecture** — Global state usage, circular dependencies
- **Style** — Mixed indentation, trailing whitespace

---

## Requirements

- VS Code 1.92.0 or higher
- Internet connection for analysis (uses cloud API)

---

## Privacy

Aspect Code sends code snippets to our analysis server for processing. We do not store your code permanently. See our [privacy policy](https://github.com/aspect-code/aspectcode#privacy) for details.

---

## Feedback & Issues

Found a bug or have a suggestion? [Open an issue](https://github.com/aspect-code/aspectcode/issues) on GitHub.

---

## License

Proprietary. See [LICENSE.md](LICENSE.md) for details.

© 2025-2026 Aspect Code. All rights reserved.
