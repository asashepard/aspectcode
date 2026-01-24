/**
 * TypeScript types for Aspect Code Engine Protocol v1
 * 
 * These interfaces mirror the JSON schema defined in server/engine/schema_protocol.md
 * and provide type safety for the VS Code extension.
 */

// ============================================================================
// Core Protocol Types
// ============================================================================

export interface ProtocolVersion {
  "aspect-code.protocol": string;
  engine_version: string;
}

export interface Range {
  startLine: number;  // 1-based
  startCol: number;   // 0-based
  endLine: number;    // 1-based
  endCol: number;     // 0-based
}

export interface Edit {
  file_path: string;
  start_byte: number;
  end_byte: number;
  replacement: string;
  range: Range;
}

export interface FindingMeta {
  tier?: number;
  category?: string;
  priority?: string;
  suggestions?: string[];
  [key: string]: any;  // Allow additional metadata
}

export interface Finding {
  rule_id: string;
  message: string;
  file_path: string;
  uri: string;
  start_byte: number;
  end_byte: number;
  range: Range;
  severity: "error" | "warning" | "info";
  code_frame?: string;
  suppression_hint?: string;
  meta?: FindingMeta;
}

export interface Metrics {
  parse_ms: number;
  rules_ms: number;
  total_ms: number;
}

export interface ScanResult extends ProtocolVersion {
  files_scanned: number;
  rules_run: number;
  findings: Finding[];
  metrics: Metrics;
}

// ============================================================================
// Validation and Error Types
// ============================================================================

export interface ProtocolError {
  type: "version_mismatch" | "invalid_json" | "missing_fields" | "validation_error";
  message: string;
  details?: any;
}

export interface ValidationResult {
  success: boolean;
  data?: ScanResult;
  error?: ProtocolError;
}

// ============================================================================
// Protocol Decoder and Validator
// ============================================================================

/**
 * Current supported protocol version.
 * Update this when the protocol changes.
 */
export const SUPPORTED_PROTOCOL_VERSION = "1";

/**
 * Validates that a value is a string.
 */
function isString(value: any): value is string {
  return typeof value === "string";
}

/**
 * Validates that a value is a number.
 */
function isNumber(value: any): value is number {
  return typeof value === "number" && !isNaN(value);
}

/**
 * Validates that a value is an object (not null or array).
 */
function isObject(value: any): value is Record<string, any> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Validates that a value is an array.
 */
function isArray(value: any): value is any[] {
  return Array.isArray(value);
}

/**
 * Validates a Range object.
 */
function validateRange(value: any): value is Range {
  if (!isObject(value)) return false;
  
  return (
    isNumber(value.startLine) && value.startLine >= 1 &&
    isNumber(value.startCol) && value.startCol >= 0 &&
    isNumber(value.endLine) && value.endLine >= 1 &&
    isNumber(value.endCol) && value.endCol >= 0
  );
}

/**
 * Validates a Finding object.
 */
function validateFinding(value: any): value is Finding {
  if (!isObject(value)) return false;
  
  // Required fields
  if (
    !isString(value.rule_id) ||
    !isString(value.message) ||
    !isString(value.file_path) ||
    !isString(value.uri) ||
    !isNumber(value.start_byte) || value.start_byte < 0 ||
    !isNumber(value.end_byte) || value.end_byte < 0 ||
    !validateRange(value.range) ||
    !["error", "warning", "info"].includes(value.severity)
  ) {
    return false;
  }
  
  // Optional fields
  if (value.code_frame !== undefined && !isString(value.code_frame)) {
    return false;
  }
  
  if (value.suppression_hint !== undefined && !isString(value.suppression_hint)) {
    return false;
  }
  
  if (value.meta !== undefined && !isObject(value.meta)) {
    return false;
  }
  
  return true;
}

/**
 * Validates a Metrics object.
 */
function validateMetrics(value: any): value is Metrics {
  if (!isObject(value)) return false;
  
  return (
    isNumber(value.parse_ms) && value.parse_ms >= 0 &&
    isNumber(value.rules_ms) && value.rules_ms >= 0 &&
    isNumber(value.total_ms) && value.total_ms >= 0
  );
}

/**
 * Validates and decodes a ScanResult from raw JSON.
 * 
 * @param rawJson - Raw JSON string from the engine
 * @returns Validation result with typed data or error
 */
export function decodeScanResult(rawJson: string): ValidationResult {
  let parsed: any;
  
  // Parse JSON
  try {
    parsed = JSON.parse(rawJson);
  } catch (error) {
    return {
      success: false,
      error: {
        type: "invalid_json",
        message: "Failed to parse JSON response from engine",
        details: error
      }
    };
  }
  
  // Check protocol version
  if (!isString(parsed["aspect-code.protocol"])) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'aspectcode.protocol' field",
        details: parsed
      }
    };
  }
  
  if (parsed["aspect-code.protocol"] !== SUPPORTED_PROTOCOL_VERSION) {
    return {
      success: false,
      error: {
        type: "version_mismatch",
        message: `Protocol version mismatch. Expected '${SUPPORTED_PROTOCOL_VERSION}', got '${parsed["aspect-code.protocol"]}'`,
        details: parsed
      }
    };
  }
  
  // Check required fields
  if (!isString(parsed.engine_version)) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'engine_version' field",
        details: parsed
      }
    };
  }
  
  if (!isNumber(parsed.files_scanned) || parsed.files_scanned < 0) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'files_scanned' field",
        details: parsed
      }
    };
  }
  
  if (!isNumber(parsed.rules_run) || parsed.rules_run < 0) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'rules_run' field",
        details: parsed
      }
    };
  }
  
  if (!isArray(parsed.findings)) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'findings' field - must be an array",
        details: parsed
      }
    };
  }
  
  if (!validateMetrics(parsed.metrics)) {
    return {
      success: false,
      error: {
        type: "missing_fields",
        message: "Missing or invalid 'metrics' field",
        details: parsed
      }
    };
  }
  
  // Validate findings (normalize severity first)
  for (let i = 0; i < parsed.findings.length; i++) {
    const finding = parsed.findings[i];
    
    // Normalize severity: 'warn' -> 'warning'
    if (finding && finding.severity === 'warn') {
      finding.severity = 'warning';
    }
    
    if (!validateFinding(finding)) {
      return {
        success: false,
        error: {
          type: "validation_error",
          message: `Invalid finding at index ${i}`,
          details: finding
        }
      };
    }
  }
  
  // All validation passed - return typed result
  return {
    success: true,
    data: parsed as ScanResult
  };
}

/**
 * Helper function to group findings by file.
 * 
 * @param findings - Array of findings
 * @returns Map of file path to findings
 */
export function groupFindingsByFile(findings: Finding[]): Map<string, Finding[]> {
  const grouped = new Map<string, Finding[]>();
  
  for (const finding of findings) {
    const existing = grouped.get(finding.file_path) || [];
    existing.push(finding);
    grouped.set(finding.file_path, existing);
  }
  
  return grouped;
}

/**
 * Helper function to create a suppression comment for a finding.
 * 
 * @param finding - Finding to create suppression for
 * @returns Suppression comment string
 */
export function createSuppressionComment(finding: Finding): string {
  if (finding.suppression_hint) {
    return finding.suppression_hint;
  }
  
  // Fallback to generic format
  return `# Aspect Code: ignore[${finding.rule_id}]`;
}

