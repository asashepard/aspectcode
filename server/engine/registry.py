"""
Registry for rules and language adapters.

This module provides a central registry to register and discover rules
and language adapters in the Aspect Code engine.
"""

import fnmatch
import pkgutil
import importlib
import sys
from typing import Dict, List, Optional, Set
from .types import Rule, LanguageAdapter
from .profiles import RuleProfile, get_profile_rule_ids, get_default_profile


class Registry:
    """Central registry for rules and adapters."""
    
    def __init__(self):
        self._rules: List[Rule] = []
        self._adapters: Dict[str, LanguageAdapter] = {}
        self._rule_index: Dict[str, Rule] = {}  # id -> rule
        
    def register_rule(self, rule: Rule) -> None:
        """Register a rule in the registry."""
        if rule.meta.id in self._rule_index:
            # Skip duplicate registration silently to avoid import noise
            return
        
        self._rules.append(rule)
        self._rule_index[rule.meta.id] = rule
        
    def register_adapter(self, language: str, adapter: LanguageAdapter) -> None:
        """Register a language adapter. Silently skips if already registered."""
        if language in self._adapters:
            # Skip duplicate registration silently (like register_rule)
            return
        
        self._adapters[language] = adapter
        
    def get_adapter(self, language: str) -> Optional[LanguageAdapter]:
        """Get adapter for a language."""
        return self._adapters.get(language)
    
    def get_adapter_for_file(self, file_path: str) -> Optional[LanguageAdapter]:
        """Get adapter for a file based on its extension."""
        import os
        ext = os.path.splitext(file_path)[1].lower()
        
        for adapter in self._adapters.values():
            if ext in adapter.file_extensions:
                return adapter
        return None
        
    def get_rule(self, rule_id: str) -> Optional[Rule]:
        """Get rule by id."""
        return self._rule_index.get(rule_id)
    
    def get_rule_surface(self, rule_id: str) -> str:
        """Get the surface type for a rule ('kb', 'findings', or 'both').
        
        Returns 'both' (default) if rule not found or has no surface field.
        """
        rule = self._rule_index.get(rule_id)
        if rule and hasattr(rule.meta, 'surface'):
            return getattr(rule.meta, 'surface', 'both')
        return 'both'
    
    def is_user_facing_rule(self, rule_id: str) -> bool:
        """Check if a rule should appear in user-facing findings panel.
        
        Returns True for rules with surface='findings' or 'both' (default).
        Returns False for rules with surface='kb' (KB-only rules).
        """
        surface = self.get_rule_surface(rule_id)
        return surface in ('findings', 'both')
        
    def get_all_rules(self) -> List[Rule]:
        """Get all registered rules."""
        return self._rules.copy()
        
    def get_rules(self, filter_ids: Optional[List[str]] = None) -> List[Rule]:
        """Get rules, optionally filtered by IDs."""
        if filter_ids is None:
            return self.get_all_rules()
        
        rules = []
        for rule_id in filter_ids:
            rule = self.get_rule(rule_id)
            if rule:
                rules.append(rule)
            else:
                print(f"Warning: Rule '{rule_id}' not found", file=sys.stderr)
        return rules
        
    def get_rule_ids(self) -> List[str]:
        """Get all registered rule IDs."""
        return list(self._rule_index.keys())
        
    def get_rules_for_language(self, language: str) -> List[Rule]:
        """Get all rules that support a specific language."""
        return [rule for rule in self._rules if language in rule.meta.langs]
        
    def get_rules_for_profile(self, profile: RuleProfile, language: str) -> List[Rule]:
        """Get rules for a specific profile and language."""
        profile_rule_ids = get_profile_rule_ids(profile)
        
        # Get all rules for this language
        language_rules = self.get_rules_for_language(language)
        
        if profile == RuleProfile.ALL:
            # Return all rules for this language
            return language_rules
        
        # Filter by profile rule IDs
        profile_rules = []
        for rule in language_rules:
            if rule.meta.id in profile_rule_ids:
                profile_rules.append(rule)
                
        return profile_rules
    
    def get_enabled_rules_with_profile(self, enabled_patterns: List[str], language: str, 
                                     profile: Optional[RuleProfile] = None) -> List[Rule]:
        """Get rules enabled by patterns, filtered by profile."""
        if profile is None:
            profile = get_default_profile()
        
        # First apply profile filtering
        profile_rules = self.get_rules_for_profile(profile, language)
        
        if not enabled_patterns:
            return []
            
        # Special case: "*" means all rules from the profile
        if enabled_patterns == ["*"]:
            return profile_rules
        
        # Filter profile rules by patterns  
        enabled_rules = []
        for rule in profile_rules:
            for pattern in enabled_patterns:
                if fnmatch.fnmatch(rule.meta.id, pattern):
                    enabled_rules.append(rule)
                    break  # Don't add the same rule multiple times
                    
        return enabled_rules
        
    def get_all_adapters(self) -> Dict[str, LanguageAdapter]:
        """Get all registered adapters."""
        return self._adapters.copy()
        
    def list_supported_languages(self) -> List[str]:
        """List all supported languages."""
        return list(self._adapters.keys())
        
    def discover_rules(self, entry_packages: List[str]) -> int:
        """
        Auto-discover and register rules from packages.
        
        Args:
            entry_packages: List of package names to discover from
            
        Returns:
            Number of rules discovered and registered
        """
        initial_count = len(self._rules)
        
        for package_name in entry_packages:
            try:
                self._discover_from_package(package_name)
            except Exception as e:
                print(f"Warning: Failed to discover rules from {package_name}: {e}", file=sys.stderr)
        
        return len(self._rules) - initial_count
        
    def _discover_from_package(self, package_name: str) -> None:
        """Discover rules from a specific package."""
        try:
            # Import the main package
            package = importlib.import_module(package_name)
        except ImportError as e:
            print(f"Warning: Could not import package {package_name}: {e}", file=sys.stderr)
            return
            
        # Walk through all submodules
        if hasattr(package, '__path__'):
            for importer, modname, ispkg in pkgutil.walk_packages(
                package.__path__, 
                package.__name__ + "."
            ):
                try:
                    module = importlib.import_module(modname)
                    self._extract_rules_from_module(module, modname)
                except Exception as e:
                    print(f"Warning: Failed to import {modname}: {e}", file=sys.stderr)
                    continue
    
    def _extract_rules_from_module(self, module, module_name: str) -> None:
        """Extract rules from a module."""
        # Look for RULES list
        if hasattr(module, 'RULES'):
            rules = getattr(module, 'RULES')
            if isinstance(rules, list):
                for rule in rules:
                    try:
                        # If it's a class, instantiate it
                        if isinstance(rule, type):
                            rule_instance = rule()
                            self.register_rule(rule_instance)
                        else:
                            self.register_rule(rule)
                    except Exception as e:
                        print(f"Warning: Failed to register rule from {module_name}: {e}", file=sys.stderr)
        
        # Look for individual rule objects (attributes ending with 'Rule' or having 'meta' attribute)
        for attr_name in dir(module):
            if attr_name.startswith('_'):
                continue
                
            attr = getattr(module, attr_name)
            
            # Check if it's a rule class (has meta and visit methods)
            if (hasattr(attr, 'meta') and hasattr(attr, 'visit') and 
                hasattr(attr, 'requires')):
                try:
                    # If it's a class, instantiate it first
                    if isinstance(attr, type):
                        rule_instance = attr()
                        self.register_rule(rule_instance)
                    else:
                        self.register_rule(attr)
                except Exception as e:
                    print(f"Warning: Failed to register rule {attr_name} from {module_name}: {e}", file=sys.stderr)
        
    def clear(self) -> None:
        """Clear all registered rules and adapters (mainly for testing)."""
        self._rules.clear()
        self._adapters.clear()
        self._rule_index.clear()


