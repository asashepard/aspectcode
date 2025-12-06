"""
JSON schema validation for Aspect Code findings.

This module provides JSON schema definitions and validation helpers to ensure
findings conform to a well-defined contract for downstream tools.
"""

from typing import List, Dict, Any, Optional
import json
from pathlib import Path

# Current protocol version
PROTOCOL_VERSION = "1"
ENGINE_VERSION = "0.1.0"

# JSON Schema for a single Finding
FINDING_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_id": {
            "type": "string",
            "description": "Rule identifier that generated this finding"
        },
        "message": {
            "type": "string", 
            "description": "Human-readable description of the issue"
        },
        "file_path": {
            "type": "string",
            "description": "Absolute native file path where the issue was found"
        },
        "uri": {
            "type": "string",
            "description": "File URI for VS Code compatibility"
        },
        "start_byte": {
            "type": "integer",
            "minimum": 0,
            "description": "Start byte offset of the issue"
        },
        "end_byte": {
            "type": "integer", 
            "minimum": 0,
            "description": "End byte offset of the issue"
        },
        "range": {
            "type": "object",
            "properties": {
                "startLine": {"type": "integer", "minimum": 1},
                "startCol": {"type": "integer", "minimum": 0},
                "endLine": {"type": "integer", "minimum": 1},
                "endCol": {"type": "integer", "minimum": 0}
            },
            "required": ["startLine", "startCol", "endLine", "endCol"],
            "additionalProperties": False,
            "description": "Line/column range (1-based lines, 0-based columns)"
        },
        "severity": {
            "type": "string",
            "enum": ["info", "warning", "error"],
            "description": "Severity level of the finding"
        },
        "code_frame": {
            "type": "string",
            "description": "Source code excerpt with highlighting"
        },
        "autofix": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file_path": {"type": "string"},
                    "start_byte": {"type": "integer", "minimum": 0},
                    "end_byte": {"type": "integer", "minimum": 0},
                    "replacement": {"type": "string"},
                    "range": {
                        "type": "object",
                        "properties": {
                            "startLine": {"type": "integer", "minimum": 1},
                            "startCol": {"type": "integer", "minimum": 0},
                            "endLine": {"type": "integer", "minimum": 1},
                            "endCol": {"type": "integer", "minimum": 0}
                        },
                        "required": ["startLine", "startCol", "endLine", "endCol"],
                        "additionalProperties": False
                    }
                },
                "required": ["file_path", "start_byte", "end_byte", "replacement", "range"],
                "additionalProperties": False
            },
            "description": "Optional list of edits to fix the issue"
        },
        "suppression_hint": {
            "type": "string",
            "description": "Comment text to suppress this rule"
        },
        "meta": {
            "type": "object",
            "description": "Optional metadata about the finding"
        }
    },
    "required": ["rule_id", "message", "file_path", "uri", "start_byte", "end_byte", "range", "severity"],
    "additionalProperties": False
}

# JSON Schema for the full runner output
RUNNER_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "aspect-code.protocol": {
            "type": "string",
            "description": "Protocol version"
        },
        "engine_version": {
            "type": "string", 
            "description": "Engine version"
        },
        "files_scanned": {
            "type": "integer",
            "minimum": 0,
            "description": "Number of files that were scanned"
        },
        "rules_run": {
            "type": "integer", 
            "minimum": 0,
            "description": "Number of rules that were executed"
        },
        "findings": {
            "type": "array",
            "items": FINDING_JSON_SCHEMA,
            "description": "List of all findings"
        },
        "metrics": {
            "type": "object",
            "properties": {
                "parse_ms": {"type": "number", "minimum": 0},
                "rules_ms": {"type": "number", "minimum": 0}, 
                "total_ms": {"type": "number", "minimum": 0}
            },
            "required": ["parse_ms", "rules_ms", "total_ms"],
            "additionalProperties": False,
            "description": "Performance metrics"
        }
    },
    "required": ["aspect-code.protocol", "engine_version", "files_scanned", "rules_run", "findings", "metrics"],
    "additionalProperties": False
}


def normalize_path_for_protocol(file_path: str) -> tuple[str, str]:
    """
    Normalize a file path for protocol output.
    
    Args:
        file_path: File path (relative or absolute)
        
    Returns:
        Tuple of (absolute_native_path, file_uri)
    """
    path = Path(file_path).resolve()
    absolute_path = str(path)
    file_uri = path.as_uri()
    return absolute_path, file_uri


def byte_to_line_col(text: str, byte_offset: int) -> tuple[int, int]:
    """
    Convert byte offset to 1-based line, 0-based column.
    
    Args:
        text: Source text
        byte_offset: Byte offset (0-based)
        
    Returns:
        Tuple of (line, col) where line is 1-based, col is 0-based
    """
    if byte_offset >= len(text):
        byte_offset = len(text)
    
    # Count newlines up to byte_offset
    line = text[:byte_offset].count('\n') + 1
    
    # Find start of current line
    last_newline = text.rfind('\n', 0, byte_offset)
    if last_newline == -1:
        col = byte_offset
    else:
        col = byte_offset - last_newline - 1
    
    return line, col


