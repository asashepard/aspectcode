#!/usr/bin/env python3
"""
Manual Alpha Profile Review Harness

INTERNAL USE ONLY - For maintainer false-positive review.

This script:
1. Clones/updates a set of representative open-source repos
2. Runs the alpha profile analysis on each
3. Writes findings to JSON files for manual inspection

Usage:
    python tools/run_manual_alpha_review.py              # Run all repos
    python tools/run_manual_alpha_review.py --repo fastapi  # Run specific repo
    python tools/run_manual_alpha_review.py --lang python   # Run all Python repos
    python tools/run_manual_alpha_review.py --skip-clone    # Skip clone/update, just analyze
    python tools/run_manual_alpha_review.py --list          # List configured repos

Output:
    .aspect_manual_repos/<repo_name>/              # Cloned repo
    .aspect_manual_repos/<repo_name>/findings_debug.json  # Findings for review
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.absolute()
sys.path.insert(0, str(PROJECT_ROOT))

from tools.manual_review_repos import REVIEW_REPOS, REPOS_BASE_DIR, get_repos_for_language, get_repo_by_name


def resolve_server_root(explicit: Optional[str] = None) -> Optional[Path]:
    """Resolve the server root for importing the Python engine.

    The OSS VS Code extension can run without the Python server.
    These maintainer tools operate on the Python engine/rules and therefore
    require a server checkout.

    Resolution order:
      1) --server-root
      2) env ASPECTCODE_SERVER_ROOT
      3) <project_root>/server (monorepo checkout)
    """
    candidates: List[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    env_root = os.environ.get("ASPECTCODE_SERVER_ROOT")
    if env_root:
        candidates.append(Path(env_root))
    candidates.append(PROJECT_ROOT / "server")

    for p in candidates:
        try:
            p = p.expanduser().resolve()
        except Exception:
            continue

        if (p / "engine").exists() and (p / "rules").exists():
            return p

    return None


def ensure_server_on_path(server_root: Path) -> None:
    """Ensure the server root is on sys.path so imports like engine.* work."""
    sr = str(server_root)
    if sr not in sys.path:
        sys.path.insert(0, sr)


def run_command(cmd: List[str], cwd: Optional[str] = None, capture: bool = True) -> tuple:
    """
    Run a shell command and return (success, stdout, stderr).
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=600  # 10 minute timeout for large clones
        )
        return (result.returncode == 0, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (False, "", "Command timed out after 600 seconds")
    except Exception as e:
        return (False, "", str(e))


def clone_or_update_repo(repo: Dict[str, Any], base_dir: Path) -> bool:
    """
    Clone repo if not present, or update if already cloned.
    Returns True if repo is ready for analysis.
    """
    name = repo["name"]
    url = repo["url"]
    repo_path = base_dir / name
    branch = repo.get("branch")
    
    if repo_path.exists():
        # Update existing repo
        print(f"  Updating {name}...")
        
        # Fetch latest
        success, _, stderr = run_command(["git", "fetch", "--all"], cwd=str(repo_path))
        if not success:
            print(f"    Warning: git fetch failed: {stderr}")
        
        # Reset to origin/main or origin/master
        for default_branch in ["main", "master"]:
            success, _, _ = run_command(
                ["git", "reset", "--hard", f"origin/{default_branch}"],
                cwd=str(repo_path)
            )
            if success:
                break
        
        return True
    else:
        # Clone new repo
        print(f"  Cloning {name} from {url}...")
        
        clone_cmd = ["git", "clone", "--depth", "1"]  # Shallow clone for speed
        if branch:
            clone_cmd.extend(["--branch", branch])
        clone_cmd.extend([url, str(repo_path)])
        
        success, _, stderr = run_command(clone_cmd)
        
        if not success:
            print(f"    Error: Failed to clone: {stderr}")
            return False
        
        return True


def run_alpha_analysis(repo: Dict[str, Any], base_dir: Path) -> Dict[str, Any]:
    """
    Run alpha profile analysis on a repo.
    Returns a dict with analysis results.
    """
    name = repo["name"]
    language = repo["language"]
    repo_path = base_dir / name
    path_filter = repo.get("path_filter")
    
    # Determine analysis path
    if path_filter:
        analysis_path = repo_path / path_filter
    else:
        analysis_path = repo_path
    
    if not analysis_path.exists():
        return {
            "success": False,
            "error": f"Analysis path does not exist: {analysis_path}",
            "findings_count": 0,
            "findings": []
        }
    
    print(f"  Analyzing {name} ({language})...")
    
    # Import analysis functions
    try:
        from engine.runner import setup_adapters, collect_files, analyze_file, build_project_graph
        from engine.registry import discover_rules, get_rules_for_profile
        from engine.profiles import RuleProfile, ALPHA_DEFAULT_RULE_IDS
        from engine.config import load_config
        from engine.file_filter import is_excluded_path
    except ImportError as e:
        return {
            "success": False,
            "error": f"Failed to import engine modules: {e}",
            "findings_count": 0,
            "findings": []
        }
    
    # Set up engine
    setup_adapters()
    discover_rules(["rules"])
    config = load_config()  # Use load_config() for proper defaults
    
    # Get rules for this language
    try:
        rules = get_rules_for_profile(RuleProfile.ALPHA_DEFAULT, language)
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to get rules for {language}: {e}",
            "findings_count": 0,
            "findings": []
        }
    
    if not rules:
        return {
            "success": False,
            "error": f"No rules found for language: {language}",
            "findings_count": 0,
            "findings": []
        }
    
    # Collect files
    files = collect_files([str(analysis_path)], language)
    print(f"    Found {len(files)} {language} files")
    
    if not files:
        return {
            "success": True,
            "error": None,
            "findings_count": 0,
            "findings": [],
            "files_analyzed": 0
        }
    
    # Build project graph if needed
    needs_project_graph = any(
        getattr(rule, 'requires', None) and 
        getattr(rule.requires, 'project_graph', False) 
        for rule in rules
    )
    project_graph = None
    if needs_project_graph and len(files) > 0:
        try:
            project_graph = build_project_graph(files, language, config)
        except Exception:
            pass  # Continue without project graph
    
    # Analyze files
    all_findings = []
    files_analyzed = 0
    
    for file_path in files:
        if is_excluded_path(file_path):
            continue
        
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue
        
        findings, _ = analyze_file(
            file_path, language, rules, config,
            debug_adapter=False, debug_output=[],
            project_graph=project_graph
        )
        
        files_analyzed += 1
        
        # Convert findings to serializable format
        rel_path = os.path.relpath(file_path, str(repo_path))
        
        for finding in findings:
            # Get line number
            line = 1
            try:
                text_before = content[:finding.start_byte]
                line = text_before.count('\n') + 1
            except Exception:
                pass
            
            # Get code snippet
            snippet = ""
            try:
                snippet = content[finding.start_byte:finding.end_byte][:80]
                snippet = ' '.join(snippet.split())
            except Exception:
                pass
            
            all_findings.append({
                "rule_id": finding.rule,
                "file": rel_path,
                "line": line,
                "message": finding.message,
                "severity": finding.severity,
                "code_snippet": snippet,
            })
    
    return {
        "success": True,
        "error": None,
        "findings_count": len(all_findings),
        "findings": all_findings,
        "files_analyzed": files_analyzed
    }