# Global registry instance
_global_registry = Registry()


# Load default adapters
def _load_default_adapters():
    """Load default language adapters."""
    try:
        from .python_adapter import default_python_adapter
        _global_registry.register_adapter("python", default_python_adapter)
    except ImportError as e:
        print(f"Warning: Could not load Python adapter: {e}", file=sys.stderr)
    
    try:
        from .javascript_adapter import default_javascript_adapter
        from .typescript_adapter import default_typescript_adapter
        _global_registry.register_adapter("javascript", default_javascript_adapter)
        _global_registry.register_adapter("typescript", default_typescript_adapter)
    except ImportError as e:
        print(f"Warning: Could not load JavaScript/TypeScript adapters: {e}", file=sys.stderr)


# Note: Initialize adapters manually when needed, not on module import
# to avoid conflicts with runner setup
# _load_default_adapters()


# Convenience functions that operate on the global registry
def register_rule(rule: Rule) -> None:
    """Register a rule in the global registry."""
    _global_registry.register_rule(rule)


def register_adapter(language: str, adapter: LanguageAdapter) -> None:
    """Register a language adapter in the global registry."""
    _global_registry.register_adapter(language, adapter)


def get_adapter(language: str) -> Optional[LanguageAdapter]:
    """Get adapter for a language from the global registry."""
    return _global_registry.get_adapter(language)


