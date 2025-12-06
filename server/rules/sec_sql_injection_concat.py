"""Security rule: Detect SQL injection via string concatenation/interpolation.

Flags SQL built via string concatenation/interpolation with variables and then executed.
Recommends parameterized queries/prepared statements with separate bindings.
"""

import re
from typing import Iterator
from engine.types import RuleMeta, Rule, RuleContext, Finding, Requires


class SecSqlInjectionConcatRule:
    """Detect SQL injection vulnerabilities from string concatenation."""
    
    meta = RuleMeta(
        id="sec.sql_injection_concat",
        category="sec",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detect SQL injection via string concatenation/interpolation",
        langs=["python", "javascript", "typescript", "java", "csharp", "ruby", "go", "php", "sql"],
    )
    requires = Requires(syntax=True)

    # SQL keywords that indicate SQL operations
    SQL_KEYWORDS = {
        "select", "update", "delete", "insert", "where", "from", "join", "into", 
        "values", "limit", "order", "group", "exec", "execute", "alter", "create",
        "drop", "truncate", "merge", "union", "having"
    }
    
    # SQL execution methods by language
    SINKS = {
        "python": {
            "execute", "executemany", "executescript",
            # SQLAlchemy
            "exec_driver_sql",
            # Django
            "raw", "extra",
        },
        "javascript": {
            "query", "run", "exec",
            # Sequelize
            # MongoDB (though NoSQL, similar concerns)
            "find", "findOne", "aggregate",
        },
        "typescript": {
            "query", "run", "exec",
            # TypeORM
            "createQueryBuilder",
        },
        "java": {
            "executeQuery", "executeUpdate", "executeLargeUpdate",
            "executeBatch", "executeLargeBatch",
            # JDBC
            "prepareStatement", "createStatement",
        },
        "csharp": {
            "ExecuteReader", "ExecuteScalar", "ExecuteNonQuery", 
            "ExecuteReaderAsync", "ExecuteScalarAsync", "ExecuteNonQueryAsync",
            # Entity Framework
            "FromSqlRaw", "ExecuteSqlRaw",
        },
        "ruby": {
            "exec", "query",
            # ActiveRecord
            "find_by_sql", "execute_query",
            "select_all", "select_one", "select_value",
        },
        "go": {
            "Query", "QueryContext", "QueryRow", "QueryRowContext",
            "Exec", "ExecContext", "Prepare", "PrepareContext",
        },
        "php": {
            "mysqli_query", "mysql_query", "query", "exec", "prepare",
            # PDO
        },
        "sql": {
            "EXEC", "EXECUTE", "sp_executesql", "EXEC_IMMEDIATE",
            "EXECUTE_IMMEDIATE",
        },
    }
    
    # ORM methods that don't take raw SQL (false positive prevention)
    ORM_SAFE_METHODS = {
        "python": {"delete", "add", "commit", "refresh", "get", "merge", "expunge", "close", 
                   "select", "insert", "update", "exec", "execute"},  # SQLModel/SQLAlchemy ORM functions
        "javascript": {"save", "remove", "create", "update", "delete", "findOne", "findMany",
                       "queryparse", "querystring"},  # URL query string parsing, not SQL
        "typescript": {"save", "remove", "create", "update", "delete", "findOne", "findMany",
                       "queryparse", "querystring"},  # URL query string parsing, not SQL
        "java": {"save", "delete", "persist", "merge", "find", "getReference"},
        "csharp": {"Add", "Remove", "Update", "Find", "SaveChanges", "SaveChangesAsync"},
        "ruby": {"save", "destroy", "create", "update", "delete"},
    }
    
    # ORM/Query builder patterns that use method chaining (safe SQL construction)
    ORM_CHAIN_PATTERNS = {
        "python": {".where(", ".filter(", ".order_by(", ".group_by(", ".join(", ".select_from("},
        "javascript": {".where(", ".orderBy(", ".groupBy(", ".leftJoin(", ".innerJoin("},
        "typescript": {".where(", ".orderBy(", ".groupBy(", ".leftJoin(", ".innerJoin("},
    }
    
    # SQL constructor classes/methods that take SQL as first argument
    SQL_CONSTRUCTORS = {
        "java": {"PreparedStatement", "Statement", "CallableStatement"},
        "csharp": {"SqlCommand", "OleDbCommand", "OdbcCommand", "SqlCommandBuilder"},
        "python": {"cursor", "connection"},
        "javascript": {"Query", "QueryBuilder"},
        "typescript": {"Query", "QueryBuilder"},
        "ruby": {},  # ActiveRecord methods are already in SINKS
        "go": {},  # Usually direct function calls
        "php": {"mysqli_stmt", "PDOStatement"},
        "sql": {},
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for SQL injection via string concatenation."""
        if not ctx.syntax:
            return
            
        # Get language from adapter
        language = ctx.language
        if callable(language):
            language = language()
        if language not in self.SINKS:
            return
            
        # Walk through all nodes to find function calls
        for node in ctx.walk_nodes():
            # Check both SQL execution calls and SQL constructors
            if self._is_sql_call(node, language) or self._is_sql_constructor(node, language):
                sql_arg = self._get_first_sql_arg(node)
                if sql_arg and self._is_dynamic_sql(sql_arg, language, ctx):
                    start_pos, end_pos = ctx.node_span(sql_arg)
                    yield Finding(
                        rule=self.meta.id,
                        message="SQL query built from string concatenation—use parameterized queries to prevent injection attacks.",
                        file=ctx.file_path,
                        start_byte=start_pos,
                        end_byte=end_pos,
                        severity="error"
                    )

    def _is_sql_call(self, node, language: str) -> bool:
        """Check if node is a call to a SQL execution method."""
        node_type = getattr(node, 'type', '')
        if node_type not in {'call_expression', 'call', 'function_call', 'method_call', 'method_invocation', 'invocation_expression'}:
            return False
            
        # Get the function/method name being called
        callee = self._get_callee_name(node)
        if not callee:
            return False
        
        # Check if this is an ORM safe method (not raw SQL)
        # e.g., session.delete(model), session.add(model), Model.objects.filter()
        safe_methods = self.ORM_SAFE_METHODS.get(language, set())
        callee_lower = callee.lower()
        method_name = callee.split('.')[-1] if '.' in callee else callee
        method_name_lower = method_name.lower()
        
        # Skip if the method is a known safe ORM method
        if method_name_lower in {m.lower() for m in safe_methods}:
            return False
            
        # Also skip common ORM patterns
        # session.delete(), session.add(), session.commit() etc.
        orm_patterns = [
            'session.', 'db.session.', 'objects.', '.objects',
            'repository.', 'dao.', 'entity.', 'model.',
        ]
        for pattern in orm_patterns:
            if pattern in callee_lower and method_name_lower in {m.lower() for m in safe_methods}:
                return False
            
        # Check if it matches any SQL sink for this language
        sinks = self.SINKS.get(language, set())
        
        # For most languages, check if the method name matches or ends with a sink
        for sink in sinks:
            if (callee == sink or 
                callee.endswith(f".{sink}") or 
                callee.endswith(f"->{sink}") or  # C-style pointer access
                (language == "php" and sink in callee.lower())):
                return True
                
        return False

    def _is_sql_constructor(self, node, language: str) -> bool:
        """Check if node is a call to a SQL constructor/builder."""
        node_type = getattr(node, 'type', '')
        if node_type not in {'call_expression', 'call', 'function_call', 'method_call', 'method_invocation', 'object_creation_expression', 'new_expression'}:
            return False
            
        # Get the constructor/class name being called
        callee = self._get_callee_name(node)
        if not callee:
            return False
            
        # Check if it matches any SQL constructor for this language
        constructors = self.SQL_CONSTRUCTORS.get(language, set())
        
        # For constructors, look for the class name
        for constructor in constructors:
            if (constructor in callee or 
                callee.endswith(f".{constructor}") or
                callee.startswith(f"new {constructor}") or
                constructor.lower() in callee.lower()):
                return True
                
        return False

    def _get_callee_name(self, node) -> str:
        """Extract the function/method name from a call node."""
        node_type = getattr(node, 'type', '')
        
        # Try to get the function name from different node structures
        if hasattr(node, 'function'):
            func_node = node.function
            return self._get_node_text(func_node)
        elif hasattr(node, 'name'):
            return self._get_node_text(node.name)
        elif hasattr(node, 'children') and node.children:
            # For Java method_invocation, structure is: object.method(args)
            # We need to find the method name identifier before argument_list
            if node_type == 'method_invocation':
                # Find method name - it's the identifier right before the argument_list
                for i, child in enumerate(node.children):
                    child_type = getattr(child, 'type', '')
                    if child_type == 'argument_list' and i > 0:
                        # Get the previous non-dot identifier
                        for j in range(i - 1, -1, -1):
                            prev_child = node.children[j]
                            prev_type = getattr(prev_child, 'type', '')
                            if prev_type == 'identifier':
                                return self._get_node_text(prev_child)
                # If no argument_list, get last identifier
                for child in reversed(node.children):
                    child_type = getattr(child, 'type', '')
                    if child_type == 'identifier':
                        return self._get_node_text(child)
            
            # For C# object_creation_expression, structure is: new TypeName(args)
            # Find the identifier after 'new' keyword
            if node_type == 'object_creation_expression':
                for child in node.children:
                    child_type = getattr(child, 'type', '')
                    if child_type == 'identifier':
                        return self._get_node_text(child)
                    # Also handle generic_name for generic types
                    if child_type == 'generic_name':
                        return self._get_node_text(child)
            
            # For other languages, first child is often the function name
            first_child = node.children[0]
            return self._get_node_text(first_child)
        
        return ""

    def _get_first_sql_arg(self, call_node):
        """Get the SQL argument from a function call."""
        # Try different ways to access arguments
        args = None
        if hasattr(call_node, 'arguments') and call_node.arguments:
            if hasattr(call_node.arguments, 'children'):
                args = call_node.arguments.children
            else:
                args = call_node.arguments
        else:
            # Alternative: look for argument list in children
            for child in getattr(call_node, 'children', []):
                child_type = getattr(child, 'type', '')
                if child_type in {'argument_list', 'arguments'}:
                    if hasattr(child, 'children'):
                        args = child.children
                        break
        
        if not args:
            return None
            
        # Filter out punctuation/separators to get actual arguments
        actual_args = []
        for arg in args:
            arg_type = getattr(arg, 'type', '')
            if arg_type not in {'(', ')', ',', 'comma', 'punctuation', ''}:
                actual_args.append(arg)
        
        if not actual_args:
            return None
            
        # Get function name to determine which argument contains SQL
        func_name = self._get_callee_name(call_node)
        
        # Functions where SQL is the second argument (index 1)
        second_arg_functions = {
            'mysqli_query', 'mysql_query',  # PHP: mysqli_query($conn, $sql)
            'QueryContext', 'QueryRowContext', 'ExecContext', 'PrepareContext',  # Go: QueryContext(ctx, sql)
        }
        
        if any(fn in func_name for fn in second_arg_functions):
            return actual_args[1] if len(actual_args) > 1 else None
        
        # For most functions, SQL is the first argument
        return actual_args[0]

    def _is_dynamic_sql(self, node, language: str, ctx) -> bool:
        """Check if a node represents dynamically constructed SQL."""
        if not node:
            return False
        
        node_type = getattr(node, 'type', '')
        
        # Unwrap C# argument wrapper
        if node_type == 'argument' and hasattr(node, 'children') and node.children:
            for child in node.children:
                child_type = getattr(child, 'type', '')
                if child_type not in {'(', ')', ',', 'comma', 'punctuation', ''}:
                    node = child
                    node_type = getattr(node, 'type', '')
                    break
        
        node_text = self._get_node_text(node)
        
        # Skip CSS/DOM selectors (not SQL)
        # e.g., [aria-controls="..."], querySelector, etc.
        if self._looks_like_css_selector(node_text):
            return False
        
        # Check if this is part of an ORM query builder chain (safe)
        # e.g., delete(Item).where(col(Item.owner_id) == user_id)
        chain_patterns = self.ORM_CHAIN_PATTERNS.get(language, set())
        if chain_patterns:
            # Look at parent context to see if this is a query builder chain
            parent = getattr(node, 'parent', None)
            while parent:
                parent_text = self._get_node_text(parent)
                if parent_text and any(pattern in parent_text for pattern in chain_patterns):
                    return False  # This is ORM query builder syntax, not raw SQL
                parent = getattr(parent, 'parent', None)
                # Limit depth to avoid performance issues
                if parent_text and len(parent_text) > 500:
                    break
        
        # 1) Direct string concatenation with +
        if node_type in {'binary_expression', 'binary_operator', 'concatenated_string'}:
            if self._looks_like_sql(node_text):
                return True
                
        # 2) Template strings/interpolation
        if node_type in {'template_string', 'template_literal', 'interpolated_string', 
                        'f_string', 'formatted_string', 'string_interpolation'}:
            if self._looks_like_sql(node_text) and self._has_interpolation(node_text, language):
                return True
                
        # 3) Format/sprintf-style calls
        if node_type in {'call_expression', 'call', 'function_call'}:
            callee = self._get_callee_name(node)
            if any(fmt_method in callee.lower() for fmt_method in 
                   ['format', 'sprintf', 'string.format', 'fmt.sprintf', 'printf']):
                if self._looks_like_sql(node_text):
                    return True
                    
        # 4) Variable identifier that might be dynamically built
        if node_type in {'identifier', 'name', 'variable'}:
            # For simple heuristic, check if it's a variable with SQL-like name
            var_name = node_text.lower()
            
            # Skip URL query string variables (not SQL)
            # e.g., querystring, queryparse, query_string, query_params, routerQuery
            url_query_patterns = ['querystring', 'queryparse', 'query_string', 'query_params', 
                                   'query_param', 'urlquery', 'search_params', 'searchparams',
                                   'routerquery', 'router_query', 'queryparams', 'searchquery',
                                   'urlparams', 'url_params', 'getquery', 'validatedquery',
                                   'queryschema', 'query_schema',  # Zod/validation schemas
                                   'zodquery', 'parsequery', 'parsedquery']
            if any(pattern in var_name for pattern in url_query_patterns):
                return False
            
            if any(sql_word in var_name for sql_word in ['sql', 'query', 'statement']):
                return True  # Assume variables with SQL-like names are dynamic
                
        # 5) String literal that looks like SQL and might be in dynamic context
        if node_type in {'string_literal', 'string', 'quoted_string', 'string_content'}:
            if self._looks_like_sql(node_text):
                # Check if it has interpolation markers or is in dynamic context
                if (self._has_interpolation(node_text, language) or 
                    not self._has_placeholders(node_text)):
                    return self._is_likely_dynamic_context(node, ctx)
                    
        return False

    def _looks_like_sql(self, text: str) -> bool:
        """Check if text looks like SQL based on keywords."""
        if not text:
            return False
            
        text_lower = text.lower()
        
        # Must contain at least one SQL keyword
        has_sql_keyword = any(keyword in text_lower for keyword in self.SQL_KEYWORDS)
        
        # Also consider SQL operators and patterns that indicate SQL fragments
        sql_patterns = [
            '=',  # equality operator
            '!=', '<>', # not equal
            '<', '>', '<=', '>=',  # comparison operators
            'like', 'ilike',  # pattern matching
            'in (', 'not in',  # list membership
            'is null', 'is not null',  # null checks
            'and ', 'or ',  # logical operators
            'between',  # range operator
        ]
        
        has_sql_pattern = any(pattern in text_lower for pattern in sql_patterns)
        
        # For very short strings that look like SQL conditions, be more permissive
        if len(text.strip()) > 5 and ('=' in text or 'like' in text_lower):
            return True
            
        return has_sql_keyword or has_sql_pattern

    def _has_interpolation(self, text: str, language: str) -> bool:
        """Check if text has variable interpolation."""
        if not text:
            return False
            
        # JavaScript/TypeScript template literals
        if language in {'javascript', 'typescript'} and '${' in text:
            return True
            
        # Python f-strings
        if language == 'python' and ('{' in text and '}' in text):
            return True
            
        # Ruby interpolation
        if language == 'ruby' and '#{' in text:
            return True
            
        # PHP variable interpolation
        if language == 'php' and '$' in text:
            return True
            
        # General format placeholders
        if '%s' in text or '%d' in text or '%' in text:
            return True
            
        return False

    def _has_placeholders(self, text: str) -> bool:
        """Check if SQL string has proper placeholders."""
        if not text:
            return False
            
        # Common SQL placeholders
        if '?' in text:  # JDBC, PDO style
            return True
        if re.search(r'\$\d+', text):  # PostgreSQL style ($1, $2, etc.)
            return True
        if re.search(r':\w+', text):  # Named parameters (:name, :id, etc.)
            return True
        if re.search(r'@\w+', text):  # SQL Server style (@param)
            return True
        if re.search(r'%\(\w+\)s', text):  # Python pyformat style
            return True
            
        return False

    def _is_likely_dynamic_context(self, node, syntax_tree) -> bool:
        """Check if a static SQL string is in a dynamic context."""
        # Look at parent nodes to see if this string is being concatenated
        current = node
        for _ in range(3):  # Check up to 3 levels up
            if hasattr(current, 'parent') and current.parent:
                current = current.parent
                parent_kind = getattr(current, 'kind', '')
                
                # If parent is concatenation, this is dynamic
                if parent_kind in {'binary_expression', 'binary_operator'} and \
                   getattr(current, 'operator', '') in {'+', '||'}:
                    return True
                    
                # If parent is format call, this is dynamic
                if parent_kind in {'call_expression', 'function_call'}:
                    callee = self._get_callee_name(current)
                    if any(fmt_method in callee.lower() for fmt_method in 
                           ['format', 'sprintf', 'string.format', 'fmt.sprintf']):
                        return True
            else:
                break
                
        return False

    def _get_node_text(self, node) -> str:
        """Get text content of a node."""
        if not node:
            return ""
            
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
            
        return ""

    def _looks_like_css_selector(self, text: str) -> bool:
        """Check if text looks like a CSS/DOM selector, not SQL."""
        if not text:
            return False
        
        # CSS attribute selectors: [attr="value"], [data-*], [aria-*], [href*=]
        css_patterns = [
            '[aria-', '[data-', '[role=', '[class=', '[id=',
            '[href', '[src', '[type=', '[name=',  # More attribute selectors
            'queryselector', 'queryselectorall', 'getelementsby',
            '.classname', '#id-',
            'a[', 'button[', 'input[', 'div[',  # Common element selectors
        ]
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in css_patterns)


# Export rule for registration
RULES = [SecSqlInjectionConcatRule()]


