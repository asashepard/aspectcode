# server/rules/errors_partial_function_implementation.py
"""
Rule to detect functions/methods with placeholder implementations.

This rule analyzes functions across multiple languages for:
- Python: raise NotImplementedError
- TypeScript/JavaScript: throw new Error("not implemented")
- Go: panic("not implemented")
- Java: throw new UnsupportedOperationException()
- C#: throw new NotImplementedException()
- C/C++: abort(), assert(0), __builtin_trap()
- Ruby: raise NotImplementedError
- Rust: unimplemented!(), todo!()
- Swift: fatalError("unimplemented")

When functions contain only placeholder statements, it suggests adding proper
implementation or linking to documentation/tickets.
"""

from typing import Set, Optional, List
from engine.types import RuleContext, Finding, RuleMeta, Requires

class ErrorsPartialFunctionImplementationRule:
    """Rule to detect functions/methods with placeholder implementations."""
    
    meta = RuleMeta(
        id="errors.partial_function_implementation",
        category="errors",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detects functions/methods whose body contains only placeholder implementations.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )
    
    requires = Requires(syntax=True)

    # Language-specific function-like node types
    FUNCTION_LIKE_TYPES = {
        "python": {"function_definition", "async_function_definition"},
        "typescript": {"function_declaration", "method_definition", "arrow_function"},
        "javascript": {"function_declaration", "method_definition", "arrow_function"},
        "go": {"function_declaration", "method_declaration"},
        "java": {"method_declaration", "constructor_declaration"},
        "cpp": {"function_definition", "method_definition"},
        "c": {"function_definition"},
        "csharp": {"method_declaration", "constructor_declaration"},
        "ruby": {"method", "def"},
        "rust": {"function_item"},
        "swift": {"function_declaration"},
    }

    # Language-specific placeholder statement patterns
    PLACEHOLDER_PATTERNS = {
        "python": {
            "raise_statement": ["NotImplementedError", "NotImplemented"],
        },
        "typescript": {
            "throw_statement": ["Error", "not implemented", "unimplemented"],
        },
        "javascript": {
            "throw_statement": ["Error", "not implemented", "unimplemented"],
        },
        "go": {
            "call_expression": ["panic"],
            "expression_statement": ["panic"],
        },
        "java": {
            "throw_statement": ["UnsupportedOperationException", "NotImplementedException"],
        },
        "cpp": {
            "expression_statement": ["abort", "assert", "__builtin_trap"],
            "call_expression": ["abort", "assert", "__builtin_trap"],
        },
        "c": {
            "expression_statement": ["abort", "assert", "__builtin_trap"],
            "call_expression": ["abort", "assert", "__builtin_trap"],
        },
        "csharp": {
            "throw_statement": ["NotImplementedException", "NotSupportedException"],
        },
        "ruby": {
            "raise_statement": ["NotImplementedError"],
            "command": ["raise"],
        },
        "rust": {
            "macro_invocation": ["unimplemented", "todo", "panic"],
        },
        "swift": {
            "call_expression": ["fatalError"],
        },
    }

    def visit(self, ctx: RuleContext):
        """Visit file and check for functions with placeholder implementations."""
        language = ctx.adapter.language_id
        
        # Skip unsupported languages
        if not self._matches_language(ctx, self.meta.langs):
            return

        # Get function types for this language
        function_types = self.FUNCTION_LIKE_TYPES.get(language, set())
        if not function_types:
            return

        # Walk the syntax tree looking for function definitions
        for node in ctx.walk_nodes(ctx.tree):
            if not hasattr(node, 'type'):
                continue
                
            node_type = node.type
            if node_type in function_types:
                # Check if this function has only placeholder implementation
                placeholder_stmt = self._find_sole_placeholder(ctx, node, language)
                if placeholder_stmt:
                    finding = self._create_finding(ctx, node, placeholder_stmt, language)
                    if finding:
                        yield finding

    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        if not tree or not hasattr(tree, 'root_node'):
            return

        def walk_recursive(node):
            yield node
            if hasattr(node, 'children'):
                children = getattr(node, 'children', [])
                if children:
                    try:
                        for child in children:
                            yield from walk_recursive(child)
                    except (TypeError, AttributeError):
                        # Handle mock objects or tree-sitter iteration issues
                        pass

        yield from walk_recursive(tree.root_node)

    def _matches_language(self, ctx: RuleContext, supported_langs: List[str]) -> bool:
        """Check if the current language is supported."""
        return ctx.adapter.language_id in supported_langs

    def _find_sole_placeholder(self, ctx: RuleContext, function_node, language: str) -> Optional:
        """Find if the function has exactly one statement that is a placeholder."""
        # Find function body
        body_node = self._find_function_body(function_node, language)
        if not body_node:
            return None

        # Get non-comment, non-whitespace statements from body
        statements = self._extract_body_statements(body_node, language)
        
        # Must have exactly one statement
        if len(statements) != 1:
            return None

        statement = statements[0]
        
        # Check if this single statement is a placeholder
        if self._is_placeholder_statement(statement, language, ctx.text):
            return statement

        return None

    def _find_function_body(self, function_node, language: str):
        """Find the body node of a function."""
        # Common body node types across languages
        body_types = {
            "block", "body", "compound_statement", "block_statement", 
            "function_body", "method_body", "suite", "statement_block"
        }
        
        for child in self._get_children(function_node):
            if hasattr(child, 'type') and child.type in body_types:
                return child
                
        # For some languages, the body might be the function node itself
        return function_node

    def _extract_body_statements(self, body_node, language: str) -> List:
        """Extract non-trivial statements from function body."""
        if not body_node:
            return []

        statements = []
        for child in self._get_children(body_node):
            if not hasattr(child, 'type'):
                continue
                
            child_type = child.type
            
            # Skip comments, whitespace, and other non-statement nodes
            if child_type in {"comment", "line_comment", "block_comment", "whitespace", 
                             "newline", ";", "{", "}", "indent", "dedent"}:
                continue
                
            # Include actual statements
            if self._is_statement_node(child_type, language):
                statements.append(child)

        return statements

    def _is_statement_node(self, node_type: str, language: str) -> bool:
        """Check if a node type represents a statement."""
        statement_types = {
            "expression_statement", "return_statement", "if_statement", "while_statement",
            "for_statement", "assignment_statement", "declaration", "local_declaration",
            "call_expression", "throw_statement", "raise_statement", "assert_statement",
            "break_statement", "continue_statement", "try_statement", "with_statement",
            "macro_invocation", "command", "method_invocation"
        }
        
        return node_type in statement_types or "_statement" in node_type or "_expression" in node_type

    def _is_placeholder_statement(self, statement, language: str, file_text: str) -> bool:
        """Check if a statement is a placeholder implementation."""
        if not hasattr(statement, 'type'):
            return False

        statement_type = statement.type
        patterns = self.PLACEHOLDER_PATTERNS.get(language, {})
        
        if statement_type not in patterns:
            return False

        # Extract text content of the statement
        statement_text = self._extract_node_text(statement, file_text)
        if not statement_text:
            return False

        # Check for language-specific placeholder patterns
        keywords = patterns[statement_type]
        return any(keyword in statement_text for keyword in keywords)

    def _extract_node_text(self, node, file_text: str) -> str:
        """Extract text content from a node."""
        if not node or not file_text:
            return ""
        
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte)
        
        # For mock objects in tests, try to extract from the mock structure
        if hasattr(node, 'text') and node.text:
            text = node.text
            # Convert bytes to string if necessary
            if isinstance(text, bytes):
                try:
                    return text.decode('utf-8')
                except UnicodeDecodeError:
                    return ""
            return str(text)
        
        if start_byte >= 0 and end_byte > start_byte:
            try:
                # Handle both string and bytes
                if isinstance(file_text, str):
                    file_bytes = file_text.encode('utf-8')
                else:
                    file_bytes = file_text
                
                if end_byte <= len(file_bytes):
                    return file_bytes[start_byte:end_byte].decode('utf-8')
            except (UnicodeDecodeError, IndexError):
                pass
        
        return ""

    def _get_children(self, node):
        """Get children of a node, handling different tree-sitter implementations."""
        if not node:
            return []
        
        children = getattr(node, 'children', [])
        if children:
            try:
                return list(children)
            except (TypeError, AttributeError):
                return []
        return []

    def _create_finding(self, ctx: RuleContext, function_node, placeholder_stmt, language: str) -> Optional[Finding]:
        """Create a finding for a function with placeholder implementation."""
        # Get the span for the placeholder statement
        start_byte = getattr(placeholder_stmt, 'start_byte', 0)
        end_byte = getattr(placeholder_stmt, 'end_byte', start_byte + 10)

        # Generate message
        function_name = self._extract_function_name(function_node, ctx.text)
        if function_name:
            message = f"'{function_name}' has placeholder code (pass/TODO/NotImplementedError)—implement it or add a tracking ticket."
        else:
            message = "Function has placeholder code (pass/TODO/NotImplementedError)—implement it or add a tracking ticket."

        # Generate suggestion
        suggestion = self._create_refactoring_suggestion(language, function_name)

        finding = Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="info",  # As specified in requirements
            autofix=None,  # suggest-only
            meta={
                "suggestion": suggestion,
                "language": language,
                "function_name": function_name,
                "placeholder_type": getattr(placeholder_stmt, 'type', 'unknown'),
                "placeholder_span": {
                    "start": start_byte,
                    "end": end_byte
                }
            }
        )

        return finding

    def _extract_function_name(self, function_node, file_text: str) -> Optional[str]:
        """Extract the function name from a function node."""
        # Look for identifier nodes that typically contain function names
        for child in self._get_children(function_node):
            if hasattr(child, 'type') and child.type in {"identifier", "name"}:
                name_text = self._extract_node_text(child, file_text)
                if name_text and name_text.isidentifier():
                    return name_text
        
        return None

    def _create_refactoring_suggestion(self, language: str, function_name: Optional[str]) -> str:
        """Create language-specific refactoring suggestion."""
        func_ref = f"'{function_name}'" if function_name else "this function"
        
        base_suggestion = f"""Placeholder implementation detected in {func_ref}. Consider these options:

1. **Implement the function**: Replace the placeholder with actual logic
2. **Add TODO comment**: Link to issue tracker or documentation
3. **Mark as abstract**: If this should be implemented by subclasses
4. **Remove if unused**: Delete if no longer needed

"""
        
        if language == "python":
            return base_suggestion + self._create_python_suggestion(function_name)
        elif language in ["typescript", "javascript"]:
            return base_suggestion + self._create_js_ts_suggestion(language, function_name)
        elif language == "java":
            return base_suggestion + self._create_java_suggestion(function_name)
        elif language == "csharp":
            return base_suggestion + self._create_csharp_suggestion(function_name)
        elif language == "go":
            return base_suggestion + self._create_go_suggestion(function_name)
        elif language == "rust":
            return base_suggestion + self._create_rust_suggestion(function_name)
        elif language in ["c", "cpp"]:
            return base_suggestion + self._create_c_cpp_suggestion(language, function_name)
        elif language == "ruby":
            return base_suggestion + self._create_ruby_suggestion(function_name)
        elif language == "swift":
            return base_suggestion + self._create_swift_suggestion(function_name)
        else:
            return base_suggestion + "Replace the placeholder with actual implementation."

    def _create_python_suggestion(self, function_name: Optional[str]) -> str:
        """Create Python-specific refactoring suggestion."""
        return """Python-specific options:

```python
# ❌ Current placeholder
def process_data(data):
    raise NotImplementedError

# ✅ Option 1: Implement the function
def process_data(data):
    \"\"\"Process the input data and return results.\"\"\"
    # Validate input
    if not data:
        raise ValueError("Data cannot be empty")
    
    # Process data
    result = [item.upper() for item in data if item.strip()]
    return result

# ✅ Option 2: Add TODO with ticket reference
def process_data(data):
    # TODO: Implement data processing logic
    # See: https://github.com/project/repo/issues/123
    raise NotImplementedError("Data processing not yet implemented - see issue #123")

# ✅ Option 3: Abstract method (if in a base class)
from abc import ABC, abstractmethod

class BaseProcessor(ABC):
    @abstractmethod
    def process_data(self, data):
        \"\"\"Process data - must be implemented by subclasses.\"\"\"
        pass

# ✅ Option 4: Graceful fallback
def process_data(data):
    \"\"\"Process data with fallback behavior.\"\"\"
    # TODO: Implement optimized processing (issue #123)
    # For now, return data as-is
    return data
```"""

    def _create_js_ts_suggestion(self, language: str, function_name: Optional[str]) -> str:
        """Create JavaScript/TypeScript-specific refactoring suggestion."""
        lang_name = "TypeScript" if language == "typescript" else "JavaScript"
        return f"""{lang_name}-specific options:

```{language}
// ❌ Current placeholder
function processData(data) {{
    throw new Error("Not implemented");
}}

// ✅ Option 1: Implement the function
function processData(data) {{
    // Validate input
    if (!data || !Array.isArray(data)) {{
        throw new Error("Data must be a non-empty array");
    }}
    
    // Process data
    return data.filter(item => item.trim()).map(item => item.toUpperCase());
}}

// ✅ Option 2: Add TODO with ticket reference
function processData(data) {{
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    throw new Error("Data processing not yet implemented - see issue #123");
}}

// ✅ Option 3: Abstract method (TypeScript)
{('abstract class BaseProcessor {' + '''
    abstract processData(data: any[]): any[];
}''' if language == 'typescript' else '// Use interface or base class pattern')}

// ✅ Option 4: Graceful fallback
function processData(data) {{
    // TODO: Implement optimized processing (issue #123)
    console.warn("Using fallback data processing");
    return data; // Return data as-is for now
}}
```"""

    def _create_java_suggestion(self, function_name: Optional[str]) -> str:
        """Create Java-specific refactoring suggestion."""
        return """Java-specific options:

```java
// ❌ Current placeholder
public List<String> processData(List<String> data) {
    throw new UnsupportedOperationException();
}

// ✅ Option 1: Implement the method
public List<String> processData(List<String> data) {
    // Validate input
    if (data == null || data.isEmpty()) {
        throw new IllegalArgumentException("Data cannot be null or empty");
    }
    
    // Process data
    return data.stream()
        .filter(item -> item != null && !item.trim().isEmpty())
        .map(String::toUpperCase)
        .collect(Collectors.toList());
}

// ✅ Option 2: Add TODO with ticket reference
public List<String> processData(List<String> data) {
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    throw new UnsupportedOperationException("Data processing not yet implemented - see issue #123");
}

// ✅ Option 3: Abstract method
public abstract class BaseProcessor {
    public abstract List<String> processData(List<String> data);
}

// ✅ Option 4: Graceful fallback
public List<String> processData(List<String> data) {
    // TODO: Implement optimized processing (issue #123)
    logger.warn("Using fallback data processing");
    return new ArrayList<>(data); // Return copy for now
}
```"""

    def _create_csharp_suggestion(self, function_name: Optional[str]) -> str:
        """Create C#-specific refactoring suggestion."""
        return """C#-specific options:

```csharp
// ❌ Current placeholder
public List<string> ProcessData(List<string> data)
{
    throw new NotImplementedException();
}

// ✅ Option 1: Implement the method
public List<string> ProcessData(List<string> data)
{
    // Validate input
    if (data == null || !data.Any())
    {
        throw new ArgumentException("Data cannot be null or empty", nameof(data));
    }
    
    // Process data
    return data
        .Where(item => !string.IsNullOrWhiteSpace(item))
        .Select(item => item.ToUpper())
        .ToList();
}

// ✅ Option 2: Add TODO with ticket reference
public List<string> ProcessData(List<string> data)
{
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    throw new NotImplementedException("Data processing not yet implemented - see issue #123");
}

// ✅ Option 3: Abstract method
public abstract class BaseProcessor
{
    public abstract List<string> ProcessData(List<string> data);
}

// ✅ Option 4: Graceful fallback
public List<string> ProcessData(List<string> data)
{
    // TODO: Implement optimized processing (issue #123)
    _logger.LogWarning("Using fallback data processing");
    return new List<string>(data); // Return copy for now
}
```"""

    def _create_go_suggestion(self, function_name: Optional[str]) -> str:
        """Create Go-specific refactoring suggestion."""
        return """Go-specific options:

```go
// ❌ Current placeholder
func ProcessData(data []string) []string {
    panic("not implemented")
}

// ✅ Option 1: Implement the function
func ProcessData(data []string) []string {
    // Validate input
    if len(data) == 0 {
        return nil
    }
    
    // Process data
    var result []string
    for _, item := range data {
        if strings.TrimSpace(item) != "" {
            result = append(result, strings.ToUpper(item))
        }
    }
    return result
}

// ✅ Option 2: Add TODO with ticket reference
func ProcessData(data []string) []string {
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    panic("ProcessData not yet implemented - see issue #123")
}

// ✅ Option 3: Interface-based design
type DataProcessor interface {
    ProcessData(data []string) []string
}

// ✅ Option 4: Graceful fallback
func ProcessData(data []string) []string {
    // TODO: Implement optimized processing (issue #123)
    log.Println("Warning: Using fallback data processing")
    // Return copy for now
    result := make([]string, len(data))
    copy(result, data)
    return result
}
```"""

    def _create_rust_suggestion(self, function_name: Optional[str]) -> str:
        """Create Rust-specific refactoring suggestion."""
        return """Rust-specific options:

```rust
// ❌ Current placeholder
fn process_data(data: Vec<String>) -> Vec<String> {
    unimplemented!()
}

// ✅ Option 1: Implement the function
fn process_data(data: Vec<String>) -> Vec<String> {
    // Process data
    data.into_iter()
        .filter(|item| !item.trim().is_empty())
        .map(|item| item.to_uppercase())
        .collect()
}

// ✅ Option 2: Add TODO with ticket reference
fn process_data(data: Vec<String>) -> Vec<String> {
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    unimplemented!("Data processing not yet implemented - see issue #123")
}

// ✅ Option 3: Trait-based design
trait DataProcessor {
    fn process_data(&self, data: Vec<String>) -> Vec<String>;
}

// ✅ Option 4: Graceful fallback with Result
fn process_data(data: Vec<String>) -> Result<Vec<String>, &'static str> {
    // TODO: Implement optimized processing (issue #123)
    eprintln!("Warning: Using fallback data processing");
    Ok(data) // Return data as-is for now
}

// ✅ Option 5: Use todo!() for clearer intent
fn process_data(data: Vec<String>) -> Vec<String> {
    todo!("Implement data processing - issue #123")
}
```"""

    def _create_c_cpp_suggestion(self, language: str, function_name: Optional[str]) -> str:
        """Create C/C++-specific refactoring suggestion."""
        lang_name = "C++" if language == "cpp" else "C"
        
        if language == "cpp":
            return f"""{lang_name}-specific options:

```cpp
// ❌ Current placeholder
std::vector<std::string> processData(const std::vector<std::string>& data) {{
    std::abort();
}}

// ✅ Option 1: Implement the function
std::vector<std::string> processData(const std::vector<std::string>& data) {{
    // Validate input
    if (data.empty()) {{
        return {{}};
    }}
    
    // Process data
    std::vector<std::string> result;
    for (const auto& item : data) {{
        if (!item.empty()) {{
            std::string upper = item;
            std::transform(upper.begin(), upper.end(), upper.begin(), ::toupper);
            result.push_back(upper);
        }}
    }}
    return result;
}}

// ✅ Option 2: Add TODO with assertion
std::vector<std::string> processData(const std::vector<std::string>& data) {{
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    assert(false && "processData not yet implemented - see issue #123");
}}

// ✅ Option 3: Graceful fallback
std::vector<std::string> processData(const std::vector<std::string>& data) {{
    // TODO: Implement optimized processing (issue #123)
    std::cerr << "Warning: Using fallback data processing" << std::endl;
    return data; // Return copy for now
}}
```"""
        else:  # C
            return f"""{lang_name}-specific options:

```c
// ❌ Current placeholder
void process_data(char** data, int count) {{
    abort();
}}

// ✅ Option 1: Implement the function
void process_data(char** data, int count, char*** result, int* result_count) {{
    // Validate input
    if (data == NULL || count <= 0) {{
        *result = NULL;
        *result_count = 0;
        return;
    }}
    
    // TODO: Implement actual processing logic
    *result = malloc(count * sizeof(char*));
    *result_count = count;
    for (int i = 0; i < count; i++) {{
        (*result)[i] = strdup(data[i]);
    }}
}}

// ✅ Option 2: Add TODO with assertion
void process_data(char** data, int count) {{
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    assert(0 && "process_data not yet implemented - see issue #123");
}}

// ✅ Option 3: Graceful fallback
void process_data(char** data, int count, char*** result, int* result_count) {{
    // TODO: Implement optimized processing (issue #123)
    fprintf(stderr, "Warning: Using fallback data processing\\n");
    *result = malloc(count * sizeof(char*));
    *result_count = count;
    for (int i = 0; i < count; i++) {{
        (*result)[i] = strdup(data[i]);
    }}
}}
```"""

    def _create_ruby_suggestion(self, function_name: Optional[str]) -> str:
        """Create Ruby-specific refactoring suggestion."""
        return """Ruby-specific options:

```ruby
# ❌ Current placeholder
def process_data(data)
  raise NotImplementedError
end

# ✅ Option 1: Implement the method
def process_data(data)
  # Validate input
  raise ArgumentError, "Data cannot be nil or empty" if data.nil? || data.empty?
  
  # Process data
  data.select { |item| !item.strip.empty? }
      .map(&:upcase)
end

# ✅ Option 2: Add TODO with ticket reference
def process_data(data)
  # TODO: Implement data processing logic
  # See: https://github.com/project/repo/issues/123
  raise NotImplementedError, "Data processing not yet implemented - see issue #123"
end

# ✅ Option 3: Graceful fallback
def process_data(data)
  # TODO: Implement optimized processing (issue #123)
  warn "Using fallback data processing"
  data.dup # Return copy for now
end

# ✅ Option 4: Module-based design
module DataProcessor
  def process_data(data)
    raise NotImplementedError, "Must implement process_data in #{self.class}"
  end
end
```"""

    def _create_swift_suggestion(self, function_name: Optional[str]) -> str:
        """Create Swift-specific refactoring suggestion."""
        return """Swift-specific options:

```swift
// ❌ Current placeholder
func processData(_ data: [String]) -> [String] {
    fatalError("Not implemented")
}

// ✅ Option 1: Implement the function
func processData(_ data: [String]) -> [String] {
    // Validate and process data
    return data.compactMap { item in
        let trimmed = item.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed.uppercased()
    }
}

// ✅ Option 2: Add TODO with ticket reference
func processData(_ data: [String]) -> [String] {
    // TODO: Implement data processing logic
    // See: https://github.com/project/repo/issues/123
    fatalError("Data processing not yet implemented - see issue #123")
}

// ✅ Option 3: Protocol-based design
protocol DataProcessor {
    func processData(_ data: [String]) -> [String]
}

// ✅ Option 4: Graceful fallback with Result
func processData(_ data: [String]) -> Result<[String], Error> {
    // TODO: Implement optimized processing (issue #123)
    print("Warning: Using fallback data processing")
    return .success(data) // Return data as-is for now
}

// ✅ Option 5: Optional return for unimplemented
func processData(_ data: [String]) -> [String]? {
    // TODO: Implement data processing logic (issue #123)
    return nil // Indicates not yet implemented
}
```"""


# Register this rule when the module is imported
try:
    from ..engine.registry import register_rule
except ImportError:
    try:
        from engine.registry import register_rule
    except ImportError:
        # For test execution - registry may not be available
        def register_rule(rule):
            pass

register_rule(ErrorsPartialFunctionImplementationRule())


