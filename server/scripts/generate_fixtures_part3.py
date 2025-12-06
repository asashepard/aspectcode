#!/usr/bin/env python3
"""
Generate remaining test fixtures for alpha rules (part 3).
Covers: concurrency, complexity, style, naming, ident rules
"""

import json
from pathlib import Path

TARGET_LANGS = ["python", "typescript", "javascript", "java", "csharp"]
EXTENSIONS = {"python": ".py", "typescript": ".ts", "javascript": ".js", "java": ".java", "csharp": ".cs"}

FIXTURES = {
    "concurrency.lock_not_released": {
        "python": '''# Should trigger: concurrency.lock_not_released
import threading

lock = threading.Lock()

def critical_section():
    lock.acquire()
    do_work()
    # missing lock.release()
    
def do_work():
    pass
''',
        "java": '''// Should trigger: concurrency.lock_not_released
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantLock;

public class LockNotReleased {
    private Lock lock = new ReentrantLock();
    
    public void criticalSection() {
        lock.lock();
        doWork();
        // missing lock.unlock()
    }
    
    private void doWork() {}
}
''',
        "csharp": '''// Should trigger: concurrency.lock_not_released
using System.Threading;

public class LockNotReleased {
    private object lockObj = new object();
    private Mutex mutex = new Mutex();
    
    public void CriticalSection() {
        mutex.WaitOne();
        DoWork();
        // missing mutex.ReleaseMutex()
    }
    
    private void DoWork() {}
}
'''
    },

    "concurrency.blocking_in_async": {
        "python": '''# Should trigger: concurrency.blocking_in_async
import asyncio
import time

async def fetch_data():
    time.sleep(5)  # blocking call in async function
    return "data"
''',
        "typescript": '''// Should trigger: concurrency.blocking_in_async
import fs from 'fs';

async function fetchData(): Promise<string> {
    const data = fs.readFileSync('file.txt', 'utf-8');  // blocking call in async
    return data;
}
''',
        "javascript": '''// Should trigger: concurrency.blocking_in_async
const fs = require('fs');

async function fetchData() {
    const data = fs.readFileSync('file.txt', 'utf-8');  // blocking call in async
    return data;
}
'''
    },

    "complexity.long_function": {
        "python": '''# Should trigger: complexity.long_function
def very_long_function():
    line1 = 1
    line2 = 2
    line3 = 3
    line4 = 4
    line5 = 5
    line6 = 6
    line7 = 7
    line8 = 8
    line9 = 9
    line10 = 10
    line11 = 11
    line12 = 12
    line13 = 13
    line14 = 14
    line15 = 15
    line16 = 16
    line17 = 17
    line18 = 18
    line19 = 19
    line20 = 20
    line21 = 21
    line22 = 22
    line23 = 23
    line24 = 24
    line25 = 25
    line26 = 26
    line27 = 27
    line28 = 28
    line29 = 29
    line30 = 30
    line31 = 31
    line32 = 32
    line33 = 33
    line34 = 34
    line35 = 35
    line36 = 36
    line37 = 37
    line38 = 38
    line39 = 39
    line40 = 40
    line41 = 41
    line42 = 42
    line43 = 43
    line44 = 44
    line45 = 45
    line46 = 46
    line47 = 47
    line48 = 48
    line49 = 49
    line50 = 50
    line51 = 51
    return line51
''',
        "typescript": '''// Should trigger: complexity.long_function
function veryLongFunction(): number {
    const line1 = 1; const line2 = 2; const line3 = 3; const line4 = 4; const line5 = 5;
    const line6 = 6; const line7 = 7; const line8 = 8; const line9 = 9; const line10 = 10;
    const line11 = 11; const line12 = 12; const line13 = 13; const line14 = 14; const line15 = 15;
    const line16 = 16; const line17 = 17; const line18 = 18; const line19 = 19; const line20 = 20;
    const line21 = 21; const line22 = 22; const line23 = 23; const line24 = 24; const line25 = 25;
    const line26 = 26; const line27 = 27; const line28 = 28; const line29 = 29; const line30 = 30;
    const line31 = 31; const line32 = 32; const line33 = 33; const line34 = 34; const line35 = 35;
    const line36 = 36; const line37 = 37; const line38 = 38; const line39 = 39; const line40 = 40;
    const line41 = 41; const line42 = 42; const line43 = 43; const line44 = 44; const line45 = 45;
    const line46 = 46; const line47 = 47; const line48 = 48; const line49 = 49; const line50 = 50;
    return line50;
}
''',
        "javascript": '''// Should trigger: complexity.long_function
function veryLongFunction() {
    const line1 = 1; const line2 = 2; const line3 = 3; const line4 = 4; const line5 = 5;
    const line6 = 6; const line7 = 7; const line8 = 8; const line9 = 9; const line10 = 10;
    const line11 = 11; const line12 = 12; const line13 = 13; const line14 = 14; const line15 = 15;
    const line16 = 16; const line17 = 17; const line18 = 18; const line19 = 19; const line20 = 20;
    const line21 = 21; const line22 = 22; const line23 = 23; const line24 = 24; const line25 = 25;
    const line26 = 26; const line27 = 27; const line28 = 28; const line29 = 29; const line30 = 30;
    const line31 = 31; const line32 = 32; const line33 = 33; const line34 = 34; const line35 = 35;
    const line36 = 36; const line37 = 37; const line38 = 38; const line39 = 39; const line40 = 40;
    const line41 = 41; const line42 = 42; const line43 = 43; const line44 = 44; const line45 = 45;
    const line46 = 46; const line47 = 47; const line48 = 48; const line49 = 49; const line50 = 50;
    return line50;
}
''',
        "java": '''// Should trigger: complexity.long_function
public class LongFunction {
    public int veryLongFunction() {
        int line1 = 1; int line2 = 2; int line3 = 3; int line4 = 4; int line5 = 5;
        int line6 = 6; int line7 = 7; int line8 = 8; int line9 = 9; int line10 = 10;
        int line11 = 11; int line12 = 12; int line13 = 13; int line14 = 14; int line15 = 15;
        int line16 = 16; int line17 = 17; int line18 = 18; int line19 = 19; int line20 = 20;
        int line21 = 21; int line22 = 22; int line23 = 23; int line24 = 24; int line25 = 25;
        int line26 = 26; int line27 = 27; int line28 = 28; int line29 = 29; int line30 = 30;
        int line31 = 31; int line32 = 32; int line33 = 33; int line34 = 34; int line35 = 35;
        int line36 = 36; int line37 = 37; int line38 = 38; int line39 = 39; int line40 = 40;
        int line41 = 41; int line42 = 42; int line43 = 43; int line44 = 44; int line45 = 45;
        int line46 = 46; int line47 = 47; int line48 = 48; int line49 = 49; int line50 = 50;
        return line50;
    }
}
''',
        "csharp": '''// Should trigger: complexity.long_function
public class LongFunction {
    public int VeryLongFunction() {
        int line1 = 1; int line2 = 2; int line3 = 3; int line4 = 4; int line5 = 5;
        int line6 = 6; int line7 = 7; int line8 = 8; int line9 = 9; int line10 = 10;
        int line11 = 11; int line12 = 12; int line13 = 13; int line14 = 14; int line15 = 15;
        int line16 = 16; int line17 = 17; int line18 = 18; int line19 = 19; int line20 = 20;
        int line21 = 21; int line22 = 22; int line23 = 23; int line24 = 24; int line25 = 25;
        int line26 = 26; int line27 = 27; int line28 = 28; int line29 = 29; int line30 = 30;
        int line31 = 31; int line32 = 32; int line33 = 33; int line34 = 34; int line35 = 35;
        int line36 = 36; int line37 = 37; int line38 = 38; int line39 = 39; int line40 = 40;
        int line41 = 41; int line42 = 42; int line43 = 43; int line44 = 44; int line45 = 45;
        int line46 = 46; int line47 = 47; int line48 = 48; int line49 = 49; int line50 = 50;
        return line50;
    }
}
'''
    },

    "style.mixed_indentation": {
        "python": '''# Should trigger: style.mixed_indentation
def function_with_mixed_indent():
    if True:
        print("spaces")
	print("tabs")  # tab character here
''',
        "typescript": '''// Should trigger: style.mixed_indentation
function mixedIndent() {
    if (true) {
        console.log("spaces");
	console.log("tabs");  // tab character here
    }
}
''',
        "javascript": '''// Should trigger: style.mixed_indentation
function mixedIndent() {
    if (true) {
        console.log("spaces");
	console.log("tabs");  // tab character here
    }
}
''',
        "java": '''// Should trigger: style.mixed_indentation
public class MixedIndentation {
    public void mixedIndent() {
        if (true) {
            System.out.println("spaces");
	    System.out.println("tabs");  // tab character here
        }
    }
}
''',
        "csharp": '''// Should trigger: style.mixed_indentation
public class MixedIndentation {
    public void MixedIndent() {
        if (true) {
            Console.WriteLine("spaces");
	    Console.WriteLine("tabs");  // tab character here
        }
    }
}
'''
    },

    "naming.project_term_inconsistency": {
        "python": '''# Should trigger: naming.project_term_inconsistency
class UserManager:
    def get_usr(self):  # inconsistent: usr vs user
        pass
    
    def create_user(self):
        pass
    
    def delete_usr(self):  # inconsistent: usr vs user
        pass
''',
        "typescript": '''// Should trigger: naming.project_term_inconsistency
class UserManager {
    getUsr(): void {}  // inconsistent: usr vs user
    
    createUser(): void {}
    
    deleteUsr(): void {}  // inconsistent: usr vs user
}
''',
        "javascript": '''// Should trigger: naming.project_term_inconsistency
class UserManager {
    getUsr() {}  // inconsistent: usr vs user
    
    createUser() {}
    
    deleteUsr() {}  // inconsistent: usr vs user
}
''',
        "java": '''// Should trigger: naming.project_term_inconsistency
public class UserManager {
    public void getUsr() {}  // inconsistent: usr vs user
    
    public void createUser() {}
    
    public void deleteUsr() {}  // inconsistent: usr vs user
}
''',
        "csharp": '''// Should trigger: naming.project_term_inconsistency
public class UserManager {
    public void GetUsr() {}  // inconsistent: usr vs user
    
    public void CreateUser() {}
    
    public void DeleteUsr() {}  // inconsistent: usr vs user
}
'''
    },

    "ident.shadowing": {
        "python": '''# Should trigger: ident.shadowing
x = 10

def outer():
    x = 20  # shadows global x
    
    def inner():
        x = 30  # shadows outer x
        return x
    
    return inner()
'''
    },

    "ident.duplicate_definition": {
        "python": '''# Should trigger: ident.duplicate_definition
def process_data():
    pass

def process_data():  # duplicate definition
    pass
''',
        "typescript": '''// Should trigger: ident.duplicate_definition
function processData(): void {}

function processData(): void {}  // duplicate definition
''',
        "javascript": '''// Should trigger: ident.duplicate_definition
function processData() {}

function processData() {}  // duplicate definition
''',
        "java": '''// Should trigger: ident.duplicate_definition
public class DuplicateDefinition {
    public void processData() {}
    
    public void processData() {}  // duplicate definition (overload without params diff)
}
''',
        "csharp": '''// Should trigger: ident.duplicate_definition
public class DuplicateDefinition {
    public void ProcessData() {}
    
    public void ProcessData() {}  // duplicate definition (overload without params diff)
}
'''
    },

    "imports.cycle": {
        "python": '''# Should trigger: imports.cycle (when paired with module_b.py)
# This is module_a.py
from module_b import func_b

def func_a():
    return func_b()
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
    
    # For imports.cycle, create the paired module
    module_b_content = '''# Module B for cycle testing
from module_a import func_a

def func_b():
    return func_a()
'''
    cycle_dir = fixtures_dir / "python"
    (cycle_dir / "module_b.py").write_text(module_b_content)
    # Rename imports_cycle to module_a
    if (cycle_dir / "imports_cycle.py").exists():
        (cycle_dir / "imports_cycle.py").rename(cycle_dir / "module_a.py")
        print(f"Renamed: imports_cycle.py -> module_a.py (for cycle testing)")
    
    print(f"\nTotal fixtures (part 3): {len(generated)}")
    print(f"Rules covered: {len(FIXTURES)}")


if __name__ == "__main__":
    generate_fixtures()
