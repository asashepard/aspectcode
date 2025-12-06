"""
Configuration management for the Aspect Code engine.

This module provides configuration loading with sensible defaults for
thresholds, severities, and other engine settings.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Any
import yaml
import os


@dataclass
class EngineConfig:
    """Configuration for the Aspect Code engine."""
    
    # Rule execution settings
    enabled_rules: List[str]
    max_findings_per_file: int = 50
    max_total_findings: int = 1000
    
    # Severity thresholds
    severity_threshold: str = "info"  # "info", "warning", "error"
    
    # Performance settings
    enable_caching: bool = True
    max_cache_size: int = 100
    
    # Advanced features (experimental)
    enable_dependency_tracking: bool = True  # Enable by default for Tier 2 architectural rules
    
    # Rule severity overrides (rule_id -> severity)
    rule_severities: Dict[str, str] = None
    
    # Language-specific settings
    language_configs: Dict[str, Dict[str, Any]] = None
    
    # Rule-specific configuration
    rule_configs: Dict[str, Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.language_configs is None:
            object.__setattr__(self, 'language_configs', {})
        if self.rule_severities is None:
            object.__setattr__(self, 'rule_severities', {})
        if self.rule_configs is None:
            object.__setattr__(self, 'rule_configs', {})


def load_config(config_path: Optional[str] = None) -> EngineConfig:
    """
    Load configuration from file or use defaults.
    
    Args:
        config_path: Path to config file (YAML). If None, uses defaults.
        
    Returns:
        EngineConfig instance
    """
    # Default configuration
    defaults = {
        "enabled_rules": [],
        "max_findings_per_file": 50,
        "max_total_findings": 1000,
        "severity_threshold": "info",
        "enable_caching": True,
        "max_cache_size": 100,
        "enable_dependency_tracking": True,  # Enable for Tier 2 architectural rules
        "rule_severities": {
            # Phase-A rule defaults
            "imports.wildcard": "error",
            "lang.ts_loose_equality": "warn",
            "mut.default_mutable_arg": "error",
            "func.async_mismatch.await_in_sync": "error",
            
            # Tier-1 rule defaults  
            "imports.unused": "error",
            "ident.shadowing": "warn", 
            "imports.side_effect_only": "info",
            
            # Tier-2 rule defaults
            "imports.missing_file_target": "error",
            "imports.cycle": "error"
        },
        "language_configs": {
            "python": {
                "max_line_length": 88,
                "max_function_params": 5,
                "max_nesting_depth": 4,
                "resolver": {
                    "extra_sys_path": [],
                    "treat_site_packages_as_external": True
                }
            },
            "typescript": {
                "max_line_length": 100,
                "max_function_params": 6,
                "prefer_const": True
            },
            "javascript": {
                "max_line_length": 100,
                "max_function_params": 6,
                "prefer_const": True
            }
        },
        
        # Rule-specific configuration
        "rule_configs": {
            "imports.unused": {
                "consider_type_checking_usage": False,
                "consider_dunder_all_reexports": True
            },
            "imports.side_effect_only": {
                "allow_annotation": "aspect-code: keep-side-effect"
            },
            "imports.missing_file_target": {
                "ignore_external": True
            },
            "imports.cycle": {
                "ignore_external": True
            }
        }
    }
    
    # Load from file if provided
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                file_config = yaml.safe_load(f) or {}
                
            # Merge with defaults
            merged_config = defaults.copy()
            merged_config.update(file_config)
            
            # Deep merge language configs
            if "language_configs" in file_config:
                for lang, lang_config in file_config["language_configs"].items():
                    if lang in merged_config["language_configs"]:
                        merged_config["language_configs"][lang].update(lang_config)
                    else:
                        merged_config["language_configs"][lang] = lang_config
            
            # Deep merge rule severities
            if "rule_severities" in file_config:
                merged_config["rule_severities"].update(file_config["rule_severities"])
            
            # Deep merge rule configs
            if "rule_configs" in file_config:
                for rule_id, rule_config in file_config["rule_configs"].items():
                    if rule_id in merged_config["rule_configs"]:
                        merged_config["rule_configs"][rule_id].update(rule_config)
                    else:
                        merged_config["rule_configs"][rule_id] = rule_config
                        
            return EngineConfig(**merged_config)
            
        except Exception as e:
            print(f"Warning: Failed to load config from {config_path}: {e}")
            print("Using default configuration.")
    
    return EngineConfig(**defaults)


def get_default_config() -> EngineConfig:
    """Get default configuration without loading from file."""
    return load_config(None)


def save_config(config: EngineConfig, config_path: str) -> None:
    """
    Save configuration to file.
    
    Args:
        config: EngineConfig to save
        config_path: Path where to save the config
    """
    config_dict = {
        "enabled_rules": config.enabled_rules,
        "max_findings_per_file": config.max_findings_per_file,
        "max_total_findings": config.max_total_findings,
        "severity_threshold": config.severity_threshold,
        "enable_caching": config.enable_caching,
        "max_cache_size": config.max_cache_size,
        "enable_dependency_tracking": config.enable_dependency_tracking,
        "rule_severities": config.rule_severities,
        "rule_configs": config.rule_configs,
        "language_configs": config.language_configs
    }
    
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        yaml.dump(config_dict, f, default_flow_style=False, indent=2)


def find_config_file(start_path: str = ".") -> Optional[str]:
    """
    Find configuration file by walking up the directory tree.
    
    Looks for files in this order:
    1. .aspect-code.yml
    2. .aspect-code.yaml
    3. aspect-code.yml
    4. aspect-code.yaml
    
    Args:
        start_path: Directory to start searching from
        
    Returns:
        Path to config file or None if not found
    """
    config_names = [".aspect-code.yml", ".aspect-code.yaml", "aspect-code.yml", "aspect-code.yaml"]
    
    current_path = os.path.abspath(start_path)
    
    while True:
        for config_name in config_names:
            config_path = os.path.join(current_path, config_name)
            if os.path.exists(config_path):
                return config_path
        
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:
            # Reached the root directory
            break
        current_path = parent_path
    
    return None


def get_rule_severity(rule_id: str, config: EngineConfig, default_severity: str = "warn") -> str:
    """
    Get the configured severity for a rule, falling back to default.
    
    Args:
        rule_id: Rule identifier (e.g., "imports.wildcard")
        config: Engine configuration
        default_severity: Fallback severity if not configured
        
    Returns:
        Severity level ("info", "warn", or "error")
    """
    if config.rule_severities and rule_id in config.rule_severities:
        return config.rule_severities[rule_id]
    return default_severity

