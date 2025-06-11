import logging
import time
import json
from typing import Dict, Any, Optional, List, Tuple, Union
from .models import ShopifyOrderInfo, OrderStatus
from .client import ShopifyApiClient
from .config import ShopifyConfigManager
from nodeless import PaymentHandler
import sqlite3
from uuid import uuid4

logger = logging.getLogger(__name__)


class ShopifyService:
    """Business logic for Shopify checkout integration"""
    
    def __init__(self, config_manager: ShopifyConfigManager, payment_handler: PaymentHandler, db_path: Optional[str] = None):
        self.config_manager = config_manager
        self.payment_handler = payment_handler
        self.db_path = db_path or self.config_manager.db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize database tables for order tracking"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create orders table if it doesn't exist
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS shopify_orders (
                id INTEGER PRIMARY KEY,
                shop_url TEXT NOT NULL,
                order_id TEXT NOT NULL,
                checkout_token TEXT NOT NULL,
                invoice_id TEXT,
                amount REAL NOT NULL,
                currency TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                metadata TEXT,
                UNIQUE(shop_url, order_id)
            )
            ''')
            
            conn.commit()
            conn.close()
            logger.info(f"Initialized Shopify orders database at {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize order database: {str(e)}")
            raise
    
    def get_client(self, shop_url: str) -> Optional[ShopifyApiClient]:
        """Get a configured Shopify API client for a shop"""
        config = self.config_manager.get_config(shop_url)
        if not config:
            logger.error(f"No configuration found for shop {shop_url}")
            return None
        
        return ShopifyApiClient(config)
    
    def process_checkout(self, shop_url: str, checkout_token: str, redirect: bool = True) -> Dict[str, Any]:
        """Process a checkout request and create an invoice"""
        try:
            # Get client for the shop
            client = self.get_client(shop_url)
            if not client:
                return {"success": False, "error": "Shop not configured"}
            
            # Check if we already have an invoice for this checkout
            existing_order = self.get_order_by_checkout_token(shop_url, checkout_token)
            if existing_order and existing_order.get("invoice_id"):
                logger.info(f"Found existing invoice {existing_order['invoice_id']} for checkout {checkout_token}")
                return {
                    "success": True,
                    "order_id": existing_order["order_id"],
                    "invoice_id": existing_order["invoice_id"],
                    "redirect_url": f"/invoice/{existing_order['invoice_id']}",
                    "status": existing_order["status"]
                }
            
            # Get order information from Shopify
            order_info = client.get_order_by_checkout_token(checkout_token)
            if not order_info:
                logger.error(f"Could not find order for checkout token {checkout_token}")
                return {"success": False, "error": "Order not found"}
            
            # Create payment invoice using the payment handler
            invoice_response = self.payment_handler.receive_payment(
                amount=int(order_info.amount * 100),  # Convert to satoshis
                payment_method="LIGHTNING",
                description=f"Payment for Shopify order {order_info.order_id}"
            )
            
            if not invoice_response or "destination" not in invoice_response:
                logger.error(f"Failed to create invoice for order {order_info.order_id}")
                return {"success": False, "error": "Failed to create invoice"}
            
            invoice_id = invoice_response["destination"]
            
            # Save order to database
            self.save_order(
                shop_url=shop_url,
                order_id=order_info.order_id,
                checkout_token=checkout_token,
                invoice_id=invoice_id,
                amount=order_info.amount,
                currency=order_info.currency,
                status=OrderStatus.PENDING,
                metadata=order_info.metadata
            )
            
            logger.info(f"Created invoice {invoice_id} for order {order_info.order_id}")
            
            return {
                "success": True,
                "order_id": order_info.order_id,
                "invoice_id": invoice_id,
                "redirect_url": f"/invoice/{invoice_id}",
                "status": OrderStatus.PENDING
            }
            
        except Exception as e:
            logger.error(f"Error processing checkout {checkout_token} for shop {shop_url}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def save_order(self, shop_url: str, order_id: str, checkout_token: str, invoice_id: str, 
                  amount: float, currency: str, status: str, metadata: Dict[str, Any] = None) -> bool:
        """Save order information to the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            metadata_json = json.dumps(metadata or {})
            
            cursor.execute(
                """
                INSERT OR REPLACE INTO shopify_orders 
                (shop_url, order_id, checkout_token, invoice_id, amount, currency, status, created_at, updated_at, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (shop_url, order_id, checkout_token, invoice_id, amount, currency, status, now, now, metadata_json)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"Saved order {order_id} with invoice {invoice_id} to database")
            return True
        except Exception as e:
            logger.error(f"Failed to save order {order_id}: {str(e)}")
            return False
    
    def update_order_status(self, shop_url: str, order_id: str, status: str) -> bool:
        """Update the status of an order"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            now = time.strftime('%Y-%m-%d %H:%M:%S')
            
            cursor.execute(
                """
                UPDATE shopify_orders
                SET status = ?, updated_at = ?
                WHERE shop_url = ? AND order_id = ?
                """,
                (status, now, shop_url, order_id)
            )
            
            conn.commit()
            conn.close()
            
            logger.info(f"Updated order {order_id} status to {status}")
            return True
        except Exception as e:
            logger.error(f"Failed to update order {order_id} status: {str(e)}")
            return False
    
    def get_order(self, shop_url: str, order_id: str) -> Optional[Dict[str, Any]]:
        """Get order information from the database"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT * FROM shopify_orders
                WHERE shop_url = ? AND order_id = ?
                """,
                (shop_url, order_id)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                order_data = dict(row)
                if 'metadata' in order_data and order_data['metadata']:
                    order_data['metadata'] = json.loads(order_data['metadata'])
                return order_data
            
            return None
        except Exception as e:
            logger.error(f"Failed to get order {order_id}: {str(e)}")
            return None
    
    def get_order_by_checkout_token(self, shop_url: str, checkout_token: str) -> Optional[Dict[str, Any]]:
        """Get order information by checkout token"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT * FROM shopify_orders
                WHERE shop_url = ? AND checkout_token = ?
                """,
                (shop_url, checkout_token)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                order_data = dict(row)
                if 'metadata' in order_data and order_data['metadata']:
                    order_data['metadata'] = json.loads(order_data['metadata'])
                return order_data
            
            return None
        except Exception as e:
            logger.error(f"Failed to get order by checkout token {checkout_token}: {str(e)}")
            return None
    
    def get_order_by_invoice_id(self, invoice_id: str) -> Optional[Dict[str, Any]]:
        """Get order information by invoice ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute(
                """
                SELECT * FROM shopify_orders
                WHERE invoice_id = ?
                """,
                (invoice_id,)
            )
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                order_data = dict(row)
                if 'metadata' in order_data and order_data['metadata']:
                    order_data['metadata'] = json.loads(order_data['metadata'])
                return order_data
            
            return None
        except Exception as e:
            logger.error(f"Failed to get order by invoice ID {invoice_id}: {str(e)}")
            return None
    
    def check_payment_status(self, invoice_id: str) -> str:
        """Check the payment status of an invoice"""
        try:
            # Get the payment from payment handler
            payments = self.payment_handler.list_payments()
            
            # Find the payment matching our invoice ID (destination)
            for payment in payments:
                if payment.get("destination") == invoice_id and payment.get("status") == "SUCCEEDED":
                    return OrderStatus.COMPLETED
            
            # If no completed payment is found, check if the order is in our database
            order = self.get_order_by_invoice_id(invoice_id)
            if order:
                return order["status"]
            
            return OrderStatus.PENDING
        except Exception as e:
            logger.error(f"Failed to check payment status for invoice {invoice_id}: {str(e)}")
            return OrderStatus.PENDING
    
    def process_payment_notification(self, invoice_id: str, status: str) -> bool:
        """Process a payment notification and update the order status"""
        try:
            # Get the order for this invoice
            order = self.get_order_by_invoice_id(invoice_id)
            if not order:
                logger.error(f"No order found for invoice {invoice_id}")
                return False
            
            shop_url = order["shop_url"]
            order_id = order["order_id"]
            
            # Update order status in our database
            if status == "SUCCEEDED":
                new_status = OrderStatus.COMPLETED
            elif status == "FAILED":
                new_status = OrderStatus.FAILED
            else:
                new_status = OrderStatus.PENDING
            
            self.update_order_status(shop_url, order_id, new_status)
            
            # If payment completed, capture the transaction in Shopify
            if new_status == OrderStatus.COMPLETED:
                client = self.get_client(shop_url)
                if client:
                    if client.create_transaction(order_id, order["amount"]):
                        logger.info(f"Captured transaction for order {order_id}")
                    else:
                        logger.error(f"Failed to capture transaction for order {order_id}")
                        return False
            
            return True
        except Exception as e:
            logger.error(f"Error processing payment notification for invoice {invoice_id}: {str(e)}")
            return False
    
    def handle_webhook(self, shop_url: str, topic: str, payload: Dict[str, Any], hmac_header: str) -> bool:
        """Handle a webhook from Shopify"""
        try:
            # Verify webhook signature
            webhook_secret = self.config_manager.get_webhook_secret(shop_url)
            if not webhook_secret:
                logger.error(f"No webhook secret found for shop {shop_url}")
                return False
            
            client = self.get_client(shop_url)
            if not client:
                logger.error(f"No client found for shop {shop_url}")
                return False
            
            # Convert payload back to string for verification
            payload_string = json.dumps(payload)
            
            if not client.verify_webhook(payload_string, hmac_header, webhook_secret):
                logger.error(f"Invalid webhook signature for shop {shop_url}")
                return False
            
            # Process different webhook topics
            if topic == "orders/paid":
                order_id = payload.get("id")
                if not order_id:
                    logger.error("No order ID in webhook payload")
                    return False
                
                # Verify this order is in our database
                order = self.get_order(shop_url, str(order_id))
                if not order:
                    logger.warning(f"Order {order_id} not found in database, might not be processed by us")
                    return True  # Not an error, just not our order
                
                # Order is already paid in Shopify, make sure our status is updated
                self.update_order_status(shop_url, str(order_id), OrderStatus.COMPLETED)
                logger.info(f"Updated order {order_id} status to COMPLETED from webhook")
            
            elif topic == "orders/cancelled":
                order_id = payload.get("id")
                if not order_id:
                    logger.error("No order ID in webhook payload")
                    return False
                
                # Update order status
                order = self.get_order(shop_url, str(order_id))
                if order:
                    self.update_order_status(shop_url, str(order_id), OrderStatus.CANCELED)
                    logger.info(f"Updated order {order_id} status to CANCELED from webhook")
            
            # Add more webhook handlers as needed
            
            return True
        except Exception as e:
            logger.error(f"Error handling webhook from shop {shop_url}: {str(e)}")
            return False
