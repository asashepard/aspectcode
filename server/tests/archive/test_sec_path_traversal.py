"""Test suite for sec.path_traversal rule.

Tests path traversal detection across multiple languages including
user-controlled paths and literal traversal patterns.
"""

import pytest
from engine.types import RuleContext
from rules.sec_path_traversal import SecPathTraversalRule


class MockNode:
    """Mock syntax tree node for testing."""
    
    def __init__(self, kind='', text='', start_byte=0, end_byte=None, children=None, parent=None, **kwargs):
        self.kind = kind
        self.type = kind
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_byte = start_byte
        self.end_byte = end_byte if end_byte is not None else start_byte + len(text)
        self.children = children or []
        self.parent = parent
        
        # Add any additional attributes
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Set up parent-child relationships
        for child in self.children:
            if child:
                child.parent = self


class MockSyntax:
    """Mock syntax tree for testing."""
    
    def __init__(self, root_node=None):
        self.root_node = root_node
        self._nodes = []
        if root_node:
            self._collect_nodes(root_node)
    
    def _collect_nodes(self, node):
        """Collect all nodes for walking."""
        self._nodes.append(node)
        for child in getattr(node, 'children', []):
            if child:
                self._collect_nodes(child)
    
    def walk(self):
        """Walk through all nodes."""
        return self._nodes


class MockAdapter:
    """Mock adapter for testing."""
    
    def __init__(self, language='python'):
        self.lang = language
        
    def language_id(self):
        return self.lang


