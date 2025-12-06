<div align="center">

# Aspect Code

**AI-Powered Static Analysis for Modern Development**

[![Status](https://img.shields.io/badge/status-alpha-orange)]()
[![Languages](https://img.shields.io/badge/languages-5-blue)]()
[![Rules](https://img.shields.io/badge/rules-27+-green)]()

*Fewer errors. Better structure. Less time debugging AI responses.*

</div>

---

## Overview

Aspect Code is a static analysis tool that combines **Tree-sitter-powered code analysis** with **AI assistant integration**. It scans your codebase for issues and generates contextual knowledge bases that enhance tools like GitHub Copilot, Cursor, and Claude.

> ⚠️ **Alpha Release** — Supports 8 languages with focus on 5 primary targets. The alpha_default profile contains 27 curated rules.

## Features

- **Smart Analysis** — Detects security vulnerabilities, bugs, concurrency issues, complexity problems, and architectural patterns
- **AI Integration** — Generates instruction files for Copilot, Cursor, Claude, and generic agents
- **Knowledge Base** — Creates `.aspect/` directories containing structured documentation about your codebase: architectural diagrams, code conventions, data flows, dependency graphs, and high-impact areas. This context helps AI assistants understand your project structure and give more accurate suggestions.
- **Fast & Incremental** — Tree-sitter-based parsing with smart incremental indexing

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
| Ruby | Limited |
| Rust | Limited |
| PHP | Limited |
| Swift | Limited |

## Architecture

```
aspectcode/
├── extension/    # VS Code extension (TypeScript)
├── server/       # Analysis engine & API (Python + FastAPI)
└── tools/        # Internal testing utilities
```

## Quick Start

### Extension

```bash
cd extension
npm install        # Fetches Tree-sitter parsers
npm run build      # Build extension + webview
```

### Server

```bash
cd server
python -m venv .venv
.venv\Scripts\activate    # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Configuration

| Setting | Description |
|---------|-------------|
| `aspectcode.serverBaseUrl` | Backend URL (default: `http://localhost:8000`) |
| `aspectcode.pythonPath` | Custom Python executable |
| `aspectcode.enabledCategories` | Rule categories to enable |

## Rule Categories

The **alpha_default** profile includes curated rules across:

- **Security** — SQL injection, hardcoded secrets, path traversal, insecure random, JWT validation
- **Bugs** — Float equality, iteration modification, recursion without base case, incompatible comparisons
- **Concurrency** — Unreleased locks, blocking in async contexts
- **Complexity** — Cyclomatic complexity, long functions, deep nesting
- **Dead Code** — Unused variables, unused imports, duplicate definitions
- **Errors** — Swallowed exceptions, broad catch blocks, partial implementations
- **Imports** — Unused imports, circular dependencies
- **Style** — Mixed indentation, trailing whitespace, inconsistent formatting
- **Testing** — Flaky tests with sleep, missing assertions
- **Architecture** — Global state usage, entry points, external integrations
- **Naming** — Convention violations, shadowing, inconsistent terminology
- **Memory** (C/C++) — Buffer overflows, use-after-free, null checks
- **Performance** — String concatenation in loops, repeated regex compilation


