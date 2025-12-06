# Aspect Code Engine Protocol v1

This document defines the JSON protocol between the Aspect Code analysis engine and VS Code extension.

## Version Information

All protocol messages include versioning:

```json
{
  "aspect-code.protocol": "1",
  "engine_version": "0.1.0"
}
```

## Scan Result Format

The primary output from `python -m server.engine.runner --format json` is a `scan_result`:

### Top-level Structure

```json
{
  "aspect-code.protocol": "1",
  "engine_version": "0.1.0",
  "files_scanned": 42,
  "rules_run": 9,
  "findings": [...],
  "metrics": {
    "parse_ms": 15.2,
    "rules_ms": 128.7,
    "total_ms": 156.3
  }
}
```

## Finding Format

Each finding represents a rule violation or suggestion:

```json
{
  "rule_id": "imports.unused",
  "message": "Unused import 'requests'",
  "severity": "warning",
  "file_path": "/absolute/path/to/file.py",
  "uri": "file:///absolute/path/to/file.py",
  "start_byte": 123,
  "end_byte": 145,
  "range": {
    "startLine": 5,
    "startCol": 0,
    "endLine": 5,
    "endCol": 22
  },
  "code_frame": "import requests\n       ^^^^^^^",
  "autofix": [
    {
      "file_path": "/absolute/path/to/file.py",
      "start_byte": 123,
      "end_byte": 145,
      "replacement": "",
      "range": {
        "startLine": 5,
        "startCol": 0,
        "endLine": 5,
        "endCol": 22
      }
    }
  ],
  "suppression_hint": "# aspect-code: ignore[imports.unused]",
  "meta": {
    "tier": 1,
    "category": "imports",
    "autofix_safety": "safe",
    "suggestions": [
      "Remove unused import",
      "Use the imported module somewhere in your code"
    ]
  }
}
```

### Field Specifications

#### Required Fields

- **`rule_id`** (string): Unique rule identifier (e.g., "imports.unused")
- **`message`** (string): Human-readable description
- **`severity`** (string): One of "error", "warning", "info"
- **`file_path`** (string): Absolute native file path
- **`uri`** (string): File URI (file://) for VS Code compatibility
- **`start_byte`** (int): Zero-based byte offset start
- **`end_byte`** (int): Zero-based byte offset end
- **`range`** (object): Line/column positions (1-based lines, 0-based columns)
  - **`startLine`** (int): 1-based line number
  - **`startCol`** (int): 0-based column number
  - **`endLine`** (int): 1-based line number  
  - **`endCol`** (int): 0-based column number

#### Optional Fields

- **`code_frame`** (string): Source code excerpt with highlighting
- **`autofix`** (array): List of Edit objects for automatic fixes
- **`suppression_hint`** (string): Comment text to suppress this rule
- **`meta`** (object): Additional metadata about the rule/finding

### Edit Format

Edits support both byte offsets and line/column ranges for flexibility:

```json
{
  "file_path": "/absolute/path/to/file.py",
  "start_byte": 123,
  "end_byte": 145,
  "replacement": "import os",
  "range": {
    "startLine": 5,
    "startCol": 0,
    "endLine": 5,
    "endCol": 22
  }
}
```

Extensions can choose to use either byte offsets or line/column ranges based on their needs.

## Path Normalization

### Requirements

1. **Absolute paths**: All file paths must be absolute
2. **Native format**: Use OS-native path separators (\ on Windows, / on Unix)
3. **Resolved**: Resolve symlinks and relative components (.., .)
4. **URI compatibility**: Generate file:// URIs that VS Code can parse correctly

### Windows Specifics

- Drive letters must be uppercase: `C:\path\to\file.py`
- URI format: `file:///C:/path/to/file.py` (note triple slash and forward slashes)
- Backslashes in paths must be normalized to forward slashes in URIs

### Examples

| Platform | file_path | uri |
|----------|-----------|-----|
| Windows | `C:\code\repo\main.py` | `file:///C:/code/repo/main.py` |
| macOS | `/Users/dev/repo/main.py` | `file:///Users/dev/repo/main.py` |
| Linux | `/home/dev/repo/main.py` | `file:///home/dev/repo/main.py` |

## Error Handling

### Protocol Version Mismatch

If the extension receives a different protocol version, it should:

1. Log a warning to the Output channel
2. Attempt to parse known fields
3. Display a notification suggesting engine update

### Invalid JSON

If JSON parsing fails:

1. Log the raw output to Output channel
2. Display error with suggestion to check engine installation
3. Return empty findings array

### Missing Required Fields

If required fields are missing:

1. Log specific field names to Output channel
2. Skip the malformed finding
3. Continue processing remaining findings

## Autofix Safety Levels

The `meta.autofix_safety` field indicates how safe the autofix is:

- **`"safe"`**: Can be applied automatically without user review
- **`"caution"`**: Should prompt user before applying
- **`"suggest-only"`**: Only show as suggestion, never auto-apply

## Rule Metadata

The `meta` object provides context about the rule:

```json
{
  "tier": 1,
  "category": "imports", 
  "autofix_safety": "safe",
  "priority": "P0",
  "suggestions": [
    "Remove unused import",
    "Use the imported module"
  ]
}
```

## Command Line Interface

### Scan Workspace

```bash
python -m server.engine.runner \
  --paths /workspace/root \
  --format json \
  --discover \
  --jobs 4 \
  --validate
```

### Scan Single File

```bash
python -m server.engine.runner \
  --paths /path/to/file.py \
  --lang python \
  --format json
```

### Debug Options

```bash
python -m server.engine.runner \
  --paths /workspace \
  --lang python \
  --format json \
  --debug-resolver \
  --graph-dump /tmp/graph.json
```

## Backward Compatibility

Protocol v1 is the initial version. Future versions will:

1. Increment the protocol version number
2. Maintain backward compatibility for at least one major version
3. Document migration paths for breaking changes
4. Provide clear upgrade instructions in error messages
