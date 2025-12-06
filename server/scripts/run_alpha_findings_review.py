#!/usr/bin/env python3
"""
Alpha Profile Findings Review Script

INTERNAL USE ONLY - For maintainer review of findings to identify false positives.

This script runs the alpha profile against a target repository and outputs
all findings to a JSON file for manual review. Use this to:
- Audit finding quality before releases
- Identify false positive patterns
- Validate rule precision on real-world codebases

Usage:
    python -m scripts.run_alpha_findings_review <path-to-repo> [options]
    
    # Or from server directory:
    python scripts/run_alpha_findings_review.py /path/to/repo
    
    # With options:
    python scripts/run_alpha_findings_review.py /path/to/repo --output findings.json
    python scripts/run_alpha_findings_review.py /path/to/repo --language python
    python scripts/run_alpha_findings_review.py /path/to/repo --ndjson
    python scripts/run_alpha_findings_review.py /path/to/repo --summary

Output:
    - findings_debug.json: JSON array of all findings
    - findings_debug.ndjson: Newline-delimited JSON (one finding per line)
    
Each finding includes:
    - rule_id: The rule that triggered
    - file: Relative file path
    - line: Line number (1-indexed)
    - column: Column number (1-indexed)
    - message: Human-readable finding message
    - severity: info/warn/error
    - code_snippet: The relevant code (first ~80 chars)

Review Process:
    1. Run on a codebase you're familiar with
    2. Sort/group by rule_id
    3. For each finding, ask: "Is this a real issue?"
    4. Track false positives and update rules or disable in profiles.py
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.runner import setup_adapters, collect_files, analyze_file, build_project_graph
from engine.registry import discover_rules, get_rules_for_profile
from engine.profiles import RuleProfile, ALPHA_DEFAULT_RULE_IDS
from engine.config import EngineConfig, load_config
from engine.file_filter import should_analyze_file, is_excluded_path


def get_line_col(content: str, byte_offset: int) -> tuple:
    """Convert byte offset to line and column (1-indexed)."""
    if byte_offset <= 0:
        return (1, 1)
    
    text_before = content[:byte_offset]
    lines = text_before.split('\n')
    line = len(lines)
    col = len(lines[-1]) + 1 if lines else 1
    return (line, col)


def get_code_snippet(content: str, start_byte: int, end_byte: int, max_len: int = 80) -> str:
    """Extract a code snippet from byte offsets."""
    try:
        snippet = content[start_byte:end_byte]
        # Clean up whitespace
        snippet = ' '.join(snippet.split())
        if len(snippet) > max_len:
            snippet = snippet[:max_len] + "..."
        return snippet
    except Exception:
        return ""


def run_alpha_review(
    repo_path: str,
    output_file: Optional[str] = None,
    language: Optional[str] = None,
    use_ndjson: bool = False,
    show_summary: bool = True,
    verbose: bool = False
) -> List[Dict[str, Any]]:
    """
    Run alpha profile against a repository and collect findings.
    
    Args:
        repo_path: Path to the repository to analyze
        output_file: Output file path (default: findings_debug.json)
        language: Limit to specific language (default: all)
        use_ndjson: Output as newline-delimited JSON
        show_summary: Print summary statistics
        verbose: Print verbose output
        
    Returns:
        List of finding dictionaries
    """
    repo_path = os.path.abspath(repo_path)
    
    if not os.path.isdir(repo_path):
        print(f"Error: {repo_path} is not a directory", file=sys.stderr)
        sys.exit(1)
    
    # Set up default output
    if output_file is None:
        ext = ".ndjson" if use_ndjson else ".json"
        output_file = os.path.join(repo_path, f"findings_debug{ext}")
    
    print(f"Aspect Code Alpha Profile Review")
    print(f"=" * 50)
    print(f"Repository: {repo_path}")
    print(f"Output: {output_file}")
    print(f"Profile: alpha_default ({len(ALPHA_DEFAULT_RULE_IDS)} rules)")
    print()
    
    # Set up engine
    setup_adapters()
    discover_rules(["rules"])
    config = EngineConfig()  # Use defaults
    
    # Determine languages to analyze
    if language:
        languages = [language]
    else:
        languages = ["python", "typescript", "javascript", "java", "csharp", "go"]
    
    all_findings: List[Dict[str, Any]] = []
    stats = {
        "files_analyzed": 0,
        "files_skipped": 0,
        "by_rule": defaultdict(int),
        "by_severity": defaultdict(int),
        "by_language": defaultdict(int),
        "parse_time_ms": 0,
    }
    
    start_time = time.time()
    
    for lang in languages:
        if verbose:
            print(f"Analyzing {lang} files...")
        
        # Get rules for this language
        try:
            rules = get_rules_for_profile(RuleProfile.ALPHA_DEFAULT, lang)
        except Exception as e:
            if verbose:
                print(f"  Skipping {lang}: {e}")
            continue
        
        if not rules:
            if verbose:
                print(f"  No rules for {lang}")
            continue
        
        # Collect files
        files = collect_files([repo_path], lang)
        
        if verbose:
            print(f"  Found {len(files)} {lang} files")
        
        # Build project graph if any Tier 2 rules need it
        needs_project_graph = any(
            getattr(rule, 'requires', None) and 
            getattr(rule.requires, 'project_graph', False) 
            for rule in rules
        )
        project_graph = None
        if needs_project_graph and len(files) > 0:
            try:
                project_graph = build_project_graph(files, lang, config)
            except Exception as e:
                if verbose:
                    print(f"  Warning: Could not build project graph: {e}")
        
        # Analyze each file
        for file_path in files:
            # Skip files that shouldn't be analyzed
            if is_excluded_path(file_path):
                stats["files_skipped"] += 1
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
            except Exception:
                stats["files_skipped"] += 1
                continue
            
            findings, parse_time = analyze_file(
                file_path, lang, rules, config, 
                debug_adapter=False, debug_output=[],
                project_graph=project_graph
            )
            
            stats["files_analyzed"] += 1
            stats["parse_time_ms"] += parse_time
            stats["by_language"][lang] += len(findings)
            
            # Convert findings to review format
            rel_path = os.path.relpath(file_path, repo_path)
            
            for finding in findings:
                line, col = get_line_col(content, finding.start_byte)
                snippet = get_code_snippet(content, finding.start_byte, finding.end_byte)
                
                review_finding = {
                    "rule_id": finding.rule,
                    "file": rel_path,
                    "line": line,
                    "column": col,
                    "message": finding.message,
                    "severity": finding.severity,
                    "code_snippet": snippet,
                    "start_byte": finding.start_byte,
                    "end_byte": finding.end_byte,
                }
                
                all_findings.append(review_finding)
                stats["by_rule"][finding.rule] += 1
                stats["by_severity"][finding.severity] += 1
    
    elapsed = time.time() - start_time
    
    # Write output
    print(f"Writing {len(all_findings)} findings to {output_file}...")
    
    with open(output_file, 'w', encoding='utf-8') as f:
        if use_ndjson:
            for finding in all_findings:
                f.write(json.dumps(finding) + "\n")
        else:
            json.dump(all_findings, f, indent=2)
    
    # Print summary
    if show_summary:
        print()
        print(f"Summary")
        print(f"-" * 50)
        print(f"Files analyzed: {stats['files_analyzed']}")
        print(f"Files skipped: {stats['files_skipped']}")
        print(f"Total findings: {len(all_findings)}")
        print(f"Time: {elapsed:.2f}s")
        print()
        
        if stats["by_severity"]:
            print("By severity:")
            for sev in ["error", "warn", "info"]:
                if sev in stats["by_severity"]:
                    print(f"  {sev}: {stats['by_severity'][sev]}")
            print()
        
        if stats["by_rule"]:
            print("By rule (top 20):")
            sorted_rules = sorted(stats["by_rule"].items(), key=lambda x: -x[1])[:20]
            for rule_id, count in sorted_rules:
                print(f"  {rule_id}: {count}")
            print()
        
        if stats["by_language"]:
            print("By language:")
            for lang, count in sorted(stats["by_language"].items()):
                if count > 0:
                    print(f"  {lang}: {count}")
    
    return all_findings


def main():
    parser = argparse.ArgumentParser(
        description="Run alpha profile findings review for false positive identification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "repo_path",
        help="Path to the repository to analyze"
    )
    
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: findings_debug.json in repo)"
    )
    
    parser.add_argument(
        "--language", "-l",
        choices=["python", "typescript", "javascript", "java", "csharp", "go"],
        help="Limit analysis to specific language"
    )
    
    parser.add_argument(
        "--ndjson",
        action="store_true",
        help="Output as newline-delimited JSON instead of JSON array"
    )
    
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Don't print summary statistics"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    run_alpha_review(
        repo_path=args.repo_path,
        output_file=args.output,
        language=args.language,
        use_ndjson=args.ndjson,
        show_summary=not args.no_summary,
        verbose=args.verbose
    )


if __name__ == "__main__":
    main()
