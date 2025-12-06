"""
Bug Detection Rule: Possible Null/None Dereference

Detects potential null dereferences when variables may be null from assignments
and haven't been checked before use. Supports Java, C#, C++, C, Python, and TypeScript.

This rule implements a simple forward data-flow analysis to track variables that
may contain null values and flags dereferences of such variables.
"""

import re
from typing import List, Set, Dict, Iterable, Optional

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugNullDerefPossibleRule:
    """
    Rule to detect possible null/None dereferences.
    
    Tracks variables that may be null due to:
    - Assignment from possibly-null returning functions
    - Direct null assignment
    - Not being checked for null before dereference
    
    Flags dereferences including:
    - Member/field access (obj.field, obj->field)
    - Method calls (obj.method())
    - Array/element access (obj[index])
    - Pointer dereference (*ptr)
    """
    
    meta = RuleMeta(
        id="bug.null_deref_possible",
        category="bug",
        tier=1,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects possible null/None dereferences when variables may be null and haven't been checked",
        langs=["java", "csharp", "cpp", "c", "python", "typescript"]
    )
    
    requires = Requires(syntax=True, scopes=True, raw_text=True)
    
    # Functions/methods that may return null/None
    NULLY_CALL_NAMES = {
        "java": {"map.get", "find", "firstOrNull", "getOrDefault", "get", "findFirst", "orElse"},
        "csharp": {"TryGetValue", "FirstOrDefault", "Find", "GetValueOrDefault", "Where", "SingleOrDefault"},
        "cpp": {"getenv", "strchr", "strstr", "malloc", "calloc", "realloc", "fopen", "dynamic_cast"},
        "c": {"getenv", "strchr", "strstr", "malloc", "calloc", "realloc", "fopen", "strtok"},
        "python": {"dict.get", "re.match", "re.search", "os.getenv", "find", "get"},
        "typescript": {"map.get", "find", "querySelector", "get", "getElementById", "findIndex"}
    }
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Main entry point for rule analysis."""
        if not ctx.raw_text:
            return
            
        language = ctx.language
        if language not in self.meta.langs:
            return
            
        # Use simplified text-based analysis similar to bug_uninitialized_use
        yield from self._analyze_text_based(ctx, ctx.raw_text, language)
    
    def _analyze_text_based(self, ctx: RuleContext, text: str, language: str) -> Iterable[Finding]:
        """Text-based analysis for null dereference detection."""
        lines = text.split('\n')
        maybe_null_vars = set()
        
        for line_num, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or stripped.startswith('//'):
                continue
                
            # Check for assignments that may introduce null values
            self._process_assignments(stripped, language, maybe_null_vars)
            
            # Check for null safety guards that clear variables
            self._process_null_guards(stripped, language, maybe_null_vars)
            
            # Check for dereferences of potentially null variables
            yield from self._check_dereferences(ctx, line, line_num, stripped, language, maybe_null_vars)
    
    def _process_assignments(self, line: str, language: str, maybe_null_vars: Set[str]):
        """Process assignments that may introduce null values."""
        # Direct null assignment patterns
        null_patterns = {
            "java": [r'(\w+)\s*=\s*null', r'(\w+)\s*=\s*\w+\.get\(', r'(\w+)\s*=\s*\w+\.find\('],
            "csharp": [r'(\w+)\s*=\s*null', r'(\w+)\s*=\s*\w+\.FirstOrDefault\(', r'(\w+)\s*=\s*\w+\.Find\('],
            "cpp": [r'(\w+)\s*=\s*nullptr', r'(\w+)\s*=\s*NULL', r'(\w+)\s*=\s*getenv\(', r'(\w+)\s*=\s*malloc\('],
            "c": [r'(\w+)\s*=\s*NULL', r'(\w+)\s*=\s*getenv\(', r'(\w+)\s*=\s*malloc\(', r'(\w+)\s*=\s*fopen\('],
            "python": [r'(\w+)\s*=\s*None', r'(\w+)\s*=\s*\w+\.get\(', r'(\w+)\s*=\s*os\.getenv\(', r'(\w+)\s*=\s*re\.match\('],
            "typescript": [r'(\w+)\s*=\s*null', r'(\w+)\s*=\s*undefined', r'(\w+)\s*=\s*\w+\.get\(', r'(\w+)\s*=\s*\w+\.find\(']
        }
        
        # Non-null assignment patterns (string literals, numbers, etc.)
        nonnull_patterns = {
            "java": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\d+', r'(\w+)\s*=\s*new\s+\w+', r'(\w+)\s*=\s*Objects\.requireNonNull\('],
            "csharp": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\d+', r'(\w+)\s*=\s*new\s+\w+'],
            "cpp": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\d+', r'(\w+)\s*=\s*new\s+\w+'],
            "c": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\d+'],
            "python": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\'[^\']*\'', r'(\w+)\s*=\s*\d+', r'(\w+)\s*=\s*\[\]', r'(\w+)\s*=\s*\{\}'],
            "typescript": [r'(\w+)\s*=\s*"[^"]*"', r'(\w+)\s*=\s*\'[^\']*\'', r'(\w+)\s*=\s*\d+', r'(\w+)\s*=\s*\[\]', r'(\w+)\s*=\s*\{\}']
        }
        
        # Check for non-null assignments first (these clear the maybe_null status)
        nonnull_pats = nonnull_patterns.get(language, [])
        for pattern in nonnull_pats:
            match = re.search(pattern, line)
            if match:
                var_name = match.group(1)
                maybe_null_vars.discard(var_name)  # Clear from maybe_null set
                return  # Early return to avoid adding to maybe_null
        
        # Check for potentially null assignments
        patterns = null_patterns.get(language, [])
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                var_name = match.group(1)
                maybe_null_vars.add(var_name)
    
    def _process_null_guards(self, line: str, language: str, maybe_null_vars: Set[str]):
        """Process null safety guards that clear variables from maybe_null set."""
        # Null check patterns that guarantee non-null
        guard_patterns = {
            "java": [
                r'if\s*\(\s*(\w+)\s*!=\s*null\s*\)',
                r'Objects\.requireNonNull\(\s*(\w+)\s*\)',
                r'Assert\.assertNotNull\(\s*(\w+)\s*\)'
            ],
            "csharp": [
                r'if\s*\(\s*(\w+)\s*!=\s*null\s*\)',
                r'ArgumentNullException\.ThrowIfNull\(\s*(\w+)\s*\)',
                r'Debug\.Assert\(\s*(\w+)\s*!=\s*null\s*\)'
            ],
            "cpp": [
                r'if\s*\(\s*(\w+)\s*!=\s*nullptr\s*\)',
                r'if\s*\(\s*(\w+)\s*!=\s*NULL\s*\)',
                r'if\s*\(\s*(\w+)\s*\)'
            ],
            "c": [
                r'if\s*\(\s*(\w+)\s*!=\s*NULL\s*\)',
                r'if\s*\(\s*(\w+)\s*\)',
                r'assert\(\s*(\w+)\s*\)'
            ],
            "python": [
                r'if\s+(\w+)\s+is\s+not\s+None',
                r'if\s+(\w+):',
                r'assert\s+(\w+)\s+is\s+not\s+None'
            ],
            "typescript": [
                r'if\s*\(\s*(\w+)\s*!=\s*null\s*\)',
                r'if\s*\(\s*(\w+)\s*\)',
                r'assert\(\s*(\w+)\s*\)'
            ]
        }
        
        patterns = guard_patterns.get(language, [])
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                var_name = match.group(1)
                maybe_null_vars.discard(var_name)
    
    def _check_dereferences(self, ctx: RuleContext, line: str, line_num: int, 
                          stripped: str, language: str, maybe_null_vars: Set[str]) -> Iterable[Finding]:
        """Check for dereferences of potentially null variables."""
        # Skip if this line contains a null guard (same line protection)
        if self._line_has_null_guard(stripped, language):
            return
            
        # Dereference patterns for each language
        deref_patterns = {
            "java": [
                r'(\w+)\.(\w+)',      # obj.method or obj.field
                r'(\w+)\[',           # array access
            ],
            "csharp": [
                r'(\w+)\.(\w+)',      # obj.Method or obj.Field
                r'(\w+)\[',           # array/indexer access
            ],
            "cpp": [
                r'\*(\w+)',           # pointer dereference
                r'(\w+)->(\w+)',      # pointer member access
                r'(\w+)\.(\w+)',      # object member access
                r'(\w+)\[',           # array access
            ],
            "c": [
                r'\*(\w+)',           # pointer dereference
                r'(\w+)->(\w+)',      # pointer member access
                r'(\w+)\.(\w+)',      # struct member access
                r'(\w+)\[',           # array access
            ],
            "python": [
                r'(\w+)\.(\w+)',      # obj.attr or obj.method()
                r'(\w+)\[',           # subscript access
            ],
            "typescript": [
                r'(\w+)\.(\w+)',      # obj.prop or obj.method()
                r'(\w+)\[',           # element access
            ]
        }
        
        patterns = deref_patterns.get(language, [])
        for pattern in patterns:
            for match in re.finditer(pattern, stripped):
                # Extract variable name (handle different capture groups)
                if pattern.startswith(r'\*'):
                    # Pointer dereference: *var
                    var_name = match.group(1)
                    deref_text = match.group(0)
                elif '->' in pattern:
                    # Pointer member: var->member
                    var_name = match.group(1)
                    deref_text = match.group(0)
                else:
                    # Most common: var.member or var[
                    var_name = match.group(1)
                    deref_text = match.group(0)
                
                # Check for TypeScript optional chaining
                if language == "typescript" and self._is_optional_chaining(stripped, match.start()):
                    continue
                    
                if var_name in maybe_null_vars:
                    # Calculate byte position
                    start_byte = self._get_byte_position(ctx.raw_text, line_num, match.start())
                    end_byte = self._get_byte_position(ctx.raw_text, line_num, match.end())
                    
                    message = self._generate_message(var_name, deref_text, language)
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=message,
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="error",
                        meta={
                            "suggestion": self._generate_suggestion(var_name, language),
                            "autofix_safety": "suggest-only"
                        }
                    )
    
    def _line_has_null_guard(self, line: str, language: str) -> bool:
        """Check if the line contains a null guard on the same line."""
        guard_indicators = {
            "java": ["!= null", "Objects.requireNonNull"],
            "csharp": ["!= null", "ArgumentNullException.ThrowIfNull"],
            "cpp": ["!= nullptr", "!= NULL"],
            "c": ["!= NULL"],
            "python": ["is not None", "assert"],
            "typescript": ["!= null", "!== null"]
        }
        
        indicators = guard_indicators.get(language, [])
        return any(indicator in line for indicator in indicators)
    
    def _is_optional_chaining(self, line: str, pos: int) -> bool:
        """Check if this is TypeScript optional chaining (?. or ?[)."""
        if pos > 0:
            return line[pos-1:pos+1] in ["?.", "?["]
        return False
    
    def _get_byte_position(self, text: str, line_num: int, char_pos: int) -> int:
        """Calculate byte position from line number and character position."""
        lines = text.split('\n')
        byte_pos = 0
        
        # Add bytes for all previous lines (including newlines)
        for i in range(line_num):
            if i < len(lines):
                byte_pos += len(lines[i].encode('utf-8')) + 1  # +1 for newline
        
        # Add bytes for characters in current line up to char_pos
        if line_num < len(lines):
            current_line = lines[line_num]
            byte_pos += len(current_line[:char_pos].encode('utf-8'))
        
        return byte_pos
    
    def _generate_message(self, var_name: str, deref_text: str, language: str) -> str:
        """Generate appropriate error message for the dereference."""
        null_term = {
            "java": "null",
            "csharp": "null", 
            "cpp": "null",
            "c": "NULL",
            "python": "None",
            "typescript": "null/undefined"
        }.get(language, "null")
        
        return f"Possible {null_term} dereference of '{var_name}'. Check for {null_term} before dereferencing or ensure a non-null contract."
    
    def _generate_suggestion(self, var_name: str, language: str) -> str:
        """Generate language-specific suggestion for fixing the issue."""
        suggestions = {
            "java": f"Add null check: if ({var_name} != null) {{ ... }} or use Objects.requireNonNull({var_name})",
            "csharp": f"Add null check: if ({var_name} != null) {{ ... }} or use ArgumentNullException.ThrowIfNull({var_name})",
            "cpp": f"Add null check: if ({var_name} != nullptr) {{ ... }} or use assertions",
            "c": f"Add null check: if ({var_name} != NULL) {{ ... }} or use assertions", 
            "python": f"Add null check: if {var_name} is not None: ... or use assert {var_name} is not None",
            "typescript": f"Add null check: if ({var_name} != null) {{ ... }} or use optional chaining: {var_name}?."
        }
        
        return suggestions.get(language, f"Add null check before using {var_name}")


# Register the rule
_rule = BugNullDerefPossibleRule()
RULES = [_rule]


