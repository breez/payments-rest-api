"""
Configuration management for the payments REST API
Handles feature flags and module enablement
"""
import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Main configuration class for the application"""
    
    # Core API settings
    API_SECRET: Optional[str] = os.getenv("API_SECRET")
    API_KEY_NAME: str = "x-api-key"
    
    # Webhook configuration
    WEBHOOK_URL: Optional[str] = os.getenv('WEBHOOK_URL')
    
    # Feature flags
    SHOPIFY_ENABLED: bool = os.getenv("SHOPIFY_ENABLED", "false").lower() in ("true", "1", "yes", "on")
    
    # Shopify-specific configuration (only relevant if SHOPIFY_ENABLED is True)
    SHOPIFY_DB_PATH: Optional[str] = os.getenv("SHOPIFY_DB_PATH")
    
    @classmethod
    def is_shopify_enabled(cls) -> bool:
        """Check if Shopify integration is enabled"""
        return cls.SHOPIFY_ENABLED
    
    @classmethod
    def get_shopify_db_path(cls) -> Optional[str]:
        """Get the Shopify database path"""
        if cls.SHOPIFY_ENABLED:
            return cls.SHOPIFY_DB_PATH or os.path.expanduser("~/.shopify_api/shopify.db")
        return None
    
    @classmethod
    def validate_config(cls) -> list[str]:
        """Validate configuration and return any errors"""
        errors = []
        
        if not cls.API_SECRET:
            errors.append("API_SECRET environment variable is required")
        
        # Only validate Shopify config if it's enabled
        if cls.SHOPIFY_ENABLED:
            # Note: Shopify configuration is stored in the database
            # We don't require environment variables for individual shops
            pass
            
        return errors


# Global config instance
config = Config() 