"""
Project-wide symbol index for cross-file analysis.

This module provides infrastructure to collect and query symbols (functions,
classes, variables, etc.) across all files in a project, enabling Tier 2 rules
to perform cross-file analysis like naming consistency checking.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Optional, Tuple, Pattern
from collections import defaultdict
import re
import os
from pathlib import Path

from .types import LanguageAdapter


@dataclass(frozen=True)
class ProjectSymbol:
    """Represents a symbol declaration visible across the project."""
    name: str
    kind: str  # "function", "class", "method", "variable", "const", "type", "interface", etc.
    file_path: str
    start_byte: int
    end_byte: int
    language: str
    scope_kind: str  # "module", "class", "function", "namespace", etc.
    visibility: str  # "public", "private", "protected", "internal"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def file_name(self) -> str:
        """Get just the file name without directory path."""
        return os.path.basename(self.file_path)
    
    @property
    def qualified_name(self) -> str:
        """Get a qualified name including file context if useful."""
        return f"{self.file_name}::{self.name}"


class ProjectSymbolIndex:
    """Index of symbols visible across project files.
    
    Provides fast lookup capabilities for cross-file analysis:
    - Find all symbols with a given name
    - Find symbols matching patterns  
    - Find symbols by type/kind
    - Find symbols in specific files
    """
    
    def __init__(self):
        self._symbols: List[ProjectSymbol] = []
        
        # Indexes for fast lookup
        self._by_name: Dict[str, List[ProjectSymbol]] = defaultdict(list)
        self._by_kind: Dict[str, List[ProjectSymbol]] = defaultdict(list)
        self._by_file: Dict[str, List[ProjectSymbol]] = defaultdict(list)
        self._by_language: Dict[str, List[ProjectSymbol]] = defaultdict(list)
        self._by_visibility: Dict[str, List[ProjectSymbol]] = defaultdict(list)
        
        # Compiled regex cache for pattern matching
        self._pattern_cache: Dict[str, Pattern] = {}
    
    def add_symbol(self, symbol: ProjectSymbol) -> None:
        """Add a symbol to the index."""
        self._symbols.append(symbol)
        
        # Update indexes
        self._by_name[symbol.name].append(symbol)
        self._by_kind[symbol.kind].append(symbol)
        self._by_file[symbol.file_path].append(symbol)
        self._by_language[symbol.language].append(symbol)
        self._by_visibility[symbol.visibility].append(symbol)
    
    def add_symbols(self, symbols: List[ProjectSymbol]) -> None:
        """Add multiple symbols to the index."""
        for symbol in symbols:
            self.add_symbol(symbol)
    
    def clear(self) -> None:
        """Clear all symbols from the index."""
        self._symbols.clear()
        self._by_name.clear()
        self._by_kind.clear()
        self._by_file.clear()
        self._by_language.clear()
        self._by_visibility.clear()
        self._pattern_cache.clear()
    
    # ================================
    # Query methods
    # ================================
    
    def find_by_name(self, name: str) -> List[ProjectSymbol]:
        """Find all symbols with the exact name."""
        return self._by_name.get(name, [])
    
    def find_by_kind(self, kind: str) -> List[ProjectSymbol]:
        """Find all symbols of a specific kind."""
        return self._by_kind.get(kind, [])
    
    def find_by_file(self, file_path: str) -> List[ProjectSymbol]:
        """Find all symbols defined in a specific file."""
        return self._by_file.get(file_path, [])
    
    def find_by_language(self, language: str) -> List[ProjectSymbol]:
        """Find all symbols in a specific programming language."""
        return self._by_language.get(language, [])
    
    def find_by_visibility(self, visibility: str) -> List[ProjectSymbol]:
        """Find all symbols with specific visibility."""
        return self._by_visibility.get(visibility, [])
    
    def find_by_pattern(self, pattern: str, kind: Optional[str] = None) -> List[ProjectSymbol]:
        """Find symbols whose names match a regex pattern.
        
        Args:
            pattern: Regular expression pattern to match against symbol names
            kind: Optional filter to only include symbols of specific kind
        
        Returns:
            List of symbols matching the pattern
        """
        # Compile and cache regex patterns
        if pattern not in self._pattern_cache:
            try:
                self._pattern_cache[pattern] = re.compile(pattern)
            except re.error:
                return []  # Invalid regex
        
        regex = self._pattern_cache[pattern]
        
        # Filter symbols by pattern and optionally by kind
        results = []
        symbols_to_check = self._by_kind.get(kind, []) if kind else self._symbols
        
        for symbol in symbols_to_check:
            if regex.search(symbol.name):
                results.append(symbol)
        
        return results
    
    def find_functions_by_verb_pattern(self, verb_pattern: str) -> List[ProjectSymbol]:
        """Find functions/methods matching a verb pattern (e.g., 'get_.*', 'fetch_.*')."""
        return self.find_by_pattern(verb_pattern, kind="function") + \
               self.find_by_pattern(verb_pattern, kind="method")
    
    def find_similar_names(self, base_name: str, threshold: float = 0.7) -> List[ProjectSymbol]:
        """Find symbols with names similar to the base name using fuzzy matching.
        
        This can help identify potential naming inconsistencies.
        """
        # Simple implementation using string similarity
        # Could be enhanced with more sophisticated algorithms
        results = []
        base_lower = base_name.lower()
        
        for symbol in self._symbols:
            symbol_lower = symbol.name.lower()
            
            # Calculate simple similarity ratio
            if len(symbol_lower) == 0:
                continue
            
            # Use a simple edit distance approach
            similarity = self._calculate_similarity(base_lower, symbol_lower)
            if similarity >= threshold and symbol.name != base_name:
                results.append(symbol)
        
        return results
    
    def group_by_noun_phrase(self, verb_synonyms: Dict[str, Set[str]]) -> Dict[Tuple[str, str], List[ProjectSymbol]]:
        """Group function symbols by their noun phrase for consistency analysis.
        
        This is specifically useful for naming consistency rules.
        Returns: Dict[(noun_phrase, kind) -> List[symbols]]
        """
        groups = defaultdict(list)
        
        functions = self.find_by_kind("function") + self.find_by_kind("method")
        
        for symbol in functions:
            noun_phrase = self._extract_noun_phrase(symbol.name, verb_synonyms)
            if noun_phrase:
                key = (noun_phrase, symbol.kind)
                groups[key].append(symbol)
        
        return groups
    
    # ================================
    # Statistics and utilities
    # ================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the symbol index."""
        return {
            "total_symbols": len(self._symbols),
            "symbols_by_kind": {k: len(v) for k, v in self._by_kind.items()},
            "symbols_by_language": {k: len(v) for k, v in self._by_language.items()},
            "symbols_by_visibility": {k: len(v) for k, v in self._by_visibility.items()},
            "files_indexed": len(self._by_file),
            "cached_patterns": len(self._pattern_cache)
        }
    
    def __len__(self) -> int:
        """Return total number of symbols."""
        return len(self._symbols)
    
    def __bool__(self) -> bool:
        """Return True if index contains symbols."""
        return len(self._symbols) > 0
    
    # ================================
    # Private helper methods
    # ================================
    
    def _calculate_similarity(self, s1: str, s2: str) -> float:
        """Calculate similarity ratio between two strings using simple metrics."""
        if not s1 or not s2:
            return 0.0
        
        # Use longest common subsequence approach
        longer = s1 if len(s1) > len(s2) else s2
        shorter = s2 if len(s1) > len(s2) else s1
        
        if len(longer) == 0:
            return 1.0
        
        # Simple similarity: count common characters
        common = sum(1 for c in shorter if c in longer)
        return common / len(longer)
    
    def _extract_noun_phrase(self, symbol_name: str, verb_synonyms: Dict[str, Set[str]]) -> Optional[str]:
        """Extract noun phrase from a function name for grouping."""
        # Split identifier into parts
        parts = self._split_identifier(symbol_name)
        if len(parts) < 2:
            return None
        
        # Check if first part is a known verb
        verb = parts[0].lower()
        is_verb = any(verb == canonical or verb in synonyms 
                     for canonical, synonyms in verb_synonyms.items())
        
        if is_verb:
            return " ".join(parts[1:])
        
        return None
    
    def _split_identifier(self, name: str) -> List[str]:
        """Split identifier into component words."""
        if not name:
            return []
        
        # Handle camelCase and PascalCase
        s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
        s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
        
        # Split on non-alphanumeric characters and whitespace
        parts = re.split(r"[\W_\s]+", s)
        
        # Clean and normalize
        return [p.lower() for p in parts if p and p.isalpha()]


