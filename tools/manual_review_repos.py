"""
Manual Review Repository Configuration

This module defines the set of representative open-source repositories used
for manual false-positive review of the alpha profile rules.

INTERNAL USE ONLY - For maintainer review, not user-facing.

To add a new repo:
    1. Add an entry to REVIEW_REPOS below
    2. Run: python tools/run_manual_alpha_review.py

To remove a repo:
    1. Comment out or delete the entry
    2. Optionally delete the local clone from .aspect_manual_repos/
"""

from typing import List, Dict, Any


# Base directory for all cloned repos (relative to project root)
REPOS_BASE_DIR = ".aspect_manual_repos"


# Representative repositories for manual alpha review
# Each entry is a dict with:
#   - name: Human-readable identifier (used for directory and output file naming)
#   - url: Git clone URL
#   - language: Primary language for analysis
#   - branch: (optional) Specific branch to checkout, defaults to default branch
#   - path_filter: (optional) Subdirectory to analyze, defaults to repo root
#   - notes: (optional) Notes about the repo for maintainers
#
REVIEW_REPOS: List[Dict[str, Any]] = [
    # =========================================================================
    # PYTHON
    # =========================================================================
    {
        "name": "fastapi",
        "url": "https://github.com/tiangolo/fastapi.git",
        "language": "python",
        "notes": "FastAPI framework - modern async Python web framework",
    },
    {
        "name": "httpx",
        "url": "https://github.com/encode/httpx.git",
        "language": "python",
        "notes": "HTTPX async HTTP client - well-structured Python codebase",
    },
    
    # =========================================================================
    # JAVASCRIPT (Node.js)
    # =========================================================================
    {
        "name": "express",
        "url": "https://github.com/expressjs/express.git",
        "language": "javascript",
        "notes": "Express.js - most popular Node.js web framework",
    },
    {
        "name": "lodash",
        "url": "https://github.com/lodash/lodash.git",
        "language": "javascript",
        "notes": "Lodash utility library - pure JavaScript, many utility functions",
    },
    
    # =========================================================================
    # TYPESCRIPT
    # =========================================================================
    {
        "name": "nextjs-realworld",
        "url": "https://github.com/reck1ess/next-realworld-example-app.git",
        "language": "typescript",
        "notes": "Next.js RealWorld example - TypeScript fullstack app",
    },
    {
        "name": "cal-com",
        "url": "https://github.com/calcom/cal.com.git",
        "language": "typescript",
        "path_filter": "apps/web",  # Focus on main web app, not all packages
        "notes": "Cal.com scheduling - large TypeScript/Next.js monorepo",
    },
    
    # =========================================================================
    # JAVA
    # =========================================================================
    {
        "name": "spring-petclinic",
        "url": "https://github.com/spring-projects/spring-petclinic.git",
        "language": "java",
        "notes": "Spring Boot Petclinic - canonical Spring Boot sample app",
    },
    {
        "name": "java-design-patterns",
        "url": "https://github.com/iluwatar/java-design-patterns.git",
        "language": "java",
        "path_filter": "singleton",  # Just one pattern to keep it manageable
        "notes": "Java design patterns - well-structured Java code examples",
    },
    
    # =========================================================================
    # C# / .NET
    # =========================================================================
    {
        "name": "eShopOnWeb",
        "url": "https://github.com/dotnet-architecture/eShopOnWeb.git",
        "language": "csharp",
        "notes": "eShopOnWeb - Microsoft's reference .NET web app architecture",
    },
    {
        "name": "clean-architecture",
        "url": "https://github.com/jasontaylordev/CleanArchitecture.git",
        "language": "csharp",
        "notes": "Clean Architecture template - well-structured C# solution",
    },
]


def get_repos_for_language(language: str) -> List[Dict[str, Any]]:
    """Get all repos configured for a specific language."""
    return [r for r in REVIEW_REPOS if r["language"] == language]


def get_repo_by_name(name: str) -> Dict[str, Any] | None:
    """Get a specific repo by name."""
    for repo in REVIEW_REPOS:
        if repo["name"] == name:
            return repo
    return None


def list_all_languages() -> List[str]:
    """Get list of all languages with configured repos."""
    return sorted(set(r["language"] for r in REVIEW_REPOS))
