"""
Suppression system for Aspect Code rules.

This module provides functionality to parse and check suppression comments
in source code to selectively disable rule findings.
"""

import re
import fnmatch
from typing import Dict, List, Set, Tuple


class SuppressionParser:
    """Parser for Aspect Code suppression comments."""
    
    def __init__(self, text: str):
        self.text = text
        self.lines = text.split('\n')
        self._parse_suppressions()
    
    def _parse_suppressions(self):
        """Parse all suppression comments in the text."""
        self.line_suppressions: Dict[int, Set[str]] = {}  # line_number -> {rule_patterns}
        
        for line_num, line in enumerate(self.lines, 1):
            patterns = self._extract_suppression_patterns(line)
            if patterns:
                self.line_suppressions[line_num] = patterns
    
    def _extract_suppression_patterns(self, line: str) -> Set[str]:
        """Extract suppression patterns from a line."""
        patterns = set()
        
        # Look for aspect-code: ignore[pattern] comments
        ignore_pattern = r'#\s*aspect-code:\s*ignore\s*\[\s*([^\]]+)\s*\]'
        matches = re.finditer(ignore_pattern, line, re.IGNORECASE)
        
        for match in matches:
            pattern_list = match.group(1)
            # Split on commas and clean up whitespace
            for pattern in pattern_list.split(','):
                pattern = pattern.strip()
                if pattern:
                    patterns.add(pattern)
        
        return patterns
    
    def is_suppressed(self, rule_id: str, start_byte: int) -> bool:
        """Check if a rule finding should be suppressed."""
        # Convert byte offset to line number
        line_num = self._byte_to_line(start_byte)
        
        # Check suppressions on the same line
        if line_num in self.line_suppressions:
            for pattern in self.line_suppressions[line_num]:
                if self._matches_pattern(rule_id, pattern):
                    return True
        
        return False
    
    def _byte_to_line(self, byte_offset: int) -> int:
        """Convert byte offset to 1-based line number."""
        if byte_offset < 0:
            return 1
        if byte_offset >= len(self.text):
            return len(self.lines)
        
        # Count newlines up to byte offset
        lines_before = self.text[:byte_offset].count('\n')
        return lines_before + 1
    
    def _matches_pattern(self, rule_id: str, pattern: str) -> bool:
        """Check if a rule ID matches a suppression pattern."""
        # Exact match
        if rule_id == pattern:
            return True
        
        # Glob pattern match (e.g., imports.*)
        if fnmatch.fnmatch(rule_id, pattern):
            return True
        
        return False
    
    def get_suppression_stats(self) -> Dict[str, int]:
        """Get statistics about suppressions in the file."""
        all_patterns = set()
        for patterns in self.line_suppressions.values():
            all_patterns.update(patterns)
        
        return {
            "suppressed_lines": len(self.line_suppressions),
            "unique_patterns": len(all_patterns),
            "total_suppressions": sum(len(patterns) for patterns in self.line_suppressions.values())
        }


def filter_suppressed_findings(findings: List, text: str) -> List:
    """Filter out suppressed findings from a list."""
    if not findings:
        return findings
    
    parser = SuppressionParser(text)
    filtered_findings = []
    
    for finding in findings:
        rule_id = getattr(finding, 'rule', '')
        start_byte = getattr(finding, 'start_byte', 0)
        
        if not parser.is_suppressed(rule_id, start_byte):
            filtered_findings.append(finding)
    
    return filtered_findings


def validate_suppression_patterns(text: str) -> List[Tuple[int, str]]:
    """
    Validate suppression patterns in text and return any errors.
    
    Returns:
        List of (line_number, error_message) tuples
    """
    errors = []
    lines = text.split('\n')
    
    for line_num, line in enumerate(lines, 1):
        # Look for malformed patterns
        ignore_patterns = re.findall(r'#\s*Aspect Code:\s*ignore\s*\[[^\]]*\]', line, re.IGNORECASE)
        
        for pattern in ignore_patterns:
            # Check for empty brackets
            if re.search(r'\[\s*\]', pattern):
                errors.append((line_num, "Empty suppression pattern"))
            
            # Check for unclosed brackets
            if pattern.count('[') != pattern.count(']'):
                errors.append((line_num, "Unclosed suppression bracket"))
    
    return errors