def infer_visibility(symbol_dict: Dict[str, Any], language: str = "") -> str:
    """Infer the visibility/accessibility of a symbol from its metadata.
    
    Args:
        symbol_dict: Symbol information from adapter
        language: Programming language for language-specific rules
    
    Returns:
        Visibility string: "public", "private", "protected", "internal"
    """
    name = symbol_dict.get('name', '')
    kind = symbol_dict.get('kind', '')
    meta = symbol_dict.get('meta', {})
    
    # Check explicit visibility in metadata
    if 'visibility' in meta:
        return meta['visibility']
    
    # Language-specific inference rules
    if language in ('python', 'py'):
        # Python conventions
        if name.startswith('__') and name.endswith('__'):
            return 'public'  # Dunder methods are public interface
        elif name.startswith('__'):
            return 'private'  # Name mangling
        elif name.startswith('_'):
            return 'protected'  # Convention for internal use
        else:
            return 'public'
    
    elif language in ('typescript', 'javascript', 'ts', 'js'):
        # TypeScript/JavaScript
        if name.startswith('_'):
            return 'private'
        elif meta.get('is_exported', True):  # Default to exported
            return 'public'
        else:
            return 'private'
    
    elif language in ('java', 'csharp', 'c#'):
        # Java/C# have explicit modifiers
        modifiers = meta.get('modifiers', [])
        if 'private' in modifiers:
            return 'private'
        elif 'protected' in modifiers:
            return 'protected'
        elif 'internal' in modifiers:
            return 'internal'
        else:
            return 'public'
    
    elif language in ('cpp', 'c++', 'c'):
        # C++ access specifiers
        access = meta.get('access', 'public')
        return access
    
    elif language == 'go':
        # Go: uppercase = public, lowercase = private
        if name and name[0].isupper():
            return 'public'
        else:
            return 'private'
    
    elif language == 'rust':
        # Rust: pub keyword
        if meta.get('is_pub', False):
            return 'public'
        else:
            return 'private'
    
    # Default fallback
    return 'public'


