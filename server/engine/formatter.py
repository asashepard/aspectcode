"""
Code formatting utilities for the Aspect Code engine.

This module provides no-op stubs for code formatters like Black and Prettier.
The actual formatting integration will be implemented later.
"""

from typing import Optional, Dict, Any
from abc import ABC, abstractmethod


class Formatter(ABC):
    """Abstract base class for code formatters."""
    
    @abstractmethod
    def format(self, code: str, **options) -> str:
        """Format code and return the formatted result."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if the formatter is available/installed."""
        pass


class BlackFormatter(Formatter):
    """Python code formatter using Black (stub implementation)."""
    
    def format(self, code: str, **options) -> str:
        """Format Python code using Black (not implemented yet)."""
        # TODO: Implement Black integration
        # This would call Black programmatically to format Python code
        return code
    
    def is_available(self) -> bool:
        """Check if Black is available."""
        try:
            import black
            return True
        except ImportError:
            return False


class PrettierFormatter(Formatter):
    """JavaScript/TypeScript formatter using Prettier (stub implementation)."""
    
    def format(self, code: str, **options) -> str:
        """Format JavaScript/TypeScript code using Prettier (not implemented yet)."""
        # TODO: Implement Prettier integration
        # This would call Prettier via subprocess or Node.js bindings
        return code
    
    def is_available(self) -> bool:
        """Check if Prettier is available."""
        import shutil
        return shutil.which("prettier") is not None


class NoOpFormatter(Formatter):
    """No-operation formatter that returns code unchanged."""
    
    def format(self, code: str, **options) -> str:
        """Return code unchanged."""
        return code
    
    def is_available(self) -> bool:
        """Always available."""
        return True


# Registry of formatters by language
_formatters: Dict[str, Formatter] = {
    "python": NoOpFormatter(),  # Will be BlackFormatter() when implemented
    "typescript": NoOpFormatter(),  # Will be PrettierFormatter() when implemented  
    "javascript": NoOpFormatter(),  # Will be PrettierFormatter() when implemented
}


def get_formatter(language: str) -> Optional[Formatter]:
    """Get formatter for a language."""
    return _formatters.get(language)


def format_code(code: str, language: str, **options) -> str:
    """
    Format code for a specific language.
    
    Args:
        code: Source code to format
        language: Programming language
        **options: Formatter-specific options
        
    Returns:
        Formatted code (or original if no formatter available)
    """
    formatter = get_formatter(language)
    if formatter and formatter.is_available():
        return formatter.format(code, **options)
    return code


def is_formatter_available(language: str) -> bool:
    """Check if a formatter is available for a language."""
    formatter = get_formatter(language)
    return formatter is not None and formatter.is_available()


def register_formatter(language: str, formatter: Formatter) -> None:
    """Register a formatter for a language."""
    _formatters[language] = formatter


def list_available_formatters() -> Dict[str, bool]:
    """List all languages and whether formatters are available."""
    return {lang: formatter.is_available() for lang, formatter in _formatters.items()}


