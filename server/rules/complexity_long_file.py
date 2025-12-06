# server/rules/complexity_long_file.py
"""
Rule to detect overly large files and suggest splitting them by responsibility.

This rule analyzes files for:
- Effective lines of code (excluding blank lines and comment-only lines)
- Compares against configurable thresholds (repo median + ratio, absolute cap)
- Suggests concrete split strategies via refactoring guidance comments

When thresholds are exceeded, it suggests inserting guidance comments with file split strategies.
"""

from typing import List, Set, Optional, Tuple, Iterable
import re
from engine.types import RuleContext, Finding, RuleMeta, Requires

# Default configuration
DEFAULTS = {
    "median_loc": 200,     # repo median LOC if not supplied
    "ratio": 2.0,          # flag if file_loc > median_loc * ratio
    "absolute_cap": 1000,  # always flag if above this
}

class ComplexityLongFileRule:
    """Rule to flag files that are significantly larger than typical and suggest splitting by responsibility."""
    
    meta = RuleMeta(
        id="complexity.long_file",
        category="complexity",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Flag files that are significantly larger than typical and suggest splitting by responsibility.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Visit a file and check if it's overly large."""
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get configuration
        config = getattr(ctx, "config", {}) or {}
        median = int(config.get("median_loc", DEFAULTS["median_loc"]))
        ratio = float(config.get("ratio", DEFAULTS["ratio"]))
        cap = int(config.get("absolute_cap", DEFAULTS["absolute_cap"]))

        # Count effective lines of code
        text = ctx.text
        loc = self._count_effective_loc(text)

        # Calculate threshold
        threshold = max(int(median * ratio), cap)
        if loc <= threshold:
            return

        # Create finding with suggestion
        finding = self._create_finding(ctx, loc, median, ratio, cap, threshold)
        if finding:
            yield finding

    def _matches_language(self, ctx: RuleContext, supported_langs: List[str]) -> bool:
        """Check if the current language is supported."""
        return ctx.adapter.language_id in supported_langs

    def _count_effective_loc(self, text: str) -> int:
        """Count effective lines of code, excluding blank lines and comment-only lines."""
        lines = text.splitlines()
        count = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                # Skip blank lines
                continue
                
            # Very coarse comment checks per common syntaxes
            if self._is_comment_only_line(stripped):
                # Treat entire line comments as non-code
                continue
                
            count += 1
            
        return count

    def _is_comment_only_line(self, stripped_line: str) -> bool:
        """Check if a line is comment-only based on common comment patterns."""
        # Common comment starters
        comment_starters = [
            "//",      # C-style single line
            "#",       # Python, Ruby, shell
            "/*",      # C-style block start
            "*",       # C-style block continuation
            "*/",      # C-style block end (standalone)
            "<!--",    # HTML/XML comments
            "-->",     # HTML/XML comment end
            ";",       # Some assembly/config files
        ]
        
        for starter in comment_starters:
            if stripped_line.startswith(starter):
                return True
                
        # Check for lines that end with block comment close (entire line is comment)
        if stripped_line.endswith("*/") and stripped_line.startswith("*"):
            return True
            
        return False

    def _get_comment_leader(self, language: str) -> str:
        """Get the appropriate comment leader for the language."""
        comment_leaders = {
            "python": "#",
            "ruby": "#",
            "javascript": "//",
            "typescript": "//",
            "go": "//",
            "java": "//",
            "csharp": "//",
            "cpp": "//",
            "c": "//",
            "rust": "//",
            "swift": "//",
        }
        return comment_leaders.get(language, "//")

    def _create_finding(self, ctx: RuleContext, loc: int, median: int, ratio: float, cap: int, threshold: int) -> Optional[Finding]:
        """Create a finding for a large file."""
        message = f"File is large (LOC={loc} > threshold={threshold}). Consider splitting by responsibility."
        
        # Create refactoring suggestion
        suggestion = self._create_refactoring_suggestion(ctx, loc, median, ratio, cap, threshold)
        
        # For file-level findings, use the entire file range
        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=0,
            end_byte=len(ctx.text.encode('utf-8', errors='ignore')),
            severity="info",
            autofix=None,  # suggest-only, no autofix
            meta={
                "suggestion": suggestion,
                "loc": loc,
                "median_loc": median,
                "ratio": ratio,
                "absolute_cap": cap,
                "threshold": threshold
            }
        )
        
        return finding

    def _create_refactoring_suggestion(self, ctx: RuleContext, loc: int, median: int, ratio: float, cap: int, threshold: int) -> str:
        """Create a refactoring suggestion for splitting the large file."""
        language = ctx.adapter.language_id
        leader = self._get_comment_leader(language)
        
        # Concrete split ideas based on common patterns
        ideas = [
            "move data types/interfaces/DTOs to a dedicated module",
            "extract utility functions to a `utils`/`helpers` module", 
            "split large class into smaller collaborators or mixins",
            "separate I/O (API/DB) from domain logic",
            "group feature-specific code into submodules",
        ]
        
        # Format as comment block
        bullets = "\n".join(f"{leader}   - {idea}" for idea in ideas[:4])
        
        header = (
            f"{leader} This file is large (LOC={loc}; median~{median}, ratio={ratio}, cap={cap}).\n"
            f"{leader} Consider splitting by responsibility:\n"
            f"{bullets}\n"
            f"{leader}\n"
        )
        
        return (
            f"Large files reduce navigability and increase merge conflicts. "
            f"Splitting by responsibility improves cohesion. Consider inserting this guidance comment at the top of the file:\n\n"
            f"{header}"
        )

    def _suggest_file_header_note(self, ctx: RuleContext, text: str, loc: int, median: int, ratio: float, cap: int, threshold: int) -> Tuple[str, str]:
        """Create a suggested diff for inserting a file header note."""
        leader = self._get_comment_leader(ctx.adapter.language_id)
        insertion_at = 0  # top-of-file
        
        # Prepare comment block with concrete split ideas
        ideas = [
            "move data types/interfaces/DTOs to a dedicated module",
            "extract utility functions to a `utils`/`helpers` module",
            "split large class into smaller collaborators or mixins", 
            "separate I/O (API/DB) from domain logic",
            "group feature-specific code into submodules",
        ]
        bullets = "\n".join(f"{leader}   - {x}" for x in ideas[:4])
        header = (
            f"{leader} This file is large (LOC={loc}; median~{median}, ratio={ratio}, cap={cap}).\n"
            f"{leader} Consider splitting by responsibility:\n"
            f"{bullets}\n"
            f"{leader}\n"
        )

        before = text[:insertion_at]
        after = header + text[insertion_at:]

        diff = (
            "--- a/long-file\n"
            "+++ b/long-file\n"
            f"-{before}\n"
            f"+{after}\n"
        )
        rationale = "Large files reduce navigability and increase merge conflicts. Splitting by responsibility improves cohesion."
        return diff, rationale


# Register the rule
try:
    from . import register
    register(ComplexityLongFileRule())
except ImportError:
    # Handle direct execution or testing
    pass


