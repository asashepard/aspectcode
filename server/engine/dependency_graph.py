"""
Dependency Graph for Aspect Code Engine

Provides minimal impact analysis to answer the question: 
"When a method or file is changed or deleted, what other methods or files are affected?"

This module implements a simple but powerful dependency tracking system that enables
tier 2 rules to perform cross-file analysis and impact assessment.
"""

from collections import defaultdict
from typing import Dict, Set, List, Optional
import logging

logger = logging.getLogger(__name__)


class DependencyGraph:
    """
    Tracks cross-file symbol dependencies for impact analysis.
    
    This class provides the core capability to understand what symbols depend 
    on what other symbols across the entire codebase, enabling sophisticated
    impact analysis when considering changes.
    """
    
    def __init__(self):
        # Maps symbol -> set of symbols that depend on it
        # e.g., "user.py::User" -> {"controller.py::UserController", "service.py::UserService"}
        self._dependents: Dict[str, Set[str]] = defaultdict(set)
        
        # Maps symbol -> set of symbols it depends on  
        # e.g., "controller.py::UserController" -> {"user.py::User", "service.py::UserService"}
        self._dependencies: Dict[str, Set[str]] = defaultdict(set)
        
        # Cache for performance
        self._symbol_count = 0
        self._dependency_count = 0
    
    def add_dependency(self, dependent: str, dependency: str):
        """
        Record that 'dependent' uses/depends on 'dependency'.
        
        Args:
            dependent: The symbol that depends on something (e.g., "controller.py::create_user")
            dependency: The symbol being depended upon (e.g., "user.py::User")
        """
        if dependent == dependency:
            return  # Ignore self-dependencies
            
        self._dependents[dependency].add(dependent)
        self._dependencies[dependent].add(dependency)
        self._dependency_count += 1
    
    def get_impacted_symbols(self, changed_symbol: str) -> Set[str]:
        """
        Get all symbols that would be affected if changed_symbol is modified.
        
        This is the core method for impact analysis - it tells you what would
        break if you change or delete a specific symbol.
        
        Args:
            changed_symbol: The symbol being changed (e.g., "user.py::User")
            
        Returns:
            Set of symbols that depend on the changed symbol
        """
        return self._dependents.get(changed_symbol, set()).copy()
    
    def get_dependencies_of(self, symbol: str) -> Set[str]:
        """
        Get all symbols that this symbol depends on.
        
        Args:
            symbol: The symbol to analyze (e.g., "controller.py::UserController")
            
        Returns:
            Set of symbols that this symbol depends on
        """
        return self._dependencies.get(symbol, set()).copy()
    
    def get_impacted_files(self, changed_file: str, symbol_index) -> Set[str]:
        """
        Get all files that would be affected if changed_file is modified.
        
        Args:
            changed_file: The file being changed (e.g., "models/user.py")
            symbol_index: Symbol index to look up symbols by file
            
        Returns:
            Set of file paths that would be affected
        """
        affected_files = set()
        
        # Get all symbols in the changed file
        file_symbols = symbol_index.find_by_file(changed_file)
        
        # For each symbol in the file, find what depends on it
        for symbol in file_symbols:
            impacted_symbols = self.get_impacted_symbols(symbol.qualified_name)
            
            # Find the files containing the impacted symbols
            for impacted_symbol in impacted_symbols:
                # Extract file path from qualified name (format: "path/file.py::symbol")
                if "::" in impacted_symbol:
                    file_path = impacted_symbol.split("::")[0]
                    affected_files.add(file_path)
        
        return affected_files
    
    def get_critical_dependencies(self, threshold: int = 5) -> List[Dict[str, any]]:
        """
        Get symbols that have many dependents (potential single points of failure).
        
        Args:
            threshold: Minimum number of dependents to be considered critical
            
        Returns:
            List of critical dependencies with metadata
        """
        critical = []
        
        for symbol, dependents in self._dependents.items():
            if len(dependents) >= threshold:
                critical.append({
                    "symbol": symbol,
                    "dependent_count": len(dependents),
                    "dependents": list(dependents),
                    "risk_level": self._classify_risk_level(len(dependents))
                })
        
        # Sort by dependent count (most critical first)
        critical.sort(key=lambda x: x["dependent_count"], reverse=True)
        return critical
    
    def get_unused_symbols(self, symbol_index) -> List[Dict[str, any]]:
        """
        Find symbols that appear to be unused (no dependents).
        
        Args:
            symbol_index: Symbol index to get symbol details
            
        Returns:
            List of potentially unused symbols
        """
        unused = []
        
        # Get all symbols from the symbol index
        all_symbols = symbol_index._symbols if hasattr(symbol_index, '_symbols') else []
        
        for symbol in all_symbols:
            # Only check public symbols that could be unused
            if (symbol.visibility == 'public' and 
                symbol.kind in ['function', 'class', 'method'] and
                not symbol.name.startswith('_')):  # Skip private symbols
                
                # Check if anything depends on this symbol
                dependents = self.get_impacted_symbols(symbol.qualified_name)
                
                if len(dependents) == 0:
                    unused.append({
                        "symbol": symbol.qualified_name,
                        "name": symbol.name,
                        "kind": symbol.kind,
                        "file": symbol.file_path,
                        "confidence": "high" if not symbol.name.startswith('test') else "medium"
                    })
        
        return unused
    
    def get_dependency_chain(self, start_symbol: str, max_depth: int = 3) -> Dict[str, any]:
        """
        Analyze the full dependency chain from a starting symbol.
        
        Args:
            start_symbol: Symbol to start the chain analysis from
            max_depth: Maximum depth to traverse
            
        Returns:
            Nested structure showing the dependency chain
        """
        visited = set()
        
        def build_chain(current_symbol: str, depth: int) -> List[Dict[str, any]]:
            if depth >= max_depth or current_symbol in visited:
                return []
            
            visited.add(current_symbol)
            dependencies = self.get_dependencies_of(current_symbol)
            
            chain = []
            for dep in dependencies:
                chain.append({
                    "symbol": dep,
                    "depth": depth + 1,
                    "dependencies": build_chain(dep, depth + 1)
                })
            
            return chain
        
        return {
            "start_symbol": start_symbol,
            "max_depth": max_depth,
            "dependency_chain": build_chain(start_symbol, 0)
        }
    
    def _classify_risk_level(self, dependent_count: int) -> str:
        """Classify risk level based on number of dependents"""
        if dependent_count > 20:
            return "critical"
        elif dependent_count > 10:
            return "high"
        elif dependent_count > 5:
            return "medium"
        else:
            return "low"
    
    def get_stats(self) -> Dict[str, any]:
        """Get statistics about the dependency graph"""
        total_symbols = len(self._dependents) + len(self._dependencies)
        unique_symbols = len(set(list(self._dependents.keys()) + list(self._dependencies.keys())))
        
        return {
            "unique_symbols": unique_symbols,
            "total_dependencies": self._dependency_count,
            "symbols_with_dependents": len(self._dependents),
            "symbols_with_dependencies": len(self._dependencies),
            "avg_dependents_per_symbol": (
                sum(len(deps) for deps in self._dependents.values()) / len(self._dependents)
                if self._dependents else 0
            ),
            "avg_dependencies_per_symbol": (
                sum(len(deps) for deps in self._dependencies.values()) / len(self._dependencies) 
                if self._dependencies else 0
            )
        }


