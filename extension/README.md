# Aspect Code

**Knowledge Base Generator for AI Coding Assistants**

Aspect Code generates a structured knowledge base (`.aspect/`) that helps AI coding assistants understand your codebase architecture before making changes.

---

## What It Does

- **Generates `.aspect/` Knowledge Base** — Creates `architecture.md`, `map.md`, and `context.md` files describing your project structure
- **Creates AI Instruction Files** — Generates instruction files for GitHub Copilot, Cursor, Claude, and other assistants
- **Visualizes Dependencies** — Interactive dependency graph showing file relationships and hub files

---

## Supported Languages

Python, TypeScript, JavaScript, Java, C#

---

## Getting Started

1. Install the extension
2. Open a workspace with supported source files
3. Click the **+** button in the Aspect Code panel to generate the knowledge base
4. AI assistants will automatically pick up the generated instruction files

---

## Generated Files

| File | Purpose |
|------|---------|
| `.aspect/architecture.md` | High-risk hubs, directory layout, entry points |
| `.aspect/map.md` | Data models, symbol index, naming conventions |
| `.aspect/context.md` | Module clusters, external integrations, data flows |

---

## Requirements

- VS Code 1.92.0 or higher

---

## Docs

https://aspectcode.com/docs

---

## License

Proprietary. See [LICENSE.md](LICENSE.md) for details.

© 2025-2026 Aspect Code. All rights reserved.
