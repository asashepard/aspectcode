#!/usr/bin/env python3
"""
Findings Review Tool

INTERNAL USE ONLY - For maintainer false-positive review.

This tool aggregates findings from one or more findings_debug.json files
and generates per-rule markdown reports for manual review.

Usage:
    # Review findings from one or more JSON files
    python -m tools.review_findings path/to/findings_debug.json [more files...]
    
    # Review all findings in .aspect_manual_repos
    python -m tools.review_findings --all
    
    # Find the implementation file for a specific rule
    python -m tools.review_findings --find-rule ident.shadowing
    
    # Generate report to a custom output directory
    python -m tools.review_findings --output-dir my_review/ findings.json

Output:
    tools/findings_review/
        _summary.md              # Overview of all rules with counts
        ident.shadowing.md       # Per-rule detailed report
        sec.sql_injection.md
        ...
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set


# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))


# KB-only rules (surface="kb") - excluded from user-facing review
# These rules power .aspect/ KB generation but are not shown to users
KB_ONLY_RULES: Set[str] = {
    "arch.entry_point",
    "arch.data_model", 
    "arch.external_integration",
    "analysis.change_impact",
    "architecture.critical_dependency",
    "deadcode.unused_public",
    "architecture.dependency_cycle_impact",
    "imports.unused",
    "naming.project_term_inconsistency",
}


# ============================================================================
# DATA STRUCTURES
# ============================================================================

class RuleSummary:
    """Aggregated data for a single rule_id."""
    
    def __init__(self, rule_id: str):
        self.rule_id = rule_id
        self.total_count = 0
        self.by_directory: Dict[str, int] = defaultdict(int)
        self.by_file: Dict[str, int] = defaultdict(int)
        self.by_repo: Dict[str, int] = defaultdict(int)
        self.severities: Dict[str, int] = defaultdict(int)
        self.findings: List[Dict[str, Any]] = []  # Sample of findings
        
    def add_finding(self, finding: Dict[str, Any], repo: str, max_samples: int = 20):
        """Add a finding to this rule's summary."""
        self.total_count += 1
        
        # Track by repo
        self.by_repo[repo] += 1
        
        # Track by file
        file_path = finding.get("file", "unknown")
        self.by_file[file_path] += 1
        
        # Track by top-level directory
        parts = file_path.replace("\\", "/").split("/")
        if len(parts) > 1:
            top_dir = parts[0] + "/"
        else:
            top_dir = "(root)"
        self.by_directory[top_dir] += 1
        
        # Track severity
        severity = finding.get("severity", "unknown")
        self.severities[severity] += 1
        
        # Keep a sample of findings (spread across different files)
        if len(self.findings) < max_samples:
            # Add repo context to finding
            finding_with_context = {**finding, "_repo": repo}
            self.findings.append(finding_with_context)
        elif self.total_count % 50 == 0:
            # Periodically replace a finding to get variety
            import random
            idx = random.randint(0, len(self.findings) - 1)
            finding_with_context = {**finding, "_repo": repo}
            self.findings[idx] = finding_with_context


class FindingsAggregator:
    """Aggregates findings from multiple JSON files."""
    
    def __init__(self):
        self.by_rule: Dict[str, RuleSummary] = {}
        self.repos_analyzed: List[str] = []
        self.total_files = 0
        self.total_findings = 0
        
    def load_file(self, json_path: str, include_kb_rules: bool = False) -> bool:
        """Load a findings_debug.json file and aggregate its findings.
        
        Args:
            json_path: Path to the findings_debug.json file
            include_kb_rules: If False (default), exclude KB-only rules from aggregation
        """
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            print(f"Error loading {json_path}: {e}", file=sys.stderr)
            return False
        
        repo = data.get("repo", Path(json_path).parent.name)
        self.repos_analyzed.append(repo)
        self.total_files += data.get("files_analyzed", 0)
        
        findings = data.get("findings", [])
        
        # Filter and count findings
        filtered_findings = []
        for finding in findings:
            rule_id = finding.get("rule_id", "unknown")
            
            # Skip KB-only rules unless explicitly included
            if not include_kb_rules and rule_id in KB_ONLY_RULES:
                continue
            
            filtered_findings.append(finding)
        
        self.total_findings += len(filtered_findings)
        
        for finding in filtered_findings:
            rule_id = finding.get("rule_id", "unknown")
            
            if rule_id not in self.by_rule:
                self.by_rule[rule_id] = RuleSummary(rule_id)
            
            self.by_rule[rule_id].add_finding(finding, repo)
        
        return True
    
    def get_sorted_rules(self) -> List[RuleSummary]:
        """Get rules sorted by total count (descending)."""
        return sorted(self.by_rule.values(), key=lambda r: -r.total_count)


