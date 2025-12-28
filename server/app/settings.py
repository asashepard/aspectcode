"""
Aspect Code Server Settings

Configuration management using pydantic settings.
Loads from environment variables with ASPECT_CODE_ prefix.
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import computed_field
from typing import List, Optional, Literal


class Settings(BaseSettings):
    """
    Server configuration settings.
    
    Environment variables:
    - ASPECT_CODE_API_KEYS_RAW: Comma-separated list of valid API keys (admin/service)
    - ASPECT_CODE_ALLOWED_ORIGINS_RAW: Comma-separated list of allowed CORS origins
    - ASPECT_CODE_MIN_CLIENT_VERSION: Minimum extension version required (optional)
    - ASPECT_CODE_RATE_LIMIT: Requests per minute per API key (default: 60)
    - ASPECT_CODE_MAX_CONCURRENT: Max concurrent requests per API key (default: 2)
    - ASPECT_CODE_DAILY_CAP: Daily request cap per API key (default: 5000)
    - ASPECT_CODE_LIMITS_ENABLED: Enable rate limiting (default: true)
    - ASPECT_CODE_DEBUG: Enable debug mode (default: false)
    - ASPECT_CODE_MODE: Authentication mode - 'alpha', 'prod', or 'both' (default: both)
    - DATABASE_URL: PostgreSQL connection string for Neon DB
    """
    
    model_config = SettingsConfigDict(
        env_prefix="ASPECT_CODE_",
        env_file=".env",
        extra="ignore",
    )
    
    # Raw string fields for comma-separated values
    api_keys_raw: str = ""
    allowed_origins_raw: str = ""
    
    # Client version enforcement (optional)
    min_client_version: Optional[str] = None
    
    # Rate limiting - requests per minute
    rate_limit: int = 60  # requests per minute per API key
    
    # Max concurrent requests per API key (discourages key sharing)
    max_concurrent: int = 2
    
    # Daily cap per API key (resets at midnight UTC)
    daily_cap: int = 5000
    
    # Master switch for rate limiting
    limits_enabled: bool = True
    
    # Debug mode
    debug: bool = False
    
    # Authentication mode: alpha (free), prod (paid), or both
    # Default to 'both' - check both alpha_users and users tables
    # (alpha_users will be renamed to users when we exit alpha)
    mode: Literal["alpha", "prod", "both"] = "both"

    @computed_field
    @property
    def api_keys(self) -> List[str]:
        """Parse comma-separated API keys into list."""
        if not self.api_keys_raw:
            return []
        return [v.strip() for v in self.api_keys_raw.split(",") if v.strip()]
    
    @computed_field
    @property
    def allowed_origins(self) -> List[str]:
        """Parse comma-separated allowed origins into list."""
        if not self.allowed_origins_raw:
            return []
        return [v.strip() for v in self.allowed_origins_raw.split(",") if v.strip()]


# Database URL (read separately since it doesn't have the ASPECT_CODE_ prefix)
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Global settings instance
settings = Settings()