def detect_language_from_file_path(file_path: str) -> Optional[str]:
    """Detect programming language from file extension."""
    ext = Path(file_path).suffix.lower()
    
    extension_map = {
        '.py': 'python',
        '.pyi': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.java': 'java',
        '.cs': 'csharp',
        '.cpp': 'cpp',
        '.cxx': 'cpp',
        '.cc': 'cpp',
        '.hpp': 'cpp',
        '.h': 'c',  # Could be C or C++, assume C
        '.c': 'c',
        '.go': 'go',
        '.rs': 'rust',
        '.rb': 'ruby',
        '.swift': 'swift',
        '.php': 'php',
        '.sql': 'sql',
    }
    
    return extension_map.get(ext)


def build_symbol_index(files: List[str], adapters: Dict[str, LanguageAdapter], 
                      excluded_paths: Optional[Set[str]] = None) -> ProjectSymbolIndex:
    """Build a project-wide symbol index from a list of files.
    
    Args:
        files: List of file paths to index
        adapters: Dictionary mapping language IDs to language adapters
        excluded_paths: Optional set of path patterns to exclude
    
    Returns:
        ProjectSymbolIndex containing all discovered symbols
    """
    index = ProjectSymbolIndex()
    excluded_paths = excluded_paths or set()
    
    for file_path in files:
        # Skip excluded paths
        if _is_excluded_path(file_path, excluded_paths):
            continue
        
        # Detect language and get adapter
        language = detect_language_from_file_path(file_path)
        if not language or language not in adapters:
            continue
        
        adapter = adapters[language]
        
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Parse the file
            tree = adapter.parse(content)
            if not tree:
                continue
            
            # Extract symbols using the adapter's symbol extraction
            symbol_defs = []
            if hasattr(adapter, 'iter_symbol_defs'):
                symbol_defs = list(adapter.iter_symbol_defs(tree))
            else:
                # Fallback to basic symbol extraction if iter_symbol_defs not available
                continue
            
            # Convert to ProjectSymbol objects and add to index
            for sym_dict in symbol_defs:
                try:
                    symbol = ProjectSymbol(
                        name=sym_dict['name'],
                        kind=sym_dict['kind'],
                        file_path=file_path,
                        start_byte=sym_dict['start'],
                        end_byte=sym_dict.get('end', sym_dict['start']),
                        language=language,
                        scope_kind=sym_dict.get('scope_kind', 'module'),
                        visibility=infer_visibility(sym_dict, language),
                        metadata=sym_dict.get('meta', {})
                    )
                    index.add_symbol(symbol)
                except (KeyError, TypeError) as e:
                    # Skip malformed symbol definitions
                    print(f"Warning: Skipping malformed symbol in {file_path}: {e}")
                    continue
        
        except Exception as e:
            print(f"Warning: Failed to index symbols in {file_path}: {e}")
            continue
    
    return index


def build_symbol_index_from_adapters_registry(files: List[str], 
                                            excluded_paths: Optional[Set[str]] = None) -> ProjectSymbolIndex:
    """Build symbol index using adapters from the global registry.
    
    This is a convenience function that automatically gets adapters from the registry.
    """
    try:
        from .registry import get_all_adapters
        adapters = get_all_adapters()
        return build_symbol_index(files, adapters, excluded_paths)
    except ImportError:
        print("Warning: Could not import adapter registry")
        return ProjectSymbolIndex()


def _is_excluded_path(file_path: str, excluded_paths: Set[str]) -> bool:
    """Check if file path should be excluded from indexing."""
    if not file_path:
        return False
    
    # Normalize path separators
    normalized_path = file_path.replace("\\", "/")
    path_parts = normalized_path.split("/")
    
    # Check if any path component matches excluded patterns
    for excluded in excluded_paths:
        if excluded in path_parts:
            return True
        
        # Also check for pattern matching (simple glob-like)
        if "*" in excluded:
            import fnmatch
            if fnmatch.fnmatch(normalized_path, excluded):
                return True
    
    return False

