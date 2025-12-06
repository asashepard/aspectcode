"""
Iteration Modification Detection Rule

This rule detects mutations of a collection while iterating over it with 
for-each/for...of/for...in/each loops. Such mutations can lead to undefined 
behavior, runtime errors, or incorrect results.

Common problematic patterns:
- Adding/removing items during iteration
- Modifying collection structure while looping
- Element assignment that changes iteration order

Examples:
- RISKY: for x in items: items.append(x)  
- SAFE:  for x in list(items): items.append(x)

- RISKY: for (const v of arr) { arr.splice(0, 1); }
- SAFE:  for (const v of [...arr]) { arr.splice(0, 1); }

- RISKY: for item in collection { collection.remove(item) }
- SAFE:  iterator.remove() or iterate over snapshot
"""

import re
from typing import Iterable, Set, Optional, List, Dict

try:
    from ..engine.types import Rule, RuleMeta, Requires, RuleContext, Finding
except ImportError:
    # Handle direct execution or testing
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding


class BugIterationModificationRule:
    """
    Detects mutations of collections during for-each iteration.
    
    This rule identifies cases where a collection is being modified while
    iterating over it, which can lead to undefined behavior, runtime errors,
    or incorrect results. It suggests using snapshots or safe removal APIs.
    
    Covers multiple iteration patterns:
    - Python: for x in collection
    - JavaScript/TypeScript: for (x of collection), for (x in collection)
    - Java: for (Type x : collection)
    - C#: foreach (Type x in collection)
    - Ruby: collection.each { |x| ... }
    """
    
    meta = RuleMeta(
        id="bug.iteration_modification",
        category="bug",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Flags mutations of collections during for-each iteration; suggests using snapshots or safe removal APIs",
        langs=["python", "java", "csharp", "javascript", "typescript", "ruby"]
    )
    
    requires = Requires(syntax=True)
    
    # Methods that mutate collections in each language
    MUTATING_METHODS = {
        "python": {"append", "extend", "insert", "remove", "pop", "clear", "update", "discard", "add"},
        "javascript": {"push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin", "clear", "delete"},
        "typescript": {"push", "pop", "shift", "unshift", "splice", "sort", "reverse", "fill", "copyWithin", "clear", "delete"},
        "java": {"add", "addAll", "remove", "removeAll", "removeIf", "retainAll", "clear", "put", "putAll"},
        "csharp": {"Add", "AddRange", "Remove", "RemoveAt", "RemoveAll", "Clear", "Insert", "InsertRange", "Enqueue", "Dequeue", "Push", "Pop", "TryDequeue", "TryPop"},
        "ruby": {"push", "<<", "pop", "shift", "unshift", "insert", "delete", "delete_if", "clear", "merge!", "update"},
    }
    
    # Patterns for detecting for-each loops in different languages
    FOREACH_PATTERNS = {
        "python": [
            r'for\s+\w+\s+in\s+(\w+)\s*:',  # for x in collection:
            r'for\s+\w+\s*,\s*\w+\s+in\s+enumerate\s*\(\s*(\w+)\s*\)\s*:',  # for i, x in enumerate(collection):
        ],
        "javascript": [
            r'for\s*\(\s*(?:const|let|var)?\s*\w+\s+(?:of|in)\s+(\w+)\s*\)',  # for (x of/in collection)
        ],
        "typescript": [
            r'for\s*\(\s*(?:const|let|var)?\s*\w+\s+(?:of|in)\s+(\w+)\s*\)',  # for (x of/in collection)
        ],
        "java": [
            r'for\s*\(\s*\w+\s+\w+\s*:\s*(\w+)\s*\)',  # for (Type x : collection)
        ],
        "csharp": [
            r'foreach\s*\(\s*\w+\s+\w+\s+in\s+(\w+)\s*\)',  # foreach (Type x in collection)
        ],
        "ruby": [
            r'(\w+)\.each\s*\{',  # collection.each { |x| ... }
            r'(\w+)\.each\s+do',  # collection.each do |x| ... end
        ],
    }
    
    # Patterns that indicate safe iteration (snapshots)
    SNAPSHOT_PATTERNS = [
        r'list\(',      # Python: list(collection)
        r'tuple\(',     # Python: tuple(collection)
        r'set\(',       # Python: set(collection)
        r'sorted\(',    # Python: sorted(collection)
        r'copy\(',      # Various: copy(collection)
        r'slice\(',     # Various: slice(collection)
        r'clone\(',     # Various: clone(collection)
        r'toList\(',    # Java: collection.toList()
        r'Array\.from\(',  # JS: Array.from(collection)
        r'\[\.\.\.',    # JS/TS: [...collection]
    ]
    
    def visit(self, ctx: RuleContext) -> Iterable[Finding]:
        """Analyze text for iteration modification patterns."""
        if ctx.language not in self.meta.langs:
            return
        
        # Analyze text using pattern matching approach
        yield from self._analyze_text(ctx, ctx.text, ctx.language)
    
    def _analyze_text(self, ctx: RuleContext, text: str, language: str) -> Iterable[Finding]:
        """Analyze text for collection mutation during iteration."""
        lines = text.split('\n')
        
        for line_num, line in enumerate(lines):
            # Skip comments and strings to avoid false positives
            if self._is_comment_or_string_line(line, language):
                continue
            
            # Look for for-each loop patterns
            patterns = self.FOREACH_PATTERNS.get(language, [])
            for pattern in patterns:
                for match in re.finditer(pattern, line, re.IGNORECASE):
                    collection_name = match.group(1)
                    
                    # Skip if this looks like a snapshot iteration
                    if self._is_snapshot_iteration(line):
                        continue
                    
                    # Find the loop body and check for mutations
                    loop_start_line = line_num
                    if self._loop_body_mutates_collection(lines, loop_start_line, collection_name, language):
                        # Calculate byte position for the loop header
                        line_start_byte = sum(len(lines[i]) + 1 for i in range(line_num))
                        match_start = line_start_byte + match.start()
                        match_end = line_start_byte + match.end()
                        
                        finding = Finding(
                            rule=self.meta.id,
                            message="Modifying a collection while iterating over it—this can skip items or cause errors.",
                            file=ctx.file_path,
                            start_byte=match_start,
                            end_byte=match_end,
                            severity="error",
                            autofix=None,  # suggest-only
                            meta={
                                "suggestion": self._generate_suggestion(collection_name, language),
                                "collection": collection_name,
                                "language": language
                            }
                        )
                        yield finding
    
    def _is_comment_or_string_line(self, line: str, language: str) -> bool:
        """Check if line is primarily a comment or string literal."""
        stripped = line.strip()
        
        # Language-specific comment patterns
        comment_patterns = {
            "python": [r'^\s*#'],
            "javascript": [r'^\s*//', r'^\s*/\*'],
            "typescript": [r'^\s*//', r'^\s*/\*'],
            "java": [r'^\s*//', r'^\s*/\*'],
            "csharp": [r'^\s*//', r'^\s*/\*'],
            "ruby": [r'^\s*#']
        }
        
        patterns = comment_patterns.get(language, [])
        for pattern in patterns:
            if re.match(pattern, stripped):
                return True
        
        return False
    
    def _is_snapshot_iteration(self, line: str) -> bool:
        """Check if the iteration is over a snapshot (safe pattern)."""
        # Remove spaces to make pattern matching more reliable
        normalized_line = line.replace(' ', '')
        
        for pattern in self.SNAPSHOT_PATTERNS:
            if re.search(pattern, normalized_line):
                return True
        
        return False
    
    def _loop_body_mutates_collection(self, lines: List[str], loop_start_line: int, collection_name: str, language: str) -> bool:
        """Check if the loop body contains mutations of the specified collection."""
        # Find the extent of the loop body
        body_lines = self._extract_loop_body(lines, loop_start_line, language)
        
        # Check each line in the body for mutations
        for body_line in body_lines:
            if self._line_mutates_collection(body_line, collection_name, language):
                return True
        
        return False
    
    def _extract_loop_body(self, lines: List[str], loop_start_line: int, language: str) -> List[str]:
        """Extract the lines that constitute the loop body."""
        body_lines = []
        
        if language == "python":
            # Python uses indentation
            return self._extract_python_loop_body(lines, loop_start_line)
        elif language in ["javascript", "typescript", "java", "csharp"]:
            # These languages use braces
            return self._extract_braced_loop_body(lines, loop_start_line)
        elif language == "ruby":
            # Ruby uses blocks
            return self._extract_ruby_loop_body(lines, loop_start_line)
        
        return body_lines
    
    def _extract_python_loop_body(self, lines: List[str], loop_start_line: int) -> List[str]:
        """Extract Python loop body based on indentation."""
        body_lines = []
        
        if loop_start_line >= len(lines):
            return body_lines
        
        # Find the base indentation level of the for statement
        for_line = lines[loop_start_line]
        base_indent = len(for_line) - len(for_line.lstrip())
        
        # Collect indented lines following the for statement
        current_line = loop_start_line + 1
        while current_line < len(lines):
            line = lines[current_line]
            
            # Skip empty lines
            if not line.strip():
                current_line += 1
                continue
            
            # Check indentation
            line_indent = len(line) - len(line.lstrip())
            
            # If indentation is greater than base, it's part of the body
            if line_indent > base_indent:
                body_lines.append(line)
            else:
                # We've reached the end of the loop body
                break
            
            current_line += 1
        
        return body_lines
    
    def _extract_braced_loop_body(self, lines: List[str], loop_start_line: int) -> List[str]:
        """Extract loop body for languages that use braces."""
        body_lines = []
        
        # Find the opening brace
        brace_count = 0
        found_opening = False
        current_line = loop_start_line
        
        # Look for opening brace (might be on same line or next line)
        while current_line < len(lines):
            line = lines[current_line]
            
            for char in line:
                if char == '{':
                    brace_count += 1
                    if not found_opening:
                        found_opening = True
                        # Start collecting from next line
                        current_line += 1
                        break
                elif char == '}':
                    brace_count -= 1
                    if found_opening and brace_count == 0:
                        # End of loop body
                        return body_lines
            
            if found_opening and current_line < len(lines):
                body_lines.append(lines[current_line])
            
            current_line += 1
            
            # Safety check to avoid infinite loops
            if current_line > loop_start_line + 100:
                break
        
        return body_lines
    
    def _extract_ruby_loop_body(self, lines: List[str], loop_start_line: int) -> List[str]:
        """Extract Ruby loop body for each blocks."""
        body_lines = []
        
        if loop_start_line >= len(lines):
            return body_lines
        
        each_line = lines[loop_start_line]
        
        # Check if it's a single-line block { ... }
        if '{' in each_line and '}' in each_line:
            # Single line block
            body_lines.append(each_line)
        elif '{' in each_line:
            # Multi-line block with braces
            brace_count = each_line.count('{') - each_line.count('}')
            current_line = loop_start_line + 1
            
            while current_line < len(lines) and brace_count > 0:
                line = lines[current_line]
                brace_count += line.count('{') - line.count('}')
                body_lines.append(line)
                current_line += 1
        elif 'do' in each_line:
            # Multi-line block with do...end
            current_line = loop_start_line + 1
            
            while current_line < len(lines):
                line = lines[current_line]
                if line.strip().startswith('end'):
                    break
                body_lines.append(line)
                current_line += 1
        
        return body_lines
    
    def _line_mutates_collection(self, line: str, collection_name: str, language: str) -> bool:
        """Check if a line contains mutations of the specified collection."""
        # Check for method calls that mutate the collection
        mutating_methods = self.MUTATING_METHODS.get(language, set())
        
        for method in mutating_methods:
            # Pattern: collection.method(...) or collection method(...) 
            method_pattern = rf'\b{re.escape(collection_name)}\.{re.escape(method)}\s*\('
            if re.search(method_pattern, line):
                return True
            
            # Ruby special syntax: collection << item
            if language == "ruby" and method == "<<":
                append_pattern = rf'\b{re.escape(collection_name)}\s*<<\s*\w+'
                if re.search(append_pattern, line):
                    return True
        
        # Check for element assignment: collection[index] = value
        element_assign_pattern = rf'\b{re.escape(collection_name)}\[.+?\]\s*='
        if re.search(element_assign_pattern, line):
            return True
        
        # Check for delete operations
        if language == "python":
            del_pattern = rf'\bdel\s+{re.escape(collection_name)}\['
            if re.search(del_pattern, line):
                return True
        elif language in ["javascript", "typescript"]:
            delete_pattern = rf'\bdelete\s+{re.escape(collection_name)}\['
            if re.search(delete_pattern, line):
                return True
        
        return False
    
    def _generate_suggestion(self, collection_name: str, language: str) -> str:
        """Generate a language-specific suggestion for safe iteration."""
        suggestions = {
            "python": f"Iterate over list({collection_name}) or use a while loop with iterator",
            "javascript": f"Iterate over [...{collection_name}] or use a traditional for loop",
            "typescript": f"Iterate over [...{collection_name}] or use a traditional for loop",
            "java": f"Use Iterator.remove() or iterate over {collection_name}.toList()",
            "csharp": f"Iterate over {collection_name}.ToList() or use a for loop with indices",
            "ruby": f"Iterate over {collection_name}.dup or use while/until with iterator"
        }
        
        return suggestions.get(language, f"Iterate over a copy of {collection_name} to avoid concurrent modification")


# Register the rule
_rule = BugIterationModificationRule()
RULES = [_rule]