def create_range_from_bytes(text: str, start_byte: int, end_byte: int) -> dict:
    """
    Create a protocol range object from byte offsets.
    
    Args:
        text: Source text
        start_byte: Start byte offset
        end_byte: End byte offset
        
    Returns:
        Range dictionary with startLine, startCol, endLine, endCol
    """
    start_line, start_col = byte_to_line_col(text, start_byte)
    end_line, end_col = byte_to_line_col(text, end_byte)
    
    return {
        "startLine": start_line,
        "startCol": start_col,
        "endLine": end_line,
        "endCol": end_col
    }


def validate_findings(findings: List[Dict[str, Any]]) -> List[str]:
    """
    Validate a list of findings against the JSON schema.
    
    Args:
        findings: List of finding dictionaries to validate
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    # Try to import jsonschema for full validation
    try:
        import jsonschema
        
        for i, finding in enumerate(findings):
            try:
                jsonschema.validate(finding, FINDING_JSON_SCHEMA)
            except jsonschema.ValidationError as e:
                errors.append(f"Finding {i}: {e.message}")
            except Exception as e:
                errors.append(f"Finding {i}: Validation error: {e}")
                
    except ImportError:
        # Fallback to basic validation without jsonschema
        for i, finding in enumerate(findings):
            errors.extend(_basic_validate_finding(finding, i))
    
    return errors


def validate_runner_output(output: Dict[str, Any]) -> List[str]:
    """
    Validate runner output against the schema.
    
    Args:
        output: Runner output dictionary
        
    Returns:
        List of validation errors (empty if valid)
    """
    errors = []
    
    try:
        import jsonschema
        try:
            jsonschema.validate(output, RUNNER_OUTPUT_SCHEMA)
        except jsonschema.ValidationError as e:
            errors.append(f"Output validation: {e.message}")
        except Exception as e:
            errors.append(f"Output validation error: {e}")
            
    except ImportError:
        # Basic validation without jsonschema
        errors.extend(_basic_validate_output(output))
    
    return errors


def _basic_validate_finding(finding: Dict[str, Any], index: int) -> List[str]:
    """Basic validation without jsonschema dependency."""
    errors = []
    
    # Required fields
    required_fields = ["rule", "message", "file", "start_byte", "end_byte", "severity"]
    for field in required_fields:
        if field not in finding:
            errors.append(f"Finding {index}: Missing required field '{field}'")
        elif finding[field] is None:
            errors.append(f"Finding {index}: Field '{field}' cannot be null")
    
    # Type checks
    if "rule" in finding and not isinstance(finding["rule"], str):
        errors.append(f"Finding {index}: 'rule' must be a string")
        
    if "message" in finding and not isinstance(finding["message"], str):
        errors.append(f"Finding {index}: 'message' must be a string")
        
    if "file" in finding and not isinstance(finding["file"], str):
        errors.append(f"Finding {index}: 'file' must be a string")
        
    for byte_field in ["start_byte", "end_byte"]:
        if byte_field in finding:
            if not isinstance(finding[byte_field], int) or finding[byte_field] < 0:
                errors.append(f"Finding {index}: '{byte_field}' must be a non-negative integer")
    
    if "severity" in finding and finding["severity"] not in ["info", "warn", "error"]:
        errors.append(f"Finding {index}: 'severity' must be one of: info, warn, error")
    
    return errors


def _basic_validate_output(output: Dict[str, Any]) -> List[str]:
    """Basic validation for runner output without jsonschema."""
    errors = []
    
    # Required fields
    required_fields = ["files_scanned", "rules_run", "findings", "metrics"]
    for field in required_fields:
        if field not in output:
            errors.append(f"Missing required field '{field}'")
    
    # Type checks
    for int_field in ["files_scanned", "rules_run"]:
        if int_field in output:
            if not isinstance(output[int_field], int) or output[int_field] < 0:
                errors.append(f"'{int_field}' must be a non-negative integer")
    
    if "findings" in output:
        if not isinstance(output["findings"], list):
            errors.append("'findings' must be a list")
        else:
            for i, finding in enumerate(output["findings"]):
                errors.extend(_basic_validate_finding(finding, i))
    
    if "metrics" in output:
        if not isinstance(output["metrics"], dict):
            errors.append("'metrics' must be an object")
        else:
            required_metrics = ["parse_ms", "rules_ms", "total_ms"]
            for metric in required_metrics:
                if metric not in output["metrics"]:
                    errors.append(f"Missing required metric '{metric}'")
                elif not isinstance(output["metrics"][metric], (int, float)) or output["metrics"][metric] < 0:
                    errors.append(f"Metric '{metric}' must be a non-negative number")
    
    return errors


def findings_to_json(findings: List[Any], text_cache: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """
    Convert Finding objects to JSON-serializable dictionaries.
    
    Args:
        findings: List of Finding objects
        text_cache: Optional cache of file_path -> text content for range conversion
        
    Returns:
        List of finding dictionaries conforming to protocol v1
    """
    if text_cache is None:
        text_cache = {}
        
    result = []
    for finding in findings:
        # Normalize path and create URI
        abs_path, uri = normalize_path_for_protocol(finding.file)
        
        # Get source text for range conversion
        text = text_cache.get(abs_path, "")
        range_obj = create_range_from_bytes(text, finding.start_byte, finding.end_byte)
        
        finding_dict = {
            "rule_id": finding.rule,
            "message": finding.message,
            "file_path": abs_path,
            "uri": uri,
            "start_byte": finding.start_byte,
            "end_byte": finding.end_byte,
            "range": range_obj,
            "severity": finding.severity
        }
        
        # Add autofix with both byte and range info
        if finding.autofix:
            finding_dict["autofix"] = []
            for edit in finding.autofix:
                # Normalize edit file path (could be different from finding file)
                edit_abs_path, _ = normalize_path_for_protocol(getattr(edit, 'file_path', finding.file))
                edit_text = text_cache.get(edit_abs_path, text)  # Fallback to finding text
                edit_range = create_range_from_bytes(edit_text, edit.start_byte, edit.end_byte)
                
                finding_dict["autofix"].append({
                    "file_path": edit_abs_path,
                    "start_byte": edit.start_byte,
                    "end_byte": edit.end_byte,
                    "replacement": edit.replacement,
                    "range": edit_range
                })
        
        # Add suppression hint if available
        if hasattr(finding, 'suppression_hint') and finding.suppression_hint:
            finding_dict["suppression_hint"] = finding.suppression_hint
        
        # Add meta if available
        if finding.meta:
            finding_dict["meta"] = finding.meta
            
        result.append(finding_dict)
    
    return result


def findings_to_legacy_violations(findings: List[Any], text_cache: Dict[str, str] = None) -> List[Dict[str, Any]]:
    """
    Convert Finding objects to legacy violations format for backward compatibility.
    
    Args:
        findings: List of Finding objects
        text_cache: Optional cache of file_path -> text content for location strings
        
    Returns:
        List of violation dictionaries in legacy format
    """
    import hashlib
    
    if text_cache is None:
        text_cache = {}
        
    result = []
    for finding in findings:
        # Normalize path
        abs_path, _ = normalize_path_for_protocol(finding.file)
        
        # Get source text for line/col conversion
        text = text_cache.get(abs_path, "")
        start_line, start_col = byte_to_line_col(text, finding.start_byte)
        end_line, end_col = byte_to_line_col(text, finding.end_byte)
        
        # Create stable ID for legacy compatibility
        location_str = f"{abs_path}:{start_line}:{start_col}-{end_line}:{end_col}"
        primary_name = getattr(finding, 'primary_name', finding.rule)
        stable_id = hashlib.sha1(f"{finding.rule}:{location_str}:{primary_name}".encode()).hexdigest()[:12]
        
        # Map severity from protocol v1 to legacy format
        severity_map = {"info": "low", "warn": "medium", "warning": "medium", "error": "high"}
        legacy_severity = severity_map.get(finding.severity, "medium")
        
        violation = {
            "id": stable_id,
            "rule": finding.rule,
            "explain": finding.message,
            "severity": legacy_severity,
            "locations": [location_str],
            "fixable": bool(finding.autofix and len(finding.autofix) > 0)
        }
        
        # Add suggested_patchlet if available
        if finding.autofix and finding.autofix:
            # Create a short label for the fix type
            patchlet_name = _infer_patchlet_name(finding)
            violation["suggested_patchlet"] = patchlet_name
        
        result.append(violation)
    
    return result


def _infer_patchlet_name(finding: Any) -> str:
    """Infer a patchlet name from the finding metadata."""
    if finding.meta:
        # Check for specific patterns in meta
        if "replacement" in finding.meta:
            return "replace_op"
        elif "unused" in finding.rule:
            return "remove_unused_import"
        elif "mutable" in finding.rule:
            return "none_guard"
        elif "equality" in finding.rule:
            return "strict_equality"
    
    # Fallback to rule-based inference
    if "imports.unused" in finding.rule:
        return "remove_unused_import"
    elif "ts_loose_equality" in finding.rule:
        return "strict_equality"
    elif "mut.default_mutable_arg" in finding.rule:
        return "none_guard"
    else:
        return "autofix"

