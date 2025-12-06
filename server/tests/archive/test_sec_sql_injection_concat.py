"""Test suite for sec.sql_injection_concat rule."""

import pytest
from engine.types import RuleContext
from rules.sec_sql_injection_concat import SecSqlInjectionConcatRule


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
    
    def node_span(self, node):
        """Return span for node."""
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 10))


class TestSecSqlInjectionConcatRule:
    """Test SQL injection detection via concatenation."""

    def setup_method(self):
        self.rule = SecSqlInjectionConcatRule()

    def test_python_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in Python."""
        # String concatenation
        code = '''cursor.execute("SELECT * FROM users WHERE name = '" + name + "'")'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message
        assert findings[0].severity == "error"

    def test_python_f_string_detection(self):
        """Test detection of f-string SQL in Python."""
        code = '''cursor.execute(f"DELETE FROM posts WHERE id = {post_id}")'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message

    def test_javascript_template_literal_detection(self):
        """Test detection of template literal SQL in JavaScript."""
        code = '''client.query(`SELECT * FROM items WHERE q = '${q}'`)'''
        ctx = self._create_context(code, "javascript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message

    def test_typescript_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in TypeScript."""
        code = '''
        const sql = "UPDATE t SET x=" + x + " WHERE id=" + id;
        db.query(sql);
        '''
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        # Should find at least one finding (the db.query call)
        assert len(findings) >= 1
        assert "SQL injection" in findings[0].message

    def test_java_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in Java."""
        code = '''
        Statement s = conn.createStatement();
        s.executeQuery("SELECT * FROM t WHERE id=" + id);
        '''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert "SQL injection" in findings[0].message

    def test_csharp_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in C#."""
        code = '''
        var cmd = new SqlCommand("DELETE FROM T WHERE id=" + id, conn);
        cmd.ExecuteNonQuery();
        '''
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert "SQL injection" in findings[0].message

    def test_ruby_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in Ruby."""
        code = '''User.where("email = '#{email}'")'''
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message

    def test_go_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in Go."""
        code = '''db.Query(fmt.Sprintf("SELECT * FROM t WHERE name = '%s'", name))'''
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message

    def test_php_dynamic_sql_detection(self):
        """Test detection of dynamic SQL in PHP."""
        code = '''mysqli_query($conn, "SELECT * FROM users WHERE u='$u' AND p='$p'");'''
        ctx = self._create_context(code, "php")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 1
        assert "SQL injection" in findings[0].message

    def test_sql_dynamic_execution(self):
        """Test detection of dynamic SQL execution in SQL."""
        code = '''
        DECLARE @sql NVARCHAR(MAX) = 'SELECT * FROM t WHERE n=' + CAST(@n AS NVARCHAR(10));
        EXEC(@sql);
        '''
        ctx = self._create_context(code, "sql")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) >= 1
        assert "SQL injection" in findings[0].message

    def test_python_safe_parameterized_query(self):
        """Test that parameterized queries are not flagged in Python."""
        code = '''cursor.execute("SELECT * FROM users WHERE name = %s", (name,))'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag parameterized queries
        assert len(findings) == 0

    def test_python_named_parameters(self):
        """Test that named parameters are not flagged in Python."""
        code = '''cursor.execute("UPDATE t SET x = :x WHERE id = :id", {"x": x, "id": id})'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_typescript_parameterized_query(self):
        """Test that parameterized queries are not flagged in TypeScript."""
        code = '''await client.query("SELECT * FROM items WHERE q = $1", [q]);'''
        ctx = self._create_context(code, "typescript")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_java_prepared_statement(self):
        """Test that prepared statements are not flagged in Java."""
        code = '''
        PreparedStatement ps = conn.prepareStatement("SELECT * FROM t WHERE id=?");
        ps.setInt(1, id);
        ps.executeQuery();
        '''
        ctx = self._create_context(code, "java")
        findings = list(self.rule.visit(ctx))
        
        # The prepareStatement call with static SQL should not be flagged
        assert len(findings) == 0

    def test_csharp_parameterized_query(self):
        """Test that parameterized queries are not flagged in C#."""
        code = '''
        var cmd = new SqlCommand("SELECT * FROM T WHERE id=@id", conn);
        cmd.Parameters.AddWithValue("@id", id);
        cmd.ExecuteReader();
        '''
        ctx = self._create_context(code, "csharp")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_ruby_safe_activerecord(self):
        """Test that safe ActiveRecord queries are not flagged."""
        code = '''User.where("email = ?", email)'''
        ctx = self._create_context(code, "ruby")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_go_parameterized_query(self):
        """Test that parameterized queries are not flagged in Go."""
        code = '''db.Query("SELECT * FROM t WHERE name = $1", name)'''
        ctx = self._create_context(code, "go")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_php_prepared_statement(self):
        """Test that prepared statements are not flagged in PHP."""
        code = '''
        $stmt = $pdo->prepare("INSERT INTO t (a) VALUES (:a)");
        $stmt->execute([":a" => $a]);
        '''
        ctx = self._create_context(code, "php")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_identifier_built_then_executed(self):
        """Test detection when SQL is built in variable then executed."""
        code = '''
        sql = "SELECT * FROM t WHERE id=" + str(i);
        cursor.execute(sql);
        '''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should detect the dynamic SQL in the execute call
        assert len(findings) >= 1
        assert "SQL injection" in findings[0].message

    def test_non_sql_strings_ignored(self):
        """Test that non-SQL strings are not flagged."""
        code = '''
        print("Hello " + name)
        log.info(f"Processing user {user_id}")
        '''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Should not flag non-SQL strings
        assert len(findings) == 0

    def test_static_sql_without_variables(self):
        """Test that static SQL without variables is not flagged."""
        code = '''cursor.execute("SELECT * FROM users")'''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        # Static SQL without concatenation should be safe
        assert len(findings) == 0

    def test_non_sql_method_calls_ignored(self):
        """Test that non-SQL method calls are ignored."""
        code = '''
        result = process("data " + input)
        logger.info(f"Status: {status}")
        '''
        ctx = self._create_context(code, "python")
        findings = list(self.rule.visit(ctx))
        
        assert len(findings) == 0

    def test_multiple_languages_sql_detection(self):
        """Test SQL detection across multiple languages."""
        test_cases = [
            ("python", '''cursor.executemany("INSERT INTO t VALUES (" + values + ")")'''),
            ("javascript", '''pool.query("DELETE FROM items WHERE id=" + id)'''),
            ("java", '''stmt.executeUpdate("UPDATE users SET name='" + name + "'")'''),
            ("csharp", '''cmd.ExecuteScalar("SELECT COUNT(*) FROM t WHERE x=" + x)'''),
            ("ruby", '''conn.execute("select * from x where q=" + q.to_s)'''),
            ("go", '''tx.QueryContext(ctx, "SELECT * FROM t WHERE id=" + strconv.Itoa(id))'''),
            ("php", '''$pdo->exec("DELETE FROM logs WHERE date < '$date'")'''),
        ]
        
        for lang, code in test_cases:
            ctx = self._create_context(code, lang)
            findings = list(self.rule.visit(ctx))
            assert len(findings) >= 1, f"Failed to detect SQL injection in {lang}: {code}"
            assert "SQL injection" in findings[0].message

    def test_rule_metadata(self):
        """Test rule metadata is correctly configured."""
        assert self.rule.meta.id == "sec.sql_injection_concat"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P0"
        assert self.rule.meta.autofix_safety == "suggest-only"
        
        # Check all required languages are supported
        expected_langs = {"python", "javascript", "typescript", "java", "csharp", "ruby", "go", "php", "sql"}
        assert set(self.rule.meta.langs) == expected_langs

    def _create_context(self, code: str, lang: str = "python") -> RuleContext:
        """Create a mock context for testing."""
        # Create mock nodes based on the code structure
        nodes = self._parse_code_structure(code, lang)
        
        # Create a root node containing all parsed nodes
        root_node = MockNode(
            kind='source_file',
            text=code,
            start_byte=0,
            end_byte=len(code),
            children=nodes
        )
        
        # Create mock adapter
        class MockAdapter:
            def language_id(self):
                return lang
        
        syntax_tree = MockSyntax(root_node)
        return RuleContext(
            file_path=f"test.{lang}",
            text=code,
            tree=syntax_tree,
            adapter=MockAdapter(),
            config={},
            scopes=None,
            project_graph=None,
        )

    def _parse_code_structure(self, code: str, lang: str):
        """Parse code structure to create realistic mock nodes."""
        nodes = []
        
        # Simple heuristic parsing for test purposes
        import re
        
        # Find function calls with more specific patterns
        call_patterns = [
            r'(\w+(?:\.\w+)*)\s*\(\s*((?:[^()]|\([^()]*\))*)\s*\)',  # method.call(args) with nested parens
        ]
        
        for pattern in call_patterns:
            for match in re.finditer(pattern, code):
                start, end = match.span()
                func_name = match.group(1)
                args_text = match.group(2)
                
                # Create argument nodes
                arg_nodes = []
                if args_text.strip():
                    # Split arguments on commas (basic splitting)
                    # This is a simplified approach - real parsing would handle nested commas
                    raw_args = [arg.strip() for arg in args_text.split(',')]
                    arg_start = start + code[start:].find('(') + 1
                    
                    for arg_text in raw_args:
                        if arg_text:
                            arg_node = self._create_arg_node(arg_text, arg_start, lang)
                            if arg_node:
                                arg_nodes.append(arg_node)
                            arg_start += len(arg_text) + 1  # +1 for comma
                
                # Create function call node
                call_node = MockNode(
                    kind='call_expression',
                    text=match.group(0),
                    start_byte=start,
                    end_byte=end,
                    children=arg_nodes,
                    function=MockNode(kind='identifier', text=func_name)
                )
                
                # Set up arguments attribute
                if arg_nodes:
                    call_node.arguments = MockNode(
                        kind='argument_list',
                        children=arg_nodes
                    )
                
                nodes.append(call_node)
        
        return nodes

    def _create_arg_node(self, arg_text: str, start_byte: int, lang: str):
        """Create an argument node based on the argument text."""
        arg_text = arg_text.strip()
        if not arg_text:
            return None
        
        # Handle complex expressions more carefully
        
        # Binary expressions (concatenation) - most important for SQL injection
        if '+' in arg_text and ('"' in arg_text or "'" in arg_text or '`' in arg_text):
            return MockNode(
                kind='binary_expression',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text),
                operator='+'
            )
            
        # Template literals (JavaScript/TypeScript)
        elif arg_text.startswith('`') and arg_text.endswith('`'):
            return MockNode(
                kind='template_string',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text)
            )
            
        # F-strings (Python)
        elif arg_text.startswith('f"') or arg_text.startswith("f'"):
            return MockNode(
                kind='f_string',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text)
            )
            
        # String literals with interpolation (Ruby, PHP)
        elif (('"' in arg_text and '#{' in arg_text) or  # Ruby interpolation
              ('"' in arg_text and '$' in arg_text and lang == 'php' and 
               (arg_text.startswith('"') or arg_text.startswith("'")))):  # PHP interpolation in strings only
            return MockNode(
                kind='interpolated_string',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text)
            )
            
        # Format calls (sprintf, String.format, etc.)
        elif any(fmt_call in arg_text for fmt_call in ['format(', 'sprintf(', 'fmt.Sprintf(', 'String.format(']):
            return MockNode(
                kind='call_expression',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text),
                function=MockNode(kind='identifier', text='format')
            )
            
        # Regular string literals
        elif ((arg_text.startswith('"') and arg_text.endswith('"')) or 
              (arg_text.startswith("'") and arg_text.endswith("'"))):
            return MockNode(
                kind='string_literal',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text)
            )
            
        # Variables/identifiers
        else:
            return MockNode(
                kind='identifier',
                text=arg_text,
                start_byte=start_byte,
                end_byte=start_byte + len(arg_text)
            )


if __name__ == "__main__":
    pytest.main([__file__])

