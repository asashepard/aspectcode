"""
Rule: memory.leak.open_not_closed

Detects opens/allocations that are not reliably closed/freed on all control-flow paths.
Recommends using with/context managers (Python), defer Close (Go), try-with-resources (Java),
using (C#), RAII (C/C++/Rust/Swift), or explicit close()/free()/delete.

Category: memory
Severity: error
Priority: P0
Languages: python, typescript, javascript, go, java, cpp, c, csharp, ruby, rust, swift
Autofix: suggest-only
"""

from typing import Iterator, Dict, Set, Any, List, Optional
from engine.types import RuleContext, Finding
from engine.types import Rule, RuleMeta, Requires


class MemoryOpenNotClosedRule:
    """Detect resource acquisitions that are not reliably closed/freed on all paths."""
    
    meta = RuleMeta(
        id="memory.leak.open_not_closed",
        category="memory",
        tier=1,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects opens/allocations that are not reliably closed/freed on all control-flow paths.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True, scopes=True, raw_text=True)
    
    # Heuristic acquisition/release signatures (normalized callee names)
    ACQUIRE = {
        "python": {"open", "tempfile.NamedTemporaryFile", "sqlite3.connect", "socket.socket"},
        "javascript": {"fs.open", "fs.createReadStream", "fs.createWriteStream", "fs.promises.open", "net.createConnection"},
        "typescript": {"fs.open", "fs.createReadStream", "fs.createWriteStream", "fs.promises.open", "net.createConnection"},
        "go": {"os.Open", "os.Create", "net.Dial", "sql.Open"},
        "java": {"java.io.FileInputStream.<init>", "java.io.FileOutputStream.<init>", "java.io.RandomAccessFile.<init>", 
                "java.util.zip.ZipFile.<init>", "java.sql.Connection.<init>", "java.sql.DriverManager.getConnection"},
        "csharp": {"new System.IO.FileStream", "System.IO.File.Open", "System.Net.Sockets.Socket..ctor", 
                  "System.Data.SqlClient.SqlConnection..ctor"},
        "c": {"fopen", "open", "socket", "malloc", "calloc", "realloc"},
        "cpp": {"fopen", "open", "socket", "malloc", "calloc", "realloc", "new"},
        "ruby": {"File.open", "TCPSocket.new"},
        "rust": {"std::fs::File::open", "std::net::TcpStream::connect"},
        "swift": {"FileHandle(forReadingAtPath:)", "FileHandle(forWritingAtPath:)", "fopen"},
    }
    
    RELEASE = {
        "python": {"close", "commit", "rollback", "shutdown"},
        "javascript": {"close", "end", "destroy", "fs.close", "filehandle.close"},
        "typescript": {"close", "end", "destroy", "fs.close", "filehandle.close"},
        "go": {"Close"},
        "java": {"close"},
        "csharp": {"Close", "Dispose"},
        "c": {"fclose", "close", "free"},
        "cpp": {"fclose", "close", "free", "delete"},
        "ruby": {"close"},
        "rust": {"drop", "shutdown"},
        "swift": {"close", "fclose"},
    }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect files opened but not closed with resource tracking."""
        if not ctx.tree:
            return
            
        # Get language ID
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        
        if language not in self.meta.langs:
            return
            
        # Track file resources within function scopes
        for scope in self._find_function_scopes(ctx):
            opened_files = self._find_file_open_calls(ctx, scope)
            closed_files = self._find_file_close_calls(ctx, scope)
            
            for file_var, open_node in opened_files.items():
                if file_var not in closed_files:
                    start_byte, end_byte = self._get_node_span(open_node)
                    yield Finding(
                        rule=self.meta.id,
                        message=f"File resource '{file_var}' opened but never closed, potential resource leak",
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="warning"
                    )
    
    def _find_function_scopes(self, ctx: RuleContext):
        """Find all function scope nodes in the syntax tree."""
        if not ctx.tree:
            return []
        
        function_nodes = []
        
        def visit_node(node):
            if hasattr(node, 'type') and node.type in [
                'function_definition', 'method_definition', 'async_function_definition',
                'function', 'method', 'constructor', 'lambda', 'arrow_function'
            ]:
                function_nodes.append(node)
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    visit_node(child)
        
        visit_node(ctx.tree.root_node)
        return function_nodes
    
    def _find_file_open_calls(self, ctx, scope_node):
        """Find file open operations in scope."""
        opened_files = {}
        
        # Use iterative traversal to avoid recursion limit
        visited = set()
        stack = [scope_node]
        
        while stack:
            node = stack.pop()
            node_id = id(node)
            
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node_text = self._get_node_text(node, ctx)
            if any(pattern in node_text for pattern in ['open(', 'fopen(', 'File.open', 'FileReader']):
                # Try to extract variable name
                var_name = self._extract_assignment_target(ctx, node)
                if var_name:
                    opened_files[var_name] = node
            
            # Add children to stack
            for child in getattr(node, 'children', []):
                stack.append(child)
        
        return opened_files
    
    def _find_file_close_calls(self, ctx, scope_node):
        """Find file close operations in scope."""
        closed_files = set()
        
        # Use iterative traversal to avoid recursion limit
        visited = set()
        stack = [scope_node]
        
        while stack:
            node = stack.pop()
            node_id = id(node)
            
            if node_id in visited:
                continue
            visited.add(node_id)
            
            node_text = self._get_node_text(node, ctx)
            if any(pattern in node_text for pattern in ['.close()', 'fclose(', '.Close()']):
                # Extract the variable being closed
                var_name = node_text.split('.')[0].strip()
                if var_name.isidentifier():
                    closed_files.add(var_name)
            
            # Add children to stack
            for child in getattr(node, 'children', []):
                stack.append(child)
        
        return closed_files
    
    def _extract_assignment_target(self, ctx, node):
        """Extract the variable name from assignment."""
        # Look for parent assignment
        parent = getattr(node, 'parent', None)
        if parent:
            parent_text = self._get_node_text(parent, ctx)
            if '=' in parent_text:
                target = parent_text.split('=')[0].strip()
                if target.isidentifier():
                    return target
        return None
    
    def _walk_tree(self, node):
        """Walk the tree iteratively (stack-based) to avoid recursion limit."""
        visited = set()
        stack = [node]
        
        while stack:
            current = stack.pop()
            node_id = id(current)
            
            # Skip already visited
            if node_id in visited:
                continue
            
            visited.add(node_id)
            yield current
            
            # Add children to stack (reversed to maintain order)
            if hasattr(current, 'children') and current.children:
                stack.extend(reversed(current.children))
    
    def _is_function_scope(self, node) -> bool:
        """Check if node represents a function/method scope."""
        if not hasattr(node, 'kind'):
            return False
        return node.kind in {
            "function_definition", "function_declaration", "method_definition",
            "function", "method", "constructor", "lambda", "arrow_function"
        }
    
    def _check_scope(self, ctx: RuleContext, scope_node) -> Iterator[Finding]:
        """Check a function scope for resource leaks."""
        lang = ctx.adapter.language_id
        
        # Track resources by variable/receiver name → acquisition node
        held: Dict[str, Any] = {}
        
        # Get all statements in the scope
        statements = self._get_statements(scope_node)
        
        for stmt in statements:
            # Skip statements that encode structured-safe patterns
            if self._structured_safe(stmt, lang, ctx):
                continue
                
            callee = self._get_callee_text(stmt, ctx)
            recv = self._get_receiver_name(stmt, ctx)
            var = self._get_target_var(stmt, ctx) or recv
            
            # Check for resource acquisition
            if self._is_acquire(lang, callee):
                if var and var not in held:
                    held[var] = stmt
                    
            # Check for resource release
            elif self._is_release(lang, callee, recv):
                if recv in held:
                    held.pop(recv, None)
                elif var in held:
                    held.pop(var, None)
            
            # Check for early exits with held resources
            if self._is_early_exit(stmt) and held:
                for name, acq_stmt in list(held.items()):
                    start, end = self._get_call_span(ctx, acq_stmt)
                    yield Finding(
                        rule=self.meta.id,
                        file=ctx.file_path,
                        message=f"Resource '{name}' may not be closed/freed on all paths; use with/RAII/using/try-with-resources or ensure close/free in finally/defer.",
                        severity="error",
                        start_byte=start,
                        end_byte=end,
                    )
                held.clear()
        
        # Check for resources held at end of scope
        for name, acq_stmt in held.items():
            start, end = self._get_call_span(ctx, acq_stmt)
            yield Finding(
                rule=self.meta.id,
                file=ctx.file_path,
                message=f"Resource '{name}' acquired but not clearly released on all paths.",
                severity="error",
                start_byte=start,
                end_byte=end,
            )
    
    def _get_statements(self, scope_node) -> List[Any]:
        """Get all statements from a scope node."""
        statements = []
        
        # Try to get body/block
        body = getattr(scope_node, 'body', None)
        if body:
            if hasattr(body, 'children') and body.children:
                statements.extend(body.children)
            elif hasattr(body, '__iter__'):
                statements.extend(body)
        
        # Fallback: get children directly
        if not statements and hasattr(scope_node, 'children'):
            statements = [child for child in scope_node.children 
                         if hasattr(child, 'kind') and child.kind not in {'identifier', 'parameters'}]
        
        return statements
    
    def _is_acquire(self, lang: str, callee: str) -> bool:
        """Check if callee is a resource acquisition function."""
        sigs = self.ACQUIRE.get(lang, set())
        return any(callee.endswith(s) or callee == s or s in callee for s in sigs)
    
    def _is_release(self, lang: str, callee: str, recv: str) -> bool:
        """Check if callee is a resource release function."""
        sigs = self.RELEASE.get(lang, set())
        
        # Direct method/function call
        if any(callee.endswith(s) or callee == s for s in sigs):
            return True
            
        # Method call like var.close()
        if any(s in callee for s in sigs):
            return True
            
        # Receiver-based release
        if recv and any(s == recv for s in sigs):
            return True
            
        return False
    
    def _structured_safe(self, stmt, lang: str, ctx: RuleContext) -> bool:
        """Check if statement uses structured patterns that guarantee release."""
        if not hasattr(stmt, 'kind'):
            return False
            
        stmt_text = self._get_node_text(ctx, stmt)
        
        if lang == "python":
            # with statement
            if stmt.kind == "with_statement":
                return True
            # try/finally with .close() in finally
            if stmt.kind == "try_statement":
                return self._has_finally_with_release(stmt, lang, ctx)
                
        elif lang in {"javascript", "typescript"}:
            # try/finally pattern
            if stmt.kind == "try_statement":
                return self._has_finally_with_release(stmt, lang, ctx)
                
        elif lang == "go":
            # defer x.Close()
            if "defer " in stmt_text and "Close(" in stmt_text:
                return True
                
        elif lang == "java":
            # try-with-resources
            if stmt.kind == "try_statement" and "try (" in stmt_text:
                return True
            # try/finally with close
            if stmt.kind == "try_statement":
                return self._has_finally_with_release(stmt, lang, ctx)
                
        elif lang == "csharp":
            # using statement/declaration
            if stmt.kind in {"using_statement", "using_declaration"} or stmt_text.strip().startswith("using"):
                return True
            # try/finally with close
            if stmt.kind == "try_statement":
                return self._has_finally_with_release(stmt, lang, ctx)
                
        elif lang == "cpp":
            # RAII via smart pointers/streams
            if any(k in stmt_text for k in ("unique_ptr<", "shared_ptr<", "std::ifstream", "std::ofstream", "std::fstream")):
                return True
                
        elif lang == "rust":
            # RAII: normal variables auto-drop; hazardous only if mem::forget present
            if "mem::forget" not in stmt_text:
                return True
                
        elif lang == "swift":
            # defer { ... close() }
            if "defer" in stmt_text and "close(" in stmt_text:
                return True
                
        elif lang == "ruby":
            # File.open(...) { |f| ... } block auto-closes
            if stmt.kind == "block" and "File.open" in stmt_text and "{" in stmt_text:
                return True
        
        return False
    
    def _has_finally_with_release(self, try_stmt, lang: str, ctx: RuleContext) -> bool:
        """Check if try statement has finally block with release calls."""
        # Look for finally block in children
        for child in getattr(try_stmt, 'children', []):
            if hasattr(child, 'kind') and 'finally' in child.kind:
                return self._block_calls_release(child, lang, ctx)
        return False
    
    def _block_calls_release(self, block, lang: str, ctx: RuleContext) -> bool:
        """Check if block contains release calls."""
        for node in ctx.walk_nodes(block):
            callee = self._get_callee_text(node, ctx)
            recv = self._get_receiver_name(node, ctx)
            if self._is_release(lang, callee, recv):
                return True
        return False
    
    def _is_early_exit(self, stmt) -> bool:
        """Check if statement is an early exit (return, throw, break, continue)."""
        if not hasattr(stmt, 'kind'):
            return False
        return stmt.kind in {
            "return_statement", "throw_statement", "break_statement", 
            "continue_statement", "raise_statement", "panic"
        }
    
    def _get_target_var(self, stmt, ctx: RuleContext) -> Optional[str]:
        """Extract the variable receiving the resource assignment."""
        if not hasattr(stmt, 'kind'):
            return None
            
        # Handle different assignment patterns
        if stmt.kind in {"assignment_expression", "assignment", "variable_declaration", "let_declaration"}:
            # Look for left-hand side identifier
            if hasattr(stmt, 'left'):
                return self._get_identifier_text(stmt.left, ctx)
            elif hasattr(stmt, 'declarators') and stmt.declarators:
                # Java/C# style: Type var = new Resource()
                declarator = stmt.declarators[0] if hasattr(stmt.declarators, '__getitem__') else stmt.declarators
                if hasattr(declarator, 'name'):
                    return self._get_identifier_text(declarator.name, ctx)
                    
        # Go-style: var := expr
        if ":=" in self._get_node_text(ctx, stmt):
            parts = self._get_node_text(ctx, stmt).split(":=")
            if len(parts) >= 2:
                var_part = parts[0].strip()
                # Handle "f, err := os.Open(...)"
                if "," in var_part:
                    return var_part.split(",")[0].strip()
                return var_part
        
        return None
    
    def _get_callee_text(self, stmt, ctx: RuleContext) -> str:
        """Get the callee text from a statement."""
        if not hasattr(stmt, 'kind'):
            return ""
            
        # Try to find call expression
        if stmt.kind in {"call_expression", "call", "invocation_expression", "method_call"}:
            # For tree-sitter, function name is first identifier child
            if hasattr(stmt, 'children') and stmt.children:
                for child in stmt.children:
                    if child.type == "identifier":
                        if hasattr(child, 'text'):
                            text = child.text
                            if hasattr(text, 'decode'):
                                return text.decode()
                            else:
                                return str(text)
                        break
            
            # Fallback: Get function/method name
            if hasattr(stmt, 'function'):
                return self._get_node_text(ctx, stmt.function)
            elif hasattr(stmt, 'callee'):
                return self._get_node_text(ctx, stmt.callee)
                
        # Look for calls in assignment
        if hasattr(stmt, 'right') and hasattr(stmt.right, 'kind'):
            if stmt.right.kind in {"call_expression", "call", "invocation_expression"}:
                return self._get_callee_text(stmt.right, ctx)
                
        # Look in children for call expressions
        for child in getattr(stmt, 'children', []):
            if hasattr(child, 'kind') and child.kind in {"call_expression", "call", "invocation_expression"}:
                return self._get_callee_text(child, ctx)
                
        return ""
    
    def _get_receiver_name(self, stmt, ctx: RuleContext) -> str:
        """Get the receiver/object name for method calls."""
        callee_text = self._get_callee_text(stmt, ctx)
        if "." in callee_text:
            return callee_text.split(".")[0]
        return ""
    
    def _get_identifier_text(self, node, ctx: RuleContext) -> Optional[str]:
        """Get text from an identifier node."""
        if not node:
            return None
        text = self._get_node_text(ctx, node)
        # Clean up text (remove whitespace, handle simple cases)
        if text and text.isidentifier():
            return text
        return None
    
    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
            
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, str):
                return text
            elif hasattr(text, 'decode'):
                return text.decode('utf-8', errors='ignore')
                
        # Try to get span and extract from source
        try:
            if hasattr(ctx.adapter, 'node_span') and ctx.text:
                start, end = ctx.adapter.node_span(node)
                if start is not None and end is not None and start >= 0 and end <= len(ctx.text):
                    return ctx.text[start:end]
        except:
            pass
            
        return ""
    
    def _get_call_span(self, ctx: RuleContext, node):
        """Get the span of a call node for reporting."""
        try:
            # Try to get the callee span specifically
            if hasattr(node, 'function'):
                callee = node.function
            elif hasattr(node, 'callee'):
                callee = node.callee
            else:
                callee = node
                
            if hasattr(ctx.adapter, 'node_span'):
                return ctx.adapter.node_span(callee)
        except:
            pass
            
        # Fallback span
        return (0, 10)
    
    def _get_node_span(self, node):
        """Get the byte span of a node for reporting."""
        try:
            if hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return (node.start_byte, node.end_byte)
        except:
            pass
        # Fallback span
        return (0, 10)


# Register the rule
_rule = MemoryOpenNotClosedRule()
RULES = [_rule]