def build_dependency_graph(files: List[str], adapters: Dict, symbol_index) -> DependencyGraph:
    """
    Build a dependency graph by analyzing cross-file symbol usage.
    
    This function examines all files in the project and builds a comprehensive
    dependency graph showing which symbols depend on which other symbols.
    
    Args:
        files: List of file paths to analyze
        adapters: Language adapters for parsing different file types
        symbol_index: Symbol index containing all symbols in the project
        
    Returns:
        DependencyGraph instance with all dependencies mapped
    """
    logger.info(f"Building dependency graph for {len(files)} files")
    dep_graph = DependencyGraph()
    
    # Clear and rebuild the symbol name index for O(1) lookups
    clear_symbol_name_index()
    _build_symbol_name_index(symbol_index)
    
    # Process each file to find cross-file dependencies
    for file_path in files:
        try:
            # Get the appropriate language adapter
            adapter = _get_adapter_for_file(file_path, adapters)
            if not adapter:
                logger.debug(f"No adapter found for file: {file_path}")
                continue
            
            # Read and parse the file
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except (UnicodeDecodeError, FileNotFoundError) as e:
                logger.debug(f"Could not read file {file_path}: {e}")
                continue
            
            # Parse the file to get the syntax tree
            # Ensure content is bytes for tree-sitter
            if isinstance(content, bytes):
                content_bytes = content
            elif isinstance(content, str):
                content_bytes = content.encode('utf-8')
            else:
                logger.debug(f"Unexpected content type for {file_path}: {type(content)}")
                continue
            
            tree = adapter.parse(content_bytes)
            if not tree:
                continue
            
            # Extract dependencies from this file
            _extract_file_dependencies(file_path, tree, adapter, symbol_index, dep_graph)
            
        except Exception as e:
            logger.warning(f"Error processing file {file_path} for dependency graph: {e}")
            continue
    
    stats = dep_graph.get_stats()
    logger.info(f"Dependency graph built: {stats['unique_symbols']} symbols, {stats['total_dependencies']} dependencies")
    
    return dep_graph