class TestSecPathTraversalRule:
    """Test cases for the path traversal rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecPathTraversalRule()
    
    def _create_context(self, code: str, language: str) -> RuleContext:
        """Create a test context."""
        # Check for method chaining like "Path(...).open()"
        if ').' in code and code.count('(') >= 2:
            # This is a method call on a constructed object
            # Find the last method call
            last_dot = code.rfind('.')
            if last_dot > 0:
                # Find the opening paren of the last method call
                method_paren = code.find('(', last_dot)
                if method_paren > 0:
                    # Extract the method name
                    method_name = code[last_dot + 1:method_paren]
                    # Create a method call node
                    root_node = MockNode(
                        kind='call_expression',
                        text=code,
                        start_byte=0,
                        end_byte=len(code),
                        children=self._parse_method_chain(code, language, method_name)
                    )
                else:
                    root_node = self._create_simple_call_node(code, language)
            else:
                root_node = self._create_simple_call_node(code, language)
        elif language == 'java' and code.startswith('new '):
            # Java constructor
            root_node = MockNode(
                kind='object_creation_expression',
                text=code,
                start_byte=0,
                end_byte=len(code),
                children=self._parse_java_constructor(code)
            )
        else:
            # Regular function/method call
            root_node = self._create_simple_call_node(code, language)
        
        tree = MockSyntax(root_node)
        adapter = MockAdapter(language)
        
        return RuleContext(
            file_path="test.py",
            text=code,
            tree=tree,
            adapter=adapter,
            config={}
        )
    
    def _create_simple_call_node(self, code: str, language: str) -> MockNode:
        """Create a simple call node for regular function calls."""
        if '(' in code and ')' in code:
            return MockNode(
                kind='call_expression',
                text=code,
                start_byte=0,
                end_byte=len(code),
                children=self._parse_call_structure(code, language)
            )
        else:
            return MockNode(
                kind='expression_statement',
                text=code,
                start_byte=0,
                end_byte=len(code)
            )
    
    def _parse_method_chain(self, code: str, language: str, method_name: str) -> list:
        """Parse method chaining like Path(...).open()."""
        children = []
        
        # Create an attribute node that represents the full method access
        # For "Path(...).open()", we want the callee to be "Path.open" or just "open"
        last_dot = code.rfind('.')
        object_part = code[:last_dot]
        
        # Check if it's a constructor + method pattern
        if '(' in object_part and object_part.count('(') >= 1:
            # This is like "Path(...).open()" - extract constructor name
            first_paren = object_part.index('(')
            constructor_name = object_part[:first_paren]
            full_method = f"{constructor_name}.{method_name}"
        else:
            full_method = f"{object_part}.{method_name}"
        
        # Create attribute node
        children.append(MockNode(
            kind='attribute',
            text=full_method,
            start_byte=0,
            end_byte=last_dot + len(method_name) + 1
        ))
        
        # Add arguments from the method call
        method_paren = code.find('(', last_dot)
        if method_paren > 0:
            method_end = code.rfind(')')
            args_text = code[method_paren:method_end + 1]
            inner_args = code[method_paren + 1:method_end]
            
            children.append(MockNode(
                kind='arguments',
                text=args_text,
                start_byte=method_paren,
                end_byte=method_end + 1,
                children=self._parse_arguments_with_position(inner_args, method_paren + 1, code)
            ))
        
        return children
    
    def _parse_java_constructor(self, code: str) -> list:
        """Parse Java constructor call structure."""
        children = []
        
        # Find the constructor name
        paren_idx = code.index('(')
        constructor_part = code[:paren_idx]
        
        children.append(MockNode(
            kind='identifier',
            text=constructor_part,
            start_byte=0,
            end_byte=len(constructor_part)
        ))
        
        # Add arguments
        args_start = code.index('(')
        args_end = code.rindex(')')
        args_text = code[args_start:args_end + 1]
        inner_args = code[args_start + 1:args_end]
        
        children.append(MockNode(
            kind='arguments',
            text=args_text,
            start_byte=args_start,
            end_byte=args_end + 1,
            children=self._parse_arguments_with_position(inner_args, args_start + 1, code)
        ))
        
        return children
    
    def _parse_call_structure(self, code: str, language: str) -> list:
        """Parse basic call structure for testing."""
        children = []
        
        # Handle method calls like "Path(...).open()"
        if '.' in code and '(' in code:
            # This is a method call
            last_dot = code.rfind('.', 0, code.index('('))
            if last_dot > 0:
                # Extract object and method parts
                object_part = code[:last_dot]
                method_start = last_dot + 1
                paren_pos = code.index('(', method_start)
                method_name = code[method_start:paren_pos]
                
                # Create attribute node representing the full method call
                children.append(MockNode(
                    kind='attribute',
                    text=f"{object_part}.{method_name}",
                    start_byte=0,
                    end_byte=paren_pos
                ))
                
                # Add arguments
                args_start = code.index('(')
                args_end = code.rindex(')')
                args_text = code[args_start:args_end + 1]
                inner_args = code[args_start + 1:args_end]
                
                children.append(MockNode(
                    kind='arguments',
                    text=args_text,
                    start_byte=args_start,
                    end_byte=args_end + 1,
                    children=self._parse_arguments_with_position(inner_args, args_start + 1, code)
                ))
                
                return children
        
        # Simple heuristic to find callee for regular function calls
        if '(' in code:
            callee_end = code.index('(')
            callee_text = code[:callee_end].strip()
            
            # Special handling for Java constructors
            if language == 'java' and callee_text.startswith('new '):
                # For Java constructors, keep the full "new ClassName" text
                callee_kind = 'object_creation_expression'
                # Don't remove 'new ' - keep full text for sink detection
            elif '.' in callee_text:
                callee_kind = 'member_expression' if language in ['javascript', 'typescript'] else 'attribute'
            else:
                callee_kind = 'identifier'
            
            children.append(MockNode(
                kind=callee_kind,
                text=callee_text,
                start_byte=0,
                end_byte=len(callee_text)
            ))
            
            # Add arguments node if present
            args_start = code.index('(')
            args_end = code.rindex(')')
            args_text = code[args_start:args_end + 1]
            inner_args = code[args_start + 1:args_end]
            
            children.append(MockNode(
                kind='arguments',
                text=args_text,
                start_byte=args_start,
                end_byte=args_end + 1,
                children=self._parse_arguments_with_position(inner_args, args_start + 1, code)
            ))
        
        return children
    
    def _parse_arguments_with_position(self, args_text: str, base_offset: int, full_code: str) -> list:
        """Parse argument text into mock nodes with proper positioning."""
        args_children = []
        
        # Create argument nodes based on content
        if args_text.strip():
            # Split on commas (simple heuristic)
            arg_parts = [part.strip() for part in args_text.split(',')]
            current_offset = 0
            
            for i, arg_part in enumerate(arg_parts):
                if not arg_part:
                    continue
                
                # Find the actual position in the arguments text
                arg_start_in_args = args_text.find(arg_part, current_offset)
                if arg_start_in_args == -1:
                    arg_start_in_args = current_offset
                
                # Calculate absolute position in full code
                arg_start_absolute = base_offset + arg_start_in_args
                
                # Determine argument type and extract proper text
                if arg_part.startswith(('"', "'", '`')):
                    # For string literals, extract the content without quotes
                    arg_kind = 'string'
                    if len(arg_part) >= 2 and arg_part[0] == arg_part[-1] and arg_part[0] in '"\'`':
                        string_content = arg_part[1:-1]  # Remove quotes
                        args_children.append(MockNode(
                            kind=arg_kind,
                            text=string_content,  # Just the content
                            start_byte=arg_start_absolute + 1,  # Start after opening quote
                            end_byte=arg_start_absolute + len(arg_part) - 1   # End before closing quote
                        ))
                        current_offset = arg_start_in_args + len(arg_part)
                        continue
                elif any(pattern in arg_part for pattern in ['+', '${', '#{', 'f"', "f'"]):
                    if '+' in arg_part:
                        arg_kind = 'binary_expression'
                    elif '${' in arg_part:
                        arg_kind = 'template_string'
                    elif '#{' in arg_part:
                        arg_kind = 'interpolated_string'
                    elif 'f"' in arg_part or "f'" in arg_part:
                        arg_kind = 'fstring'
                    else:
                        arg_kind = 'string'
                elif any(hint in arg_part.lower() for hint in ['path', 'name', 'file', 'param', 'req']):
                    arg_kind = 'identifier'
                else:
                    arg_kind = 'identifier'
                
                args_children.append(MockNode(
                    kind=arg_kind,
                    text=arg_part,
                    start_byte=arg_start_absolute,
                    end_byte=arg_start_absolute + len(arg_part)
                ))
                current_offset = arg_start_in_args + len(arg_part)
        
        return args_children
    

    
    def test_rule_metadata(self):
        """Test rule metadata is correct."""
        meta = self.rule.meta
        assert meta.id == "sec.path_traversal"
        assert meta.category == "sec"
        assert meta.tier == 0
        assert meta.priority == "P1"
        assert "python" in meta.langs
        assert "javascript" in meta.langs
        assert meta.autofix_safety == "suggest-only"
    
    def test_positive_cases_python(self):
        """Test Python path traversal detection."""
        code = 'open("uploads/" + name, "rb")'
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "path traversal" in findings[0].message.lower()
        assert findings[0].severity == "warn"
    
    def test_positive_cases_javascript(self):
        """Test JavaScript/TypeScript path traversal detection."""
        code = 'fs.readFileSync(`./uploads/${req.params.name}`)'
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
        assert "path traversal" in findings[0].message.lower()
    
    def test_positive_cases_typescript(self):
        """Test TypeScript specific patterns."""
        code = 'fs.promises.readFile("./uploads/" + filename)'
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
    
    def test_positive_cases_java(self):
        """Test Java path traversal detection."""
        code = 'new java.io.File("/var/data/" + filename)'
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
    
    def test_positive_cases_go(self):
        """Test Go path traversal detection."""
        code = 'os.ReadFile("uploads/" + name)'
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
    
    def test_positive_cases_ruby(self):
        """Test Ruby path traversal detection."""
        code = 'File.read("uploads/" + name)'
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
    
    def test_positive_cases_csharp(self):
        """Test C# path traversal detection."""
        code = 'File.ReadAllText(@"C:\\uploads\\" + userFile)'
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        assert len(findings) >= 1
    
    def test_traversal_literal_cases(self):
        """Test detection of literal traversal patterns."""
        # Dot-dot traversal
        code1 = 'fs.readFileSync("../secrets/config.json")'
        ctx1 = self._create_context(code1, "javascript")
        findings = list(self.rule.visit(ctx1))
        assert len(findings) >= 1
        
        # Absolute path
        code2 = 'open("/etc/passwd")'
        ctx2 = self._create_context(code2, "python")
        findings = list(self.rule.visit(ctx2))
        assert len(findings) >= 1
        
        # Windows absolute path
        code3 = 'File.ReadAllText("C:\\\\windows\\\\system32\\\\config\\\\sam")'
        ctx3 = self._create_context(code3, "csharp")
        findings = list(self.rule.visit(ctx3))
        assert len(findings) >= 1
    
    def test_negative_cases_with_guards(self):
        """Test that properly guarded cases don't trigger warnings."""
        # Python with normalization
        code1 = '''
        import pathlib
        full = pathlib.Path(base, name).resolve()
        if not str(full).startswith(str(pathlib.Path(base).resolve())):
            raise ValueError()
        full.open("rb")
        '''
        ctx1 = self._create_context(code1, "python")
        findings = list(self.rule.visit(ctx1))
        # Should not trigger because of guard patterns
        assert len(findings) == 0
        
        # JavaScript with path.resolve
        code2 = '''
        const path = require("path");
        const full = path.resolve(BASE, req.params.name);
        if (!full.startsWith(BASE)) throw new Error();
        fs.promises.readFile(full);
        '''
        ctx2 = self._create_context(code2, "javascript")
        findings = list(self.rule.visit(ctx2))
        assert len(findings) == 0
        
        # Go with filepath.Clean
        code3 = '''
        p := filepath.Clean(filepath.Join(base, name))
        if !strings.HasPrefix(p, base) { panic("bad") }
        os.Open(p)
        '''
        ctx3 = self._create_context(code3, "go")
        findings = list(self.rule.visit(ctx3))
        assert len(findings) == 0
    
    def test_negative_cases_static_paths(self):
        """Test that static, safe paths don't trigger warnings."""
        # Static string without traversal
        code1 = 'open("config.txt", "r")'
        ctx1 = self._create_context(code1, "python")
        findings = list(self.rule.visit(ctx1))
        assert len(findings) == 0
        
        # Safe relative path
        code2 = 'fs.readFileSync("./data/static.json")'
        ctx2 = self._create_context(code2, "javascript")
        findings = list(self.rule.visit(ctx2))
        assert len(findings) == 0
    
    def test_user_hint_detection(self):
        """Test detection of user-controlled variables."""
        user_vars = ['filename', 'path', 'user_input', 'req_params', 'request_body']
        
        for var in user_vars:
            code = f'open({var})'
            ctx = self._create_context(code, "python")
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect {var} as user-controlled"
    
    def test_sink_detection(self):
        """Test that the rule correctly identifies file operation sinks."""
        sinks_by_lang = {
            'python': ['open', 'os.open', 'Path.open', 'shutil.copy'],
            'javascript': ['fs.readFile', 'fs.writeFile', 'readFileSync'],
            'java': ['new File', 'Files.readAllBytes', 'Paths.get'],
            'go': ['os.Open', 'os.ReadFile', 'ioutil.WriteFile'],
            'ruby': ['File.open', 'File.read', 'FileUtils.cp'],
            'csharp': ['File.ReadAllText', 'Directory.GetFiles']
        }
        
        for lang, sinks in sinks_by_lang.items():
            for sink in sinks:
                assert self.rule._is_sink(lang, sink), f"Should detect {sink} as sink for {lang}"
    
    def test_comprehensive_positive_coverage(self):
        """Test comprehensive coverage of positive cases across languages."""
        positive_cases = [
            # Python
            ('python', 'open("uploads/" + name, "rb")', True),
            ('python', 'Path(base_dir + filename).open()', True),
            
            # JavaScript
            ('javascript', 'fs.readFileSync(`./uploads/${req.params.name}`)', True),
            ('javascript', 'fs.promises.writeFile("data/" + userFile, content)', True),
            
            # TypeScript (same patterns as JS)
            ('typescript', 'fs.readFile(path + filename, callback)', True),
            
            # Java
            ('java', 'new java.io.File("/var/data/" + filename)', True),
            ('java', 'Files.readAllBytes(Paths.get(baseDir + userPath))', True),
            
            # C#
            ('csharp', 'File.ReadAllText(@"C:\\uploads\\" + userFile)', True),
            ('csharp', 'Directory.GetFiles(rootPath + userDir)', True),
            
            # Go
            ('go', 'os.ReadFile("uploads/" + name)', True),
            ('go', 'ioutil.WriteFile(basePath + filename, data, 0644)', True),
            
            # Ruby
            ('ruby', 'File.read("uploads/" + name)', True),
            ('ruby', 'FileUtils.cp(srcPath + userFile, destPath)', True),
        ]
        
        total_violations = 0
        for lang, code, should_violate in positive_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            if should_violate:
                total_violations += len(findings)
                assert len(findings) > 0, f"Should detect violation in {lang}: {code}"
        
        # Should have detected violations in most positive cases
        assert total_violations >= 10, f"Expected at least 10 violations, got {total_violations}"
    
    def test_literal_traversal_patterns(self):
        """Test detection of various literal traversal patterns."""
        traversal_patterns = [
            "../config.json",
            "../../etc/passwd", 
            "/etc/shadow",
            "C:\\windows\\system32\\config\\sam",
            "~/sensitive_file.txt",
            "..\\windows\\system.ini"
        ]
        
        for pattern in traversal_patterns:
            code = f'open("{pattern}")'
            ctx = self._create_context(code, "python")
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Should detect traversal pattern: {pattern}"
    
    def test_guard_pattern_detection(self):
        """Test that normalization guards are properly detected."""
        guard_patterns = [
            "os.path.realpath(path)",
            "pathlib.Path(base, name).resolve()",
            "path.resolve(BASE, name)",
            "filepath.Clean(filepath.Join(base, name))",
            "File.expand_path(File.join(base, name))",
            "Path.GetFullPath(Path.Combine(baseDir, name))"
        ]
        
        for guard in guard_patterns:
            # Create context with guard pattern
            code = f'{guard}; open(result)'
            ctx = self._create_context(code, "python")
            
            # The guard detection should work
            call_node = ctx.tree._nodes[0]
            has_guard = self.rule._has_normalization_guard(call_node, None, "python", ctx)
            assert has_guard, f"Should detect guard pattern: {guard}"

