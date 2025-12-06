"""
Rule to detect and fix excessive blank lines.

This rule identifies runs of multiple consecutive blank lines and collapses them
to a single blank line, preserving the file's existing line ending style.
"""

from typing import Iterator, List, Tuple

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority


class StyleBlankLinesExcessiveRule(Rule):
    """Rule to collapse runs of multiple blank lines to a single blank line."""
    
    meta = RuleMeta(
        id="style.blank_lines.excessive",
        category="style", 
        tier=0,
        priority="P2",
        autofix_safety="safe",
        description="Collapse runs of multiple blank lines to a single blank line.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(raw_text=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and detect excessive blank lines."""
        # Check if this language is supported
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return
        
        text = ctx.text
        if not text:
            return
        
        # Find all excessive blank line runs
        edits = self._find_excessive_blank_lines(text)
        
        if not edits:
            return
        
        # Report a single finding for the entire file with all fixes
        message = f"Excessive blank lines detected; collapsing {len(edits)} runs to single blank lines."
        
        yield Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=0,
            end_byte=len(text.encode('utf-8')),
            severity="info",
            autofix=edits,
            meta={
                "runs_collapsed": len(edits),
                "description": "Multiple consecutive blank lines found and collapsed"
            }
        )
    
    def _find_excessive_blank_lines(self, text: str) -> List[Edit]:
        """
        Find runs of excessive blank lines and return edits to fix them.
        
        Args:
            text: The file content as a string
            
        Returns:
            List of Edit objects to remove excessive blank lines
        """
        edits = []
        lines = text.splitlines(keepends=True)
        
        if not lines:
            return edits
        
        # Track consecutive blank lines
        blank_run_start = None
        blank_run_length = 0
        current_byte_pos = 0
        
        for i, line in enumerate(lines):
            line_start_byte = current_byte_pos
            line_bytes = line.encode('utf-8')
            line_end_byte = current_byte_pos + len(line_bytes)
            
            # Check if line is blank (only whitespace)
            is_blank = self._is_blank_line(line)
            
            if is_blank:
                if blank_run_start is None:
                    # Start of a new blank run
                    blank_run_start = i
                    blank_run_length = 1
                else:
                    # Continue existing blank run
                    blank_run_length += 1
                    
                    # If we have 2+ blank lines, mark the extra ones for removal
                    if blank_run_length >= 2:
                        # Remove this extra blank line
                        edits.append(Edit(
                            start_byte=line_start_byte,
                            end_byte=line_end_byte,
                            replacement=""
                        ))
            else:
                # Non-blank line, reset blank run tracking
                blank_run_start = None
                blank_run_length = 0
            
            current_byte_pos = line_end_byte
        
        # Sort edits by start position in reverse order for safe application
        edits.sort(key=lambda e: e.start_byte, reverse=True)
        return edits
    
    def _is_blank_line(self, line: str) -> bool:
        """
        Check if a line is blank (contains only whitespace).
        
        Args:
            line: The line to check (may include line ending)
            
        Returns:
            True if the line contains only whitespace characters
        """
        # Remove line endings first, then check if remaining content is only whitespace
        content = line.rstrip('\r\n')
        return content.strip() == ""


# Export the rule instance for registration
rule = StyleBlankLinesExcessiveRule()

# Register the rule with the global registry
try:
    from engine.registry import register_rule
    register_rule(rule)
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass


