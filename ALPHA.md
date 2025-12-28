# Aspect Code Alpha

Welcome to the Aspect Code alpha! This VS Code extension analyzes your codebase for bugs, complexity issues, and architectural patterns.

## Installation

1. Install the **Aspect Code** extension from VS Code marketplace (or VSIX if provided)
2. On first launch, you'll be prompted to enter your API key
3. Run **Aspect Code: Enter API Key** from the command palette if needed later

## What It Does

- **Code Analysis**: Detects bugs, potential null dereferences, complexity issues, and architectural patterns
- **Knowledge Base**: Builds a local `.aspect/` folder with codebase summaries for AI assistants
- **Auto-regeneration**: Keeps the KB up-to-date on save or idle (configurable)

## Local Files

The extension creates a `.aspect/` folder in your workspace containing:
- KB summary files (for AI assistants like Copilot, Cursor, Claude)
- Cached analysis results
- Workspace fingerprint for staleness detection

> **Note**: Add `.aspect/` to your `.gitignore` if you don't want to commit these files.

## Rate Limits

To ensure fair usage during alpha, the server enforces these limits per API key:

| Limit | Default | Description |
|-------|---------|-------------|
| **RPM** | 60 | Requests per minute |
| **Concurrency** | 2 | Max parallel requests |
| **Daily Cap** | 5,000 | Total requests per day (resets at midnight UTC) |

### What Happens When You Hit Limits

- **RPM/Concurrency**: Extension automatically retries with exponential backoff
- **Daily Cap**: No auto-retry. You'll see a message with reset time.

Check your current usage: run `/limits` in your terminal:
```bash
curl -H "X-Api-Key: YOUR_KEY" https://api.aspectcode.com/limits
```

## Commands

| Command | Description |
|---------|-------------|
| `Aspect Code: Show Panel` | Open the main panel |
| `Aspect Code: Enter API Key` | Set or change your API key |
| `Aspect Code: Clear API Key` | Remove stored API key |
| `Aspect Code: Examine` | Run analysis on current files |
| `Aspect Code: Force Reindex` | Clear cache and rebuild KB |
| `Aspect Code: Copy Debug Info` | Copy diagnostic info for support |

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `aspectcode.serverBaseUrl` | `https://api.aspectcode.com` | Server URL |
| `aspectcode.autoRegenerateKb` | `onSave` | When to regenerate KB: `off`, `onSave`, `idle` |

## Getting Debug Info

If you encounter issues:

1. Run **Aspect Code: Copy Debug Info** from command palette
2. This copies diagnostic information to your clipboard
3. Share this with support (no sensitive data is included)

## Common Issues

### "API key is missing or invalid"
- Run **Aspect Code: Enter API Key** and paste your key
- Keys are stored securely in VS Code's secret storage

### "Daily limit reached"
- Wait until midnight UTC for reset
- Contact support if you need higher limits

### "Rate limit exceeded"
- The extension will auto-retry with backoff
- If persistent, you may have too many tabs/workspaces running analysis

### KB not updating
- Check `aspectcode.autoRegenerateKb` setting
- Run **Aspect Code: Force Reindex** to rebuild from scratch

### Extension seems slow
- Analysis is throttled to 2 concurrent requests
- Large workspaces take time on first index
- Subsequent analyses use cached data

## Support

- Use **Copy Debug Info** command to collect diagnostics
- Report issues with the debug info attached

---

**Version**: Alpha  
**Rate Limits**: 60 RPM, 2 concurrent, 5000 daily cap
