# Contributing

Thanks for your interest in contributing.

## Quick Start (Extension)

```bash
cd extension
npm install
npm run build
```

## What To Work On

- Bug fixes and reliability improvements
- Documentation improvements
- Small, focused UX improvements in the panel

If you’re unsure, open an issue describing what you want to change.

## Pull Requests

- Keep PRs small and focused (one feature/fix per PR)
- Prefer simple implementations over heavy abstractions
- Add/update tests when there’s a clear place to do so
- Avoid reformatting unrelated code

## Development Notes

- The extension should not write any workspace files until the user explicitly triggers setup (e.g. via the **+** button).
- When changing packaging/bundling, verify the VSIX contains required runtime files (notably the Tree-sitter WASM).

## License

By contributing, you agree that your contributions will be licensed under this repository’s license (see LICENSE.md).