def _get_adapter_for_file(file_path: str, adapters: Dict):
    """Get the appropriate language adapter for a file"""
    # Map file extensions to adapter names
    extension_map = {
        '.py': 'python',
        '.ts': 'typescript', 
        '.tsx': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.java': 'java',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'c',
        '.h': 'c',
        '.hpp': 'cpp',
        '.cs': 'csharp',
        '.go': 'go',
        '.rs': 'rust'
    }
    
    for ext, adapter_name in extension_map.items():
        if file_path.lower().endswith(ext):
            return adapters.get(adapter_name)
    
    return None


def _extract_file_dependencies(file_path: str, tree, adapter, symbol_index, dep_graph: DependencyGraph):
    """
    Extract dependencies from a single file and add them to the dependency graph.
    
    This function analyzes the syntax tree of a file to find:
    1. Symbols defined in this file  
    2. Symbols used/referenced from other files
    3. Creates dependency relationships between them
    """
    # Get symbols defined in this file
    file_symbols = symbol_index.find_by_file(file_path)
    file_symbol_names = {symbol.name: symbol.qualified_name for symbol in file_symbols}
    
    # Build interval tree for fast location lookup
    intervals = _build_symbol_intervals(file_symbols)
    
    # Use adapter to find imports and symbol usage
    root_node = tree.root_node
    
    # Find imports/includes
    imports = _extract_imports(root_node, adapter, file_path)
    
    # Find symbol usages throughout the file
    usages = _extract_symbol_usages(root_node, adapter, file_path)
    
    # Limit usages to prevent O(n^2) blowup on large files
    MAX_USAGES_PER_FILE = 500
    if len(usages) > MAX_USAGES_PER_FILE:
        usages = usages[:MAX_USAGES_PER_FILE]
    
    # Create dependencies based on imports and usages
    for usage in usages:
        # Find which symbol in this file is using the external symbol (O(log n) with intervals)
        usage_location = usage.get('start_byte', 0)
        containing_symbol = _find_containing_symbol_fast(usage_location, intervals) if intervals else None
        
        if containing_symbol:
            # Look for the used symbol in the symbol index (O(1) with name index)
            used_symbol = _resolve_used_symbol(usage['name'], imports, symbol_index, file_path)
            
            if used_symbol and used_symbol.qualified_name != containing_symbol.qualified_name:
                # Create dependency: containing_symbol depends on used_symbol
                dep_graph.add_dependency(containing_symbol.qualified_name, used_symbol.qualified_name)