# ============================================================================
# RULE IMPLEMENTATION FINDER
# ============================================================================

def find_rule_implementation(rule_id: str) -> List[str]:
    """
    Find the implementation file(s) for a given rule_id.
    
    Searches server/rules/ for files containing the rule_id string.
    Returns list of matching file paths.
    """
    rules_dir = PROJECT_ROOT / "server" / "rules"
    if not rules_dir.exists():
        return []
    
    matches = []
    rule_pattern = re.compile(re.escape(rule_id), re.IGNORECASE)
    
    for py_file in rules_dir.glob("*.py"):
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            # Look for the rule_id in the file (in id= or rule= assignments)
            if f'"{rule_id}"' in content or f"'{rule_id}'" in content:
                matches.append(str(py_file))
        except Exception:
            pass
    
    return matches


def build_rule_to_file_map() -> Dict[str, List[str]]:
    """
    Build a mapping of rule_id -> implementation files.
    
    Scans all rule files and extracts their rule IDs.
    """
    rules_dir = PROJECT_ROOT / "server" / "rules"
    if not rules_dir.exists():
        return {}
    
    rule_map = defaultdict(list)
    
    # Pattern to match rule ID definitions
    id_pattern = re.compile(r'''id\s*=\s*["']([a-z0-9_.]+)["']''', re.IGNORECASE)
    
    for py_file in rules_dir.glob("*.py"):
        try:
            content = py_file.read_text(encoding='utf-8', errors='ignore')
            for match in id_pattern.finditer(content):
                rule_id = match.group(1)
                rule_map[rule_id].append(str(py_file))
        except Exception:
            pass
    
    return dict(rule_map)


# ============================================================================
# MARKDOWN REPORT GENERATION
# ============================================================================

def generate_summary_report(aggregator: FindingsAggregator, output_dir: Path) -> str:
    """Generate the _summary.md overview report."""
    lines = [
        "# Findings Review Summary",
        "",
        f"**Repos analyzed:** {', '.join(aggregator.repos_analyzed)}",
        f"**Total files:** {aggregator.total_files:,}",
        f"**Total findings:** {aggregator.total_findings:,}",
        f"**Unique rules triggered:** {len(aggregator.by_rule)}",
        "",
        "---",
        "",
        "## Rules by Finding Count",
        "",
        "| Rule ID | Count | Top Directory | Severity | Action Needed? |",
        "|---------|-------|---------------|----------|----------------|",
    ]
    
    for rule in aggregator.get_sorted_rules():
        # Get top directory
        top_dirs = sorted(rule.by_directory.items(), key=lambda x: -x[1])
        top_dir = top_dirs[0][0] if top_dirs else "n/a"
        top_dir_pct = (top_dirs[0][1] / rule.total_count * 100) if top_dirs else 0
        
        # Get primary severity
        severities = sorted(rule.severities.items(), key=lambda x: -x[1])
        primary_sev = severities[0][0] if severities else "?"
        
        # Create link to detail file
        safe_id = rule.rule_id.replace(".", "_")
        
        lines.append(
            f"| [{rule.rule_id}]({safe_id}.md) | {rule.total_count:,} | "
            f"{top_dir} ({top_dir_pct:.0f}%) | {primary_sev} | |"
        )
    
    lines.extend([
        "",
        "---",
        "",
        "## Quick Triage Guide",
        "",
        "For each rule with high counts:",
        "",
        "1. **Check the directory distribution** - If 80%+ are in `docs_src/`, `tests/`, "
        "or `examples/`, the rule may be firing on non-production code",
        "",
        "2. **Review the sample findings** - Open the rule's detail file and scan "
        "the 10-20 sample findings. Are they real issues or false positives?",
        "",
        "3. **Decide action:**",
        "   - ✅ **Keep as-is** - Findings look legitimate",
        "   - ⚠️ **Tighten** - Add guards to reduce false positives",
        "   - ❌ **Disable for alpha** - Too noisy, disable in `profiles.py`",
        "",
        "4. **Find the rule implementation:**",
        "   ```",
        "   python -m tools.review_findings --find-rule <rule_id>",
        "   ```",
        "",
    ])
    
    content = "\n".join(lines)
    output_file = output_dir / "_summary.md"
    output_file.write_text(content, encoding='utf-8')
    return str(output_file)


