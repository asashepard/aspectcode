"""Rule: sec.path_traversal

Warn on file operations that use user-controlled paths without normalization/whitelisting.
Detects path traversal vulnerabilities where paths can escape base directories.
"""

from typing import Iterator, List, Optional, Set, Dict

from engine.types import Rule, RuleContext, RuleMeta, Finding, Requires


class SecPathTraversalRule:
    """Rule implementation for detecting path traversal vulnerabilities."""
    
    meta = RuleMeta(
        id="sec.path_traversal",
        category="sec",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Warn on file operations using user-controlled paths without normalization",
        langs=["python", "javascript", "typescript", "java", "csharp", "go", "ruby"],
    )
    requires = Requires(syntax=True)
    
    def __init__(self):
        # File operation sinks by language
        self.SINK_TAILS = {
            "python": {
                "open", "os.open", "os.remove", "os.rename", "os.unlink", "os.rmdir",
                "shutil.copy", "shutil.copy2", "shutil.move", "shutil.rmtree", "shutil.copytree",
                "Path.open", "Path.unlink", "Path.rename", "Path.read_text", "Path.write_text",
                "pathlib.Path.open", "pathlib.Path.unlink", "pathlib.Path.rename"
            },
            "javascript": {
                "fs.readFile", "fs.readFileSync", "fs.promises.readFile",
                "fs.writeFile", "fs.writeFileSync", "fs.promises.writeFile",
                "fs.readdir", "fs.readdirSync", "fs.promises.readdir",
                "fs.unlink", "fs.unlinkSync", "fs.promises.unlink",
                "fs.rename", "fs.renameSync", "fs.promises.rename",
                "fs.createReadStream", "fs.createWriteStream",
                "readFile", "readFileSync", "writeFile", "writeFileSync"
            },
            "typescript": {
                "fs.readFile", "fs.readFileSync", "fs.promises.readFile",
                "fs.writeFile", "fs.writeFileSync", "fs.promises.writeFile",
                "fs.readdir", "fs.readdirSync", "fs.promises.readdir",
                "fs.unlink", "fs.unlinkSync", "fs.promises.unlink",
                "fs.rename", "fs.renameSync", "fs.promises.rename",
                "fs.createReadStream", "fs.createWriteStream",
                "readFile", "readFileSync", "writeFile", "writeFileSync"
            },
            "java": {
                "java.io.File", "new File", "File.<init>",
                "java.nio.file.Paths.get", "Paths.get",
                "java.nio.file.Files.", "Files.newInputStream", "Files.newOutputStream",
                "Files.readAllBytes", "Files.write", "Files.copy", "Files.move"
            },
            "csharp": {
                "System.IO.File.", "File.ReadAllText", "File.WriteAllText", "File.ReadAllBytes",
                "File.OpenRead", "File.OpenWrite", "File.Create", "File.Delete",
                "System.IO.Directory.", "Directory.GetFiles", "Directory.CreateDirectory",
                "Directory.Delete", "File.", "Directory."
            },
            "go": {
                "os.Open", "os.OpenFile", "os.ReadFile", "os.WriteFile",
                "os.Remove", "os.RemoveAll", "os.Rename", "os.Create",
                "ioutil.ReadFile", "ioutil.WriteFile"
            },
            "ruby": {
                "File.open", "File.read", "File.write", "File.rename", "File.delete",
                "File.unlink", "File.chmod", "File.chown",
                "Dir.open", "Dir.glob", "Dir.foreach",
                "FileUtils.", "FileUtils.cp", "FileUtils.mv", "FileUtils.rm",
                "IO.read", "IO.write"
            }
        }
        
        # Hints that suggest user-controlled input
        self.USER_HINTS = (
            "path", "filepath", "filename", "file", "dir", "dirname",
            "request", "req", "params", "query", "body", "input", "param",
            "argv", "user", "upload", "name", "url", "uri"
        )
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for path traversal vulnerabilities."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Get language from adapter
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        if language not in self.SINK_TAILS:
            return
        
        for node in ctx.tree.walk():
            # Check if this is a function call
            if not self._is_call_node(node):
                continue
                
            callee = self._get_callee_text(node, ctx)
            if not callee or not self._is_sink(language, callee):
                continue
            
            # Get the path argument (typically first argument)
            path_arg = self._get_path_argument(node)
            if not path_arg:
                continue
            
            # Check if this looks like a vulnerable pattern
            is_user_controlled = self._looks_user_controlled(path_arg, ctx)
            has_traversal = self._has_traversal_literal(path_arg, ctx)
            
            if is_user_controlled or has_traversal:
                # Check if there are normalization guards
                if not self._has_normalization_guard(node, path_arg, language, ctx):
                    start_byte, end_byte = self._get_node_span(path_arg)
                    message = ("File path may contain user input without validation—"
                              "sanitize or restrict to a base directory to prevent path traversal.")
                    yield Finding(
                        rule=self.meta.id,
                        message=message,
                        file=ctx.file_path,
                        start_byte=start_byte,
                        end_byte=end_byte,
                        severity="warning"
                    )
    
    def _is_call_node(self, node) -> bool:
        """Check if node represents a function call."""
        kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        return kind in {
            'call_expression', 'call', 'function_call', 'method_call',
            'invocation_expression', 'method_invocation', 'constructor_call',
            'object_creation_expression'  # For Java 'new File(...)'
        }
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the callee text from a call node."""
        # Try to find the function/method being called
        callee_node = None
        
        # Look for common callee patterns
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'identifier', 'member_expression', 'member_access_expression', 
                             'attribute', 'qualified_name', 
                             'dotted_name', 'type_identifier', 'constructor_name'}:
                callee_node = child
                break
        
        if not callee_node:
            return ""
        
        # Get the text of the callee
        start_byte = getattr(callee_node, 'start_byte', 0)
        end_byte = getattr(callee_node, 'end_byte', start_byte)
        
        return ctx.text[start_byte:end_byte]
    
    def _is_sink(self, language: str, callee: str) -> bool:
        """Check if the callee is a file operation sink."""
        sinks = self.SINK_TAILS.get(language, set())
        
        # Direct match
        if callee in sinks:
            return True
        
        # Check for suffix matches and partial matches
        for sink in sinks:
            # Exact match
            if callee == sink:
                return True
            # Suffix match (qualified names)
            if callee.endswith('.' + sink) or callee.endswith('::' + sink):
                return True
            # Prefix match for namespace patterns like "Files."
            if sink.endswith('.') and sink in callee:
                return True
            # Constructor patterns like "new File"
            if sink.startswith('new ') and callee.endswith(sink[4:]):
                return True
            # Split on parentheses for method calls
            if callee.split('(')[0].endswith(sink):
                return True
        
        return False
    
    def _get_path_argument(self, node):
        """Extract the path argument from a call node (typically first argument)."""
        # First try to get arguments from the current call
        args = self._get_call_arguments(node)
        if args:
            return args[0]
        
        # For method calls like Path(...).method(), check if the path is in the constructor
        # Look for patterns like "Path.method" or "object.method" where object might be a constructor
        callee_text = ""
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'identifier', 'member_expression', 'attribute', 'qualified_name', 'dotted_name'}:
                callee_text = getattr(child, 'text', b'').decode()
                break
        
        # Check if this is a method call on a constructor like "Path(...).open()"
        if '.' in callee_text:
            parts = callee_text.split('.')
            if len(parts) >= 2:
                constructor_name = parts[0]
                method_name = parts[1]
                
                # If this looks like a method on a path-like constructor
                if constructor_name in {'Path', 'pathlib.Path', 'File', 'java.io.File'} and \
                   method_name in {'open', 'read', 'write', 'readText', 'writeText'}:
                    
                    # Try to find the constructor call in the node tree
                    # Look for constructor pattern in the full text
                    node_text = getattr(node, 'text', b'').decode()
                    if '(' in node_text and ')' in node_text:
                        # Extract the constructor arguments
                        # For "Path(arg).method()", we want to extract "arg"
                        first_paren = node_text.find('(')
                        if first_paren > 0:
                            # Find the matching closing paren for the constructor
                            paren_count = 0
                            constructor_end = -1
                            for i, char in enumerate(node_text[first_paren:], first_paren):
                                if char == '(':
                                    paren_count += 1
                                elif char == ')':
                                    paren_count -= 1
                                    if paren_count == 0:
                                        constructor_end = i
                                        break
                            
                            if constructor_end > first_paren:
                                constructor_args = node_text[first_paren + 1:constructor_end]
                                if constructor_args.strip():
                                    # Create a simple node-like object for the constructor argument
                                    class SimpleNode:
                                        def __init__(self, text, kind='identifier'):
                                            self.text = text.encode() if isinstance(text, str) else text
                                            self.kind = kind
                                            self.start_byte = 0
                                            self.end_byte = len(text)
                                    
                                    arg_text = constructor_args.strip()
                                    kind = 'binary_expression' if '+' in arg_text else 'identifier'
                                    return SimpleNode(arg_text, kind)
        
        return None
    
    def _get_call_arguments(self, node) -> list:
        """Extract arguments from a call node."""
        args = []
        
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'arguments', 'argument_list', 'parameter_list'}:
                # Get the actual argument nodes
                for arg_child in getattr(child, 'children', []):
                    arg_kind = getattr(arg_child, 'kind', '') or getattr(arg_child, 'type', '')
                    if arg_kind not in {',', '(', ')', 'comma'}:
                        args.append(arg_child)
                break
        
        return args
    
    def _looks_user_controlled(self, node, ctx: RuleContext) -> bool:
        """Check if a node looks like user-controlled input."""
        kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        text = self._get_node_text(node, ctx)
        
        # Dynamic string construction patterns
        if kind in {"binary_expression", "template_string", "interpolated_string", "fstring", "f_string"}:
            return True
        
        # Check identifier names for user-input hints
        if kind in {"identifier", "name"}:
            name = text.lower()
            return any(hint in name for hint in self.USER_HINTS)
        
        # Check for object property access like req.params.file
        if any(hint in text.lower() for hint in self.USER_HINTS):
            return True
        
        # Member access patterns (req.params, request.query, etc.)
        if kind in {"member_expression", "attribute"}:
            return any(hint in text.lower() for hint in self.USER_HINTS)
        
        return False
    
    def _has_traversal_literal(self, node, ctx: RuleContext) -> bool:
        """Check if a node contains literal path traversal patterns."""
        text = self._get_node_text(node, ctx).lower()
        
        # Directory traversal patterns
        if ".." in text:
            return True
        
        # Absolute path patterns - check both quoted and unquoted
        absolute_patterns = [
            "/", "\\",  # Unix/Windows absolute paths
            "c:", "d:",  # Windows drive letters
            "~"   # Home directory
        ]
        
        # Check if text starts with absolute patterns (unquoted)
        if any(text.startswith(pattern) for pattern in absolute_patterns):
            return True
        
        # Check if text contains quoted absolute patterns
        quoted_patterns = [
            "'/", '"/','`/', "'\\", '"\\', "`\\",  # Unix/Windows absolute
            "'c:", '"c:', "`c:",  # Windows drive letters
            "'..", '"..',"`..","'~", '"~', "`~"   # Relative traversal/home
        ]
        if any(pattern in text for pattern in quoted_patterns):
            return True
        
        return False
    
    def _has_normalization_guard(self, call_node, path_arg, language: str, ctx: RuleContext) -> bool:
        """Check if there are normalization/validation guards nearby."""
        import re
        
        # Get surrounding context (parent block or statement)
        context_text = self._get_surrounding_context(call_node, ctx)
        
        # Keep original text (lowercase only) for pattern matching
        text = context_text.lower()
        
        # Patterns that indicate path normalization/validation (exact matches)
        # These are specific enough to not need word boundaries
        exact_patterns = [
            # Python
            "os.path.realpath", "os.path.abspath", "pathlib.path.resolve", 
            "path.resolve(", ".resolve(", ".startswith(",
            
            # JavaScript/TypeScript
            "path.resolve(", "path.normalize(", "path.join(",
            
            # Java
            "torealpath(", "normalize(", "toabsolutepath(", ".startswith(",
            
            # C#
            "path.getfullpath(", "path.ispathrooted(", 
            "stringcomparison.ordinal",
            
            # Go
            "filepath.clean(", "filepath.join(", "strings.hasprefix(",
            
            # Ruby
            "file.expand_path(", "file.join(", "start_with?(",
        ]
        
        # Check exact patterns (these are specific enough)
        text_normalized = text.replace(" ", "").replace("\n", "").replace("\t", "")
        for pattern in exact_patterns:
            if pattern.replace(" ", "") in text_normalized:
                return True
        
        # Word-boundary patterns - these need regex to avoid false positives
        # e.g., "throw" should not match "throws" in Java method signatures
        word_patterns = [
            r'\bif\s*\(',      # if statement with condition
            r'\bunless\b',     # Ruby unless
            r'\braise\b',      # Python raise
            r'\bthrow\s+\w',   # throw followed by exception (not throws in signature)
            r'\bpanic\b',      # Go panic
            r'\bvalidate\w*\s*\(', # validate function call
            r'\bcheck\w*\s*\(',    # check function call
            r'\bwhitelist\b',
            r'\ballowlist\b',
        ]
        
        for pattern in word_patterns:
            if re.search(pattern, text):
                return True
        
        return False
    
    def _get_surrounding_context(self, node, ctx: RuleContext, max_distance: int = 300) -> str:
        """Get surrounding context text for guard detection."""
        start_byte = max(0, getattr(node, 'start_byte', 0) - max_distance)
        end_byte = min(len(ctx.text), getattr(node, 'end_byte', 0) + max_distance)
        
        return ctx.text[start_byte:end_byte]
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
        """Get the text content of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte)
        
        return ctx.text[start_byte:end_byte]
    
    def _get_node_span(self, node) -> tuple:
        """Get the span of a node for reporting."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 0))


# Export rule for registration
RULES = [SecPathTraversalRule()]