def _extract_imports(root_node, adapter, file_path: str) -> List[Dict[str, str]]:
    """Extract import statements from a file"""
    imports = []
    
    # This is a simplified extraction - in a full implementation,
    # each language adapter would provide methods for this
    
    # For Python files
    if file_path.endswith('.py'):
        imports.extend(_extract_python_imports(root_node))
    # For TypeScript/JavaScript files  
    elif file_path.endswith(('.ts', '.tsx', '.js', '.jsx')):
        imports.extend(_extract_ts_imports(root_node))
    
    return imports


def _extract_python_imports(root_node) -> List[Dict[str, str]]:
    """Extract Python import statements"""
    imports = []
    
    def traverse(node):
        try:
            if node.type == 'import_statement':
                # import module
                for child in node.children:
                    if child.type == 'dotted_name':
                        module_text = child.text
                        if isinstance(module_text, bytes):
                            module_text = module_text.decode('utf-8')
                        imports.append({
                            'module': module_text,
                            'alias': None,
                            'type': 'module'
                        })
            elif node.type == 'import_from_statement':
                # from module import name
                module = None
                names = []
                for child in node.children:
                    if child.type == 'dotted_name' and not module:
                        module_text = child.text
                        if isinstance(module_text, bytes):
                            module_text = module_text.decode('utf-8')
                        module = module_text
                    elif child.type == 'import_list':
                        for name_node in child.children:
                            if name_node.type == 'dotted_name':
                                name_text = name_node.text
                                if isinstance(name_text, bytes):
                                    name_text = name_text.decode('utf-8')
                                names.append(name_text)
                
                for name in names:
                    imports.append({
                        'module': module,
                        'name': name,
                        'type': 'from_import'
                    })
            
            for child in node.children:
                traverse(child)
        except Exception as e:
            # Skip any problematic nodes
            pass
    
    traverse(root_node)
    return imports


def _extract_ts_imports(root_node) -> List[Dict[str, str]]:
    """Extract TypeScript/JavaScript import statements"""
    imports = []
    
    def traverse(node):
        try:
            if node.type == 'import_statement':
                # Parse import statement
                module_path = None
                imported_names = []
                
                for child in node.children:
                    if child.type == 'string' and module_path is None:
                        # Remove quotes from module path
                        module_text = child.text
                        if isinstance(module_text, bytes):
                            module_text = module_text.decode('utf-8')
                        module_path = module_text.strip('"\'')
                    elif child.type == 'import_clause':
                        # Extract imported names
                        imported_names.extend(_extract_import_names(child))
                
                for name in imported_names:
                    imports.append({
                        'module': module_path,
                        'name': name,
                        'type': 'es6_import'
                    })
            
            for child in node.children:
                traverse(child)
        except Exception as e:
            # Skip problematic nodes
            pass
    
    traverse(root_node)
    return imports


def _extract_import_names(import_clause_node) -> List[str]:
    """Extract imported names from an import clause"""
    names = []
    
    def traverse(node):
        try:
            if node.type == 'identifier':
                name_text = node.text
                if isinstance(name_text, bytes):
                    name_text = name_text.decode('utf-8')
                names.append(name_text)
            
            for child in node.children:
                traverse(child)
        except Exception as e:
            # Skip problematic nodes
            pass
    
    traverse(import_clause_node)
    return names


