"""
Autofix service for applying safe automatic fixes to code.

This service takes findings from the validation engine and applies their
associated autofix edits to generate corrected code.
"""

import os
import sys
import time
import difflib
from typing import Dict, List, Optional, Set, Any
from pathlib import Path

# Add server to path for imports
server_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

try:
    from engine.validation import validate_paths
    from engine.types import Finding, Edit
    from engine.profiles import AUTO_FIX_V1_RULE_IDS
    print("[DEBUG] Successfully imported engine modules - using dataclass Finding")
except ImportError as e:
    print(f"Warning: Could not import engine modules: {e}")
    # Define minimal types for fallback
    class Finding:
        def __init__(self):
            self.autofix = None
            self.meta = {}
    class Edit:
        def __init__(self):
            self.start_byte = 0
            self.end_byte = 0
            self.replacement = ""
    AUTO_FIX_V1_RULE_IDS = []
    print("[DEBUG] Using fallback Finding class")

from ..models import AutofixRequest, AutofixResponse, AutofixFile, AutofixSkipped


class AutofixService:
    """Service for applying automatic fixes to code."""
    
    def __init__(self):
        # Use the official AUTO_FIX_V1_RULE_IDS from profiles
        self.safe_rules = set(AUTO_FIX_V1_RULE_IDS)
    
    def apply_autofixes(self, request: AutofixRequest) -> AutofixResponse:
        """Apply automatic fixes based on the request."""
        start_time = time.time()
        
        print(f"[DEBUG] Starting autofix for repo_root: {request.repo_root}")
        
        try:
            # Validate repo root
            if not os.path.isdir(request.repo_root):
                print(f"[DEBUG] Invalid repo root: {request.repo_root}")
                return AutofixResponse(
                    fixes_applied=0,
                    files_changed=0,
                    took_ms=int((time.time() - start_time) * 1000)
                )
            
            # Validate rule_id if provided (must be in AUTO_FIX_V1_RULE_IDS)
            if request.rule_id and request.rule_id not in self.safe_rules:
                print(f"[DEBUG] Rule {request.rule_id} not in AUTO_FIX_V1_RULE_IDS")
                return AutofixResponse(
                    fixes_applied=0,
                    files_changed=0,
                    skipped=[AutofixSkipped(
                        finding_id=request.finding_id or "unknown",
                        reason=f"Rule {request.rule_id} not in AUTO_FIX_V1_RULE_IDS (safe autofix rules)"
                    )],
                    took_ms=int((time.time() - start_time) * 1000)
                )
            
            print("[DEBUG] Validations passed, getting findings...")
            
            # Get current findings by running validation
            findings = self._get_findings(request)
            print(f"[DEBUG] Found {len(findings)} total findings")
            
            # Filter for safe autofixes
            safe_findings = self._filter_safe_findings(findings, request)
            print(f"[DEBUG] Filtered to {len(safe_findings)} safe autofixable findings")
            
            if not safe_findings:
                return AutofixResponse(
                    fixes_applied=0,
                    files_changed=0,
                    took_ms=int((time.time() - start_time) * 1000)
                )
            
            # Apply fixes and generate response
            return self._apply_fixes_to_files(safe_findings, request, start_time)
            
        except Exception as e:
            print(f"[DEBUG] Autofix error: {e}")
            import traceback
            traceback.print_exc()
            return AutofixResponse(
                fixes_applied=0,
                files_changed=0,
                took_ms=int((time.time() - start_time) * 1000)
            )
    
    def _get_findings(self, request: AutofixRequest) -> List[Finding]:
        """Get findings by running validation on the repository."""
        try:
            # Determine paths to validate
            if request.violation_files:
                paths = request.violation_files
            elif request.file_path:
                paths = [request.file_path]
            else:
                paths = [request.repo_root]
            
            # Run validation to get current findings
            # Use alpha_default profile to ensure we get the right rules
            result = validate_paths(paths, profile="alpha_default")
            
            # Convert dict findings back to Finding objects
            findings = []
            for finding_dict in result.get("findings", []):
                # Create Finding with required constructor arguments
                finding = Finding(
                    rule=finding_dict.get("rule_id", ""),
                    message=finding_dict.get("message", ""),
                    file=finding_dict.get("file_path", ""),
                    start_byte=finding_dict.get("start_byte", 0),
                    end_byte=finding_dict.get("end_byte", 0),
                    severity=finding_dict.get("severity", "warn"),
                    meta=finding_dict.get("meta", {}),
                    autofix=None  # Will be populated below if needed
                )
                
                # Convert autofix data to Edit objects if present
                if finding_dict.get("autofix"):
                    autofix_edits = []
                    for edit_dict in finding_dict["autofix"]:
                        edit = Edit(
                            start_byte=edit_dict["start_byte"],
                            end_byte=edit_dict["end_byte"],
                            replacement=edit_dict["replacement"]
                        )
                        autofix_edits.append(edit)
                    
                    # Create new Finding instance with autofix
                    finding = finding._replace(autofix=autofix_edits)
                
                findings.append(finding)
            
            return findings
            
        except Exception as e:
            print(f"Error getting findings: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def _filter_safe_findings(self, findings: List[Finding], request: AutofixRequest) -> List[Finding]:
        """Filter findings to only include safe autofixes."""
        safe_findings = []
        
        for finding in findings:
            # Skip if no autofix available
            if not finding.autofix:
                continue
            
            # CRITICAL: Rule must be in AUTO_FIX_V1_RULE_IDS
            if finding.rule not in self.safe_rules:
                print(f"[DEBUG] Skipping {finding.rule} - not in AUTO_FIX_V1_RULE_IDS")
                continue
            
            # If specific rule requested, filter by it
            if request.rule_id and request.rule_id != finding.rule:
                continue
                
            # If specific finding ID requested, filter by it
            if request.finding_id and hasattr(finding, 'id') and finding.id != request.finding_id:
                continue
                
            # If specific location requested, filter by it
            if (request.start_byte is not None and request.end_byte is not None and 
                request.file_path is not None):
                if (finding.file != request.file_path or
                    finding.start_byte != request.start_byte or
                    finding.end_byte != request.end_byte):
                    continue
            
            # If specific IDs requested, filter by them
            if request.select_ids or request.select:
                select_ids = request.select_ids or request.select or []
                finding_id = getattr(finding, 'id', None) or f"{finding.rule}_{finding.start_byte}"
                if finding_id not in select_ids:
                    continue
            
            # Limit number of fixes
            if len(safe_findings) >= request.max_fixes:
                break
            
            safe_findings.append(finding)
        
        return safe_findings
    
    def _apply_fixes_to_files(self, findings: List[Finding], request: AutofixRequest, start_time: float) -> AutofixResponse:
        """Apply edits to files and generate response."""
        # Group findings by file
        files_with_findings = {}
        skipped = []
        
        for finding in findings:
            if not finding.autofix:
                continue
            
            file_path = finding.file
            if file_path not in files_with_findings:
                files_with_findings[file_path] = []
            
            files_with_findings[file_path].append(finding)
        
        # Apply fixes to each file - ONE FINDING AT A TIME to avoid byte offset issues
        fixed_files = []
        total_fixes = 0
        
        for file_path, file_findings in files_with_findings.items():
            try:
                # Make path absolute
                if not os.path.isabs(file_path):
                    abs_path = os.path.join(request.repo_root, file_path)
                else:
                    abs_path = file_path
                
                # Read original file
                if not os.path.exists(abs_path):
                    continue
                
                with open(abs_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()
                
                # Collect ALL edits from ALL findings for this file
                all_edits = []
                for finding in file_findings:
                    if finding.autofix:
                        all_edits.extend(finding.autofix)
                
                # Apply all edits at once in reverse byte order
                # This prevents byte offset corruption between findings
                if all_edits:
                    current_content = self._apply_edits_to_content(original_content, all_edits)
                    total_fixes += len(all_edits)
                else:
                    current_content = original_content                
                # Only create fixed file entry if content changed
                if current_content != original_content:
                    # Calculate relative path for response
                    rel_path = os.path.relpath(abs_path, request.repo_root)
                    
                    fixed_files.append(AutofixFile(
                        relpath=rel_path,
                        content=current_content
                    ))
                
            except Exception as e:
                print(f"Error fixing file {file_path}: {e}")
                import traceback
                traceback.print_exc()
                skipped.append(AutofixSkipped(
                    finding_id=f"file_{file_path}",
                    reason=str(e)
                ))
        
        # Generate unified diff if files were changed
        patched_diff = None
        if fixed_files:
            patched_diff = self._generate_unified_diff(fixed_files, request.repo_root)
        
        return AutofixResponse(
            fixes_applied=total_fixes,
            files_changed=len(fixed_files),
            patched_diff=patched_diff,
            files=fixed_files if fixed_files else None,
            skipped=skipped if skipped else None,
            took_ms=int((time.time() - start_time) * 1000)
        )
    
    def _apply_edits_to_content(self, content: str, edits: List[Edit]) -> str:
        """Apply a list of edits to content, sorted by position in reverse order."""
        if not edits:
            return content
        
        # Merge overlapping or adjacent edits on the same line
        merged_edits = self._merge_same_line_edits(content, edits)
        
        # Sort edits by start_byte in descending order to avoid offset issues
        sorted_edits = sorted(merged_edits, key=lambda e: e.start_byte, reverse=True)
        
        # Apply edits from end to start
        result = content
        original_len = len(content)
        
        for edit in sorted_edits:
            # Validate edit bounds against ORIGINAL content length
            if edit.start_byte < 0 or edit.end_byte > original_len or edit.start_byte > edit.end_byte:
                continue
            
            # Validate edit bounds against CURRENT result length
            if edit.start_byte > len(result) or edit.end_byte > len(result):
                continue
            
            # Apply the edit
            result = result[:edit.start_byte] + edit.replacement + result[edit.end_byte:]
        
        return result
    
    def _merge_same_line_edits(self, content: str, edits: List[Edit]) -> List[Edit]:
        """Merge edits that affect the same line to avoid corruption."""
        if len(edits) <= 1:
            return edits
        
        # Group edits by which line they affect
        line_groups = {}
        for edit in edits:
            # Find the line containing this edit
            line_start = content.rfind('\n', 0, edit.start_byte)
            if line_start == -1:
                line_start = 0
            else:
                line_start += 1
            
            line_end = content.find('\n', edit.start_byte)
            if line_end == -1:
                line_end = len(content)
            else:
                line_end += 1  # Include newline
            
            line_key = (line_start, line_end)
            if line_key not in line_groups:
                line_groups[line_key] = []
            line_groups[line_key].append(edit)
        
        # Merge edits that are on the same line
        merged = []
        for (line_start, line_end), line_edits in line_groups.items():
            if len(line_edits) == 1:
                # Single edit on this line, no merging needed
                merged.append(line_edits[0])
            else:
                # Multiple edits on same line - check if they would corrupt
                # For now, if all edits are deletions (replacement=''), merge to remove entire line
                all_deletions = all(e.replacement == '' for e in line_edits)
                if all_deletions:
                    # Remove entire line
                    merged.append(Edit(line_start, line_end, ''))
                else:
                    # Keep individual edits (might need more sophisticated merging)
                    merged.extend(line_edits)
        
        return merged
    
    def _generate_unified_diff(self, fixed_files: List[AutofixFile], repo_root: str) -> str:
        """Generate a unified diff for all changed files."""
        diff_lines = []
        
        for file in fixed_files:
            abs_path = os.path.join(repo_root, file.relpath)
            
            try:
                # Read original content
                with open(abs_path, 'r', encoding='utf-8') as f:
                    original = f.read()
                
                # Generate diff for this file
                diff = difflib.unified_diff(
                    original.splitlines(keepends=True),
                    file.content.splitlines(keepends=True),
                    fromfile=f"a/{file.relpath}",
                    tofile=f"b/{file.relpath}"
                )
                
                diff_lines.extend(diff)
                
            except Exception as e:
                print(f"Error generating diff for {file.relpath}: {e}")
        
        return ''.join(diff_lines)


# Global service instance
_autofix_service = None

def get_autofix_service() -> AutofixService:
    """Get the global autofix service instance."""
    global _autofix_service
    if _autofix_service is None:
        _autofix_service = AutofixService()
    return _autofix_service