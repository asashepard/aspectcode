# Changelog

All notable changes to the Aspect Code extension will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.4] - 2026-01-17

### Changed
- Centralized workspace file discovery to reduce redundant scans and improve determinism
- Improved large-repo behavior via deterministic filtering (size/pattern) and debounced invalidation
- Reload/Re-index now supports full refresh paths and better panel loading feedback

## [0.1.0] - 2026-01-10

### Added
- Initial pre-release of Aspect Code VS Code extension
- Tree-sitter-powered static analysis for Python, TypeScript, JavaScript, Java, and C#
- Knowledge base generation for AI assistants (Copilot, Cursor, Claude)
- Real-time analysis with incremental parsing
- Webview panel with findings overview and dependency graph
- Impact analysis for current file
- Integration with `.copilot-instructions.md`, `.cursorrules`, `CLAUDE.md`, and `AGENTS.md`

### Known Limitations
- Alpha release - API and features may change
- Limited language support with some experimental language support (Go, C/C++)
