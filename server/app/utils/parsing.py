"""Parser interface and implementations for extracting structured data from source files."""

from typing import Protocol, Dict, Any, List, Optional
import libcst as cst
import hashlib
from pathlib import Path
import time


class ParsedSymbol:
    """A symbol (function, class, variable) found in source code."""
    
    def __init__(self, name: str, type: str, line: int, col: int = 0, 
                 docstring: Optional[str] = None, **kwargs):
        self.name = name
        self.type = type  # "function", "class", "variable", "import"
        self.line = line
        self.col = col
        self.docstring = docstring
        self.extra = kwargs
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "name": self.name,
            "type": self.type,
            "line": self.line,
            "col": self.col
        }
        if self.docstring:
            result["docstring"] = self.docstring
        if self.extra:
            result.update(self.extra)
        return result


class Parser(Protocol):
    """Protocol for language-specific source code parsers."""
    
    def summarize(self, path: str, text: str) -> Dict[str, Any]:
        """Extract structured information from source code.
        
        Args:
            path: File path for context
            text: Source code content
            
        Returns:
            Dictionary containing:
            - imports: List of import statements
            - symbols: List of ParsedSymbol dicts
            - language: Language identifier
            - parse_error: Optional error message if parsing failed
        """
        ...


class PythonParser:
    """LibCST-based Python parser for extracting imports, symbols, and structure."""
    
    def __init__(self, timeout_seconds: float = 2.0):
        self.timeout_seconds = timeout_seconds
    
    def summarize(self, path: str, text: str) -> Dict[str, Any]:
        """Extract Python IR using LibCST.
        
        Handles CRLF safely and extracts:
        - Import statements (with aliases)
        - Function and class definitions (with docstrings)
        - Module-level variables
        """
        start_time = time.time()
        
        try:
            # Parse with LibCST (handles CRLF automatically)
            tree = cst.parse_module(text)
            
            visitor = PythonSummaryVisitor()
            tree.visit(visitor)
            
            # Check for timeout
            if time.time() - start_time > self.timeout_seconds:
                return self._minimal_ir(path, text, "Parsing timeout")
            
            return {
                "language": "python",
                "imports": visitor.imports,
                "symbols": [sym.to_dict() for sym in visitor.symbols],
                "parse_time_ms": int((time.time() - start_time) * 1000)
            }
            
        except Exception as e:
            # Fallback to minimal IR on parse error
            return self._minimal_ir(path, text, str(e))
    
    def _minimal_ir(self, path: str, text: str, error: str) -> Dict[str, Any]:
        """Generate minimal IR when full parsing fails."""
        # Extract imports using simple regex as fallback
        import re
        imports = []
        
        for line in text.split('\n'):
            line = line.strip()
            # Simple import detection
            if line.startswith('import ') or line.startswith('from '):
                imports.append({
                    "statement": line,
                    "type": "import" if line.startswith('import ') else "from_import"
                })
        
        return {
            "language": "python",
            "imports": imports,
            "symbols": [],
            "parse_error": error,
            "parse_time_ms": 0
        }


