# Aspect Code Tools

These scripts are **maintainer utilities**.

The OSS VS Code extension is designed to work **standalone/offline** for KB generation and assistant instructions. The Python server/rule engine is optional and may live in a separate repo/directory.

## Manual Review Harness (Server Engine)

A harness for running the alpha profile against multiple real-world open-source 
repositories to identify false positives before release.

### Purpose

If you are developing the **Python engine/rules**, this harness helps sanity-check signal/noise on real-world repos. This harness:

1. Clones a set of representative repos (Python, JS, TS, Java, C#)
2. Runs the alpha profile analysis on each
3. Outputs findings to JSON files for manual inspection

### Quick Start

```bash
# From project root
python tools/run_manual_alpha_review.py
```

If your server checkout is not at `./server`, pass:

```bash
python tools/run_manual_alpha_review.py --server-root /path/to/aspectcode-server
```

Or set `ASPECTCODE_SERVER_ROOT`.

This will:
- Clone/update all configured repos to `.aspect_manual_repos/`
- Run analysis on each
- Write findings to `.aspect_manual_repos/<repo>/findings_debug.json`

### Options

```bash
# List all configured repos
python tools/run_manual_alpha_review.py --list

# Run only a specific repo
python tools/run_manual_alpha_review.py --repo fastapi

# Run only repos for a specific language
python tools/run_manual_alpha_review.py --lang python

# Skip clone/update (if repos already cloned)
python tools/run_manual_alpha_review.py --skip-clone

# Verbose output
python tools/run_manual_alpha_review.py -v
```

### Output

Each repo gets a `findings_debug.json` file:

```
.aspect_manual_repos/
  fastapi/
    findings_debug.json    <- Findings for FastAPI
    ... (cloned repo files)
  express/
    findings_debug.json    <- Findings for Express
    ...
```

The JSON includes:
- `findings`: Array of all findings with rule_id, file, line, message, severity
- `summary_by_rule`: Count of findings per rule (sorted by frequency)
- `files_analyzed`: Number of files processed

### Review Process

1. **Run the harness**: `python tools/run_manual_alpha_review.py`

2. **Check the summary**: The script prints a summary showing findings by repo and top rules.

3. **Open findings files**: Look at `findings_debug.json` for each repo.

4. **Group by rule_id**: Use `jq` or your editor to sort/group by rule.
   ```bash
   # Count findings by rule
   cat findings_debug.json | jq '.summary_by_rule'
   
   # See all findings for a specific rule
   cat findings_debug.json | jq '.findings | map(select(.rule_id == "sec.hardcoded_secret"))'
   ```

5. **For each finding, ask**:
   - Is this a real issue? → Keep the rule as-is
   - Is this noise? → tighten the rule logic/filtering in your server checkout

6. **Re-run and verify**: After fixes, re-run with `--skip-clone` to verify improvements.

### Adding/Removing Repos

Edit `tools/manual_review_repos.py`:

```python
REVIEW_REPOS = [
    {
        "name": "my-repo",           # Directory name and identifier
        "url": "https://...",        # Git clone URL
        "language": "python",        # Primary language
        "branch": "main",            # (optional) Specific branch
        "path_filter": "src",        # (optional) Subdirectory to analyze
        "notes": "Description",      # (optional) Notes for maintainers
    },
    ...
]
```

### Configured Repos

Currently configured for review:

| Language   | Repos                            |
|------------|----------------------------------|
| Python     | fastapi, httpx                   |
| JavaScript | express, lodash                  |
| TypeScript | nextjs-realworld, cal-com        |
| Java       | spring-petclinic, java-design-patterns |
| C#         | eShopOnWeb, clean-architecture   |

### Notes

- **Clone depth**: Uses `--depth 1` for shallow clones (faster, less disk)
- **Disk usage**: Expect ~500MB-2GB total for all repos
- **Time**: First run takes 5-15 minutes (cloning); subsequent runs are faster
- **Path filters**: Some large monorepos use `path_filter` to limit analysis scope

### Related Files

- `tools/manual_review_repos.py` - Repo configuration
- `tools/run_manual_alpha_review.py` - Main harness script
- `tools/review_findings.py` - Findings aggregation and review reports
- (optional) your server checkout’s `engine/` and `rules/` directories

---

## Findings Review Tool

After running analysis, use this tool to aggregate and review findings across
all repos, generating per-rule markdown reports for efficient triage.

### Purpose

Instead of manually scanning raw JSON, this tool:

1. Aggregates findings from all `findings_debug.json` files
2. Groups by `rule_id` with counts and directory distributions
3. Generates markdown reports optimized for quick human scanning
4. Helps you identify noisy rules to tighten or disable

### Quick Start

```bash
# After running the analysis harness, generate review reports:
python -m tools.review_findings --all

# Or specify specific files:
python -m tools.review_findings .aspect_manual_repos/fastapi/findings_debug.json
```

This creates:
```
tools/findings_review/
  _summary.md              # Overview with all rules and counts
  ident_shadowing.md       # Detailed report for ident.shadowing
  sec_sql_injection.md     # Detailed report for sec.sql_injection
  ...
```

### Options

```bash
# Load all findings from .aspect_manual_repos/
python -m tools.review_findings --all

# Custom output directory
python -m tools.review_findings --output-dir my_review/ --all

# Find implementation file for a specific rule (requires a server checkout)
python -m tools.review_findings --server-root /path/to/aspectcode-server --find-rule ident.shadowing

# List all known rules with their implementation files
python -m tools.review_findings --server-root /path/to/aspectcode-server --list-rules
```

### Review Workflow

1. **Generate analysis**: Run the manual review harness
   ```bash
   python tools/run_manual_alpha_review.py
   ```

2. **Generate reports**: Create markdown summaries
   ```bash
   python -m tools.review_findings --all
   ```

3. **Open summary**: Start with `tools/findings_review/_summary.md`
   - Rules are sorted by finding count (highest first)
   - Shows top directory for each rule (e.g., 80% in `docs_src/`)
   - Link to each rule's detail page

4. **Triage each rule**: Open the per-rule `.md` files
   - **Directory distribution**: If 80%+ in `docs/`, `tests/`, `examples/` → likely noise
   - **Sample findings**: Scan 10-15 examples - are they real issues?
   - **Mark your decision**: Keep / Tighten / Disable

5. **Fix noisy rules**:
   ```bash
   # Find the rule implementation
   python -m tools.review_findings --server-root /path/to/aspectcode-server --find-rule <rule_id>
   
   # Then adjust rule logic/filtering in your server checkout
   ```

6. **Iterate**: Re-run analysis and review until findings are clean
   ```bash
   python tools/run_manual_alpha_review.py --skip-clone
   python -m tools.review_findings --all
   ```

### Sample Report Structure

**`_summary.md`** (overview):
```markdown
## Rules by Finding Count

| Rule ID | Count | Top Directory | Severity | Action Needed? |
|---------|-------|---------------|----------|----------------|
| arch.entry_point | 1,496 | docs_src/ (85%) | info | |
| deadcode.unused_public | 1,475 | tests/ (60%) | warning | |
| ident.shadowing | 96 | fastapi/ (40%) | warn | |
```

**`ident_shadowing.md`** (per-rule detail):
```markdown
# Rule: `ident.shadowing`

**Total findings:** 96
**Implementation:** rules/ident_shadowing.py (via `--server-root`)

## Directory Distribution
| Directory | Count | % |
|-----------|-------|---|
| docs_src/ | 45 | 47% |
| fastapi/ | 38 | 40% |
| tests/ | 13 | 13% |

## Sample Findings
### 1. fastapi: `security/oauth2.py:42`
**Message:** 'id' shadows the built-in 'id'...
**Code:** `id`
```

### Alpha Triage Philosophy

**For alpha, we prioritize precision over recall:**

- ✅ **Keep** rules that fire on real issues with <5% false positive rate
- ⚠️ **Tighten** rules that have good signal but need path/context guards
- ❌ **Disable** rules that are too noisy to fix quickly

It's better to ship fewer, highly accurate rules than many noisy ones.
Users will lose trust if they see bogus findings.

### Output Files

Reports are written to `tools/findings_review/` by default:

| File | Purpose |
|------|---------|
| `_summary.md` | Overview of all rules with counts and quick triage table |
| `<rule_id>.md` | Detailed report for each rule with samples |

### Related Commands

```bash
# Full workflow
python tools/run_manual_alpha_review.py           # Clone & analyze repos
python -m tools.review_findings --all             # Generate reports
python -m tools.review_findings --find-rule X    # Find rule implementation
python -m tools.review_findings --list-rules     # List all known rules
```
