import os
import json
import logging
from typing import Optional, Dict, Any
from .models import ShopifyConfig
from pathlib import Path
import sqlite3

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = os.path.expanduser("~/.shopify_api/shopify.db")


class ShopifyConfigManager:
    """Manages Shopify configuration stored in SQLite"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.getenv("SHOPIFY_DB_PATH", DEFAULT_DB_PATH)
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()
    
    def _init_db(self):
        """Initialize the database schema if it doesn't exist"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create config table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS shopify_config (
                id INTEGER PRIMARY KEY,
                shop_url TEXT UNIQUE,
                api_key TEXT,
                api_secret TEXT,
                access_token TEXT,
                webhook_secret TEXT
            )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Initialized Shopify config database at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize database: {str(e)}")
            raise
    
    def get_config(self, shop_url: str) -> Optional[ShopifyConfig]:
        """Retrieve configuration for a specific shop"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT shop_url, api_key, api_secret, access_token FROM shopify_config WHERE shop_url = ?", 
                (shop_url,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return ShopifyConfig(
                    shop_url=result[0],
                    api_key=result[1],
                    api_secret=result[2],
                    access_token=result[3]
                )
            return None
        except Exception as e:
            logger.error(f"Failed to get config for {shop_url}: {str(e)}")
            return None
    
    def save_config(self, config: ShopifyConfig, webhook_secret: Optional[str] = None) -> bool:
        """Save or update a shop configuration"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if config exists
            cursor.execute(
                "SELECT id FROM shopify_config WHERE shop_url = ?", 
                (config.shop_url,)
            )
            
            result = cursor.fetchone()
            
            if result:
                # Update existing config
                cursor.execute(
                    """
                    UPDATE shopify_config 
                    SET api_key = ?, api_secret = ?, access_token = ?, webhook_secret = ?
                    WHERE shop_url = ?
                    """, 
                    (config.api_key, config.api_secret, config.access_token, webhook_secret, config.shop_url)
                )
            else:
                # Insert new config
                cursor.execute(
                    """
                    INSERT INTO shopify_config (shop_url, api_key, api_secret, access_token, webhook_secret) 
                    VALUES (?, ?, ?, ?, ?)
                    """, 
                    (config.shop_url, config.api_key, config.api_secret, config.access_token, webhook_secret)
                )
            
            conn.commit()
            conn.close()
            logger.info(f"Saved config for shop {config.shop_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to save config for {config.shop_url}: {str(e)}")
            return False
    
    def delete_config(self, shop_url: str) -> bool:
        """Delete a shop configuration"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("DELETE FROM shopify_config WHERE shop_url = ?", (shop_url,))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Deleted config for shop {shop_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete config for {shop_url}: {str(e)}")
            return False

    def get_webhook_secret(self, shop_url: str) -> Optional[str]:
        """Retrieve webhook secret for a specific shop"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT webhook_secret FROM shopify_config WHERE shop_url = ?", 
                (shop_url,)
            )
            
            result = cursor.fetchone()
            conn.close()
            
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get webhook secret for {shop_url}: {str(e)}")
            return None
