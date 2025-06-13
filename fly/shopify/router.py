from fastapi import APIRouter, Depends, HTTPException, Header, Request, Body
from fastapi.security.api_key import APIKeyHeader
from typing import Dict, Any, Optional, List
import logging
from .models import (
    ShopifyCheckoutRequest, 
    ShopifyWebhookPayload, 
    OrderTransactionRequest,
    ShopifyConfigCreate,
    OrderStatus
)
from .service import ShopifyService
from .config import ShopifyConfigManager
from .client import ShopifyApiClient
import sys
import os

# Add the parent directory to the path to import from main.py
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nodeless import PaymentHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/shopify", tags=["shopify"])

# Dependencies
from config import config
API_KEY_NAME = config.API_KEY_NAME
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

async def get_api_key(api_key: str = Header(None, alias=API_KEY_NAME)):
    # This should match the validation in main.py
    
    if not config.API_SECRET:
        raise HTTPException(status_code=500, detail="API key not configured on server")
    
    if api_key != config.API_SECRET:
        raise HTTPException(
            status_code=401,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key

def get_shopify_service(db_path: Optional[str] = None):
    try:
        # Get database path from config if not provided
        if not db_path:
            db_path = config.get_shopify_db_path()
        
        config_manager = ShopifyConfigManager(db_path)
        # Import the payment handler getter from main module
        try:
            from main import get_payment_handler
            payment_handler = get_payment_handler()
        except ImportError:
            # Fallback to creating new PaymentHandler
            payment_handler = PaymentHandler()
        
        return ShopifyService(config_manager, payment_handler, db_path)
    except Exception as e:
        logger.error(f"Failed to initialize ShopifyService: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Service initialization error: {str(e)}")

# Endpoints
@router.post("/checkout")
async def process_checkout(
    request: ShopifyCheckoutRequest,
    shop: str = Header(..., description="Shop domain (e.g. my-store.myshopify.com)"),
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Process a checkout request and create a payment invoice"""
    logger.info(f"Processing checkout request for shop {shop}, token {request.checkout_token}")
    
    result = service.process_checkout(shop, request.checkout_token, request.redirect)
    
    if not result.get("success", False):
        logger.error(f"Checkout processing failed: {result.get('error', 'Unknown error')}")
        raise HTTPException(status_code=400, detail=result.get("error", "Checkout processing failed"))
    
    return result


@router.post("/webhook")
async def handle_webhook(
    request: Request,
    shop: str = Header(..., description="Shop domain"),
    shopify_hmac: str = Header(..., alias="X-Shopify-Hmac-Sha256"),
    shopify_topic: str = Header(..., alias="X-Shopify-Topic"),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Handle webhooks from Shopify"""
    logger.info(f"Received webhook from shop {shop}, topic {shopify_topic}")
    
    # Get the raw request body for HMAC verification
    body = await request.body()
    body_str = body.decode()
    
    # Parse the JSON body
    import json
    try:
        payload = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload in webhook")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    
    # Handle the webhook
    success = service.handle_webhook(shop, shopify_topic, payload, shopify_hmac)
    
    if not success:
        logger.error(f"Webhook handling failed for shop {shop}, topic {shopify_topic}")
        # Return 200 even on error to prevent Shopify from retrying
        return {"success": False, "message": "Webhook handling failed"}
    
    return {"success": True}

@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    shop: str = Header(..., description="Shop domain"),
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Get order details"""
    logger.info(f"Getting order {order_id} for shop {shop}")
    
    order = service.get_order(shop, order_id)
    
    if not order:
        logger.error(f"Order {order_id} not found for shop {shop}")
        raise HTTPException(status_code=404, detail="Order not found")
    
    return order

@router.post("/orders/{order_id}/capture")
async def capture_order(
    order_id: str,
    request: OrderTransactionRequest,
    shop: str = Header(..., description="Shop domain"),
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Capture payment for an order"""
    logger.info(f"Capturing payment for order {order_id}, shop {shop}")
    
    # Get the order from the database
    order = service.get_order(shop, order_id)
    
    if not order:
        logger.error(f"Order {order_id} not found for shop {shop}")
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get the Shopify client
    client = service.get_client(shop)
    
    if not client:
        logger.error(f"No Shopify client found for shop {shop}")
        raise HTTPException(status_code=400, detail="Shop not configured")
    
    # Determine amount to capture
    amount = request.amount or order["amount"]
    
    # Capture the payment
    success = client.create_transaction(order_id, amount)
    
    if not success:
        logger.error(f"Failed to capture payment for order {order_id}")
        raise HTTPException(status_code=400, detail="Failed to capture payment")
    
    # Update order status
    service.update_order_status(shop, order_id, OrderStatus.COMPLETED)
    
    return {"success": True, "order_id": order_id, "amount": amount}

@router.post("/orders/{order_id}/cancel")
async def cancel_order(
    order_id: str,
    request: OrderTransactionRequest,
    shop: str = Header(..., description="Shop domain"),
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Cancel an order"""
    logger.info(f"Cancelling order {order_id}, shop {shop}")
    
    # Get the order from the database
    order = service.get_order(shop, order_id)
    
    if not order:
        logger.error(f"Order {order_id} not found for shop {shop}")
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Get the Shopify client
    client = service.get_client(shop)
    
    if not client:
        logger.error(f"No Shopify client found for shop {shop}")
        raise HTTPException(status_code=400, detail="Shop not configured")
    
    # Cancel the order
    success = client.cancel_order(order_id, request.reason)
    
    if not success:
        logger.error(f"Failed to cancel order {order_id}")
        raise HTTPException(status_code=400, detail="Failed to cancel order")
    
    # Update order status
    service.update_order_status(shop, order_id, OrderStatus.CANCELED)
    
    return {"success": True, "order_id": order_id}

@router.post("/config")
async def create_config(
    config: ShopifyConfigCreate,
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Create or update Shopify configuration"""
    logger.info(f"Creating/updating config for shop {config.shop_url}")
    
    # Save configuration
    from .models import ShopifyConfig
    shop_config = ShopifyConfig(
        shop_url=config.shop_url,
        api_key=config.api_key,
        api_secret=config.api_secret,
        access_token=config.access_token
    )
    
    success = service.config_manager.save_config(shop_config, config.webhook_secret)
    
    if not success:
        logger.error(f"Failed to save config for shop {config.shop_url}")
        raise HTTPException(status_code=400, detail="Failed to save configuration")
    
    return {"success": True, "shop_url": config.shop_url}

@router.get("/verify/{invoice_id}")
async def verify_payment(
    invoice_id: str,
    api_key: str = Depends(get_api_key),
    service: ShopifyService = Depends(get_shopify_service)
):
    """Verify payment status for an invoice"""
    logger.info(f"Verifying payment for invoice {invoice_id}")
    
    status = service.check_payment_status(invoice_id)
    
    # Get the order for this invoice
    order = service.get_order_by_invoice_id(invoice_id)
    
    if not order:
        logger.error(f"No order found for invoice {invoice_id}")
        raise HTTPException(status_code=404, detail="Invoice not found")
    
    return {
        "invoice_id": invoice_id,
        "order_id": order["order_id"],
        "status": status,
        "amount": order["amount"],
        "currency": order["currency"]
    }