def _extract_symbol_usages(root_node, adapter, file_path: str) -> List[Dict[str, any]]:
    """Extract symbol usage from a file"""
    usages = []
    
    def traverse(node):
        try:
            # Look for identifiers that could be symbol references
            if node.type == 'identifier':
                symbol_text = node.text
                if isinstance(symbol_text, bytes):
                    symbol_text = symbol_text.decode('utf-8')
                symbol_name = symbol_text
                
                # Skip very common names that are likely not external symbols
                if symbol_name not in ['self', 'this', 'return', 'if', 'else', 'for', 'while']:
                    usages.append({
                        'name': symbol_name,
                        'start_byte': node.start_byte,
                        'end_byte': node.end_byte
                    })
            
            # Also track property access for member expressions like Class.method()
            # This captures usages like ItemsService.readItems() where readItems is a method
            elif node.type == 'property_identifier':
                symbol_text = node.text
                if isinstance(symbol_text, bytes):
                    symbol_text = symbol_text.decode('utf-8')
                symbol_name = symbol_text
                
                usages.append({
                    'name': symbol_name,
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'is_property': True  # Mark as property access
                })
            
            for child in node.children:
                traverse(child)
        except Exception as e:
            # Skip problematic nodes
            pass
    
    traverse(root_node)
    return usages


def _build_symbol_intervals(file_symbols):
    """Build a sorted list of (start_byte, end_byte, symbol) for efficient lookup"""
    intervals = [(s.start_byte, s.end_byte, s) for s in file_symbols if hasattr(s, 'start_byte') and hasattr(s, 'end_byte')]
    intervals.sort(key=lambda x: x[0])
    return intervals


def _find_containing_symbol_fast(location: int, intervals):
    """Find which symbol contains the given byte location using binary search"""
    if not intervals:
        return None
    
    # Binary search for candidate
    lo, hi = 0, len(intervals) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        start, end, symbol = intervals[mid]
        if start <= location <= end:
            return symbol
        elif location < start:
            hi = mid - 1
        else:
            lo = mid + 1
    
    # Check adjacent intervals (overlapping symbols)
    for i in range(max(0, lo - 1), min(len(intervals), lo + 2)):
        start, end, symbol = intervals[i]
        if start <= location <= end:
            return symbol
    
    return None


def _find_containing_symbol(location: int, file_symbols):
    """Find which symbol contains the given byte location (legacy fallback)"""
    for symbol in file_symbols:
        if hasattr(symbol, 'start_byte') and hasattr(symbol, 'end_byte'):
            if symbol.start_byte <= location <= symbol.end_byte:
                return symbol
    return None


# Global cache for symbol name -> symbols mapping
_symbol_name_index: Dict[str, List] = {}
_symbol_name_index_built = False


def _build_symbol_name_index(symbol_index):
    """Build an index from symbol name to list of symbols for O(1) lookup"""
    global _symbol_name_index, _symbol_name_index_built
    
    if _symbol_name_index_built:
        return
    
    _symbol_name_index.clear()
    symbols = symbol_index._symbols if hasattr(symbol_index, '_symbols') else []
    
    for symbol in symbols:
        name = symbol.name
        if name not in _symbol_name_index:
            _symbol_name_index[name] = []
        _symbol_name_index[name].append(symbol)
    
    _symbol_name_index_built = True


def clear_symbol_name_index():
    """Clear the symbol name index (call when symbol index changes)"""
    global _symbol_name_index, _symbol_name_index_built
    _symbol_name_index.clear()
    _symbol_name_index_built = False


def _resolve_used_symbol(symbol_name: str, imports: List[Dict], symbol_index, current_file: str):
    """Resolve a used symbol name to an actual symbol in the index - OPTIMIZED"""
    global _symbol_name_index, _symbol_name_index_built
    
    # Build index if not already built
    if not _symbol_name_index_built:
        _build_symbol_name_index(symbol_index)
    
    # O(1) lookup by name
    candidates = _symbol_name_index.get(symbol_name, [])
    
    # Find first match from different file
    for symbol in candidates:
        if symbol.file_path != current_file:
            return symbol
    
    # No match found
    return None


