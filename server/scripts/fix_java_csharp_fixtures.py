#!/usr/bin/env python3
"""
Fix Java/C# fixtures to match actual rule detection patterns.

This script reads each rule's implementation to extract the patterns it detects,
then generates fixtures that WILL trigger the rule.
"""

import os
import sys

# Add server to path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, server_dir)

from pathlib import Path

FIXTURE_BASE = Path(server_dir) / "tests" / "fixtures" / "alpha_rule_triggers"

# Corrected Java fixtures based on actual rule patterns
JAVA_FIXTURES = {
    # sec.path_traversal - use patterns from rule's SINK_TAILS
    "sec_path_traversal.java": '''// Should trigger: sec.path_traversal
import java.io.*;
import java.nio.file.*;

public class PathTraversal {
    public byte[] readUserFile(String filename) throws IOException {
        // Rule looks for: new File, Paths.get, Files.readAllBytes, etc.
        String userPath = "/app/files/" + filename;
        File file = new File(userPath);  // This is a sink!
        return Files.readAllBytes(Paths.get(userPath));  // Also a sink
    }
}
''',

    # sec.open_redirect - use redirect patterns
    "sec_open_redirect.java": '''// Should trigger: sec.open_redirect
import javax.servlet.http.*;

public class RedirectHandler {
    public void handleRedirect(HttpServletRequest request, HttpServletResponse response) throws Exception {
        String url = request.getParameter("url");
        response.sendRedirect(url);  // Open redirect vulnerability!
    }
}
''',

    # sec.insecure_random - use java.util.Random
    "sec_insecure_random.java": '''// Should trigger: sec.insecure_random
import java.util.Random;

public class InsecureRandom {
    public String generateToken() {
        Random random = new Random();  // Insecure for crypto!
        return String.valueOf(random.nextInt());
    }
}
''',

    # sec.sql_injection_concat - SQL string concat
    "sec_sql_injection_concat.java": '''// Should trigger: sec.sql_injection_concat
import java.sql.*;

public class SqlInjection {
    public void queryUser(Connection conn, String userId) throws SQLException {
        String query = "SELECT * FROM users WHERE id = " + userId;  // SQL injection!
        Statement stmt = conn.createStatement();
        stmt.executeQuery(query);
    }
}
''',

    # sec.hardcoded_secret - look for password/secret patterns
    "sec_hardcoded_secret.java": '''// Should trigger: sec.hardcoded_secret
public class HardcodedSecret {
    private static final String API_KEY = "sk_live_abc123def456";
    private static final String PASSWORD = "admin123";
    private static final String SECRET = "super-secret-key";
    
    public String getCredentials() {
        return API_KEY + PASSWORD;
    }
}
''',

    # security.jwt_without_exp - JWT without expiration
    "security_jwt_without_exp.java": '''// Should trigger: security.jwt_without_exp
import io.jsonwebtoken.Jwts;

public class JwtHandler {
    public String createToken(String subject) {
        // JWT without expiration claim!
        return Jwts.builder()
            .setSubject(subject)
            .signWith(key)
            .compact();
    }
}
''',

    # arch.global_state_usage - global mutable state
    "arch_global_state_usage.java": '''// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int counter = 0;  // Global mutable state!
    public static String config = "default";
    
    public void increment() {
        counter++;
    }
}
''',

    # bug.iteration_modification - modify collection during iteration
    "bug_iteration_modification.java": '''// Should trigger: bug.iteration_modification
import java.util.*;

public class IterationBug {
    public void removeItems(List<String> items) {
        for (String item : items) {
            if (item.isEmpty()) {
                items.remove(item);  // ConcurrentModificationException!
            }
        }
    }
}
''',

    # bug.recursion_no_base_case - infinite recursion
    "bug_recursion_no_base_case.java": '''// Should trigger: bug.recursion_no_base_case
public class InfiniteRecursion {
    public int factorial(int n) {
        // Missing base case - infinite recursion!
        return n * factorial(n - 1);
    }
}
''',

    # deadcode.unused_variable - unused variables
    "deadcode_unused_variable.java": '''// Should trigger: deadcode.unused_variable
public class UnusedVar {
    public void process() {
        int unusedValue = 42;  // Never used!
        String result = "ok";
        System.out.println(result);
    }
}
''',

    # imports.unused - unused imports
    "imports_unused.java": '''// Should trigger: imports.unused
import java.util.List;  // Not used!
import java.util.ArrayList;  // Not used!
import java.io.File;  // Not used!

public class UnusedImports {
    public void doNothing() {
        System.out.println("Hello");
    }
}
''',

    # ident.duplicate_definition - duplicate method
    "ident_duplicate_definition.java": '''// Should trigger: ident.duplicate_definition
public class DuplicateDef {
    public void process() {
        System.out.println("first");
    }
    
    public void process() {  // Duplicate method!
        System.out.println("second");
    }
}
''',

    # style.mixed_indentation - tabs and spaces
    "style_mixed_indentation.java": '''// Should trigger: style.mixed_indentation
public class MixedIndent {
    public void method1() {
        int x = 1;  // spaces
	int y = 2;  // tab
    }
}
''',

    # complexity.high_cyclomatic - many branches
    "complexity_high_cyclomatic.java": '''// Should trigger: complexity.high_cyclomatic
public class HighComplexity {
    public String classify(int a, int b, int c, int d, int e) {
        if (a > 0) {
            if (b > 0) {
                if (c > 0) {
                    if (d > 0) {
                        if (e > 0) {
                            return "all positive";
                        } else if (e < 0) {
                            return "e negative";
                        }
                    } else if (d < 0) {
                        return "d negative";
                    }
                } else if (c < 0) {
                    return "c negative";
                }
            } else if (b < 0) {
                return "b negative";
            }
        } else if (a < 0) {
            return "a negative";
        }
        return "default";
    }
}
''',

    # complexity.long_function - function with many lines
    "complexity_long_function.java": '''// Should trigger: complexity.long_function
public class LongFunction {
    public void veryLongMethod() {
''' + '\n'.join([f'        int var{i} = {i};  // line {i}' for i in range(60)]) + '''
    }
}
''',

    # errors.broad_catch - catch Exception
    "errors_broad_catch.java": '''// Should trigger: errors.broad_catch
public class BroadCatch {
    public void process() {
        try {
            riskyOperation();
        } catch (Exception e) {  // Too broad!
            log(e);
        }
    }
    
    private void riskyOperation() throws Exception {}
    private void log(Exception e) {}
}
''',

    # errors.swallowed_exception - empty catch block
    "errors_swallowed_exception.java": '''// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void process() {
        try {
            riskyOperation();
        } catch (Exception e) {
            // Swallowed! No logging or handling
        }
    }
    
    private void riskyOperation() throws Exception {}
}
''',

    # test.flaky_sleep - sleep in test
    "test_flaky_sleep.java": '''// Should trigger: test.flaky_sleep
import org.junit.Test;

public class FlakyTest {
    @Test
    public void testWithSleep() throws Exception {
        Thread.sleep(1000);  // Flaky!
        assertEquals(1, 1);
    }
}
''',

    # test.no_assertions - test without assertions
    "test_no_assertions.java": '''// Should trigger: test.no_assertions
import org.junit.Test;

public class NoAssertionTest {
    @Test
    public void testWithoutAssert() {
        int x = calculate();
        // No assertion! Test passes for any value
    }
    
    private int calculate() { return 42; }
}
''',

    # concurrency.lock_not_released - lock without try-finally
    "concurrency_lock_not_released.java": '''// Should trigger: concurrency.lock_not_released
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public class LockNotReleased {
    private Lock lock = new ReentrantLock();
    
    public void process() {
        lock.lock();  // Not in try-finally!
        doWork();
        lock.unlock();  // May not execute if exception thrown
    }
    
    private void doWork() {}
}
''',

    # bug.float_equality - direct float comparison
    "bug_float_equality.java": '''// Should trigger: bug.float_equality
public class FloatEquality {
    public boolean checkEqual(double a, double b) {
        return a == b;  // Bad: direct float comparison!
    }
}
''',

    # bug.boolean_bitwise_misuse - & instead of &&
    "bug_boolean_bitwise_misuse.java": '''// Should trigger: bug.boolean_bitwise_misuse
public class BitwiseMisuse {
    public boolean check(boolean a, boolean b) {
        if (a & b) {  // Should be &&
            return true;
        }
        return a | b;  // Should be ||
    }
}
''',

    # bug.incompatible_comparison - type mismatch comparison
    "bug_incompatible_comparison.java": '''// Should trigger: bug.incompatible_comparison
public class IncompatibleCompare {
    public boolean compare(String s, Integer i) {
        return s.equals(i);  // Incompatible types!
    }
}
''',

    # errors.partial_function_implementation - TODO in method
    "errors_partial_function_implementation.java": '''// Should trigger: errors.partial_function_implementation
public class PartialImpl {
    public void notImplemented() {
        // TODO: implement this method
        throw new UnsupportedOperationException("Not implemented");
    }
}
''',

    # naming.project_term_inconsistency - inconsistent naming
    "naming_project_term_inconsistency.java": '''// Should trigger: naming.project_term_inconsistency
public class TermInconsistency {
    private String userId;  // uses "User"
    private String clientId;  // uses "Client" - inconsistent!
    private String customerId;  // uses "Customer" - another term!
}
''',
}