def generate_rule_report(rule: RuleSummary, output_dir: Path) -> str:
    """Generate a detailed markdown report for a single rule."""
    # Find implementation files
    impl_files = find_rule_implementation(rule.rule_id)
    
    lines = [
        f"# Rule: `{rule.rule_id}`",
        "",
        f"**Total findings:** {rule.total_count:,}",
        "",
    ]
    
    # Implementation location
    if impl_files:
        lines.append("**Implementation:**")
        for f in impl_files:
            rel_path = os.path.relpath(f, PROJECT_ROOT)
            lines.append(f"- `{rel_path}`")
        lines.append("")
    
    # Severity breakdown
    lines.append("## Severity Breakdown")
    lines.append("")
    for sev, count in sorted(rule.severities.items(), key=lambda x: -x[1]):
        pct = count / rule.total_count * 100
        lines.append(f"- **{sev}:** {count:,} ({pct:.1f}%)")
    lines.append("")
    
    # Directory distribution
    lines.append("## Directory Distribution")
    lines.append("")
    lines.append("| Directory | Count | % |")
    lines.append("|-----------|-------|---|")
    
    top_dirs = sorted(rule.by_directory.items(), key=lambda x: -x[1])[:10]
    for dir_name, count in top_dirs:
        pct = count / rule.total_count * 100
        lines.append(f"| `{dir_name}` | {count:,} | {pct:.1f}% |")
    lines.append("")
    
    # Repository breakdown (if multiple repos)
    if len(rule.by_repo) > 1:
        lines.append("## By Repository")
        lines.append("")
        for repo, count in sorted(rule.by_repo.items(), key=lambda x: -x[1]):
            pct = count / rule.total_count * 100
            lines.append(f"- **{repo}:** {count:,} ({pct:.1f}%)")
        lines.append("")
    
    # Sample findings
    lines.append("## Sample Findings")
    lines.append("")
    lines.append("A representative sample of findings for manual review:")
    lines.append("")
    
    for i, finding in enumerate(rule.findings[:15], 1):
        repo = finding.get("_repo", "unknown")
        file_path = finding.get("file", "unknown")
        line_num = finding.get("line", "?")
        message = finding.get("message", "")
        snippet = finding.get("code_snippet", "")
        
        lines.append(f"### {i}. {repo}: `{file_path}:{line_num}`")
        lines.append("")
        lines.append(f"**Message:** {message}")
        lines.append("")
        if snippet:
            lines.append(f"**Code:** `{snippet}`")
            lines.append("")
        lines.append("---")
        lines.append("")
    
    # Action section
    lines.extend([
        "## Triage Decision",
        "",
        "After reviewing the samples above, choose one:",
        "",
        "- [ ] ✅ **Keep as-is** - Findings are legitimate",
        "- [ ] ⚠️ **Tighten** - Add guards to reduce false positives",
        "- [ ] ❌ **Disable for alpha** - Set `enabled=False` in `profiles.py`",
        "",
        "### Notes",
        "",
        "_Add your notes here after review..._",
        "",
    ])
    
    content = "\n".join(lines)
    safe_id = rule.rule_id.replace(".", "_")
    output_file = output_dir / f"{safe_id}.md"
    output_file.write_text(content, encoding='utf-8')
    return str(output_file)


