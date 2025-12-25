"""
CLI runner for the Aspect Code Tree-sitter engine.

This module provides the main CLI entry point for loading adapters,
parsing files, running rules, and outputting results.
"""

import argparse
import json
import sys
import os
import time
import concurrent.futures
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path

from .types import RuleContext, Finding
from .registry import register_adapter, get_adapter, get_enabled_rules, discover_rules, discover_alpha_rules_only, get_rule_ids, get_all_adapters, is_user_facing_rule
from .config import load_config, find_config_file, EngineConfig
from .profiles import RuleProfile, validate_profile, get_default_profile
from .schema import (validate_findings, validate_runner_output, findings_to_json, 
                    findings_to_legacy_violations, PROTOCOL_VERSION, ENGINE_VERSION)
from .scopes import build_scopes
from .suppressions import filter_suppressed_findings
from .resolver import PythonResolver
from .project_graph import ImportGraph, build_import_graph_signature
from .symbol_index import ProjectSymbolIndex, build_symbol_index
from .dependency_graph import DependencyGraph, build_dependency_graph
from .file_filter import should_analyze_file, is_excluded_path, filter_files

# Global scope cache: (file_path, mtime) -> ScopeGraph
_scope_cache = {}

# Global project graph cache: signature -> (resolver, import_graph)
_project_graph_cache = {}

# Global AST cache: (file_path, mtime) -> (tree, language)
# Shared across languages - e.g., JS adapter can use cached TS parse for .js files
_ast_cache = {}
_AST_CACHE_MAX_SIZE = 500  # Keep last 500 parsed files

# Per-rule timing data: rule_id -> {"total_ms": float, "call_count": int, "files": int}
_rule_timing = {}
_timing_enabled = False

def enable_rule_timing():
    """Enable per-rule timing collection."""
    global _timing_enabled
    _timing_enabled = True
    
def disable_rule_timing():
    """Disable per-rule timing collection."""
    global _timing_enabled
    _timing_enabled = False
    
def get_rule_timing() -> Dict[str, Any]:
    """Get collected rule timing data."""
    return _rule_timing.copy()

def clear_rule_timing():
    """Clear collected rule timing data."""
    global _rule_timing
    _rule_timing = {}

def get_cached_ast(file_path: str, adapter) -> Any:
    """
    Get cached AST for a file, or parse and cache it.
    
    This allows sharing parsed ASTs across language processing.
    For example, when processing JS after TS, we can reuse the parse
    if both adapters can handle the file.
    
    Args:
        file_path: Absolute path to the file
        adapter: Language adapter with parse() method
        
    Returns:
        Parsed tree, or None on error
    """
    global _ast_cache
    
    try:
        file_stat = os.stat(file_path)
        cache_key = (file_path, file_stat.st_mtime)
        
        # Check if we have a cached AST
        if cache_key in _ast_cache:
            return _ast_cache[cache_key]
        
        # Parse the file
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        tree = adapter.parse(content)
        
        # Cache the result
        _ast_cache[cache_key] = tree
        
        # Clean up old cache entries (simple LRU: keep last N)
        if len(_ast_cache) > _AST_CACHE_MAX_SIZE:
            oldest_keys = list(_ast_cache.keys())[:-_AST_CACHE_MAX_SIZE]
            for old_key in oldest_keys:
                del _ast_cache[old_key]
        
        return tree
        
    except Exception as e:
        print(f"Warning: Failed to parse {file_path}: {e}", file=sys.stderr)
        return None

def clear_ast_cache():
    """Clear the AST cache."""
    global _ast_cache
    _ast_cache = {}


def setup_adapters():
    """Set up and register language adapters."""
    try:
        # Import and register Python adapter
        from .python_adapter import default_python_adapter
        register_adapter(default_python_adapter.language_id, default_python_adapter)
    except ImportError as e:
        print(f"Warning: Could not load Python adapter: {e}", file=sys.stderr)
    
    try:
        # Import and register TypeScript/JavaScript adapters
        from .typescript_adapter import default_typescript_adapter
        from .javascript_adapter import default_javascript_adapter
        register_adapter(default_typescript_adapter.language_id, default_typescript_adapter)
        register_adapter(default_javascript_adapter.language_id, default_javascript_adapter)
    except ImportError as e:
        print(f"Warning: Could not load TypeScript/JavaScript adapters: {e}", file=sys.stderr)
    
    try:
        # Import and register C/C++ adapters
        from .c_adapter import default_c_adapter
        from .cpp_adapter import default_cpp_adapter
        register_adapter(default_c_adapter.language_id, default_c_adapter)
        register_adapter(default_cpp_adapter.language_id, default_cpp_adapter)
    except ImportError as e:
        print(f"Warning: Could not load C/C++ adapters: {e}", file=sys.stderr)
    
    try:
        # Import and register other language adapters if available
        from .java_adapter import default_java_adapter
        register_adapter(default_java_adapter.language_id, default_java_adapter)
    except ImportError as e:
        print(f"Warning: Could not load Java adapter: {e}", file=sys.stderr)
    
    try:
        from .go_adapter import default_go_adapter
        register_adapter(default_go_adapter.language_id, default_go_adapter)
    except ImportError as e:
        print(f"Warning: Could not load Go adapter: {e}", file=sys.stderr)
    
    try:
        from .csharp_adapter import default_csharp_adapter
        register_adapter(default_csharp_adapter.language_id, default_csharp_adapter)
    except ImportError as e:
        print(f"Warning: Could not load C# adapter: {e}", file=sys.stderr)


