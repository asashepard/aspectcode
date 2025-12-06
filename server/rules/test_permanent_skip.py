"""
Rule: test.permanent_skip

Flags tests that are skipped/ignored/disabled without a linked ticket/justification 
or an expiry date. Enforces policy: every skip must include a reference 
(e.g., TICKET-123, BUG:1234, URL) or an expiry (e.g., expires=2025-12-31) 
in the reason string or adjacent comment.
"""

import re
from typing import List, Set, Dict, Iterable, Optional, Tuple, Any

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit


class TestPermanentSkipRule:
    """
    Rule to detect skipped/ignored tests without proper justification.
    
    Flags test functions/methods that are skipped or ignored without including:
    - A ticket reference (TICKET-123, BUG:1234, JIRA, etc.)
    - An expiry date (expires=2025-12-31, until=2026-01-01, etc.)
    - A URL reference (http://, https://)
    
    Examples of flagged patterns:
    - @pytest.mark.skip(reason="flaky")
    - test.skip("temporarily disabled", () => {})
    - @Disabled() // Java
    
    Examples of allowed patterns:
    - @pytest.mark.skip(reason="TICKET-123 flaky test")
    - test.skip("BUG:456 broken on CI", () => {})
    - @Disabled("expires=2025-12-31")
    """
    
    meta = RuleMeta(
        id="test.permanent_skip",
        category="test",
        tier=0,  # Using text-based analysis
        priority="P2",
        autofix_safety="suggest-only",
        description="Flags tests that are skipped/ignored/disabled without a linked ticket/justification or an expiry date",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=False)
    
    # Skip/ignore patterns per language
    SKIP_PATTERNS = {
        "python": [
            r"@pytest\.mark\.skip\s*\([^)]*\)",
            r"@pytest\.mark\.xfail\s*\([^)]*\)",
            r"@unittest\.skip\s*\([^)]*\)",
            r"pytest\.skip\s*\([^)]*\)"
        ],
        "javascript": [
            r"test\.skip\s*\([^)]*\)",
            r"it\.skip\s*\([^)]*\)",
            r"describe\.skip\s*\([^)]*\)",
            r"\bxit\s*\([^)]*\)",
            r"\bxtest\s*\([^)]*\)"
        ],
        "typescript": [
            r"test\.skip\s*\([^)]*\)",
            r"it\.skip\s*\([^)]*\)",
            r"describe\.skip\s*\([^)]*\)",
            r"\bxit\s*\([^)]*\)",
            r"\bxtest\s*\([^)]*\)"
        ],
        "go": [
            r"t\.Skip\s*\([^)]*\)",
            r"t\.SkipNow\s*\([^)]*\)"
        ],
        "java": [
            r"@(?:org\.junit\.)?Ignore\b",
            r"@(?:org\.junit\.jupiter\.api\.)?Disabled\b",
            r"@Test\s*\([^)]*enabled\s*=\s*false"
        ],
        "csharp": [
            r"\[Ignore\]",
            r"\[Fact\s*\([^)]*Skip\s*=[^)]*\)\]",
            r"\[Test\s*\([^)]*Skip\s*=[^)]*\)\]"
        ],
        "cpp": [
            r"GTEST_SKIP\s*\(\s*\)",
            r"TEST\s*\(\s*DISABLED_[^,]*,[^)]*\)"
        ],
        "c": [
            r"GTEST_SKIP\s*\(\s*\)",
            r"TEST\s*\(\s*DISABLED_[^,]*,[^)]*\)"
        ],
        "ruby": [
            r"\bpending\s*(?:\([^)]*\))?",
            r"\bskip\s*(?:\([^)]*\))?",
            r"\bxit\s*\([^)]*\)"
        ],
        "rust": [
            r"#\[ignore\]"
        ],
        "swift": [
            r"XCTSkip\s*\([^)]*\)",
            r"XCTSkipIf\s*\([^)]*\)",
            r"XCTSkipUnless\s*\([^)]*\)"
        ]
    }
    
    # Patterns that indicate acceptable justification
    JUSTIFICATION_PATTERNS = [
        r"TICKET-\d+",
        r"BUG:\d+",
        r"ISSUE:\d+",
        r"\bJIRA\b",
        r"https?://",
        r"expires?=\d{4}-\d{2}-\d{2}",
        r"expiry=\d{4}-\d{2}-\d{2}",
        r"until=\d{4}-\d{2}-\d{2}",
        r"20\d{2}-\d{2}-\d{2}"  # Date pattern (YYYY-MM-DD)
    ]
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.text:
            return
        
        # Get language from context
        language = self._get_language_from_context(ctx)
        if language not in self.meta.langs:
            return
        
        # Find skipped tests and check for justification
        yield from self._analyze_skipped_tests(ctx, language)
    
    def _get_language_from_context(self, ctx: RuleContext) -> str:
        """Extract language from context."""
        if hasattr(ctx, 'adapter') and hasattr(ctx.adapter, 'language_id'):
            return ctx.adapter.language_id
        
        # Fallback: extract from file extension
        file_path = ctx.file_path
        ext = file_path.split('.')[-1].lower()
        ext_map = {
            'py': 'python',
            'ts': 'typescript', 'tsx': 'typescript',
            'js': 'javascript', 'jsx': 'javascript',
            'go': 'go',
            'java': 'java',
            'cpp': 'cpp', 'cc': 'cpp', 'cxx': 'cpp', 'hpp': 'cpp',
            'c': 'c', 'h': 'c',
            'cs': 'csharp',
            'rb': 'ruby',
            'rs': 'rust',
            'swift': 'swift'
        }
        return ext_map.get(ext, 'python')
    
    def _analyze_skipped_tests(self, ctx: RuleContext, language: str) -> Iterable[Finding]:
        """Find and analyze skipped tests using text patterns."""
        text = ctx.text
        patterns = self.SKIP_PATTERNS.get(language, [])
        
        for pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE | re.DOTALL):
                skip_text = match.group(0)
                start_pos = match.start()
                end_pos = match.end()
                
                # Check if this is in a test context
                if not self._is_test_context(text, start_pos, language):
                    continue
                
                # Get surrounding context for justification check
                context = self._get_surrounding_context(text, start_pos, end_pos)
                
                if not self._has_justification(skip_text, context):
                    yield Finding(
                        rule=self.meta.id,
                        message="Skipped/ignored test without ticket or expiry. Add a reference (e.g., TICKET-123) or an expiry (e.g., expires=YYYY-MM-DD).",
                        file=ctx.file_path,
                        start_byte=start_pos,
                        end_byte=end_pos,
                        severity="info"
                    )
    
    def _get_surrounding_context(self, text: str, start_pos: int, end_pos: int) -> str:
        """Get surrounding text context for justification check."""
        # Get the line containing the skip and a few lines before/after
        lines = text.split('\n')
        
        # Find which line contains the skip
        current_pos = 0
        target_line = 0
        for i, line in enumerate(lines):
            if current_pos <= start_pos <= current_pos + len(line):
                target_line = i
                break
            current_pos += len(line) + 1  # +1 for newline
        
        # Get context (2 lines before and after)
        context_start = max(0, target_line - 2)
        context_end = min(len(lines), target_line + 3)
        context_lines = lines[context_start:context_end]
        
        return '\n'.join(context_lines)
    
    def _is_test_context(self, text: str, position: int, language: str) -> bool:
        """Check if the skip is in a test context (function or class)."""
        # For JavaScript/TypeScript, skip patterns are often the test themselves
        if language in {"javascript", "typescript"}:
            # Get the text around the position to check if this is a skip pattern
            lines = text.split('\n')
            current_pos = 0
            target_line = 0
            
            for i, line in enumerate(lines):
                if current_pos <= position <= current_pos + len(line):
                    target_line = i
                    break
                current_pos += len(line) + 1
            
            if target_line < len(lines):
                line = lines[target_line]
                # If the line contains a skip pattern, it's inherently a test
                js_skip_patterns = [
                    r"\btest\.skip\s*\(",
                    r"\bit\.skip\s*\(",
                    r"\bxit\s*\(",
                    r"\bxtest\s*\(",
                    r"\bdescribe\.skip\s*\(",
                ]
                for pattern in js_skip_patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        return True
        
        # Get the line containing the skip
        lines = text.split('\n')
        current_pos = 0
        target_line = 0
        
        for i, line in enumerate(lines):
            if current_pos <= position <= current_pos + len(line):
                target_line = i
                break
            current_pos += len(line) + 1
        
        # Look backwards and forwards for test function/method patterns
        test_patterns = {
            "python": [
                r"def\s+test_\w+",
                r"def\s+\w*test\w*",
                r"class\s+Test\w+",
            ],
            "javascript": [
                r"\b(?:test|it|describe)\s*\(",
                r"function\s+test\w*",
            ],
            "typescript": [
                r"\b(?:test|it|describe)\s*\(",
                r"function\s+test\w*",
            ],
            "java": [
                r"@Test\b",
                r"void\s+test\w*",
                r"public\s+void\s+test\w*",
            ],
            "go": [
                r"func\s+Test\w+",
            ],
            "csharp": [
                r"\[Test\]",
                r"\[Fact\]",
                r"\[Theory\]",
                r"void\s+Test\w*",
            ],
            "cpp": [
                r"TEST\s*\(",
                r"TEST_F\s*\(",
            ],
            "c": [
                r"TEST\s*\(",
                r"TEST_F\s*\(",
            ],
            "ruby": [
                r"def\s+test_\w+",
                r"it\s+['\"]",
                r"test\s+['\"]",
            ],
            "rust": [
                r"#\[\s*test\s*\]",
                r"fn\s+test_\w+",
            ],
            "swift": [
                r"func\s+test\w*",
                r"@Test\s+func",
            ],
        }
        
        patterns = test_patterns.get(language, [])
        if not patterns:
            return True  # Default to allowing if no patterns defined
        
        # Check previous and next lines for test context (decorators often precede function definitions)
        for i in range(max(0, target_line - 5), min(len(lines), target_line + 5)):
            if i < len(lines):
                line = lines[i]
                for pattern in patterns:
                    if re.search(pattern, line, re.IGNORECASE):
                        return True
        
        return False
    
    def _has_justification(self, skip_text: str, context: str) -> bool:
        """Check if the skip has proper justification."""
        # Combine skip text and surrounding context
        full_text = skip_text + " " + context
        
        # Check for any justification patterns
        for pattern in self.JUSTIFICATION_PATTERNS:
            if re.search(pattern, full_text, re.IGNORECASE):
                return True
        
        return False


# Create rule instance and register it
_rule = TestPermanentSkipRule()

# Export rule in RULES list for auto-discovery
RULES = [_rule]

# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
    register_rule(_rule)
except ImportError:
    # Fallback for direct imports
    try:
        from engine.registry import register_rule
        register_rule(_rule)
    except ImportError:
        pass