# ============================================================================
# MAIN CLI
# ============================================================================

def find_all_findings_files() -> List[str]:
    """Find all findings_debug.json files in .aspect_manual_repos."""
    base_dir = PROJECT_ROOT / ".aspect_manual_repos"
    if not base_dir.exists():
        return []
    
    return [str(f) for f in base_dir.rglob("findings_debug.json")]


def main():
    parser = argparse.ArgumentParser(
        description="Review and aggregate findings from analysis JSON files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "json_files",
        nargs="*",
        help="Path(s) to findings_debug.json files"
    )
    
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Load all findings_debug.json files from .aspect_manual_repos/"
    )
    
    parser.add_argument(
        "--output-dir", "-o",
        default="tools/findings_review",
        help="Output directory for markdown reports (default: tools/findings_review)"
    )
    
    parser.add_argument(
        "--find-rule", "-f",
        metavar="RULE_ID",
        help="Find the implementation file(s) for a specific rule_id and exit"
    )
    
    parser.add_argument(
        "--list-rules",
        action="store_true",
        help="List all known rule_ids with their implementation files"
    )
    
    args = parser.parse_args()
    
    # Handle --find-rule
    if args.find_rule:
        matches = find_rule_implementation(args.find_rule)
        if matches:
            print(f"Rule '{args.find_rule}' is implemented in:")
            for m in matches:
                rel_path = os.path.relpath(m, PROJECT_ROOT)
                print(f"  {rel_path}")
        else:
            print(f"No implementation found for rule '{args.find_rule}'")
            print("Try checking the rules directory manually:")
            print(f"  {PROJECT_ROOT / 'server' / 'rules'}")
        return
    
    # Handle --list-rules
    if args.list_rules:
        rule_map = build_rule_to_file_map()
        if rule_map:
            print("Known rules and their implementations:\n")
            for rule_id in sorted(rule_map.keys()):
                files = rule_map[rule_id]
                rel_files = [os.path.relpath(f, PROJECT_ROOT) for f in files]
                print(f"  {rule_id}")
                for rf in rel_files:
                    print(f"    -> {rf}")
        else:
            print("No rules found in server/rules/")
        return
    
    # Determine input files
    json_files = args.json_files
    if args.all:
        json_files = find_all_findings_files()
        if not json_files:
            print("No findings_debug.json files found in .aspect_manual_repos/")
            print("Run the manual review harness first:")
            print("  python tools/run_manual_alpha_review.py")
            sys.exit(1)
    
    if not json_files:
        parser.print_help()
        print("\nError: No input files specified. Use --all or provide paths.")
        sys.exit(1)
    
    # Load and aggregate findings
    print(f"Loading findings from {len(json_files)} file(s)...")
    aggregator = FindingsAggregator()
    
    for json_path in json_files:
        print(f"  Loading {json_path}...")
        aggregator.load_file(json_path)
    
    print(f"\nAggregated {aggregator.total_findings:,} findings across {len(aggregator.by_rule)} rules")
    
    # Generate reports
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = PROJECT_ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"\nGenerating reports in {output_dir}/")
    
    # Summary report
    summary_file = generate_summary_report(aggregator, output_dir)
    print(f"  Created {os.path.relpath(summary_file, PROJECT_ROOT)}")
    
    # Per-rule reports
    for rule in aggregator.get_sorted_rules():
        rule_file = generate_rule_report(rule, output_dir)
        print(f"  Created {os.path.relpath(rule_file, PROJECT_ROOT)}")
    
    print(f"\nDone! Open {os.path.relpath(summary_file, PROJECT_ROOT)} to start reviewing.")
    print("\nQuick commands:")
    print(f"  # Find a rule's implementation")
    print(f"  python -m tools.review_findings --find-rule <rule_id>")
    print(f"\n  # List all known rules")
    print(f"  python -m tools.review_findings --list-rules")


if __name__ == "__main__":
    main()
