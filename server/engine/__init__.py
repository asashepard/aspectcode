"""
Aspect Code Tree-sitter engine package.

This package provides a language-agnostic code analysis engine built on Tree-sitter.
"""

from .types import (
    Finding, RuleMeta, Rule, RuleContext, Edit, Requires,
    LanguageAdapter, ImportInfo, FunctionInfo, ParamDefaultInfo, BinaryOpInfo,
    Severity, FileRange, NodeRange
)

from .registry import (
    register_rule, register_adapter, get_adapter, get_rule,
    get_all_rules, get_rules_for_language, get_enabled_rules,
    get_all_adapters, list_supported_languages, clear
)

from .config import (
    EngineConfig, load_config, get_default_config, save_config, find_config_file, get_rule_severity
)

__all__ = [
    # Types
    "Finding", "RuleMeta", "Rule", "RuleContext", "Edit", "Requires",
    "LanguageAdapter", "ImportInfo", "FunctionInfo", "ParamDefaultInfo", "BinaryOpInfo",
    "Severity", "FileRange", "NodeRange",
    
    # Registry
    "register_rule", "register_adapter", "get_adapter", "get_rule",
    "get_all_rules", "get_rules_for_language", "get_enabled_rules", 
    "get_all_adapters", "list_supported_languages", "clear",
    
    # Config
    "EngineConfig", "load_config", "get_default_config", "save_config", "find_config_file", "get_rule_severity"
]