class PythonSummaryVisitor(cst.CSTVisitor):
    """LibCST visitor for extracting Python symbols and imports."""
    
    def __init__(self):
        self.imports: List[Dict[str, Any]] = []
        self.symbols: List[ParsedSymbol] = []
        self.current_line = 1
    
    def visit_Import(self, node: cst.Import) -> None:
        """Extract import statements."""
        for name in node.names:
            if isinstance(name, cst.ImportStar):
                continue
            
            import_name = name.name.value
            alias = name.asname.name.value if name.asname else None
            
            self.imports.append({
                "type": "import",
                "module": import_name,
                "name": import_name,
                "alias": alias,
                "line": self.current_line
            })
    
    def visit_ImportFrom(self, node: cst.ImportFrom) -> None:
        """Extract from...import statements."""
        if isinstance(node.names, cst.ImportStar):
            return
        
        module_name = ""
        if node.module:
            module_name = cst.Module([]).code_for_node(node.module)
        
        for name in node.names:
            import_name = name.name.value
            alias = name.asname.name.value if name.asname else None
            
            self.imports.append({
                "type": "from_import",
                "module": module_name,
                "name": import_name,
                "alias": alias,
                "line": self.current_line
            })
    
    def visit_FunctionDef(self, node: cst.FunctionDef) -> None:
        """Extract function definitions."""
        # Get position if available
        pos = getattr(node, 'metadata', {}).get('position', None)
        line = pos.start.line if pos else self.current_line
        col = pos.start.column if pos else 0
        
        # Extract docstring
        docstring = self._extract_docstring(node.body)
        
        # Count parameters
        param_count = len(node.params.params)
        
        symbol = ParsedSymbol(
            name=node.name.value,
            type="function",
            line=line,
            col=col,
            docstring=docstring,
            param_count=param_count,
            is_async=isinstance(node, cst.FunctionDef) and node.asynchronous is not None
        )
        
        self.symbols.append(symbol)
    
    def visit_ClassDef(self, node: cst.ClassDef) -> None:
        """Extract class definitions."""
        # Get position if available
        pos = getattr(node, 'metadata', {}).get('position', None)
        line = pos.start.line if pos else self.current_line
        col = pos.start.column if pos else 0
        
        # Extract docstring
        docstring = self._extract_docstring(node.body)
        
        # Extract base classes
        bases = []
        for arg in node.bases:
            if isinstance(arg.value, cst.Name):
                bases.append(arg.value.value)
        
        symbol = ParsedSymbol(
            name=node.name.value,
            type="class",
            line=line,
            col=col,
            docstring=docstring,
            bases=bases
        )
        
        self.symbols.append(symbol)
    
    def visit_Assign(self, node: cst.Assign) -> None:
        """Extract module-level variable assignments."""
        # Only capture simple module-level assignments
        for target in node.targets:
            if isinstance(target.target, cst.Name):
                symbol = ParsedSymbol(
                    name=target.target.value,
                    type="variable",
                    line=self.current_line,
                    col=0
                )
                self.symbols.append(symbol)
    
    def _extract_docstring(self, body) -> Optional[str]:
        """Extract docstring from function/class body."""
        if isinstance(body, cst.SimpleStatementSuite):
            # Single line function - check if it's a string literal
            for stmt in body.body:
                if isinstance(stmt, cst.Expr) and isinstance(stmt.value, cst.SimpleString):
                    return stmt.value.value.strip('\'"')
            return None
        
        elif isinstance(body, cst.IndentedBlock):
            # Multi-line function - check first statement
            if body.body:
                first_stmt = body.body[0]
                if isinstance(first_stmt, cst.SimpleStatementLine):
                    for body_stmt in first_stmt.body:
                        if isinstance(body_stmt, cst.Expr) and isinstance(body_stmt.value, cst.SimpleString):
                            return body_stmt.value.value.strip('\'"')
        
        return None


class TreeSitterParser:
    """Fallback parser for non-Python languages.
    
    Returns a minimal IR structure to allow indexing to proceed.
    Full tree-sitter parsing is done by the engine adapters during validation.
    """
    
    def __init__(self, language: str):
        self.language = language
    
    def summarize(self, path: str, text: str) -> Dict[str, Any]:
        """Return minimal IR structure for non-Python files."""
        return {
            "language": self.language,
            "symbols": [],
            "imports": [],
            "exports": [],
            "docstring": None
        }


def get_parser(language: str) -> Parser:
    """Factory function to get appropriate parser for language."""
    if language.lower() == "python":
        return PythonParser()
    else:
        return TreeSitterParser(language)


def detect_language(path: str) -> str:
    """Detect programming language from file extension."""
    suffix = Path(path).suffix.lower()
    
    language_map = {
        '.py': 'python',
        '.pyi': 'python',
        '.ts': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.tsx': 'typescript',
        '.go': 'go',
        '.rs': 'rust',
        '.java': 'java',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp'
    }
    
    return language_map.get(suffix, 'other')


def compute_file_hash(content: str) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def detect_newline_style(content: str) -> str:
    """Detect newline style in file content."""
    has_crlf = '\r\n' in content
    has_lf = '\n' in content and '\r\n' not in content.replace('\r\n', '')
    
    if has_crlf and has_lf:
        return 'MIXED'
    elif has_crlf:
        return 'CRLF' 
    elif has_lf:
        return 'LF'
    else:
        return 'LF'  # Default for empty files

