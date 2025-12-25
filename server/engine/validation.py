"""
Validation service for the tree-sitter engine.

This module provides a clean, normalized interface for code validation
that abstracts the complexity of adapter loading, rule discovery, and
file processing.
"""

import time
import os
import sys
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path

from .registry import register_adapter, get_adapter, register_rule, get_enabled_rules, get_rule
from .runner import (collect_files, analyze_file, build_unified_jsts_project_graph,
                     enable_rule_timing, disable_rule_timing, get_rule_timing, clear_rule_timing,
                     get_cached_ast, clear_ast_cache)
from .config import load_config, find_config_file
from .types import Finding
from .schema import create_range_from_bytes
from .profiles import RuleProfile, validate_profile, get_default_profile


class ValidationService:
    """Service for validating code using tree-sitter rules."""
    
    def __init__(self):
        self._adapters_loaded = False
        self._rules_loaded = False
        self._loaded_rule_ids = []
    
    def ensure_adapters_loaded(self) -> None:
        """Ensure all language adapters are loaded."""
        if self._adapters_loaded:
            return
            
        # Load Python adapter
        try:
            if not get_adapter("python"):
                from .python_adapter import default_python_adapter
                register_adapter(default_python_adapter.language_id, default_python_adapter)
        except Exception as e:
            print(f"Warning: Could not load Python adapter: {e}")
        
        # Load JavaScript adapter
        try:
            if not get_adapter("javascript"):
                from .javascript_adapter import default_javascript_adapter
                register_adapter(default_javascript_adapter.language_id, default_javascript_adapter)
        except Exception as e:
            print(f"Warning: Could not load JavaScript adapter: {e}")
        
        # Load TypeScript adapter
        try:
            if not get_adapter("typescript"):
                from .typescript_adapter import default_typescript_adapter
                register_adapter(default_typescript_adapter.language_id, default_typescript_adapter)
        except Exception as e:
            print(f"Warning: Could not load TypeScript adapter: {e}")
        
        # Load Java adapter
        try:
            if not get_adapter("java"):
                from .java_adapter import default_java_adapter
                register_adapter(default_java_adapter.language_id, default_java_adapter)
        except Exception as e:
            print(f"Warning: Could not load Java adapter: {e}")
        
        # Load C# adapter
        try:
            if not get_adapter("csharp"):
                from .csharp_adapter import default_csharp_adapter
                register_adapter(default_csharp_adapter.language_id, default_csharp_adapter)
        except Exception as e:
            print(f"Warning: Could not load C# adapter: {e}")
        
        self._adapters_loaded = True
    
    def ensure_rules_loaded(self) -> None:
        """Ensure all rules are loaded systematically."""
        if self._rules_loaded:
            return
            
        import importlib.util
        import sys
        import glob
        
        # Get the rules directory - use absolute path based on this file's location
        engine_dir = os.path.dirname(__file__)  # This file is in server/engine/
        server_dir = os.path.dirname(engine_dir)  # Go up to server/
        rules_dir = os.path.join(server_dir, "rules")
        
        # Find ALL Python files in the rules directory
        rule_files = glob.glob(os.path.join(rules_dir, "*.py"))
        
        loaded_rules = []
        for rule_file in rule_files:
            if rule_file.endswith("__init__.py"):
                continue  # Skip __init__.py
                
            try:
                # Import the module
                module_name = os.path.basename(rule_file)[:-3]  # Remove .py
                spec = importlib.util.spec_from_file_location(module_name, rule_file)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                
                # First check for RULES list (instances)
                rules_found = False
                if hasattr(module, 'RULES') and isinstance(module.RULES, list):
                    for rule in module.RULES:
                        if (hasattr(rule, 'meta') and hasattr(rule, 'visit') and 
                            hasattr(rule, 'requires') and hasattr(rule.meta, 'id')):
                            try:
                                register_rule(rule)
                                loaded_rules.append(rule.meta.id)
                                rules_found = True
                            except Exception as e:
                                print(f"Warning: Failed to register rule from RULES list in {module_name}: {e}")
                
                # If no RULES list found, look for individual rule instances/classes
                if not rules_found:
                    for attr_name in dir(module):
                        if attr_name.startswith('_'):
                            continue
                            
                        attr = getattr(module, attr_name)
                        
                        # Check if it looks like a rule (has meta, visit, requires attributes)
                        if (hasattr(attr, 'meta') and hasattr(attr, 'visit') and 
                            hasattr(attr, 'requires') and hasattr(attr.meta, 'id')):
                            try:
                                # Prefer instances over classes
                                if hasattr(attr, '__class__') and not callable(attr):
                                    # This is an instance
                                    register_rule(attr)
                                    loaded_rules.append(attr.meta.id)
                                    break  # Use first valid instance found
                                elif callable(getattr(attr, '__init__', None)):
                                    # This is a class, create an instance
                                    rule_instance = attr()
                                    register_rule(rule_instance)
                                    loaded_rules.append(rule_instance.meta.id)
                                    break  # Use first valid class found
                            except Exception as e:
                                print(f"Warning: Failed to register rule {attr_name} from {module_name}: {e}")
                            
            except Exception as e:
                print(f"Warning: Could not load rule file {rule_file}: {e}")
        
        print(f"Loaded {len(loaded_rules)} rules from {len(rule_files)} rule files")
        print(f"Loaded rules: {loaded_rules}")
        
        self._loaded_rule_ids = loaded_rules
        self._rules_loaded = True
    
    def get_loaded_rules(self) -> List[str]:
        """Get list of loaded rule IDs."""
        self.ensure_rules_loaded()
        return self._loaded_rule_ids.copy()
    
    def validate_paths(self, paths: List[str], languages: Optional[List[str]] = None, 
                      profile: Optional[str] = None, enable_project_graph: bool = True,
                      collect_rule_timing: bool = False) -> Dict[str, Any]:
        """
        Validate code at the given paths.
        
        Args:
            paths: List of file or directory paths to validate
            languages: Optional list of languages to process (default: all supported)
            profile: Rule profile to use (default: alpha_default)
            enable_project_graph: Enable dependency graph for Tier 2 architectural rules (default: True)
            collect_rule_timing: If True, collect per-rule timing data (default: False)
            
        Returns:
            Validation result dictionary with findings and metrics
        """
        start_time = time.time()
        
        # Enable rule timing if requested
        if collect_rule_timing:
            enable_rule_timing()
            clear_rule_timing()
        
        # Ensure everything is loaded
        self.ensure_adapters_loaded()
        self.ensure_rules_loaded()
        
        # Validate and set profile
        if profile is None:
            rule_profile = get_default_profile()
        else:
            rule_profile = validate_profile(profile)
        
        # Load configuration
        config_path = find_config_file(paths[0] if paths else ".")
        config = load_config(config_path)
        
        # Determine languages to process
        if languages is None:
            languages = ["python", "javascript", "typescript", "java", "csharp"]
        
        all_findings = []
        total_files = 0
        language_stats = {}
        
        # Pre-collect files for all languages to enable unified JS/TS graph
        files_by_language = {}
        for language in languages:
            files = collect_files(paths, language, None)
            if files:
                files_by_language[language] = files
        
        # Check if we need unified JS/TS graph
        has_js = "javascript" in files_by_language and files_by_language["javascript"]
        has_ts = "typescript" in files_by_language and files_by_language["typescript"]
        use_unified_jsts = has_js and has_ts and enable_project_graph
        
        # Build unified JS/TS project graph if both languages present
        unified_jsts_graph = None
        if use_unified_jsts:
            js_files = files_by_language.get("javascript", [])
            ts_files = files_by_language.get("typescript", [])
            
            # Check if any JS/TS rule needs project graph
            needs_jsts_graph = False
            for lang in ["javascript", "typescript"]:
                rules = get_enabled_rules(["*"], lang, rule_profile)
                for rule in rules:
                    requires = getattr(rule, 'requires', None)
                    if requires and getattr(requires, 'project_graph', False):
                        needs_jsts_graph = True
                        break
                if needs_jsts_graph:
                    break
            
            if needs_jsts_graph:
                try:
                    unified_jsts_graph = build_unified_jsts_project_graph(js_files, ts_files, config)
                except Exception as e:
                    print(f"⚠ Failed to build unified JS/TS graph: {e}. Falling back to per-language graphs.")
                    unified_jsts_graph = None
        
        # Process each language
        profile_rule_ids_used = set()
        for language in languages:
            # Get rules for this language and profile
            rules = get_enabled_rules(["*"], language, rule_profile)
            if not rules:
                continue
            
            # Track which rules are actually being used
            for rule in rules:
                profile_rule_ids_used.add(rule.meta.id)
            
            # Get files for this language
            files = files_by_language.get(language, [])
            if not files:
                continue
                
            files_count = len(files)
            total_files += files_count
            
            # Determine project graph to use
            project_graph = None
            
            if enable_project_graph:
                # Use unified graph for JS/TS if available
                if language in ("javascript", "typescript") and unified_jsts_graph:
                    project_graph = unified_jsts_graph
                else:
                    # Check if any rule needs project graph
                    needs_project_graph = False
                    for rule in rules:
                        requires = getattr(rule, 'requires', None)
                        if not requires:
                            continue
                        if not getattr(requires, 'project_graph', False):
                            continue
                        if hasattr(rule, 'meta') and hasattr(rule.meta, 'langs'):
                            if language in rule.meta.langs:
                                needs_project_graph = True
                                break
                        else:
                            needs_project_graph = True
                            break
                    
                    if needs_project_graph:
                        from .runner import build_project_graph
                        print(f"Building project graph for {language} ({len(files)} files)...")
                        try:
                            project_graph = build_project_graph(files, language, config)
                            if project_graph:
                                if isinstance(project_graph, dict):
                                    symbol_index = project_graph.get('symbol_index')
                                    symbol_count = len(symbol_index.symbols) if symbol_index and hasattr(symbol_index, 'symbols') else 0
                                    dep_graph = project_graph.get('dependency_graph')
                                    if dep_graph and hasattr(dep_graph, 'get_stats'):
                                        dep_stats = dep_graph.get_stats()
                                        print(f"✓ Project graph built with {symbol_count} symbols, {dep_stats.get('total_dependencies', 0)} dependencies")
                                    else:
                                        print(f"✓ Project graph built with {symbol_count} symbols")
                                else:
                                    if len(project_graph) >= 3:
                                        symbol_index = project_graph[2]
                                        symbol_count = len(symbol_index.symbols) if hasattr(symbol_index, 'symbols') else 0
                                        print(f"✓ Project graph built (legacy format) with {symbol_count} symbols")
                            else:
                                print("⚠ Project graph building returned None, Tier 2 rules disabled")
                        except Exception as e:
                            print(f"⚠ Failed to build project graph: {e}. Tier 2 rules disabled")
                            project_graph = None
            
            # Analyze files
            language_findings = []
            language_parse_time = 0.0
            
            for file_path in files:
                findings, parse_time = analyze_file(
                    file_path, language, rules, config, 
                    debug_adapter=False, debug_output=[], 
                    debug_scopes=False, project_graph=project_graph
                )
                language_findings.extend(findings)
                language_parse_time += parse_time
            
            # Store language statistics
            language_stats[language] = {
                "files_processed": files_count,
                "rules_run": len(rules),
                "findings_count": len(language_findings),
                "parse_time_ms": language_parse_time
            }
            
            all_findings.extend(language_findings)
        
        # Print summary of which rules were actually used
        print(f"\n{'='*60}")
        print(f"Profile '{rule_profile.value}' applied: {len(profile_rule_ids_used)} unique rules used")
        print(f"Rules: {sorted(profile_rule_ids_used)}")
        print(f"{'='*60}\n")
        
        # Calculate metrics
        total_time_ms = (time.time() - start_time) * 1000
        
        # Convert findings to standard format
        findings_data = []
        text_cache = {}  # Cache file contents for range calculation
        
        for finding in all_findings:
            # Read file content for range calculation (with caching)
            file_path = finding.file
            if file_path not in text_cache:
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        text_cache[file_path] = f.read()
                except Exception:
                    text_cache[file_path] = ""  # Fallback for read errors
            
            # Calculate proper range from byte offsets
            text = text_cache[file_path]
            range_obj = create_range_from_bytes(text, finding.start_byte, finding.end_byte)
            
            # Get priority from rule metadata
            rule = get_rule(finding.rule)
            priority = rule.meta.priority if rule and hasattr(rule, 'meta') else "P1"
            
            finding_dict = {
                "rule_id": finding.rule,
                "message": finding.message,
                "file_path": finding.file,
                "uri": f"file:///{finding.file.replace(os.sep, '/')}",
                "start_byte": finding.start_byte,
                "end_byte": finding.end_byte,
                "range": range_obj,
                "severity": finding.severity,
                "priority": priority  # Add priority for UI categorization
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
            
            findings_data.append(finding_dict)
        
        # Collect rule timing if enabled
        rule_timing_data = None
        if collect_rule_timing:
            rule_timing_data = get_rule_timing()
            disable_rule_timing()
        
        # Create result
        result = {
            "aspect-code.protocol": "1",
            "engine_version": "0.1.0", 
            "files_scanned": total_files,
            "rules_run": sum(stats["rules_run"] for stats in language_stats.values()),
            "findings": findings_data,
            "metrics": {
                "total_ms": total_time_ms,
                "parse_ms": sum(stats["parse_time_ms"] for stats in language_stats.values()),
                "rules_ms": total_time_ms,  # Approximate
                "languages": language_stats
            }
        }
        
        # Add rule timing to result if collected
        if rule_timing_data:
            result["rule_timing"] = rule_timing_data
        
        return result
    
    def validate_repository(self, repo_root: str, profile: Optional[str] = None) -> Dict[str, Any]:
        """Validate an entire repository."""
        return self.validate_paths([repo_root], profile=profile)
    
    def validate_files(self, file_paths: List[str], profile: Optional[str] = None) -> Dict[str, Any]:
        """Validate specific files."""
        return self.validate_paths(file_paths, profile=profile)
    
    def validate_files_content(self, files: List[Dict[str, str]], profile: Optional[str] = None,
                               enable_project_graph: bool = False) -> Dict[str, Any]:
        """
        Validate files from their content (for remote validation).
        
        Args:
            files: List of dicts with 'path', 'content', and optional 'language' keys
            profile: Rule profile to use (default: alpha_default)
            enable_project_graph: Enable dependency graph (disabled by default for remote)
            
        Returns:
            Validation result dictionary with findings and metrics
        """
        import time
        start_time = time.time()
        
        # Ensure everything is loaded
        self.ensure_adapters_loaded()
        self.ensure_rules_loaded()
        
        # Validate and set profile
        if profile is None:
            rule_profile = get_default_profile()
        else:
            rule_profile = validate_profile(profile)
        
        # Load default configuration
        from .config import load_config
        config = load_config(None)
        
        # Determine languages to process
        languages = ["python", "javascript", "typescript", "java", "csharp"]
        
        # Group files by language
        files_by_language: Dict[str, List[Dict[str, str]]] = {}
        
        for file_info in files:
            file_path = file_info.get('path', '')
            content = file_info.get('content', '')
            language = file_info.get('language')
            
            # Auto-detect language from extension if not provided
            if not language:
                if file_path.endswith('.py'):
                    language = 'python'
                elif file_path.endswith('.ts') or file_path.endswith('.tsx'):
                    language = 'typescript'
                elif file_path.endswith('.js') or file_path.endswith('.jsx'):
                    language = 'javascript'
                elif file_path.endswith('.java'):
                    language = 'java'
                elif file_path.endswith('.cs'):
                    language = 'csharp'
                else:
                    continue  # Skip unsupported files
            
            if language not in files_by_language:
                files_by_language[language] = []
            files_by_language[language].append({'path': file_path, 'content': content})
        
        all_findings = []
        language_stats = {}
        profile_rule_ids_used = set()
        
        # Process each language
        for language, lang_files in files_by_language.items():
            if language not in languages:
                continue
            
            adapter = get_adapter(language)
            if not adapter:
                continue
            
            # Get enabled rules for this language
            rules = get_enabled_rules(["*"], language, rule_profile)
            if not rules:
                continue
            
            # Track rules used
            for rule in rules:
                profile_rule_ids_used.add(getattr(rule.meta, 'id', 'unknown'))
            
            # Analyze each file
            language_findings = []
            language_parse_time = 0.0
            
            for file_info in lang_files:
                from .runner import analyze_file
                findings, parse_time = analyze_file(
                    file_info['path'], language, rules, config,
                    debug_adapter=False, debug_output=[],
                    debug_scopes=False, project_graph=None,
                    content=file_info['content']  # Pass content directly
                )
                language_findings.extend(findings)
                language_parse_time += parse_time
            
            # Store language statistics
            language_stats[language] = {
                "files_processed": len(lang_files),
                "rules_run": len(rules),
                "findings_count": len(language_findings),
                "parse_time_ms": language_parse_time
            }
            
            all_findings.extend(language_findings)
        
        # Calculate metrics
        total_time_ms = (time.time() - start_time) * 1000
        
        # Convert findings to standard format
        findings_data = []
        for finding in all_findings:
            try:
                # Create range from bytes using provided content
                file_content = None
                for file_info in files:
                    if file_info.get('path') == finding.file:
                        file_content = file_info.get('content', '')
                        break
                
                if file_content:
                    from .schema import create_range_from_bytes
                    range_info = create_range_from_bytes(file_content, finding.start_byte, finding.end_byte)
                else:
                    range_info = {"startLine": 1, "startCol": 1, "endLine": 1, "endCol": 1}
                
                finding_dict = {
                    "rule_id": finding.rule,
                    "severity": finding.severity,
                    "message": finding.message,
                    "file_path": finding.file,
                    "start_byte": finding.start_byte,
                    "end_byte": finding.end_byte,
                    "range": range_info,
                    "priority": getattr(finding, 'priority', 'P1')
                }
                findings_data.append(finding_dict)
            except Exception as e:
                print(f"Warning: Failed to convert finding: {e}")
        
        total_files = sum(len(f) for f in files_by_language.values())
        
        return {
            "findings": findings_data,
            "files_scanned": total_files,
            "total_findings": len(findings_data),
            "profile": rule_profile.value,
            "metrics": {
                "total_ms": total_time_ms,
                "parse_ms": sum(s.get("parse_time_ms", 0) for s in language_stats.values()),
                "rules_ms": total_time_ms,
                "languages": language_stats
            }
        }


# Global service instance
_validation_service = None


def get_validation_service() -> ValidationService:
    """Get the global validation service instance."""
    global _validation_service
    if _validation_service is None:
        _validation_service = ValidationService()
    return _validation_service


def validate_repository(repo_root: str, profile: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to validate a repository."""
    service = get_validation_service()
    return service.validate_paths([repo_root], profile=profile)


def validate_files(file_paths: List[str], profile: Optional[str] = None) -> Dict[str, Any]:
    """Convenience function to validate specific files."""
    service = get_validation_service()
    return service.validate_paths(file_paths, profile=profile)


def validate_paths(paths: List[str], languages: Optional[List[str]] = None, 
                  profile: Optional[str] = None, enable_project_graph: bool = True,
                  collect_rule_timing: bool = False) -> Dict[str, Any]:
    """Convenience function to validate paths."""
    service = get_validation_service()
    return service.validate_paths(paths, languages, profile, enable_project_graph, collect_rule_timing)


def validate_files_content(files: List[Dict[str, str]], profile: Optional[str] = None,
                          enable_project_graph: bool = False) -> Dict[str, Any]:
    """Convenience function to validate files from content."""
    service = get_validation_service()
    return service.validate_files_content(files, profile, enable_project_graph)