def get_adapter_for_file(file_path: str) -> Optional[LanguageAdapter]:
    """Get adapter for a file based on its extension from the global registry."""
    return _global_registry.get_adapter_for_file(file_path)


def get_rule(rule_id: str) -> Optional[Rule]:
    """Get rule by id from the global registry."""
    return _global_registry.get_rule(rule_id)


def get_rule_surface(rule_id: str) -> str:
    """Get the surface type for a rule ('kb', 'findings', or 'both')."""
    return _global_registry.get_rule_surface(rule_id)


def is_user_facing_rule(rule_id: str) -> bool:
    """Check if a rule should appear in user-facing findings panel."""
    return _global_registry.is_user_facing_rule(rule_id)


def get_all_rules() -> List[Rule]:
    """Get all registered rules from the global registry."""
    return _global_registry.get_all_rules()


def get_rules(filter_ids: Optional[List[str]] = None) -> List[Rule]:
    """Get rules, optionally filtered by IDs."""
    return _global_registry.get_rules(filter_ids)


def get_rule_ids() -> List[str]:
    """Get all registered rule IDs."""
    return _global_registry.get_rule_ids()


def get_rules_for_language(language: str) -> List[Rule]:
    """Get all rules that support a specific language from the global registry."""
    return _global_registry.get_rules_for_language(language)


def get_enabled_rules(enabled_patterns: List[str], language: str, 
                     profile: Optional[RuleProfile] = None) -> List[Rule]:
    """Get rules enabled by patterns for a specific language, filtered by profile."""
    return _global_registry.get_enabled_rules_with_profile(enabled_patterns, language, profile)


def get_rules_for_profile(profile: RuleProfile, language: str) -> List[Rule]:
    """Get rules for a specific profile and language from the global registry."""
    return _global_registry.get_rules_for_profile(profile, language)


def get_all_adapters() -> Dict[str, LanguageAdapter]:
    """Get all registered adapters from the global registry."""
    return _global_registry.get_all_adapters()


def list_supported_languages() -> List[str]:
    """List all supported languages from the global registry."""
    return _global_registry.list_supported_languages()


def discover_rules(entry_packages: List[str]) -> int:
    """Auto-discover and register rules from packages."""
    return _global_registry.discover_rules(entry_packages)


def clear() -> None:
    """Clear the global registry (mainly for testing)."""
    _global_registry.clear()


def get_registry() -> Registry:
    """Get the global registry instance (for advanced usage)."""
    return _global_registry