def collect_files(paths: List[str], language: str, extensions: Tuple[str, ...] = None) -> List[str]:
    """Collect files to analyze based on paths, language, and optional extensions override.
    
    Automatically excludes vendor/generated directories (node_modules, .venv, dist, etc.)
    using the centralized file_filter module.
    """
    adapter = get_adapter(language)
    if not adapter:
        print(f"Error: No adapter found for language '{language}'", file=sys.stderr)
        return []
    
    # Use provided extensions or adapter defaults
    file_extensions = extensions or adapter.file_extensions
    
    all_files = []
    for path in paths:
        path_obj = Path(path)
        if path_obj.is_file():
            # Single file - check if it matches the extensions and isn't excluded
            abs_path = str(path_obj.absolute())
            if any(path.endswith(ext) for ext in file_extensions) and not is_excluded_path(abs_path):
                all_files.append(abs_path)
        elif path_obj.is_dir():
            # Directory - recursively find matching files
            for ext in file_extensions:
                pattern = f"**/*{ext}"
                files = list(path_obj.rglob(pattern))
                for f in files:
                    if f.is_file():
                        abs_path = str(f.absolute())
                        # Filter out excluded directories
                        if not is_excluded_path(abs_path):
                            all_files.append(abs_path)
        else:
            print(f"Warning: Path '{path}' does not exist", file=sys.stderr)
    
    return sorted(set(all_files))  # Remove duplicates and sort


def debug_adapter_for_file(file_path: str, content: str, adapter, debug_output: List[str]) -> None:
    """Debug adapter capabilities for a single file."""
    try:
        tree = adapter.parse(content)
        
        # Count various language features
        counts = {}
        
        # Python-specific debugging
        if hasattr(adapter, 'iter_imports'):
            imports = list(adapter.iter_imports(tree))
            counts['imports'] = len(imports)
            
        if hasattr(adapter, 'iter_functions'):
            functions = list(adapter.iter_functions(tree))
            counts['functions'] = len(functions)
            
        if hasattr(adapter, 'iter_await_expressions'):
            awaits = list(adapter.iter_await_expressions(tree))
            counts['await_expressions'] = len(awaits)
        
        # TypeScript/JavaScript-specific debugging  
        if hasattr(adapter, 'iter_binary_ops'):
            binary_ops = list(adapter.iter_binary_ops(tree))
            counts['binary_ops'] = len(binary_ops)
        
        # Test enclosing function capability
        if hasattr(adapter, 'enclosing_function'):
            try:
                mid_byte = len(content) // 2
                enclosing = adapter.enclosing_function(tree, mid_byte)
                counts['enclosing_function_test'] = 'found' if enclosing else 'none'
            except Exception:
                counts['enclosing_function_test'] = 'error'
        
        debug_line = f"  {file_path}: {counts}"
        debug_output.append(debug_line)
        
    except Exception as e:
        debug_output.append(f"  {file_path}: ERROR - {e}")


def analyze_file(file_path: str, language: str, rules: List, config: EngineConfig, 
                debug_adapter: bool, debug_output: List[str], debug_scopes: bool = False,
                project_graph: Any = None, content: Optional[str] = None) -> Tuple[List[Finding], float]:
    """Analyze a single file and return findings and parse time.
    
    Args:
        file_path: Path to the file (used for context even if content is provided)
        language: Language to analyze
        rules: List of rules to run
        config: Engine configuration
        debug_adapter: Whether to debug adapter capabilities
        debug_output: List to collect debug output
        debug_scopes: Whether to debug scopes
        project_graph: Optional project graph for Tier 2 rules
        content: Optional file content (if None, reads from disk)
    """
    adapter = get_adapter(language)
    if not adapter:
        return [], 0.0
    
    start_time = time.time()
    
    try:
        # Use provided content or read from disk
        if content is None:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        
        # Parse the file - pass file_path for language-specific parsing (e.g., TSX vs TS)
        parse_start = time.time()
        if hasattr(adapter, 'set_current_file'):
            adapter.set_current_file(file_path)
        # Try to pass file_path to parse() if supported
        try:
            tree = adapter.parse(content, file_path=file_path)
        except TypeError:
            # Fallback for adapters that don't accept file_path
            tree = adapter.parse(content)
        parse_time = (time.time() - parse_start) * 1000
        
        # Debug adapter if requested
        if debug_adapter:
            debug_adapter_for_file(file_path, content, adapter, debug_output)
        
        # Check if any rule needs scopes
        needs_scopes = any(getattr(rule, 'requires', None) and getattr(rule.requires, 'scopes', False) for rule in rules)
        scopes = None
        
        if needs_scopes:
            # Check scope cache
            try:
                file_stat = os.stat(file_path)
                cache_key = (file_path, file_stat.st_mtime)
                
                if cache_key in _scope_cache:
                    scopes = _scope_cache[cache_key]
                else:
                    # Compute scopes and cache
                    scopes = build_scopes(adapter, tree, content)
                    _scope_cache[cache_key] = scopes
                    
                    # Clean up old cache entries (simple LRU: keep last 100)
                    if len(_scope_cache) > 100:
                        oldest_keys = list(_scope_cache.keys())[:-100]
                        for old_key in oldest_keys:
                            del _scope_cache[old_key]
                    
                    # Debug scopes if requested
                    if debug_scopes and scopes:
                        stats = scopes.get_stats()
                        print(f"[scopes] {file_path}: scopes={stats['scopes']} symbols={stats['symbols']} refs={stats['refs']} imports={stats['imports']}", file=sys.stderr)
                            
            except Exception as e:
                print(f"Warning: Failed to build scopes for {file_path}: {e}", file=sys.stderr)
                scopes = None
        
        # Create context for this file
        rule_config = config.language_configs.get(language, {}).copy()
        
        # Merge in rule-specific configs
        for rule in rules:
            rule_id = getattr(rule.meta, 'id', '')
            if rule_id in config.rule_configs:
                rule_config.update(config.rule_configs[rule_id])
        
        context = RuleContext(
            file_path=file_path,
            text=content,
            tree=tree,
            adapter=adapter,
            config=rule_config,
            scopes=scopes,  # Now populated when needed
            project_graph=project_graph  # Tier 2: (resolver, import_graph)
        )
        
        # Apply tree-sitter compatibility layer for better rule compatibility
        try:
            from .tree_sitter_compat import make_compatible_context
            enhanced_context = make_compatible_context(context)
        except Exception:
            # Fallback to original context if compatibility layer fails
            enhanced_context = context
        
        # Run each rule on this file
        findings = []
        for rule in rules:
            try:
                rule_id = getattr(rule.meta, 'id', 'unknown')
                
                # Per-rule file filtering: skip rules that shouldn't run on this file
                # (e.g., complexity rules on test files, certain rules on migrations)
                if not should_analyze_file(file_path, rule_id, language, content):
                    continue
                
                # Track rule timing if enabled
                rule_start = time.time() if _timing_enabled else 0
                
                rule_findings = list(rule.visit(enhanced_context))
                
                # Record timing
                if _timing_enabled:
                    rule_elapsed_ms = (time.time() - rule_start) * 1000
                    
                    if rule_id not in _rule_timing:
                        _rule_timing[rule_id] = {
                            "total_ms": 0.0,
                            "call_count": 0,
                            "findings_count": 0
                        }
                    
                    _rule_timing[rule_id]["total_ms"] += rule_elapsed_ms
                    _rule_timing[rule_id]["call_count"] += 1
                    _rule_timing[rule_id]["findings_count"] += len(rule_findings)
                
                # Apply severity overrides from config
                for finding in rule_findings:
                    # Apply configured severity if available
                    if config.rule_severities and finding.rule in config.rule_severities:
                        # Create new finding with overridden severity
                        finding = finding._replace(severity=config.rule_severities[finding.rule])
                    findings.append(finding)
                
                # Apply per-file limit
                if len(findings) >= config.max_findings_per_file:
                    findings = findings[:config.max_findings_per_file]
                    break
                    
            except Exception as e:
                print(f"Warning: Rule '{rule.meta.id}' failed on {file_path}: {e}", file=sys.stderr)
        
        # Apply suppression filtering
        findings = filter_suppressed_findings(findings, content)
        
        return findings, parse_time
        
    except Exception as e:
        print(f"Warning: Failed to analyze {file_path}: {e}", file=sys.stderr)
        return [], 0.0


