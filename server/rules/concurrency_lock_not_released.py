"""
Rule to detect lock acquisitions that are not reliably released on all control-flow paths.

This rule analyzes code to identify lock acquisition patterns that may not be properly
released, potentially causing deadlocks or resource leaks. It recommends using RAII
patterns, try/finally blocks, or context managers.
"""

from typing import Iterator, Dict, Any, Set, List, Optional
import re

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
    from engine.scopes import build_scopes
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit
    from engine.scopes import build_scopes


class ConcurrencyLockNotReleasedRule(Rule):
    """Rule to detect lock acquisitions that may not be reliably released."""
    
    meta = RuleMeta(
        id="concurrency.lock_not_released",
        description="Detects lock acquisitions that are not reliably released on all control-flow paths; recommend using RAII or try/finally patterns.",
        category="concurrency",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        langs=["java", "csharp", "cpp", "python"],
    )

    requires = Requires(syntax=True, scopes=True, raw_text=True)

    # Language-specific acquisition/release recognition (heuristic)
    ACQUIRE_CALLS = {
        "java": {"ReentrantLock.lock", "lock.lock", "readLock.lock", "writeLock.lock", "Semaphore.acquire"},
        "csharp": {"Monitor.Enter", "m.Enter", "semaphore.Wait", "semaphore.WaitAsync", "mutex.WaitOne"},
        "cpp": {"mutex.lock", "mtx.lock", "pthread_mutex_lock"},
        "python": {"lock.acquire", "RLock.acquire", "semaphore.acquire"},
    }
    
    RELEASE_CALLS = {
        "java": {"ReentrantLock.unlock", "lock.unlock", "readLock.unlock", "writeLock.unlock", "Semaphore.release"},
        "csharp": {"Monitor.Exit", "m.Exit", "semaphore.Release", "mutex.ReleaseMutex"},
        "cpp": {"mutex.unlock", "mtx.unlock", "pthread_mutex_unlock"},
        "python": {"lock.release", "RLock.release", "semaphore.release"},
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and analyze lock acquisition/release patterns."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        if not ctx.tree:
            return

        lang = ctx.adapter.language_id
        
        # Build scopes if not provided
        scopes = getattr(ctx, 'scopes', None)
        if not scopes:
            scopes = build_scopes(ctx.adapter, ctx.tree, ctx.text)
        
        # Track if we found issues through scope analysis
        found_issues = False
        
        # Analyze each scope for lock patterns
        for scope in self._walk_scopes(scopes):
            for finding in self._check_scope(ctx, scope, lang):
                found_issues = True
                yield finding
        
        # If scope analysis didn't find anything, fall back to text-based detection
        # for simpler patterns like early return after acquire without release
        if not found_issues:
            yield from self._fallback_text_analysis(ctx, lang)

    def _walk_scopes(self, scopes):
        """Walk through all scopes in the scope graph."""
        if hasattr(scopes, 'walk'):
            return scopes.walk()
        elif hasattr(scopes, 'scopes'):
            return scopes.scopes
        elif hasattr(scopes, '_scopes'):
            # ScopeGraph stores scopes in _scopes dict
            return scopes._scopes.values()
        else:
            # Fallback: treat as single scope
            return [scopes] if scopes else []

    def _check_scope(self, ctx: RuleContext, scope, lang: str) -> Iterator[Finding]:
        """
        Lightweight definite-release analysis:
        - Track (var, acquisition_node) when we see an acquire call.
        - Remove when we see a matching release or a proven RAII/structured-guard.
        - If execution can exit while the lock is held, report at acquisition.
        """
        held = {}  # name -> acquisition node
        blocks = self._get_blocks(scope)
        
        for block in blocks:
            statements = self._get_statements(block)
            for stmt in statements:
                # Check for structured guards first (RAII, try/finally, with statements)
                if self._has_structured_guard(stmt, lang):
                    continue
                
                # Detect acquire/release calls
                call_info = self._analyze_call(stmt, ctx)
                if call_info:
                    callee, receiver, args = call_info
                    name = receiver or self._name_from_args(args)
                    
                    if self._is_acquire(lang, callee, receiver):
                        if name and name not in held:
                            held[name] = stmt
                    elif self._is_release(lang, callee, receiver):
                        if name and name in held:
                            held.pop(name, None)
                
                # Check for early exits while holding locks
                if self._is_early_exit(stmt):
                    for lock_name, acq_stmt in list(held.items()):
                        span = self._get_node_span(ctx, acq_stmt)
                        yield Finding(
                            file=ctx.file_path,
                            message=f"Lock '{lock_name}' may not be released if this code path exits early—use try/finally or a context manager.",
                            severity="error",
                            span=span,
                            meta={
                                "rule_id": self.meta.id,
                                "lock_name": lock_name,
                                "issue_type": "early_exit"
                            }
                        )
                    held.clear()
        
        # End-of-scope still held → report
        for lock_name, acq_stmt in held.items():
            span = self._get_node_span(ctx, acq_stmt)
            yield Finding(
                file=ctx.file_path,
                message=f"Lock '{lock_name}' is acquired but never released—this will cause deadlocks.",
                severity="error",
                span=span,
                meta={
                    "rule_id": self.meta.id,
                    "lock_name": lock_name,
                    "issue_type": "not_released"
                }
            )

    def _get_blocks(self, scope):
        """Get basic blocks from a scope."""
        if hasattr(scope, 'basic_blocks') and scope.basic_blocks:
            return scope.basic_blocks
        else:
            # Fallback: create a single block with all statements
            class _Block:
                def __init__(self, stmts):
                    self.statements = stmts
                    self.predecessors = []
                    self.successors = []
            
            statements = getattr(scope, 'statements', [])
            if hasattr(scope, 'body'):
                statements = self._get_statements(scope.body)
            return [_Block(statements)]

    def _get_statements(self, node_or_list):
        """Extract statements from a node or list of nodes."""
        if isinstance(node_or_list, list):
            return node_or_list
        elif hasattr(node_or_list, 'statements'):
            return node_or_list.statements
        elif hasattr(node_or_list, 'children'):
            # Flatten children that look like statements
            statements = []
            for child in node_or_list.children:
                if hasattr(child, 'type') and 'statement' in child.type:
                    statements.append(child)
            return statements
        else:
            return []

    def _analyze_call(self, stmt, ctx: RuleContext):
        """Analyze a statement to extract call information."""
        # Try different patterns to extract call information
        callee = None
        receiver = None
        args = []
        
        # Method call patterns
        if hasattr(stmt, 'callee'):
            if hasattr(stmt.callee, 'property'):
                # obj.method() pattern
                receiver = self._get_text(ctx, stmt.callee.object) if hasattr(stmt.callee, 'object') else None
                callee = self._get_text(ctx, stmt.callee.property)
            else:
                callee = self._get_text(ctx, stmt.callee)
        elif hasattr(stmt, 'function'):
            # Function call pattern
            if hasattr(stmt.function, 'property'):
                receiver = self._get_text(ctx, stmt.function.object) if hasattr(stmt.function, 'object') else None
                callee = self._get_text(ctx, stmt.function.property)
            else:
                callee = self._get_text(ctx, stmt.function)
        
        # Extract arguments
        if hasattr(stmt, 'arguments'):
            args = [self._get_text(ctx, arg) for arg in stmt.arguments]
        elif hasattr(stmt, 'args'):
            args = [self._get_text(ctx, arg) for arg in stmt.args]
        
        return (callee, receiver, args) if callee else None

    def _get_text(self, ctx: RuleContext, node):
        """Get text content of a node."""
        if node is None:
            return None
        
        if hasattr(node, 'text'):
            return node.text
        elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.text[node.start_byte:node.end_byte]
        elif hasattr(node, 'value'):
            return str(node.value)
        else:
            return str(node)

    def _is_acquire(self, lang: str, callee: str, receiver: str) -> bool:
        """Check if this is a lock acquisition call."""
        if not callee:
            return False
        
        key = f"{receiver}.{callee}" if receiver and "." not in callee else callee
        patterns = self.ACQUIRE_CALLS.get(lang, set())
        return any(key.endswith(pattern) for pattern in patterns)

    def _is_release(self, lang: str, callee: str, receiver: str) -> bool:
        """Check if this is a lock release call."""
        if not callee:
            return False
        
        key = f"{receiver}.{callee}" if receiver and "." not in callee else callee
        patterns = self.RELEASE_CALLS.get(lang, set())
        return any(key.endswith(pattern) for pattern in patterns)

    def _has_structured_guard(self, stmt, lang: str) -> bool:
        """Check if statement uses structured lock management (RAII, try/finally, with)."""
        if not hasattr(stmt, 'kind'):
            return False
        
        stmt_text = self._get_text_safe(stmt)
        
        # Java/C#: try-finally with unlock in finally
        if lang in {"java", "csharp"} and stmt.type == "try_statement":
            finally_block = getattr(stmt, 'finally_block', None) or getattr(stmt, 'finally', None)
            if finally_block and self._block_calls_release(finally_block, lang):
                return True
        
        # C++: RAII with lock_guard or unique_lock
        if lang == "cpp":
            if ("lock_guard" in stmt_text or "unique_lock" in stmt_text):
                return True
        
        # Python: with statement for context managers
        if lang == "python" and stmt.type == "with_statement":
            # Don't treat explicit acquire() calls as guarded
            return ".acquire" not in stmt_text
        
        # C#: lock statement
        if lang == "csharp" and stmt.type == "lock_statement":
            return True
        
        return False

    def _get_text_safe(self, node):
        """Safely get text from a node."""
        try:
            if hasattr(node, 'text'):
                return node.text
            else:
                return ""
        except:
            return ""

    def _block_calls_release(self, block, lang: str) -> bool:
        """Check if a block contains release calls."""
        if not block:
            return False
        
        # Walk through the block looking for release calls
        nodes_to_check = [block]
        if hasattr(block, 'children'):
            nodes_to_check.extend(block.children)
        
        for node in nodes_to_check:
            if hasattr(node, 'type') and 'call' in node.type:
                call_info = self._extract_call_info(node)
                if call_info:
                    callee, receiver, _ = call_info
                    if self._is_release(lang, callee, receiver):
                        return True
        
        return False

    def _extract_call_info(self, node):
        """Extract call information from a node."""
        # Simplified version for pattern matching
        text = self._get_text_safe(node)
        if not text:
            return None
        
        # Look for method calls like obj.unlock(), Monitor.Exit(), etc.
        if "." in text:
            parts = text.split(".")
            if len(parts) >= 2:
                receiver = parts[0]
                callee = parts[1].split("(")[0]  # Remove arguments
                return (callee, receiver, [])
        
        return None

    def _is_early_exit(self, stmt) -> bool:
        """Check if statement represents an early exit (return, throw, break, continue)."""
        if not hasattr(stmt, 'type'):
            return False
        
        return stmt.type in {
            "return_statement", "throw_statement", "break_statement", 
            "continue_statement", "exit_statement", "goto_statement"
        }

    def _name_from_args(self, args: List[str]) -> Optional[str]:
        """Extract lock name from function arguments (e.g., Monitor.Enter(lock) → "lock")."""
        if args and len(args) > 0:
            # Take the first argument as the lock name
            arg = args[0].strip()
            # Remove common prefixes/suffixes
            arg = re.sub(r'^[&*]+', '', arg)  # Remove pointer/reference operators
            arg = re.sub(r'\([^)]*\)$', '', arg)  # Remove function calls
            return arg if arg.isidentifier() or '.' in arg else None
        return None

    def _get_node_span(self, ctx: RuleContext, node):
        """Get the span of a node for reporting."""
        try:
            if hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(node)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return (node.start_byte, node.end_byte)
            else:
                return (0, 10)  # Safe fallback
        except:
            return (0, 10)  # Safe fallback

    def _fallback_text_analysis(self, ctx: RuleContext, lang: str) -> Iterator[Finding]:
        """
        Fallback text-based analysis when scope analysis doesn't find patterns.
        This catches common patterns like:
        - lock.acquire() followed by return before lock.release()
        - lock.acquire() without matching release in same function
        """
        text = ctx.text
        lines = text.split('\n')
        
        # Language-specific acquire/release patterns
        acquire_patterns = {
            "python": [r'\.acquire\s*\(\s*\)', r'acquire\s*\(\s*\)'],
            "java": [r'\.lock\s*\(\s*\)', r'Lock\.lock\s*\(\s*\)', r'\.acquire\s*\(\s*\)'],
            "csharp": [r'Monitor\.Enter\s*\(', r'\.Wait\s*\(\s*\)', r'\.WaitOne\s*\(\s*\)'],
            "cpp": [r'\.lock\s*\(\s*\)', r'pthread_mutex_lock\s*\('],
        }
        
        release_patterns = {
            "python": [r'\.release\s*\(\s*\)', r'release\s*\(\s*\)'],
            "java": [r'\.unlock\s*\(\s*\)', r'Lock\.unlock\s*\(\s*\)'],
            "csharp": [r'Monitor\.Exit\s*\(', r'\.Release\s*\(', r'\.ReleaseMutex\s*\(\s*\)'],
            "cpp": [r'\.unlock\s*\(\s*\)', r'pthread_mutex_unlock\s*\('],
        }
        
        safe_patterns = {
            "python": [r'with\s+.*:', r'finally\s*:'],  # context managers and finally blocks
            "java": [r'finally\s*\{', r'try\s*\(.*\)\s*\{'],  # try-with-resources
            "csharp": [r'finally\s*\{', r'using\s*\(', r'lock\s*\('],  # using and lock statements
            "cpp": [r'lock_guard', r'unique_lock', r'scoped_lock'],  # RAII patterns
        }
        
        lang_acquires = acquire_patterns.get(lang, [])
        lang_releases = release_patterns.get(lang, [])
        lang_safe = safe_patterns.get(lang, [])
        
        # Check if this file uses any safe patterns
        has_safe_pattern = any(re.search(pattern, text) for pattern in lang_safe)
        if has_safe_pattern:
            return
        
        # Track functions/methods with acquire without release
        in_function = False
        function_start_line = 0
        function_has_acquire = False
        function_has_release = False
        acquire_line_num = 0
        acquire_match_start = 0
        
        function_start_patterns = {
            "python": r'^\s*def\s+\w+\s*\(',
            "java": r'^\s*(public|private|protected)?\s*(static)?\s*\w+\s+\w+\s*\(',
            "csharp": r'^\s*(public|private|protected)?\s*(static)?\s*\w+\s+\w+\s*\(',
            "cpp": r'^\s*\w+\s+\w+\s*\([^)]*\)\s*\{',
        }
        
        func_pattern = function_start_patterns.get(lang, r'def\s+\w+|function\s+\w+')
        
        for line_num, line in enumerate(lines):
            # Check for function start
            if re.search(func_pattern, line):
                # If ending previous function with acquire but no release
                if in_function and function_has_acquire and not function_has_release:
                    start_byte = sum(len(lines[i]) + 1 for i in range(acquire_line_num)) + acquire_match_start
                    yield Finding(
                        file=ctx.file_path,
                        message="Lock acquired but not released in all paths; use try/finally or context manager.",
                        severity="error",
                        rule=self.meta.id,
                        start_byte=start_byte,
                        end_byte=start_byte + 20,
                    )
                
                # Start new function
                in_function = True
                function_start_line = line_num
                function_has_acquire = False
                function_has_release = False
            
            # Check for acquire patterns
            for pattern in lang_acquires:
                match = re.search(pattern, line)
                if match:
                    function_has_acquire = True
                    acquire_line_num = line_num
                    acquire_match_start = match.start()
            
            # Check for release patterns
            for pattern in lang_releases:
                if re.search(pattern, line):
                    function_has_release = True
            
            # Check for early exit after acquire but before release
            if function_has_acquire and not function_has_release:
                if re.search(r'\breturn\b', line) or re.search(r'\braise\b', line) or re.search(r'\bthrow\b', line):
                    start_byte = sum(len(lines[i]) + 1 for i in range(acquire_line_num)) + acquire_match_start
                    yield Finding(
                        file=ctx.file_path,
                        message="Lock may not be released on early exit; use try/finally or context manager.",
                        severity="error",
                        rule=self.meta.id,
                        start_byte=start_byte,
                        end_byte=start_byte + 20,
                    )
                    # Reset to avoid duplicate reports in same function
                    function_has_release = True
        
        # Check final function
        if in_function and function_has_acquire and not function_has_release:
            start_byte = sum(len(lines[i]) + 1 for i in range(acquire_line_num)) + acquire_match_start
            yield Finding(
                file=ctx.file_path,
                message="Lock acquired but not released in all paths; use try/finally or context manager.",
                severity="error",
                rule=self.meta.id,
                start_byte=start_byte,
                end_byte=start_byte + 20,
            )


# Register the rule
rule = ConcurrencyLockNotReleasedRule()
RULES = [rule]


