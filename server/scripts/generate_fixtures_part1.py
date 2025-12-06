#!/usr/bin/env python3
"""
Auto-generate test fixtures for all alpha rules across all supported languages.

Each fixture is a minimal code snippet designed to trigger exactly one rule.
"""

import json
from pathlib import Path

# Target languages for testing
TARGET_LANGS = ["python", "typescript", "javascript", "java", "csharp"]

# File extensions by language
EXTENSIONS = {
    "python": ".py",
    "typescript": ".ts",
    "javascript": ".js",
    "java": ".java",
    "csharp": ".cs"
}

# Fixture templates per rule per language
# Each template should trigger the specified rule
FIXTURES = {
    "imports.unused": {
        "python": '''# Should trigger: imports.unused
import os
import sys  # unused

def main():
    print(os.getcwd())
''',
        "typescript": '''// Should trigger: imports.unused
import fs from 'fs';
import path from 'path';  // unused

console.log(fs.existsSync('.'));
''',
        "javascript": '''// Should trigger: imports.unused
const fs = require('fs');
const path = require('path');  // unused

console.log(fs.existsSync('.'));
''',
        "java": '''// Should trigger: imports.unused
import java.util.List;
import java.util.Map;  // unused

public class UnusedImport {
    public void test() {
        List<String> items = null;
    }
}
''',
        "csharp": '''// Should trigger: imports.unused
using System;
using System.IO;  // unused

public class UnusedImport {
    public void Test() {
        Console.WriteLine("test");
    }
}
'''
    },
    
    "deadcode.unused_variable": {
        "python": '''# Should trigger: deadcode.unused_variable
def example():
    used = 1
    unused = 2  # unused variable
    return used
''',
        "typescript": '''// Should trigger: deadcode.unused_variable
function example(): number {
    const used = 1;
    const unused = 2;  // unused variable
    return used;
}
''',
        "javascript": '''// Should trigger: deadcode.unused_variable
function example() {
    const used = 1;
    const unused = 2;  // unused variable
    return used;
}
''',
        "java": '''// Should trigger: deadcode.unused_variable
public class UnusedVariable {
    public int example() {
        int used = 1;
        int unused = 2;  // unused variable
        return used;
    }
}
''',
        "csharp": '''// Should trigger: deadcode.unused_variable
public class UnusedVariable {
    public int Example() {
        int used = 1;
        int unused = 2;  // unused variable
        return used;
    }
}
'''
    },

    "sec.sql_injection_concat": {
        "python": '''# Should trigger: sec.sql_injection_concat
import sqlite3

def unsafe_query(user_input):
    conn = sqlite3.connect(':memory:')
    cursor = conn.cursor()
    query = "SELECT * FROM users WHERE name = '" + user_input + "'"
    cursor.execute(query)
    return cursor.fetchall()
''',
        "typescript": '''// Should trigger: sec.sql_injection_concat
async function unsafeQuery(userInput: string, db: any) {
    const query = "SELECT * FROM users WHERE name = '" + userInput + "'";
    return await db.query(query);
}
''',
        "javascript": '''// Should trigger: sec.sql_injection_concat
async function unsafeQuery(userInput, db) {
    const query = "SELECT * FROM users WHERE name = '" + userInput + "'";
    return await db.query(query);
}
''',
        "java": '''// Should trigger: sec.sql_injection_concat
import java.sql.*;

public class SqlInjection {
    public void unsafeQuery(String userInput, Connection conn) throws SQLException {
        String query = "SELECT * FROM users WHERE name = '" + userInput + "'";
        Statement stmt = conn.createStatement();
        stmt.executeQuery(query);
    }
}
''',
        "csharp": '''// Should trigger: sec.sql_injection_concat
using System.Data.SqlClient;

public class SqlInjection {
    public void UnsafeQuery(string userInput, SqlConnection conn) {
        string query = "SELECT * FROM users WHERE name = '" + userInput + "'";
        var cmd = new SqlCommand(query, conn);
        cmd.ExecuteReader();
    }
}
'''
    },

    "sec.hardcoded_secret": {
        "python": '''# Should trigger: sec.hardcoded_secret
API_KEY = "sk_live_1234567890abcdef"
PASSWORD = "super_secret_password_123"

def connect():
    return API_KEY
''',
        "typescript": '''// Should trigger: sec.hardcoded_secret
const API_KEY = "sk_live_1234567890abcdef";
const PASSWORD = "super_secret_password_123";

export function getKey() {
    return API_KEY;
}
''',
        "javascript": '''// Should trigger: sec.hardcoded_secret
const API_KEY = "sk_live_1234567890abcdef";
const PASSWORD = "super_secret_password_123";

function getKey() {
    return API_KEY;
}
''',
        "java": '''// Should trigger: sec.hardcoded_secret
public class HardcodedSecret {
    private static final String API_KEY = "sk_live_1234567890abcdef";
    private static final String PASSWORD = "super_secret_password_123";
    
    public String getKey() {
        return API_KEY;
    }
}
''',
        "csharp": '''// Should trigger: sec.hardcoded_secret
public class HardcodedSecret {
    private const string ApiKey = "sk_live_1234567890abcdef";
    private const string Password = "super_secret_password_123";
    
    public string GetKey() {
        return ApiKey;
    }
}
'''
    },

    "errors.swallowed_exception": {
        "python": '''# Should trigger: errors.swallowed_exception
def risky_operation():
    try:
        do_something()
    except Exception:
        pass  # swallowed exception
        
def do_something():
    raise ValueError("error")
''',
        "typescript": '''// Should trigger: errors.swallowed_exception
function riskyOperation() {
    try {
        doSomething();
    } catch (e) {
        // swallowed exception
    }
}

function doSomething() {
    throw new Error("error");
}
''',
        "javascript": '''// Should trigger: errors.swallowed_exception
function riskyOperation() {
    try {
        doSomething();
    } catch (e) {
        // swallowed exception
    }
}

function doSomething() {
    throw new Error("error");
}
''',
        "java": '''// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void riskyOperation() {
        try {
            doSomething();
        } catch (Exception e) {
            // swallowed exception
        }
    }
    
    private void doSomething() throws Exception {
        throw new Exception("error");
    }
}
''',
        "csharp": '''// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void RiskyOperation() {
        try {
            DoSomething();
        } catch (Exception) {
            // swallowed exception
        }
    }
    
    private void DoSomething() {
        throw new Exception("error");
    }
}
'''
    },

    "errors.broad_catch": {
        "python": '''# Should trigger: errors.broad_catch
def handle_error():
    try:
        process_data()
    except Exception as e:  # too broad
        print(f"Error: {e}")
        
def process_data():
    pass
''',
        "typescript": '''// Should trigger: errors.broad_catch
function handleError() {
    try {
        processData();
    } catch (e) {  // too broad - catches everything
        console.log("Error:", e);
    }
}

function processData() {}
''',
        "javascript": '''// Should trigger: errors.broad_catch
function handleError() {
    try {
        processData();
    } catch (e) {  // too broad - catches everything
        console.log("Error:", e);
    }
}

function processData() {}
''',
        "java": '''// Should trigger: errors.broad_catch
public class BroadCatch {
    public void handleError() {
        try {
            processData();
        } catch (Exception e) {  // too broad
            System.out.println("Error: " + e);
        }
    }
    
    private void processData() {}
}
''',
        "csharp": '''// Should trigger: errors.broad_catch
public class BroadCatch {
    public void HandleError() {
        try {
            ProcessData();
        } catch (Exception e) {  // too broad
            Console.WriteLine("Error: " + e);
        }
    }
    
    private void ProcessData() {}
}
'''
    },

    "bug.float_equality": {
        "python": '''# Should trigger: bug.float_equality
def check_value(x):
    if x == 0.1 + 0.2:  # dangerous float equality
        return True
    return False
''',
        "typescript": '''// Should trigger: bug.float_equality
function checkValue(x: number): boolean {
    if (x == 0.1 + 0.2) {  // dangerous float equality
        return true;
    }
    return false;
}
''',
        "javascript": '''// Should trigger: bug.float_equality
function checkValue(x) {
    if (x == 0.1 + 0.2) {  // dangerous float equality
        return true;
    }
    return false;
}
''',
        "java": '''// Should trigger: bug.float_equality
public class FloatEquality {
    public boolean checkValue(double x) {
        if (x == 0.1 + 0.2) {  // dangerous float equality
            return true;
        }
        return false;
    }
}
''',
        "csharp": '''// Should trigger: bug.float_equality
public class FloatEquality {
    public bool CheckValue(double x) {
        if (x == 0.1 + 0.2) {  // dangerous float equality
            return true;
        }
        return false;
    }
}
'''
    },

    "complexity.high_cyclomatic": {
        "python": '''# Should trigger: complexity.high_cyclomatic
def complex_function(a, b, c, d, e, f, g, h, i, j, k):
    if a: return 1
    elif b: return 2
    elif c: return 3
    elif d: return 4
    elif e: return 5
    elif f: return 6
    elif g: return 7
    elif h: return 8
    elif i: return 9
    elif j: return 10
    elif k: return 11
    else: return 0
''',
        "typescript": '''// Should trigger: complexity.high_cyclomatic
function complexFunction(a: boolean, b: boolean, c: boolean, d: boolean, e: boolean, f: boolean, g: boolean, h: boolean, i: boolean, j: boolean, k: boolean): number {
    if (a) return 1;
    else if (b) return 2;
    else if (c) return 3;
    else if (d) return 4;
    else if (e) return 5;
    else if (f) return 6;
    else if (g) return 7;
    else if (h) return 8;
    else if (i) return 9;
    else if (j) return 10;
    else if (k) return 11;
    else return 0;
}
''',
        "javascript": '''// Should trigger: complexity.high_cyclomatic
function complexFunction(a, b, c, d, e, f, g, h, i, j, k) {
    if (a) return 1;
    else if (b) return 2;
    else if (c) return 3;
    else if (d) return 4;
    else if (e) return 5;
    else if (f) return 6;
    else if (g) return 7;
    else if (h) return 8;
    else if (i) return 9;
    else if (j) return 10;
    else if (k) return 11;
    else return 0;
}
''',
        "java": '''// Should trigger: complexity.high_cyclomatic
public class HighCyclomatic {
    public int complexFunction(boolean a, boolean b, boolean c, boolean d, boolean e, boolean f, boolean g, boolean h, boolean i, boolean j, boolean k) {
        if (a) return 1;
        else if (b) return 2;
        else if (c) return 3;
        else if (d) return 4;
        else if (e) return 5;
        else if (f) return 6;
        else if (g) return 7;
        else if (h) return 8;
        else if (i) return 9;
        else if (j) return 10;
        else if (k) return 11;
        else return 0;
    }
}
''',
        "csharp": '''// Should trigger: complexity.high_cyclomatic
public class HighCyclomatic {
    public int ComplexFunction(bool a, bool b, bool c, bool d, bool e, bool f, bool g, bool h, bool i, bool j, bool k) {
        if (a) return 1;
        else if (b) return 2;
        else if (c) return 3;
        else if (d) return 4;
        else if (e) return 5;
        else if (f) return 6;
        else if (g) return 7;
        else if (h) return 8;
        else if (i) return 9;
        else if (j) return 10;
        else if (k) return 11;
        else return 0;
    }
}
'''
    },

    "test.no_assertions": {
        "python": '''# Should trigger: test.no_assertions
import pytest

def test_something():
    result = calculate()
    # No assertion - test doesn't verify anything
    
def calculate():
    return 42
''',
        "typescript": '''// Should trigger: test.no_assertions
describe('Test Suite', () => {
    it('should do something', () => {
        const result = calculate();
        // No assertion - test doesn't verify anything
    });
});

function calculate() {
    return 42;
}
''',
        "javascript": '''// Should trigger: test.no_assertions
describe('Test Suite', () => {
    it('should do something', () => {
        const result = calculate();
        // No assertion - test doesn't verify anything
    });
});

function calculate() {
    return 42;
}
''',
        "java": '''// Should trigger: test.no_assertions
import org.junit.Test;

public class NoAssertionsTest {
    @Test
    public void testSomething() {
        int result = calculate();
        // No assertion - test doesn't verify anything
    }
    
    private int calculate() {
        return 42;
    }
}
''',
        "csharp": '''// Should trigger: test.no_assertions
using NUnit.Framework;

[TestFixture]
public class NoAssertionsTest {
    [Test]
    public void TestSomething() {
        int result = Calculate();
        // No assertion - test doesn't verify anything
    }
    
    private int Calculate() {
        return 42;
    }
}
'''
    },

    "test.flaky_sleep": {
        "python": '''# Should trigger: test.flaky_sleep
import time
import pytest

def test_with_sleep():
    start_process()
    time.sleep(5)  # flaky sleep in test
    assert check_result()
    
def start_process():
    pass
    
def check_result():
    return True
''',
        "typescript": '''// Should trigger: test.flaky_sleep
describe('Flaky Test', () => {
    it('should wait', async () => {
        startProcess();
        await new Promise(r => setTimeout(r, 5000));  // flaky sleep
        expect(checkResult()).toBe(true);
    });
});

function startProcess() {}
function checkResult() { return true; }
''',
        "javascript": '''// Should trigger: test.flaky_sleep
describe('Flaky Test', () => {
    it('should wait', async () => {
        startProcess();
        await new Promise(r => setTimeout(r, 5000));  // flaky sleep
        expect(checkResult()).toBe(true);
    });
});

function startProcess() {}
function checkResult() { return true; }
''',
        "java": '''// Should trigger: test.flaky_sleep
import org.junit.Test;
import static org.junit.Assert.*;

public class FlakySleepTest {
    @Test
    public void testWithSleep() throws InterruptedException {
        startProcess();
        Thread.sleep(5000);  // flaky sleep in test
        assertTrue(checkResult());
    }
    
    private void startProcess() {}
    private boolean checkResult() { return true; }
}
''',
        "csharp": '''// Should trigger: test.flaky_sleep
using NUnit.Framework;
using System.Threading;

[TestFixture]
public class FlakySleepTest {
    [Test]
    public void TestWithSleep() {
        StartProcess();
        Thread.Sleep(5000);  // flaky sleep in test
        Assert.IsTrue(CheckResult());
    }
    
    private void StartProcess() {}
    private bool CheckResult() { return true; }
}
'''
    }
}


def generate_fixtures():
    """Generate all fixture files."""
    fixtures_dir = Path(__file__).parent.parent / "tests" / "fixtures" / "alpha_rule_triggers"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    
    generated = []
    
    for rule_id, lang_fixtures in FIXTURES.items():
        safe_rule_name = rule_id.replace(".", "_")
        
        for lang, code in lang_fixtures.items():
            ext = EXTENSIONS[lang]
            filename = f"{safe_rule_name}{ext}"
            lang_dir = fixtures_dir / lang
            lang_dir.mkdir(exist_ok=True)
            
            filepath = lang_dir / filename
            filepath.write_text(code, encoding='utf-8')
            generated.append((rule_id, lang, str(filepath)))
            print(f"Generated: {filepath}")
    
    # Write manifest
    manifest = {
        "generated_fixtures": generated,
        "rules_covered": list(FIXTURES.keys()),
        "languages": TARGET_LANGS
    }
    
    manifest_path = fixtures_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest: {manifest_path}")
    print(f"Total fixtures: {len(generated)}")
    print(f"Rules covered: {len(FIXTURES)}")


if __name__ == "__main__":
    generate_fixtures()
