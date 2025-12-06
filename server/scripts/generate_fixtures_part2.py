#!/usr/bin/env python3
"""
Generate remaining test fixtures for alpha rules (part 2).
"""

import json
from pathlib import Path

TARGET_LANGS = ["python", "typescript", "javascript", "java", "csharp"]
EXTENSIONS = {"python": ".py", "typescript": ".ts", "javascript": ".js", "java": ".java", "csharp": ".cs"}

FIXTURES = {
    "arch.global_state_usage": {
        "python": '''# Should trigger: arch.global_state_usage
GLOBAL_COUNTER = 0

def increment():
    global GLOBAL_COUNTER
    GLOBAL_COUNTER += 1
    return GLOBAL_COUNTER
''',
        "typescript": '''// Should trigger: arch.global_state_usage
let globalCounter = 0;

export function increment(): number {
    globalCounter += 1;
    return globalCounter;
}
''',
        "javascript": '''// Should trigger: arch.global_state_usage
let globalCounter = 0;

function increment() {
    globalCounter += 1;
    return globalCounter;
}
''',
        "java": '''// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int globalCounter = 0;
    
    public int increment() {
        globalCounter += 1;
        return globalCounter;
    }
}
''',
        "csharp": '''// Should trigger: arch.global_state_usage
public class GlobalState {
    public static int GlobalCounter = 0;
    
    public int Increment() {
        GlobalCounter += 1;
        return GlobalCounter;
    }
}
'''
    },

    "sec.path_traversal": {
        "python": '''# Should trigger: sec.path_traversal
def read_user_file(filename):
    path = "/app/files/" + filename
    with open(path, 'r') as f:
        return f.read()
''',
        "typescript": '''// Should trigger: sec.path_traversal
import fs from 'fs';

function readUserFile(filename: string): string {
    const path = "/app/files/" + filename;
    return fs.readFileSync(path, 'utf-8');
}
''',
        "javascript": '''// Should trigger: sec.path_traversal
const fs = require('fs');

function readUserFile(filename) {
    const path = "/app/files/" + filename;
    return fs.readFileSync(path, 'utf-8');
}
''',
        "java": '''// Should trigger: sec.path_traversal
import java.io.*;
import java.nio.file.*;

public class PathTraversal {
    public String readUserFile(String filename) throws IOException {
        String path = "/app/files/" + filename;
        return Files.readString(Path.of(path));
    }
}
''',
        "csharp": '''// Should trigger: sec.path_traversal
using System.IO;

public class PathTraversal {
    public string ReadUserFile(string filename) {
        string path = "/app/files/" + filename;
        return File.ReadAllText(path);
    }
}
'''
    },

    "sec.open_redirect": {
        "python": '''# Should trigger: sec.open_redirect
from flask import redirect, request

def handle_redirect():
    url = request.args.get('url')
    return redirect(url)
''',
        "typescript": '''// Should trigger: sec.open_redirect
import { Request, Response } from 'express';

function handleRedirect(req: Request, res: Response) {
    const url = req.query.url as string;
    res.redirect(url);
}
''',
        "javascript": '''// Should trigger: sec.open_redirect
function handleRedirect(req, res) {
    const url = req.query.url;
    res.redirect(url);
}
''',
        "java": '''// Should trigger: sec.open_redirect
import javax.servlet.http.*;

public class OpenRedirect extends HttpServlet {
    protected void doGet(HttpServletRequest req, HttpServletResponse res) throws Exception {
        String url = req.getParameter("url");
        res.sendRedirect(url);
    }
}
''',
        "csharp": '''// Should trigger: sec.open_redirect
using Microsoft.AspNetCore.Mvc;

public class RedirectController : Controller {
    public IActionResult HandleRedirect(string url) {
        return Redirect(url);
    }
}
'''
    },

    "sec.insecure_random": {
        "python": '''# Should trigger: sec.insecure_random
import random

def generate_token():
    return str(random.randint(100000, 999999))
''',
        "javascript": '''// Should trigger: sec.insecure_random
function generateToken() {
    return Math.floor(Math.random() * 1000000).toString();
}
''',
        "java": '''// Should trigger: sec.insecure_random
import java.util.Random;

public class InsecureRandom {
    public String generateToken() {
        Random random = new Random();
        return String.valueOf(random.nextInt(1000000));
    }
}
''',
        "csharp": '''// Should trigger: sec.insecure_random
using System;

public class InsecureRandom {
    public string GenerateToken() {
        Random random = new Random();
        return random.Next(1000000).ToString();
    }
}
'''
    },

    "security.jwt_without_exp": {
        "python": '''# Should trigger: security.jwt_without_exp
import jwt

def create_token(user_id):
    payload = {"user_id": user_id}  # missing exp claim
    return jwt.encode(payload, "secret", algorithm="HS256")
''',
        "typescript": '''// Should trigger: security.jwt_without_exp
import jwt from 'jsonwebtoken';

function createToken(userId: string): string {
    const payload = { userId };  // missing exp claim
    return jwt.sign(payload, "secret");
}
''',
        "javascript": '''// Should trigger: security.jwt_without_exp
const jwt = require('jsonwebtoken');

function createToken(userId) {
    const payload = { userId };  // missing exp claim
    return jwt.sign(payload, "secret");
}
''',
        "java": '''// Should trigger: security.jwt_without_exp
import io.jsonwebtoken.Jwts;
import io.jsonwebtoken.SignatureAlgorithm;

public class JwtWithoutExp {
    public String createToken(String userId) {
        return Jwts.builder()
            .claim("userId", userId)  // missing exp claim
            .signWith(SignatureAlgorithm.HS256, "secret")
            .compact();
    }
}
''',
        "csharp": '''// Should trigger: security.jwt_without_exp
using System.IdentityModel.Tokens.Jwt;
using Microsoft.IdentityModel.Tokens;

public class JwtWithoutExp {
    public string CreateToken(string userId) {
        var handler = new JwtSecurityTokenHandler();
        var token = new JwtSecurityToken(
            claims: new[] { new System.Security.Claims.Claim("userId", userId) }
            // missing expires parameter
        );
        return handler.WriteToken(token);
    }
}
'''
    },

    "bug.incompatible_comparison": {
        "python": '''# Should trigger: bug.incompatible_comparison
def compare_values(x):
    if x == "5":  # comparing int with string
        return True
    return False

result = compare_values(5)
''',
        "typescript": '''// Should trigger: bug.incompatible_comparison
function compareValues(x: number): boolean {
    if ((x as any) == "5") {  // comparing number with string
        return true;
    }
    return false;
}
''',
        "javascript": '''// Should trigger: bug.incompatible_comparison
function compareValues(x) {
    if (x == "5") {  // comparing number with string (loose equality)
        return true;
    }
    return false;
}
''',
        "java": '''// Should trigger: bug.incompatible_comparison
public class IncompatibleComparison {
    public boolean compareValues(Integer x) {
        if (x.equals("5")) {  // comparing Integer with String
            return true;
        }
        return false;
    }
}
''',
        "csharp": '''// Should trigger: bug.incompatible_comparison
public class IncompatibleComparison {
    public bool CompareValues(int x) {
        if (x.Equals("5")) {  // comparing int with string
            return true;
        }
        return false;
    }
}
'''
    },

    "bug.iteration_modification": {
        "python": '''# Should trigger: bug.iteration_modification
def remove_evens(numbers):
    for num in numbers:
        if num % 2 == 0:
            numbers.remove(num)  # modifying list during iteration
    return numbers
''',
        "typescript": '''// Should trigger: bug.iteration_modification
function removeEvens(numbers: number[]): number[] {
    for (const num of numbers) {
        if (num % 2 === 0) {
            const idx = numbers.indexOf(num);
            numbers.splice(idx, 1);  // modifying array during iteration
        }
    }
    return numbers;
}
''',
        "javascript": '''// Should trigger: bug.iteration_modification
function removeEvens(numbers) {
    for (const num of numbers) {
        if (num % 2 === 0) {
            const idx = numbers.indexOf(num);
            numbers.splice(idx, 1);  // modifying array during iteration
        }
    }
    return numbers;
}
''',
        "java": '''// Should trigger: bug.iteration_modification
import java.util.*;

public class IterationModification {
    public List<Integer> removeEvens(List<Integer> numbers) {
        for (Integer num : numbers) {
            if (num % 2 == 0) {
                numbers.remove(num);  // modifying list during iteration
            }
        }
        return numbers;
    }
}
''',
        "csharp": '''// Should trigger: bug.iteration_modification
using System.Collections.Generic;

public class IterationModification {
    public List<int> RemoveEvens(List<int> numbers) {
        foreach (var num in numbers) {
            if (num % 2 == 0) {
                numbers.Remove(num);  // modifying list during iteration
            }
        }
        return numbers;
    }
}
'''
    },

    "bug.boolean_bitwise_misuse": {
        "python": '''# Should trigger: bug.boolean_bitwise_misuse
def check_conditions(a, b):
    if a & b:  # using bitwise & instead of logical and
        return True
    return False
''',
        "typescript": '''// Should trigger: bug.boolean_bitwise_misuse
function checkConditions(a: boolean, b: boolean): boolean {
    if (a & b) {  // using bitwise & instead of logical &&
        return true;
    }
    return false;
}
''',
        "javascript": '''// Should trigger: bug.boolean_bitwise_misuse
function checkConditions(a, b) {
    if (a & b) {  // using bitwise & instead of logical &&
        return true;
    }
    return false;
}
''',
        "java": '''// Should trigger: bug.boolean_bitwise_misuse
public class BooleanBitwiseMisuse {
    public boolean checkConditions(boolean a, boolean b) {
        if (a & b) {  // using bitwise & instead of logical &&
            return true;
        }
        return false;
    }
}
''',
        "csharp": '''// Should trigger: bug.boolean_bitwise_misuse
public class BooleanBitwiseMisuse {
    public bool CheckConditions(bool a, bool b) {
        if (a & b) {  // using bitwise & instead of logical &&
            return true;
        }
        return false;
    }
}
'''
    },

    "bug.recursion_no_base_case": {
        "python": '''# Should trigger: bug.recursion_no_base_case
def infinite_recursion(n):
    return infinite_recursion(n - 1)  # no base case
''',
        "typescript": '''// Should trigger: bug.recursion_no_base_case
function infiniteRecursion(n: number): number {
    return infiniteRecursion(n - 1);  // no base case
}
''',
        "javascript": '''// Should trigger: bug.recursion_no_base_case
function infiniteRecursion(n) {
    return infiniteRecursion(n - 1);  // no base case
}
''',
        "java": '''// Should trigger: bug.recursion_no_base_case
public class RecursionNoBaseCase {
    public int infiniteRecursion(int n) {
        return infiniteRecursion(n - 1);  // no base case
    }
}
''',
        "csharp": '''// Should trigger: bug.recursion_no_base_case
public class RecursionNoBaseCase {
    public int InfiniteRecursion(int n) {
        return InfiniteRecursion(n - 1);  // no base case
    }
}
'''
    },

    "errors.partial_function_implementation": {
        "python": '''# Should trigger: errors.partial_function_implementation
def process_value(value):
    if value > 0:
        return "positive"
    elif value < 0:
        return "negative"
    # missing: what if value == 0?
''',
        "typescript": '''// Should trigger: errors.partial_function_implementation
function processValue(value: number): string {
    if (value > 0) {
        return "positive";
    } else if (value < 0) {
        return "negative";
    }
    // missing: what if value === 0?
}
''',
        "javascript": '''// Should trigger: errors.partial_function_implementation
function processValue(value) {
    if (value > 0) {
        return "positive";
    } else if (value < 0) {
        return "negative";
    }
    // missing: what if value === 0?
}
''',
        "java": '''// Should trigger: errors.partial_function_implementation
public class PartialFunction {
    public String processValue(int value) {
        if (value > 0) {
            return "positive";
        } else if (value < 0) {
            return "negative";
        }
        // missing: what if value == 0?
        return null;
    }
}
''',
        "csharp": '''// Should trigger: errors.partial_function_implementation
public class PartialFunction {
    public string ProcessValue(int value) {
        if (value > 0) {
            return "positive";
        } else if (value < 0) {
            return "negative";
        }
        // missing: what if value == 0?
        return null;
    }
}
'''
    }
}


def generate_fixtures():
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
    
    print(f"\nTotal fixtures (part 2): {len(generated)}")
    print(f"Rules covered: {len(FIXTURES)}")


if __name__ == "__main__":
    generate_fixtures()
