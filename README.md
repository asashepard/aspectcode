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

## Features

- **Knowledge Base generation** — Writes `.aspect/architecture.md`, `.aspect/map.md`, and `.aspect/context.md`
- **AI instruction files** — Generates assistant-friendly instruction files for common tools
- **Dependency visualization** — Shows file relationships in the panel
- **Incremental updates** — Regenerates on save/idle (configurable)

## Supported Languages

Primary support: Python, TypeScript, JavaScript, Java, C#

## Repo Layout

```
aspectcode/
├── extension/    # VS Code extension (TypeScript)
└── server/       # Optional backend (not required for KB generation)
```

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

Pushing a tag like `v0.1.1` creates a GitHub Release with the VSIX attached (via .github/workflows/release.yml).

## License

See LICENSE.md.