def write_findings(repo: Dict[str, Any], results: Dict[str, Any], base_dir: Path) -> str:
    """
    Write findings to a JSON file.
    Returns the output file path.
    """
    name = repo["name"]
    repo_path = base_dir / name
    output_file = repo_path / "findings_debug.json"
    
    output_data = {
        "repo": name,
        "language": repo["language"],
        "url": repo["url"],
        "analysis_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "success": results["success"],
        "error": results.get("error"),
        "files_analyzed": results.get("files_analyzed", 0),
        "findings_count": results["findings_count"],
        "findings": results["findings"]
    }
    
    # Also generate a summary by rule
    by_rule = {}
    for f in results["findings"]:
        rule = f["rule_id"]
        if rule not in by_rule:
            by_rule[rule] = 0
        by_rule[rule] += 1
    output_data["summary_by_rule"] = dict(sorted(by_rule.items(), key=lambda x: -x[1]))
    
    repo_path.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)
    
    return str(output_file)


def print_summary(results: List[Dict[str, Any]]):
    """Print a summary of all analysis results."""
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    
    total_findings = 0
    by_language = {}
    by_rule = {}
    
    for r in results:
        repo = r["repo"]
        lang = repo["language"]
        count = r["results"]["findings_count"]
        total_findings += count
        
        if lang not in by_language:
            by_language[lang] = 0
        by_language[lang] += count
        
        for finding in r["results"].get("findings", []):
            rule = finding["rule_id"]
            if rule not in by_rule:
                by_rule[rule] = 0
            by_rule[rule] += 1
        
        status = "✓" if r["results"]["success"] else "✗"
        print(f"  {status} {repo['name']:25} ({lang:12}) - {count:4} findings")
    
    print()
    print(f"Total findings: {total_findings}")
    print()
    
    if by_language:
        print("By language:")
        for lang, count in sorted(by_language.items()):
            print(f"  {lang}: {count}")
        print()
    
    if by_rule:
        print("Top 10 rules by finding count:")
        sorted_rules = sorted(by_rule.items(), key=lambda x: -x[1])[:10]
        for rule, count in sorted_rules:
            print(f"  {rule}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Manual alpha profile review harness (internal maintainer tool)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--server-root",
        help=(
            "Path to the Aspect Code server checkout (folder containing engine/ and rules/). "
            "If omitted, uses ASPECTCODE_SERVER_ROOT or ./server"
        )
    )
    
    parser.add_argument(
        "--repo", "-r",
        help="Run only a specific repo by name"
    )
    
    parser.add_argument(
        "--lang", "-l",
        choices=["python", "javascript", "typescript", "java", "csharp"],
        help="Run only repos for a specific language"
    )
    
    parser.add_argument(
        "--skip-clone",
        action="store_true",
        help="Skip clone/update step, just run analysis on existing clones"
    )
    
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all configured repos and exit"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )
    
    args = parser.parse_args()
    
    # List mode
    if args.list:
        print("Configured repos for manual review:")
        print()
        for repo in REVIEW_REPOS:
            print(f"  {repo['name']:25} ({repo['language']:12}) - {repo['url']}")
            if repo.get("notes"):
                print(f"    Notes: {repo['notes']}")
            if repo.get("path_filter"):
                print(f"    Path filter: {repo['path_filter']}")
        return

    # These tools require the Python server engine (not shipped with the OSS extension).
    server_root = resolve_server_root(args.server_root)
    if not server_root:
        print("Error: Could not locate server engine (engine/ and rules/).")
        print("Provide --server-root /path/to/server or set ASPECTCODE_SERVER_ROOT.")
        print(f"Tried: {PROJECT_ROOT / 'server'}")
        sys.exit(1)

    ensure_server_on_path(server_root)
    
    # Determine which repos to process
    if args.repo:
        repo = get_repo_by_name(args.repo)
        if not repo:
            print(f"Error: No repo found with name '{args.repo}'")
            print("Use --list to see available repos")
            sys.exit(1)
        repos = [repo]
    elif args.lang:
        repos = get_repos_for_language(args.lang)
        if not repos:
            print(f"Error: No repos configured for language '{args.lang}'")
            sys.exit(1)
    else:
        repos = REVIEW_REPOS
    
    # Set up base directory
    base_dir = PROJECT_ROOT / REPOS_BASE_DIR
    base_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Manual Alpha Review Harness")
    print(f"=" * 60)
    print(f"Base directory: {base_dir}")
    print(f"Repos to process: {len(repos)}")
    print()
    
    # Process each repo
    all_results = []
    
    for repo in repos:
        name = repo["name"]
        print(f"\n[{name}]")
        
        # Clone or update
        if not args.skip_clone:
            repo_ready = clone_or_update_repo(repo, base_dir)
            if not repo_ready:
                all_results.append({
                    "repo": repo,
                    "results": {
                        "success": False,
                        "error": "Failed to clone/update repo",
                        "findings_count": 0,
                        "findings": []
                    }
                })
                continue
        else:
            repo_path = base_dir / name
            if not repo_path.exists():
                print(f"  Skipped: repo not cloned (use without --skip-clone first)")
                continue
        
        # Run analysis
        results = run_alpha_analysis(repo, base_dir)
        
        # Write findings
        if results["success"]:
            output_file = write_findings(repo, results, base_dir)
            print(f"    Wrote {results['findings_count']} findings to {output_file}")
        else:
            print(f"    Error: {results.get('error', 'Unknown error')}")
        
        all_results.append({
            "repo": repo,
            "results": results
        })
    
    # Print summary
    print_summary(all_results)
    
    print()
    print("Review the findings_debug.json files in each repo directory.")
    print("Look for patterns of false positives to address in rule logic.")


if __name__ == "__main__":
    main()