def build_project_graph(files: List[str], language: str, config: EngineConfig, 
                       debug_resolver: bool = False) -> Any:
    """
    Build project graph (resolver + import graph) if needed.
    
    Returns:
        Tuple of (resolver, import_graph, symbol_index) or None if language not supported
    """
    # Import resolvers
    from .javascript_resolver import JavaScriptResolver
    from .typescript_resolver import TypeScriptResolver
    from .java_resolver import JavaResolver
    from .csharp_resolver import CSharpResolver
    
    # Select resolver based on language
    resolver_class = None
    if language == "python":
        resolver_class = PythonResolver
    elif language == "javascript":
        resolver_class = JavaScriptResolver
    elif language == "typescript":
        resolver_class = TypeScriptResolver
    elif language == "java":
        resolver_class = JavaResolver
    elif language == "csharp":
        resolver_class = CSharpResolver
    else:
        # Language not yet supported for project graph
        return None
    
    # Build cache signature
    signature = build_import_graph_signature(files)
    
    # Check cache
    if signature in _project_graph_cache:
        return _project_graph_cache[signature]
    
    adapter = get_adapter(language)
    if not adapter:
        return None
    
    # Build resolver with project roots (directories containing files)
    project_roots = []
    for file_path in files:
        directory = os.path.dirname(os.path.abspath(file_path))
        if directory not in project_roots:
            project_roots.append(directory)
    
    # Find common project root if possible
    if len(project_roots) > 1:
        common_root = os.path.commonpath(project_roots)
        if common_root and common_root != os.path.dirname(common_root):  # Not filesystem root
            project_roots = [common_root]
    
    # Get extra paths from config (language-specific)
    resolver_config = config.language_configs.get(language, {}).get("resolver", {})
    
    # For Python: extra_sys_path
    # For JS/TS: extra_paths (additional search directories)
    extra_param = resolver_config.get("extra_sys_path" if language == "python" else "extra_paths", [])
    
    resolver = resolver_class(project_roots, extra_param)
    
    # Attach resolver to adapter for module_name_for_file calls
    adapter._resolver = resolver
    
    # Build import graph
    import_graph = ImportGraph()
    
    for file_path in files:
        try:
            # Read and parse file
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            tree = adapter.parse(content)
            
            # Get canonical module name for this file
            file_module = resolver.canonical_module_for_file(file_path)
            if file_module:
                import_graph.add_module(file_module, file_path)
                
                # Extract imports
                imports = adapter.iter_imports(tree)
                
                for import_info in imports:
                    module_name = import_info.module
                    level = getattr(import_info, 'level', 0)
                    names = import_info.names or []
                    
                    # Handle different import patterns
                    if names and not import_info.is_wildcard:
                        # from . import a, b  or  from .module import func
                        # Create edges to each named import
                        for name in names:
                            if level > 0:
                                # Relative import: from . import b -> resolve ".b"
                                resolve_module = "." * level + module_name
                                if module_name:
                                    resolve_module += "." + name
                                else:
                                    resolve_module += name
                            else:
                                # Absolute import: from module import func -> resolve "module"
                                if module_name:
                                    resolve_module = module_name
                                else:
                                    resolve_module = name
                            
                            # Resolve the import
                            result = resolver.resolve(file_path, resolve_module, None)
                            
                            if debug_resolver:
                                print(f"[resolver] {file_path}: {resolve_module} -> {result.kind} {result.module} ({result.file_path or 'no file'})", file=sys.stderr)
                                if result.meta.get("tried_paths"):
                                    for tried_path in result.meta["tried_paths"][:3]:  # Show first 3
                                        print(f"[resolver]   tried: {tried_path}", file=sys.stderr)
                            
                            # Add to graph
                            target_module = result.module
                            
                            # Add target module to graph
                            if result.kind in ("module_file", "package_init", "namespace_pkg"):
                                # Project module
                                import_graph.add_module(target_module, result.file_path)
                            elif result.kind in ("builtin", "stdlib", "third_party"):
                                # External module
                                import_graph.add_module(target_module, None)
                            # Skip "missing" modules (don't add edges for them)
                            
                            # Add edge if target resolved
                            if result.kind != "missing":
                                import_graph.add_edge(file_module, target_module)
                    else:
                        # import module  or  from module import *
                        # Build full module name for relative imports
                        if level > 0:
                            # Relative import
                            resolve_module = "." * level + module_name
                        else:
                            resolve_module = module_name
                        
                        # Resolve the import
                        result = resolver.resolve(file_path, resolve_module, names)
                        
                        if debug_resolver:
                            print(f"[resolver] {file_path}: {resolve_module} -> {result.kind} {result.module} ({result.file_path or 'no file'})", file=sys.stderr)
                            if result.meta.get("tried_paths"):
                                for tried_path in result.meta["tried_paths"][:3]:  # Show first 3
                                    print(f"[resolver]   tried: {tried_path}", file=sys.stderr)
                        
                        # Add to graph
                        target_module = result.module
                        
                        # Add target module to graph
                        if result.kind in ("module_file", "package_init", "namespace_pkg"):
                            # Project module
                            import_graph.add_module(target_module, result.file_path)
                        elif result.kind in ("builtin", "stdlib", "third_party"):
                            # External module
                            import_graph.add_module(target_module, None)
                        # Skip "missing" modules (don't add edges for them)
                        
                        # Add edge if target resolved
                        if result.kind != "missing":
                            import_graph.add_edge(file_module, target_module)
        
        except Exception as e:
            print(f"Warning: Failed to process imports for {file_path}: {e}", file=sys.stderr)
    
    # Build symbol index for all supported languages
    symbol_index = ProjectSymbolIndex()
    try:
        # Get all available adapters
        all_adapters = get_all_adapters()
        
        # Default excluded paths for common non-source directories
        excluded_paths = {
            "node_modules", ".venv", "venv", "env", "vendor", "third_party", 
            "external", "lib", "libs", "dependencies", ".git", "__pycache__",
            "build", "dist", "target", "out", "bin", ".pytest_cache", "coverage",
            "*.min.js", "*.bundle.js"
        }
        
        # Add any user-configured excluded paths
        if hasattr(config, 'symbol_index') and config.symbol_index.get('excluded_paths'):
            excluded_paths.update(config.symbol_index['excluded_paths'])
        
        # Build the index
        symbol_index = build_symbol_index(files, all_adapters, excluded_paths)
        
        if symbol_index:
            stats = symbol_index.get_stats()
            print(f"Built symbol index: {stats['total_symbols']} symbols across {stats['files_indexed']} files", file=sys.stderr)
        
    except Exception as e:
        print(f"Warning: Failed to build symbol index: {e}", file=sys.stderr)
        # Continue with empty index rather than failing
        symbol_index = ProjectSymbolIndex()
    
    # Build dependency graph if enabled
    dependency_graph = None
    if config.enable_dependency_tracking:
        try:
            print("Building dependency graph for impact analysis...", file=sys.stderr)
            dependency_graph = build_dependency_graph(files, all_adapters, symbol_index)
            dep_stats = dependency_graph.get_stats()
            print(f"Built dependency graph: {dep_stats['unique_symbols']} symbols, {dep_stats['total_dependencies']} dependencies", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Failed to build dependency graph: {e}", file=sys.stderr)
            # Continue without dependency tracking rather than failing
            dependency_graph = None
    
    # Determine project graph format based on configuration
    if config.enable_dependency_tracking and dependency_graph is not None:
        # Enhanced format: dictionary with explicit components
        project_graph = {
            'resolver': resolver,
            'import_graph': import_graph,
            'symbol_index': symbol_index,
            'dependency_graph': dependency_graph
        }
    else:
        # Legacy format: tuple (backwards compatible)
        project_graph = (resolver, import_graph, symbol_index)
    
    _project_graph_cache[signature] = project_graph
    
    # Clean up old cache entries (simple LRU: keep last 10)
    if len(_project_graph_cache) > 10:
        oldest_keys = list(_project_graph_cache.keys())[:-10]
        for old_key in oldest_keys:
            del _project_graph_cache[old_key]
    
    return project_graph


def build_unified_jsts_project_graph(js_files: List[str], ts_files: List[str], 
                                      config: EngineConfig, debug_resolver: bool = False) -> Any:
    """
    Build a unified project graph for JavaScript and TypeScript files together.
    
    This is more efficient than building separate graphs because:
    1. JS and TS share the same module system (ES modules / CommonJS)
    2. TypeScript can import JavaScript and vice versa
    3. We only need to walk directories once
    4. Symbol index is built once for all files
    
    Args:
        js_files: List of JavaScript file paths
        ts_files: List of TypeScript file paths
        config: Engine configuration
        debug_resolver: Enable debug output for resolver
        
    Returns:
        Dict with resolver, import_graph, symbol_index, and optionally dependency_graph
    """
    from .typescript_resolver import TypeScriptResolver
    
    # Combine all files
    all_files = list(set(js_files + ts_files))
    if not all_files:
        return None
    
    # Build cache signature for combined files
    signature = "jsts:" + build_import_graph_signature(all_files)
    
    # Check cache
    if signature in _project_graph_cache:
        return _project_graph_cache[signature]
    
    print(f"Building unified JS/TS project graph ({len(js_files)} JS + {len(ts_files)} TS = {len(all_files)} files)...")
    
    # Get adapters
    js_adapter = get_adapter("javascript")
    ts_adapter = get_adapter("typescript")
    
    if not js_adapter and not ts_adapter:
        return None
    
    # Build resolver with project roots
    project_roots = []
    for file_path in all_files:
        directory = os.path.dirname(os.path.abspath(file_path))
        if directory not in project_roots:
            project_roots.append(directory)
    
    # Find common project root if possible
    if len(project_roots) > 1:
        common_root = os.path.commonpath(project_roots)
        if common_root and common_root != os.path.dirname(common_root):
            project_roots = [common_root]
    
    # Get extra paths from config
    resolver_config = config.language_configs.get("typescript", {}).get("resolver", {})
    extra_param = resolver_config.get("extra_paths", [])
    
    # Use TypeScript resolver (it handles both TS and JS files)
    resolver = TypeScriptResolver(project_roots, extra_param)
    
    # Attach resolver to both adapters
    if js_adapter:
        js_adapter._resolver = resolver
    if ts_adapter:
        ts_adapter._resolver = resolver
    
    # Build import graph - process all files with appropriate adapter
    import_graph = ImportGraph()
    
    for file_path in all_files:
        try:
            # Select adapter based on file extension
            if file_path.endswith(('.ts', '.tsx')):
                adapter = ts_adapter
            else:
                adapter = js_adapter
            
            if not adapter:
                continue
            
            # Use cached AST if available
            tree = get_cached_ast(file_path, adapter)
            if tree is None:
                continue
            
            # Get canonical module name for this file
            file_module = resolver.canonical_module_for_file(file_path)
            if file_module:
                import_graph.add_module(file_module, file_path)
                
                # Extract imports
                imports = adapter.iter_imports(tree)
                
                for import_info in imports:
                    module_name = import_info.module
                    level = getattr(import_info, 'level', 0)
                    names = import_info.names or []
                    
                    # Handle different import patterns
                    if names and not import_info.is_wildcard:
                        for name in names:
                            if level > 0:
                                resolve_module = "." * level + module_name
                                if module_name:
                                    resolve_module += "." + name
                                else:
                                    resolve_module += name
                            else:
                                if module_name:
                                    resolve_module = module_name
                                else:
                                    resolve_module = name
                            
                            result = resolver.resolve(file_path, resolve_module, None)
                            
                            if debug_resolver:
                                print(f"[resolver] {file_path}: {resolve_module} -> {result.kind} {result.module}", file=sys.stderr)
                            
                            target_module = result.module
                            if result.kind in ("module_file", "package_init", "namespace_pkg"):
                                import_graph.add_module(target_module, result.file_path)
                            elif result.kind in ("builtin", "stdlib", "third_party"):
                                import_graph.add_module(target_module, None)
                            
                            if result.kind != "missing":
                                import_graph.add_edge(file_module, target_module)
                    else:
                        if level > 0:
                            resolve_module = "." * level + module_name
                        else:
                            resolve_module = module_name
                        
                        result = resolver.resolve(file_path, resolve_module, names)
                        
                        if debug_resolver:
                            print(f"[resolver] {file_path}: {resolve_module} -> {result.kind} {result.module}", file=sys.stderr)
                        
                        target_module = result.module
                        if result.kind in ("module_file", "package_init", "namespace_pkg"):
                            import_graph.add_module(target_module, result.file_path)
                        elif result.kind in ("builtin", "stdlib", "third_party"):
                            import_graph.add_module(target_module, None)
                        
                        if result.kind != "missing":
                            import_graph.add_edge(file_module, target_module)
        
        except Exception as e:
            print(f"Warning: Failed to process imports for {file_path}: {e}", file=sys.stderr)
    
    # Build symbol index for all files
    symbol_index = ProjectSymbolIndex()
    try:
        all_adapters = get_all_adapters()
        
        excluded_paths = {
            "node_modules", ".venv", "venv", "env", "vendor", "third_party",
            "external", "lib", "libs", "dependencies", ".git", "__pycache__",
            "build", "dist", "target", "out", "bin", ".pytest_cache", "coverage",
            "*.min.js", "*.bundle.js"
        }
        
        if hasattr(config, 'symbol_index') and config.symbol_index.get('excluded_paths'):
            excluded_paths.update(config.symbol_index['excluded_paths'])
        
        symbol_index = build_symbol_index(all_files, all_adapters, excluded_paths)
        
        if symbol_index:
            stats = symbol_index.get_stats()
            print(f"✓ Unified symbol index: {stats['total_symbols']} symbols across {stats['files_indexed']} files", file=sys.stderr)
    
    except Exception as e:
        print(f"Warning: Failed to build symbol index: {e}", file=sys.stderr)
        symbol_index = ProjectSymbolIndex()
    
    # Build dependency graph if enabled
    dependency_graph = None
    if config.enable_dependency_tracking:
        try:
            print("Building dependency graph for impact analysis...", file=sys.stderr)
            dependency_graph = build_dependency_graph(all_files, all_adapters, symbol_index)
            dep_stats = dependency_graph.get_stats()
            print(f"✓ Unified dependency graph: {dep_stats['unique_symbols']} symbols, {dep_stats['total_dependencies']} dependencies", file=sys.stderr)
        except Exception as e:
            print(f"Warning: Failed to build dependency graph: {e}", file=sys.stderr)
    
    # Return enhanced format
    if config.enable_dependency_tracking and dependency_graph is not None:
        project_graph = {
            'resolver': resolver,
            'import_graph': import_graph,
            'symbol_index': symbol_index,
            'dependency_graph': dependency_graph,
            'unified_jsts': True  # Flag to identify unified graph
        }
    else:
        project_graph = {
            'resolver': resolver,
            'import_graph': import_graph,
            'symbol_index': symbol_index,
            'unified_jsts': True
        }
    
    _project_graph_cache[signature] = project_graph
    
    # Clean up old cache entries
    if len(_project_graph_cache) > 10:
        oldest_keys = list(_project_graph_cache.keys())[:-10]
        for old_key in oldest_keys:
            del _project_graph_cache[old_key]
    
    print(f"✓ Unified JS/TS project graph built: {import_graph.stats()['modules']} modules, {import_graph.stats()['edges']} edges")
    
    return project_graph


def run_analysis_parallel(files: List[str], language: str, rules: List, config: EngineConfig,
                         jobs: int, debug_adapter: bool, debug_scopes: bool = False, 
                         debug_resolver: bool = False, graph_dump_path: str = None) -> Tuple[List[Finding], float, List[str]]:
    """Run analysis on files with optional parallelization."""
    debug_output = []
    
    # Check if any rule needs project graph AND applies to this language
    needs_project_graph = False
    for rule in rules:
        requires = getattr(rule, 'requires', None)
        if not requires:
            continue
        if not getattr(requires, 'project_graph', False):
            continue
        # Check if rule applies to this language
        if hasattr(rule, 'meta') and hasattr(rule.meta, 'langs'):
            if language in rule.meta.langs:
                needs_project_graph = True
                break
        else:
            # No language restriction, assume it applies
            needs_project_graph = True
            break
    
    project_graph = None
    
    if needs_project_graph or debug_resolver or graph_dump_path:
        # Build project graph
        project_graph = build_project_graph(files, language, config, debug_resolver)
        
        # Dump graph if requested
        if graph_dump_path and project_graph:
            resolver, import_graph, symbol_index = project_graph
            try:
                import_graph.save_json(graph_dump_path)
                print(f"Graph dumped to {graph_dump_path}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Failed to dump graph to {graph_dump_path}: {e}", file=sys.stderr)
    
    if jobs <= 1:
        # Sequential processing
        all_findings = []
        total_parse_time = 0.0
        
        for file_path in files:
            findings, parse_time = analyze_file(file_path, language, rules, config, debug_adapter, debug_output, debug_scopes, project_graph)
            all_findings.extend(findings)
            total_parse_time += parse_time
            
            # Apply total findings limit
            if len(all_findings) >= config.max_total_findings:
                all_findings = all_findings[:config.max_total_findings]
                break
        
        return all_findings, total_parse_time, debug_output
    
    else:
        # Parallel processing
        all_findings = []
        total_parse_time = 0.0
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as executor:
            # Submit all files for processing
            futures = {
                executor.submit(analyze_file, file_path, language, rules, config, debug_adapter, debug_output, debug_scopes, project_graph): file_path
                for file_path in files
            }
            
            # Collect results in order
            file_results = []
            for file_path in files:
                # Find the future for this file
                future = None
                for f, fp in futures.items():
                    if fp == file_path:
                        future = f
                        break
                
                if future:
                    try:
                        findings, parse_time = future.result()
                        file_results.append((findings, parse_time))
                        total_parse_time += parse_time
                    except Exception as e:
                        print(f"Warning: Failed to process {file_path}: {e}", file=sys.stderr)
                        file_results.append(([], 0.0))
            
            # Flatten findings while maintaining order
            for findings, _ in file_results:
                all_findings.extend(findings)
                if len(all_findings) >= config.max_total_findings:
                    all_findings = all_findings[:config.max_total_findings]
                    break
        
        return all_findings, total_parse_time, debug_output


def format_output(findings: List[Finding], files_count: int, rules_count: int, metrics: Dict[str, float], 
                 format_type: str, text_cache: Dict[str, str] = None) -> str:
    """Format output according to specified format."""
    if format_type == "json":
        output = {
            "aspect-code.protocol": PROTOCOL_VERSION,
            "engine_version": ENGINE_VERSION,
            "files_scanned": files_count,
            "rules_run": rules_count,
            "findings": findings_to_json(findings, text_cache),
            "metrics": metrics
        }
        return json.dumps(output, indent=2)
    
    elif format_type == "legacy":
        # Legacy format for backward compatibility with existing extension
        output = {
            "violations": findings_to_legacy_violations(findings, text_cache),
            "verdict": "risky" if findings else "safe"
        }
        return json.dumps(output, indent=2)
    
    elif format_type == "pretty":
        lines = []
        lines.append(f"Scanned {files_count} files with {rules_count} rules")
        lines.append(f"Found {len(findings)} issues")
        lines.append("")
        
        # Group findings by file
        by_file = {}
        for finding in findings:
            if finding.file not in by_file:
                by_file[finding.file] = []
            by_file[finding.file].append(finding)
        
        for file_path, file_findings in sorted(by_file.items()):
            lines.append(f"📁 {file_path}")
            for finding in file_findings:
                # Convert bytes to line/col if possible
                adapter = get_adapter("python")  # TODO: Make this language-aware
                if adapter:
                    try:
                        with open(finding.file, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        line, col = adapter.byte_to_linecol(content, finding.start_byte)
                        location = f"{line}:{col}"
                    except:
                        location = f"byte {finding.start_byte}"
                else:
                    location = f"byte {finding.start_byte}"
                
                severity_icon = {"info": "ℹ️", "warn": "⚠️", "error": "❌"}.get(finding.severity, "❓")
                lines.append(f"  {severity_icon} {location}: {finding.message} ({finding.rule})")
            lines.append("")
        
        # Add metrics
        lines.append("📊 Metrics:")
        lines.append(f"  Parse time: {metrics['parse_ms']:.1f}ms")
        lines.append(f"  Rules time: {metrics['rules_ms']:.1f}ms") 
        lines.append(f"  Total time: {metrics['total_ms']:.1f}ms")
        
        return "\n".join(lines)
    
    else:
        raise ValueError(f"Unknown format: {format_type}")


def analyze_paths(paths: List[str], discovery_packages: List[str] = None, 
                  rule_patterns: List[str] = None, config_path: str = None, 
                  verbose: bool = False, profile: str = None) -> Dict[str, Any]:
    """
    Library function to analyze paths using the tree-sitter engine.
    
    Args:
        paths: List of file/directory paths to analyze
        discovery_packages: Packages to discover rules from (default: ["server.rules"])
        rule_patterns: Rule patterns to run (default: ["*"])
        config_path: Path to config file (default: auto-detect)
        verbose: Enable verbose output
        profile: Rule profile to use (default: alpha_default)
        
    Returns:
        Dictionary with analysis results in new format
    """
    # Set defaults
    if discovery_packages is None:
        discovery_packages = ["server.rules"]
    if rule_patterns is None:
        rule_patterns = ["*"]
    
    # Validate profile
    if profile is None:
        rule_profile = get_default_profile()
    else:
        rule_profile = validate_profile(profile)
    
    try:
        # Load configuration
        if not config_path:
            config_path = find_config_file(paths[0] if paths else ".")
        config = load_config(config_path)
        
        # Discover rules - use optimized loading for alpha profile
        if rule_profile == RuleProfile.ALPHA_DEFAULT:
            rules_discovered = discover_alpha_rules_only()
        else:
            rules_discovered = discover_rules(discovery_packages)
        
        # Get enabled rules for all languages
        all_findings = []
        total_files = 0
        total_rules_ms = 0
        
        # Process each supported language
        for lang in ["python", "typescript", "javascript"]:
            # Get rules for this language with profile filtering
            rules = get_enabled_rules(rule_patterns, lang, rule_profile)
            if not rules:
                continue
                
            # Collect files for this language
            files = collect_files(paths, lang, None)
            if not files:
                continue
                
            total_files += len(files)
            
            # Run analysis
            start_time = time.time()
            if len(files) == 1:
                findings, parse_time = analyze_file(files[0], lang, rules, config, 
                                                  debug_adapter=False, debug_output=[], 
                                                  debug_scopes=False, project_graph=None)
            else:
                findings, parse_time = run_analysis_parallel(files, lang, rules, config, jobs=1, 
                                                           debug_adapter=False, debug_output=[], 
                                                           debug_scopes=False, debug_resolver=False, 
                                                           graph_dump=None)
            
            rules_ms = (time.time() - start_time) * 1000
            total_rules_ms += rules_ms
            
            # Add language info to findings
            for finding in findings:
                if hasattr(finding, '_language'):
                    finding._language = lang
                    
            all_findings.extend(findings)
        
        # Convert to new format
        result = {
            "aspect-code.protocol": "1", 
            "engine_version": "0.1.0",
            "files_scanned": total_files,
            "rules_run": len([r for lang in ["python", "typescript", "javascript"] 
                             for r in get_enabled_rules(rule_patterns, lang)]),
            "findings": [],
            "metrics": {
                "parse_ms": 0.0,
                "rules_ms": total_rules_ms,
                "total_ms": total_rules_ms
            }
        }
        
        # Convert findings to new format (excluding KB-only rules from user output)
        for finding in all_findings:
            # Skip KB-only rules (they're for .aspect/ KB generation, not user display)
            if not is_user_facing_rule(finding.rule):
                continue
                
            finding_dict = {
                "rule_id": finding.rule,
                "message": finding.message,
                "file_path": finding.file,
                "uri": f"file:///{finding.file.replace(os.sep, '/')}",
                "start_byte": finding.start_byte,
                "end_byte": finding.end_byte,
                "range": {
                    "startLine": getattr(finding, 'line', 1),
                    "startCol": getattr(finding, 'column', 1), 
                    "endLine": getattr(finding, 'end_line', 1),
                    "endCol": getattr(finding, 'end_column', 1)
                },
                "severity": finding.severity
            }
            
            # Add autofix if available
            if hasattr(finding, 'autofix') and finding.autofix:
                finding_dict["autofix"] = []
                for edit in finding.autofix:
                    edit_dict = {
                        "start_byte": edit.start_byte,
                        "end_byte": edit.end_byte,
                        "replacement": edit.replacement
                    }
                    finding_dict["autofix"].append(edit_dict)
            
            # Add meta if available  
            if hasattr(finding, 'meta') and finding.meta:
                finding_dict["meta"] = finding.meta
                
            result["findings"].append(finding_dict)
        
        return result
        
    except Exception as e:
        if verbose:
            import traceback
            traceback.print_exc()
        raise e


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Aspect Code Tree-sitter engine for code analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m server.engine.runner --paths src/ --lang python --discover server.rules --rules "*" --format json
  python -m server.engine.runner --paths app.py --lang python --rules "imports.*" --debug-adapter
  python -m server.engine.runner --paths frontend/ --lang typescript --jobs 4 --validate
        """
    )
    
    parser.add_argument(
        "--paths",
        nargs="+",
        required=True,
        help="Paths to files or directories to analyze"
    )
    
    parser.add_argument(
        "--lang", "--language",
        required=True,
        choices=["python", "typescript", "javascript"],
        help="Programming language to analyze"
    )
    
    parser.add_argument(
        "--discover",
        default="server.rules",
        help="Comma-separated packages to discover rules from (default: server.rules)"
    )
    
    parser.add_argument(
        "--rules",
        default="*",
        help="Rule patterns to run: '*' for all, or comma-separated IDs/patterns (default: *)"
    )
    
    parser.add_argument(
        "--exts",
        help="Override file extensions (comma-separated, e.g., '.py,.pyi')"
    )
    
    parser.add_argument(
        "--debug-adapter",
        action="store_true",
        help="Print adapter debugging information to stderr"
    )
    
    parser.add_argument(
        "--jobs",
        type=int,
        default=0,
        help="Number of parallel jobs (0=auto, 1=sequential, N=parallel)"
    )
    
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate JSON output against schema"
    )
    
    parser.add_argument(
        "--format",
        choices=["json", "legacy", "pretty"],
        default="json",
        help="Output format: json (protocol v1), legacy (for backward compatibility), pretty (human-readable)"
    )
    
    parser.add_argument(
        "--config",
        help="Path to configuration file"
    )
    
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose output"
    )
    
    parser.add_argument(
        "--debug-scopes",
        action="store_true",
        help="Print scope statistics to stderr"
    )
    
    parser.add_argument(
        "--debug-resolver",
        action="store_true",
        help="Print import resolution traces to stderr"
    )
    
    parser.add_argument(
        "--graph-dump",
        help="Dump project import graph to JSON file"
    )
    
    parser.add_argument(
        "--profile",
        choices=["alpha_default", "all"],
        default="alpha_default",
        help="Rule profile to use: alpha_default (focused set) or all (complete set)"
    )
    
    args = parser.parse_args()
    
    total_start = time.time()
    
    # Setup adapters
    setup_adapters()
    
    # Load configuration
    config_path = args.config
    if not config_path:
        config_path = find_config_file(args.paths[0] if args.paths else ".")
    
    config = load_config(config_path)
    
    if args.verbose:
        print(f"Using config: {config_path or 'defaults'}", file=sys.stderr)
    
    # Discover rules - use optimized loading for alpha profile
    discovery_packages = [pkg.strip() for pkg in args.discover.split(",")]
    rule_profile = validate_profile(args.profile)
    
    if rule_profile == RuleProfile.ALPHA_DEFAULT:
        rules_discovered = discover_alpha_rules_only()
    else:
        rules_discovered = discover_rules(discovery_packages)
    
    if args.verbose:
        print(f"Discovered {rules_discovered} rules from {discovery_packages}", file=sys.stderr)
        available_rule_ids = get_rule_ids()
        print(f"Available rule IDs: {available_rule_ids}", file=sys.stderr)
    
    # Parse rule filters
    if args.rules == "*":
        rule_patterns = ["*"]
    else:
        rule_patterns = [pattern.strip() for pattern in args.rules.split(",")]
    
    # Profile already validated above
    
    # Get enabled rules for this language and profile
    rules = get_enabled_rules(rule_patterns, args.lang, rule_profile)
    
    if args.verbose:
        print(f"Running {len(rules)} rules: {[r.meta.id for r in rules]}", file=sys.stderr)
    
    # Parse extensions override
    extensions = None
    if args.exts:
        extensions = tuple(ext.strip() for ext in args.exts.split(","))
    
    # Collect files to analyze
    files = collect_files(args.paths, args.lang, extensions)
    
    if args.verbose:
        print(f"Found {len(files)} files to analyze", file=sys.stderr)
        if args.debug_adapter:
            print(f"Debug adapter output:", file=sys.stderr)
    
    if not files:
        print("No files found to analyze", file=sys.stderr)
        sys.exit(1)
    
    # Determine number of jobs
    jobs = args.jobs
    if jobs == 0:
        jobs = min(4, len(files), os.cpu_count() or 1)
    
    # Run analysis
    rules_start = time.time()
    findings, parse_time_ms, debug_output = run_analysis_parallel(
        files, args.lang, rules, config, jobs, args.debug_adapter, args.debug_scopes,
        args.debug_resolver, args.graph_dump
    )
    rules_time_ms = (time.time() - rules_start) * 1000
    total_time_ms = (time.time() - total_start) * 1000
    
    # Print debug output to stderr
    if debug_output:
        for line in debug_output:
            print(line, file=sys.stderr)
    
    # Create metrics
    metrics = {
        "parse_ms": parse_time_ms,
        "rules_ms": rules_time_ms,
        "total_ms": total_time_ms
    }
    
    # Format and output results
    # Build text cache for range conversion (only for JSON format)
    text_cache = {}
    if args.format == "json":
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    # Normalize path for cache key
                    abs_path = str(Path(file_path).resolve())
                    text_cache[abs_path] = f.read()
            except Exception:
                # Skip files that can't be read
                pass
    
    output = format_output(findings, len(files), len(rules), metrics, args.format, text_cache)
    
    # Validate output if requested
    if args.validate and args.format == "json":
        try:
            output_dict = json.loads(output)
            errors = validate_runner_output(output_dict)
            if errors:
                print("JSON validation errors:", file=sys.stderr)
                for error in errors:
                    print(f"  {error}", file=sys.stderr)
                sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON output: {e}", file=sys.stderr)
            sys.exit(1)
    
    print(output)


if __name__ == "__main__":
    main()