# Corrected C# fixtures based on actual rule patterns
CSHARP_FIXTURES = {
    # sec.path_traversal - use File patterns from rule
    "sec_path_traversal.cs": '''// Should trigger: sec.path_traversal
using System.IO;

public class PathTraversal {
    public string ReadUserFile(string filename) {
        string path = "/app/files/" + filename;
        return File.ReadAllText(path);  // Sink!
    }
}
''',

    # sec.open_redirect
    "sec_open_redirect.cs": '''// Should trigger: sec.open_redirect
using Microsoft.AspNetCore.Mvc;

public class RedirectController : Controller {
    public IActionResult HandleRedirect(string url) {
        return Redirect(url);  // Open redirect!
    }
}
''',

    # sec.insecure_random
    "sec_insecure_random.cs": '''// Should trigger: sec.insecure_random
using System;

public class InsecureRandom {
    public int GenerateToken() {
        Random random = new Random();  // Not crypto-secure!
        return random.Next();
    }
}
''',

    # sec.sql_injection_concat
    "sec_sql_injection_concat.cs": '''// Should trigger: sec.sql_injection_concat
using System.Data.SqlClient;

public class SqlInjection {
    public void QueryUser(string userId) {
        string query = "SELECT * FROM users WHERE id = " + userId;
        using var cmd = new SqlCommand(query);
    }
}
''',

    # sec.hardcoded_secret
    "sec_hardcoded_secret.cs": '''// Should trigger: sec.hardcoded_secret
public class HardcodedSecret {
    private const string ApiKey = "sk_live_abc123def456";
    private const string Password = "admin123";
}
''',

    # security.jwt_without_exp
    "security_jwt_without_exp.cs": '''// Should trigger: security.jwt_without_exp
using System.IdentityModel.Tokens.Jwt;

public class JwtHandler {
    public string CreateToken(string subject) {
        var token = new JwtSecurityToken(
            issuer: "test",
            audience: "test"
            // No expiration!
        );
        return new JwtSecurityTokenHandler().WriteToken(token);
    }
}
''',

    # arch.global_state_usage
    "arch_global_state_usage.cs": '''// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int Counter = 0;  // Global mutable state!
    public static string Config = "default";
    
    public void Increment() {
        Counter++;
    }
}
''',

    # bug.iteration_modification
    "bug_iteration_modification.cs": '''// Should trigger: bug.iteration_modification
using System.Collections.Generic;

public class IterationBug {
    public void RemoveItems(List<string> items) {
        foreach (var item in items) {
            if (string.IsNullOrEmpty(item)) {
                items.Remove(item);  // InvalidOperationException!
            }
        }
    }
}
''',

    # bug.recursion_no_base_case
    "bug_recursion_no_base_case.cs": '''// Should trigger: bug.recursion_no_base_case
public class InfiniteRecursion {
    public int Factorial(int n) {
        // Missing base case!
        return n * Factorial(n - 1);
    }
}
''',

    # deadcode.unused_variable
    "deadcode_unused_variable.cs": '''// Should trigger: deadcode.unused_variable
public class UnusedVar {
    public void Process() {
        int unusedValue = 42;  // Never used!
        string result = "ok";
        Console.WriteLine(result);
    }
}
''',

    # imports.unused
    "imports_unused.cs": '''// Should trigger: imports.unused
using System.Collections.Generic;  // Not used!
using System.IO;  // Not used!
using System.Text;  // Not used!

public class UnusedUsings {
    public void DoNothing() {
        Console.WriteLine("Hello");
    }
}
''',

    # ident.duplicate_definition
    "ident_duplicate_definition.cs": '''// Should trigger: ident.duplicate_definition
public class DuplicateDef {
    public void Process() {
        Console.WriteLine("first");
    }
    
    public void Process() {  // Duplicate!
        Console.WriteLine("second");
    }
}
''',

    # style.mixed_indentation
    "style_mixed_indentation.cs": '''// Should trigger: style.mixed_indentation
public class MixedIndent {
    public void Method1() {
        int x = 1;  // spaces
	int y = 2;  // tab
    }
}
''',

    # complexity.high_cyclomatic
    "complexity_high_cyclomatic.cs": '''// Should trigger: complexity.high_cyclomatic
public class HighComplexity {
    public string Classify(int a, int b, int c, int d, int e) {
        if (a > 0) {
            if (b > 0) {
                if (c > 0) {
                    if (d > 0) {
                        if (e > 0) {
                            return "all positive";
                        } else if (e < 0) {
                            return "e negative";
                        }
                    } else if (d < 0) {
                        return "d negative";
                    }
                } else if (c < 0) {
                    return "c negative";
                }
            } else if (b < 0) {
                return "b negative";
            }
        } else if (a < 0) {
            return "a negative";
        }
        return "default";
    }
}
''',

    # complexity.long_function
    "complexity_long_function.cs": '''// Should trigger: complexity.long_function
public class LongFunction {
    public void VeryLongMethod() {
''' + '\n'.join([f'        int var{i} = {i};  // line {i}' for i in range(60)]) + '''
    }
}
''',

    # errors.broad_catch
    "errors_broad_catch.cs": '''// Should trigger: errors.broad_catch
public class BroadCatch {
    public void Process() {
        try {
            RiskyOperation();
        } catch (Exception e) {  // Too broad!
            Log(e);
        }
    }
    
    private void RiskyOperation() {}
    private void Log(Exception e) {}
}
''',

    # errors.swallowed_exception
    "errors_swallowed_exception.cs": '''// Should trigger: errors.swallowed_exception
public class SwallowedException {
    public void Process() {
        try {
            RiskyOperation();
        } catch {
            // Swallowed! No handling
        }
    }
    
    private void RiskyOperation() {}
}
''',

    # test.flaky_sleep
    "test_flaky_sleep.cs": '''// Should trigger: test.flaky_sleep
using NUnit.Framework;
using System.Threading;

[TestFixture]
public class FlakyTest {
    [Test]
    public void TestWithSleep() {
        Thread.Sleep(1000);  // Flaky!
        Assert.Pass();
    }
}
''',

    # test.no_assertions
    "test_no_assertions.cs": '''// Should trigger: test.no_assertions
using NUnit.Framework;

[TestFixture]
public class NoAssertionTest {
    [Test]
    public void TestWithoutAssert() {
        int x = Calculate();
        // No assertion!
    }
    
    private int Calculate() => 42;
}
''',

    # concurrency.lock_not_released
    "concurrency_lock_not_released.cs": '''// Should trigger: concurrency.lock_not_released
using System.Threading;

public class LockNotReleased {
    private readonly object _lock = new object();
    
    public void Process() {
        Monitor.Enter(_lock);  // Not in try-finally!
        DoWork();
        Monitor.Exit(_lock);  // May not execute
    }
    
    private void DoWork() {}
}
''',

    # bug.float_equality
    "bug_float_equality.cs": '''// Should trigger: bug.float_equality
public class FloatEquality {
    public bool CheckEqual(double a, double b) {
        return a == b;  // Bad: direct float comparison!
    }
}
''',

    # bug.boolean_bitwise_misuse
    "bug_boolean_bitwise_misuse.cs": '''// Should trigger: bug.boolean_bitwise_misuse
public class BitwiseMisuse {
    public bool Check(bool a, bool b) {
        if (a & b) {  // Should be &&
            return true;
        }
        return a | b;  // Should be ||
    }
}
''',

    # bug.incompatible_comparison
    "bug_incompatible_comparison.cs": '''// Should trigger: bug.incompatible_comparison
public class IncompatibleCompare {
    public bool Compare(string s, int i) {
        return s.Equals(i);  // Incompatible types!
    }
}
''',

    # errors.partial_function_implementation
    "errors_partial_function_implementation.cs": '''// Should trigger: errors.partial_function_implementation
public class PartialImpl {
    public void NotImplemented() {
        // TODO: implement this method
        throw new NotImplementedException();
    }
}
''',

    # naming.project_term_inconsistency
    "naming_project_term_inconsistency.cs": '''// Should trigger: naming.project_term_inconsistency
public class TermInconsistency {
    private string userId;  // uses "User"
    private string clientId;  // uses "Client" - inconsistent!
    private string customerId;  // uses "Customer" - another term!
}
''',
}


def main():
    """Write corrected fixtures."""
    java_dir = FIXTURE_BASE / "java"
    csharp_dir = FIXTURE_BASE / "csharp"
    
    java_dir.mkdir(parents=True, exist_ok=True)
    csharp_dir.mkdir(parents=True, exist_ok=True)
    
    print("Writing corrected Java fixtures...")
    for filename, content in JAVA_FIXTURES.items():
        filepath = java_dir / filename
        filepath.write_text(content, encoding='utf-8')
        print(f"  - {filepath.name}")
    
    print(f"\nWriting corrected C# fixtures...")
    for filename, content in CSHARP_FIXTURES.items():
        filepath = csharp_dir / filename
        filepath.write_text(content, encoding='utf-8')
        print(f"  - {filepath.name}")
    
    print(f"\nDone! Wrote {len(JAVA_FIXTURES)} Java fixtures and {len(CSHARP_FIXTURES)} C# fixtures.")


if __name__ == "__main__":
    main()
