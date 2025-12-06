import * as vscode from 'vscode';
import { decodeScanResult } from '../types/protocol';

// Use console.assert instead of chai for simpler testing
function assert(condition: any, message: string) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertEqual(actual: any, expected: any, message?: string) {
  if (actual !== expected) {
    throw new Error(message || `Expected ${expected}, got ${actual}`);
  }
}

suite('JSON Protocol v1 Integration', () => {
  test('Protocol decoder should parse mock scan result', () => {
    // Test that our protocol decoder works with JSON Protocol v1 string
    const mockJson = JSON.stringify({
      "aspect-code.protocol": "1",
      "engine_version": "0.1.0",
      "files_scanned": 1,
      "rules_run": 5,
      "findings": [
        {
          rule_id: "test-rule",
          message: "Test finding",
          file_path: "/test/file.py",
          uri: "file:///test/file.py",
          start_byte: 100,
          end_byte: 110,
          range: {
            startLine: 10,
            startCol: 5,
            endLine: 10,
            endCol: 15
          },
          severity: "error",
          autofix: [
            {
              file_path: "/test/file.py",
              start_byte: 100,
              end_byte: 110,
              replacement: "fixed_text",
              range: {
                startLine: 10,
                startCol: 5,
                endLine: 10,
                endCol: 15
              }
            }
          ]
        }
      ],
      "metrics": {
        parse_ms: 50,
        rules_ms: 40,
        total_ms: 100
      }
    });

    try {
      const result = decodeScanResult(mockJson);
      
      // Verify successful parsing
      assert(result.success, 'Protocol decoder should succeed');
      assert(result.data, 'Should have data when successful');
      
      if (!result.data) {
        throw new Error('Missing data in successful result');
      }
      
      // Verify protocol version
      assertEqual(result.data["aspect-code.protocol"], "1", 'Protocol version should be 1');
      assertEqual(result.data.engine_version, "0.1.0", 'Engine version should be 0.1.0');
      
      // Verify finding structure
      assertEqual(result.data.findings.length, 1, 'Should have 1 finding');
      const finding = result.data.findings[0];
      assertEqual(finding.rule_id, "test-rule", 'Rule ID should match');
      assertEqual(finding.message, "Test finding", 'Message should match');
      assertEqual(finding.severity, "error", 'Severity should match');
      assertEqual(finding.file_path, "/test/file.py", 'File path should match');
      assertEqual(finding.uri, "file:///test/file.py", 'URI should match');
      
      // Verify range structure
      assertEqual(finding.range.startLine, 10, 'Start line should match');
      assertEqual(finding.range.startCol, 5, 'Start column should match');
      assertEqual(finding.range.endLine, 10, 'End line should match');
      assertEqual(finding.range.endCol, 15, 'End column should match');
      
      // Verify autofix structure
      assert(finding.autofix && finding.autofix.length > 0, 'Should have autofix edits');
      assertEqual(finding.autofix[0].replacement, "fixed_text", 'Replacement text should match');
      
    } catch (error) {
      throw new Error(`Protocol decoder failed: ${error}`);
    }
  });

  test('New commands should be registered', async () => {
    // Test that the new JSON protocol commands are available
    const commands = await vscode.commands.getCommands();
    
    // Check for our new commands
    assert(commands.includes('aspectcode.scanWorkspace'), 'scanWorkspace command should be registered');
    assert(commands.includes('aspectcode.scanActiveFile'), 'scanActiveFile command should be registered');
    assert(commands.includes('aspectcode.applyAutofix'), 'applyAutofix command should be registered');
    assert(commands.includes('aspectcode.insertSuppression'), 'insertSuppression command should be registered');
    
    // The Aspect Code.openFinding command should also be available
    assert(commands.includes('aspectcode.openFinding'), 'openFinding command should be registered');
  });
});
